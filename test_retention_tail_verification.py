"""test_retention_tail_verification.py — Horizon Phase 1: the retention
tail, the build prompt's own §6.2 verification gate (assertions A-F).

THE ONE DEVIATION FROM THE BUILD PROMPT, STATED WHERE THE NEXT BUILD READS
IT (the same deviation test_world_kernel_verification.py records for the
prior build, for the identical reason). §6.2 names this file
`scripts/verify-retention-tail.py`. This repo's own `test_gate.py` (C6,
Ruling 3) hard-fails `scripts/ci.sh` on ANY `verify_*`/`verify-*` script
anywhere in the tree — "a verification script graduates into a suite or is
deleted when its build merges." Shipping the literal filename the build
prompt names would fail the very gate this build's own §6.1 runs.
`test_gate.py`'s own stated remedy is "graduate the durable assertions
into a suite this gate runs" — which is exactly this file, run by
`scripts/run_suites.py` like any other suite.

A, B, C, D, F block the PR (§6.2's own blocking rule). E (the tail-gate
finding — whether the 10,000-tick soak clears zero over-50ms ticks in the
windowed configuration) is NOT here: it is a property of the full soak
`world_tail_bench.py` runs (a multi-minute measurement, by design not
something every routine `scripts/ci.sh` pass re-runs — `world_kernel_bench.py`,
the prior build's own soak driver, is not named `test_*.py` for the same
reason), and its answer for this build is already durably recorded in
`horizon-retention-tail-results.md`'s own "§4 pass condition 1" section
(an explicit escalation statement, not a silent pass) plus
`.ci-logs/retention-tail-raw.json`. What belongs in an every-run gate is
the CODE-LEVEL invariants A/B/C/D/F check for, permanently, regardless of
whether anyone has re-run the multi-minute soak recently.
"""
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

BASE_REF = "main"  # the pre-this-build state (HEAD de541dc)
WINDOW = 5
N = 300  # generations, enough to cross WINDOW many times over
KERNEL_SOURCE = os.path.join(REPO, "world_kernel.py")

PERMITTED_INTERP_PY_MARKERS = ("def _seal(self, root):",)
PERMITTED_JS_INTERP_MARKERS = ("_seal(root) {",)


def _steps():
    return ["x = 0\n"] + ["x = x + 1\n"] * N + ["show x\n"]


def _load_module_at_ref(ref, modname):
    """Loads `interp.py` as it existed at `ref` into its own module
    namespace, distinct from the current (post-Rung-2) `interp` module
    already importable normally. Its own sibling imports (`world_ir`,
    `host`, `lexer`, `parser`, `planes_num`, `planes_text`,
    `world_source_map`) are untouched by this build (§5.5/check F) and
    resolve normally via `REPO` already on `sys.path` — only `interp.py`
    itself needs a second, isolated copy."""
    src = subprocess.run(
        ["git", "show", f"{ref}:interp.py"], cwd=REPO,
        capture_output=True, text=True, check=True).stdout
    tmp_dir = tempfile.mkdtemp(prefix="retention_tail_verify_")
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


def _run_windowed(interp_mod, window, steps):
    itp = interp_mod.Interpreter(host=interp_mod.TestHost(), window=window)
    for s in steps:
        itp.run(s)
    return itp


# ================================================================ A. replay-reconstructibility

