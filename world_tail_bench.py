#!/usr/bin/env python3
"""world_tail_bench.py — the retention-tail measurement harness (Horizon
Phase 1: the retention tail, build prompt §3/§4).

Reruns the engine-kernel spike's own fixture soak
(`paint/world/kernel_spike_fixture.planes`, 10,000 ticks, 30 Hz, both
retention configurations, both implementations) with the Rungs 1-2 changes
active (`world_kernel.py`'s `gc.disable()`/`gc.collect()`/`gc.freeze()`
tick-boundary maintenance; `js/world_kernel.mjs`'s `global.gc()`
tick-boundary call; `interp.py`/`js/interp.mjs`'s streamed `_seal`
fingerprint hash), and reports the same percentile table
`horizon-kernel-spike-results.md` reported, plus the tail-gate figures
(max pause, over-50ms count) build prompt §4 asks this build to report.

Structurally the same harness as `world_kernel_bench.py` (the spike's own
script, PR #87) — same fixture, same soak length, same rate, same
percentile/half-split math — reused deliberately (build prompt §3: "It
reuses the spike's fixture unchanged so the before/after diff is honest —
same workload, only the collection strategy differs"), not reimplemented.

Also re-runs `scripts/measure_update_cost.py`/`.mjs` (unmodified by this
build; the with/plus copy path Criterion B measures is untouched by Rungs
1-2) to get a LIVE with/plus-copy-cost number against A-Q3's recalibrated
1.0 ms/tick sub-threshold (build prompt §4 point 3, §8) — accepting a
pre-captured `--json` output via `--update-cost-py-json`/
`--update-cost-js-json` so a long ladder run does not have to repeat
inside the same invocation that already ran it once.

Run:  .venv/bin/python3 world_tail_bench.py [--ticks N] [--gc-interval N]
      [--update-cost-py-json PATH] [--update-cost-js-json PATH]
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
BOUNDED_WINDOW = 300  # matches world_kernel_bench.py's own bounded config
FIXED_STEP_HZ = 30
FIXED_STEP_PERIOD_MS = 1000.0 / FIXED_STEP_HZ  # 33.3ms
LONG_TASK_GATE_MS = 50.0  # design doc §16: "zero tasks over 50 ms attributable to engine work"
RECALIBRATED_STEP_GATE_MS = 5.0  # this build's §16 recalibration (build prompt §1)
AQ3_SUB_THRESHOLD_MS = 1.0  # this build's A-Q3 recalibration (build prompt §1/§8)

CONFIGS = [
    {"key": "unbounded",
     "label": "window=None (unbounded retention, WorldRuntime's default)",
     "window": None},
    {"key": "bounded",
     "label": f"window={BOUNDED_WINDOW} (bounded retention)",
     "window": BOUNDED_WINDOW},
]

# The spike's own recorded "before" numbers (horizon-kernel-spike-results.md,
# commit 432900b84eb1e50548eadb33c8d17f9da807831d) — transcribed, not
# reinvented, so the before/after diff this build reports is against an
# already-live-measured baseline (build prompt §3). Every number below is
# copied verbatim from that file; this script's own output is what is fresh.
BEFORE = {
    "unbounded": {
        "python": {"p50": 1.344, "p95": 1.597, "max": 1574.678,
                    "maxFirstHalf": 668.696, "maxSecondHalf": 1574.678},
        "js": {"p50": 0.132, "p95": 0.220, "max": 133.893,
               "maxFirstHalf": 4.384, "maxSecondHalf": 133.893},
    },
    "bounded": {
        "python": {"p50": 8.862, "p95": 9.319, "max": 305.687,
                    "maxFirstHalf": 50.521, "maxSecondHalf": 305.687},
        "js": {"p50": 3.433, "p95": 5.216, "max": 188.000,
               "maxFirstHalf": 188.000, "maxSecondHalf": 153.806},
    },
}
BEFORE_SOURCE = ("horizon-kernel-spike-results.md "
                  "(commit 432900b84eb1e50548eadb33c8d17f9da807831d)")


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


def _half_split(values):
    n = len(values)
    first, second = values[: n // 2], values[n // 2 :]
    return {"firstHalf": _percentiles(first), "secondHalf": _percentiles(second)}


def python_soak(ticks, window, gc_interval):
    k = WorldKernel(FIXTURE, host=TestHost(), window=window, trace=True,
                     gc_interval=gc_interval)
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
    stats["halfSplit"] = _half_split(sink.timings)
    return stats


_JS_SOAK_SCRIPT = """
import os from "node:os";
import { WorldKernel } from "./js/world_kernel.mjs";
import { TestSink } from "./js/world_test_sink.mjs";
import { TestHost } from "./js/host.mjs";

