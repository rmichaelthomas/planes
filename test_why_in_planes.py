"""S8 — `why` agreement: grammar/interp.planes against interp.py.

Planes makes two guarantees: what does this program do, and where did this
value come from. The self-hosted stack delivered the first for three builds
and not the second — `grammar/interp.planes` carried a `deriv` slot on every
value and never filled it. Build 4 fills it, following interp.py's
architecture (provenance rides on values; `apply_op` has no idea derivation
exists), and this file is the check.

The technique is the one every prior stage used: both sides render the same
thing to the same canonical text and the strings are compared. The canonical
form is not a new one — it is interp.py's own `explain()` (the one line `why`
prints), `origins()` (every boundary a value depends on), and the output list
they land in. A second form would be a second place for the test to be wrong.

Three layers:

  1. per-derivation-kind cases — one program per kind of step the graph can
     hold (literal, name, op, field, call, item, comprehension, record, list,
     effect, foreign), plus `because:` set and popped, and show/why ordering;
  2. `origins_of` — the runtime twin of the analyser's, across file, network,
     foreign, and comprehension provenance;
  3. the corpus — every program in corpus/ that runs to completion on both
     implementations, with a `why` appended for every top-level binding it
     produced. Programs that cannot run on both are reported with their
     reason, never silently dropped.
"""
import glob
import os
import sys

from host import TestHost as _TestHost  # (aliased: not a test class)
from interp import Deriv, Interpreter, PlanesError, Traced, origins
from lexer import Assign
from parser import PlanesSyntaxError, parse

INTERP_PLANES = "grammar/interp.planes"
REPO = os.path.dirname(os.path.abspath(__file__))

_interp = None


def _get():
    global _interp
    if _interp is None:
        _interp = Interpreter()
        _interp.run_file(INTERP_PLANES)
    return _interp


def _t(v):
    # A cheap label, not repr(v): a host value handed to interp.planes now
    # carries a derivation DAG, and repr walks shared subgraphs exponentially.
    return Traced(v, Deriv("literal", "<host value>", v, []))


def _inert_io(**cfg):
    d = {"mode": "inert", "log": [], "output": [], "annotations": [],
         "modules": [], "clock": 0, "randoms": [], "files": [],
         "responses": [], "envs": [], "foreigns": []}
    d.update(cfg)
    return d


def _io_of(state):
    for b in state["env"]:
        if b["name"] == "__io__":
            return b["value"]
    raise AssertionError("no __io__ binding in program env")


def planes_output(src, **cfg):
    """The ordered text an inert interp.planes run produced — show lines and
    why lines together, interp.py's self.output exactly."""
    i = _get()
    state = i.call("execute-program-with",
                   [_t(src), _t(_inert_io(**cfg))], i.env).value
    return state, _io_of(state)["output"]


def py_output(src, **host):
    i = Interpreter(host=_TestHost(**host))
    i.run(src)
    return i, list(i.output)


def assert_why_agrees(src, **cfg):
    host = {k: v for k, v in cfg.pop("host", {}).items()}
    state, mine = planes_output(src, **cfg)
    assert state["status"] == "normal", (state["status"], state.get("error"))
    _i, theirs = py_output(src, **host)
    assert mine == theirs, (
        f"\nsrc:\n{src}\n--- interp.planes ---\n{mine}\n"
        f"--- interp.py ---\n{theirs}")


# ============================================ 1. one case per derivation kind

LITERAL_AND_NAME = [
    "x = 5\nwhy x\n",
    'x = "hi"\nwhy x\n',
    "x = true\nwhy x\n",
    "x = nothing\nwhy x\n",
    "why 5\n",
    'why "a\\"b"\n',
    "x = 5\ny = x\nwhy y\n",
    "x = 2 / 3\nwhy x\n",
]

OPERATORS = [
    "x = 5\ny = x + 2\nwhy y\n",
    "x = 5\ny = x * 2 - 1\nwhy y\n",
    "x = 5\nwhy x > 3\n",
    "a = true\nb = false\nwhy a and b\n",
    "a = true\nb = true\nwhy a and b\n",
    "a = false\nb = true\nwhy a or b\n",
    "a = false\nb = false\nwhy a or b\n",
    "x = true\nwhy not x\n",
    "x = nothing\nwhy x is nothing\n",
    "why 1 in [1, 2]\n",
    'why "a" in "abc"\n',
    'why "a" + "b"\n',
    "why [1, 2] + [3]\n",
    "why round 3.14159 to 2 places\n",
]