def test_a_why_machine_is_byte_identical_changes_active_vs_bypassed():
    """§474, the licence this build's whole approach is measured against:
    for a representative windowed program, `why_machine`/`why_tree` on the
    value the CURRENT (Rung-2-active) `interp.py` produces must be
    byte-for-byte identical to what `interp.py` at `BASE_REF` (changes
    bypassed) would have produced. Rung 1 (world_kernel.py's GC-timing
    changes) cannot affect this by construction — it never touches
    interp.py at all — so this exercises Rung 2's `_seal` rewrite, the
    one change in this build that touches derivation-graph construction."""
    import host as host_mod
    steps = _steps()

    before_mod = _load_module_at_ref(BASE_REF, "interp_before_a")
    before_mod.TestHost = host_mod.TestHost
    itp_before = _run_windowed(before_mod, WINDOW, steps)

    import interp as after_mod
    itp_after = _run_windowed(after_mod, WINDOW, steps)

    wm_before = before_mod.why_machine(itp_before.env.get("x"))
    wm_after = after_mod.why_machine(itp_after.env.get("x"))
    assert wm_before == wm_after, "why_machine diverges, changes active vs bypassed"

    wt_before = before_mod.why_tree(itp_before.env.get("x"))
    wt_after = after_mod.why_tree(itp_after.env.get("x"))
    assert wt_before == wt_after, "why_tree diverges, changes active vs bypassed"


# ================================================================ B. determinism

def test_b_python_and_js_chain_hash_agree_for_both_retention_configurations():
    """test_world_kernel_verification.py's own test_a_* already covers this
    for `WorldKernel`'s default (window=None); this build's own risk is
    specifically the WINDOWED configuration (Rung 2 touches `_seal`, which
    only ever fires under a finite window), so this adds that case
    explicitly rather than relying on the default-only coverage."""
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


# ================================================================ C. seal surface unchanged

def test_c_seal_surface_unchanged_fingerprint_refusal_released_count():
    """`_seal`'s fingerprint, refusal sentence (`.label`), and
    `released_count` — the byte-identical-tested surface — must be
    identical to `BASE_REF` for a fixed windowed input. Rung 2 changed HOW
    the Python fingerprint is computed (streamed vs list-then-join); this
    proves it did not change WHAT it computes. (The JS side's `_seal` is
    byte-for-byte unchanged from `BASE_REF` — Rung 2 was measured there
    and reverted, see js/interp.mjs's `_seal` docstring — so this check's
    JS half is a no-op by construction, not skipped.)"""
    import host as host_mod
    steps = _steps()

    before_mod = _load_module_at_ref(BASE_REF, "interp_before_c")
    before_mod.TestHost = host_mod.TestHost
    itp_before = _run_windowed(before_mod, WINDOW, steps)
    seal_before = _find_seal(itp_before.env.get("x").node)

    import interp as after_mod
    itp_after = _run_windowed(after_mod, WINDOW, steps)
    seal_after = _find_seal(itp_after.env.get("x").node)

    assert seal_before is not None and seal_after is not None, "no seal found"
    assert seal_before.fingerprint == seal_after.fingerprint
    assert seal_before.label == seal_after.label
    assert seal_before.released_count == seal_after.released_count


# ================================================================ D. timing-span integrity

def test_d_no_gc_call_between_the_two_perf_counter_reads_in_step():
    """No `gc.` call between the two `time.perf_counter()` reads in
    `world_kernel.py`'s `step()` — Rung 1's maintenance call must sit
    strictly after `elapsed` is captured, never inside t0/elapsed (build
    prompt invariant 2, spike invariant 1 still binding). The JS
    counterpart of this same invariant (no sink call inside the timed
    span) is already covered by
    test_world_kernel_verification.py's test_b_*; this is the Rung-1-
    specific half those tests predate."""
    with open(KERNEL_SOURCE, encoding="utf-8") as fh:
        src = fh.read()

    def_idx = src.find("    def step(self):")
    assert def_idx != -1, "step() not found in world_kernel.py"
    next_def_idx = src.find("\n    def ", def_idx + 1)
    body = src[def_idx: next_def_idx if next_def_idx != -1 else len(src)]

    t0_idx = body.find("t0 = time.perf_counter()")
    elapsed_idx = body.find("elapsed = time.perf_counter() - t0")
    assert t0_idx != -1 and elapsed_idx != -1, "could not locate t0/elapsed markers"
    span = body[t0_idx:elapsed_idx]
    assert "gc." not in span, f"a gc.* call appears inside the timed span: {span!r}"


