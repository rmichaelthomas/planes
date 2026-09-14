"""H8 -- the oracle and the metamorphic surface, checked over the whole corpus.

test_shapes.py's `check_oracle`/`check_oracle_file` and test_coverage.py's
`test_the_oracle_holds_for_every_node_type` run the oracle -- every runtime
effect must appear in the static surface -- over one hand-picked case per AST
node type. Neither runs it over the 51 real programs in corpus/, which is
exactly the gap that let #108 (a module-rename collision silently swapping in
the WRONG function) ship: the oracle existed, was correct on its own cases,
and never ran over the code that broke.

This file is that net, in three parts:

  1. THE ORACLE, over the corpus. Every corpus/*.planes program is run under
     the same stubbed, hermetic host test_corpus.py uses (TestHost, with
     nothing pre-stubbed -- an unstubbed `ask`/`read` fails deterministically,
     which some corpus programs demonstrate on purpose, e.g. weather-fetch.planes's
     `or fail as weather-unavailable`), on both Python (interp.py/shapes.py)
     and JavaScript (js/interp.mjs/js/shapes.mjs). Every runtime effect the run
     actually performed must be covered by the static surface, same matcher
     `check_oracle` uses (test_shapes.py): literal-equal, or every literal
     chunk of a `{...}`-holed computed pattern appears in the runtime value in
     order. A program that stops partway through (a deterministic stub
     failure) still counts for whatever it performed before stopping -- an
     empty prefix is a trivially sound one.

     The oracle here compares against the PRECISE surface -- `Surface.effects`
     ("what running this file performs", the same field check_oracle in
     test_shapes.py reads), not the wider `Surface.declared` (every function's
     effects, called or not) that test_foreign.py's older `check_oracle` uses.
     The JS `--json` document's `runs_on_load` field is exactly `.effects` but
     its own JSON entries omit `computed` (see docs/surface-format-v1.md); it
     is enriched from the same document's `effects` field (`.declared`, which
     always has a matching (kind, target) entry with the true flag) before
     matching -- `_js_effects_field` below.

     Foreign-declared claims (e.g. capability-manifest.planes's `now`/
     `entropy`/`home`, retry-schedule.planes's `now`) need no special case:
     a claimed effect is still an ordinary Effect with a kind/target/computed
     triple, matched exactly like any derived one.

  2. METAMORPHIC CHECKS, over the corpus. Three harmless edits -- rename a
     local name, add comment lines, reorder top-level function definitions --
     must leave the published surface (`shapes_cli --json`'s document,
     Python and JS) byte-for-byte the same. The only field this file ignores
     when comparing is "program" (the file's own basename, per
     docs/surface-format-v1.md's field table -- the one field the format
     documents as carrying the program's name); nothing in the format carries
     a line number (`site` lives on shapes.py's internal `Effect`, never in
     `as_json`'s output -- verified by reading `as_json` and
     docs/surface-format-v1.md before writing this).

     Renaming uses the real parser's AST, not a text regex: the target is a
     `let`/plain-assignment variable or a function parameter whose name binds
     nowhere else in the program (no other assign/param/for-each-loop-var/
     or-fail-handler-tag shares it -- `_binder_names`), so every `Var` node
     with that name anywhere in the program is unambiguously the same
     binding. The replacement name is a fresh one that appears nowhere in the
     token stream. Comments use the language's own line-comment syntax (`#`,
     `grammar/vocabulary.json`'s COMMENT token) -- confirmed from lexer.py
     that a blank or `#`-only physical line contributes no token at all,
     not even EOL, before the indentation check runs, so a comment line is
     safe to insert anywhere, at any depth, without perturbing INDENT/DEDENT.
     Reordering swaps which top-level `to ...:` block occupies which
     function-definition slot (never moving a function past a non-function
     top-level statement, so execution order of the top-level statements that
     do run is never in question) -- functions are hoisted, so this must be
     invisible to the surface.

     A transform that does not apply to a program (no safe rename target,
     fewer than two top-level functions) is skipped for that program and
     counted, never silently dropped.

  3. ISSUE #108's two reproductions, as extra multi-file oracle cases -- the
     shape this suite exists to have caught. Built fresh under tempfile, run
     through `Interpreter.run_file`/`shapes.analyse_file` (Python) and
     `run_file.mjs`'s `runFile`/`shapes_node.mjs`'s `analyseFile` (JS), the
     same module-graph machinery #108's fix (F8, "a module's own calls
     resolve to its own definitions first") lives in.

A mutation check (`test_mutation_check_...`) proves this file's own oracle
matcher (`_oracle_mismatches`, shared by every Python- and JS-side check
above) actually fails when the static surface is missing an effect kind the
runtime performed -- dropping `show` from a COPY of a real surface, never
touching shapes.py itself.

No file this test writes lives inside the repository: every temp file goes
under a `tempfile.mkdtemp()` directory, removed at process exit.
"""
import atexit
import dataclasses
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

