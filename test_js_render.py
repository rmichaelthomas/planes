"""S5, Phase 3 — the JS canonical renderer, checked against render.py.

js/render.mjs is a port of render.py. render.py's output is already canonical
text, so this compares it byte for byte across the corpus (A.3/A.4). And it
gets render.py's own treatment (A.4): every AST node kind has a real case, no
safe fallback, a round-trip per kind on the JS side, PLUS cross-implementation
round-trips both directions — render with one, reparse with the other, which
catches divergence a same-side round-trip cannot.

render.py is the specification, and the port reproduces it exactly.

S6 UPDATE: the render round-trip limitation this suite documented in S5 — a
multi-argument call used as a record-field value that render could not reparse —
is FIXED (test_render_composition.py), along with three sibling defects it turned
out to be one of. render now round-trips the WHOLE corpus, grammar/interp.planes
and grammar/parser.planes included, on both implementations. The S5
`test_js_reproduces_render_py_roundtrip_limitation_on_interp` test is replaced
below by its opposite: both files now round-trip on both sides.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

from parser import PlanesSyntaxError, parse
from render import ast_equal, render

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))

# demo/app/net.planes needs the cross-file `known` table run_file() supplies —
# it does not parse standalone (test_render.py excludes it too).
NOT_STANDALONE_PARSEABLE = {"demo/app/net.planes"}


def _run(args):
    r = subprocess.run([NODE, "js/cli.mjs", *args], cwd=REPO,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node {args} failed: {r.stderr}")
    return r.stdout


def _js_render(path):
    return _run(["render", path])


def _js_roundtrip(path):
    return json.loads(_run(["roundtrip", path]))


def _js_astequal(a, b):
    return json.loads(_run(["astequal", a, b]))


def _all_planes():
    paths = sorted(glob.glob("*.planes")) + \
        sorted(glob.glob("demo/**/*.planes", recursive=True)) + \
        sorted(glob.glob("grammar/*.planes"))
    return [p for p in paths if p not in NOT_STANDALONE_PARSEABLE]


def _standalone_files():
    out = []
    for p in _all_planes():
        try:
            parse(open(p, encoding="utf-8").read())
            out.append(p)
        except PlanesSyntaxError:
            pass
    return out


def _py_round_trips(path):
    """render.py's actual guarantee: parse -> render -> reparse -> ast_equal."""
    src = open(path, encoding="utf-8").read()
    prog = parse(src)
    try:
        prog2 = parse(render(prog))
    except PlanesSyntaxError:
        return False
    return len(prog) == len(prog2) and all(
        ast_equal(a, b) for a, b in zip(prog, prog2))


# ================================================================ byte-for-byte corpus

def test_render_is_byte_identical_across_the_corpus():
    """render.py's output is canonical text — compare it byte for byte. Includes
    grammar/interp.planes, which render.py cannot round-trip: the render output
    still matches exactly, which is the point of a byte-for-byte oracle."""
    files = _standalone_files()
    assert len(files) >= 30, len(files)
    mismatches = [p for p in files if _js_render(p) != render(
        parse(open(p, encoding="utf-8").read()))]
    assert not mismatches, "render divergences:\n" + "\n".join(mismatches)


def test_the_deepest_nested_program_renders_identically():
    """pypi.planes — to -> for each -> for each where, or-fail wrapping both a
    call and a write — the indentation-sensitive worst case."""
    py = render(parse(open("pypi.planes", encoding="utf-8").read()))
    assert _js_render("pypi.planes") == py


# ============================================ exhaustive per-node-kind round-trip (A.4)

NODE_KIND_SNIPPETS = {
    "Num": "x = 42\n",
    "Str": 'x = "hi"\n',
    "Bool": "x = true\n",
    "Nothing": "x = nothing\n",
    "Var": "y = x\n",
    "ListLit": "x = [1, 2, 3]\n",
    "RecordLit": "x = { a: 1, b: 2 }\n",
    "RecordUpdate": "y = p with a: 1, b: 2\n",
    "ListPlus": "y = xs plus 1\n",
    "BinOp": "x = 1 + 2\n",
    "Not": "x = not true\n",
    "IsNothing": "x = y is nothing\n",
    "Field": "x = r.a.b\n",
    "Assign": "x = 1\n",
    "Because": 'x = 1 because "reason"\n',
    "Why": "why x\n",
    "Use": "use file\n",
    "FuncDef": "to f of n:\n  give n\n",
    "Call": "y = f of 1\n",
    "Give": "to f:\n  give 1\n",
    "Show": 'show "hi"\n',
    "ForEach": "y = for each p in xs where p > 0: p\n",
    "If": "if x:\n  show 1\nelse:\n  show 2\n",
    "When": "when r is { a: 1, b }:\n  show b\nelse:\n  show 0\n",
    "OrFail": "y = f of 1 or fail as e\n",
    "Fail": 'fail "boom" as oops\n',
    "Foreign": 'foreign sort of xs from "builtins.sorted" doing ask xs\n',
    "WriteTo": 'write [1] to "f.json"\n',
    "Round": "y = round x to 2 places\n",
    "Rule": 'rule [r] anything may not ask to "u" because "reason"\n',
    "Note": 'note:\n  from "src"\n  derives-from [rule-x]\n',
}


