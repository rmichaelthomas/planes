"""Tests for the static effect analyser.

The central test is the oracle: for any program, every effect that actually
occurs at runtime must appear in the statically computed surface. If the
analyser misses something a run performs, it is unsound, and an unsound
effect surface is worse than none — it would tell a user a package is safe
when it is not.
"""
import json
import sys

from interp import Interpreter
from shapes import Effect, analyse, analyse_file, diff

STORIES = {
    1: {"title": "Rust 2.0 released",       "score": 450},
    2: {"title": "Why Go is fine",          "score": 300},
    3: {"title": "Rewriting grep in Rust",  "score": 210},
    4: {"title": "A rust postmortem",       "score": 150},
}


def stub_http(url):
    if "topstories" in url:
        return json.dumps(list(STORIES.keys()))
    sid = int(url.split("/item/")[1].split(".json")[0])
    return json.dumps(STORIES[sid])


def run(src, **kw):
    i = Interpreter(**kw)
    i.run(src)
    return i


def check_oracle(src, **kw):
    """Every runtime effect must be covered by the static surface.

    Targets are compared by kind and boundary, plus target match where the
    static target is a literal. Computed targets are matched by their
    non-variable parts, since the static side cannot know the runtime value.
    """
    surface = analyse(src)
    i = run(src, **kw)

    static_by_kind = {}
    for e in surface.effects:
        static_by_kind.setdefault(e.kind, []).append(e)

    for actual in i.effects:
        kind, target = actual[0], actual[1]
        candidates = static_by_kind.get(kind, [])
        assert candidates, (
            f"runtime performed {kind!r} on {target!r} but the static "
            f"surface has no {kind!r} at all — ANALYSER IS UNSOUND")
        matched = False
        for c in candidates:
            if not c.computed and c.target == target:
                matched = True
                break
            if c.computed:
                # pattern match: every literal chunk must appear in order
                chunks = [p for p in c.target.split("{...}") if p]
                pos, ok = 0, True
                for chunk in chunks:
                    j = str(target).find(chunk, pos)
                    if j < 0:
                        ok = False
                        break
                    pos = j + len(chunk)
                if ok:
                    matched = True
                    break
        assert matched, (
            f"runtime performed {kind} on {target!r}, not covered by static "
            f"surface {[str(c) for c in candidates]} — ANALYSER IS UNSOUND")
    return surface, i


# ================================================================ soundness

def test_oracle_hn_scraper():
    """The main event: static surface covers every runtime effect."""
    src = open("hn.planes").read()
    surface, i = check_oracle(src, http=stub_http)
    assert len(i.effects) == 9
    assert surface.touches("network")
    assert surface.touches("file")


def test_oracle_ordinary_program():
    src = open("ordinary.planes").read()
    surface, i = check_oracle(src, fs={})
    assert not surface.touches("network")
    assert surface.touches("file")


def test_oracle_pure_program():
    src = "x = 5\ny = 3\nz = x + y"
    surface, i = check_oracle(src)
    assert surface.is_pure()
    assert i.effects == []


def test_oracle_recursive_function():
    src = ('use file\n'
           'to countdown of n:\n'
           '  show text of n\n'
           '  if n > 0:\n'
           '    give countdown of (n - 1)\n'
           '  give 0\n\n'
           'countdown of 3')
    surface, i = check_oracle(src)
    assert surface.touches("console")


def test_oracle_effect_inside_comprehension():
    src = ('use http\n'
           'to detail of n:\n'
           '  give ask "https://hacker-news.firebaseio.com/v0/item/" '
           '+ text of n + ".json"\n\n'
           'rs = for each i in [1, 2, 3]: detail of i')
    surface, i = check_oracle(src, http=stub_http)
    assert len(i.effects) == 3
    assert len(surface.at("network")) == 1     # one site, three executions


def test_oracle_effect_inside_string_for_each():
    """A string source is walked with the loop variable widened to UNKNOWN,
    the same as any other for-each source -- the analyser never inspects
    node.source's runtime type, so no oracle-specific change was needed for
    text iteration (interp.py's `for each` fix). This just confirms it."""
    src = 'use file\nfor each c in "abc":\n  write c to "out.json"\n'
    surface, i = check_oracle(src, fs={})
    assert len(i.effects) == 3
    assert len(surface.at("file")) == 1        # one site, three executions


def test_oracle_effect_in_untaken_branch():
    """A branch that does not run this time still belongs in the surface."""
    src = ('use file\n'
           'x = 1\n'
           'if x > 100:\n'
           '  write [1] to "never.json"\n'
           'else:\n'
           '  show "small"')
    surface, i = check_oracle(src)
    assert surface.touches("file"), "untaken branch must still be in the surface"
    assert not any(e[0] == "write" for e in i.effects), "it should not have run"


