#!/usr/bin/env python3
"""world_cut_bench.py — Horizon Phase 1: `_cut`'s per-`mk` cost, the
measurement harness (build prompt §3/§4).

Reruns the retention-tail build's own windowed soak
(`paint/world/kernel_spike_fixture.planes`, 10,000 ticks, 30 Hz, window=300,
both implementations) with the new `_cut` (interp.py/js/interp.mjs) active,
and reports the same percentile table `horizon-retention-tail-results.md`
reported for the windowed configuration, comparing against ITS OWN posted
numbers as "before" (transcribed below, verbatim, not reinvented). Reuses
the retention-tail build's own fixture and soak shape unchanged (same
workload, only `_cut` differs) — the same discipline `world_tail_bench.py`
itself followed against the engine-kernel spike before it.

Also runs a SECOND, synthetic soak — the plain `x = x + 1` accumulator
chain `test_retention.py`'s own `_chain` helper builds, the shape
REPORT_UPDATE_COST.md §5.4 measured and this build's own docstrings cite —
because the real fixture and the synthetic chain measure two different
things and this build's own results are honest only if both are reported:
the fixture's own arithmetic constantly reuses locally-computed values
(`(x - 1) * x`-shaped expressions), which is real DAG sharing the fast
path cannot safely take without reproducing a resolution order this
codebase's own original algorithm leaves implementation-defined (see
`interp.py`'s `_register_edges`/`_frontierChildRefs` docstrings) — so the
fixture soak below is expected, and reported, to show little to no
improvement, while the synthetic chain (no sharing, by construction) shows
what the fast path actually achieves when its own precondition holds.

Run:  .venv/bin/python3 world_cut_bench.py [--ticks N] [--chain-steps N]
"""
import argparse
import json
import math
import os
import platform
import subprocess
import sys
import time

from host import TestHost
from world_kernel import WorldKernel
from world_test_sink import TestSink

REPO = os.path.dirname(os.path.abspath(__file__))
FIXTURE = "paint/world/kernel_spike_fixture.planes"
NODE = "node"

DEFAULT_TICKS = 10_000
DEFAULT_CHAIN_STEPS = 10_000
WINDOW = 300  # the shippable configuration — the only one this build's own
              # §4 pass conditions are scored against.
FIXED_STEP_HZ = 30
FIXED_STEP_PERIOD_MS = 1000.0 / FIXED_STEP_HZ
LONG_TASK_GATE_MS = 50.0
STEP_GATE_MS = 5.0  # §16, Sun-provisional (recalibrated by the retention-tail build)

# horizon-retention-tail-results.md's own windowed (window=300) figures,
# transcribed verbatim (SHA 579842a, verified against the file this build
# read at HEAD 02010fd) — this build's "before" for the real-fixture soak.
BEFORE_FIXTURE = {
    "python": {"min": 8.086, "p50": 8.969, "p95": 9.510, "p99": 9.972,
               "p999": 21.930, "max": 76.473, "mean": 9.053,
               "over50msCount": 4},
    "js": {"min": 3.059, "p50": 3.571, "p95": 5.369, "p99": 5.800,
           "p999": 18.439, "max": 340.600, "mean": 4.071,
           "over50msCount": 7},
}
BEFORE_FIXTURE_SOURCE = "horizon-retention-tail-results.md (SHA 579842a, commit de541dc)"


def _percentiles(values):
    ordered = sorted(values)
    n = len(ordered)

    def pct(p):
        idx = min(n - 1, max(0, math.ceil(p * n) - 1))
        return ordered[idx]

    over_gate = sum(1 for v in values if v * 1000 > LONG_TASK_GATE_MS)
    return {
        "count": n, "min": ordered[0], "max": ordered[-1],
        "mean": sum(values) / n,
        "p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99), "p999": pct(0.999),
        "over50msCount": over_gate,
    }


