"""Planes test suite. Every claim is testable; every feature has a case."""
import json
import sys

from interp import Interpreter, PlanesError, why_tree, origins
from parser import PlanesSyntaxError


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
    return Interpreter(**kw).run(src)


def interp(src, **kw):
    i = Interpreter(**kw)
    i.run(src)
    return i


def val(src, name, **kw):
    return interp(src, **kw).env.get(name)


HN = open("hn.planes").read()


# ================================================================ TASK 1

def test_gate():
    assert run("x = 5\ny = 3\nz = x + y\nwhy z") == ["8 from x (5) + y (3)"]


def test_literal_why():
    assert run("x = 5\nwhy x") == ["5 from 5"]


def test_transitive_one_hop():
    assert run("a = 2\nb = 3\nc = a * b\nd = c + 1\nwhy d") == ["7 from c (6) + 1"]


def test_transitive_full_tree():
    tree = why_tree(val("a = 2\nb = 3\nc = a * b\nd = c + 1", "d"))
    for expect in ("d = 7", "c = 6", "a = 2", "b = 3"):
        assert expect in tree, f"{expect!r} missing from tree"


def test_precedence():
    assert val("x = 2 + 3 * 4", "x").value == 14


def test_parens():
    assert val("x = (2 + 3) * 4", "x").value == 20


def test_let_is_optional():
    assert val("let x = 5", "x").value == 5
    assert val("x = 5", "x").value == 5


def test_string_concat():
    assert val('g = "hi " + "there"', "g").value == "hi there"


def test_comparison():
    assert val("x = 5 > 3", "x").value is True


def test_unknown_name_error():
    try:
        run("why nope")
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "unknown-name" and "nope" in e.detail


def test_divide_by_zero_names_the_fix():
    try:
        run("x = 1 / 0")
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "divided-by-zero" and e.fix


# ================================================================ TASK 2

def test_function_call():
    assert val("to add of a, b:\n  give a + b\n\nr = add of 2, 3", "r").value == 5


def test_function_paren_syntax():
    assert val("to add of a, b:\n  give a + b\n\nr = add(2, 3)", "r").value == 5


def test_why_shows_call_chain():
    out = run("to add of a, b:\n  give a + b\n\nresult = add of 2, 3\nwhy result")
    assert out == ["5 from add(2, 3) = a (2) + b (3)"]


def test_call_chain_survives_in_tree():
    tree = why_tree(val("to add of a, b:\n  give a + b\n\nr = add of 2, 3", "r"))
    assert "add = 5" in tree and "a = 2" in tree and "b = 3" in tree


def test_nested_calls():
    src = ("to double of n:\n  give n * 2\n\n"
           "to bump of n:\n  give (double of n) + 1\n\n"
           "r = bump of 5")
    assert val(src, "r").value == 11
    tree = why_tree(val(src, "r"))
    assert "bump" in tree and "double" in tree


def test_of_binds_tighter_than_arithmetic():
    """`double of n + 1` is `(double of n) + 1`, not `double of (n + 1)`.

    Locked so `detail of id` in a larger expression stays unambiguous.
    """
    src = ("to double of n:\n  give n * 2\n\n"
           "a = double of 5 + 1\n"
           "b = double of (5 + 1)")
    assert val(src, "a").value == 11
    assert val(src, "b").value == 12


def test_zero_arg_multiword_function():
    assert val("to fetch stories:\n  give 42\n\nr = fetch stories", "r").value == 42


def test_multiword_function_with_argument():
    """`phone home of x` — multi-word name AND an argument."""
    src = "to phone home of x:\n  give x * 2\n\nr = phone home of 21"
    assert val(src, "r").value == 42


def test_structural_word_cannot_start_a_function_name():
    """`first` still carries syntax (`first 30 of xs`), so it stays reserved."""
    try:
        run('to first thing:\n  give 1\n')
        assert False, "should raise"
    except PlanesSyntaxError as e:
        assert "reserved word" in str(e)
        assert "first" in str(e)


def test_former_keywords_are_now_ordinary_names():
    """count, text, lower, upper, whole, ask, read are builtins, not keywords.

    They can be used as function names, and a user definition wins.
    """
    assert val('to count of xs:\n  give 99\n\nr = count of [1, 2]',
               "r").value == 99


def test_write_to_is_not_read_as_a_definition():
    """`write x to "path"` uses the same TO token as a definition."""
    i = interp('use file\nwrite [1, 2] to "out.json"', fs={})
    assert "out.json" in i.fs


def test_wrong_arity_error():
    try:
        run("to add of a, b:\n  give a + b\n\nr = add of 1")
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "wrong-arity" and "takes 2 values, given 1" in e.detail


def test_unknown_function_error():
    try:
        run("r = nope of 1")
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "unknown-function"


def test_recursion():
    src = ("to fact of n:\n"
           "  if n <= 1:\n"
           "    give 1\n"
           "  give n * fact of (n - 1)\n\n"
           "r = fact of 5")
    assert val(src, "r").value == 120


def test_function_callable_before_its_definition():
    """Definitions are hoisted; source order controls execution, not visibility.

    Without this the static analyser and the interpreter would disagree about
    what a program can do.
    """
    src = ("r = later of 5\n\n"
           "to later of n:\n"
           "  give n * 2")
    assert val(src, "r").value == 10


# ================================================================ TASK 3

def test_list_literal():
    assert val("xs = [1, 2, 3]", "xs").value == [1, 2, 3]


