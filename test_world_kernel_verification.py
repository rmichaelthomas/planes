"""test_world_kernel_verification.py — Horizon Phase 1 engine-kernel spike,
the build prompt's own §10.2 verification gate (assertions A-D).

THE ONE DEVIATION FROM THE BUILD PROMPT, STATED WHERE THE NEXT BUILD READS
IT. §10.2 names this file `scripts/verify-kernel-spike.py`. This repo's own
`test_gate.py` (C6, Ruling 3) hard-fails `scripts/ci.sh` on ANY
`verify_*`/`verify-*` script anywhere in the tree, in any language — "a
verification script graduates into a suite or is deleted when its build
merges." Shipping the literal filename the build prompt names would fail
the very gate this build's own §10.1 runs. `test_gate.py`'s own stated
remedy is "graduate the durable assertions into a suite this gate runs
(test_*.py, ...)" — which is exactly this file. Every assertion the build
prompt's §10.2 names (A-D) is here, run by `scripts/run_suites.py` like any
other suite, with the same pass/fail table printed to stdout and (see
`__main__` below) written to `kernel-spike-verification.md`.

A, B, D block the PR (per §10.2's own blocking rule). C blocks unless the
architect accepts a documented gap — this file still asserts C and reports
its own pass/fail, but does not itself decide whether a C failure blocks;
that is `test_gate.py`'s aggregate exit code / whoever reads this suite's
report, matching the build prompt's own carve-out.
"""
import os
import re
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.abspath(__file__))

READ_ONLY_CORE = (
    "world_runtime.py", "world_ir.py", "world_delta.py",
    "grammar/protocols/world-v1.json",
)
# `interp.py` was here through Horizon Phase 1's engine-kernel spike (this
# file's own build), which had no reason to touch it. Horizon Phase 1: the
# retention tail (the next build) has a narrow, sanctioned one — Rung 2's
# `_seal` allocation rewrite — so a blanket "untouched" assertion on this
# file would now fail a legitimate build rather than catch scope creep.
# `test_retention_tail_verification.py`'s own check F is the file's
# successor guard: not "never changes" but "changes only inside `_seal`" —
# a narrower, more precise invariant for exactly this file going forward,
# not a loosening of the protection this list exists to provide.
RESULTS_MD = os.path.join(REPO, "horizon-kernel-spike-results.md")
KERNEL_SOURCE = os.path.join(REPO, "world_kernel.py")


# ============================================================ A. determinism

def test_a_python_and_js_delta_sequences_are_byte_identical_over_a_soak():
    """Reuses test_world_kernel_conformance.py's own comparison — the
    build prompt's own §10.1 already runs that suite; this assertion
    exists so §10.2's checklist has its own pass/fail line for the same
    fact, not a second, independently-implemented comparison that could
    drift from the real one."""
    import test_world_kernel_conformance as conformance
    py = conformance.python_tick_outcomes()
    js = conformance.js_tick_outcomes()
    assert py == js, "python and js kernel outputs diverge over the soak"


