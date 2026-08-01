"""square-root-spec.md, asserted.

The thirteenth builtin, and the first whose exactness its ARGUMENT decides.
Everything in the spec's §8 acceptance list is a test here, and the three-way
agreement is the one that matters most: a value language's whole claim is that
the same program gives the same number everywhere, and `root` is the first
operation where "the same number" and "the same exactness" are two claims
rather than one.
"""

import json
import os
import subprocess
import sys

import interp
from interp import Deriv, PlanesError, Traced

REPO = os.path.dirname(os.path.abspath(__file__))
NODE = "node"


# ---- the rule ---------------------------------------------------------------

EXACT = ["0", "1", "4", "9", "16", "25", "100", "10000", "1000000",
         "0.25", "2.25", "6.25", "0.01", "0.0001", "12321", "99980001",
         "(1 / 9)", "(4 / 9)", "(49 / 64)", "(1 / 4)"]
INEXACT = ["2", "3", "5", "6", "7", "8", "10", "0.5", "1.5",
           "(2 / 3)", "(1 / 3)", "1.1", "99980002"]


def _run_py(src):
    it = interp.Interpreter()
    it.run(f"__r = {src}\n")
    return it.env.get("__r").value


def test_a_perfect_square_is_exact_and_correct():
    """`root of 9` is 3, and it is EXACT. Returning "approximately 3" would
    report a property of the implementation's laziness, not of the number."""
    for src in EXACT:
        v = _run_py(f"root of {src}")
        assert v.is_exact, f"root of {src} came back approximate"
        squared = _run_py(f"(root of {src}) * (root of {src})")
        assert squared.q == _run_py(src).q, f"root of {src} does not square back"


def test_what_is_not_a_perfect_square_is_approximate():
    """And approximate for the reason the entry rule gives: the true result
    cannot be represented as a rational."""
    for src in INEXACT:
        v = _run_py(f"root of {src}")
        assert not v.is_exact, f"root of {src} claimed to be exact"
        assert v.approx.op == "root"


def test_the_first_thirty_places_of_the_ones_everybody_knows():
    """Against the true decimal expansions, not against this implementation's
    own output — a self-consistent wrong answer is the failure mode a test
    written from the code cannot see."""
    known = {
        "2": "1.41421356237309504880168872421",     # ...4209698, rounds up at 30
        "3": "1.732050807568877293527446341506",
        "5": "2.236067977499789696409173668731",
        "10": "3.162277660168379331998893544433",
    }
    for src, expected in known.items():
        assert _run_py(f"root of {src}").text() == expected, src


def test_an_approximate_argument_gives_an_approximate_result():
    """§5. `root of (sine of 30)` is approximate whatever the radicand looks
    like: the input was already not the number it claimed to be."""
    v = _run_py("root of (sine of 30)")
    assert not v.is_exact
    # And the exact path preserves it too — this is the branch that could
    # silently launder an approximate value back to exact.
    laundered = _run_py("root of ((sine of 30) * 0 + 9)")
    assert not laundered.is_exact, "the exact branch laundered an approximate argument"


def test_equality_has_no_tolerance():
    """§7. Two roots of two multiply to something that is not 2, and `==`
    says so rather than hiding it behind an epsilon nobody chose."""
    assert _run_py("(root of 2) * (root of 2) == 2") is False
    assert _run_py("root of 9 == 3") is True


def test_a_negative_radicand_is_refused_and_names_the_fix():
    """§3. There is no imaginary number here, and inventing one for a single
    builtin would be a larger decision than this builtin made."""
    try:
        _run_py("root of (0 - 1)")
    except PlanesError as e:
        assert e.tag == "not-a-number"
        assert "square root of -1" in e.detail
        assert "no imaginary number" in e.fix
    else:
        raise AssertionError("root of -1 did not refuse")


def test_a_user_function_named_root_shadows_the_builtin():
    """The names mandate applies to the thirteenth builtin like the other
    twelve."""
    it = interp.Interpreter()
    it.run("to root of x:\n  give 99\n__r = root of 9\n")
    assert it.env.get("__r").value.q == 99


# ---- the three implementations ----------------------------------------------


def _self_hosted():
    i = interp.Interpreter()
    i.run_file(os.path.join(REPO, "grammar", "interp.planes"))
    i.run("__env = []\n")
    return i, i.env.get("__env")