# ================================================================ correctness

def test_pure_program_is_pure():
    s = analyse("to add of a, b:\n  give a + b\n\nr = add of 2, 3")
    assert s.is_pure()
    assert s.render().startswith("pure")


def test_transitive_effects_through_calls():
    """A caller inherits the effects of everything it calls."""
    src = ('use http\n'
           'to inner:\n'
           '  give ask "https://example.com/a.json"\n\n'
           'to middle:\n'
           '  give inner\n\n'
           'to outer:\n'
           '  give middle\n\n'
           'r = outer')
    s = analyse(src)
    assert s.touches("network"), "effects must propagate up the call graph"
    assert s.functions["outer"], "outer must inherit inner's ask"
    assert s.functions["middle"]


def test_mutual_recursion_terminates():
    src = ('use http\n'
           'to ping of n:\n'
           '  if n > 0:\n'
           '    give pong of (n - 1)\n'
           '  give ask "https://example.com/a.json"\n\n'
           'to pong of n:\n'
           '  give ping of (n - 1)\n\n'
           'r = ping of 3')
    s = analyse(src)
    assert s.touches("network")
    assert s.functions["pong"], "pong must inherit ping's ask through recursion"


def test_literal_target_is_exact():
    s = analyse('use http\nx = ask "https://example.com/a.json"')
    e = s.at("network")[0]
    assert e.target == "https://example.com/a.json"
    assert not e.computed


def test_computed_target_keeps_the_host():
    """A genuinely unknown part is marked, but the host stays visible."""
    s = analyse('use http\n'
                'to f of n:\n'
                '  give ask "https://example.com/item/" + text of n + ".json"\n\n'
                'xs = for each i in [1, 2]: f of i')
    e = s.at("network")[0]
    assert e.computed, "loop variable is not statically known"
    assert "https://example.com/item/" in e.target
    assert ".json" in e.target
    assert "{...}" in e.target


# ================================================================ constants

def test_target_resolves_through_a_variable():
    s = analyse('use http\n'
                'let base = "https://api.example.com"\n'
                'let endpoint = base + "/users"\n'
                'x = ask endpoint')
    e = s.at("network")[0]
    assert e.target == "https://api.example.com/users"
    assert not e.computed, "fully known target must not be marked computed"


def test_target_resolves_through_a_call_argument():
    """`get of "https://..."` reports that URL, not {...}."""
    s = analyse('use http\n'
                'to get of url:\n'
                '  give ask url\n\n'
                'r = get of "https://api.example.com/data.json"')
    e = s.at("network")[0]
    assert e.target == "https://api.example.com/data.json"
    assert not e.computed


def test_target_stays_unknown_when_it_really_is():
    s = analyse('use http\n'
                'to get of url:\n'
                '  give ask url\n\n'
                'xs = for each u in [1, 2]: get of u')
    e = s.at("network")[0]
    assert e.computed, "a loop variable must widen to unknown"


def test_recursive_function_is_never_specialised():
    """`countdown of 3` shows 3, 2, 1 — binding n=3 would report only `show 3`.

    This was a real unsoundness found by the oracle.
    """
    src = ('to countdown of n:\n'
           '  show text of n\n'
           '  if n > 0:\n'
           '    give countdown of (n - 1)\n'
           '  give 0\n\n'
           'countdown of 3')
    s = analyse(src)
    e = s.at("console")[0]
    assert e.computed, "recursive callee must keep its generic surface"


def test_text_of_a_known_number_is_known():
    s = analyse('use file\n'
                'let n = 7\n'
                'write [1] to "out" + text of n + ".json"')
    e = s.at("file")[0]
    assert e.target == "out7.json"
    assert not e.computed


def test_constant_folding_does_not_loop_on_recursion():
    """A recursive value-returning function must not hang the analyser."""
    s = analyse('use http\n'
                'to grow of n:\n'
                '  give grow of (n + 1)\n\n'
                'x = ask "https://example.com/" + text of (grow of 1)')
    assert s.touches("network")


def test_variable_rebound_in_a_branch_widens():
    """A name a branch may have reassigned is not knowable afterwards.

    This was a real unsoundness: without widening at the join, the surface
    reported the pre-branch value while the program asked the new one.
    """
    src = ('use http\n'
           'let u = "https://example.com/default.json"\n'
           'if 1 > 0:\n'
           '  let u = "https://example.com/other.json"\n'
           'x = ask u')
    check_oracle(src, http=lambda url: json.dumps([1]))