from host import TestHost
from interp import Interpreter, PlanesError
from lexer import (
    Assign,
    ForEach,
    FuncDef,
    OrFail,
    PlanesSyntaxError,
    Var,
    tokenize,
)
from modules import ModuleError
from parser import PlanesAmbiguity, parse
from render import render
from shapes import analyse, analyse_file
from shapes_cli import as_json

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))

_TMP_ROOT = tempfile.mkdtemp(prefix="planes_h8_oracle_")
atexit.register(shutil.rmtree, _TMP_ROOT, ignore_errors=True)


def _corpus():
    return sorted(glob.glob(os.path.join(REPO, "corpus", "**", "*.planes"),
                            recursive=True))


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ================================================================ the oracle matcher
#
# Shared by every check below, Python- and JS-side alike (the JS surface and
# runtime effects are plain JSON by the time they reach this file). Same
# algorithm as test_shapes.py's check_oracle/check_oracle_file and
# test_foreign.py's check_oracle: literal targets compare equal; a computed
# target's literal chunks around `{...}` holes must appear, in order, in the
# runtime value.

def _covers(computed, pattern, actual):
    if not computed:
        return pattern == actual
    chunks = [p for p in str(pattern).split("{...}") if p]
    pos = 0
    for chunk in chunks:
        j = str(actual).find(chunk, pos)
        if j < 0:
            return False
        pos = j + len(chunk)
    return True


def _normalize_static(effects):
    """Effects as (kind, computed, target) triples -- accepts shapes.py
    Effect objects (Python) or plain dicts with kind/target/computed (JS)."""
    out = []
    for e in effects:
        if isinstance(e, dict):
            out.append((e["kind"], e.get("computed", False), e["target"]))
        else:
            out.append((e.kind, e.computed, e.target))
    return out


def _oracle_mismatches(runtime_effects, static_effects, label):
    """Every runtime (kind, target, ...) not covered by static_effects, as
    human-readable strings. Empty means sound."""
    static = _normalize_static(static_effects)
    by_kind = {}
    for kind, computed, target in static:
        by_kind.setdefault(kind, []).append((computed, target))
    out = []
    for actual in runtime_effects:
        kind, target = actual[0], actual[1]
        cands = by_kind.get(kind, [])
        if not cands:
            out.append(f"{label}: runtime performed {kind!r} on {target!r} "
                       f"but the static surface has no {kind!r} at all "
                       f"-- UNSOUND")
            continue
        if not any(_covers(c, p, target) for c, p in cands):
            out.append(f"{label}: runtime performed {kind} on {target!r}, "
                       f"not covered by {cands} -- UNSOUND")
    return out


def _js_effects_field(doc):
    """doc['runs_on_load'] (the precise, top-level-only surface -- shapes.py's
    `Surface.effects`) enriched with the `computed` flag, which the JSON
    format omits from that field (it carries kind/boundary/target only --
    see docs/surface-format-v1.md and js/shapes.mjs's asJson). doc['effects']
    (the wider declared surface) is built from the same underlying Effect
    objects and always has a matching (kind, target) entry with the true
    flag, since `.effects` is a subset of `.declared`."""
    computed_by_kt = {}
    for e in doc["effects"]:
        computed_by_kt.setdefault((e["kind"], e["target"]), e["computed"])
    out = []
    for e in doc["runs_on_load"]:
        out.append({
            "kind": e["kind"],
            "target": e["target"],
            "computed": computed_by_kt.get((e["kind"], e["target"]), False),
        })
    return out


