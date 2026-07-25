"""Tests for the foreign function interface.

The design question this session settled: does a foreign function declare
its effects, or does the analyser derive them from the host?

Declaration, because derivation is impossible in general — the analyser would have
to analyse CPython, then a C extension — and the failure mode is silent. An
analyser that cannot see inside would report "pure", which is a guess
published as a fact.

The consequence that matters most is the default. An UNDECLARED foreign
function must not contribute nothing. It contributes `unknown`, and the
surface says it is incomplete.
"""
import sys

from interp import Interpreter, PlanesError
from parser import PlanesSyntaxError, parse
from shapes import EFFECT_KINDS, analyse


def run(src, **kw):
    return Interpreter(**kw).run(src)


def interp(src, **kw):
    i = Interpreter(**kw)
    i.run(src)
    return i


def val(src, name, **kw):
    return interp(src, **kw).env.get(name)


# ================================================================ calling out

def test_a_foreign_function_actually_runs():
    src = ('foreign sort of xs from "builtins.sorted" doing nothing\n'
           'r = sort of [3, 1, 2]')
    assert val(src, "r").value == [1, 2, 3]


def test_foreign_with_no_arguments():
    src = ('foreign now from "time.time" doing clock\n'
           't = now')
    assert val(src, "t").value > 0


def test_numbers_convert_both_ways():
    """A Planes exact number goes out as a host number and comes back exact."""
    from planes_num import Number
    src = ('foreign biggest of xs from "builtins.max" doing nothing\n'
           'r = biggest of [1.5, 2.25, 0.5]')
    v = val(src, "r").value
    assert isinstance(v, Number)
    assert v == Number.parse("2.25")


def test_multiword_foreign_name():
    src = ('foreign sort them of xs from "builtins.sorted" doing nothing\n'
           'r = sort them of [2, 1]')
    assert val(src, "r").value == [1, 2]


def test_foreign_result_is_traceable():
    """A foreign boundary is a place values enter, like the network."""
    from interp import origins, why_tree
    src = ('foreign biggest of xs from "builtins.max" doing nothing\n'
           'top = biggest of [1, 9, 4]\n'
           'plus = top + 1')
    v = val(src, "plus")
    assert v.value == 10
    assert "foreign:builtins.max" in origins(v)
    assert "entered at foreign:builtins.max" in why_tree(v)


def test_wrong_arity_on_a_foreign():
    src = ('foreign sort of xs from "builtins.sorted" doing nothing\n'
           'r = sort of 1, 2')
    try:
        run(src)
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "wrong-arity"


def test_missing_host_function_names_the_problem():
    src = ('foreign nope of x from "builtins.definitely_not_here" doing nothing\n'
           'r = nope of 1')
    try:
        run(src)
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "foreign-not-found"
        assert "builtins.definitely_not_here" in e.detail


def test_bad_target_form_names_the_fix():
    src = ('foreign nope of x from "notdotted" doing nothing\n'
           'r = nope of 1')
    try:
        run(src)
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "bad-foreign-target"
        assert "module.function" in e.fix


def test_host_exception_becomes_a_planes_error():
    src = ('foreign biggest of xs from "builtins.max" doing nothing\n'
           'r = biggest of []')
    try:
        run(src)
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "foreign-failed"
        assert "ValueError" in e.detail


def test_or_fail_renames_a_foreign_failure():
    src = ('foreign biggest of xs from "builtins.max" doing nothing\n'
           'r = (biggest of []) or fail as no-readings')
    try:
        run(src)
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "no-readings"


# ================================================================ the surface

def test_declared_effects_appear_in_the_surface():
    s = analyse('foreign now from "time.time" doing clock\n'
                't = now')
    assert s.touches("ambient")
    assert any(e.kind == "clock" for e in s.at("ambient"))


def test_declared_effects_are_marked_as_claims():
    """Planes cannot see inside the host, so it says so."""
    s = analyse('foreign now from "time.time" doing clock\n'
                't = now')
    e = s.at("ambient")[0]
    assert e.claimed, "a foreign effect is declared, not derived"
    assert "not verified" in str(e)


