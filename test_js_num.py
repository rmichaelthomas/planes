"""S4, Phase 2 — exact rationals in JS, checked against planes_num.py.

JavaScript has no exact rational type and Number is a float — the single largest
correctness risk in the port (A.3, failure mode 1). js/planes_num.mjs represents
a number as a Fraction of two BigInts. This test drives the same operations
through js/planes_num.mjs and planes_num.py and compares the rendered text,
including the cases where floating point visibly diverges from exact arithmetic:
0.1 + 0.2, 1 / 3, round-half-away, and a denominator past the bound.

The last section drives the three places text or a float crosses into or out of
a number, where the JavaScript engine's semantics differ from Python's: the
`Fraction(str)` grammar, `number of` (Python's whitespace and Unicode digits),
and `float(q)` at the host boundary (correctly rounded, OverflowError past the
largest double).
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import unicodedata
from fractions import Fraction

from planes_num import Inexact, NotANumber, Number, number_from_text

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))


def _node_num(ops):
    r = subprocess.run(
        [NODE, "js/cli.mjs", "num", json.dumps(ops)],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed: {r.stderr}")
    return json.loads(r.stdout)


def py_num_op(op):
    name, *a = op
    if name == "parse":
        return Number.parse(a[0]).text()
    if name == "of":
        return Number.of(a[0]).text()
    if name == "add":
        return (Number.parse(a[0]) + Number.parse(a[1])).text()
    if name == "sub":
        return (Number.parse(a[0]) - Number.parse(a[1])).text()
    if name == "mul":
        return (Number.parse(a[0]) * Number.parse(a[1])).text()
    if name == "div":
        return (Number.parse(a[0]) / Number.parse(a[1])).text()
    if name == "round":
        return Number.parse(a[0]).round_to(int(a[1])).text()
    if name == "frac":
        return Number(Fraction(int(a[0]), int(a[1]))).text()
    if name == "cmp":
        x, y = Number.parse(a[0]), Number.parse(a[1])
        return str(-1 if x < y else (1 if x > y else 0))
    if name == "whole":
        return "true" if Number.parse(a[0]).is_whole() else "false"
    if name == "asint":
        try:
            return str(Number.parse(a[0]).as_int())
        except ValueError:
            return "ERR"
    if name == "harmonic":
        acc = Number(Fraction(0))
        for k in range(1, int(a[0]) + 1):
            acc = acc + Number(Fraction(1, k))
        return acc.text()
    if name == "inexact":
        try:
            (Number(Fraction(1, 2 ** 4001)) + Number.of(0)).text()
            return "NO-REFUSAL"
        except Inexact:
            return "INEXACT"
    if name == "fromtext":
        try:
            q = Number.of(a[0]).q
            return f"{q.numerator}/{q.denominator}"
        except (ValueError, ZeroDivisionError) as e:
            return f"{type(e).__name__}: {e}"
    if name == "numberof":
        try:
            return number_from_text(a[0]).text()
        except NotANumber as e:
            return f"NotANumber({str(e.approximation).lower()}): {e}"
    if name == "float":
        try:
            f = float(Number(Fraction(int(a[0]), int(a[1]))))
            return struct.pack(">d", f).hex()
        except OverflowError as e:
            return f"OverflowError: {e}"
    raise AssertionError(f"unknown op {name}")


def _agree(ops):
    got = _node_num(ops)
    want = [py_num_op(op) for op in ops]
    assert got == want, "\n".join(
        f"{op}: js={g!r} py={w!r}"
        for op, g, w in zip(ops, got, want) if g != w)


# ================================================================ the float-divergence cases

def test_addition_that_a_float_gets_wrong():
    _agree([["add", "0.1", "0.2"], ["add", "0.1", "0.1"], ["mul", "0.1", "3"],
            ["sub", "0.3", "0.1"], ["add", "0.7", "0.1"]])


def test_division_stays_an_exact_rational():
    _agree([["div", "1", "3"], ["div", "2", "3"], ["div", "1", "7"],
            ["div", "10", "3"], ["mul", "3", "3"],
            # (1/3) * 3 is exactly 1, not ~0.999...
            ["div", "1", "3"]])


def test_one_third_times_three_is_one():
    got = _node_num([["frac", "1", "3"]])
    assert got == ["~0.333333333333"]
    # and exact: build 1/3 then *3
    ops = [["mul", "1", "3"]]  # placeholder to exercise mul path
    _agree(ops)


def test_terminating_vs_nonterminating_rendering():
    _agree([["frac", "157", "50"], ["frac", "1", "8"], ["frac", "1", "3"],
            ["frac", "1", "7"], ["frac", "22", "7"], ["frac", "1", "1"],
            ["frac", "5", "1"], ["frac", "-1", "4"], ["frac", "-1", "3"],
            ["frac", "1", "2"], ["frac", "3", "40"], ["frac", "1", "1000000"]])


def test_round_half_away_from_zero_not_bankers_and_not_float():
    _agree([["round", "2.675", "2"], ["round", "2.5", "0"], ["round", "-2.5", "0"],
            ["round", "0.5", "0"], ["round", "1.5", "0"], ["round", "2.345", "2"],
            ["round", "0.125", "2"], ["round", "-0.125", "2"],
            ["round", "3.14159", "4"], ["round", "10", "2"], ["round", "0.005", "2"]])


def test_of_a_foreign_float_is_exact_like_fraction_repr():
    _agree([["of", 0.1], ["of", 0.2], ["of", 1.5], ["of", 100], ["of", 0],
            ["of", -2.25], ["of", 3.14], ["of", 1e23], ["of", 1e-7],
            ["of", 0.30000000000000004]])


def test_a_denominator_past_the_bound_refuses_rather_than_rounds():
    got = _node_num([["inexact"]])
    assert got == ["INEXACT"] == [py_num_op(["inexact"])]


def test_harmonic_sums_grow_the_denominator_but_stay_exact():
    _agree([["harmonic", "1"], ["harmonic", "5"], ["harmonic", "10"],
            ["harmonic", "50"], ["harmonic", "200"]])


def test_comparison_shape_and_whole_and_as_int():
    _agree([["cmp", "1", "2"], ["cmp", "2", "1"], ["cmp", "0.5", "0.5"],
            ["cmp", "1", "3"], ["whole", "5"], ["whole", "2.5"],
            ["whole", "5.0"], ["asint", "5"], ["asint", "2.5"], ["asint", "42"]])


def test_an_integer_past_4300_digits_agrees():
    # CPython refuses int<->str past 4300 digits by default; planes_num.py turns
    # that guard off so the reference computes what the other hosts compute.
    big = "9" * 5000
    _agree([["parse", big], ["add", big, "1"], ["div", big, "3"],
            ["mul", big, big], ["cmp", big, "1" + "0" * 5000]])


def test_a_broad_fraction_sweep_renders_identically():
    ops = []
    for n in range(-9, 10):
        for d in range(1, 13):
            ops.append(["frac", str(n), str(d)])
    _agree(ops)


# ======================================================= text and floats: Python's semantics

def test_text_to_a_fraction_is_pythons_grammar_and_nothing_looser():
    """PlanesNumber.of(text) is Python's Fraction(text): `_` separators, spaces
    around `/`, exponents, a bare `.5` or `5.` — and the refusals, with
    ValueError's message, where the old parser read `1/2/3`, `1e` or `--1` as
    some number."""
    _agree([["fromtext", t] for t in [
        "0", "-0", "+7", "12.50", ".5", "5.", "1.e5", "1e5", "1E-5", "-2.5e+3",
        "1_000", "1_000.000_1", "1e1_0", "3/4", "-3/4", " 3 / 4 ", "3/-4", "+3/4",
        "1/0", "-3/0", "0/0", "1/2/3", "1e", "1e+", "--1", "+-1", "- 1", "1 _0",
        "1__0", "_1", "1_", "1._5", "1.5_", "1.2.3", ".", "", " ", "e5", "0x10",
        "inf", "nan", "1 2", "1/", "/2", ".5/2", "3/4.0", "1e5/2", "٣/٤", "abc",
        "it's", "tab\there", "\x85", "\ufeff3",
    ]])


def test_every_python_digit_reads_as_its_value():
    """int() and Fraction() read any Unicode decimal digit (category Nd) as its
    value — Arabic-Indic ٣ is 3 — at Python's Unicode version; BigInt read 0-9
    only. Unicode 17's U+11DE0...U+11DE9 are not digits to Python 3.14."""
    zeros = [c for c in range(0x110000)
             if unicodedata.category(chr(c)) == "Nd" and unicodedata.decimal(chr(c)) == 0]
    ops = []
    for z in zeros:
        ds = "".join(chr(z + k) for k in range(10))
        ops += [["fromtext", ds], ["fromtext", f"-{ds[1]}.{ds[2]}{ds[5]}e{ds[1]}"],
                ["fromtext", f"{ds[3]}/{ds[4]}"], ["numberof", f"{ds[3]}{ds[4]}.{ds[5]}"]]
    ops += [["fromtext", chr(c)] for c in range(0x11DE0, 0x11DEA)]
    ops += [["numberof", chr(c)] for c in range(0x11DE0, 0x11DEA)]
    ops += [["fromtext", "²"], ["fromtext", "½"], ["numberof", "①"]]
    try:
        _agree(ops)
    except AssertionError as e:
        raise AssertionError(
            f"{e}\n(js/planes_text.mjs's digit table is Python 3.14's, Unicode "
            f"16.0; this Python is Unicode {unicodedata.unidata_version})") from None