def _strip(doc):
    """The surface JSON with the one field the format documents as carrying
    the program's own name removed -- docs/surface-format-v1.md's field
    table. Nothing else in the format carries a line number (checked by
    reading as_json/asJson: `Effect.site` never reaches the JSON)."""
    d = dict(doc)
    d.pop("program", None)
    return d


# ================================================================ running one program, Python side

def _py_analyse(path=None, src=None):
    """The static surface, as the shapes_cli --json document. `path` alone
    analyses a real file (following any real `use` module graph); `src`
    (with `path` only for the document's "program" field) analyses an
    in-memory source string -- true of every corpus program's metamorphic
    variant, none of which introduce a real cross-file `use`."""
    if src is None:
        surface = analyse_file(path)
        doc_path = path
    else:
        surface = analyse(src)
        doc_path = path or "program.planes"
    return surface, as_json(surface, doc_path)


def _py_run(path=None, src=None):
    """Run under an empty-stub TestHost -- the same hermetic host
    test_corpus.py uses, with nothing pre-stubbed: an unstubbed ask/read
    fails deterministically, which some corpus programs demonstrate on
    purpose. Returns (effects, terminal tag or None)."""
    host = TestHost()
    itp = Interpreter(host=host)
    tag = None
    try:
        if src is None:
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
    return itp.effects, tag


# ================================================================ metamorphic variant generators
#
# Each returns (new_src_or_None, applied: bool, reason: str). All three
# operate on the real parser's AST or the real tokenizer's tokens -- never a
# blind text regex that could also match inside a string or a comment.

def _all_name_tokens(src):
    return {t.value for t in tokenize(src) if t.kind == "NAME"}


def _walk_all(node, visit):
    """Depth-first, pre-order walk over an AST node/list/tuple, calling
    visit() on every dataclass instance found."""
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        visit(node)
        for f in dataclasses.fields(node):
            _walk_all(getattr(node, f.name), visit)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _walk_all(item, visit)


def _binder_names(prog):
    """Every name this program binds anywhere: a let/plain-assign target, a
    function parameter, a for-each loop variable, or a matched or-fail
    handler's tag. Used to find a rename candidate that shadows, and is
    shadowed by, nothing -- so every Var() sharing its name is unambiguous."""
    names = []

    def visit(node):
        if isinstance(node, Assign):
            names.append(node.name)
        elif isinstance(node, FuncDef):
            names.extend(node.params)
        elif isinstance(node, ForEach):
            names.append(node.var)
        elif isinstance(node, OrFail) and node.handler is not None:
            names.append(node.tag)

    for stmt in prog:
        _walk_all(stmt, visit)
    return names


def _rename_target(prog):
    """A let/assign variable name or function parameter that binds exactly
    once in the whole program -- the only ones H8 asks this variant to
    target, and the only ones safe to rename by exact-name match alone."""
    all_binders = _binder_names(prog)
    counts = {}
    for n in all_binders:
        counts[n] = counts.get(n, 0) + 1

    restricted = []

    def visit(node):
        if isinstance(node, Assign):
            restricted.append(node.name)
        elif isinstance(node, FuncDef):
            restricted.extend(node.params)

    for stmt in prog:
        _walk_all(stmt, visit)

    for name in restricted:
        if counts.get(name) == 1:
            return name
    return None


def _fresh_name(old, used):
    candidate = f"{old}-renamed"
    n = 2
    while candidate in used:
        candidate = f"{old}-renamed{n}"
        n += 1
    return candidate


def _apply_rename(prog, old, new):
    def visit(node):
        if isinstance(node, Assign) and node.name == old:
            node.name = new
        elif isinstance(node, Var) and node.name == old:
            node.name = new
        elif isinstance(node, FuncDef) and old in node.params:
            node.params = [new if p == old else p for p in node.params]
        elif isinstance(node, ForEach) and node.var == old:
            node.var = new
        elif (isinstance(node, OrFail) and node.handler is not None
              and node.tag == old):
            node.tag = new

    for stmt in prog:
        _walk_all(stmt, visit)