def test_variable_rebound_in_a_loop_widens():
    src = ('use http\n'
           'let u = "https://example.com/default.json"\n'
           'for each i in [1, 2]:\n'
           '  let u = "https://example.com/other.json"\n'
           'x = ask u')
    check_oracle(src, http=lambda url: json.dumps([1]))


def test_sequential_rebinding_tracks_both_targets():
    src = ('use http\n'
           'let u = "https://example.com/one.json"\n'
           'x = ask u\n'
           'let u = "https://example.com/two.json"\n'
           'y = ask u')
    s, _ = check_oracle(src, http=lambda url: json.dumps([1]))
    assert len(s.at("network")) == 2
    assert set(s.targets("ask")) == {
        "https://example.com/one.json", "https://example.com/two.json"}


def test_one_function_called_with_known_and_unknown_args():
    """Specialisation must not drop the generic effect for other call sites."""
    src = ('use http\n'
           'to get of url:\n'
           '  give ask url\n\n'
           'a = get of "https://example.com/known.json"\n'
           'b = for each u in ["https://example.com/x.json"]: get of u')
    s = analyse(src)
    targets = s.targets("ask")
    assert "https://example.com/known.json" in targets
    assert any("{...}" in t for t in targets), \
        "the unknown call site must still be represented"


def test_boundaries_reported():
    s = analyse_file("hn.planes")
    assert set(s.boundaries()) == {"network", "file", "console"}


def test_targets_query():
    s = analyse_file("hn.planes")
    assert "results.json" in s.targets("write")


def test_declared_but_unused_module():
    s = analyse('use http\nuse file\nx = 5')
    assert set(s.declared_but_unused()) == {"http", "file"}


def test_used_and_declared_is_clean():
    s = analyse('use http\nx = ask "https://example.com/a.json"')
    assert s.declared_but_unused() == []
    assert s.used_but_undeclared() == []


def test_used_but_undeclared_is_caught_statically():
    """Static analysis catches the missing `use` without running anything."""
    s = analyse('x = ask "https://example.com/a.json"')
    missing = s.used_but_undeclared()
    assert len(missing) == 1
    assert missing[0].kind == "ask"


def test_effects_deduplicated_by_site():
    """Two calls to one function are one effect, not two."""
    src = ('use http\n'
           'to f:\n'
           '  give ask "https://example.com/a.json"\n\n'
           'a = f\n'
           'b = f')
    s = analyse(src)
    assert len(s.at("network")) == 1


def test_analysis_does_not_execute():
    """The analyser must never perform an effect. Boom if it does."""
    def boom(url):
        raise AssertionError("analyser performed a network call")
    s = analyse_file("hn.planes")     # no interpreter, no http at all
    assert s.touches("network")       # it found the effect without doing it


# ================================================================ diffing

def test_diff_detects_new_network_send():
    """The upgrade-diff use case."""
    before = analyse('use file\nwrite [1] to "out.json"')
    after = analyse('use file\nuse http\n'
                    'x = ask "https://tracker.example.com/collect"\n'
                    'write [1] to "out.json"')
    d = diff(before, after)
    assert not d.is_empty()
    assert "network" in d.new_boundaries
    assert any("tracker.example.com" in e.target for e in d.added)


def test_diff_of_identical_programs_is_empty():
    src = open("hn.planes").read()
    assert diff(analyse(src), analyse(src)).is_empty()


def test_diff_detects_removed_effect():
    before = analyse('use file\nwrite [1] to "out.json"')
    after = analyse('x = 5')
    d = diff(before, after)
    assert d.removed
    assert "file" in d.dropped_boundaries


def test_diff_render_names_the_new_boundary():
    before = analyse('x = 5')
    after = analyse('use http\nx = ask "https://example.com/a.json"')
    text = diff(before, after).render()
    assert "NEW BOUNDARIES CROSSED" in text
    assert "network" in text


# ================================================================ libraries

def test_library_with_no_toplevel_is_not_pure():
    """A library's effects live behind its functions. Reporting `pure`
    because nothing runs at load time is the exact lie the analyser prevents."""
    src = 'use http\nto get of url:\n  give ask url'
    s = analyse(src)
    assert s.effects == [], "nothing runs at top level"
    assert not s.is_pure(), "but the package is NOT pure"
    assert s.is_library()
    assert s.touches("network")


def test_genuinely_pure_library_is_pure():
    s = analyse("to square of n:\n  give n * n")
    assert s.is_pure()
    assert not s.is_library()


def test_effect_hidden_two_calls_deep_is_found():
    """An innocuously-named function whose network call is two hops down."""
    src = ('use http\n'
           'to helper of n:\n'
           '  give n + 1\n\n'
           'to compute of n:\n'
           '  let r = helper of n\n'
           '  give beacon of r\n\n'
           'to beacon of r:\n'
           '  give ask "https://collect.example.com/?v=" + text of r')
    s = analyse(src)
    assert s.touches("network")
    assert any("collect.example.com" in e.target for e in s.at("network"))
    assert s.functions["compute"], "compute must inherit beacon's ask"


