"""Tests for the Tier 2 text laws (planes v9.0 A.1-A.3), plus A.5's string
escapes (fix/string-escapes-and-bootstrap, v9.0 §105: text is a sequence of
Unicode code points, and the literal syntax must be able to denote any such
sequence).

`+` requires type homogeneity, `first n of` a string stays a string, and
`normalize of` is an explicit pure builtin — equality never normalizes.
"""
import sys

from interp import Interpreter, PlanesError, why_tree
from lexer import PlanesSyntaxError
from shapes import analyse


def run(src, **kw):
    return Interpreter(**kw).run(src)


def interp(src, **kw):
    i = Interpreter(**kw)
    i.run(src)
    return i


def val(src, name, **kw):
    return interp(src, **kw).env.get(name)


# ================================================================ A.1 -- + homogeneity

def test_string_plus_number_raises():
    try:
        run('x = "a" + 1')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "cannot-combine"


def test_string_plus_number_fix_is_text_of():
    assert run('x = "a" + text of 1\nshow x') == ["a1"]


def test_number_plus_number_unaffected():
    assert val("x = 1 + 2", "x").value == 3


def test_list_plus_list_unaffected():
    assert val("x = [1] + [2]", "x").value == [1, 2]


def test_string_plus_string_still_concatenates():
    assert val('x = "hi " + "there"', "x").value == "hi there"


def test_list_plus_string_raises():
    try:
        run('x = [1] + "a"')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "cannot-combine"


def test_shapes_widens_mixed_plus_to_unknown_never_raises():
    """The analyser never executes and must stay total (v9.0 invariant 2)."""
    s = analyse('x = "a" + 1\nshow x')          # must not raise
    assert s.effects, "still analyses past the mixed +"


def test_shapes_still_folds_same_type_plus():
    s = analyse('x = "a" + "b"\nshow x')
    assert s.effects[0].target == "ab", "same-type + still folds statically"


# ================================================================ A.2 -- first n of a string

def test_first_of_string_returns_a_string():
    v = val('x = first 2 of "hello"', "x").value
    assert v == "he"
    assert isinstance(v, str)


def test_first_of_list_returns_a_list():
    v = val("x = first 2 of [1, 2, 3]", "x").value
    assert v == [1, 2]
    assert isinstance(v, list)


def test_count_of_first_of_string_is_code_points():
    assert val('x = count of (first 2 of "héllo")', "x").value == 2


# ================================================================ A.3 -- normalize

def test_normalize_folds_to_nfc():
    combining = "é"       # e + combining acute
    precomposed = "é"      # \xe9, single code point
    v = val(f'x = normalize of "{combining}"', "x").value
    assert v == precomposed


def test_equality_does_not_normalize():
    combining = "é"
    precomposed = "é"
    try:
        run(f'x = ("{combining}" == "{precomposed}")')
    except PlanesError:
        assert False, "same-type string == must not raise"
    assert val(f'x = ("{combining}" == "{precomposed}")', "x").value is False


def test_normalize_of_both_sides_makes_them_equal():
    combining = "é"
    precomposed = "é"
    src = f'x = (normalize of "{combining}" == normalize of "{precomposed}")'
    assert val(src, "x").value is True


def test_why_shows_normalize_derivation():
    combining = "é"
    tree = why_tree(val(f'x = normalize of "{combining}"', "x"))
    assert "normalize of" in tree


def test_shapes_folds_normalize_statically_no_effect():
    s = analyse('x = normalize of "abc"\nshow x')
    assert s.effects[0].target == "abc"
    assert s.kinds() == ["show"], "normalize contributes no effect kind"


def test_normalize_is_not_an_effect_kind():
    from lexer import EFFECT_KINDS
    assert "normalize" not in EFFECT_KINDS


# ================================================================ A.4 -- text is iterable

def test_for_each_over_a_string_statement_form():
    out = run('s = "abc"\nfor each c in s:\n  show c\n')
    assert out == ["a", "b", "c"]


def test_for_each_over_a_string_comprehension_form_yields_a_list():
    v = val('x = for each c in "abc": c', "x").value
    assert v == ["a", "b", "c"]
    assert isinstance(v, list), "the result follows the body, not the source"


def test_for_each_over_a_string_where_filters():
    v = val('x = for each c in "abc" where c != "b": c', "x").value
    assert v == ["a", "c"]


def test_for_each_over_an_empty_string_iterates_zero_times():
    v = val('x = for each c in "": c', "x").value
    assert v == []


def test_for_each_over_a_string_elements_are_one_code_point_strings():
    v = val('x = for each c in "abc": c', "x").value
    assert all(isinstance(c, str) and len(c) == 1 for c in v)


