"""S7, Phases 2-4 — the canonical corpus, verified (A.3).

corpus/ holds programs written to be READ: each does something a person would
actually want done, and each teaches how Planes is written rather than merely
that a construct exists. This file is the mechanical half of the guarantee that
they are real programs and not fixtures — every corpus program must:

  A.3.1  run on both implementations, Python and JavaScript, to identical output
         in "inert" mode (a hermetic TestHost — writes go to memory, reads/asks
         are unstubbed and so fail deterministically or are served from an
         earlier same-run write; nothing touches the real world);
  A.3.2  round-trip — render, reparse, compare — byte-identically on both sides,
         and be in render's round-trip set (this file IS part of that set);
  A.3.3  have a computable, and mostly non-trivial, effect surface — a
         substantial share touch the world;
  A.3.4  tokenize and parse identically on the Planes-hosted stage
         (grammar/lexer.planes and grammar/parser.planes, on the JS host),
         agreeing with the reference; and
  A.5    carry its own explanation, in the language — every program uses note:
         or because:, the inert annotation planes, rather than external prose.

The count floor (A.4) is asserted in test_the_corpus_meets_its_floor.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

from host import TestHost
from interp import Interpreter, PlanesError
from lexer import (
    Because,
    Note,
    PlanesSyntaxError,
)
from modules import ModuleError
from parser import PlanesAmbiguity, parse
from render import ast_equal, render
from shapes import analyse

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))

# The count floor. Fifty is the specification's target; forty is the floor A.4
# permits when the last programs would be strained (ship forty, report the
# strain). ENFORCE_FLOOR is flipped to True in Phase 4, once the corpus is
# built — until then the batches are still growing and the count only reports.
FLOOR = 40
ENFORCE_FLOOR = True     # Phase 4: the corpus is built; the floor is enforced.

# Boundaries that count as "touching the world" — everything past the console.
WORLD = {"file", "network", "ambient"}


def _corpus():
    return sorted(glob.glob("corpus/**/*.planes", recursive=True))


def _uses_import(src):
    return any(ln.strip().startswith("use ") for ln in src.splitlines())


# ---------------------------------------------------------------- A.3.1 run agreement

def _py_run(path):
    """Run a corpus file under a hermetic TestHost — the inert mode. Returns
    (output, tag): the show lines and the terminal error tag (None on a clean
    completion, the fail tag when the program fails deterministically, e.g. an
    unstubbed `ask` guarded by `or fail`)."""
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
    return list(itp.output), tag


def _js_run(path):
    src = open(path, encoding="utf-8").read()
    cmd = "run-file" if _uses_import(src) else "run"
    r = subprocess.run([NODE, "js/cli.mjs", cmd, path],
                       cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed on {path}: {r.stderr}")
    d = json.loads(r.stdout)
    return d["output"], d["tag"]


def test_every_corpus_program_runs_identically_inert():
    """A.3.1. Python and JavaScript produce the same show output and the same
    terminal tag for every corpus program, run inert."""
    if NODE is None:
        return
    mism = []
    for f in _corpus():
        po, pt = _py_run(f)
        jo, jt = _js_run(f)
        if (po, pt) != (jo, jt):
            i = next((k for k in range(min(len(po), len(jo))) if po[k] != jo[k]),
                     None)
            detail = (f"first diff @ {i}: py={po[i]!r} js={jo[i]!r}"
                      if i is not None else "")
            mism.append(f"{f}: py=({pt},{len(po)}ln) js=({jt},{len(jo)}ln) {detail}")
    assert not mism, "run divergences:\n" + "\n".join(mism)


# ---------------------------------------------------------------- A.3.2 round-trip

def _js_render(path):
    r = subprocess.run([NODE, "js/cli.mjs", "render", path],
                       cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node render failed on {path}: {r.stderr}")
    return r.stdout


def _py_round_trips(path):
    src = open(path, encoding="utf-8").read()
    prog = parse(src)
    prog2 = parse(render(prog))       # raises if render's output won't reparse
    return len(prog) == len(prog2) and all(
        ast_equal(a, b) for a, b in zip(prog, prog2))


def test_every_corpus_program_round_trips_and_renders_identically():
    """A.3.2. render(program) reparses to the same AST (Python side), and the
    JavaScript renderer emits byte-identical text — so every corpus program is
    in render's round-trip set, both implementations. This is the set whose
    exclusion of the two largest programs let forty defects hide at #24; the
    corpus does not repeat that."""
    fails = []
    for f in _corpus():
        src = open(f, encoding="utf-8").read()
        try:
            if not _py_round_trips(f):
                fails.append(f"{f}: python round-trip AST mismatch")
        except PlanesSyntaxError:
            fails.append(f"{f}: render output did not reparse (python)")
            continue
        if NODE is not None:
            py_text = render(parse(src))
            if _js_render(f) != py_text:
                fails.append(f"{f}: JS render diverges from render.py")
    assert not fails, "round-trip failures:\n" + "\n".join(fails)


# ---------------------------------------------------------------- A.3.3 effect surface

def _surface(path):
    return analyse(open(path, encoding="utf-8").read())


def test_every_corpus_program_has_a_computable_surface():
    """A.3.3, first half. The static effect surface computes for every program;
    a corpus program whose surface cannot be derived is not a corpus program."""
    bad = []
    for f in _corpus():
        try:
            _surface(f)
        except Exception as e:  # noqa: BLE001
            bad.append(f"{f}: {type(e).__name__}: {e}")
    assert not bad, "surfaces that would not compute:\n" + "\n".join(bad)


def test_a_substantial_share_of_the_corpus_touches_the_world():
    """A.3.3, second half. A corpus of pure programs teaches nothing about the
    thing the language is for. A substantial share reach past the console — to a
    file, the network, or the ambient boundary."""
    files = _corpus()
    if not files:
        return
    touching = [f for f in files
                if WORLD & set(_surface(f).boundaries())]
    share = len(touching) / len(files)
    assert share >= 0.3, (
        f"only {len(touching)}/{len(files)} ({share:.0%}) touch the world; "
        f"a corpus of pure programs teaches nothing about effects")


# ---------------------------------------------------------------- A.3.4 Planes-hosted stage

def _meta(stage, files):
    r = subprocess.run([NODE, "js/cli.mjs", "meta", stage, *files],
                       cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node meta {stage} failed: {r.stderr[:400]}")
    return json.loads(r.stdout)


def test_the_planes_hosted_stage_tokenizes_and_parses_each_program():
    """A.3.4. grammar/lexer.planes and grammar/parser.planes — a Planes lexer
    and parser, written in Planes, running on the JavaScript host — process
    every corpus program and agree with the reference lexer.py / parser.py.
    (The whole-repo metacircular sweep in test_js_metacircular.py covers these
    too, now that corpus/ is in its glob; this pins the corpus specifically.)"""
    if NODE is None:
        return
    import lexer as pyl
    from test_parser_in_planes import canonical_program

    files = _corpus()
    lex = _meta("lex", files)
    parse_ = _meta("parse", files)
    fails = []
    for f, ltoks, past in zip(files, lex, parse_):
        want_toks = [[t.kind, t.value, t.line]
                     for t in pyl.tokenize(open(f, encoding="utf-8").read())]
        if ltoks != want_toks:
            fails.append(f"{f}: lexer.planes tokens differ from lexer.py")
        try:
            want_ast = canonical_program(parse(open(f, encoding="utf-8").read()))
        except (PlanesAmbiguity, PlanesSyntaxError):
            want_ast = None
        if isinstance(past, dict):     # parser.planes refused
            if want_ast is not None:
                fails.append(f"{f}: parser.planes refused, parser.py produced a form")
        elif past != want_ast:
            fails.append(f"{f}: parser.planes AST differs from parser.py")
    assert not fails, "Planes-hosted stage divergences:\n" + "\n".join(fails)


# ---------------------------------------------------------------- A.5 self-explanation

def _annotations(prog):
    """Every Because / Note anywhere in the program — the inert annotation
    planes, at any depth. A Note is a statement; a Because rides on an Assign or
    a Rule (its `annotation` field), which may sit inside a function body, an
    if-branch, or a loop, so this walks the whole tree."""
    import dataclasses
    found = []
    seen = set()

    def walk(node):
        if not (dataclasses.is_dataclass(node) and not isinstance(node, type)):
            return
        if id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, (Because, Note)):
            found.append(node)
        for f in dataclasses.fields(node):
            val = getattr(node, f.name)
            _walkval(val)

    def _walkval(val):
        if dataclasses.is_dataclass(val) and not isinstance(val, type):
            walk(val)
        elif isinstance(val, (list, tuple)):
            for item in val:
                _walkval(item)

    for stmt in prog:
        walk(stmt)
    return found


def test_every_corpus_program_carries_its_own_explanation():
    """A.5. Each program explains itself with the language's own annotation
    planes — a `because:` on a decision, or a standalone `note:` block — not an
    external README. A program that needs prose the language cannot hold is a
    finding (§5), reported; here we require the annotation to be present."""
    missing = []
    for f in _corpus():
        prog = parse(open(f, encoding="utf-8").read())
        if not _annotations(prog):
            missing.append(f)
    assert not missing, (
        "corpus programs with no note:/because: annotation:\n"
        + "\n".join(missing))


# ---------------------------------------------------------------- A.4 the floor

def test_the_corpus_meets_its_floor():
    """A.4. Fifty is the target; forty is the floor. The hard floor assertion is
    switched on in Phase 4 (the full verification sweep), once the corpus is
    built; during the batch build-up (Phases 2-3) the count only grows and this
    reports progress rather than failing a half-built corpus."""
    files = _corpus()
    n = len(files)
    print(f"    [corpus: {n} programs; floor {FLOOR}, target 50]")
    if ENFORCE_FLOOR:
        assert n >= FLOOR, f"corpus has {n} programs, below the floor of {FLOOR}"
    else:
        assert n >= 1, "corpus is empty"


if __name__ == "__main__":
    if NODE is None:
        print("  note  node not on PATH — JS-side checks will no-op")
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