const ticks = TICKS_PLACEHOLDER;
const windowArg = WINDOW_PLACEHOLDER;
const gcInterval = GC_INTERVAL_PLACEHOLDER;

const k = new WorldKernel("paint/world/kernel_spike_fixture.planes", {
  host: new TestHost(), window: windowArg, trace: true, gcInterval,
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
function halfSplit(values) {
  const n = values.length;
  return { firstHalf: percentiles(values.slice(0, Math.floor(n / 2))),
           secondHalf: percentiles(values.slice(Math.floor(n / 2))) };
}

const stats = percentiles(sink.timings);
stats.wallSeconds = wallSeconds;
stats.chainHash = sink.chainHash;
stats.halfSplit = halfSplit(sink.timings);

const specs = {
  cpu: os.cpus()?.[0]?.model ?? "unknown",
  cores: os.cpus()?.length ?? null,
  ramBytes: os.totalmem(),
  platform: `${os.type()} ${os.release()} ${os.arch()}`,
  nodeVersion: process.version,
  exposedGc: typeof global.gc === "function",
};

process.stdout.write(JSON.stringify({ stats, specs }));
"""


def js_soak(ticks, window, gc_interval):
    script = (_JS_SOAK_SCRIPT
              .replace("TICKS_PLACEHOLDER", str(ticks))
              .replace("WINDOW_PLACEHOLDER", "null" if window is None else str(window))
              .replace("GC_INTERVAL_PLACEHOLDER",
                       "Infinity" if gc_interval is None else str(gc_interval)))
    # --expose-gc: kept so js/world_kernel.mjs's opt-in gcInterval path is
    # available if a caller passes one — but the DEFAULT (gcInterval=
    # Infinity, this script's own --js-gc-interval default) never calls
    # global.gc() at all, because measuring it found forcing V8's
    # collector on any schedule costs more than leaving it alone (see
    # js/world_kernel.mjs's module docstring for the numbers). --expose-gc
    # is harmless to pass even when unused.
    r = subprocess.run(
        [NODE, "--expose-gc", "--input-type=module", "-e", script],
        capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        raise RuntimeError(f"js soak script exited {r.returncode}: {r.stderr}")
    return json.loads(r.stdout)


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
        "cpu": cpu,
        "cores": os.cpu_count(),
        "ramBytes": ram_bytes,
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "pythonVersion": sys.version.split()[0],
    }


def _fmt_gb(nbytes):
    if nbytes is None:
        return "unknown"
    return f"{nbytes / (1024 ** 3):.1f} GB"


def _stats_row(stats):
    return (f"| {stats['min']*1000:.3f} | {stats['p50']*1000:.3f} | {stats['p95']*1000:.3f} | "
            f"{stats['p99']*1000:.3f} | {stats['p999']*1000:.3f} | {stats['max']*1000:.3f} | "
            f"{stats['mean']*1000:.3f} | {stats['count']} |")


def run_update_cost(json_path, cmd, label):
    """Loads a pre-captured `--json` output if `json_path` is given (and
    exists), otherwise runs `cmd` fresh. Either way the number this build
    reports for A-Q3 is a genuine measurement of the CURRENT (post-Rungs-
    1-2) code — a pre-capture just avoids paying the ladder's own several-
    minute calibration cost twice inside one investigation."""
    if json_path and os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as fh:
            return json.load(fh), f"pre-captured at {json_path}"
    print(f"  running {label} fresh (no --json path given/found)...")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        raise RuntimeError(f"{label} exited {r.returncode}: {r.stderr}")
    return json.loads(r.stdout), "run fresh by this script"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=DEFAULT_TICKS)
    ap.add_argument("--gc-interval", type=int, default=1,
                     help="Python gc.collect()+gc.freeze() cadence, in ticks")
    ap.add_argument("--js-gc-interval", type=int, default=None,
                     help="JS global.gc() cadence, in ticks; default (None) "
                          "means never — measured to make things worse on "
                          "this fixture at every interval tried, see "
                          "js/world_kernel.mjs's module docstring")
    ap.add_argument("--out", default="horizon-retention-tail-results.md")
    # Not under .ci-logs/: scripts/run_suites.py treats that directory as
    # its own per-suite log scratch space and wipes non-suite-log files
    # from it on every gate run — a repo-root artifact, matching where
    # horizon-kernel-spike-results.md's own supporting files live, survives.
    ap.add_argument("--raw-json-out", default="retention-tail-raw.json")
    ap.add_argument("--update-cost-py-json", default=None)
    ap.add_argument("--update-cost-js-json", default=None)
    ap.add_argument("--skip-update-cost", action="store_true",
                     help="skip the A-Q3 with/plus copy-cost remeasure entirely")
    args = ap.parse_args()

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO,
    ).stdout.strip()

    py_specs = python_machine_specs()

    print(f"running {args.ticks}-tick soak, both configurations, both "
          f"implementations, gc_interval={args.gc_interval} (python), "
          f"js_gc_interval={args.js_gc_interval} (js, None=never)...")
    py_results = {}
    js_results = {}
    node_specs = None
    for cfg in CONFIGS:
        print(f"  python / {cfg['key']} ...")
        py_results[cfg["key"]] = python_soak(args.ticks, cfg["window"], args.gc_interval)
        s = py_results[cfg["key"]]
        print(f"    p50={s['p50']*1000:.3f}ms p95={s['p95']*1000:.3f}ms "
              f"max={s['max']*1000:.3f}ms over50ms={s['over50msCount']}")
        print(f"  js / {cfg['key']} ...")
        js_out = js_soak(args.ticks, cfg["window"], args.js_gc_interval)
        js_results[cfg["key"]] = js_out["stats"]
        node_specs = js_out["specs"]
        s = js_results[cfg["key"]]
        print(f"    p50={s['p50']*1000:.3f}ms p95={s['p95']*1000:.3f}ms "
              f"max={s['max']*1000:.3f}ms over50ms={s['over50msCount']}")

    results = {"python": py_results, "js": js_results}

    update_cost = None
    update_cost_sources = {}
    if not args.skip_update_cost:
        print("collecting A-Q3 with/plus copy-cost remeasure...")
        py_uc, py_src = run_update_cost(
            args.update_cost_py_json,
            [".venv/bin/python3", "scripts/measure_update_cost.py", "--json"],
            "scripts/measure_update_cost.py")
        js_uc, js_src = run_update_cost(
            args.update_cost_js_json,
            [NODE, "scripts/measure_update_cost.mjs", "--json"],
            "scripts/measure_update_cost.mjs")
        update_cost = {"python": py_uc, "js": js_uc}
        update_cost_sources = {"python": py_src, "js": js_src}
        print("  python source:", py_src)
        print("  js source:", js_src)

    raw_json_dir = os.path.dirname(args.raw_json_out)
    if raw_json_dir:
        os.makedirs(raw_json_dir, exist_ok=True)
    with open(args.raw_json_out, "w", encoding="utf-8") as fh:
        json.dump({
            "commit": commit, "ticks": args.ticks, "gcInterval": args.gc_interval,
            "jsGcInterval": args.js_gc_interval,
            "pySpecs": py_specs, "nodeSpecs": node_specs, "results": results,
            "updateCost": update_cost, "updateCostSources": update_cost_sources,
        }, fh, indent=2)
    print(f"wrote {args.raw_json_out}")

    write_results_md(args.out, args.ticks, args.gc_interval, args.js_gc_interval,
                      py_specs, node_specs, results, commit, update_cost,
                      update_cost_sources)
    print(f"wrote {args.out}")


def write_results_md(path, ticks, gc_interval, js_gc_interval, py_specs, node_specs,
                      results, commit, update_cost, update_cost_sources):
    from write_retention_tail_report import render
    text = render(ticks, gc_interval, js_gc_interval, py_specs, node_specs, results,
                   commit, update_cost, update_cost_sources, BEFORE, BEFORE_SOURCE,
                   CONFIGS, FIXED_STEP_HZ, FIXED_STEP_PERIOD_MS,
                   LONG_TASK_GATE_MS, RECALIBRATED_STEP_GATE_MS,
                   AQ3_SUB_THRESHOLD_MS, _stats_row, _fmt_gb)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


if __name__ == "__main__":
    main()