# ================================================================ F. value-model untouched

def test_f_interp_py_and_js_interp_mjs_changes_confined_to_seal():
    """`git diff --name-only main` for `interp.py`/`js/interp.mjs` must
    show changes only inside `_seal` — never a value/effect/builtin/plane
    surface change. Checked by naming the permitted changed region and
    asserting every diff hunk for those two files falls inside it."""
    problems = []
    for path, permitted_markers in (
        ("interp.py", PERMITTED_INTERP_PY_MARKERS),
        ("js/interp.mjs", PERMITTED_JS_INTERP_MARKERS),
    ):
        diff = subprocess.run(
            ["git", "diff", "-U0", BASE_REF, "--", path], cwd=REPO,
            capture_output=True, text=True, check=True).stdout
        if not diff.strip():
            continue  # no change to this file at all — trivially fine

        full_path = os.path.join(REPO, path)
        with open(full_path, encoding="utf-8") as fh:
            new_src = fh.read()
        marker_idx = min((new_src.find(m) for m in permitted_markers
                          if new_src.find(m) != -1), default=-1)
        if marker_idx == -1:
            problems.append(f"{path}: permitted marker not found in current source")
            continue
        seal_start_line = new_src.count("\n", 0, marker_idx) + 1
        next_def_idx = new_src.find("\n    def ", marker_idx + 1)
        seal_end_line = (new_src.count("\n", 0, next_def_idx) + 1
                          if next_def_idx != -1 else new_src.count("\n") + 1)

        for line in diff.splitlines():
            if not line.startswith("@@"):
                continue
            plus_part = line.split("+", 1)[1].split(" ", 1)[0]
            new_start = int(plus_part.split(",")[0])
            if not (seal_start_line <= new_start <= seal_end_line):
                problems.append(
                    f"{path}: hunk at new-file line {new_start} falls outside "
                    f"_seal's own span (lines {seal_start_line}-{seal_end_line})")

    assert not problems, "out-of-scope change: " + "; ".join(problems)


def test_f_streamed_and_joined_hash_produce_the_same_digest():
    """A direct check of the Python Rung 2 rewrite's own claim (interp.py's
    `_seal` docstring): hashing a sequence of lines incrementally via
    `hashlib.sha256().update()` produces the identical digest to joining
    them with `\\n` and hashing once. Not redundant with C above — C
    proves the SEAL's own output is unchanged; this proves the underlying
    STREAMING-HASH PROPERTY the rewrite relies on, independent of `_seal`."""
    lines = [f"line-{i}\x1fvalue-{i}" for i in range(50)]
    joined_digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()

    hasher = hashlib.sha256()
    for i, line in enumerate(lines):
        if i:
            hasher.update(b"\n")
        hasher.update(line.encode())
    streamed_digest = hasher.hexdigest()

    assert joined_digest == streamed_digest


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
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
            results_table.append((name, f"ERROR: {type(e).__name__}: {e}"))
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")

    report_path = os.path.join(REPO, "retention-tail-verification.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("# Horizon Phase 1: the retention tail — verification gate (§6.2)\n\n")
        fh.write("| assertion | result |\n|---|---|\n")
        for name, result in results_table:
            fh.write(f"| {name} | {result} |\n")
        fh.write(f"\n{len(tests) - len(fails)}/{len(tests)} passing.\n")
        fh.write("\nA/B/C/D/F failure blocks the PR. " + (
            "**BLOCKING FAILURE.**\n" if fails else "All pass.\n"))
        fh.write("\nE (the tail-gate finding) is not run here — it is a "
                 "property of the full multi-minute soak, recorded in "
                 "horizon-retention-tail-results.md instead. See that "
                 "file's own §4 pass condition 1 for its answer.\n")
    print(f"wrote {report_path}")

    sys.exit(1 if fails else 0)