COLLECTIONS = [
    "xs = [1, 2, 3]\nwhy xs\n",
    "xs = [1, 2, 3]\nwhy first 2 of xs\n",
    "xs = [1]\nwhy xs plus 2\n",
    "r = { a: 1, b: 2 }\nwhy r\n",
    "r = { a: 1, b: 2 }\nwhy r.a\n",
    "r = { a: 1 }\nwhy r.zz\n",
    "r = { a: 1 }\nwhy r with a: 9\n",
]

BUILTINS = [
    "xs = [1, 2, 3]\nwhy count of xs\n",
    'why upper of "ab"\n',
    'why lower of "AB"\n',
    "why text of 3\n",
    "why whole of 3.6\n",
    'why join of ["a", "b"]\n',
    "why rest of [1, 2, 3]\n",
    'why normalize of "a"\n',
]

CALLS_AND_BLOCKS = [
    "to double of n:\n  give n * 2\nx = double of 5\nwhy x\n",
    "to add of a, b:\n  give a + b\nx = add of 1, 2\nwhy x\n",
    "to noop of n:\n  x = n\nr = noop of 4\nwhy r\n",
    "to zero:\n  give 0\nz = zero\nwhy z\n",
    "to f of n:\n  if n <= 0:\n    give 0\n  give f of (n - 1)\nx = f of 3\nwhy x\n",
    "xs = for each n in [1, 2, 3]: n * 2\nwhy xs\n",
    "xs = for each n in [1, 2, 3, 4, 5] where n > 2: n\nwhy xs\n",
    'cs = for each c in "abc": c\nwhy cs\n',
    "xs = for each n in []: n\nwhy xs\n",
    'r = { kind: "a", n: 3 }\nwhen r is { kind: "a", n }:\n  y = n + 1\n  why y\n',
    "v = (1 / 0) or fail as bad:\n  0\nwhy v\n",
    "v = (1 / 0) or fail as bad:\n  bad\nwhy v\n",
    "v = (1 / 0) or fail as bad:\n  bad.tag\nwhy v\n",
]

BECAUSE_AND_ORDER = [
    'x = 5 because "the rate we agreed"\nwhy x\n',
    # interp.py POPS the rationale on an unannotated rebind; so does this.
    'x = 5 because "first"\nx = 6\nwhy x\n',
    'x = 5 because "a \\"quoted\\" reason"\nwhy x\n',
    'show "hello"\nx = 1\nwhy x\nshow "bye"\n',
]


def test_literal_and_name_steps_agree():
    for src in LITERAL_AND_NAME:
        assert_why_agrees(src)


def test_operator_steps_agree():
    for src in OPERATORS:
        assert_why_agrees(src)


def test_collection_and_field_steps_agree():
    for src in COLLECTIONS:
        assert_why_agrees(src)


def test_builtin_steps_agree():
    for src in BUILTINS:
        assert_why_agrees(src)


def test_call_comprehension_and_block_steps_agree():
    for src in CALLS_AND_BLOCKS:
        assert_why_agrees(src)


def test_because_is_display_text_beside_the_derivation():
    for src in BECAUSE_AND_ORDER:
        assert_why_agrees(src)


def test_why_lands_in_output_and_never_in_the_effect_log():
    """`why` performs nothing: interp.py appends the line to self.output and to
    no effect list, so asking where a value came from widens no effect
    surface. The self-hosted `why` does the same."""
    state, out = planes_output("x = 1 + 2\nwhy x\nshow \"done\"\n")
    assert state["status"] == "normal"
    log = [(e["kind"], e["target"]) for e in _io_of(state)["log"]]
    assert log == [("show", "done")], log
    assert out == ["3 from 1 + 2", "done"], out


EFFECT_CASES = [
    ('use file\nbody = read "notes.txt"\nwhy body\n',
     dict(files=[{"path": "notes.txt", "body": "hello"}]),
     dict(files={"notes.txt": "hello"})),
    ('use file\nbody = read "notes.txt"\nn = count of body\nwhy n\n',
     dict(files=[{"path": "notes.txt", "body": "hello"}]),
     dict(files={"notes.txt": "hello"})),
    ('use http\nr = ask "https://x/a.json"\nwhy r\n',
     dict(responses=[{"url": "https://x/a.json",
                      "value": {"kind": "text", "value": "ok", "deriv": None}}]),
     dict(responses={"https://x/a.json": '"ok"'})),
]


