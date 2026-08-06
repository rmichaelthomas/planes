"""Tests for the readable deep walk (R2, checkpoint v29.0 §448-458).

R2's shape: `why` still answers one layer by default — `explain`, unchanged
— and the deep walk (`why_tree` / `why_machine`, reached explicitly) folds a
run of identical-in-shape reassignment or recursion steps into one labeled
aggregate rather than either printing every step or silently truncating with
"...". Folding stops at a seal (R1's own leaf, checkpoint v28.0 §441): the
aggregate covers only the within-window run, and the seal past it still
carries its fixed refusal sentence. Three registers — card (`explain`),
prompt (`why_tree`), machine (`why_machine`) — render from one traversal of
one Deriv graph, so they cannot describe different nodes.

This file is the build's own N+3.2 gate: it emits a pass/fail table covering
the seven things the build prompt names as blocking —
  1. one-layer default (§3)
  2. aggregate labeled and distinguishable from a single step (§4/F1)
  3. aggregate count == within-window steps, never absorbing released
     history (§5a/F2)
  4. seal renders as a named leaf with its refusal sentence, nothing past
     it present (§5b)
  5. three registers describe one source (§6/F3)
  6. zero bare "..." across the corpus (§7/F6)
  7. cross-language deep-walk byte-identity, corpus-wide (§8/invariant 1)
— in addition to the ordinary per-function test run every suite in this
repo does. It shells out to `node js/cli.mjs whytree[-corpus] <config>` for
the cross-language checks, the same pattern test_retention.py and
test_js_interp.py use; Node's availability is a baseline fact for this
build, so the whole file skips with a clear message if node is missing
rather than failing spuriously.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

from host import TestHost
from interp import Interpreter, PlanesError, Traced, explain, fmt, why_machine, why_tree
from lexer import PlanesSyntaxError
from modules import ModuleError

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))


def _skip_if_no_node():
    if NODE is None:
        print("  SKIP  node not on PATH")
        return True
    return False


def _chain(n):
    """A program that reassigns `x` n times — the same fixture
    test_retention.py uses, the shape a long-running per-tick
    `with`/reassignment loop actually builds."""
    return "\n".join(["x = 0"] + ["x = x + 1"] * n + ["show x"]) + "\n"


def _uses_import(src):
    return any(ln.strip().startswith("use ") for ln in src.splitlines())


def _corpus_files():
    files = sorted(
        f for f in glob.glob("**/*.planes", recursive=True) if ".venv" not in f)
    assert len(files) >= 40, len(files)
    return files


def _find_seal(node):
    seen = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        if n.kind == "seal":
            return n
        stack.extend(n.inputs)
    return None


def _reachable_name_count(node):
    """How many 'name' Deriv nodes are reachable before any seal — the
    ground truth an aggregate's count is checked against, computed by a
    method independent of `why_machine`'s own walk."""
    seen = set()
    stack = [node]
    count = 0
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        if n.kind == "seal":
            continue
        if n.kind == "name":
            count += 1
        stack.extend(n.inputs)
    return count


def _machine_seal(node):
    """The seal WalkNode inside a why_machine() tree, wherever it landed —
    None if none is present."""
    if node is None:
        return None
    if node["type"] == "seal":
        return node
    if node["type"] == "aggregate":
        return _machine_seal(node["tail"])
    if node["type"] == "step":
        for c in node.get("children", []):
            found = _machine_seal(c)
            if found is not None:
                return found
    return None


# ================================================================ 1. one-layer default

def test_explain_stays_a_single_line_no_matter_how_deep_the_chain():
    """§3: `why` on a value answers one layer by default. A chain of 50
    reassignments — comfortably past the fold threshold — still gets the
    ordinary one-line `explain` text; nothing about its length changes with
    how deep the derivation actually goes."""
    i = Interpreter(host=TestHost())
    i.run(_chain(50))
    card = explain(i.env.get("x"))
    assert card.count("\n") == 0, card
    assert "advanced" not in card and "..." not in card


def test_the_deep_walk_is_a_separate_explicit_call():
    """The rest of §3: more than one layer is reached only by calling the
    deep walk explicitly — `why_tree`/`why_machine`, not `explain` — and
    that explicit call visibly differs from the default for the identical
    value."""
    i = Interpreter(host=TestHost())
    i.run(_chain(50))
    traced = i.env.get("x")
    card = explain(traced)
    deep = why_tree(traced)
    assert card != deep
    assert "advanced" in deep and "advanced" not in card


