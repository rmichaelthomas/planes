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


# ---- `sine`, the eleventh builtin -------------------------------------------


def test_sine_at_the_quarter_turns():
    """0, 90, 180, 270, 360 — and three of them land EXACTLY on the right
    rational, because the fold reaches them without running the series at all."""
    from planes_num import sine_degrees
    assert sine_degrees(n(0)).text() == "0"
    assert sine_degrees(n(90)).text() == "1"
    assert sine_degrees(n(180)).text() == "0"
    assert sine_degrees(n(270)).text() == "-1"
    assert sine_degrees(n(360)).text() == "0"


def test_every_sine_result_is_approximate_including_the_exact_looking_ones():
    """`sine of 0` is 0 and is APPROXIMATE.

    The operation's true result being representable at one argument does not
    make the operation exact. This is deliberately the opposite of what square
    root will do — sqrt(4) is exactly 2 and sqrt(2) is not representable at
    all — and it is the cleanest illustration of why square root is the harder
    case: sine's answer is decided by the OPERATION, square root's by its
    ARGUMENT.
    """
    from planes_num import sine_degrees
    for d in (0, 30, 45, 90, 180, 270, 360, -30, 1000000):
        v = sine_degrees(n(d))
        assert not v.is_exact, f"sine of {d} came back exact"
        assert v.approx.op == "sine"
        assert "40 significant digits" in v.approx.detail
        assert "8-term" in v.approx.detail
        assert "50 working decimal places" in v.approx.detail
        assert "rounded to 30" in v.approx.detail


def test_sine_symmetry():
    from planes_num import sine_degrees
    for d in (0, 7, 30, 45, 60, 89, 90, 123, 179, 250, 359):
        assert sine_degrees(n(-d)) == -sine_degrees(n(d)), f"sine of -{d}"
        assert sine_degrees(n(180 - d)) == sine_degrees(n(d)), f"sine of (180 - {d})"


def test_argument_reduction_is_exact_at_any_magnitude():
    """§5.3's load-bearing property, and the one a float implementation cannot
    offer: reducing into [0, 360) is rational arithmetic, so it loses nothing.

    `math.sin(math.radians(360000030))` is 0.500000000133..., wrong in the
    tenth decimal place. This is the same value as `sine of 30`, bit for bit.
    """
    from planes_num import sine_degrees
    base = sine_degrees(n(30))
    for k in (1, 2, 1000, 1000000, -1, -1000):
        assert sine_degrees(n(30 + 360 * k)) == base, f"30 + 360*{k}"
    assert sine_degrees(n(360000030)) == base


def test_sine_matches_a_high_precision_reference_to_the_stated_accuracy():
    """The first omitted term of an 8-term series at pi/4 is 4.62e-17, so the
    answer is good to about sixteen decimal places. Checked against a
    50-digit series, not against a double."""
    from decimal import Decimal, getcontext

    from planes_num import sine_degrees
    getcontext().prec = 60
    pi = Decimal("3.14159265358979323846264338327950288419716939937510582097494")

    def reference(deg):
        x = Decimal(deg) * pi / 180
        t, s = x, x
        for k in range(1, 30):
            t = -t * x * x / ((2 * k) * (2 * k + 1))
            s += t
        return s

    worst = Decimal(0)
    for d in range(-180, 181, 7):
        got = sine_degrees(n(d))
        d_got = Decimal(got.q.numerator) / Decimal(got.q.denominator)
        worst = max(worst, abs(d_got - reference(d)))
    assert worst < Decimal("1e-16"), f"worst error {worst}"