def test_library_render_says_so():
    s = analyse('use http\nto get of url:\n  give ask url')
    assert "library" in s.render()


# ================================================================ modules

def check_oracle_file(path, **kw):
    """Oracle for a multi-file program: static surface covers the real run."""
    from shapes import analyse_file as af
    surface = af(path)
    i = Interpreter(**kw)
    i.run_file(path)
    static_by_kind = {}
    for e in surface.effects:
        static_by_kind.setdefault(e.kind, []).append(e)
    for actual in i.effects:
        kind, target = actual[0], actual[1]
        cands = static_by_kind.get(kind, [])
        assert cands, f"runtime did {kind} on {target!r}, static has none"
        ok = False
        for c in cands:
            if not c.computed and c.target == target:
                ok = True
                break
            if c.computed:
                chunks = [p for p in c.target.split("{...}") if p]
                pos, good = 0, True
                for ch in chunks:
                    j = str(target).find(ch, pos)
                    if j < 0:
                        good = False
                        break
                    pos = j + len(ch)
                if good:
                    ok = True
                    break
        assert ok, (f"runtime did {kind} on {target!r}, not covered by "
                    f"{[str(c) for c in cands]} — ANALYSER IS UNSOUND")
    return surface, i


def test_module_graph_loads_in_dependency_order():
    import os

    from modules import load_graph
    graph = load_graph("demo/app/main.planes")
    names = [os.path.basename(p) for p, _ in graph]
    assert names.index("config.planes") < names.index("net.planes")
    assert names.index("net.planes") < names.index("main.planes")


def test_effect_in_an_imported_file_is_found():
    """main.planes has no network code; the ask lives two files away."""
    from shapes import analyse_file as af
    s = af("demo/app/main.planes")
    assert s.touches("network")
    assert any("pypi.org" in e.target for e in s.at("network"))


def test_single_file_view_reports_unresolved():
    """Without following imports, the analyser says what it cannot see."""
    from shapes import analyse_file as af
    s = af("demo/app/main.planes", follow=False)
    assert not s.touches("network")
    assert s.unresolved, "must admit there are calls it cannot resolve"


def test_constant_crosses_file_boundaries():
    """The base URL is in config.planes, the ask in net.planes."""
    from shapes import analyse_file as af
    s = af("demo/app/main.planes")
    exact = [e for e in s.at("network") if not e.computed]
    assert any(e.target == "https://pypi.org/pypi/requests/json" for e in exact)


def test_module_cycle_is_an_error_not_a_hang():
    import os

    from modules import ModuleError, load_graph
    os.makedirs("demo/cycle", exist_ok=True)
    open("demo/cycle/a.planes", "w").write("use b\nto a thing:\n  give 1\n")
    open("demo/cycle/b.planes", "w").write("use a\nto b thing:\n  give 2\n")
    try:
        load_graph("demo/cycle/a.planes")
        assert False, "should raise"
    except ModuleError as e:
        assert "cycle" in str(e)
    finally:
        import shutil
        shutil.rmtree("demo/cycle", ignore_errors=True)


def test_missing_module_names_the_fix():
    import os

    from modules import ModuleError, load_graph
    os.makedirs("demo/broken", exist_ok=True)
    open("demo/broken/m.planes", "w").write("use nowhere\nx = 1\n")
    try:
        load_graph("demo/broken/m.planes")
        assert False, "should raise"
    except ModuleError as e:
        assert "nowhere" in str(e)
        assert e.fix
    finally:
        import shutil
        shutil.rmtree("demo/broken", ignore_errors=True)


def test_builtin_modules_are_not_files():
    from modules import resolve
    assert resolve("http", "demo/app/main.planes") is None
    assert resolve("file", "demo/app/main.planes") is None


# ================================================================ namespacing

def _write(dirname, files):
    import os
    os.makedirs(dirname, exist_ok=True)
    for fname, body in files.items():
        open(os.path.join(dirname, fname), "w").write(body)


def _clean(dirname):
    import shutil
    shutil.rmtree(dirname, ignore_errors=True)


def test_two_modules_defining_one_name_is_an_error():
    """Silently letting load order decide would make the same program
    behave differently depending on the order of its `use` lines."""
    from modules import ModuleError, check_collisions, load_graph
    _write("demo/_clash", {
        "a.planes": 'to greet:\n  give "a"\n',
        "b.planes": 'to greet:\n  give "b"\n',
        "main.planes": "use a\nuse b\n\nshow greet\n",
    })
    try:
        check_collisions(load_graph("demo/_clash/main.planes"))
        assert False, "should raise"
    except ModuleError as e:
        assert "greet" in str(e)
        assert "a.planes" in str(e) and "b.planes" in str(e)
        assert e.fix
    finally:
        _clean("demo/_clash")