def test_all_three_implementations_agree_on_value_and_exactness():
    """The claim a value language lives on. `root` is the first operation
    where the answer is TWO facts — the number and whether it is exact — and
    an implementation could get either one wrong on its own.

    The self-hosted interpreter has the hardest job here: Python and
    JavaScript read a numerator and denominator straight off the fraction,
    and `grammar/interp.planes` cannot look inside a number at all, so it
    recovers them by continued fraction. `root of (1 / 9)` is the case that
    proves it — 1/3 exactly, where a naive port returns an approximation.
    """
    cases = EXACT + INEXACT
    i, env = _self_hosted()

    def planes_eval(src):
        node = i.call("node-of-source", [Traced(src, Deriv("literal", "<s>", src, []))], i.env)
        v = i.call("eval", [node, env], i.env)
        return (i.call("builtin-text", [v], i.env).value.get("value"),
                bool(v.value.get("approx")))

    diverged = []
    for c in cases:
        src = f"root of {c}"
        v = _run_py(src)
        want = (v.text(), not v.is_exact)
        got = planes_eval(src)
        if want != got:
            diverged.append((c, want, got))
    assert not diverged, f"python vs self-hosted: {diverged}"

    if not _have_node():
        return
    prog = "\n".join(f"show text of (root of {c})" for c in cases) + "\n"
    out = _js_output(prog)
    for c, got in zip(cases, out):
        want = _run_py(f"root of {c}").text()
        assert want == got, f"python vs javascript on root of {c}: {want!r} != {got!r}"


def _have_node():
    try:
        subprocess.run([NODE, "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _js_output(program):
    path = os.path.join(REPO, ".ci-root-sweep.planes")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(program)
    try:
        r = subprocess.run([NODE, os.path.join(REPO, "js", "cli.mjs"), "run", path],
                           capture_output=True, text=True, cwd=REPO)
        return json.loads(r.stdout)["output"]
    finally:
        os.unlink(path)


def test_the_negative_refusal_is_the_same_in_python_and_javascript():
    if not _have_node():
        return
    path = os.path.join(REPO, ".ci-root-neg.planes")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("show text of (root of (0 - 4))\n")
    try:
        r = subprocess.run([NODE, os.path.join(REPO, "js", "cli.mjs"), "run", path],
                           capture_output=True, text=True, cwd=REPO)
        js = json.loads(r.stdout)
    finally:
        os.unlink(path)
    try:
        _run_py("root of (0 - 4)")
    except PlanesError as e:
        assert js["tag"] == e.tag
        assert e.detail in js["message"]
        assert e.fix in js["message"]
    else:
        raise AssertionError("python did not refuse")


# ---- the static surface -----------------------------------------------------


def _surface(src):
    import shapes
    path = os.path.join(REPO, ".ci-root-surface.planes")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src)
    try:
        return shapes.analyse_file(path)
    finally:
        os.unlink(path)


def test_the_surface_says_may_be_approximate_for_root_and_approximate_for_sine():
    """§6. The two sources do not mean the same thing, and a surface that
    flattened them would be less informative rather than more."""
    root_only = _surface(
        "to hyp of a, b:\n  give root of (a * a + b * b)\nshow text of (hyp of 3, 4)\n")
    assert root_only.produces_approximate()
    assert root_only.approximation_strength() == "sometimes"
    assert "may be approximate" in root_only.render()
    assert "`root`" in root_only.render()

    sine_only = _surface("show text of (sine of 30)\n")
    assert sine_only.approximation_strength() == "always"
    assert "numbers: approximate — this program reaches `sine`" in sine_only.render()
    assert "may be approximate" not in sine_only.render()


def test_reaching_both_reports_the_stronger_claim():
    """A single walk that stopped at whichever source it met first announced a
    `sine` program with `root`'s much weaker sentence. Each source is walked
    for separately, and `sine` wins."""
    both = _surface("show text of (root of 2)\nshow text of (sine of 30)\n")
    assert both.approximation_strength() == "always"
    assert "numbers: approximate — this program reaches `sine`" in both.render()
    routes = both.approximation_routes()
    assert any(r.endswith("root") for r in routes), routes
    assert any(r.endswith("sine") for r in routes), routes


def test_a_program_that_never_reaches_either_is_silent_about_numbers():
    plain = _surface("show text of (2 + 2)\n")
    assert not plain.produces_approximate()
    assert plain.approximation_strength() is None
    assert "approximate" not in plain.render()


def test_a_user_function_named_root_is_not_a_source_of_approximation():
    """The shadowing rule reaches the analyser too."""
    s = _surface("to root of x:\n  give x\nshow text of (root of 2)\n")
    assert not s.produces_approximate(), s.render()


# ---- the counts -------------------------------------------------------------


def test_one_builtin_and_nothing_else():
    with open(os.path.join(REPO, "grammar", "vocabulary.json"), encoding="utf-8") as fh:
        vocab = json.load(fh)
    names = [b["name"] for b in vocab["builtins"]]
    assert names.count("root") == 1
    assert len(names) == 13
    assert len(vocab["keywords"]) == 32, "no keyword was added"
    assert len(vocab["effect_kinds"]) == 7, "no effect kind was added"
    entry = next(b for b in vocab["builtins"] if b["name"] == "root")
    assert entry["arity"] == 1, "every builtin is unary"


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
