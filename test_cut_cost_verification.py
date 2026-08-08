"""scripts/verify-cut-cost.py — Horizon Phase 1: `_cut`'s per-`mk` cost,
the build prompt's own §6.2 verification gate (assertions A-F).

A, B, C, D, F block the PR (§6.2's own blocking rule). E does not block —
it reports the after windowed p95 against 5.0 ms and states plainly
whether the gate passes, which `horizon-cut-cost-results.md` (written by
`world_cut_bench.py`) already does; this script's own E check just
confirms that file exists and contains an explicit pass/fail statement,
rather than re-running the 10,000-tick soak a second time here.

Graduates into `scripts/run_suites.py` the same way
`test_retention_tail_verification.py` did for the prior build (that file's
own docstring states the reason: `test_gate.py`'s C6/Ruling 3 hard-fails
`scripts/ci.sh` on any `verify_*`/`verify-*` script left in the tree — a
verification script graduates into a suite or is deleted when its build
merges).
"""
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

BASE_REF = "main"  # the pre-this-build state (HEAD 02010fd)
WINDOW = 5
N = 300  # generations, enough to cross WINDOW many times over

# Multiple allowed spans, not one: this build's own diff touches TWO
# separate regions of interp.py (the `__init__` bookkeeping fields, and
# the `_frontier*`/`_cut` method block), not one contiguous run like the
# prior build's `_seal`-only change. Each entry is (start-marker,
# end-marker); the allowed span is [start-marker's line, end-marker's
# line) — a hunk's new-file starting line must fall inside at least one.
ALLOWED_SPANS_PY = [
    ("import hashlib", "class _BuiltinName"),
    ("self._pinned = {}", "# The tracing-off fast path"),
    ("def _frontier_extends(self, node, tip):", "def _seal(self, root):"),
]
ALLOWED_SPANS_JS = [
    ('import { Host, MemoryHost, TestHost, HostError, pyJsonDumps } from "./host.mjs";',
     "export class Traced {"),
    ("this._pinned = new Map();", "// The tracing-off fast path"),
    ("// Binary min-heap helpers over `this._cutFrontier`", "_seal(root) {"),
]


def _steps():
    return ["x = 0\n"] + ["x = x + 1\n"] * N + ["show x\n"]


