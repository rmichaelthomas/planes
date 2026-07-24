"""Tests for exact numbers.

The case that motivates all of this: `why` must not report a derivation that
contains a silent rounding step. A number that has quietly lost precision
makes `why` answer a question about the answer, not about the program.
"""
import json
import sys

from interp import Interpreter, PlanesError, why_tree
from planes_num import MAX_DENOMINATOR, Inexact, Number


def run(src, **kw):
    return Interpreter(**kw).run(src)


def interp(src, **kw):
    i = Interpreter(**kw)
    i.run(src)
    return i


def val(src, name, **kw):
    return interp(src, **kw).env.get(name)


n = Number.parse


# ================================================================ exactness

def test_the_classic_float_bug_is_gone():
    """0.1 + 0.2 is 0.3. In floats it is 0.30000000000000004."""
    assert val("total = 0.1 + 0.2", "total").value == n("0.3")
    assert run("t = 0.1 + 0.2\nshow text of t") == ["0.3"]


def test_known_float_divergences():
    """Each of these gives a different answer in IEEE floats.

    In Python: 0.1+0.2 == 0.3 is False; round(2.675, 2) is 2.67;
    1.1*3 is 3.3000000000000003; 0.1*3 is 0.30000000000000004.
    """
    i = interp('a = 0.1 + 0.2 == 0.3\n'
               'b = round 2.675 to 2 places\n'
               'c = 1.1 * 3\n'
               'd = 0.1 * 3\n'
               'show text of a\n'
               'show text of b\n'
               'show text of c\n'
               'show text of d')
    assert i.output == ["true", "2.68", "3.3", "0.3"]


def test_repeated_addition_does_not_drift():
    """Ten additions of 0.1 is exactly 1, not 0.9999999999999999."""
    src = "t = 0.1 + 0.1 + 0.1 + 0.1 + 0.1 + 0.1 + 0.1 + 0.1 + 0.1 + 0.1"
    assert val(src, "t").value == n("1")
    assert run(src + "\nshow text of t") == ["1"]


def test_money_arithmetic_is_exact():
    src = ('price = 19.99\n'
           'qty = 3\n'
           'sub = price * qty\n'
           'tax = sub * 0.08\n'
           'total = sub + tax')
    assert val(src, "sub").value == n("59.97")
    assert val(src, "total").value == n("64.7676")


def test_large_integers_do_not_lose_precision():
    """Past 2^53 a float cannot represent consecutive integers."""
    assert val("b = 9007199254740993 * 2", "b").value == n("18014398509481986")


def test_division_stays_exact():
    """1/3 is one third, not 0.3333333333333333."""
    third = val("x = 1 / 3", "x").value
    assert third * 3 == n("1"), "an exact third times three is exactly one"


def test_exact_third_times_three_is_one_in_the_language():
    assert run("x = 1 / 3\ny = x * 3\nshow text of y") == ["1"]


def test_comparison_is_exact():
    assert val("a = 0.1 + 0.2 == 0.3", "a").value is True


# ================================================================ rendering

def test_terminating_decimal_prints_exactly():
    assert n("0.1").text() == "0.1"
    assert n("3.5").text() == "3.5"
    assert n("2").text() == "2"
    assert (n("0") - n("2.5")).text() == "-2.5"


def test_non_terminating_decimal_is_marked_approximate():
    """A third cannot be written exactly, so the output says so."""
    t = (n("1") / n("3")).text()
    assert t.startswith("~"), "an approximation must be visible in the output"
    assert "0.3333" in t


def test_whole_numbers_have_no_decimal_point():
    assert run("x = 4 / 2\nshow text of x") == ["2"]


# ================================================================ rounding

def test_round_is_a_named_operation():
    assert run("x = 1 / 3\nr = round x to 4 places\nshow text of r") == ["0.3333"]


def test_round_appears_in_the_derivation():
    """Rounding is deliberate, so `why` shows it as a step."""
    i = interp("x = 1 / 3\nr = round x to 2 places\nwhy r")
    assert "round to 2 places" in why_tree(i.env.get("r"))