def test_doing_nothing_contributes_nothing():
    s = analyse('foreign sort of xs from "builtins.sorted" doing nothing\n'
                'r = sort of [1]')
    assert s.is_pure()


def test_an_undeclared_foreign_is_unknown_not_pure():
    """The headline safety property of this design."""
    s = analyse('foreign mystery of x from "m.f"\n'
                'r = mystery of 1')
    assert not s.is_pure(), "an undeclared foreign must not read as pure"
    assert s.has_unknowns()
    assert any(e.kind == "unknown" for e in s.declared)


def test_an_incomplete_surface_says_so():
    s = analyse('foreign mystery of x from "m.f"\n'
                'r = mystery of 1')
    assert "incomplete" in s.render()


def test_a_library_exposing_a_foreign_effect_is_not_pure():
    """A library re-exporting a clock function is not pure, even though
    nothing in the file calls it."""
    s = analyse('foreign now from "time.time" doing clock')
    assert not s.is_pure()
    assert s.is_library()
    assert s.touches("ambient")


def test_several_declared_effects():
    s = analyse('foreign grab of u from "x.y" doing ask, clock\n'
                'r = grab of "u"')
    kinds = {e.kind for e in s.declared}
    assert "ask" in kinds and "clock" in kinds


def test_analyser_does_not_call_the_host():
    """Analysis must never execute a foreign function."""
    s = analyse('foreign boom of x from "sys.exit" doing nothing\n'
                'r = boom of 1')
    assert s.is_pure()      # got here without exiting


def test_foreign_effects_reach_a_caller():
    s = analyse('foreign now from "time.time" doing clock\n\n'
                'to stamp:\n'
                '  give now\n\n'
                'r = stamp')
    assert s.touches("ambient"), "effects must propagate up the call graph"


def test_claims_are_separable_from_derived_effects():
    s = analyse('use http\n'
                'foreign now from "time.time" doing clock\n'
                'a = ask "https://example.com/x.json"\n'
                'b = now')
    claimed = {e.kind for e in s.claims()}
    assert claimed == {"clock"}, f"got {claimed}"


# ================================================================ the oracle

def check_oracle(src, **kw):
    """Every runtime effect must be covered by the static surface.

    The oracle was previously only exercised on files without foreign
    declarations, which is how a bug that logged the wrong effect kind for
    every foreign call survived a full suite. It is exercised here.
    """
    surface = analyse(src)
    i = interp(src, **kw)
    by_kind = {}
    for e in surface.declared:
        by_kind.setdefault(e.kind, []).append(e)

    for kind, target in [(e[0], e[1]) for e in i.effects]:
        assert isinstance(kind, str), \
            f"runtime logged a non-string effect kind: {kind!r}"
        cands = by_kind.get(kind, [])
        assert cands, (f"runtime performed {kind!r} on {target!r} but the "
                       f"static surface has no {kind!r} — UNSOUND")
        ok = any(c.computed or c.target == target for c in cands)
        assert ok, (f"runtime performed {kind} on {target!r}, not covered by "
                    f"{[str(c) for c in cands]} — UNSOUND")
    return surface, i


def test_oracle_declared_clock():
    check_oracle('foreign now from "time.time" doing clock\nt = now')


def test_oracle_resolved_parameter_target():
    surface, i = check_oracle(
        'foreign echo of url from "builtins.str" doing ask url\n'
        'r = echo of "https://example.com/x"')
    assert ("ask", "https://example.com/x") in [(e[0], e[1]) for e in i.effects]
    assert "https://example.com/x" in surface.targets("ask")


def test_oracle_literal_target():
    check_oracle('foreign tag of x from "builtins.str" '
                 'doing ask "https://fixed.example.com"\n'
                 'r = tag of 1')


def test_runtime_logs_a_string_kind_not_a_tuple():
    """The bug this oracle gap hid: the logged kind was the declaration
    tuple, so the runtime effect log was unreadable for every foreign."""
    i = interp('foreign now from "time.time" doing clock\nt = now')
    kind, target = i.effects[0][0], i.effects[0][1]
    assert kind == "clock", f"logged kind was {kind!r}"
    assert target == "time.time"