def _all_ast_kinds():
    import dataclasses
    import inspect

    import lexer
    return {
        n for n, o in vars(lexer).items()
        if inspect.isclass(o) and dataclasses.is_dataclass(o)
        and o.__module__ == "lexer" and n != "Token"}


def test_every_ast_node_kind_round_trips_on_the_js_side():
    """A real case per kind, JS parse -> render -> reparse -> astEqual, with no
    safe fallback. Coverage spans every AST node kind Python's lexer defines."""
    covered = set()
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.planes")
        for kind, src in NODE_KIND_SNIPPETS.items():
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(src)
            r = _js_roundtrip(p)
            assert r["ok"], f"{kind}: JS round-trip failed for:\n{src}"
            assert kind in r["kinds"], (
                f"{kind}: snippet did not produce it (got {r['kinds']})")
            covered |= set(r["kinds"])
    covered.add("Builtin")  # dead node; the JS unit test covers its raise
    missing = _all_ast_kinds() - covered
    assert not missing, f"AST node kinds with no JS round-trip: {sorted(missing)}"


# ================================================ same-side round-trip matches render.py

def test_js_round_trip_matches_render_py_everywhere():
    """The JS renderer round-trips exactly where render.py does — and fails
    exactly where render.py fails (grammar/interp.planes). Reproducing the
    limitation is faithfulness, not a bug to fix (A.6)."""
    mismatches = []
    for p in _standalone_files():
        py_ok = _py_round_trips(p)
        js_ok = _js_roundtrip(p)["ok"]
        if py_ok != js_ok:
            mismatches.append(f"{p}: py_round_trips={py_ok} js_round_trips={js_ok}")
    assert not mismatches, "round-trip disagreements:\n" + "\n".join(mismatches)


# ================================================ cross-implementation round-trips (A.4)

def test_cross_impl_python_render_js_reparse():
    """Python renders, JS reparses, and the JS AST equals JS's parse of the
    original — over every file render.py guarantees a round-trip for."""
    files = [p for p in _standalone_files() if _py_round_trips(p)]
    assert len(files) >= 25, len(files)
    with tempfile.TemporaryDirectory() as d:
        rp = os.path.join(d, "r.planes")
        failures = []
        for path in files:
            pr = render(parse(open(path, encoding="utf-8").read()))
            with open(rp, "w", encoding="utf-8") as fh:
                fh.write(pr)
            res = _js_astequal(rp, path)
            if not res["equal"]:
                failures.append(f"{path}: {res}")
        assert not failures, "python-render/js-reparse divergences:\n" + \
            "\n".join(failures)


def test_cross_impl_js_render_python_reparse():
    """JS renders, Python reparses, and the Python AST equals Python's parse of
    the original."""
    files = [p for p in _standalone_files() if _py_round_trips(p)]
    failures = []
    for path in files:
        jr = _js_render(path)
        orig = parse(open(path, encoding="utf-8").read())
        reparsed = parse(jr)
        if len(orig) != len(reparsed) or not all(
                ast_equal(a, b) for a, b in zip(orig, reparsed)):
            failures.append(path)
    assert not failures, "js-render/python-reparse divergences:\n" + \
        "\n".join(failures)


# ================================ the S5 limitation, now fixed on both sides (S6)

def test_the_two_grammar_files_now_round_trip_on_both_implementations():
    """FLIPPED from S5's `test_js_reproduces_render_py_roundtrip_limitation_on_interp`.
    grammar/interp.planes and grammar/parser.planes exercised four render
    round-trip defects (a greedy comma tail, the `first` operator, a field on a
    call result, and a dropped or-fail handler). All are fixed in S6, so both
    files render byte-identically between the two implementations AND round-trip
    on each side — the opposite of the S5 assertion."""
    for f in ("grammar/interp.planes", "grammar/parser.planes"):
        py = render(parse(open(f, encoding="utf-8").read()))
        assert _js_render(f) == py, f"{f}: render must be byte-identical"
        parse(py)  # render.py now reparses its own output (would raise otherwise)
        assert _js_roundtrip(f)["ok"] is True, f"{f}: JS round-trip must hold"


# ================================================================ escapes round-trip

ESCAPE_SRCS = [
    r'x = "a\"b"' + "\n",
    r'x = "a\\b"' + "\n",
    r'x = "a\nb"' + "\n",
    r'x = "a\tb"' + "\n",
    'x = 1 because "a\\"b"\n',
    'rule [r] anything may not write to "a\\"b"\n',
]


def test_escaped_strings_round_trip_on_both_sides():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "e.planes")
        for src in ESCAPE_SRCS:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(src)
            assert _js_roundtrip(p)["ok"], f"JS round-trip failed:\n{src}"
            py = render(parse(src))
            assert _js_render(p) == py, f"render diverged:\n{src}"
            assert all(ast_equal(a, b) for a, b in zip(parse(src), parse(py)))


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