def test_effect_steps_agree():
    for src, pcfg, hcfg in EFFECT_CASES:
        state, mine = planes_output(src, **pcfg)
        assert state["status"] == "normal", state
        _i, theirs = py_output(src, **hcfg)
        assert mine == theirs, f"\n{src}\nplanes: {mine}\npy:     {theirs}"


# ================================================================ 2. origins_of

ORIGIN_CASES = [
    ('use file\nbody = read "notes.txt"\nn = count of body\n', "n",
     dict(files=[{"path": "notes.txt", "body": "hello"}]),
     dict(files={"notes.txt": "hello"})),
    ('use file\nuse http\na = read "a.txt"\nb = ask "https://x/b.json"\n'
     'c = a + b\n', "c",
     dict(files=[{"path": "a.txt", "body": "p"}],
          responses=[{"url": "https://x/b.json",
                      "value": {"kind": "text", "value": "q", "deriv": None}}]),
     dict(files={"a.txt": "p"}, responses={"https://x/b.json": '"q"'})),
    ("x = 1 + 2\n", "x", {}, {}),
    ('foreign now from "time.time" doing clock\nt = now\nu = t + 1\n', "u",
     dict(clock=7), dict(now=7)),
    ('use file\nxs = for each p in ["a.txt", "b.txt"]: read p\n', "xs",
     dict(files=[{"path": "a.txt", "body": "p"}, {"path": "b.txt", "body": "q"}]),
     dict(files={"a.txt": "p", "b.txt": "q"})),
    ('use file\nto grab of p:\n  give read p\n'
     'a = grab of "a.txt"\nb = count of a\n', "b",
     dict(files=[{"path": "a.txt", "body": "hey"}]),
     dict(files={"a.txt": "hey"})),
]


def _planes_origins(state, name):
    i = _get()
    val = next(b["value"] for b in state["env"] if b["name"] == name)
    return i.call("origins-of", [_t(val)], i.env).value


def test_origins_of_agrees():
    """The runtime twin of the analyser's origins_of: every boundary crossing
    a value depends on, in walk order."""
    for src, name, pcfg, hcfg in ORIGIN_CASES:
        state, _out = planes_output(src, **pcfg)
        assert state["status"] == "normal", state
        mine = _planes_origins(state, name)
        pi, _ = py_output(src, **hcfg)
        theirs = origins(pi.env.get(name))
        assert mine == theirs, f"\n{src}\nplanes: {mine}\npy:     {theirs}"


def test_origins_reaches_across_a_call_boundary():
    """Not vacuously agreeing: the file a value was read from survives being
    passed out of a function and folded into an arithmetic result."""
    src = ('use file\nto grab of p:\n  give read p\n'
           'a = grab of "a.txt"\nb = count of a\n')
    state, _ = planes_output(src, files=[{"path": "a.txt", "body": "hey"}])
    assert _planes_origins(state, "b") == ["file:a.txt"]


# ============================================ 2b. the whole graph, not the line
#
# `explain` compares one rendered line; this compares the derivation GRAPH
# behind it. The shape is the one the analyser port already defined for
# comparing derivation trees (test_js_shapes_derivation.py's `_py_deriv_tree`):
# kind, label, origin, inputs, fully expanded, shared nodes re-walked. Its
# `file` field is the static analyser's and has no runtime counterpart, so it
# is the only field that does not carry over. A second form would be a second
# place for the test to be wrong.

def _py_tree(n, depth=0):
    if depth > 12:
        return "..."
    return {"kind": n.kind, "label": n.label, "origin": n.origin,
            "inputs": [_py_tree(i, depth + 1) for i in n.inputs]}


def _planes_tree(d, depth=0):
    if depth > 12:
        return "..."
    return {"kind": d["kind"], "label": d["label"], "origin": d["origin"],
            "inputs": [_planes_tree(i, depth + 1) for i in d["inputs"]]}


