"""H6: four-way `sine` agreement, and the determinism claim it backs.

A value language's whole claim is that the same program gives the same
number everywhere. Every other builtin here is exact, so every other builtin
proves that claim by construction: exact rational arithmetic is the same
arithmetic no matter who wrote the tree-walker. `sine` is different — it is
APPROXIMATE at every argument (grammar/vocabulary.json's
`value_properties[0].introduced_by`), computed by a truncated Taylor series
over a stated rational approximation of pi/180, not by anything a CPU FPU or
a math library would give four different answers for. Four independent
ports of that series (`planes_num.py`, `js/planes_num.mjs`,
`grammar/interp.planes`'s `sine-of-degrees`, and Swift's
`PlanesNumber.sineDegrees`) had never been checked against each other digit
for digit before this suite — each host tests its own sine in isolation
(`test_exactness.py`, `js/test/exactness.test.mjs`, `test_swift_num.py`
tests every OTHER numeric op but not sine), and `root` (the other builtin in
`introduced_by`, and the only other one) fares no better: `test_square_root.py`
checks Python/JS/self-hosted but has no Swift counterpart at all.

It has bitten once already: `test_world_kernel_conformance.py`'s docstring
records Python and JS `sine` disagreeing "in a low decimal digit" during the
kernel spike, and that fixture now rounds before comparing rather than
requiring exact agreement. This suite is the one that was missing — it
sweeps a broad set of angles (and, since `root` is the only other operation
that can return an approximate value, a broad set of radicands) through all
four hosts and asserts the exact text form is identical, byte for byte.

No `cosine` exists to compare (asserted below, against
`vocabulary.json`, not eyeballed) — `sine` and `root` are the whole
approximate surface.

What "the exact text form" means here is deliberately `Number.text()` /
`PlanesNumber.text()` / self-hosted `builtin-text`, not numerator/denominator
read off the internals: `text()` is exactly what `show text of (sine of d)`
prints in a running program (`interp.py`'s `fmt()` calls `.text()` for a
Number; the self-hosted `text` builtin dispatches to `builtin-text` the same
way `show` does) — see `test_the_text_form_is_what_show_would_print` for the
explicit round trip through real `show` output. Two numbers with different
text disagree exactly when the underlying rationals differ, since `.text()`
is a deterministic rendering of the reduced fraction.

Angle/radicand coverage, all deduplicated by value before evaluation:
  - `sine`: every integer degree from -720 to 720 (1441 values); the
    quarter turns out to 3 full turns and their +/-1 neighbours; three large
    values (360000030, 10**12 + 45, -10**9); four fractional angles
    (1/3, 45/2, 22/7, and 0.1 typed as an exact DECIMAL literal, not a
    fraction, so decimal-point parsing is exercised too); and 250 angles
    from a seeded PRNG (`random.Random(SEED)`) mixing wide-range integers
    and arbitrary fractions.
  - `root`: `test_square_root.py`'s own EXACT/INEXACT acceptance lists; the
    same four fractional/decimal values; the same two large values; and 200
    non-negative values from a seeded PRNG, weighted so some land on perfect
    squares (the exact branch) and most do not (the approximate branch).

Each host is driven the way its sibling suites already drive it:
  - Python: `planes_num.sine_degrees` / `root_of`, directly — the reference.
  - JavaScript: one `node js/cli.mjs num '<json ops>'` subprocess call,
    batching every value into a single process (`test_swift_num.py`'s and
    `test_js_num.py`'s pattern). `sine`/`root` num-ops were added to
    `js/cli.mjs` for this suite, mirroring `add`/`sub`/`round`.
  - `grammar/interp.planes`: one Python process, self-hosted interpreter
    loaded once, then driven per value through `node-of-source` / `eval` /
    `builtin-text` — `test_square_root.py`'s `_self_hosted()` pattern,
    exactly.
  - Swift: one `planes-swift num '<json ops>'` subprocess call
    (`swift_host.command`), through `sine`/`root` num-ops added to
    `NumCommand.swift` for this suite, mirroring the JS addition op for op.
    Swift has no `run` command yet (`README.md`'s "Three implementations" —
    a fourth is under way but does not run programs), so its `PlanesNumber`
    is driven directly, the way `test_swift_num.py` already drives every
    other numeric op.

If a host disagrees, this suite does not round the comparison away: the
failing value is reported explicitly and the suite fails until the
underlying host is fixed to match the Python reference.
"""
import json
import os
import random
import subprocess
import sys
from fractions import Fraction

import interp
from interp import Deriv, Traced
from planes_num import Number, root_of, sine_degrees
from swift_host import SWIFT, command

REPO = os.path.dirname(os.path.abspath(__file__))
NODE = "node"
SEED = 20260913  # today, per the sprint doc — fixed so the sweep never flaps


# =========================================================== value sets


