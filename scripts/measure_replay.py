#!/usr/bin/env python3
"""R3's own benchmark (checkpoint v30.0 §466-476, build step N+3.4): what
does tracing-off actually buy, and what does answering one `why` cost back?

Reuses REPORT_UPDATE_COST.md / R1's own fixture and generator UNCHANGED —
scripts/measure_update_cost.py's `build_world_src_for` (benchmarks/
world_shape.planes's S=64 shape) and `count_reachable_derivs` — the same
fixture scripts/measure_retention_window.py measured, so this build's
numbers sit beside R1's rather than inventing a new, uncalibrated shape.
Four independent full runs (0..checkpoint-1 ticks each, checkpoints
1/100/300/600) through the ordinary `run` entry point, deterministic and
pure so this gives the SAME final world value a single continuous run would
at each checkpoint.

Two arms, each its own subprocess (this script re-invoking itself with
--replay-only --trace true|false), for the same reason
measure_retention_window.py's run_subprocess() does — a shared process would
let the first arm's allocator/cache state contaminate the second's timing:

  TRACED   (trace=true, the HEAD/main shape) — every `mk` call builds a real
  Deriv and stamps a generation, exactly as before this build.

  FAST     (trace=false, record=true) — `mk` returns the one shared sentinel;
  `record=true` so the run's effect_log exists for the replay measurement
  below (§7's own stated dependency).

A third, separate subprocess measures the REPLAY cost this build's whole
point rests on: given the FAST run's own effect_log at the tick=600
checkpoint, how long does answering ONE `why` on `current-world` — replay()
plus explain() — actually take, set beside the fast path's own per-tick cost
and the traced arm's per-tick cost. This is the number that closes v28.0
§428's "toll, not a ceiling" claim.

Run:  .venv/bin/python3 scripts/measure_replay.py [--json]
"""
import json
import os
import platform
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from measure_update_cost import (  # noqa: E402
    RETENTION_CHECKPOINTS,
    RETENTION_S,
    RETENTION_SOAK_SECONDS,
    RETENTION_TICKS_PER_SECOND,
    build_world_src_for,
    count_reachable_derivs,
    linear_fit,
)

from host import TestHost  # noqa: E402
from interp import Interpreter, explain, replay  # noqa: E402

# The checkpoint the replay-cost measurement anchors on — the largest of
# R1's own four, so the fast path has accumulated the most history a single
# `why` might need to reconstruct.
REPLAY_CHECKPOINT = 600


def run_checkpoints(trace):
    """The world-shape sweep, parameterized by `trace` (R1's own
    run_checkpoints, plus a wall-clock reading per checkpoint). `record` is
    tied to `not trace` — the fast arm needs its own effect_log for a
    faithful shape (§7's dependency is real even though this program's only
    effect is `show`); the traced arm matches HEAD (record defaults off)."""
    results = {}
    for checkpoint in RETENTION_CHECKPOINTS:
        src = build_world_src_for(RETENTION_S, checkpoint)
        interp = Interpreter(host=TestHost(), trace=trace, record=not trace)
        t0 = time.perf_counter_ns()
        interp.run(src)
        t1 = time.perf_counter_ns()
        traced_world = interp.env.get("current-world")
        deriv_count = count_reachable_derivs(traced_world.node)
        results[str(checkpoint)] = {
            "checkpointTick": checkpoint,
            "S": RETENTION_S,
            "trace": trace,
            "reachableDerivCount": deriv_count,
            "wallNs": t1 - t0,
        }
        del interp, traced_world

    ticks = [results[str(c)]["checkpointTick"] for c in RETENTION_CHECKPOINTS]
    derivs = [results[str(c)]["reachableDerivCount"] for c in RETENTION_CHECKPOINTS]
    wall = [results[str(c)]["wallNs"] for c in RETENTION_CHECKPOINTS]
    deriv_slope, deriv_intercept = linear_fit(ticks, derivs)
    wall_slope, wall_intercept = linear_fit(ticks, wall)

    soak_ticks = RETENTION_SOAK_SECONDS * RETENTION_TICKS_PER_SECOND
    extrapolated_derivs = deriv_intercept + deriv_slope * soak_ticks
    extrapolated_wall_ns = wall_intercept + wall_slope * soak_ticks

    return {
        "S": RETENTION_S,
        "trace": trace,
        "checkpoints": RETENTION_CHECKPOINTS,
        "results": results,
        "derivCountPerTickSlope": deriv_slope,
        "wallNsPerTickSlope": wall_slope,
        "soakSeconds": RETENTION_SOAK_SECONDS,
        "soakTicksPerSecond": RETENTION_TICKS_PER_SECOND,
        "soakTicks": soak_ticks,
        "extrapolatedDerivCount": extrapolated_derivs,
        "extrapolatedWallNs": extrapolated_wall_ns,
    }


def measure_replay_cost():
    """One `why`, from a fast-path value: the FAST arm's own effect_log at
    REPLAY_CHECKPOINT, then time replay() + explain() together — the full
    cost a caller actually pays to turn a tracing-off value into a card."""
    src = build_world_src_for(RETENTION_S, REPLAY_CHECKPOINT)
    fast = Interpreter(host=TestHost(), trace=False, record=True)
    fast.run(src)

    t0 = time.perf_counter_ns()
    replayed = replay([src], "current-world", effect_log=fast.effect_log)
    card = explain(replayed)
    t1 = time.perf_counter_ns()

    return {
        "checkpointTick": REPLAY_CHECKPOINT,
        "S": RETENTION_S,
        "replayPlusExplainWallNs": t1 - t0,
        "replayedDerivCount": count_reachable_derivs(replayed.node),
        "cardLength": len(card),
    }