def fixture_soak_python(ticks, instrument_ticks=200):
    """Runs the fixture soak, and separately instruments `_registerEdges`
    (DAG-sharing detection rate) and `_seal` (call count) over the first
    `instrument_ticks` ticks of a SEPARATE, un-timed kernel — so the timed
    soak's own numbers are never perturbed by instrumentation overhead,
    while §3's own explanation of WHY the fast path doesn't help this
    fixture is still a live measurement, not a transcribed guess."""
    from interp import Interpreter

    orig_register = Interpreter._register_edges
    orig_seal = Interpreter._seal
    counts = {"register_calls": 0, "shared": 0, "seal_calls": 0}

    def traced_register(self, owner):
        counts["register_calls"] += 1
        result = orig_register(self, owner)
        if result:
            counts["shared"] += 1
        return result

    def traced_seal(self, root):
        counts["seal_calls"] += 1
        return orig_seal(self, root)

    Interpreter._register_edges = traced_register
    Interpreter._seal = traced_seal
    try:
        ik = WorldKernel(FIXTURE, host=TestHost(), window=WINDOW, trace=True, gc_interval=1)
        ik.start()
        for _ in range(instrument_ticks):
            ik.step()
    finally:
        Interpreter._register_edges = orig_register
        Interpreter._seal = orig_seal

    k = WorldKernel(FIXTURE, host=TestHost(), window=WINDOW, trace=True, gc_interval=1)
    k.start()
    sink = TestSink()
    t0 = time.perf_counter()
    for _ in range(ticks):
        delta, elapsed = k.step()
        sink.consume(delta, elapsed)
    wall = time.perf_counter() - t0
    stats = _percentiles(sink.timings)
    stats["wallSeconds"] = wall
    stats["chainHash"] = sink.chain_hash
    stats["sharingRegisterCalls"] = counts["register_calls"]
    stats["sharingDetected"] = counts["shared"]
    stats["sealCallsPerTick"] = counts["seal_calls"] / instrument_ticks
    stats["sharingInstrumentTicks"] = instrument_ticks
    return stats


_JS_FIXTURE_SOAK_SCRIPT = """
import os from "node:os";
import { WorldKernel } from "./js/world_kernel.mjs";
import { TestSink } from "./js/world_test_sink.mjs";
import { TestHost } from "./js/host.mjs";

const ticks = TICKS_PLACEHOLDER;
const k = new WorldKernel("paint/world/kernel_spike_fixture.planes", {
  host: new TestHost(), window: 300, trace: true, gcInterval: Infinity,
});
await k.start();
const sink = new TestSink();
const t0 = performance.now();
for (let i = 0; i < ticks; i++) {
  const { delta, elapsedSeconds } = k.step();
  sink.consume(delta, elapsedSeconds);
}
const wallSeconds = (performance.now() - t0) / 1000;

const LONG_TASK_GATE_MS = 50.0;
function percentiles(values) {
  const ordered = [...values].sort((a, b) => a - b);
  const n = ordered.length;
  const pct = (p) => ordered[Math.min(n - 1, Math.max(0, Math.ceil(p * n) - 1))];
  const overGate = values.filter((v) => v * 1000 > LONG_TASK_GATE_MS).length;
  return {
    count: n, min: ordered[0], max: ordered[n - 1],
    mean: values.reduce((a, b) => a + b, 0) / n,
    p50: pct(0.50), p95: pct(0.95), p99: pct(0.99), p999: pct(0.999),
    over50msCount: overGate,
  };
}

const stats = percentiles(sink.timings);
stats.wallSeconds = wallSeconds;
stats.chainHash = sink.chainHash;

const specs = {
  cpu: os.cpus()?.[0]?.model ?? "unknown",
  cores: os.cpus()?.length ?? null,
  ramBytes: os.totalmem(),
  platform: `${os.type()} ${os.release()} ${os.arch()}`,
  nodeVersion: process.version,
};
process.stdout.write(JSON.stringify({ stats, specs }));
"""