def test_shadowing_an_imported_name_is_an_error():
    from modules import ModuleError, check_collisions, load_graph
    _write("demo/_shadow", {
        "lib.planes": 'to helper:\n  give "lib"\n',
        "main.planes": 'use lib\n\nto helper:\n  give "main"\n\nshow helper\n',
    })
    try:
        check_collisions(load_graph("demo/_shadow/main.planes"))
        assert False, "should raise"
    except ModuleError as e:
        assert "helper" in str(e)
    finally:
        _clean("demo/_shadow")


def test_collision_stops_the_interpreter():
    from modules import ModuleError
    _write("demo/_clash2", {
        "a.planes": 'to greet:\n  give "a"\n',
        "b.planes": 'to greet:\n  give "b"\n',
        "main.planes": "use a\nuse b\n\nshow greet\n",
    })
    try:
        Interpreter().run_file("demo/_clash2/main.planes")
        assert False, "should raise rather than silently pick one"
    except ModuleError:
        pass
    finally:
        _clean("demo/_clash2")


def test_collision_stops_the_analyser():
    """A surface for a program with an ambiguous call graph would be a guess."""
    from modules import ModuleError
    from shapes import analyse_file as af
    _write("demo/_clash3", {
        "a.planes": 'use http\nto grab:\n  give ask "https://a.example.com/x"\n',
        "b.planes": 'use http\nto grab:\n  give ask "https://b.example.com/x"\n',
        "main.planes": "use a\nuse b\n\nr = grab\n",
    })
    try:
        af("demo/_clash3/main.planes")
        assert False, "should refuse to publish an ambiguous surface"
    except ModuleError:
        pass
    finally:
        _clean("demo/_clash3")


def test_diamond_dependency_is_not_a_collision():
    """Two modules importing the same third module share one copy."""
    _write("demo/_diamond", {
        "base.planes": 'to shared value:\n  give "base"\n',
        "left.planes": 'use base\nto left thing:\n  give shared value + "-l"\n',
        "right.planes": 'use base\nto right thing:\n  give shared value + "-r"\n',
        "main.planes": "use left\nuse right\n\nshow left thing\nshow right thing\n",
    })
    try:
        out = Interpreter().run_file("demo/_diamond/main.planes")
        assert out == ["base-l", "base-r"]
    finally:
        _clean("demo/_diamond")


def test_load_order_does_not_change_behaviour():
    """With collisions banned, `use` order cannot affect the result."""
    files = {
        "one.planes": 'to alpha bit:\n  give "1"\n',
        "two.planes": 'to beta bit:\n  give "2"\n',
    }
    _write("demo/_order", dict(
        files, **{"main.planes": "use one\nuse two\n\nshow alpha bit + beta bit\n"}))
    try:
        a = Interpreter().run_file("demo/_order/main.planes")
    finally:
        _clean("demo/_order")
    _write("demo/_order2", dict(
        files, **{"main.planes": "use two\nuse one\n\nshow alpha bit + beta bit\n"}))
    try:
        b = Interpreter().run_file("demo/_order2/main.planes")
    finally:
        _clean("demo/_order2")
    assert a == b == ["12"]


def test_same_name_in_unrelated_graphs_is_fine():
    """Collision is per program, not global. Two apps may both define `main`."""
    _write("demo/_appA", {"main.planes": 'to run:\n  give 1\n\nshow text of run\n'})
    _write("demo/_appB", {"main.planes": 'to run:\n  give 2\n\nshow text of run\n'})
    try:
        assert Interpreter().run_file("demo/_appA/main.planes") == ["1"]
        assert Interpreter().run_file("demo/_appB/main.planes") == ["2"]
    finally:
        _clean("demo/_appA")
        _clean("demo/_appB")


# ================================================================ renaming

def test_rename_resolves_a_collision():
    """Two modules exporting one name, neither editable by the consumer."""
    _write("demo/_ren", {
        "loader.planes": 'use http\nto load record of id:\n'
                         '  give ask "https://example.com/" + id + ".json"\n',
        "cache.planes": 'use file\nto load record of id:\n'
                        '  give read "cache-" + id + ".json"\n',
        "main.planes": "use loader\n"
                       "use cache with load record as load cached\n\n"
                       'fresh = load record of "x"\n'
                       'old = load cached of "x"\n',
    })
    try:
        i = Interpreter(http=lambda u: json.dumps({"ok": 1}),
                        fs={"cache-x.json": '{"cached": true}'})
        i.run_file("demo/_ren/main.planes")
        kinds = [e[0] for e in i.effects]
        assert "ask" in kinds and "read" in kinds, \
            "both modules must be reachable after the rename"
    finally:
        _clean("demo/_ren")


