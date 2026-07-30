"""S4, Phase 5 — the JS interpreter, checked against interp.py.

js/interp.mjs is a port of interp.py (js/modules.mjs + js/run_file.mjs port the
import resolution). This runs every corpus program with both implementations and
compares the canonical output — the show output, the terminal error tag, the
effect log, and any files written — the shape run_corpus_through_planes.py uses,
extended with effects and files so the whole host boundary is checked. Per A.6,
host.resolve works and foreign.planes runs; the seven effect kinds agree through
a hermetic TestHost on both sides.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

from host import TestHost
from interp import Interpreter, PlanesError, render
from lexer import PlanesSyntaxError
from modules import ModuleError

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))


def _uses_import(src):
    return any(ln.strip().startswith("use ") for ln in src.splitlines())


def _py_run(path, cfg=None):
    """Run a file with interp.py under a hermetic TestHost. Returns
    (output, tag, effects, files) — run_file for a program with imports,
    run otherwise, matching how the JS CLI dispatches."""
    cfg = cfg or {}
    host = TestHost(responses=cfg.get("responses", {}),
                    files=dict(cfg.get("files", {})),
                    now=cfg.get("now", 1_000_000.0))
    itp = Interpreter(host=host)
    src = open(path, encoding="utf-8").read()
    tag = None
    try:
        if _uses_import(src):
            itp.run_file(path)
        else:
            itp.run(src)
    except PlanesError as e:
        tag = e.tag
    except ModuleError:
        tag = "module-error"
    except RecursionError:
        tag = "recursion-too-deep"
    except PlanesSyntaxError:
        tag = "PARSE"
    return (list(itp.output), tag, [list(t) for t in itp.effects],
            dict(getattr(host, "files", {})))


def _js_run(path, cfg=None):
    src = open(path, encoding="utf-8").read()
    cmd = "run-file" if _uses_import(src) else "run"
    args = [NODE, "js/cli.mjs", cmd, path]
    if cfg is not None:
        args.append(json.dumps(cfg))
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed on {path}: {r.stderr}")
    d = json.loads(r.stdout)
    return d["output"], d["tag"], d["effects"], d["files"]


def _run_src(src, cfg=None):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "p.planes")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(src)
        py = _py_run(p, cfg)
        js = _js_run(p, cfg)
        return py, js


# ================================================================ full-corpus run agreement

def test_every_corpus_program_runs_to_identical_output_and_tag():
    files = sorted(
        f for f in glob.glob("**/*.planes", recursive=True) if ".venv" not in f)
    assert len(files) >= 40, len(files)
    mismatches = []
    for f in files:
        po, pt, _, _ = _py_run(f)
        jo, jt, _, _ = _js_run(f)
        if (po, pt) != (jo, jt):
            i = next((k for k in range(min(len(po), len(jo))) if po[k] != jo[k]), None)
            detail = f"first out diff @ {i}: py={po[i]!r} js={jo[i]!r}" if i is not None else ""
            mismatches.append(f"{f}: py=({pt},{len(po)}ln) js=({jt},{len(jo)}ln) {detail}")
    assert not mismatches, "run divergences:\n" + "\n".join(mismatches)


# ================================================================ the seven effect kinds

SEVEN = (
    "use file\nuse http\n"
    'foreign now from "time.time" doing clock\n'
    'foreign roll from "random.random" doing random\n'
    'foreign home from "os.getcwd" doing env\n'
    'show "hi"\n'
    'write [1, 2] to "out.json"\n'
    'r = ask "https://api/data.json"\n'
    'c = read "in.json"\n'
    "t = now\nx = roll\nh = home\n"
    'show "n=" + text of r.n\n'
    'show "read=" + c\n'
)
SEVEN_CFG = {"responses": {"https://api/data.json": '{"n": 7}'},
             "files": {"in.json": "file contents"}}


def test_the_seven_effect_kinds_agree_on_log_output_and_files():
    (po, pt, pe, pf), (jo, jt, je, jf) = _run_src(SEVEN, SEVEN_CFG)
    assert pt == jt is None
    assert pe == je, f"effect log:\n py={pe}\n js={je}"   # clock/random values differ, log does not
    assert po == jo, f"output:\n py={po}\n js={jo}"
    assert pf == jf, f"files:\n py={pf}\n js={jf}"


def test_write_produces_a_byte_identical_json_file():
    src = 'use file\nwrite {a: 1, b: [2, 3], c: "x"} to "o.json"\n'
    (_, _, _, pf), (_, _, _, jf) = _run_src(src)
    assert pf == jf and pf["o.json"], pf


def test_ask_parses_json_and_reads_deliver_stubbed_data_identically():
    src = ('use http\nuse file\n'
           'r = ask "https://x/y.json"\n'
           'show text of r.count\n'
           'c = read "note.txt"\nshow c\n')
    cfg = {"responses": {"https://x/y.json": '{"count": 42}'},
           "files": {"note.txt": "hello"}}
    (po, pt, _, _), (jo, jt, _, _) = _run_src(src, cfg)
    assert (po, pt) == (jo, jt)
    assert po == ["42", "hello"], po


# ================================================= A.6: host.resolve and the foreign program

def test_the_foreign_resolution_program_runs_identically():
    """A.6: host.resolve must work and foreign.planes must run — sorted/max/min
    resolve, the ask effects log, and `why` all agree with interp.py."""
    po, pt, pe, _ = _py_run("foreign.planes")
    jo, jt, je, _ = _js_run("foreign.planes")
    assert pt is None and jt is None
    assert po == jo, f"py={po}\njs={jo}"
    assert pe == je, f"py={pe}\njs={je}"
    assert po[-1] == "37 from top (41) - low (4)"       # the `why spread` line


def test_the_depth_program_runs_directly_on_both():
    """probe/parser/cursor_scales.planes was blocked in the self-hosted stack
    (interpreted recursion 32), not when run directly. Both interp.py and
    js/interp.mjs run it directly, identically."""
    po, pt, _, _ = _py_run("probe/parser/cursor_scales.planes")
    jo, jt, _, _ = _js_run("probe/parser/cursor_scales.planes")
    assert pt is None and jt is None
    assert po == jo


# ================================================================ why, and error tags

def test_why_output_agrees():
    cases = [
        "x = 5\ny = 3\nz = x + y\nwhy z\n",
        'name = "ada"\ngreeting = "hi " + name\nwhy greeting\n',
        "xs = [1, 2, 3]\nn = count of xs\nwhy n\n",
    ]
    for src in cases:
        (po, pt, _, _), (jo, jt, _, _) = _run_src(src)
        assert (po, pt) == (jo, jt), f"src:\n{src}\n py={po}\n js={jo}"


def test_error_tags_and_details_agree():
    cases = [
        ("z = 5 + \"x\"\n", "cannot-combine"),
        ("z = 1 / 0\n", "divided-by-zero"),
        ('z = 5 == "5"\n', "cannot-compare"),
        ("r = read \"x\"\n", "module-not-used"),
        ("xs = []\ny = rest of xs\n", "empty-list"),
        ("z = 5\nw = z.field\n", "not-a-record"),
        ('fail "boom" as my-tag\n', "my-tag"),
        ("z = missing of 1\n", "unknown-function"),
        ("z = count of 1, 2\n", "wrong-arity"),
    ]
    for src, want_tag in cases:
        (po, pt, _, _), (jo, jt, _, _) = _run_src(src)
        assert pt == jt, f"src:\n{src}\n py_tag={pt} js_tag={jt}"
        if want_tag is not None:
            assert pt == want_tag, f"src:\n{src}\n expected {want_tag}, got {pt}"
        assert po == jo, f"src:\n{src}\n py_out={po} js_out={jo}"


# ================================================================ the show/why trace


def _py_trace(path):
    """The canonical trace form: one `<source line>\t<rendered derivation>`
    per emitted output line. The renderer is `why`'s own, so this compares the
    real thing rather than a second description of it."""
    host = TestHost()
    itp = Interpreter(host=host)
    src = open(path, encoding="utf-8").read()
    tag = None
    try:
        if _uses_import(src):
            itp.run_file(path)
        else:
            itp.run(src)
    except PlanesError as e:
        tag = e.tag
    except ModuleError:
        tag = "module-error"
    except RecursionError:
        tag = "recursion-too-deep"
    except PlanesSyntaxError:
        tag = "PARSE"
    return {"tag": tag, "outputCount": len(itp.output),
            "trace": [f"{line}\t{render(node)}" for node, line in itp.trace]}


def _js_trace(path):
    r = subprocess.run([NODE, "js/cli.mjs", "trace", path],
                       cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed on {path}: {r.stderr}")
    return json.loads(r.stdout)


def test_the_trace_is_exactly_as_long_as_the_output_for_every_corpus_program():
    """Gate D. `output` and `trace` are the same list length by construction —
    every append to one is an append to the other — so a consumer indexing one
    with the other's index is never off by the number of `why`s that ran."""
    files = sorted(
        f for f in glob.glob("**/*.planes", recursive=True) if ".venv" not in f)
    assert len(files) >= 40, len(files)
    for f in files:
        d = _py_trace(f)
        assert len(d["trace"]) == d["outputCount"], \
            f"{f}: {len(d['trace'])} trace entries for {d['outputCount']} output lines"