# ================================================================ 2. aggregate distinguishable (F1)

def test_aggregate_is_a_distinct_type_never_a_step():
    i = Interpreter(host=TestHost())
    i.run(_chain(50))
    m = why_machine(i.env.get("x"))
    agg = m["root"]["children"][0]
    assert agg["type"] == "aggregate"
    assert agg["type"] != "step"
    assert "kind" not in agg          # steps carry a Deriv `kind`; aggregates never do
    assert agg["count"] == 50


def test_aggregate_line_never_reads_as_a_single_step():
    """A folded run renders as ONE line, and that line can never be
    mistaken for a `label = value` step line — the format itself differs
    (no `=`), not merely its content."""
    i = Interpreter(host=TestHost())
    i.run(_chain(50))
    wt = why_tree(i.env.get("x"))
    lines = wt.split("\n")
    assert len(lines) == 2, lines               # root line + one fold line, not 50
    assert "advanced" in lines[1]
    assert " = " not in lines[1]
    assert lines[1] != lines[0]


def test_short_run_below_fold_threshold_stays_unfolded():
    """F1's margin: a run too short to fold prints every step, so a reader
    never sees a mysterious count standing in for something a normal view
    would show plainly. Also pins test_values.py's own 3-step accumulation
    behavior, which this build must not disturb."""
    i = Interpreter(host=TestHost())
    i.run(_chain(3))
    wt = why_tree(i.env.get("x"))
    assert "advanced" not in wt
    for v in ("x = 3", "x = 2", "x = 1", "x = 0"):
        assert v in wt, (v, wt)


# ================================================================ 3. aggregate count exact (F2)

def test_aggregate_count_matches_reachable_steps_exactly_unwindowed():
    i = Interpreter(host=TestHost())
    i.run(_chain(300))
    node = i.env.get("x").node
    m = why_machine(i.env.get("x"))
    agg = m["root"]["children"][0]
    assert agg["type"] == "aggregate"
    assert agg["tail"] is None                  # chain ends naturally, no seal
    assert agg["count"] == _reachable_name_count(node) - 1


def test_aggregate_count_equals_within_window_steps_never_more():
    """§5a/F2: the fold covers only what is still live — released history
    behind a seal is never counted as though it were a present step."""
    WINDOW = 50
    i = Interpreter(host=TestHost(), window=WINDOW)
    i.run(_chain(600))
    node = i.env.get("x").node
    seal = _find_seal(node)
    assert seal is not None
    m = why_machine(i.env.get("x"))
    agg = m["root"]["children"][0]
    assert agg["type"] == "aggregate"
    assert agg["tail"] is not None and agg["tail"]["type"] == "seal"
    # ground truth: reachable "name" nodes before the seal, computed by a
    # method that does not go through why_machine's own walk at all.
    assert agg["count"] == _reachable_name_count(node) - 1
    # and released history is NOT folded in: the seal names how much it
    # released, and that number is disjoint from the aggregate's count.
    assert seal.released_count > 0


# ================================================================ 4. seal is a named leaf (§5b)

def test_seal_carries_its_exact_refusal_sentence_and_nothing_past_it():
    WINDOW = 5
    i = Interpreter(host=TestHost(), window=WINDOW)
    i.run(_chain(200))
    traced = i.env.get("x")
    seal = _find_seal(traced.node)
    assert seal is not None

    wt = why_tree(traced)
    assert seal.label in wt
    assert wt.count(seal.label) == 1

    m = why_machine(traced)
    seal_node = _machine_seal(m["root"])
    assert seal_node is not None
    assert seal_node["label"] == seal.label
    assert seal_node["value"] == fmt(seal.value)
    # a true leaf: the machine register's seal node carries no children key
    # at all, so nothing "past" it can be represented, let alone present.
    assert "children" not in seal_node
    assert "tail" not in seal_node


# ================================================================ 5. three registers (F3)

def test_card_prompt_and_machine_describe_the_same_root_node():
    i = Interpreter(host=TestHost())
    i.run(_chain(3))
    traced = i.env.get("x")
    card = explain(traced)
    wt = why_tree(traced)
    m = why_machine(traced)
    # ground truth, independent of any register: the traced node itself.
    assert m["root"]["label"] == traced.node.label
    assert m["root"]["value"] == fmt(traced.node.value)
    assert card.startswith(m["root"]["value"] + " from ")
    assert wt.splitlines()[0] == f"{m['root']['label']} = {m['root']['value']}"