def test_analyser_sees_both_surfaces_after_a_rename():
    from shapes import analyse_file as af
    _write("demo/_ren2", {
        "loader.planes": 'use http\nto load record of id:\n'
                         '  give ask "https://example.com/" + id + ".json"\n',
        "cache.planes": 'use file\nto load record of id:\n'
                        '  give read "cache-" + id + ".json"\n',
        "main.planes": "use loader\n"
                       "use cache with load record as load cached\n\n"
                       'fresh = load record of "x"\n'
                       'old = load cached of "x"\n',
    })
    try:
        s = af("demo/_ren2/main.planes")
        assert s.touches("network"), "the un-renamed module's ask must show"
        assert s.touches("file"), "the renamed module's read must show"
        assert not s.unresolved, f"unresolved: {s.unresolved}"
    finally:
        _clean("demo/_ren2")


def test_rename_replaces_rather_than_aliases():
    """Registering both names would put the collision straight back.

    The rename target is `b greet`, not `greet b` -- the latter would
    share the prefix `greet` with the original name still in scope from
    `a`, and `show greet b` would then be amber (§69.5 site 1): `greet`
    alone and `greet b` are both known names, and nothing says which was
    meant.
    """
    _write("demo/_ren3", {
        "a.planes": 'to greet:\n  give "a"\n',
        "b.planes": 'to greet:\n  give "b"\n',
        "main.planes": "use a\nuse b with greet as b greet\n\n"
                       "show greet\nshow b greet\n",
    })
    try:
        out = Interpreter().run_file("demo/_ren3/main.planes")
        assert out == ["a", "b"], f"got {out}"
    finally:
        _clean("demo/_ren3")


def test_a_module_still_calls_its_own_functions_after_being_renamed():
    """Importers see the new name; the module sees its own."""
    _write("demo/_ren4", {
        "lib.planes": 'to inner:\n  give 5\n\n'
                      'to outer:\n  give inner\n',
        "main.planes": "use lib with outer as lib outer\n\n"
                       "r = lib outer\n",
    })
    try:
        i = Interpreter()
        i.run_file("demo/_ren4/main.planes")
        assert i.env.get("r").value == 5
    finally:
        _clean("demo/_ren4")


def test_several_renames_from_one_module():
    _write("demo/_ren5", {
        "lib.planes": 'to one:\n  give 1\n\nto two:\n  give 2\n',
        "main.planes": "use lib with one as lib one with two as lib two\n\n"
                       "a = lib one\nb = lib two\n",
    })
    try:
        i = Interpreter()
        i.run_file("demo/_ren5/main.planes")
        assert i.env.get("a").value == 1
        assert i.env.get("b").value == 2
    finally:
        _clean("demo/_ren5")


def test_renaming_into_an_existing_name_still_collides():
    """A rename can create a collision as easily as it resolves one."""
    from modules import ModuleError, check_collisions, load_graph
    _write("demo/_ren6", {
        "a.planes": 'to greet:\n  give "a"\n',
        "b.planes": 'to hello:\n  give "b"\n',
        "main.planes": "use a\nuse b with hello as greet\n\nshow greet\n",
    })
    try:
        check_collisions(load_graph("demo/_ren6/main.planes"))
        assert False, "should raise"
    except ModuleError as e:
        assert "greet" in str(e)
    finally:
        _clean("demo/_ren6")


def test_collision_error_suggests_a_rename():
    from modules import ModuleError, check_collisions, load_graph
    _write("demo/_ren7", {
        "a.planes": 'to greet:\n  give "a"\n',
        "b.planes": 'to greet:\n  give "b"\n',
        "main.planes": "use a\nuse b\n\nshow greet\n",
    })
    try:
        check_collisions(load_graph("demo/_ren7/main.planes"))
        assert False, "should raise"
    except ModuleError as e:
        assert "with greet as" in e.fix, f"fix was: {e.fix}"
    finally:
        _clean("demo/_ren7")


# ================================================================ adversarial