def test_for_each_over_a_string_counts_code_points_not_utf8_bytes():
    # "h\u00e9llo" -- a precomposed e-acute, one code point, two UTF-8 bytes.
    # Iteration must yield 5 elements (code points), not 6 (bytes).
    v = val('x = for each c in "h\u00e9llo": c', "x").value
    assert len(v) == 5
    assert len("h\u00e9llo".encode("utf-8")) == 6, "the byte count this test guards against"
    assert v == ["h", "\u00e9", "l", "l", "o"]


def test_rebinding_outside_the_loop_accumulates_across_iterations():
    """The fold-lexer design (probe/fold_tokens.planes) rests on `acc =
    acc plus c` inside a for-each *statement* body reaching out to rebind
    the outer `acc`, on every iteration, via v4.0 §58's scope-walking
    assignment (Env.set walks parent scopes to find where a name already
    lives) -- not the comprehension form's own automatic result list,
    which is a different mechanism and already covered elsewhere. This
    was untested until probe/accumulate_in_loop.planes exercised it."""
    n = val('acc = []\nfor each c in "abc":\n  acc = acc plus c\nx = count of acc',
            "x").value
    assert n == 3
    acc = val('acc = []\nfor each c in "abc":\n  acc = acc plus c\nx = acc', "x").value
    assert acc == ["a", "b", "c"]


def test_for_each_over_a_number_still_raises_not_a_collection():
    try:
        run("for each c in 5:\n  show c\n")
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "not-a-collection"


def test_for_each_over_a_record_still_raises_not_a_collection():
    try:
        run('for each c in { a: 1 }:\n  show c\n')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "not-a-collection"


def test_not_a_collection_fix_text_names_strings_as_acceptable():
    try:
        run("for each c in 5:\n  show c\n")
        assert False, "should raise"
    except PlanesError as e:
        assert "string" in e.fix


# ================================================================ A.5 -- string escapes

def test_escaped_quote_resolves():
    v = val(r'x = "a\"b"', "x").value
    assert v == 'a"b'
    assert len(v) == 3


def test_escaped_backslash_resolves():
    v = val(r'x = "a\\b"', "x").value
    assert v == "a\\b"
    assert len(v) == 3


def test_escaped_newline_resolves():
    v = val(r'x = "a\nb"', "x").value
    assert v == "a\nb"
    assert len(v) == 3


def test_escaped_tab_resolves():
    v = val(r'x = "a\tb"', "x").value
    assert v == "a\tb"
    assert len(v) == 3


def test_count_of_counts_resolved_code_points_not_source_characters():
    # Source spells 4 characters between the quotes (a, \, n, b); the
    # resolved value is 3 code points (a, newline, b) -- count of must
    # see the resolved text, not the raw source.
    assert val(r'x = count of "a\nb"', "x").value == 3


def test_unknown_escape_raises_naming_the_four_that_exist():
    try:
        run(r'x = "a\zb"')
        assert False, "should raise"
    except PlanesSyntaxError as e:
        msg = str(e)
        for legal in ('\\"', "\\\\", "\\n", "\\t"):
            assert legal in msg, f"{legal!r} not named in: {msg}"


def test_trailing_backslash_before_closing_quote_raises():
    """`"a\"` -- the backslash escapes the quote (\") instead of ending
    the string, so the string is unterminated; this must be a clear
    syntax error, not a silently-dropped or silently-truncated token
    (the failure mode finditer's default skip-ahead would otherwise
    produce)."""
    try:
        run('x = "a\\"')
        assert False, "should raise"
    except PlanesSyntaxError:
        pass


def test_escaped_quote_string_equals_the_same_text_built_another_way():
    # Two different source spellings of the same 3-code-point value: the
    # quote escaped inline, versus the quote as its own escaped literal
    # concatenated in -- both must resolve to identical text.
    inline = val(r'x = "a\"b"', "x").value
    concatenated = val(r'x = "a" + "\"" + "b"', "x").value
    assert inline == concatenated == 'a"b'


def test_double_backslash_yields_exactly_one_backslash():
    v = val(r'x = "\\"', "x").value
    assert v == "\\"
    assert len(v) == 1
    assert list(v) == ["\\"]


def test_why_tree_because_line_re_escapes():
    """why_tree's `because=` line prints a value back as a quoted Planes
    literal (interp.py) -- the same re-quote-as-source shape render.py's
    Str case has, and the same fix (planes_text.escape_string_literal): a
    because-text containing a quote must round-trip in the tree's own
    output, not corrupt it."""
    tree = why_tree(val('x = 1', "x"), because='a"b')
    assert 'because "a\\"b"' in tree


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