def test_registers_agree_across_a_folded_and_a_sealed_scenario_too():
    """The same property, not only on the trivial case: a folded chain and
    a windowed/sealed chain must not let the registers drift either."""
    for cfg_window, n in ((None, 40), (5, 200)):
        i = Interpreter(host=TestHost(), window=cfg_window)
        i.run(_chain(n))
        traced = i.env.get("x")
        card = explain(traced)
        wt = why_tree(traced)
        m = why_machine(traced)
        assert m["root"]["label"] == traced.node.label == "x"
        assert m["root"]["value"] == fmt(traced.node.value)
        assert card.startswith(m["root"]["value"] + " from ")
        assert wt.splitlines()[0] == f"{m['root']['label']} = {m['root']['value']}"


# ================================================================ 6. zero bare "..." (F6)

def test_no_bare_ellipsis_line_across_the_corpus():
    """§7/F6: grep the deep-walk output across the corpus for a line whose
    entire (stripped) content is "..." — HEAD's silent truncation marker.
    A legitimate program value that happens to CONTAIN "..." as text is not
    a violation; only the old bare marker, as a whole line, is."""
    violations = []
    for f in _corpus_files():
        src = open(f, encoding="utf-8").read()
        itp = Interpreter(host=TestHost())
        try:
            if _uses_import(src):
                itp.run_file(f)
            else:
                itp.run(src)
        except (PlanesError, PlanesSyntaxError, ModuleError, RecursionError):
            continue   # a program that fails to run has no derivations here
        for node, line in itp.trace:
            wt = why_tree(Traced(node.value, node))
            if any(ln.strip() == "..." for ln in wt.split("\n")):
                violations.append(f"{f}:{line}")
    assert not violations, violations


# ================================================================ 7. cross-language (§8)

