"""A value carries whether it is exact — the reference, and all three agreeing.

A number is APPROXIMATE when the true result of the operation that produced it
cannot be represented as a rational, and EXACT otherwise. The property rides on
the value, not on the expression that read it, so it survives being stored in a
list, pulled back out, and used in arithmetic a thousand operations later.

Phase 1 landed the property INERT: it exists, it propagates, and nothing in the
language produces an approximate value. The synthetic marker used here —
`with_approx` — is the same one `sine` uses, so what these tests prove about
propagation is what `sine`'s results actually get.

The JavaScript half of the same claims is js/test/exactness.test.mjs; the
agreement between the two, and with the interpreter-in-Planes, is the last
section here.
"""
import os
import shutil
import subprocess
import sys

from planes_num import MAX_DENOMINATOR, Approximation, Inexact, Number

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))

MARK = Approximation("sine", "test scaffolding")


def n(v):
    return Number.of(v)


def approx(v):
    return n(v).with_approx(MARK)


# ---- exact is the default, and every operation preserves it -----------------


def test_a_number_is_exact_unless_it_says_otherwise():
    for v in (0, 1, -7, "0.1", "12.5"):
        assert n(v).is_exact, v
        assert n(v).approx is None, v
    assert (n(1) / n(3)).is_exact


def test_exact_combined_with_exact_stays_exact():
    a = n(1) / n(3)
    b = n("0.1")
    for r in (a + b, a - b, a * b, a / b, -a, -b):
        assert r.is_exact
    # and the arithmetic itself is unchanged
    assert (a * n(3)).text() == "1"
    assert (n("0.1") + n("0.2")).text() == "0.3"


# ---- approximate propagates through everything ------------------------------


def test_anything_touching_an_approximate_value_is_approximate():
    a = approx("0.5")
    e = n(4)
    cases = {
        "approx + exact": a + e, "exact + approx": e + a,
        "approx - exact": a - e, "exact - approx": e - a,
        "approx * exact": a * e, "exact * approx": e * a,
        "approx / exact": a / e, "exact / approx": e / a,
        "negated": -a, "approx + approx": a + a,
    }
    for name, r in cases.items():
        assert not r.is_exact, name
        assert r.approx == MARK, f"{name} keeps the entry point"


def test_the_entry_point_survives_a_long_chain_of_exact_operations():
    v = approx("0.5")
    for _ in range(200):
        v = ((v + n(1)) * n(2)) / n(2) - n(1)
    assert not v.is_exact
    assert v.approx == MARK, "200 operations later, it still names where it entered"


def test_the_entry_point_is_shared_by_reference_not_copied():
    a = approx("0.5")
    assert (a + n(1)).approx is a.approx, "one record, however long the chain"
    assert ((a * n(3)) / n(7)).approx is a.approx


def test_an_approximate_value_carried_through_a_collection_is_still_approximate():
    xs = [n(1), approx("0.5"), n(3)]
    assert [x.is_exact for x in xs] == [True, False, True]
    rest = xs[1:]                       # what `rest of` does
    assert not rest[0].is_exact
    assert rest[0].approx == MARK


# ---- the two rules that look like exceptions --------------------------------


def test_round_to_places_returns_an_exact_value():
    third = n(1) / n(3)
    assert third.is_exact
    rounded = third.round_to(2)
    assert rounded.is_exact, "0.33 is the exact result of the operation asked for"
    assert rounded.text() == "0.33"


def test_rounding_money_keeps_it_exact():
    """Three items at 19.99 with 8.25% tax, rounded to the cent.

    If rounding marked values approximate, every invoice in the corpus would
    come out flagged and the exact-money claim would be destroyed by the very
    feature meant to make precision visible.
    """
    subtotal = n("19.99") * n(3)
    tax = (subtotal * n("0.0825")).round_to(2)
    total = subtotal + tax
    assert subtotal.text() == "59.97"
    assert tax.text() == "4.95"
    assert total.text() == "64.92"
    for v in (subtotal, tax, total):
        assert v.is_exact


def test_rounding_an_approximate_value_does_not_launder_it_back_to_exact():
    r = approx("0.3333").round_to(2)
    assert not r.is_exact
    assert r.approx == MARK


def test_equality_between_approximate_values_has_no_tolerance():
    a = approx("0.5")
    b = approx("0.5")
    c = approx("0.5000000000000000000000000000001")
    assert a == b, "equal rationals are equal"
    assert a != c, "unequal rationals are unequal, however close"
    assert a == n("0.5"), "an approximate value equals an exact one of the same rational"
    assert a < c, "ordering is the plain rational ordering too"


