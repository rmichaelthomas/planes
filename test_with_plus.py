"""Tests for `with` (record update) and `plus` (list append) — the two
locked-but-unbuilt constructs of v5.0 §72, closed in this build.

Locked semantics, verbatim: "`with` produces a new record differing in
the named fields. Originals are untouched. Both nest and compose like
any other expression." "`plus` produces a new list with the item
appended. Originals are untouched. Both nest and compose like any other
expression."
"""
import sys

from interp import Interpreter, PlanesError, why_tree


def run(src, **kw):
    return Interpreter(**kw).run(src)


def interp(src, **kw):
    i = Interpreter(**kw)
    i.run(src)
    return i


def val(src, name, **kw):
    return interp(src, **kw).env.get(name)


# ================================================================ with

def test_with_produces_a_new_record():
    i = interp('p = { name: "a", owed: 5 }\nq = p with owed: 0\n')
    assert i.env.get("q").value == {"name": "a", "owed": 0}


def test_with_leaves_the_original_untouched():
    i = interp('p = { name: "a", owed: 5 }\nq = p with owed: 0\n')
    assert i.env.get("p").value == {"name": "a", "owed": 5}


def test_with_multiple_fields_one_clause():
    i = interp('p = { a: 1, b: 2, c: 3 }\nq = p with a: 9, c: 8\n')
    assert i.env.get("q").value == {"a": 9, "b": 2, "c": 8}
    assert i.env.get("p").value == {"a": 1, "b": 2, "c": 3}


def test_with_chains_left_to_right():
    i = interp('p = { name: "a", owed: 5 }\n'
               'q = p with owed: 0 with name: "b"\n')
    assert i.env.get("q").value == {"name": "b", "owed": 0}
    assert i.env.get("p").value == {"name": "a", "owed": 5}


def test_with_composes_as_a_call_argument():
    i = interp('use file\np = { a: 1 }\nwrite (p with a: 2) to "o.json"\n', fs={})
    assert i.fs["o.json"] == '{\n  "a": 2\n}'


def test_with_why_shows_a_node_pointing_at_the_base():
    i = interp('p = { a: 1 }\nq = p with a: 2\n')
    tree = why_tree(i.env.get("q"))
    assert "with" in tree
    assert "p = {record}" in tree


def test_with_on_a_non_record_raises():
    try:
        run('x = 5 with a: 1\n')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "not-a-record"


def test_with_field_value_can_be_a_full_expression():
    i = interp('p = { total: 0 }\nn = 3\nq = p with total: n * 2\n')
    assert i.env.get("q").value == {"total": 6}


def test_with_does_not_collide_with_the_module_rename_with():
    i = interp('use http with ask as fetch\nx = 1\n', http=lambda u: '"ok"')
    assert i.env.get("x").value == 1


def test_with_in_a_list_literal_disambiguates_from_the_comma():
    i = interp('a = { x: 1 }\nb = { x: 2 }\n'
               'xs = [a with x: 9, b with x: 8]\n')
    assert i.env.get("xs").value == [{"x": 9}, {"x": 8}]


def test_with_before_a_second_call_argument_disambiguates_from_the_comma():
    i = interp('to pair of a, b:\n  give [a, b]\n\n'
               'r = { x: 1 }\n'
               'ys = pair of (r with x: 9), 7\n')
    assert i.env.get("ys").value == [{"x": 9}, 7]


# ================================================================ plus

def test_plus_produces_a_new_list():
    i = interp('xs = [1, 2]\nys = xs plus 3\n')
    assert i.env.get("ys").value == [1, 2, 3]


def test_plus_leaves_the_original_untouched():
    i = interp('xs = [1, 2]\nys = xs plus 3\n')
    assert i.env.get("xs").value == [1, 2]


def test_plus_chains_left_to_right():
    i = interp('xs = [1]\nys = xs plus 3 plus 4\n')
    assert i.env.get("ys").value == [1, 3, 4]
    assert i.env.get("xs").value == [1]


def test_plus_why_shows_a_node_pointing_at_the_base():
    i = interp('xs = [1, 2]\nys = xs plus 3\n')
    tree = why_tree(i.env.get("ys"))
    assert "plus" in tree
    assert "xs = [2 items]" in tree


def test_plus_on_a_non_list_raises():
    try:
        run('x = 5 plus 1\n')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "not-a-list"


def test_plus_binds_below_arithmetic():
    """`xs plus a + b` reads as `xs plus (a + b)`, not `(xs plus a) + b`
    (which would raise cannot-combine — a list can't `+` a number)."""
    i = interp('xs = [1]\na = 2\nb = 3\nys = xs plus a + b\n')
    assert i.env.get("ys").value == [1, 5]


def test_plus_of_an_arithmetic_expression_directly():
    i = interp('xs = [10]\nys = xs plus (2 * 3 - 1)\n')
    assert i.env.get("ys").value == [10, 5]


def test_plus_is_not_the_string_or_list_plus_operator():
    """`+` on two lists still concatenates (v9.0 A.1) — `plus` is a
    distinct operation (append a bare item), not a spelling of `+`."""
    i = interp('xs = [1, 2]\nys = xs + [3]\nzs = xs plus 3\n')
    assert i.env.get("ys").value == i.env.get("zs").value == [1, 2, 3]


# ================================================================ shapes.py soundness (invariant 3)

def test_with_produces_no_effect():
    from shapes import analyse
    s = analyse('p = { a: 1 }\nq = p with a: 2\nshow q\n')
    assert s.kinds() == ["show"]


def test_plus_produces_no_effect():
    from shapes import analyse
    s = analyse('xs = [1]\nys = xs plus 2\nshow ys\n')
    assert s.kinds() == ["show"]


def test_shapes_walks_into_with_and_plus_for_effects_they_wrap():
    """The operators themselves are pure, but an effect inside a field
    value or item must still reach the static surface."""
    from shapes import analyse
    s = analyse('use http\np = { a: 1 }\n'
               'q = p with a: (ask "https://example.com/a.json")\n')
    assert "ask" in s.kinds()

    s2 = analyse('use http\nxs = [1]\n'
                'ys = xs plus (ask "https://example.com/a.json")\n')
    assert "ask" in s2.kinds()


def test_shapes_never_raises_on_with_or_plus():
    from shapes import analyse
    analyse('p = { a: 1 }\nq = p with a: 2\nxs = [1] plus 2\n')   # must not raise


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