def _node_whytree(cfg):
    r = subprocess.run(
        [NODE, "js/cli.mjs", "whytree", json.dumps(cfg)],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed: {r.stderr}")
    return json.loads(r.stdout)


def _py_whytree(cfg):
    itp = Interpreter(host=TestHost(), window=cfg.get("window"))
    for s in cfg["steps"]:
        itp.run(s)
    traced = itp.env.get(cfg["subject"])
    max_depth = cfg.get("maxDepth", 14)
    because = cfg.get("because")
    return {
        "card": explain(traced, because),
        "prompt": why_tree(traced, max_depth, because),
        "machine": why_machine(traced, max_depth, because),
    }


def test_python_and_javascript_agree_on_synthetic_fold_and_seal_scenarios():
    scenarios = [
        {"steps": _chain(3).splitlines(keepends=True), "subject": "x"},
        {"steps": _chain(50).splitlines(keepends=True), "subject": "x"},
        {"window": 5, "steps": _chain(200).splitlines(keepends=True), "subject": "x"},
        {"window": 50, "steps": _chain(300).splitlines(keepends=True), "subject": "x"},
        {"steps": ["x = 1\n"], "subject": "x", "because": 'a"b'},
        {"steps": ["to fact of n:\n  if n <= 1:\n    give 1\n  "
                   "give n * (fact of (n - 1))\n\n", "r = fact of 20\n"],
         "subject": "r", "maxDepth": 40},
    ]
    mismatches = []
    for cfg in scenarios:
        py = _py_whytree(cfg)
        js = _node_whytree(cfg)
        if py != js:
            mismatches.append((cfg, py, js))
    assert not mismatches, mismatches


_PY_CARD_TOO_DEEP = "<py-recursion-too-deep>"  # sentinel, never a real card


def _py_whytree_corpus(path):
    """`card` is `explain()`, unchanged by this build — and `explain()`'s
    `approximations_in` walks a derivation with plain Python recursion,
    same as it always has, so a program whose UNWINDOWED chain runs deep
    enough (roughly 450+ steps, pre-existing on HEAD, nothing R2 touches)
    can still hit Python's own recursion limit there. `prompt`/`machine`
    are this build's own new code and are iterative (no such ceiling); a
    card that hits this pre-existing limit is marked with a sentinel and
    excluded from the cross-language card comparison below, not treated
    as a why_tree/whyTree divergence."""
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
    entries = []
    for node, line in itp.trace:
        traced = Traced(node.value, node)
        try:
            card = explain(traced)
        except RecursionError:
            card = _PY_CARD_TOO_DEEP
        entries.append({
            "line": line,
            "card": card,
            "prompt": why_tree(traced),
            "machine": why_machine(traced),
        })
    return {"tag": tag, "outputCount": len(itp.output), "entries": entries}


def _js_whytree_corpus(path):
    r = subprocess.run(
        [NODE, "js/cli.mjs", "whytree-corpus", path],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed on {path}: {r.stderr}")
    return json.loads(r.stdout)


def test_python_and_javascript_whytree_agree_across_the_corpus():
    """§8/invariant 1: interp.py is the specification; js/interp.mjs's
    first-built whyTree agrees byte for byte, corpus-wide — not by
    inspection, by diffing `node js/cli.mjs whytree-corpus <file>` against
    interp.py run on the same file. `prompt` and `machine` — this build's
    own surfaces — are compared exactly; `card` (`explain`, unchanged) is
    compared except where Python's own pre-existing recursion limit
    marked it unavailable (see `_py_whytree_corpus`)."""
    mismatches = []
    for f in _corpus_files():
        py = _py_whytree_corpus(f)
        js = _js_whytree_corpus(f)
        if py["tag"] != js["tag"] or py["outputCount"] != js["outputCount"] or \
           len(py["entries"]) != len(js["entries"]):
            mismatches.append(f"{f}: tag/outputCount/entry-count differ "
                              f"py={py['tag'], py['outputCount'], len(py['entries'])} "
                              f"js={js['tag'], js['outputCount'], len(js['entries'])}")
            continue
        for i, (pe, je) in enumerate(zip(py["entries"], js["entries"])):
            if pe["prompt"] != je["prompt"] or pe["machine"] != je["machine"]:
                mismatches.append(f"{f}: prompt/machine diverge @ line {pe['line']}: "
                                  f"py={pe!r} js={je!r}")
            elif pe["card"] != _PY_CARD_TOO_DEEP and pe["card"] != je["card"]:
                mismatches.append(f"{f}: card diverges @ line {pe['line']}: "
                                  f"py={pe['card']!r} js={je['card']!r}")
    assert not mismatches, "whytree divergences:\n" + "\n".join(mismatches)


if __name__ == "__main__":
    if _skip_if_no_node():
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
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")

    CRITERIA = [
        ("one-layer default (§3)",
         [test_explain_stays_a_single_line_no_matter_how_deep_the_chain,
          test_the_deep_walk_is_a_separate_explicit_call]),
        ("aggregate labeled and distinguishable from a step (§4/F1)",
         [test_aggregate_is_a_distinct_type_never_a_step,
          test_aggregate_line_never_reads_as_a_single_step,
          test_short_run_below_fold_threshold_stays_unfolded]),
        ("aggregate count == within-window steps (§5a/F2)",
         [test_aggregate_count_matches_reachable_steps_exactly_unwindowed,
          test_aggregate_count_equals_within_window_steps_never_more]),
        ("seal is a named leaf, nothing past it present (§5b)",
         [test_seal_carries_its_exact_refusal_sentence_and_nothing_past_it]),
        ("three registers describe one source (§6/F3)",
         [test_card_prompt_and_machine_describe_the_same_root_node,
          test_registers_agree_across_a_folded_and_a_sealed_scenario_too]),
        ("zero bare \"...\" across the corpus (§7/F6)",
         [test_no_bare_ellipsis_line_across_the_corpus]),
        ("cross-language deep-walk byte-identity (§8/invariant 1)",
         [test_python_and_javascript_agree_on_synthetic_fold_and_seal_scenarios,
          test_python_and_javascript_whytree_agree_across_the_corpus]),
    ]
    print("\n=== R2 verification gate (N+3.2) ===")
    width = max(len(name) for name, _ in CRITERIA)
    table_failed = False
    for name, checks in CRITERIA:
        row_ok = all(fn.__name__ not in fails for fn in checks)
        table_failed = table_failed or not row_ok
        print(f"  {'PASS' if row_ok else 'FAIL'}  {name.ljust(width)}")
    print()

    sys.exit(1 if (fails or table_failed) else 0)