ADVERSARIAL = {
    "effect in a where-clause": '''use http
to probe of n:
  give count of (ask "https://example.com/a.json") > 0

xs = for each i in [1, 2] where probe of i: i''',

    "effect in a comprehension source": '''use http
to src:
  give ask "https://example.com/list.json"

xs = for each i in src: i''',

    "effect inside or-fail": '''use http
x = ask "https://example.com/a.json"
  or fail as down''',

    "effect in a function nested inside a function": '''use http
to outer:
  to inner:
    give ask "https://example.com/deep.json"
  give inner

r = outer''',

    "effect in an if-condition": '''use http
to check:
  give count of (ask "https://example.com/flag.json") > 0

if check:
  show "yes"''',

    "effect as an argument to another call": '''use http
to id of x:
  give x

r = id of (ask "https://example.com/arg.json")''',

    "effect in a list literal": '''use http
xs = [ask "https://example.com/one.json", 2]''',

    "effect behind a field access": '''use http
r = (ask "https://example.com/rec.json").a''',

    "function called before it is defined": '''use http
r = later

to later:
  give ask "https://example.com/late.json"''',
}


def test_adversarial_no_effect_escapes():
    """Ten attempts to smuggle an effect past the analyser. All must fail."""
    def any_stub(url):
        # a list of records: works as a collection AND supports .a
        if "rec" in url:
            return json.dumps({"a": 1})
        return json.dumps([1, 2, 3])

    for name, src in ADVERSARIAL.items():
        try:
            check_oracle(src, http=any_stub)
        except AssertionError as e:
            raise AssertionError(f"[{name}] {e}")


# ================================================================ published form

def test_json_and_human_views_agree():
    """A published artifact must not contradict the surface a person reads.

    It did: `sneaky.planes` emitted `"effects": []` beside
    `"boundaries": ["network"]`, because the JSON reported only top-level
    effects while the human view reported the declared surface. A consumer
    parsing `effects` would have concluded the package does nothing.
    """
    import glob

    from shapes import analyse_file as af
    from shapes_cli import as_json

    for path in sorted(glob.glob("demo/pkgs/*.planes")):
        s = af(path)
        doc = as_json(s, path)
        kinds_in_effects = {e["kind"] for e in doc["effects"]}
        assert set(doc["kinds"]) == kinds_in_effects, (
            f"{path}: 'kinds' says {doc['kinds']} but 'effects' contains "
            f"{sorted(kinds_in_effects)}")
        boundaries = {e["boundary"] for e in doc["effects"]}
        assert set(doc["boundaries"]) == boundaries, (
            f"{path}: 'boundaries' and 'effects' disagree")
        assert doc["pure"] == (not doc["effects"]), \
            f"{path}: 'pure' disagrees with 'effects'"


def test_json_declares_its_format_version():
    """A consumer that does not recognise the version should refuse the
    document rather than guess at field meanings."""
    from shapes import analyse_file as af
    from shapes_cli import FORMAT_VERSION, as_json
    doc = as_json(af("demo/pkgs/sneaky.planes"), "demo/pkgs/sneaky.planes")
    assert doc["format"] == FORMAT_VERSION


def test_json_separates_what_runs_on_load_from_what_is_offered():
    """Both facts matter and they are different: a library offers network
    reach without performing it at load."""
    from shapes import analyse_file as af
    from shapes_cli import as_json
    doc = as_json(af("demo/pkgs/sneaky.planes"), "demo/pkgs/sneaky.planes")
    assert doc["kind"] == "library"
    assert doc["effects"], "it offers a network call"
    assert doc["runs_on_load"] == [], "it performs nothing at load"


def test_json_reports_whether_the_surface_is_complete():
    import os
    import tempfile

    from shapes_cli import as_json
    d = tempfile.mkdtemp()
    p = os.path.join(d, "m.planes")
    open(p, "w").write('foreign x of a from "m.f"\nr = x of 1')
    try:
        from shapes import analyse_file as af
        doc = as_json(af(p), p)
        assert doc["complete"] is False, \
            "a surface with an undeclared foreign is not complete"
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


# ================================================================ derivation

def test_derivation_reaches_a_literal():
    s = analyse('use http\nlet u = "https://x"\nx = ask u')
    e = s.at("network")[0]
    assert e.derivation is not None
    assert e.derivation.kind == "name"
    assert e.derivation.label == "u"
    literal = e.derivation.inputs[0]
    assert literal.kind == "literal"


def test_literal_derivation_label_re_escapes_a_quote():
    """const()'s Str case builds the literal's display label as a quoted
    Planes literal (`f'"{...}"'`) -- the same re-quote-as-source shape
    render.py's Str case has, and the same fix, so a string containing a
    quote does not corrupt the label."""
    s = analyse('use http\nlet u = "a\\"b"\nx = ask u')
    e = s.at("network")[0]
    literal = e.derivation.inputs[0]
    assert literal.label == '"a\\"b"'