def _load_module_at_ref(ref, modname):
    src = subprocess.run(
        ["git", "show", f"{ref}:interp.py"], cwd=REPO,
        capture_output=True, text=True, check=True).stdout
    tmp_dir = tempfile.mkdtemp(prefix="cut_cost_verify_")
    tmp_path = os.path.join(tmp_dir, f"{modname}.py")
    with open(tmp_path, "w", encoding="utf-8") as fh:
        fh.write(src)
    spec = importlib.util.spec_from_file_location(modname, tmp_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


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


def _reachable(node):
    seen = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        if n.kind != "seal":
            stack.extend(n.inputs)
    return len(seen)


def _run_windowed(interp_mod, window, steps):
    itp = interp_mod.Interpreter(host=interp_mod.TestHost(), window=window)
    for s in steps:
        itp.run(s)
    return itp


# ================================================================ A. replay-reconstructibility

def test_a_why_machine_is_byte_identical_before_and_after():
    """§474: for a representative windowed program (and a DAG-sharing
    program — the shape §3 of this build's own results doc names as the
    fast path's real limit, so the gate has to cover it, not just the
    clean accumulator case), `why_machine`/`why_tree` on the value the
    CURRENT `interp.py` produces must be byte-for-byte identical to what
    `interp.py` at `BASE_REF` (this build's changes bypassed) produces.
    """
    import host as host_mod
    before_mod = _load_module_at_ref(BASE_REF, "interp_before_a")
    before_mod.TestHost = host_mod.TestHost
    import interp as after_mod

    programs = [
        ("linear", _steps()),
        ("dag-sharing", ["a = 0\n", "b = 0\n"] +
         ["a = a + a\n", "b = b + a\n", "a = a + b\n"] * 80 + ["show a\n"]),
    ]
    for label, steps in programs:
        subj = "x" if label == "linear" else "a"
        itp_before = _run_windowed(before_mod, WINDOW, steps)
        itp_after = _run_windowed(after_mod, WINDOW, steps)
        wm_before = before_mod.why_machine(itp_before.env.get(subj))
        wm_after = after_mod.why_machine(itp_after.env.get(subj))
        assert wm_before == wm_after, f"{label}: why_machine diverges"
        wt_before = before_mod.why_tree(itp_before.env.get(subj))
        wt_after = after_mod.why_tree(itp_after.env.get(subj))
        assert wt_before == wt_after, f"{label}: why_tree diverges"


# ================================================================ B. determinism

def test_b_python_and_js_agree_on_the_kernel_soak_chain_hash():
    from host import TestHost
    from world_kernel import WorldKernel
    from world_test_sink import TestSink

    for window in (None, 300):
        k = WorldKernel("paint/world/kernel_spike_fixture.planes",
                         host=TestHost(), window=window)
        k.start()
        sink = TestSink()
        for _ in range(300):
            delta, elapsed = k.step()
            sink.consume(delta, elapsed)
        py_hash = sink.chain_hash
        assert re.fullmatch(r"[0-9a-f]{64}", py_hash)

        js_script = f"""
        import {{ WorldKernel }} from "./js/world_kernel.mjs";
        import {{ TestSink }} from "./js/world_test_sink.mjs";
        import {{ TestHost }} from "./js/host.mjs";
        const k = new WorldKernel("paint/world/kernel_spike_fixture.planes",
          {{ host: new TestHost(), window: {"null" if window is None else window} }});
        await k.start();
        const sink = new TestSink();
        for (let i = 0; i < 300; i++) {{
          const {{ delta, elapsedSeconds }} = k.step();
          sink.consume(delta, elapsedSeconds);
        }}
        process.stdout.write(sink.chainHash);
        """
        r = subprocess.run(["node", "--input-type=module", "-e", js_script],
                            capture_output=True, text=True, cwd=REPO)
        assert r.returncode == 0, r.stderr
        js_hash = r.stdout.strip()
        assert py_hash == js_hash, (
            f"window={window}: python chain hash {py_hash} != js chain hash {js_hash}")


# ================================================================ C. seal identity

def test_c_seal_identity_unchanged_from_base_ref():
    """Every seal's generation/fingerprint/released_count identical to
    `BASE_REF`'s `_cut` output, for a FIXED windowed input, both a clean
    linear accumulator and a DAG-sharing program, at several window
    sizes — the absolute requirement (§5.2): a faster cut that produces a
    different seal is a wrong cut, whether or not the fast path itself
    ends up running for a given call."""
    import host as host_mod
    before_mod = _load_module_at_ref(BASE_REF, "interp_before_c")
    before_mod.TestHost = host_mod.TestHost
    import interp as after_mod

    programs = [
        ("linear", _steps(), "x"),
        ("dag-sharing", ["a = 0\n", "b = 0\n", "c = 0\n"] +
         ["a = a + a\n", "b = b + a\n", "c = a + b\n", "a = a + c\n"] * 60 +
         ["show a\n"], "a"),
    ]
    for label, steps, subj in programs:
        for window in (3, 5, 30, 100):
            itp_before = _run_windowed(before_mod, window, steps)
            itp_after = _run_windowed(after_mod, window, steps)
            seal_before = _find_seal(itp_before.env.get(subj).node)
            seal_after = _find_seal(itp_after.env.get(subj).node)
            assert seal_before is not None and seal_after is not None, (
                f"{label}/{window}: no seal found on one side")
            assert seal_before.generation == seal_after.generation, label
            assert seal_before.fingerprint == seal_after.fingerprint, label
            assert seal_before.released_count == seal_after.released_count, label


# ================================================================ D. unbounded untouched

def test_d_unbounded_window_reachable_count_and_cost_unchanged():
    """A `window=None` run's derivation is unchanged from `BASE_REF` —
    `mk`'s own guard (`if self.window is not None: self._cut(node)`)
    means `_cut` is never even called on this path, so this is really a
    check that nothing else in this build's diff touched that guard."""
    import host as host_mod
    before_mod = _load_module_at_ref(BASE_REF, "interp_before_d")
    before_mod.TestHost = host_mod.TestHost
    import interp as after_mod

    steps = _steps()
    itp_before = before_mod.Interpreter(host=before_mod.TestHost(), window=None)
    itp_after = after_mod.Interpreter(host=after_mod.TestHost(), window=None)
    for s in steps:
        itp_before.run(s)
        itp_after.run(s)
    assert itp_before.output == itp_after.output
    node_before, node_after = itp_before.env.get("x").node, itp_after.env.get("x").node

    def reachable(node):
        seen = set()
        stack = [node]
        while stack:
            n = stack.pop()
            if id(n) in seen:
                continue
            seen.add(id(n))
            stack.extend(n.inputs)
        return len(seen)

    assert reachable(node_before) == reachable(node_after)
    assert itp_after._generation == itp_before._generation


# ================================================================ E. step gate (non-blocking, explicit statement required)

def test_e_results_doc_states_the_step_gate_outcome_explicitly():
    path = os.path.join(REPO, "horizon-cut-cost-results.md")
    assert os.path.exists(path), (
        "horizon-cut-cost-results.md missing — run world_cut_bench.py first")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert "§4 pass condition 1" in text
    assert "clears 5.0 ms?" in text
    assert "FAIL" in text or "PASS" in text, (
        "results doc does not state pass/fail explicitly (§6.2.E / S1)")


# ================================================================ F. value-model untouched

def _diff_hunks_out_of_scope(path, allowed_spans):
    diff = subprocess.run(
        ["git", "diff", "-U0", BASE_REF, "--", path], cwd=REPO,
        capture_output=True, text=True, check=True).stdout
    if not diff.strip():
        return []
    full_path = os.path.join(REPO, path)
    with open(full_path, encoding="utf-8") as fh:
        new_src = fh.read()
    spans = []
    for start_marker, end_marker in allowed_spans:
        start_idx = new_src.find(start_marker)
        end_idx = new_src.find(end_marker)
        if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
            return [f"{path}: could not locate span markers "
                     f"({start_marker!r} -> {end_marker!r})"]
        start_line = new_src.count("\n", 0, start_idx) + 1
        end_line = new_src.count("\n", 0, end_idx) + 1
        spans.append((start_line, end_line))

    problems = []
    for line in diff.splitlines():
        if not line.startswith("@@"):
            continue
        plus_part = line.split("+", 1)[1].split(" ", 1)[0]
        new_start = int(plus_part.split(",")[0])
        if not any(s <= new_start < e for s, e in spans):
            problems.append(f"{path}: hunk at new-file line {new_start} "
                             f"falls outside every allowed span {spans}")
    return problems


def test_f_interp_py_and_js_interp_mjs_changes_confined_to_cut():
    """`git diff --name-only main` for `interp.py`/`js/interp.mjs` must
    show changes only inside the `__init__` bookkeeping and the
    `_frontier*`/`_cut` method block (plus the one-line `heapq` import in
    Python) — never a value/effect/builtin/plane surface change."""
    problems = []
    problems += _diff_hunks_out_of_scope("interp.py", ALLOWED_SPANS_PY)
    problems += _diff_hunks_out_of_scope("js/interp.mjs", ALLOWED_SPANS_JS)
    assert not problems, "out-of-scope change: " + "; ".join(problems)


def test_f_only_expected_files_changed():
    diff = subprocess.run(
        ["git", "diff", "--name-only", BASE_REF], cwd=REPO,
        capture_output=True, text=True, check=True).stdout.split()
    allowed = {
        "interp.py", "js/interp.mjs",
        "world_cut_bench.py", "scripts/verify-cut-cost.py",
        "horizon-cut-cost-results.md", "cut-cost-raw.json",
        "cut-cost-verification.md",
        # Regenerated by `grammar_gen.py`, not hand-edited: interp.py's new
        # code shifts every later line number, and errors.json records
        # each catalogued error's site as `interp.py:<line>` (D2 doctrine,
        # grammar/README.md) — a legitimate consequence of this build's
        # own diff, not a value-model change.
        "grammar/errors.json",
        # Pre-existing in the working tree before this build started (see
        # the session's own initial `git status`) — Rob's own in-progress
        # work, unrelated to this build, and never staged/committed here.
        "docs/superpowers/specs/2026-08-01-horizon-living-passage-game-engine-design.md",
    }
    unexpected = [f for f in diff if f not in allowed]
    assert not unexpected, f"unexpected files changed: {unexpected}"


if __name__ == "__main__":
    fails = []
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    results_table = []
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
            results_table.append((name, "PASS"))
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            fails.append(name)
            results_table.append((name, f"FAIL: {e}"))
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
            results_table.append((name, f"ERROR: {type(e).__name__}: {e}"))
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")

    CRITERIA = [
        ("A. replay-reconstructibility (§474)",
         [test_a_why_machine_is_byte_identical_before_and_after], True),
        ("B. determinism (python/js chain hash agree)",
         [test_b_python_and_js_agree_on_the_kernel_soak_chain_hash], True),
        ("C. seal identity absolute (§5.2)",
         [test_c_seal_identity_unchanged_from_base_ref], True),
        ("D. unbounded path untouched",
         [test_d_unbounded_window_reachable_count_and_cost_unchanged], True),
        ("E. step gate stated explicitly (non-blocking)",
         [test_e_results_doc_states_the_step_gate_outcome_explicitly], False),
        ("F. value-model / diff scope untouched",
         [test_f_interp_py_and_js_interp_mjs_changes_confined_to_cut,
          test_f_only_expected_files_changed], True),
    ]
    print("\n=== _cut cost verification gate (build prompt §6.2) ===")
    width = max(len(name) for name, _, _ in CRITERIA)
    table_lines = [f"| {'criterion'.ljust(width)} | blocking | result |",
                    f"|{'-'*(width+2)}|----------|--------|"]
    gate_failed = False
    for name, checks, blocking in CRITERIA:
        row_ok = all(fn.__name__ not in fails for fn in checks)
        if blocking:
            gate_failed = gate_failed or not row_ok
        status = "PASS" if row_ok else "FAIL"
        print(f"  {status}  {name.ljust(width)}  {'blocking' if blocking else 'non-blocking'}")
        table_lines.append(f"| {name.ljust(width)} | {'yes' if blocking else 'no'} | {status} |")

    with open(os.path.join(REPO, "cut-cost-verification.md"), "w", encoding="utf-8") as fh:
        fh.write("# `_cut` cost verification (build prompt §6.2)\n\n")
        fh.write("\n".join(table_lines) + "\n")
    print("\nwrote cut-cost-verification.md")

    sys.exit(1 if (fails and gate_failed) else 0)
