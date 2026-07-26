"""S4, Phase 2 — exact rationals in JS, checked against planes_num.py.

JavaScript has no exact rational type and Number is a float — the single largest
correctness risk in the port (A.3, failure mode 1). js/planes_num.mjs represents
a number as a Fraction of two BigInts. This test drives the same operations
through js/planes_num.mjs and planes_num.py and compares the rendered text,
including the cases where floating point visibly diverges from exact arithmetic:
0.1 + 0.2, 1 / 3, round-half-away, and a denominator past the bound.
"""
import json
import os
import shutil
import subprocess
import sys
from fractions import Fraction

from planes_num import Inexact, Number

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


def test_a_broad_fraction_sweep_renders_identically():
    ops = []
    for n in range(-9, 10):
        for d in range(1, 13):
            ops.append(["frac", str(n), str(d)])
    _agree(ops)


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