# ================================================================ targets

def test_literal_target_appears_in_the_surface():
    s = analyse('foreign send of x from "m.post" '
                'doing ask "https://api.example.com/events"\n'
                'r = send of 1')
    assert "https://api.example.com/events" in s.targets("ask")


def test_parameter_target_resolves_at_the_call_site():
    """The valuable case: a real host name survives a foreign boundary."""
    s = analyse('foreign fetch of url from "u.r.urlopen" doing ask url\n'
                'r = fetch of "https://pypi.org/pypi/requests/json"')
    assert "https://pypi.org/pypi/requests/json" in s.targets("ask")


def test_parameter_target_stays_unknown_when_the_argument_is():
    s = analyse('foreign fetch of url from "u.r.urlopen" doing ask url\n'
                'rs = for each u in ["a", "b"]: fetch of u')
    assert all(e.computed for e in s.at("network"))


def test_a_declaration_with_no_target_says_so():
    s = analyse('foreign vague of x from "m.v" doing ask\nr = vague of 1')
    e = s.at("network")[0]
    assert "not stated" in e.target
    assert e.computed


def test_target_must_name_a_real_parameter():
    try:
        parse('foreign f of a from "m.f" doing ask nope')
        assert False, "should raise"
    except PlanesSyntaxError as e:
        assert "not a parameter" in str(e)
        assert "parameters: a" in str(e)


def test_several_effects_with_and_without_targets():
    s = analyse('foreign grab of u from "m.g" doing ask u, clock\n'
                'r = grab of "https://example.com/x"')
    assert "https://example.com/x" in s.targets("ask")
    assert s.touches("ambient")


# ================================================================ diffing

def test_diff_catches_a_changed_foreign_destination():
    """Identical Planes code, identical effect kinds, different destination.

    Before targets this diff was empty — the exact hole targets close.
    """
    from shapes import diff
    before = analyse('foreign send of x from "m.post" '
                     'doing ask "https://api.example.com/events"\n'
                     'r = send of 1')
    after = analyse('foreign send of x from "m.post" '
                    'doing ask "https://collect.tracking.io/beacon"\n'
                    'r = send of 1')
    d = diff(before, after)
    assert not d.is_empty()
    assert d.is_significant(), "a new destination must fail a build"
    assert any("collect.tracking.io" in e.target for e in d.added)
    assert "NEW DESTINATIONS" in d.render()


def test_diff_of_an_unchanged_foreign_is_empty():
    from shapes import diff
    src = ('foreign send of x from "m.post" doing ask "https://a.example.com"\n'
           'r = send of 1')
    assert diff(analyse(src), analyse(src)).is_empty()


def test_a_new_boundary_still_outranks_a_new_destination():
    from shapes import diff
    before = analyse('x = 5')
    after = analyse('foreign send of x from "m.post" '
                    'doing ask "https://a.example.com"\n'
                    'r = send of 1')
    d = diff(before, after)
    assert "NEW BOUNDARIES CROSSED" in d.render()
    assert d.is_significant()


# ================================================================ vocabulary

def test_ambient_effects_are_in_the_closed_vocabulary():
    """clock, random and env make a result depend on something outside the
    program, so they are effects."""
    for kind in ("clock", "random", "env"):
        assert EFFECT_KINDS[kind] == "ambient"


def test_effect_vocabulary_stays_closed():
    """An open vocabulary cannot be searched or diffed across packages."""
    assert set(EFFECT_KINDS) == {
        "ask", "read", "write", "show", "clock", "random", "env"}


# ================================================================ demo file

def test_the_demo_runs():
    i = Interpreter()
    i.run_file("foreign.planes")
    assert "spread:  37" in i.output


def test_the_demo_surface_is_complete():
    from shapes import analyse_file
    s = analyse_file("foreign.planes")
    assert not s.has_unknowns(), "every foreign in the demo declares itself"


if __name__ == "__main__":
    fails = []
    tests = [(k, f) for k, f in sorted(globals().items()) if k.startswith("test_")]
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