def test_no_implementation_reaches_for_a_host_trigonometric_function():
    """Invariant 4. Every source AND test file, in both languages, plus the
    self-hosted interpreter: a `math.sin` borrowed "just for the tests" would
    make the agreement suite prove nothing.

    Comments are stripped first. Three checks in this repo have now been
    written that could not tell NAMING a forbidden thing from DOING it, and
    each one failed on a comment explaining why the thing is forbidden.
    """
    import glob
    import re

    def strip_comments(path, src):
        if path.endswith(".py"):
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    node.value = ""
            return ast.unparse(tree)
        if path.endswith((".mjs", ".js")):
            no_block = re.sub(r"/\*[\s\S]*?\*/", "", src)
            return re.sub(r"(^|[^:])//[^\n]*", r"\1", no_block)
        if path.endswith(".planes"):
            return "\n".join(ln.split("#")[0] for ln in src.splitlines())
        return src

    import ast

    # RENDERER-SIDE, NOT LANGUAGE-SIDE. These four are the drawing runtime, and
    # the drawing protocol puts transcendental arithmetic deliberately on the
    # renderer's side of the line: a program emits `draw rotate 30` and the
    # renderer computes the rotation; a program emits an OKLCH hue in degrees
    # and `color.mjs` converts it. None of them touches a Planes value, and
    # none of them is an implementation of `sine`. Named one by one rather
    # than matched by a pattern, so a fifth file cannot join them quietly.
    GEOMETRY_ONLY = {
        "color.mjs",                    # OKLCH hue (degrees) -> OKLab a/b
        "svg.mjs",                      # arc endpoints from the swept angle
        "paint_conformance.test.mjs",   # the same endpoints, asserted
        "paint_svg.test.mjs",
        "protocol_v2.test.mjs",         # v2 §9.2: rotated ellipse/rect corners,
                                         # hand-computed the same way to check against
    }
    offenders = []
    roots = (glob.glob(os.path.join(REPO, "*.py"))
             + glob.glob(os.path.join(REPO, "js", "*.mjs"))
             + glob.glob(os.path.join(REPO, "js", "paint", "*.mjs"))
             + glob.glob(os.path.join(REPO, "js", "test", "*.mjs"))
             + glob.glob(os.path.join(REPO, "grammar", "*.planes"))
             + glob.glob(os.path.join(REPO, "paint", "*.planes"))
             + glob.glob(os.path.join(REPO, "scripts", "*.py")))
    scanned = 0
    for path in roots:
        base = os.path.basename(path)
        if base in GEOMETRY_ONLY:
            continue
        with open(path, encoding="utf-8") as f:
            src = f.read()
        code = strip_comments(path, src)
        scanned += 1
        for pattern in ("math.sin", "Math.sin", "math.cos", "Math.cos",
                        "math.tan", "Math.tan", "math.radians"):
            if pattern in code:
                offenders.append(f"{os.path.relpath(path, REPO)}: {pattern}")
    assert scanned > 80, f"only {scanned} files scanned — the glob is not reaching them"
    assert not offenders, "host trigonometry reached for:\n  " + "\n  ".join(offenders)


def test_a_sine_result_carries_a_bounded_denominator():
    """§5.4: left unbounded, one `sine` hands the rest of a program a fraction
    whose denominator grows through every operation after it."""
    from planes_num import RESULT_PLACES, sine_degrees
    for d in (30, 45, 60, 123, 359):
        v = sine_degrees(n(d))
        assert v.q.denominator <= 10 ** RESULT_PLACES, (d, v.q.denominator)


def test_sine_refuses_a_non_number():
    from host import TestHost
    from interp import Interpreter, PlanesError
    i = Interpreter(host=TestHost())
    try:
        i.run('v = sine of "thirty"\n')
    except PlanesError as e:
        assert e.tag == "not-a-number", e.tag
        assert "degrees" in str(e), str(e)
        return
    raise AssertionError("sine of text was accepted")


# ---- `why` names where each side stopped being exact ------------------------


def _why(src):
    from host import TestHost
    from interp import Interpreter
    i = Interpreter(host=TestHost())
    i.run(src)
    return i.output


def test_why_on_an_approximate_comparison_names_the_entry_point():
    """The whole reason the no-tolerance rule is defensible.

    `sine of 30` is not `1/2` — it is 0.4999999999999999999530..., and `==`
    says so plainly, with no epsilon. What makes that honest rather than
    surprising is the next line: `why` names where the left side stopped being
    exact and with what parameters, so a reader can see that the difference is
    the fifth of a trillionth of a trillionth the series stops at, and decide
    for themselves whether they wanted a tolerance — rather than being handed
    one nobody chose.
    """
    out = _why("a = sine of 30\nhalf = 1 / 2\nnear = a == half\nwhy near\n")
    assert out[0].startswith("false from a (0.499999999999999999953058170618) == half (0.5)")
    assert "approximate — sine:" in out[0]
    assert "40 significant digits" in out[0]
    assert "8-term Taylor series" in out[0]