def _sine_values():
    """Every distinct angle (as a Fraction) this suite checks, with a label."""
    seen = {}

    def add(frac, label=None):
        frac = Fraction(frac)
        seen.setdefault(frac, label or str(frac))

    for d in range(-720, 721):
        add(d)

    for base in (0, 90, 180, 270, 360, 450, 540, 630, 720, 810, 900, 990, 1080):
        for signed in (base, -base):
            for delta in (-1, 0, 1):
                add(signed + delta)

    for v in (360000030, 10 ** 12 + 45, -10 ** 9):
        add(v)

    add(Fraction(1, 3), "1/3")
    add(Fraction(45, 2), "45/2")
    add(Fraction(22, 7), "22/7")
    add(Fraction(1, 10), "0.1")  # literal override below: decimal, not 1/10

    rng = random.Random(SEED)
    for _ in range(250):
        if rng.random() < 0.5:
            add(rng.randint(-10 ** 9, 10 ** 9))
        else:
            num = rng.randint(-10 ** 6, 10 ** 6)
            den = rng.randint(1, 5000)
            add(Fraction(num, den))

    return seen


def _root_values():
    """Every distinct non-negative radicand this suite checks, with a label."""
    seen = {}

    def add(frac, label=None):
        frac = Fraction(frac)
        seen.setdefault(frac, label or str(frac))

    # test_square_root.py's own acceptance lists, exact and approximate.
    for v in ("0", "1", "4", "9", "16", "25", "100", "10000", "1000000",
              "0.25", "2.25", "6.25", "0.01", "0.0001", "12321", "99980001",
              "(1 / 9)", "(4 / 9)", "(49 / 64)", "(1 / 4)"):
        add(Fraction(v.strip("()").replace(" / ", "/")))
    for v in ("2", "3", "5", "6", "7", "8", "10", "0.5", "1.5",
              "(2 / 3)", "(1 / 3)", "1.1", "99980002"):
        add(Fraction(v.strip("()").replace(" / ", "/")))

    add(Fraction(1, 3), "1/3")
    add(Fraction(45, 2), "45/2")
    add(Fraction(22, 7), "22/7")
    add(Fraction(1, 10), "0.1")  # literal override below: decimal, not 1/10

    for v in (360000030, 10 ** 12 + 45):
        add(v)

    rng = random.Random(SEED + 1)
    for _ in range(200):
        r = rng.random()
        if r < 0.3:
            base = rng.randint(0, 10 ** 6)
            add(base * base)
        elif r < 0.65:
            add(rng.randint(0, 10 ** 9))
        else:
            num = rng.randint(0, 10 ** 6)
            den = rng.randint(1, 5000)
            add(Fraction(num, den))

    return seen


# 0.1 must be typed as a decimal literal, not a fraction, in every host so
# decimal-point parsing is what gets exercised — override both literal forms
# for exactly that one value.
_DECIMAL_OVERRIDE = {Fraction(1, 10): "0.1"}


def _num_op_literal(frac):
    """The text `Number.parse` / `PlanesNumber.parse` reads directly — the
    grammar all three hosts' Fraction-from-string readers share (a leading
    sign, digits, an optional `/denominator` OR an optional `.fraction`)."""
    if frac in _DECIMAL_OVERRIDE:
        return _DECIMAL_OVERRIDE[frac]
    return f"{frac.numerator}/{frac.denominator}" if frac.denominator != 1 else str(frac.numerator)


def _source_literal(frac):
    """The Planes SOURCE text for this value — `f of x` binds tighter than
    `/`, so a fractional argument needs its own parens (`sine of 1/3` would
    parse as `(sine of 1) / 3`)."""
    if frac in _DECIMAL_OVERRIDE:
        return _DECIMAL_OVERRIDE[frac]
    if frac.denominator == 1:
        return str(frac.numerator)
    return f"({frac.numerator} / {frac.denominator})"


SINE_VALUES = _sine_values()
ROOT_VALUES = _root_values()
SINE_ORDER = sorted(SINE_VALUES, key=lambda f: (f.denominator, f.numerator))
ROOT_ORDER = sorted(ROOT_VALUES, key=lambda f: (f.denominator, f.numerator))


# =========================================================== host runners


def _python_results(values, fn):
    return [fn(Number(v)).text() for v in values]