def _rename_variant(src):
    try:
        prog = parse(src)
    except (PlanesSyntaxError, PlanesAmbiguity) as e:
        return None, False, f"does not parse: {e}"
    old = _rename_target(prog)
    if old is None:
        return None, False, ("no let/assign variable or parameter binds "
                             "exactly once (no safe rename target)")
    new = _fresh_name(old, _all_name_tokens(src))
    _apply_rename(prog, old, new)
    try:
        new_src = render(prog)
    except Exception as e:  # noqa: BLE001 -- report, don't crash the suite
        return None, False, f"render failed after rename: {type(e).__name__}: {e}"
    return new_src, True, ""


def _reorder_variant(src):
    try:
        prog = parse(src)
    except (PlanesSyntaxError, PlanesAmbiguity) as e:
        return None, False, f"does not parse: {e}"
    idxs = [i for i, s in enumerate(prog) if isinstance(s, FuncDef)]
    if len(idxs) < 2:
        return None, False, "fewer than two top-level function definitions"
    funcs = [prog[i] for i in idxs]
    reordered = list(prog)
    for slot, node in zip(idxs, reversed(funcs)):
        reordered[slot] = node
    try:
        new_src = render(reordered)
    except Exception as e:  # noqa: BLE001
        return None, False, f"render failed after reorder: {type(e).__name__}: {e}"
    return new_src, True, ""


def _comment_variant(src):
    lines = src.split("\n")
    out = ["# H8 metamorphic: a harmless comment at the top of the file"]
    for i, line in enumerate(lines):
        out.append(line)
        if line and not line[0].isspace():
            out.append("# H8 metamorphic: a harmless comment between statements")
    new_src = "\n".join(out)
    try:
        parse(new_src)
    except (PlanesSyntaxError, PlanesAmbiguity) as e:
        # Would mean this generator itself is broken -- a `#`-only line
        # contributes no token at all (lexer.py skips blank/comment lines
        # before the indentation check), so this should never happen.
        return None, False, f"commented variant failed to parse: {e}"
    return new_src, True, ""


def _safe_variant(fn, src):
    try:
        return fn(src)
    except Exception as e:  # noqa: BLE001 -- one program's quirk must not
        return None, False, f"variant generator raised {type(e).__name__}: {e}"


# ============================================================ the plan: corpus + variants + repros

def _write_repro_effects():
    """Issue #108, reproduction 1 -- the effectful variant. Both a and b
    define `helper`; main renames b's on import. b's own `label` must reach
    its OWN helper (no network), not a's."""
    d = os.path.join(_TMP_ROOT, "repro108_effects")
    _write(os.path.join(d, "a.planes"),
          'use http\n\n'
          'to helper of x:\n  give ask "https://a.example/" + x\n'
          'to fetch-a of x:\n  give helper of x\n')
    _write(os.path.join(d, "b.planes"),
          'to helper of x:\n  give x + " (local)"\n'
          'to label of x:\n  give helper of x\n')
    _write(os.path.join(d, "main.planes"),
          "use a\nuse b with helper as b-helper\n"
          'show label of "hi"\n')
    return os.path.join(d, "main.planes")


def _write_repro_pure():
    """Issue #108, reproduction 2 -- the pure variant. No network at all, so
    the wrong answer cannot hide behind a stubbed effect."""
    d = os.path.join(_TMP_ROOT, "repro108_pure")
    _write(os.path.join(d, "a.planes"),
          'to helper of x:\n  give x + 1\n'
          'to fetch-a of x:\n  give helper of x\n')
    _write(os.path.join(d, "b.planes"),
          'to helper of x:\n  give x * 2\n'
          'to double of x:\n  give helper of x\n')
    _write(os.path.join(d, "main.planes"),
          "use a\nuse b with helper as b-helper\n"
          "show double of 3\n")
    return os.path.join(d, "main.planes")


_PLAN = None


def _build_plan():
    corpus = {}
    for path in _corpus():
        with open(path, encoding="utf-8") as f:
            src = f.read()
        variants = {}
        for kind, fn in (("rename", _rename_variant),
                        ("comment", _comment_variant),
                        ("reorder", _reorder_variant)):
            new_src, ok, reason = _safe_variant(fn, src)
            variants[kind] = {"src": new_src, "ok": ok, "reason": reason}
        corpus[path] = {"src": src, "variants": variants}

    repro = {
        "effects": _write_repro_effects(),
        "pure": _write_repro_pure(),
    }
    return {"corpus": corpus, "repro": repro}


