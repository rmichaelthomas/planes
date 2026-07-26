"""S4, Phase 7 — the metacircular conformance test (A.1).

The strongest conformance test in this repo's history: grammar/lexer.planes,
grammar/parser.planes, and grammar/interp.planes — a Planes implementation
written in Planes — run ON the JavaScript implementation (js/interp.mjs), and
that stack processes the corpus, checked against the Python implementation
(lexer.py / parser.py / interp.py). Any divergence anywhere in the three layers
shows up here.

The result, stated plainly (A.1, §7): it finds nothing. Every stage agrees. The
one non-agreement in the interp stage is the known interp.planes limitation — it
has no dynamic host.resolve (the second host's single non-effect method), so
foreign.planes refuses where interp.py runs it; js/interp.mjs itself runs
foreign.planes (test_js_interp.py). And the depth-blocked program runs on the
deeper JS stack where the CPython metacircular stack could not.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

import lexer as pyl
from host import TestHost
from interp import Interpreter, PlanesError
from lexer import PlanesSyntaxError
from parser import PlanesAmbiguity, parse
from test_parser_in_planes import canonical_program

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))
FOREIGN_REFUSALS = {"foreign-needs-host", "foreign-not-found"}


def _all_files():
    return sorted(f for f in glob.glob("**/*.planes", recursive=True) if ".venv" not in f)


def _standalone():
    return [f for f in _all_files()
            if not any(ln.strip().startswith("use ")
                       for ln in open(f, encoding="utf-8").read().splitlines())]


def _meta(stage, files):
    r = subprocess.run([NODE, "js/cli.mjs", "meta", stage, *files],
                       cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node meta {stage} failed: {r.stderr[:400]}")
    return json.loads(r.stdout)


# ============================================= the lexer stage (lexer.planes on JS)

def test_the_planes_lexer_on_js_tokenizes_the_whole_corpus_like_lexer_py():
    files = _all_files()
    results = _meta("lex", files)
    mism = []
    for f, m in zip(files, results):
        want = [[t.kind, t.value, t.line] for t in pyl.tokenize(open(f, encoding="utf-8").read())]
        if m != want:
            mism.append(f)
    assert not mism, f"metacircular lexer divergences: {mism}"


# ============================================= the parser stage (parser.planes on JS)

def test_the_planes_parser_on_js_parses_the_corpus_like_parser_py():
    files = _standalone()
    results = _meta("parse", files)
    real = []
    for f, m in zip(files, results):
        py_form = None
        py_refused = False
        try:
            py_form = canonical_program(parse(open(f, encoding="utf-8").read()))
        except (PlanesAmbiguity, PlanesSyntaxError):
            py_refused = True
        if isinstance(m, dict):                     # parser.planes refused (amber / parse error)
            if not py_refused:
                real.append(f"{f}: js refused ({m}), py produced a form")
        elif m != py_form:
            real.append(f"{f}: canonical AST differs")
    assert not real, "metacircular parser divergences:\n" + "\n".join(real)


# ============================================= the interp stage (interp.planes on JS)

def _py_run(f):
    itp = Interpreter(host=TestHost())
    tag = None
    try:
        itp.run(open(f, encoding="utf-8").read())
    except PlanesError as e:
        tag = e.tag
    except (PlanesAmbiguity, PlanesSyntaxError):
        tag = "PARSE"
    return list(itp.output), tag


def test_the_planes_interpreter_on_js_runs_the_corpus_like_interp_py():
    files = _standalone()
    results = _meta("run", files)
    real, host_resolve_gap = [], []
    for f, m in zip(files, results):
        py_out, py_tag = _py_run(f)
        if isinstance(m, dict) and "error" in m:
            if m["error"] in ("ambiguity", "parse-error"):
                continue                            # a parse refusal both sides make
            if m["error"] == "foreign-needs-host":
                host_resolve_gap.append(f)          # the known interp.planes gap
                continue
            real.append(f"{f}: js errored {m['error']}, py=({py_tag})")
        else:
            mt = m.get("tag")
            if m.get("output") == py_out and mt == py_tag:
                continue
            if (mt in FOREIGN_REFUSALS and py_tag in FOREIGN_REFUSALS
                    and m.get("output") == py_out):
                continue                            # both refuse an unloadable foreign
            if mt == "foreign-needs-host" and py_tag is None:
                host_resolve_gap.append(f)
                continue
            real.append(f"{f}: js=({mt}) py=({py_tag})")
    assert not real, "metacircular interp divergences:\n" + "\n".join(real)
    # The only non-agreement is foreign.planes — interp.planes has no dynamic
    # host.resolve; js/interp.mjs runs it (test_js_interp.py). Named, not hidden.
    assert host_resolve_gap == ["foreign.planes"], host_resolve_gap


def test_the_depth_blocked_program_runs_on_the_metacircular_js_stack():
    """probe/parser/cursor_scales.planes hit interpreted-recursion-32 on the
    CPython metacircular stack (interp.planes-on-interp.py). On the deeper JS
    stack it runs through the full three layers, matching interp.py's direct
    run — the depth win A.6 predicts."""
    f = "probe/parser/cursor_scales.planes"
    (m,) = _meta("run", [f])
    assert "error" not in m, f"expected a clean metacircular run, got {m}"
    py_out, py_tag = _py_run(f)
    assert m["output"] == py_out and m["tag"] == py_tag


if __name__ == "__main__":
    if NODE is None:
        print("  SKIP  node not on PATH")
        sys.exit(0)
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