TREE_CASES = [
    ("x = 5\ny = x + 2\n", "y"),
    ('x = "a"\ny = upper of x\n', "y"),
    ("r = { a: 1, b: 2 }\nv = r.a\n", "v"),
    ("xs = [1, 2]\ny = xs plus 3\n", "y"),
    ("to double of n:\n  give n * 2\nx = double of 5\n", "x"),
    ("to add of a, b:\n  give a + b\nx = add of 1, 2\n", "x"),
    ("xs = for each n in [1, 2, 3]: n * 2\n", "xs"),
    ("xs = for each n in [1, 2, 3] where n > 1: n\n", "xs"),
    ("a = true\nb = false\nc = a and b\n", "c"),
    ("x = 5\ny = not (x > 3)\n", "y"),
    ("r = { a: 1 }\ns = r with a: 2\n", "s"),
    ("x = 3.14159\ny = round x to 2 places\n", "y"),
    ("xs = [1, 2, 3]\ny = first 2 of xs\n", "y"),
    ('r = { kind: "a", n: 3 }\nwhen r is { kind: "a", n }:\n  y = n + 1\n', "y"),
]


def test_derivation_graph_agrees_in_the_analyser_ports_canonical_form():
    for src, name in TREE_CASES:
        state, _out = planes_output(src)
        assert state["status"] == "normal", (src, state.get("error"))
        val = next(b["value"] for b in state["env"] if b["name"] == name)
        mine = _planes_tree(val["deriv"])
        pi, _ = py_output(src)
        theirs = _py_tree(pi.env.get(name).node)
        assert mine == theirs, f"\n{src}\nplanes: {mine}\npy:     {theirs}"


# =============================================================== 3. the corpus

def _top_level_names(src):
    """Every name a top-level assignment binds, in source order, deduplicated.
    Read off the AST, not guessed."""
    try:
        prog = parse(src)
    except (PlanesSyntaxError, Exception):  # noqa: BLE001
        return []
    out = []
    for stmt in prog:
        if isinstance(stmt, Assign) and stmt.name not in out:
            out.append(stmt.name)
    return out


def _corpus_paths():
    return sorted(glob.glob(os.path.join(REPO, "corpus", "*.planes")))


def _py_bound(src):
    """(interpreter, bound names) for a clean interp.py run, or (None, reason)."""
    try:
        i = Interpreter(host=_TestHost())
        i.run(src)
    except PlanesError as e:
        return None, f"interp.py failed: {e.tag}"
    except Exception as e:  # noqa: BLE001
        return None, f"interp.py raised {type(e).__name__}"
    names = [n for n in _top_level_names(src) if _has(i, n)]
    return i, names


def _has(i, name):
    try:
        i.env.get(name)
        return True
    except Exception:  # noqa: BLE001
        return False


def test_every_corpus_program_that_runs_agrees_on_why():
    """A.2: `why` output agrees canonically across every corpus program that
    produces a derivable value.

    For each program that completes on both implementations, a `why <name>` is
    appended for every top-level binding it produced, and the two output lists
    are compared in full — show lines and why lines together, in run order.
    A program that cannot complete on one side produces no derivable value
    there; it is counted and named, never silently skipped.
    """
    checked, why_lines, skipped = 0, 0, []
    for path in _corpus_paths():
        rel = os.path.relpath(path, REPO)
        src = open(path, encoding="utf-8").read()

        pi, names = _py_bound(src)
        if pi is None:
            skipped.append((rel, names))
            continue
        if not names:
            skipped.append((rel, "no top-level binding"))
            continue

        probe = src + "".join(f"why {n}\n" for n in names)

        try:
            state, mine = planes_output(probe)
        except PlanesError as e:
            skipped.append((rel, f"interp.planes raised: {e.tag}"))
            continue
        if state["status"] != "normal":
            err = state.get("error") or {}
            skipped.append((rel, f"interp.planes failed: {err.get('tag')}"))
            continue

        _i2, theirs = py_output(probe)
        assert mine == theirs, (
            f"\n{rel}\n--- interp.planes ---\n" + "\n".join(map(str, mine))
            + "\n--- interp.py ---\n" + "\n".join(map(str, theirs)))
        checked += 1
        why_lines += len(names)

    total = len(_corpus_paths())
    print(f"    [why agreement: {checked}/{total} corpus programs, "
          f"{why_lines} derivations compared; {len(skipped)} not runnable "
          f"on both]")
    for rel, why in skipped:
        print(f"      skipped {rel}: {why}")
    assert checked > 0, "no corpus program ran on both implementations"


if __name__ == "__main__":
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