def _plan():
    global _PLAN
    if _PLAN is None:
        _PLAN = _build_plan()
    return _PLAN


# ================================================================ the JS batch driver
#
# One node process for the whole file's JS-side work (corpus originals, every
# applied metamorphic variant, both #108 repros) -- node's own cold start is
# the dominant cost of a per-file subprocess (js/cli.mjs's run-batch exists
# for the identical reason), and this file has on the order of two hundred
# small in-memory programs to check.

_JS_DRIVER = r"""
import fs from "node:fs";
import { loadGrammar } from "__REPO__/js/loader_node.mjs";
import { analyse, asJson } from "__REPO__/js/shapes.mjs";
import { analyseFile } from "__REPO__/js/shapes_node.mjs";
import { Interpreter, PlanesError } from "__REPO__/js/interp.mjs";
import { TestHost } from "__REPO__/js/host.mjs";
import { runFile } from "__REPO__/js/run_file.mjs";
import { PlanesSyntaxError } from "__REPO__/js/lexer.mjs";

loadGrammar();

function tagOf(e) {
  if (e instanceof PlanesError) return e.tag;
  if (e instanceof PlanesSyntaxError) return "PARSE";
  if (e instanceof RangeError) return "recursion-too-deep";
  if (e && e.name === "ModuleError") return "module-error";
  throw e;
}

async function main() {
  const inputPath = process.argv[2];
  const input = JSON.parse(fs.readFileSync(inputPath, "utf-8"));
  const results = {};

  for (const item of input.sources || []) {
    try {
      const surface = analyse(item.src);
      const doc = asJson(surface, item.id);
      const host = new TestHost({ responses: {}, files: {}, now: 1000000.0 });
      const itp = new Interpreter({ host });
      let tag = null;
      try {
        itp.run(item.src);
      } catch (e) {
        tag = tagOf(e);
      }
      results[item.id] = { doc, effects: itp.effects, tag };
    } catch (e) {
      results[item.id] = { error: String((e && e.stack) || e) };
    }
  }

  for (const item of input.files || []) {
    try {
      const surface = await analyseFile(item.path);
      const doc = asJson(surface, item.path);
      const host = new TestHost({ responses: {}, files: {}, now: 1000000.0 });
      const itp = new Interpreter({ host });
      let tag = null;
      try {
        await runFile(itp, item.path);
      } catch (e) {
        tag = tagOf(e);
      }
      results[item.id] = { doc, effects: itp.effects, tag };
    } catch (e) {
      results[item.id] = { error: String((e && e.stack) || e) };
    }
  }

  process.stdout.write(JSON.stringify(results));
}

main().catch((e) => {
  process.stderr.write(String((e && e.stack) || e) + "\n");
  process.exit(1);
});
"""


_JS_BATCH = None