def test_round_half_away_from_zero():
    """2.675 rounds to 2.68. In floats it gives 2.67, because 2.675 is
    not representable — the classic demonstration of the problem."""
    assert n("2.675").round_to(2) == n("2.68")
    assert run("r = round 2.675 to 2 places\nshow text of r") == ["2.68"]


def test_round_to_zero_places():
    assert run("r = round 3.7 to 0 places\nshow text of r") == ["4"]


def test_whole_of():
    assert run("w = whole of 3.7\nshow text of w") == ["4"]
    assert run("w = whole of 3.2\nshow text of w") == ["3"]


def test_round_a_non_number_is_an_error():
    try:
        run('r = round "hello" to 2 places')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "not-a-number"


# ================================================================ boundaries

def test_foreign_floats_become_exact_on_entry():
    """A JSON 0.1 is one tenth from then on, not 0.1000000000000000055."""
    def stub(u):
        return json.dumps({"price": 0.1, "qty": 3})
    i = interp('use http\n'
               'item = ask "https://x/y.json"\n'
               'line = item.price * item.qty\n'
               'plus = line + 0.2\n'
               'show text of plus', http=stub)
    assert i.output == ["0.5"], "0.1 * 3 + 0.2 is exactly 0.5"


def test_exact_value_survives_a_file_round_trip():
    i = interp('use file\n'
               'x = 0.1 + 0.2\n'
               'write [x] to "out.json"', fs={})
    assert '"0.3"' in i.fs["out.json"], \
        "a non-whole exact value goes out as text, not a rounded float"


def test_whole_numbers_write_as_numbers():
    i = interp('use file\nwrite [4 / 2] to "out.json"', fs={})
    assert json.loads(i.fs["out.json"]) == [2]


def test_why_crosses_a_boundary_with_exact_values():
    def stub(u):
        return json.dumps({"price": 0.1})
    v = val('use http\n'
            'item = ask "https://x/y.json"\n'
            'total = item.price + 0.2', "total", http=stub)
    assert v.value == n("0.3")
    tree = why_tree(v)
    assert "entered at network:" in tree
    assert "0.3" in tree


# ================================================================ limits

def test_unbounded_precision_is_refused_not_rounded():
    """A refusal is visible; a silent rounding is not."""
    try:
        Number(1) / Number(MAX_DENOMINATOR * 10 + 1)
        assert False, "should refuse"
    except Inexact as e:
        assert "precision" in str(e)


def test_realistic_fraction_sums_stay_inside_the_bound():
    """Summing 2000 distinct fractions is ordinary work, not pathological."""
    acc = Number(0)
    for k in range(1, 2001):
        acc = acc + Number(1) / Number(k)
    assert acc > Number(7), "the harmonic sum to 2000 is about 8.18"


def test_needs_rounding_error_names_the_fix():
    huge = "1" + "0" * 1250
    try:
        run(f"x = 1 / {huge}")
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "needs-rounding"
        assert e.fix and "round" in e.fix


def test_divide_by_zero_still_caught():
    try:
        run("x = 1 / 0")
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "divided-by-zero"


def test_arithmetic_on_text_is_an_error():
    try:
        run('x = 5 - "hello"')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "not-a-number"
        assert e.fix


def test_comparing_a_number_with_text_is_an_error():
    try:
        run('x = 5 < "hello"')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "cannot-compare"


# ================================================================ integration

def test_count_returns_a_number():
    assert val("c = count of [1, 2, 3]", "c").value == n("3")
    assert run("c = count of [1, 2, 3]\nshow text of c") == ["3"]


def test_average_of_a_list_is_exact():
    src = ('xs = [1, 2, 4]\n'
           'total = 1 + 2 + 4\n'
           'avg = total / (count of xs)')
    v = val(src, "avg")
    assert v.value * 3 == n("7"), "seven thirds times three is exactly seven"


def test_ordinary_program_still_runs():
    i = interp(open("ordinary.planes").read(), fs={})
    assert i.output == ["above threshold"]
    assert i.env.get("avg").value == n("25")


def test_reserved_words_include_round_and_places():
    from lexer import KEYWORDS
    assert "round" in KEYWORDS and "places" in KEYWORDS


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