def test_a_semantic_hash_chain_is_unbroken_on_both_implementations():
    """"Unbroken": every consume() call produces a new, well-formed
    64-hex-digit chain value distinct from its predecessor — never a
    reset, never a repeat, on both implementations, over a real soak."""
    from host import TestHost
    from world_kernel import WorldKernel
    from world_test_sink import TestSink

    k = WorldKernel("paint/world/kernel_spike_fixture.planes", host=TestHost())
    k.start()
    sink = TestSink()
    seen = set()
    for _ in range(300):
        delta, elapsed = k.step()
        sink.consume(delta, elapsed)
        assert re.fullmatch(r"[0-9a-f]{64}", sink.chain_hash)
        assert sink.chain_hash not in seen, "chain hash repeated — the chain broke"
        seen.add(sink.chain_hash)

    js_script = """
    import { WorldKernel } from "./js/world_kernel.mjs";
    import { TestSink } from "./js/world_test_sink.mjs";
    import { TestHost } from "./js/host.mjs";
    const k = new WorldKernel("paint/world/kernel_spike_fixture.planes", { host: new TestHost() });
    await k.start();
    const sink = new TestSink();
    const seen = new Set();
    for (let i = 0; i < 300; i++) {
      const { delta, elapsedSeconds } = k.step();
      sink.consume(delta, elapsedSeconds);
      if (!/^[0-9a-f]{64}$/.test(sink.chainHash)) throw new Error("malformed chain hash");
      if (seen.has(sink.chainHash)) throw new Error("chain hash repeated");
      seen.add(sink.chainHash);
    }
    process.stdout.write("ok");
    """
    r = subprocess.run(["node", "--input-type=module", "-e", js_script],
                       capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "ok"


# ========================================================== B. timing integrity

def test_b_the_timed_span_in_step_never_calls_a_sink_by_static_inspection():
    """The instrumented region: everything textually between the two
    `time.perf_counter()` calls in `WorldKernel.step`. No sink-shaped call
    (`.consume(`) may appear there — `step()` returns data and leaves
    dispatch to the caller by construction (world_kernel.py's own module
    docstring), and this assertion is what keeps that true as the file
    changes."""
    with open(KERNEL_SOURCE, encoding="utf-8") as fh:
        src = fh.read()
    step_body = src[src.index("def step(self):"):]
    rest = step_body[1:]
    end = rest.index("\n    def ") + 1 if "\n    def " in rest else len(step_body)
    step_body = step_body[:end]
    first = step_body.index("time.perf_counter()")
    second = step_body.index("time.perf_counter()", first + 1)
    instrumented_region = step_body[first:second]
    assert ".consume(" not in instrumented_region, (
        "a sink call appears inside step()'s timed span:\n" + instrumented_region)


def test_b_sink_cost_is_excluded_from_the_recorded_figure_by_measurement():
    """The dynamic half of B: attach an artificially slow sink AFTER
    step() returns (the only place the real bench loop / test_world_kernel.py
    ever calls one) and confirm step()'s own reported `elapsed` does not
    grow — if sink cost were leaking into the timed span, this would be
    the first thing to show it.

    MEDIAN over 40 samples, not a single call or a p95: `scripts/ci.sh`
    runs suites under `run_suites.py`'s parallel jobs, and waking up from a
    `time.sleep()` under real contention can land the very next
    `perf_counter()`-timed call behind other processes in the OS run queue
    — inflating ONE call's wall-clock reading for a reason that has
    nothing to do with sink cost (found directly: a first version of this
    test using p95 over 30 samples flagged a false positive under
    `scripts/ci.sh`'s parallel run that a serial run never showed). A real
    leak inflates EVERY one of the 40 calls by roughly the sink's own sleep
    duration, which moves the median unmistakably; a handful of contention
    outliers do not."""
    from host import TestHost
    from world_kernel import WorldKernel

    k = WorldKernel("paint/world/kernel_spike_fixture.planes", host=TestHost())
    k.start()
    baseline = sorted(k.step()[1] for _ in range(40))
    baseline_median = baseline[len(baseline) // 2]

    class SlowSink:
        def consume(self, delta, elapsed):
            time.sleep(0.05)  # 50ms -- far larger than any real step cost here

    slow = SlowSink()
    measured_while_sinking_slowly = []
    for _ in range(40):
        delta, elapsed = k.step()
        measured_while_sinking_slowly.append(elapsed)
        slow.consume(delta, elapsed)  # deliberately AFTER, outside the timed call

    measured = sorted(measured_while_sinking_slowly)
    measured_median = measured[len(measured) // 2]
    # Comfortably below the ~50ms a real leak would add to every call;
    # comfortably above what contention noise does to a MEDIAN of 40.
    ceiling = max(baseline_median * 10, 0.005)
    assert measured_median < ceiling, (
        f"step()'s own elapsed MEDIAN grew to {measured_median*1000:.3f}ms "
        f"(baseline median {baseline_median*1000:.3f}ms, ceiling "
        f"{ceiling*1000:.3f}ms) with a 50ms sink attached after every call — "
        "sink cost may be leaking into the timed span")


# ========================================================= C. results completeness

def test_c_the_results_file_is_complete():
    """Every field build prompt §6 names, present and non-empty; no figure
    equal to a value hard-coded in the build prompt itself (the placeholder
    gate values, restated as if they were a measurement)."""
    assert os.path.exists(RESULTS_MD), (
        f"{RESULTS_MD} does not exist — run world_kernel_bench.py first")
    with open(RESULTS_MD, encoding="utf-8") as fh:
        text = fh.read()

    required_substrings = [
        "Machine specs", "CPU |", "cores |", "RAM |", "OS |",
        "Fixture profile", '"containedSubjects": 12',
        "Fixed-step rate:** 30 Hz",
        "Python (world_kernel.py)", "JavaScript (js/world_kernel.mjs)",
        "Recalibration statement (Sun-provisional)",
        "Sun-provisional",
        "Headline measured p95",
    ]
    missing = [s for s in required_substrings if s not in text]
    assert not missing, f"horizon-kernel-spike-results.md is missing: {missing}"

    # No invented figure: a machine-spec cell must not read "unknown"/empty,
    # and the recalibration line's own headline number must be a real
    # decimal, not a restatement of the 10.0/33.3 placeholder constants.
    headline_match = re.search(r"Headline measured p95\*\*.*?: \*\*([\d.]+) ms\*\*", text)
    assert headline_match, "no headline p95 figure found in the recalibration statement"
    headline_value = float(headline_match.group(1))
    assert headline_value not in (10.0, 33.3, 33.333), (
        f"headline p95 ({headline_value} ms) exactly equals a build-prompt "
        "placeholder constant — looks invented rather than measured")
    assert "unknown" not in re.search(r"## Machine specs.*?## Fixture profile", text, re.S).group(0)


# ================================================================ D. read-only core

def test_d_the_read_only_core_files_are_untouched():
    r = subprocess.run(
        ["git", "diff", "--name-only", "main", "--", *READ_ONLY_CORE],
        capture_output=True, text=True, cwd=REPO)
    changed = [line for line in r.stdout.splitlines() if line.strip()]
    assert not changed, f"read-only core files were touched: {changed}"


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

    report_path = os.path.join(REPO, "kernel-spike-verification.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("# Horizon Phase 1 engine-kernel spike — verification gate (§10.2)\n\n")
        fh.write("| assertion | result |\n|---|---|\n")
        for name, result in results_table:
            fh.write(f"| {name} | {result} |\n")
        fh.write(f"\n{len(tests) - len(fails)}/{len(tests)} passing.\n")
        c_failed = any(n.startswith("test_c_") and r != "PASS" for n, r in results_table)
        abcd_blocking_failed = any(
            (n.startswith("test_a_") or n.startswith("test_b_") or n.startswith("test_d_"))
            and r != "PASS" for n, r in results_table)
        fh.write("\nA/B/D failure blocks the PR. " + (
            "**A/B/D FAILED — BLOCKING.**\n" if abcd_blocking_failed else "A/B/D all pass.\n"))
        fh.write("C failure blocks unless the architect accepts a documented gap. " + (
            "**C FAILED.**\n" if c_failed else "C passes.\n"))
    print(f"wrote {report_path}")

    sys.exit(1 if fails else 0)