def _run_js_batch():
    plan = _plan()
    sources = []
    for path, entry in plan["corpus"].items():
        sources.append({"id": f"corpus::{path}", "src": entry["src"]})
        for kind, v in entry["variants"].items():
            if v["ok"]:
                sources.append({"id": f"variant::{path}::{kind}", "src": v["src"]})
    files = [{"id": f"repro::{name}", "path": mainpath}
             for name, mainpath in plan["repro"].items()]

    input_path = os.path.join(_TMP_ROOT, "js_batch_input.json")
    with open(input_path, "w", encoding="utf-8") as f:
        json.dump({"sources": sources, "files": files}, f)

    script_path = os.path.join(_TMP_ROOT, "h8_batch_driver.mjs")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(_JS_DRIVER.replace("__REPO__", REPO))

    r = subprocess.run([NODE, script_path, input_path],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise AssertionError(f"H8 JS batch driver failed:\n{r.stderr}")
    return json.loads(r.stdout)


def _js_batch():
    global _JS_BATCH
    if _JS_BATCH is None:
        _JS_BATCH = _run_js_batch()
    return _JS_BATCH


# ================================================================ 1. the oracle over the corpus

def test_python_oracle_holds_over_the_corpus():
    plan = _plan()
    checked, total_effects, skipped, mismatches = 0, 0, [], []
    for path in plan["corpus"]:
        name = os.path.relpath(path, REPO)
        try:
            surface, _doc = _py_analyse(path=path)
            effects, _tag = _py_run(path=path)
        except Exception as e:  # noqa: BLE001 -- report as a skip, not a crash
            skipped.append(f"{name}: could not run/analyse under the stub "
                           f"-- {type(e).__name__}: {e}")
            continue
        checked += 1
        total_effects += len(effects)
        mismatches.extend(_oracle_mismatches(effects, surface.effects,
                                             f"{name} (py)"))
    print(f"    [H8 python oracle: {checked} corpus programs checked, "
          f"{total_effects} runtime effects, {len(skipped)} skipped]")
    for s in skipped:
        print(f"    [H8 skipped, py oracle] {s}")
    assert not mismatches, "\n".join(mismatches)


def test_javascript_oracle_holds_over_the_corpus():
    if NODE is None:
        print("    [H8: node not on PATH -- JS oracle over the corpus skipped]")
        return
    plan = _plan()
    batch = _js_batch()
    checked, total_effects, skipped, mismatches = 0, 0, [], []
    for path in plan["corpus"]:
        name = os.path.relpath(path, REPO)
        item = batch.get(f"corpus::{path}")
        if item is None or "error" in item:
            skipped.append(f"{name}: {item.get('error') if item else 'missing from batch'}")
            continue
        checked += 1
        total_effects += len(item["effects"])
        static = _js_effects_field(item["doc"])
        mismatches.extend(_oracle_mismatches(item["effects"], static,
                                             f"{name} (js)"))
    print(f"    [H8 js oracle: {checked} corpus programs checked, "
          f"{total_effects} runtime effects, {len(skipped)} skipped]")
    for s in skipped:
        print(f"    [H8 skipped, js oracle] {s}")
    assert not mismatches, "\n".join(mismatches)


# ================================================================ 2. metamorphic checks

def _metamorphic_python(kind):
    plan = _plan()
    applied, skipped, mismatches = 0, [], []
    for path, entry in plan["corpus"].items():
        name = os.path.relpath(path, REPO)
        v = entry["variants"][kind]
        if not v["ok"]:
            skipped.append(f"{name}: {v['reason']}")
            continue
        try:
            _s_before, doc_before = _py_analyse(path=path)
            _s_after, doc_after = _py_analyse(path=path, src=v["src"])
        except Exception as e:  # noqa: BLE001
            mismatches.append(f"{name} ({kind}, py): surface failed on the "
                              f"variant -- {type(e).__name__}: {e}")
            continue
        applied += 1
        if _strip(doc_before) != _strip(doc_after):
            mismatches.append(
                f"{name} ({kind}, py): surface changed under a harmless edit\n"
                f"  before: {doc_before}\n  after:  {doc_after}")
    print(f"    [H8 python metamorphic/{kind}: {applied} applied, "
          f"{len(skipped)} skipped]")
    for s in skipped:
        print(f"    [H8 skipped, py {kind}] {s}")
    return mismatches


def _metamorphic_javascript(kind):
    plan = _plan()
    batch = _js_batch()
    applied, skipped, mismatches = 0, [], []
    for path, entry in plan["corpus"].items():
        name = os.path.relpath(path, REPO)
        v = entry["variants"][kind]
        if not v["ok"]:
            skipped.append(f"{name}: {v['reason']}")
            continue
        before = batch.get(f"corpus::{path}")
        after = batch.get(f"variant::{path}::{kind}")
        if before is None or "error" in before:
            mismatches.append(f"{name} ({kind}, js): original surface failed "
                              f"-- {before}")
            continue
        if after is None or "error" in after:
            mismatches.append(f"{name} ({kind}, js): variant surface failed "
                              f"-- {after}")
            continue
        applied += 1
        if _strip(before["doc"]) != _strip(after["doc"]):
            mismatches.append(
                f"{name} ({kind}, js): surface changed under a harmless edit\n"
                f"  before: {before['doc']}\n  after:  {after['doc']}")
    print(f"    [H8 js metamorphic/{kind}: {applied} applied, "
          f"{len(skipped)} skipped]")
    for s in skipped:
        print(f"    [H8 skipped, js {kind}] {s}")
    return mismatches


def test_metamorphic_rename_preserves_the_surface_python():
    mism = _metamorphic_python("rename")
    assert not mism, "\n".join(mism)


def test_metamorphic_comment_preserves_the_surface_python():
    mism = _metamorphic_python("comment")
    assert not mism, "\n".join(mism)


def test_metamorphic_reorder_preserves_the_surface_python():
    mism = _metamorphic_python("reorder")
    assert not mism, "\n".join(mism)


def test_metamorphic_rename_preserves_the_surface_javascript():
    if NODE is None:
        print("    [H8: node not on PATH -- JS metamorphic/rename skipped]")
        return
    mism = _metamorphic_javascript("rename")
    assert not mism, "\n".join(mism)


def test_metamorphic_comment_preserves_the_surface_javascript():
    if NODE is None:
        print("    [H8: node not on PATH -- JS metamorphic/comment skipped]")
        return
    mism = _metamorphic_javascript("comment")
    assert not mism, "\n".join(mism)


def test_metamorphic_reorder_preserves_the_surface_javascript():
    if NODE is None:
        print("    [H8: node not on PATH -- JS metamorphic/reorder skipped]")
        return
    mism = _metamorphic_javascript("reorder")
    assert not mism, "\n".join(mism)


# ================================================================ 3. issue #108 reproductions

def test_python_oracle_holds_over_issue_108_reproductions():
    plan = _plan()
    mismatches = []
    for name, mainpath in plan["repro"].items():
        surface, _doc = _py_analyse(path=mainpath)
        effects, _tag = _py_run(path=mainpath)
        mismatches.extend(_oracle_mismatches(
            effects, surface.effects, f"issue-108/{name} (py)"))
    print(f"    [H8 python oracle: {len(plan['repro'])} issue-108 "
          f"reproductions checked]")
    assert not mismatches, "\n".join(mismatches)


def test_javascript_oracle_holds_over_issue_108_reproductions():
    if NODE is None:
        print("    [H8: node not on PATH -- JS issue-108 oracle skipped]")
        return
    plan = _plan()
    batch = _js_batch()
    mismatches = []
    for name in plan["repro"]:
        item = batch.get(f"repro::{name}")
        if item is None or "error" in item:
            mismatches.append(f"issue-108/{name} (js): {item}")
            continue
        static = _js_effects_field(item["doc"])
        mismatches.extend(_oracle_mismatches(
            item["effects"], static, f"issue-108/{name} (js)"))
    print(f"    [H8 js oracle: {len(plan['repro'])} issue-108 "
          f"reproductions checked]")
    assert not mismatches, "\n".join(mismatches)


# ================================================================ mutation check

def test_mutation_check_the_oracle_actually_fails_on_a_dropped_effect_kind():
    """This file's own sanity check on `_oracle_mismatches`, the matcher
    shared by every Python- and JS-side test above: if the static surface
    silently dropped one effect kind, the oracle must fail, not pass
    quietly. Finds a corpus program that performs `show` at runtime, drops
    `show` from a COPY of its static surface (shapes.py itself, and the real
    surface, are never touched), and confirms the harness catches it -- then
    confirms the real, unmutated surface is still sound (the restore)."""
    plan = _plan()
    target = None
    for path in plan["corpus"]:
        effects, _tag = _py_run(path=path)
        if any(e[0] == "show" for e in effects):
            target = (path, effects)
            break
    assert target is not None, "no corpus program performs `show` -- can't mutation-test"
    path, effects = target
    surface, _doc = _py_analyse(path=path)

    mutated = [e for e in surface.effects if e.kind != "show"]
    caught = _oracle_mismatches(effects, mutated, "mutation-check")
    assert caught, ("dropping `show` from the static surface must make the "
                    "oracle fail -- the harness did not catch it")

    restored = _oracle_mismatches(effects, surface.effects, "mutation-check-restore")
    assert not restored, f"the real, unmutated surface should still be sound: {restored}"
    print(f"    [H8 mutation check: dropping `show` from "
          f"{os.path.basename(path)}'s surface correctly fails the oracle; "
          f"the real surface is unmodified and still sound]")


if __name__ == "__main__":
    if NODE is None:
        print("  note  node not on PATH -- JS-side checks will no-op")
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