def test_why_names_the_entry_once_when_both_sides_entered_the_same_way():
    """`sine of 30` and `sine of 150` ARE equal, and `==` says so.

    Both entered through the same operation with the same parameters, so there
    is one entry point to name, not two. The dedup is by CONTENT — the
    operation and its parameters — and not by object identity, which is a trap
    `why_tree` fell into once before (S8's named finding: identity dedup is
    unreproducible in a value language).
    """
    out = _why("a = sine of 30\nb = sine of 150\nsame = a == b\nwhy same\n")
    assert out[0].startswith("true from")
    assert out[0].count("approximate — sine:") == 1, out[0]


def test_why_says_nothing_about_approximation_when_there_is_none():
    out = _why("a = 1 / 3\nb = a * 3\nwhy b\n")
    assert "approximate" not in out[0], out[0]


def test_both_implementations_render_the_same_why():
    if NODE is None:
        return
    src = "a = sine of 30\nhalf = 1 / 2\nnear = a == half\nwhy near\n"
    mine = _why(src)
    import json
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".planes", delete=False) as f:
        f.write(src)
        path = f.name
    try:
        r = subprocess.run([NODE, "js/cli.mjs", "run", path],
                           capture_output=True, text=True, cwd=REPO)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["output"] == mine
    finally:
        os.unlink(path)


# ---- the seams this build was not allowed to move ---------------------------


def test_sine_is_unary_and_the_builtin_count_moved_by_exactly_one():
    import json
    with open(os.path.join(REPO, "grammar", "vocabulary.json"), encoding="utf-8") as f:
        vocab = json.load(f)
    names = [b["name"] for b in vocab["builtins"]]
    # 12 now (A-Q19 added `number`) — this asserts sine's own seam (unary,
    # present exactly once, no keyword or effect kind added alongside it),
    # not that the count is frozen at what sine itself left it at.
    assert len(names) == 12, names
    assert names.count("sine") == 1
    entry = next(b for b in vocab["builtins"] if b["name"] == "sine")
    assert entry["arity"] == 1, "the unary-builtin invariant holds"
    assert all(b["arity"] == 1 for b in vocab["builtins"]), "every builtin is unary"
    assert len(vocab["keywords"]) == 32, "no keyword was added"
    assert len(vocab["effect_kinds"]) == 7, "no effect kind was added"


def test_the_foreign_route_was_not_the_delivery_mechanism():
    """`sharedTargets` is untouched, and no host gained a trigonometric target.

    §251's portability argument for making this a builtin rather than a
    `foreign` was that a foreign target names a host path and so forks a
    shared library. That argument is FALSE — `js/host.mjs` exports
    `sharedTargets()`, a host-independent table mapping Python-canonical names
    onto each host's implementation, and `time.time` and `builtins.sorted`
    already cross it. The CATEGORY argument stands and is what this build
    rests on: `foreign` is for effect boundaries, and `sine` reaches nothing.
    So the check is not that the route was unavailable — it is that it was not
    taken.
    """
    for rel in ("js/host.mjs", "host.py"):
        with open(os.path.join(REPO, rel), encoding="utf-8") as f:
            src = f.read()
        for target in ("math.sin", "math.cos", "math.tan"):
            assert target not in src, f"{rel} gained a {target} target"


# ---- the static surface answers it without running anything -----------------


def _surface(path):
    from shapes import analyse_file
    return analyse_file(os.path.join(REPO, path), follow=True)


def test_the_surface_says_bloom_produces_approximate_values_without_running_it():
    """Checkpoint §232's third question — a computed fact about a program —
    answered for numerics, and with a witness anyone can look at."""
    s = _surface("paint/bloom.planes")
    assert s.produces_approximate()
    routes = s.approximation_routes()
    assert "(top level)  ->  wave  ->  cosine  ->  sine" in routes, routes
    assert "numbers: approximate" in s.render()
    assert "wave  ->  cosine  ->  sine" in s.render()


def test_the_surface_says_turtle_and_snake_do_not():
    for name in ("turtle", "snake"):
        s = _surface(f"paint/{name}.planes")
        assert not s.produces_approximate(), (name, s.approximation_routes())
        assert "approximate" not in s.render(), name


def test_importing_a_module_that_can_approximate_is_not_producing_one():
    """snake `use`s math, which now declares `cosine` and `tangent`. It calls
    neither, and it produces no approximate values.

    This is where approximation and effects part company, deliberately. An
    effect is AUTHORITY — a library that re-exports a clock makes its consumer
    impure whether or not the consumer calls it. Approximation is PRODUCTION.
    Reporting it the other way would flag every program that touches the maths
    module for anything at all, and the fact would be worth nothing.
    """
    snake = _surface("paint/snake.planes")
    assert "math" in snake.modules
    assert not snake.produces_approximate()
    # and the library, asked on its own, says yes
    lib = _surface("paint/math.planes")
    assert lib.produces_approximate()
    assert lib.approximation_routes() == ["cosine  ->  sine", "tangent  ->  sine"]