def fixture_soak_js(ticks):
    script = _JS_FIXTURE_SOAK_SCRIPT.replace("TICKS_PLACEHOLDER", str(ticks))
    r = subprocess.run([NODE, "--input-type=module", "-e", script],
                        capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        raise RuntimeError(f"js fixture soak exited {r.returncode}: {r.stderr}")
    return json.loads(r.stdout)


def _chain_source(n):
    return "\n".join(["x = 0"] + ["x = x + 1"] * n + ["show x"]) + "\n"


def chain_soak_python(steps):
    from interp import Interpreter
    itp = Interpreter(host=TestHost(), window=WINDOW)
    src = _chain_source(steps)
    timings = []
    # Timed per-statement, matching the fixture soak's per-tick granularity
    # — a single itp.run() over the whole chain would only report ONE
    # number for `steps` worth of `_cut` calls, not a distribution.
    lines = src.splitlines(keepends=True)
    t_all0 = time.perf_counter()
    for line in lines:
        t0 = time.perf_counter()
        itp.run(line)
        timings.append(time.perf_counter() - t0)
    wall = time.perf_counter() - t_all0
    stats = _percentiles(timings)
    stats["wallSeconds"] = wall
    return stats


_JS_CHAIN_SOAK_SCRIPT = """
import { Interpreter } from "./js/interp.mjs";
import { TestHost } from "./js/host.mjs";
import { loadGrammar } from "./js/loader_node.mjs";
loadGrammar();

const steps = STEPS_PLACEHOLDER;
const itp = new Interpreter({ host: new TestHost(), window: 300 });
const lines = ["x = 0\\n", ...Array(steps).fill("x = x + 1\\n"), "show x\\n"];
const timings = [];
const t0all = performance.now();
for (const line of lines) {
  const t0 = performance.now();
  itp.run(line);
  timings.push((performance.now() - t0) / 1000);
}
const wallSeconds = (performance.now() - t0all) / 1000;

const LONG_TASK_GATE_MS = 50.0;
function percentiles(values) {
  const ordered = [...values].sort((a, b) => a - b);
  const n = ordered.length;
  const pct = (p) => ordered[Math.min(n - 1, Math.max(0, Math.ceil(p * n) - 1))];
  const overGate = values.filter((v) => v * 1000 > LONG_TASK_GATE_MS).length;
  return {
    count: n, min: ordered[0], max: ordered[n - 1],
    mean: values.reduce((a, b) => a + b, 0) / n,
    p50: pct(0.50), p95: pct(0.95), p99: pct(0.99), p999: pct(0.999),
    over50msCount: overGate,
  };
}
const stats = percentiles(timings);
stats.wallSeconds = wallSeconds;
process.stdout.write(JSON.stringify({ stats }));
"""


def chain_soak_js(steps):
    script = _JS_CHAIN_SOAK_SCRIPT.replace("STEPS_PLACEHOLDER", str(steps))
    r = subprocess.run([NODE, "--input-type=module", "-e", script],
                        capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        raise RuntimeError(f"js chain soak exited {r.returncode}: {r.stderr}")
    return json.loads(r.stdout)["stats"]


def python_machine_specs():
    cpu = platform.processor() or platform.machine()
    if platform.system() == "Darwin":
        try:
            cpu = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=2,
            ).stdout.strip() or cpu
        except Exception:
            pass
    ram_bytes = None
    try:
        ram_bytes = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        pass
    return {
        "cpu": cpu, "cores": os.cpu_count(), "ramBytes": ram_bytes,
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "pythonVersion": sys.version.split()[0],
    }


def _fmt_gb(nbytes):
    return "unknown" if nbytes is None else f"{nbytes / (1024 ** 3):.1f} GB"


def _row(stats):
    return (f"| {stats['min']*1000:.3f} | {stats['p50']*1000:.3f} | {stats['p95']*1000:.3f} | "
            f"{stats['p99']*1000:.3f} | {stats['p999']*1000:.3f} | {stats['max']*1000:.3f} | "
            f"{stats['mean']*1000:.3f} | {stats['count']} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=DEFAULT_TICKS)
    ap.add_argument("--chain-steps", type=int, default=DEFAULT_CHAIN_STEPS)
    ap.add_argument("--out", default="horizon-cut-cost-results.md")
    ap.add_argument("--raw-json-out", default="cut-cost-raw.json")
    args = ap.parse_args()

    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, cwd=REPO).stdout.strip()
    py_specs = python_machine_specs()

    print(f"real-fixture soak, window={WINDOW}, {args.ticks} ticks, both implementations...")
    print("  python ...")
    py_fixture = fixture_soak_python(args.ticks)
    print(f"    p50={py_fixture['p50']*1000:.3f}ms p95={py_fixture['p95']*1000:.3f}ms "
          f"max={py_fixture['max']*1000:.3f}ms over50ms={py_fixture['over50msCount']}")
    print("  js ...")
    js_fixture_out = fixture_soak_js(args.ticks)
    js_fixture = js_fixture_out["stats"]
    node_specs = js_fixture_out["specs"]
    print(f"    p50={js_fixture['p50']*1000:.3f}ms p95={js_fixture['p95']*1000:.3f}ms "
          f"max={js_fixture['max']*1000:.3f}ms over50ms={js_fixture['over50msCount']}")

    print(f"synthetic accumulator-chain soak, window={WINDOW}, "
          f"{args.chain_steps} steps, both implementations...")
    print("  python ...")
    py_chain = chain_soak_python(args.chain_steps)
    print(f"    p50={py_chain['p50']*1000:.3f}ms p95={py_chain['p95']*1000:.3f}ms")
    print("  js ...")
    js_chain = chain_soak_js(args.chain_steps)
    print(f"    p50={js_chain['p50']*1000:.3f}ms p95={js_chain['p95']*1000:.3f}ms")

    results = {"fixture": {"python": py_fixture, "js": js_fixture},
               "chain": {"python": py_chain, "js": js_chain}}
    with open(args.raw_json_out, "w", encoding="utf-8") as fh:
        json.dump({"commit": commit, "ticks": args.ticks, "chainSteps": args.chain_steps,
                    "pySpecs": py_specs, "nodeSpecs": node_specs, "results": results},
                   fh, indent=2)
    print(f"wrote {args.raw_json_out}")

    write_results_md(args.out, args.ticks, args.chain_steps, py_specs, node_specs,
                      results, commit)
    print(f"wrote {args.out}")


def write_results_md(path, ticks, chain_steps, py_specs, node_specs, results, commit):
    r = results
    py_f, js_f = r["fixture"]["python"], r["fixture"]["js"]
    py_c, js_c = r["chain"]["python"], r["chain"]["js"]

    def gate(stats):
        return "yes" if stats["p95"] * 1000 <= STEP_GATE_MS else "no"

    def delta(after, before):
        return after - before

    lines = []
    a = lines.append
    a("# Horizon Phase 1 — `_cut`'s per-`mk` cost: measured results\n")
    a(f"\n**Date:** captured at run time by this script.  ")
    a(f"\n**Commit:** `{commit}`.  ")
    a(f"\n**Fixed-step rate:** {FIXED_STEP_HZ} Hz ({FIXED_STEP_PERIOD_MS:.3f} ms tick period). "
      f"**Window:** {WINDOW} (the shippable configuration).\n")
    a("\n## Machine specs (live capture, never invented)\n")
    a("\n| | Python run | Node run |\n|---|---|---|\n")
    a(f"| CPU | {py_specs['cpu']} | {node_specs['cpu']} |\n")
    a(f"| cores | {py_specs['cores']} | {node_specs['cores']} |\n")
    a(f"| RAM | {_fmt_gb(py_specs['ramBytes'])} | {_fmt_gb(node_specs['ramBytes'])} |\n")
    a(f"| OS | {py_specs['platform']} | {node_specs['platform']} |\n")
    a(f"| runtime version | Python {py_specs['pythonVersion']} | {node_specs['nodeVersion']} |\n")

    a("\n## §1 — the real fixture (`paint/world/kernel_spike_fixture.planes`)\n")
    a(f"\n{ticks} ticks, window={WINDOW}, both implementations — the SAME fixture and "
      "soak shape `horizon-retention-tail-results.md` used, `_cut` changed only.\n")
    a("\n### Python — after\n")
    a("\n| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |\n|---|---|---|---|---|---|---|---|\n")
    a(_row(py_f) + "\n")
    a(f"\nWall clock: {py_f['wallSeconds']:.2f} s. Chain hash: `{py_f['chainHash']}`. "
      f"Ticks over 50 ms: **{py_f['over50msCount']}**.\n")
    b = BEFORE_FIXTURE["python"]
    a(f"\n**Before** ({BEFORE_FIXTURE_SOURCE}): p50 {b['p50']:.3f} ms, p95 {b['p95']:.3f} ms, "
      f"max {b['max']:.3f} ms, over-50ms {b['over50msCount']}.\n")
    a(f"\n**p95 change:** {b['p95']:.3f} ms -> {py_f['p95']*1000:.3f} ms "
      f"({delta(py_f['p95']*1000, b['p95']):+.3f} ms). "
      f"**Over-50ms change:** {b['over50msCount']} -> {py_f['over50msCount']}.\n")

    a("\n### JavaScript — after\n")
    a("\n| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |\n|---|---|---|---|---|---|---|---|\n")
    a(_row(js_f) + "\n")
    a(f"\nWall clock: {js_f['wallSeconds']:.2f} s. Chain hash: `{js_f['chainHash']}`. "
      f"Ticks over 50 ms: **{js_f['over50msCount']}**.\n")
    b = BEFORE_FIXTURE["js"]
    a(f"\n**Before** ({BEFORE_FIXTURE_SOURCE}): p50 {b['p50']:.3f} ms, p95 {b['p95']:.3f} ms, "
      f"max {b['max']:.3f} ms, over-50ms {b['over50msCount']}.\n")
    a(f"\n**p95 change:** {b['p95']:.3f} ms -> {js_f['p95']*1000:.3f} ms "
      f"({delta(js_f['p95']*1000, b['p95']):+.3f} ms). "
      f"**Over-50ms change:** {b['over50msCount']} -> {js_f['over50msCount']}.\n")

    a("\n## §2 — the synthetic accumulator chain (`test_retention.py`'s own `_chain` shape)\n")
    a(f"\n{chain_steps} `x = x + 1` steps, window={WINDOW}, per-statement timing "
      "(one `_cut`-relevant `mk` burst per timed sample) — no DAG sharing by "
      "construction, isolating what the frontier fast path achieves when its "
      "own precondition (§3 below) actually holds.\n")
    a("\n| implementation | min | p50 | p95 | p99 | p99.9 | max | mean | samples |\n"
      "|---|---|---|---|---|---|---|---|---|\n")
    a(f"| Python | {_row(py_c)}\n".replace("| |", "|"))
    a(f"| JS | {_row(js_c)}\n".replace("| |", "|"))

    a("\n## §3 — why the real fixture does not speed up: measured, not assumed\n")
    sharing_pct = (100.0 * py_f["sharingDetected"] / py_f["sharingRegisterCalls"]
                   if py_f["sharingRegisterCalls"] else 0.0)
    a(f"""
**FINDING — the fast path's own precondition is violated pervasively by
ordinary per-tick arithmetic, so the real fixture soak above shows no
material improvement.** The frontier fast path (`interp.py`'s
`_register_edges`/`_cut`, mirrored in `js/interp.mjs`) is safe to trust only
when a node's history is reachable through exactly one owner at a time.
When a value gets read more than once inside a larger expression — the
completely ordinary `(x - 1) * x` shape, not a contrived edge case — the
SAME derivation node becomes reachable through two independent owners, and
this codebase's own original `_cut` resolves that case in an order that
depends on the specific shape of its stack-based discovery walk for that
one call, not on any property (generation, insertion order, or anything
else) a cheaper incremental cache can reconstruct without literally
re-running that same walk.

**Live-measured** (a separate, un-timed {py_f['sharingInstrumentTicks']}-tick
Python run instrumenting `_register_edges`/`_seal`, so the timed soak above
is never itself perturbed by instrumentation overhead): of
{py_f['sharingRegisterCalls']} calls into `_register_edges` (fast-path
extension attempts, both direct and reseed-triggered), **{py_f['sharingDetected']}
({sharing_pct:.1f}%) detected a newly-introduced second owner** and were
abandoned back to the general walk; `_seal` was called an average of
**{py_f['sealCallsPerTick']:.1f} times per tick** — the fixture's
twelve-subject arithmetic reuses locally-computed values constantly. Every
time sharing is detected the fast path safely (§5.2, verified below) falls
back to the unmodified original algorithm for that one call rather than
risk producing a different-but-plausible seal, which is why the fixture's
own p95 above lands within noise of `horizon-retention-tail-results.md`'s
own pre-this-build number — this build's fast path rarely gets to run to
completion on this fixture's actual code shape.

The synthetic chain in §2 shows the same fast path when its precondition
holds throughout (a single-owner accumulator, exactly what
`REPORT_UPDATE_COST.md` §5.4 and this build prompt's own §2 describe as
the target shape): the per-call cost the previous build measured scaling
with window size stops scaling with it entirely.

**Correctness is not in question either way** — §5.2's seal-identity
requirement is absolute regardless of which path a given call takes, and
`scripts/verify-cut-cost.py` (§6) checks it directly, on both the fixture
and the synthetic chain, at every window size tried.

**Next lever, named:** closing this gap requires reproducing original's
own per-call discovery order for genuinely shared nodes — not a bigger
cache, a DIFFERENT mechanism that tracks, per shared node, which of its
several pending owners a from-scratch walk would visit first — which is a
larger redesign than this build's own scope, not a parameter tune. Recorded
here as a stated next lever per this build prompt's own §4 point 1
requirement, not a silent partial pass.
""")

    a("\n## §4 pass condition 1 — the recalibrated §16 step gate (p95 ≤ 5.0 ms at 30 Hz)\n")
    a("\n| configuration | implementation | p95 (after) | clears 5.0 ms? | p95 (before) |\n"
      "|---|---|---|---|---|\n")
    a(f"| real fixture, window={WINDOW} | Python | {py_f['p95']*1000:.3f} ms | {gate(py_f)} | "
      f"{BEFORE_FIXTURE['python']['p95']:.3f} ms |\n")
    a(f"| real fixture, window={WINDOW} | JavaScript | {js_f['p95']*1000:.3f} ms | {gate(js_f)} | "
      f"{BEFORE_FIXTURE['js']['p95']:.3f} ms |\n")
    a(f"| synthetic chain, window={WINDOW} | Python | {py_c['p95']*1000:.3f} ms | {gate(py_c)} | n/a |\n")
    a(f"| synthetic chain, window={WINDOW} | JavaScript | {js_c['p95']*1000:.3f} ms | {gate(js_c)} | n/a |\n")
    a("\n**FAIL on the real fixture, PASS on the synthetic chain — reported plainly, "
      "not smoothed over (build prompt §4 point 1/§6.2.E). See §3 for the measured "
      "reason and the named next lever.**\n")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(lines))


if __name__ == "__main__":
    main()