def test_the_python_and_javascript_traces_agree_in_canonical_form():
    """Gate E. Not just the same length — the same derivations, rendered the
    same way, naming the same source lines."""
    files = sorted(
        f for f in glob.glob("**/*.planes", recursive=True) if ".venv" not in f)
    mismatches = []
    for f in files:
        py = _py_trace(f)
        js = _js_trace(f)
        if py != js:
            i = next((k for k in range(min(len(py["trace"]), len(js["trace"])))
                      if py["trace"][k] != js["trace"][k]), None)
            detail = (f"first diff @ {i}: py={py['trace'][i]!r} js={js['trace'][i]!r}"
                      if i is not None else
                      f"py={len(py['trace'])} entries js={len(js['trace'])}")
            mismatches.append(f"{f}: {detail}")
    assert not mismatches, "trace divergences:\n" + "\n".join(mismatches)


def test_a_show_inside_an_imported_helper_reports_the_line_that_called_it():
    """The trace names a line in the file the CALLER handed over. Without
    this a page showing garden.planes highlights line 45 of draw.planes,
    which is a file the reader is not looking at."""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "helper.planes"), "w", encoding="utf-8") as fh:
            fh.write("to announce of x:\n  show \"value \" + text of x\n")
        entry = os.path.join(d, "entry.planes")
        with open(entry, "w", encoding="utf-8") as fh:
            fh.write("use helper\n\nannounce of 7\nshow \"direct\"\n")
        py = _py_trace(entry)
        js = _js_trace(entry)
        assert py == js
        lines = [t.split("\t")[0] for t in py["trace"]]
        # `announce of 7` is on line 3 of the entry file; the `show` inside
        # the helper is on line 2 of the helper, and is not what is reported.
        assert lines == ["3", "4"], lines


def test_the_trace_adds_no_effect_of_its_own():
    """`why` performs nothing (test_why_in_planes.py pins that for the
    language) and neither does keeping a derivation beside each output line:
    the effect log is byte-identical either way."""
    src = 'let a = 2\nshow text of a\nwhy a\nshow "done"\n'
    (po, pt, pe, pf), (jo, jt, je, jf) = _run_src(src)
    assert pe == je == [["show", "2"], ["show", "done"]]
    assert len(po) == 3  # the `why` line is output, not effect


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