def test_no_epsilon_or_tolerance_constant_exists_in_the_numeric_tower():
    """The no-tolerance rule, checked against the code rather than the prose.

    Docstrings and comments are stripped first: this file's own tower SAYS
    "no epsilon, no tolerance" in three places, and a check that cannot tell
    naming a thing from doing it is not a check.
    """
    import ast
    with open(os.path.join(REPO, "planes_num.py"), encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    code = ast.unparse(tree)
    for word in ("epsilon", "EPSILON", "tolerance", "1e-"):
        assert word not in code, f"{word} appears in the numeric tower's code"


# ---- the property is not the rendering --------------------------------------


def test_the_tilde_in_rendering_means_non_terminating_not_approximate():
    """Two marks, two questions, never conflated.

    A third is EXACT and prints with a leading `~` because its decimal
    expansion does not terminate. A half marked approximate prints without one.
    """
    third = n(1) / n(3)
    assert third.is_exact
    assert third.text().startswith("~")

    half = approx("0.5")
    assert not half.is_exact
    assert half.text() == "0.5"


def test_the_bound_still_refuses_rather_than_approximating():
    from fractions import Fraction
    v = Number(Fraction(1, MAX_DENOMINATOR))
    try:
        v / n(3)
    except Inexact:
        return
    raise AssertionError("past the bound must refuse, not become a new kind of approximate")


# ---- nothing in the language produces one yet (Phase 1 lands inert) ---------


def test_no_corpus_program_produces_an_approximate_value():
    """The whole corpus, run, with every number reached checked.

    Phase 1 adds the property and nothing else: if any program's values come
    out approximate before `sine` exists, the property is leaking.
    """
    import glob

    from host import TestHost
    from interp import Interpreter, PlanesError, Traced
    from lexer import PlanesSyntaxError

    def walk(v, seen):
        if isinstance(v, Number):
            seen.append(v)
        elif isinstance(v, Traced):
            walk(v.value, seen)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x, seen)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x, seen)

    checked = 0
    programs = 0
    for path in sorted(glob.glob(os.path.join(REPO, "corpus", "*.planes"))):
        with open(path, encoding="utf-8") as f:
            src = f.read()
        itp = Interpreter(host=TestHost())
        try:
            itp.run(src)
        except (PlanesError, PlanesSyntaxError, RecursionError):
            pass                        # a program that refuses still has values
        programs += 1
        seen = []
        walk(itp.env.vars, seen)        # every top-level binding, values and inside collections
        for v in seen:
            assert v.is_exact, (
                f"{os.path.basename(path)} produced an approximate value before `sine` exists "
                f"— the property is leaking")
            checked += 1
    assert programs >= 40, f"only {programs} corpus programs found"
    assert checked > 100, f"the walk reached only {checked} numbers — it is barely testing anything"


# ---- the three implementations agree on the property ------------------------

# One battery, three implementations, same answers. Each entry is
# (expression, expected-text, expected-exact).
BATTERY = [
    ("1 + 2", "3", True),
    ("1 / 3", "~0.333333333333", True),
    ("(1 / 3) * 3", "1", True),
    ("0.1 + 0.2", "0.3", True),
    ("round (1 / 3) to 2 places", "0.33", True),
    ("round 19.99 to 1 places", "20", True),
    ("(19.99 * 3) + round ((19.99 * 3) * 0.0825) to 2 places", "64.92", True),
    ("whole of 7.9", "8", True),
    ("count of [1, 2, 3]", "3", True),
    ("0 - 5", "-5", True),
    ("2 * (3 + 4)", "14", True),
]


def _reference(expr):
    from host import TestHost
    from interp import Interpreter
    itp = Interpreter(host=TestHost())
    itp.run(f"let v = {expr}\nshow text of v\n")
    v = itp.env.get("v").value
    return itp.output[0], v.is_exact


def _port(expr):
    src = f"let v = {expr}\nshow text of v\n"
    r = subprocess.run([NODE, "js/cli.mjs", "exactness", src],
                       capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stderr
    import json
    d = json.loads(r.stdout)
    return d["text"], d["exact"]


def _self_hosted(expr):
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import run_corpus_selfhosted as sh
    src = f"let v = {expr}\nshow text of v\n"
    out, tag = sh.planes_run(src, {})
    assert tag is None, f"{expr}: self-hosted failed with {tag}"
    state = sh._planes().call(
        "execute-program-with", [sh._t(src), sh._t(sh.inert_io())], sh._planes().env).value
    v = next(b["value"] for b in state["env"] if b["name"] == "v")
    return out[0], v["approx"] is None


def test_the_three_implementations_agree_on_text_and_exactness():
    for expr, want_text, want_exact in BATTERY:
        got = _reference(expr)
        assert got == (want_text, want_exact), f"reference {expr}: {got}"
        if NODE is not None:
            assert _port(expr) == got, f"port {expr}: {_port(expr)} vs {got}"
        assert _self_hosted(expr) == got, f"self-hosted {expr}: {_self_hosted(expr)} vs {got}"


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
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
