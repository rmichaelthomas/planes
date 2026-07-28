"""Tests for the value-model semantics build.

Three locked decisions: scope-walking assignment (V-Q5), record literals
(v2.0 §35), and equality through the guard `<` already uses (V-Q1), which
also removes truthy as a third notion of sameness.
"""
import json
import sys

from interp import Interpreter, PlanesError, why_tree
from parser import PlanesSyntaxError


def run(src, **kw):
    return Interpreter(**kw).run(src)


def interp(src, **kw):
    i = Interpreter(**kw)
    i.run(src)
    return i


def val(src, name, **kw):
    return interp(src, **kw).env.get(name)


def raises(tag, fn):
    try:
        fn()
    except PlanesError as e:
        assert e.tag == tag, f"expected tag {tag!r}, got {e.tag!r}: {e}"
        return e
    raise AssertionError(f"expected PlanesError {tag!r}, nothing raised")


# ================================================================ binding (V-Q5)

def test_summing_a_list_in_a_loop_produces_the_sum():
    src = ('total = 0\n'
           'for each n in [1, 2, 3, 4, 5]:\n'
           '  total = total + n\n'
           'show text of total')
    assert run(src) == ["15"]


def test_why_on_the_accumulated_total_shows_each_addition():
    src = ('total = 0\n'
           'for each n in [1, 2, 3]:\n'
           '  total = total + n\n')
    tree = why_tree(val(src, "total"))
    assert tree.count("+ =") == 3, "one derivation node per accumulation step"
    assert "total = 0" in tree
    assert "total = 1" in tree
    assert "total = 3" in tree
    assert "total = 6" in tree


def test_parameter_named_like_an_outer_variable_does_not_modify_it():
    src = ('x = 100\n'
           'to bump of x:\n'
           '  x = x + 1\n'
           '  give x\n'
           'y = bump of 5\n'
           'show text of x\n'
           'show text of y')
    assert run(src) == ["100", "6"]


def test_let_inside_a_loop_shadows_and_does_not_escape():
    src = ('total = 0\n'
           'for each n in [1, 2, 3]:\n'
           '  let total = n\n'
           'show text of total')
    assert run(src) == ["0"]


def test_let_accumulator_hazard_is_now_refused_a_q9():
    """The exact A-Q9 cold-start failure (grammar/vocabulary.json's
    binding_semantics hazard text): an agent given only the grammar files
    wrote `let total = total + order.amount` inside a `for each`.
    eval_foreach still builds a fresh Env per iteration and `let` still
    binds locally into it, exactly as before (V-Q5, untouched by this
    build) -- the write would still be discarded when the iteration ends.
    What changed is that the program no longer reaches that write at all:
    `Interpreter.run` now calls `find_discarded_writes` (parser.py) on the
    freshly parsed AST before executing a single statement, and this exact
    shape is refused with the `discarded-write` tag instead of silently
    writing 0 (the discarded-write build, reports/REPORT_VALUES.md's V-Q1
    reasoning extended: a `0` here is true about the computation and
    useless about the mistake)."""
    src = ('use file\n'
           'let total = 0\n'
           'for each order in [{ amount: 3 }, { amount: 4 }]:\n'
           '  let total = total + order.amount\n'
           'write total to "total.json"')
    try:
        interp(src, fs={})
        assert False, "should have raised discarded-write"
    except PlanesError as e:
        assert e.tag == "discarded-write"
        assert "'total'" in e.detail
        assert "let" in e.fix


def test_bare_assignment_accumulator_writes_the_sum():
    """The A-Q9 fix: dropping `let` from the accumulating line lets `=`
    walk the enclosing scopes and rebind the outer total instead."""
    i = interp('use file\n'
               'total = 0\n'
               'for each order in [{ amount: 3 }, { amount: 4 }]:\n'
               '  total = total + order.amount\n'
               'write total to "total.json"', fs={})
    assert json.loads(i.fs["total.json"]) == 7


def test_assignment_inside_if_still_escapes():
    src = ('x = 1\n'
           'if true:\n'
           '  x = 2\n'
           'show text of x')
    assert run(src) == ["2"]


# ================================================================ records

def test_record_literal_parses_evaluates_and_field_accesses():
    src = ('p = { first: "Ada", last: "Lovelace" }\n'
           'show p.first\n'
           'show p.last')
    assert run(src) == ["Ada", "Lovelace"]


def test_record_nests_three_deep_addressed_by_path():
    src = 'r = { a: { b: { c: 42 } } }\nshow text of r.a.b.c'
    assert run(src) == ["42"]


def test_duplicate_field_name_is_a_syntax_error():
    try:
        run('r = { a: 1, a: 2 }')
        raise AssertionError("expected a PlanesSyntaxError")
    except PlanesSyntaxError as e:
        assert "twice" in str(e)


def test_trailing_comma_accepted():
    src = 'r = { a: 1, b: 2, }\nshow text of r.a'
    assert run(src) == ["1"]


def test_keyword_like_field_name_works():
    src = 'r = { to: "x", from: "y" }\nshow r.to\nshow r.from'
    assert run(src) == ["x", "y"]


def test_record_round_trips_through_write_to():
    i = interp('use file\n'
               'r = { a: 1, b: "hi", c: [1, 2, 3] }\n'
               'write r to "out.json"', fs={})
    written = json.loads(i.fs["out.json"])
    assert written == {"a": 1, "b": "hi", "c": [1, 2, 3]}


# ================================================================ equality (V-Q1)

def test_equal_numbers_same_representation():
    assert val("a = (1 == 1.0)", "a").value is True


def test_equal_numbers_exact_arithmetic():
    assert val("a = (0.1 + 0.2 == 0.3)", "a").value is True


def test_number_and_text_cannot_compare():
    raises("cannot-compare", lambda: run('a = (5 == "5")'))


def test_bool_and_number_cannot_compare():
    raises("cannot-compare", lambda: run('a = (true == 1)'))


def test_zero_and_false_cannot_compare():
    raises("cannot-compare", lambda: run('a = (0 == false)'))


def test_nothing_equals_nothing_is_an_error():
    e = raises("cannot-compare", lambda: run('a = (nothing == nothing)'))
    assert "is nothing" in e.fix


def test_is_nothing_tests_absence():
    assert val("x = nothing\nb = x is nothing", "b").value is True
    assert val("x = 5\nb = x is nothing", "b").value is False


def test_equal_lists():
    assert val("a = ([1, 2] == [1, 2])", "a").value is True


def test_lists_with_a_type_mismatch_inside_raise():
    raises("cannot-compare", lambda: run('a = ([1, 2] == [1, "2"])'))


def test_lists_of_different_length_are_unequal_not_an_error():
    assert val('a = ([1, 2] == [1, 2, 3])', "a").value is False


def test_equal_records():
    assert val("a = ({ a: 1 } == { a: 1 })", "a").value is True


def test_records_with_different_fields_raise_naming_them():
    e = raises("cannot-compare", lambda: run('a = ({ a: 1 } == { b: 1 })'))
    assert "a" in e.detail and "b" in e.detail


def test_if_requires_a_yes_no_value():
    raises("not-a-yes-no", lambda: run('if 0:\n  show "x"'))


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