def test_a_user_function_named_sine_shadows_the_builtin_and_the_fact():
    from shapes import analyse
    s = analyse("to sine of x:\n  give x * 2\nshow text of (sine of 3)\n")
    assert not s.produces_approximate(), s.approximation_routes()


def test_the_route_is_the_shortest_one_and_crosses_files():
    from shapes import analyse
    s = analyse("to a of x:\n  give b of x\nto b of x:\n  give sine of x\n"
                "to direct of x:\n  give sine of x\nshow text of (a of 1)\n")
    assert s.approximation_routes()[0] == "(top level)  ->  a  ->  b  ->  sine"
    assert "direct  ->  sine" in s.approximation_routes()


def test_both_analysers_agree_on_the_approximation_routes():
    """The port has to see the same call graph, or the fact is only true where
    it happens to be asked."""
    import json
    if NODE is None:
        return
    for name in ("turtle", "bloom", "snake", "math", "draw"):
        path = os.path.join("paint", f"{name}.planes")
        mine = _surface(path)
        r = subprocess.run([NODE, "js/cli.mjs", "shapes", path],
                           capture_output=True, text=True, cwd=REPO)
        assert r.returncode == 0, r.stderr
        theirs = json.loads(r.stdout)
        assert theirs.get("approximate", []) == [list(p) for p in mine.approximate], (
            name, theirs.get("approximate"), mine.approximate)


# ---- the three implementations agree on the property ------------------------

# One battery, three implementations, same answers. Each entry is
# (expression, expected-text, expected-exact).
BATTERY = [
    ("1 + 2", "3", True),
    ("sine of 0", "0", False),
    ("sine of 30", "0.499999999999999999953058170618", False),
    ("sine of 90", "1", False),
    ("sine of 360000030", "0.499999999999999999953058170618", False),
    ("(sine of 30) + 1", "1.499999999999999999953058170618", False),
    ("round (sine of 30) to 4 places", "0.5", False),
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


def _port_src(src):
    r = subprocess.run([NODE, "js/cli.mjs", "exactness", src],
                       capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stderr
    import json
    d = json.loads(r.stdout)
    return d["text"], d["exact"]


def _port(expr):
    return _port_src(f"let v = {expr}\nshow text of v\n")


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


SINE_INPUTS = (
    list(range(-180, 181, 3))                       # negatives, zero, quadrants
    + [0, 90, 180, 270, 360, 45, 135, 225, 315]     # the fold's boundaries
    + [360000030, -360000030, 1000000, 123456789]   # large magnitudes
    + ["0.5", "1.25", "89.999", "0.001", "44.9", "45.1"]   # fractional degrees
)


def test_all_three_implementations_agree_bit_for_bit_on_sine():
    """Over 100 inputs, one rendered string each, three implementations.

    Not "agree to twelve digits" — the same digits. Three implementations
    doing integer arithmetic with one rounding rule cannot drift the way three
    readings of "reduce a fraction" can, and this is what asserts it.
    """
    from host import TestHost
    from interp import Interpreter
    assert len(SINE_INPUTS) > 100, len(SINE_INPUTS)

    reference = {}
    for d in SINE_INPUTS:
        src = f"v = sine of ({d})\nshow text of v\n"
        i = Interpreter(host=TestHost())
        i.run(src)
        reference[str(d)] = i.output[0]

    if NODE is not None:
        for d in SINE_INPUTS:
            src = f"v = sine of ({d})\nshow text of v\n"
            got, exact = _port_src(src)
            assert got == reference[str(d)], f"port sine of {d}: {got} vs {reference[str(d)]}"
            assert exact is False, f"port sine of {d} came back exact"

    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import run_corpus_selfhosted as sh
    for d in SINE_INPUTS:
        src = f"v = sine of ({d})\nshow text of v\n"
        out, tag = sh.planes_run(src, {})
        assert tag is None, f"self-hosted sine of {d} failed: {tag}"
        assert out[0] == reference[str(d)], (
            f"self-hosted sine of {d}: {out[0]} vs {reference[str(d)]}")


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