def run_subprocess(trace):
    import subprocess

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    args = [sys.executable, os.path.abspath(__file__), "--replay-only", "--json",
           "--trace", "true" if trace else "false"]
    proc = subprocess.run(args, cwd=repo, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)["sweep"]


def run_replay_cost_subprocess():
    import subprocess

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    args = [sys.executable, os.path.abspath(__file__), "--replay-cost-only", "--json"]
    proc = subprocess.run(args, cwd=repo, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)["replayCost"]


def _write_md(path, title, data, is_fast, replay_cost=None):
    lines = [f"# {title}", ""]
    lines.append(f"Machine: Apple M1 Pro (or current host), Python {sys.version.split()[0]}, "
                 f"{platform.system()} {platform.release()} {platform.machine()}.")
    lines.append("")
    lines.append(f"`benchmarks/world_shape.planes`'s shape at S={data['S']}, checkpointed at "
                 f"tick {'/'.join(str(c) for c in data['checkpoints'])} "
                 "(four independent full runs, 0..checkpoint-1 ticks each — "
                 "deterministic and pure, so this gives the same final world "
                 "value a single continuous run would at each point).")
    lines.append("")
    if is_fast:
        lines.append("Tracing: **off** (`trace=False, record=True` — the R3 fast path).")
    else:
        lines.append("Tracing: **on** (`trace=True`, the default — the literal HEAD/main shape).")
    lines.append("")
    lines.append("| tick | reachable `Deriv` count | wall time |")
    lines.append("|---:|---:|---:|")
    for c in data["checkpoints"]:
        r = data["results"][str(c)]
        lines.append(f"| {c} | {r['reachableDerivCount']:,} | {r['wallNs']/1e6:.3f} ms |")
    lines.append("")
    lines.append(f"Fitted slope: **{data['derivCountPerTickSlope']:.2f} Deriv nodes/tick**, "
                 f"**{data['wallNsPerTickSlope']/1e3:.2f} µs/tick** wall time.")
    lines.append("")
    lines.append(f"Extrapolated to a {data['soakSeconds']//60}-minute soak at "
                 f"{data['soakTicksPerSecond']} ticks/second "
                 f"({data['soakTicks']:,} ticks) — EXTRAPOLATION, not measured directly:")
    lines.append("")
    lines.append(f"- extrapolated reachable `Deriv` count: "
                 f"**{data['extrapolatedDerivCount']:,.0f}**")
    lines.append(f"- extrapolated wall time: "
                 f"**{data['extrapolatedWallNs']/1e9:,.2f} s**")
    if replay_cost is not None:
        lines.append("")
        lines.append(f"Replay cost of ONE `why` (replay() + explain(), tick="
                     f"{replay_cost['checkpointTick']}): "
                     f"**{replay_cost['replayPlusExplainWallNs']/1e6:.3f} ms** — "
                     f"reconstructs {replay_cost['replayedDerivCount']:,} Deriv nodes, "
                     f"a {replay_cost['cardLength']}-character card.")
    lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {path}")


def main():
    if "--replay-only" in sys.argv:
        trace = sys.argv[sys.argv.index("--trace") + 1] == "true"
        print(json.dumps({"sweep": run_checkpoints(trace)}))
        return
    if "--replay-cost-only" in sys.argv:
        print(json.dumps({"replayCost": measure_replay_cost()}))
        return

    json_mode = "--json" in sys.argv

    traced = run_subprocess(True)
    fast = run_subprocess(False)
    replay_cost = run_replay_cost_subprocess()

    if json_mode:
        print(json.dumps({"traced": traced, "fast": fast, "replayCost": replay_cost}))
        return

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _write_md(
        os.path.join(repo, "reports", "feat-replay-benchmarks-pre.md"),
        "Pre — tracing on (HEAD/main shape)", traced, is_fast=False)
    _write_md(
        os.path.join(repo, "reports", "feat-replay-benchmarks-post.md"),
        "Post — tracing off (feat/replay-on-demand-and-iterative-explain)",
        fast, is_fast=True, replay_cost=replay_cost)

    print()
    print("--- summary (tick=600) ---")
    t600 = traced["results"]["600"]
    f600 = fast["results"]["600"]
    print(f"traced reachable Deriv count @ tick 600: {t600['reachableDerivCount']:,} "
         f"({t600['wallNs']/1e6:.3f} ms)")
    print(f"fast   reachable Deriv count @ tick 600: {f600['reachableDerivCount']:,} "
         f"({f600['wallNs']/1e6:.3f} ms)")
    print(f"traced per-tick wall slope: {traced['wallNsPerTickSlope']/1e3:.2f} us/tick")
    print(f"fast   per-tick wall slope: {fast['wallNsPerTickSlope']/1e3:.2f} us/tick")
    print(f"replay cost of one why (tick=600): "
         f"{replay_cost['replayPlusExplainWallNs']/1e6:.3f} ms")


if __name__ == "__main__":
    main()