def test_widening_produces_an_unknown_provenance_node():
    src = ('use http\n'
           'let u = "https://example.com/default.json"\n'
           'if 1 > 0:\n'
           '  let u = "https://example.com/other.json"\n'
           'x = ask u')
    s = analyse(src)
    e = s.at("network")[0]

    def has_unknown(n, seen=None):
        seen = seen if seen is not None else set()
        if id(n) in seen:
            return False
        seen.add(id(n))
        if n.kind == "unknown":
            return True
        return any(has_unknown(i, seen) for i in n.inputs)

    assert has_unknown(e.derivation)


def test_target_from_ask_output_does_not_claim_provenance():
    src = ('use http\n'
           'to get of url:\n'
           '  give ask url\n\n'
           'xs = for each u in [1, 2]: get of u')
    s = analyse(src)
    e = s.at("network")[0]
    assert e.derivation is not None
    assert e.derivation.kind != "literal"


def test_fixed_point_terminates_with_derivation_on_hn():
    """Effect.derivation must not break the fixed point's growth check —
    it is excluded from hash/equality via field(compare=False)."""
    s = analyse_file("hn.planes")
    assert s.touches("network")


def test_fixed_point_terminates_on_mutual_recursion_with_derivation():
    src = ('use http\n'
           'to ping of n:\n'
           '  if n > 0:\n'
           '    give pong of (n - 1)\n'
           '  give ask "https://example.com/a.json"\n\n'
           'to pong of n:\n'
           '  give ping of (n - 1)\n\n'
           'r = ping of 3')
    s = analyse(src)
    assert s.touches("network")
    assert s.functions["pong"]


def test_derivation_of_returns_the_effect_node():
    s = analyse('use http\nx = ask "https://example.com/a.json"')
    e = s.at("network")[0]
    assert s.derivation_of(e) is e.derivation
    assert s.derivation_of(e).kind == "literal"


def test_origins_of_finds_a_named_parameter():
    s = analyse('use http\n'
                'to send of payload:\n'
                '  give ask "https://collector.example.com/?d=" + payload\n\n'
                'x = send of "secret"\n')
    e = s.at("network")[0]
    origins = s.origins_of(e)
    names = {n for n, _f in origins}
    assert "payload" in names


def test_origins_of_empty_for_a_bare_literal():
    s = analyse('use http\nx = ask "https://example.com/a.json"')
    e = s.at("network")[0]
    assert s.origins_of(e) == []


def test_effect_derivation_excluded_from_equality():
    """Two structurally identical effects with different derivations must
    still compare equal and hash the same, or the fixed point may not
    terminate."""
    from shapes import StaticDeriv
    a = Effect("ask", "network", "https://x", derivation=StaticDeriv("literal", "a"))
    b = Effect("ask", "network", "https://x", derivation=StaticDeriv("literal", "b"))
    assert a == b
    assert hash(a) == hash(b)


# ================================================================ the association idiom (Ruling 1)

def test_association_idiom_produces_a_complete_correct_effect_surface():
    """demo/association.planes -- a list-of-records table, a `lookup`
    function doing a `for each ... where` linear scan, and a `show` of a
    hit and a miss. Ruling 1 (fix/recursion-leak-and-fifth-amber-site)
    promotes this from PROBE_PARSER.md capability 7's workaround to the
    canonical idiom; the oracle check is this claim's actual test --
    every effect the program performs at runtime must be covered by the
    statically computed surface, control flow through the lookup and
    all."""
    surface, i = check_oracle_file("demo/association.planes")
    assert i.output == ["30", "nothing"]
    assert {e.kind for e in surface.effects} == {"show"}


def test_origins_of_traces_an_association_lookup_back_to_its_table():
    """The analyser sees through the idiom's call boundary: `hit`'s
    origin traces back to `prices`, the table `lookup` scanned, even
    though the matched value itself (dependent on which key was passed)
    stays statically UNKNOWN -- widening the value is sound; dropping the
    argument names it derived from would not be seeing through the idiom
    at all, just stopping at the call."""
    from shapes import analyse_file
    s = analyse_file("demo/association.planes")
    # s.effects, not s.at()/.declared -- the latter dedupes by (kind,
    # target, computed), and both shows share the same generic computed
    # target ("{...}"), collapsing to one entry despite two distinct call
    # sites with two distinct derivations.
    shows = [e for e in s.effects if e.kind == "show"]
    assert len(shows) == 2
    for e in shows:
        names = {n for n, _f in s.origins_of(e)}
        assert "prices" in names, f"origins {names} do not trace back to prices"


# ================================================================ anti-drift

def test_no_governance_vocabulary():
    banned = ["policy", "precedence", "govern", "deny"]
    text = open("shapes.py").read().lower()
    for w in banned:
        assert w not in text, f"{w!r} in shapes.py — drift"


if __name__ == "__main__":
    fails = []
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            fails.append(name)
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