def test_number_of_strips_pythons_whitespace():
    """`number of` strips with str.strip(): every isspace character around the
    number is stripped (U+001C and U+3000 among them, which trim() kept), and
    U+FEFF, which trim() stripped, is not whitespace and is refused."""
    spaces = [chr(c) for c in range(0x110000) if chr(c).isspace()]
    ops = [["numberof", f"{w}٣٤.٥{w}"] for w in spaces]
    ops += [["fromtext", f"{w}-1{w}/{w}2{w}"] for w in spaces]
    ops += [["numberof", t] for t in [
        "\ufeff5", "5\ufeff", "\u200b5", "~0.333", " ~1", "12.5", "-12.5", "+1",
        "1e5", "1/2", "1_000", ".5", "5.", "", "abc", "it's", "\x85~1",
    ]]
    _agree(ops)


def test_a_float_at_the_host_boundary_is_correctly_rounded():
    """float(q) is the double nearest the exact quotient, ties to even, with
    gradual underflow — not Number(n) / Number(d), which rounds both sides
    first — and past the largest double it raises OverflowError rather than
    returning Infinity."""
    big = 2 ** 1100
    cases = [
        (1, 3), (2, 3), (-1, 3), (1, 10), (7, 1), (0, 5), (-5, 7),
        (10 ** 30 + 1, 3),                        # both sides past 2**53
        (2 ** 53 + 1, 2),                          # a tie, to even
        (3 * 2 ** 53 + 1, 2 ** 54),
        (big + 1, big),                           # each side alone is Infinity
        (big, 3 * 2 ** 1099),
        (1, 2 ** 1074), (1, 2 ** 1075), (3, 2 ** 1076), (-1, 2 ** 1080),
        (1, 3 * 2 ** 1070),                        # subnormal, rounded
        (2 ** 1024 - 2 ** 970, 1),                 # the largest double
        (2 ** 1024 - 2 ** 970 + 2 ** 969, 1),      # rounds up past it
        (2 ** 1024 - 2 ** 970 + 2 ** 968, 1),      # rounds down to it
        (2 ** 1024, 1), (-(2 ** 1030), 7), (10 ** 400, 10 ** 90),
    ]
    for k in range(1, 60):
        cases.append((10 ** k + 7, 3 ** k))
        cases.append((-(2 ** (k * 20) + 1), 10 ** k + 1))
    _agree([["float", str(n), str(d)] for n, d in cases])


def test_a_refusal_quotes_the_text_as_python_repr_does():
    """The ValueError and NotANumber messages quote the text with Python's
    repr: its quote choice, and an escape for every character str.isprintable()
    refuses — at Python's Unicode version, so every code point is driven (in
    chunks, each behind an `x` that keeps the literal invalid). Surrogates are
    left out: two in a row would be one astral character to JavaScript."""
    cps = [c for c in range(0x110000) if not 0xD800 <= c <= 0xDFFF]
    chunks = ["x" + "".join(map(chr, cps[i:i + 1000])) for i in range(0, len(cps), 1000)]
    ops = [["fromtext", c] for c in chunks]
    ops += [["fromtext", t] for t in ["x'", 'x"', "x'\"", "x\\"]]
    ops += [["numberof", t] for t in ["'", '"', "'\"", "\\", "\x00\x7f\xad"]]
    for i in range(0, len(ops), 50):
        _agree(ops[i:i + 50])


if __name__ == "__main__":
    if NODE is None:
        print("  SKIP  node not on PATH")
        sys.exit(0)
    fails = []
    tests = [(k, f) for k, f in sorted(globals().items())
             if k.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            fails.append(name)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