def test_count_of():
    assert val("n = count of [1, 2, 3]", "n").value == 3


def test_first_of():
    assert val("xs = first 2 of [1, 2, 3, 4]", "xs").value == [1, 2]


def test_comprehension():
    assert val("ys = for each x in [1, 2, 3]: x * 2", "ys").value == [2, 4, 6]


def test_comprehension_with_where():
    assert val("ys = for each x in [1, 2, 3, 4] where x > 2: x", "ys").value == [3, 4]


def test_comprehension_provenance():
    assert "for each x" in why_tree(val("ys = for each x in [1,2,3]: x * 2", "ys"))


def test_lower_and_in():
    assert val('hit = "rust" in lower of "Rust 2.0"', "hit").value is True


def test_and_or_not():
    assert val("a = true and false", "a").value is False
    assert val("b = true or false", "b").value is True
    assert val("c = not false", "c").value is True


def test_if_else():
    src = ('to grade of n:\n'
           '  if n > 50:\n'
           '    give "pass"\n'
           '  else:\n'
           '    give "fail"\n\n'
           'r = grade of 70')
    assert val(src, "r").value == "pass"


def test_record_dot_access():
    i = interp('use http\n'
               's = ask "https://hacker-news.firebaseio.com/v0/item/1.json"\n'
               't = s.title', http=stub_http)
    assert i.env.get("t").value == "Rust 2.0 released"


def test_dot_on_non_record_errors():
    try:
        run("x = 5\ny = x.title")
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "not-a-record"


def test_ask_requires_module():
    try:
        run('x = ask "https://example.com/a.json"')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "module-not-used" and "use http" in e.fix


def test_write_requires_module():
    try:
        run('write [1, 2] to "out.json"')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "module-not-used"


def test_or_fail_renames_error():
    def boom(url):
        raise RuntimeError("connection refused")
    try:
        run('use http\nx = ask "https://example.com/a.json"\n  or fail as api-down',
            http=boom)
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "api-down"


def test_write_then_read_roundtrip():
    i = interp('use file\nwrite [1, 2, 3] to "out.json"', fs={})
    assert json.loads(i.fs["out.json"]) == [1, 2, 3]


def test_effects_are_recorded_in_order():
    i = interp('use http\nuse file\n'
               'x = ask "https://hacker-news.firebaseio.com/v0/item/1.json"\n'
               'show "hi"\n'
               'write [1] to "o.json"', http=stub_http)
    assert [e[0] for e in i.effects] == ["ask", "show", "write"]


# ---------------------------------------------------------------- the scraper

def test_hn_scraper_runs():
    i = interp(HN, http=stub_http)
    assert i.output == [
        "found 2",
        "Rust 2.0 released  (450)",
        "Rewriting grep in Rust  (210)",
    ]


def test_hn_scraper_writes_results():
    i = interp(HN, http=stub_http)
    written = json.loads(i.fs["results.json"])
    assert len(written) == 2 and written[0]["title"] == "Rust 2.0 released"


def test_hn_scraper_effect_surface():
    i = interp(HN, http=stub_http)
    kinds = [e[0] for e in i.effects]
    assert kinds.count("ask") == 5
    assert kinds.count("write") == 1
    assert kinds.count("show") == 3


def test_why_crosses_the_network_boundary():
    src = ('use http\n'
           'to detail of story-id:\n'
           '  give ask "https://hacker-news.firebaseio.com/v0/item/" '
           '+ text of story-id + ".json"\n\n'
           's = detail of 1\n'
           'bumped = s.score + 50')
    v = val(src, "bumped", http=stub_http)
    assert v.value == 500
    origs = origins(v)
    assert len(origs) == 1
    assert origs[0].startswith("network:") and "item/1.json" in origs[0]


def test_why_one_line_for_network_value():
    src = ('use http\n'
           's = ask "https://hacker-news.firebaseio.com/v0/item/1.json"\n'
           'bumped = s.score + 50\n'
           'why bumped')
    assert run(src, http=stub_http)[-1] == "500 from s ({record}).score + 50"


# ---------------------------------------------------------------- anti-drift

def test_no_governance_vocabulary_in_source():
    """If the substrate has grown a rule plane, this fails."""
    banned = ["policy", "precedence", "govern", "allow ", "deny"]
    for fname in ("lexer.py", "parser.py", "interp.py"):
        text = open(fname).read().lower()
        for word in banned:
            assert word not in text, f"{word!r} appeared in {fname} — drift"


def test_ordinary_program_needs_no_governance():
    """Arithmetic, comprehension, conditional, file IO. No rules anywhere."""
    src = ('use file\n'
           'prices = [10, 25, 5, 40]\n'
           'big = for each p in prices where p > 8: p\n'
           'n = count of big\n'
           'avg = 75 / n\n'
           'if avg > 20:\n'
           '  show "above"\n'
           'else:\n'
           '  show "below"\n'
           'write big to "big.json"')
    i = interp(src, fs={})
    assert i.output == ["above"]
    assert i.env.get("n").value == 3
    assert i.env.get("avg").value == 25.0


def test_ordinary_program_is_traceable():
    """Session gate: Why can trace the ordinary program."""
    src = ('prices = [10, 25, 5, 40]\n'
           'big = for each p in prices where p > 8: p\n'
           'n = count of big\n'
           'avg = 75 / n')
    tree = why_tree(val(src, "avg"))
    assert "avg = 25" in tree
    assert "count of = 3" in tree
    assert "for each p where ..." in tree


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