def _have_node():
    try:
        subprocess.run([NODE, "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _js_num(ops):
    r = subprocess.run([NODE, os.path.join(REPO, "js", "cli.mjs"), "num", json.dumps(ops)],
                        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node js/cli.mjs num failed: {r.stderr}")
    return json.loads(r.stdout)


def _swift_num(ops):
    r = subprocess.run(command("num", json.dumps(ops)), cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"planes-swift num failed: {r.stderr}")
    return json.loads(r.stdout)


class SelfHosted:
    """One self-hosted interpreter, loaded once, reused for every value —
    `test_square_root.py`'s `_self_hosted()`, kept alive across many calls
    instead of being rebuilt per case."""

    def __init__(self):
        self.i = interp.Interpreter()
        self.i.run_file(os.path.join(REPO, "grammar", "interp.planes"))
        self.i.run("__env = []\n")
        self.env = self.i.env.get("__env")

    def eval_text(self, src):
        traced = Traced(src, Deriv("literal", "<s>", src, []))
        node = self.i.call("node-of-source", [traced], self.i.env)
        v = self.i.call("eval", [node, self.env], self.i.env)
        return self.i.call("builtin-text", [v], self.i.env).value.get("value")


# =========================================================== the agreement


def _compare(op_name, planes_fn, values, order):
    """Python (reference) vs. self-hosted vs. JS vs. Swift, for every value
    in `order`, on `op_name` (`"sine"` or `"root"`). Returns the divergences
    found, `[]` when every available host agrees with Python."""
    literals = [_num_op_literal(v) for v in order]
    source_literals = [_source_literal(v) for v in order]
    labels = [values[v] for v in order]

    want = _python_results(order, planes_fn)

    sh = SelfHosted()
    got_self_hosted = [sh.eval_text(f"{op_name} of {lit}") for lit in source_literals]

    got_js = None
    if _have_node():
        got_js = _js_num([[op_name, lit] for lit in literals])

    got_swift = None
    if SWIFT is not None:
        got_swift = _swift_num([[op_name, lit] for lit in literals])

    divergences = []
    for idx, label in enumerate(labels):
        if got_self_hosted[idx] != want[idx]:
            divergences.append((op_name, "self-hosted", label, want[idx], got_self_hosted[idx]))
        if got_js is not None and got_js[idx] != want[idx]:
            divergences.append((op_name, "javascript", label, want[idx], got_js[idx]))
        if got_swift is not None and got_swift[idx] != want[idx]:
            divergences.append((op_name, "swift", label, want[idx], got_swift[idx]))
    return divergences


def test_sine_agrees_across_python_javascript_self_hosted_and_swift():
    divergences = _compare("sine", sine_degrees, SINE_VALUES, SINE_ORDER)
    assert not divergences, "\n".join(
        f"sine of {label}: python={want!r} {host}={got!r}"
        for _op, host, label, want, got in divergences)


def test_root_agrees_across_python_javascript_self_hosted_and_swift():
    divergences = _compare("root", root_of, ROOT_VALUES, ROOT_ORDER)
    assert not divergences, "\n".join(
        f"root of {label}: python={want!r} {host}={got!r}"
        for _op, host, label, want, got in divergences)


# =========================================================== show, not just text()


def test_the_text_form_is_what_show_would_print():
    """`.text()` is the comparison this suite relies on everywhere else —
    this is the explicit proof that it is what a running program's `show`
    actually prints, in the two hosts that can run a whole program
    (Swift has no `run` yet). A handful of representative values, not the
    full sweep: this is about the CHANNEL, not further angle coverage."""
    sample = [Fraction(0), Fraction(30), Fraction(-1, 3), Fraction(45, 2), Fraction(10 ** 12 + 45)]

    py_program = "\n".join(f"show text of (sine of {_source_literal(v)})" for v in sample) + "\n"
    it = interp.Interpreter()
    py_shown = it.run(py_program)
    py_direct = [sine_degrees(Number(v)).text() for v in sample]
    assert py_shown == py_direct, (py_shown, py_direct)

    if not _have_node():
        return
    path = os.path.join(REPO, ".ci-sine-show.planes")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(py_program)
    try:
        r = subprocess.run([NODE, os.path.join(REPO, "js", "cli.mjs"), "run", path],
                            capture_output=True, text=True, cwd=REPO)
        js_shown = json.loads(r.stdout)["output"]
    finally:
        os.unlink(path)
    assert js_shown == py_direct, (js_shown, py_direct)


# =========================================================== the vocabulary claim


def test_sine_and_root_are_the_only_approximate_builtins():
    """This suite's scope is exhaustive only if this is true: if a third
    builtin ever starts returning approximate values (a `cosine`, a
    `tangent`), it enters `introduced_by` and this assertion — and this
    docstring's claim of exhaustive coverage — breaks until the new builtin
    gets its own four-way sweep here."""
    with open(os.path.join(REPO, "grammar", "vocabulary.json"), encoding="utf-8") as fh:
        vocab = json.load(fh)
    exactness = next(p for p in vocab["value_properties"] if p["property"] == "exactness")
    assert exactness["introduced_by"] == ["sine", "root"]


# =========================================================== the counts, for the PR


def test_the_sweep_is_broad_and_deduplicated():
    """Not a correctness check — a guard against this suite quietly shrinking
    to a handful of cases over time."""
    assert len(SINE_VALUES) > 1500, len(SINE_VALUES)
    assert len(ROOT_VALUES) > 150, len(ROOT_VALUES)
    # dict keys are already unique; this documents that intent as an assertion.
    assert len(set(SINE_VALUES)) == len(SINE_VALUES)
    assert len(set(ROOT_VALUES)) == len(ROOT_VALUES)


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
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
