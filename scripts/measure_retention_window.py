#!/usr/bin/env python3
"""R1's own benchmark (checkpoint v28.0 §441, build step 6): does a
retention window actually bound the growth REPORT_UPDATE_COST.md §5.4
measured as unbounded?

Reuses that report's own fixture and generator UNCHANGED —
scripts/measure_update_cost.py's `build_world_src_for` (benchmarks/
world_shape.planes's S=64 shape) and `count_reachable_derivs` — rather than
inventing a new one to measure against, so the "unbounded" arm here
reproduces §5.4's own numbers exactly instead of a new, uncalibrated shape.
Four independent full runs (0..checkpoint-1 ticks each, checkpoints
1/100/300/600) through the ordinary `run` entry point, deterministic and
pure so this gives the SAME final world value a single continuous run would
give at each checkpoint — identical method to run_retention_phase() there.

The one addition: an optional `window=` on the Interpreter. Two arms:

  UNBOUNDED — no window argument at all, the literal HEAD/main shape.
  Reproduces §5.4's numbers; run on this branch this is invariant 2's own
  proof against a real, complex program rather than only the toy chains in
  test_retention.py.

  WINDOWED — the same four checkpoints, same S, with a window sized to keep
  roughly ten ticks of full history (WINDOW = 10 * §5.4's measured 89
  nodes/tick, rounded to 900) intact and everything behind it sealed.

Each arm runs as its own subprocess (this script re-invoking itself with
--retention-only [--window N]), for the same reason
measure_update_cost.py's run_retention_subprocess() does: `ru_maxrss` is a
process-wide high-water mark, and running both arms in one process would
let the first contaminate the second's reading.

Run:  .venv/bin/python3 scripts/measure_retention_window.py [--json]
"""
import json
import os
import platform
import sys

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
from interp import Interpreter  # noqa: E402

# 10 ticks' worth of full history at §5.4's measured 89 Deriv nodes/tick,
# rounded up — large enough that a `why` query a moment ago still sees
# everything, small enough that the contrast with the unbounded arm is
# unmistakable at these checkpoints.
WINDOW = 900


def run_checkpoints(window):
    """The retention phase itself, parameterized by window (None =
    unbounded). Identical to measure_update_cost.py's run_retention_phase()
    except for that one parameter — see this module's docstring for why it
    is not simply imported and reused verbatim."""
    import gc
    import resource

    results = {}
    for checkpoint in RETENTION_CHECKPOINTS:
        src = build_world_src_for(RETENTION_S, checkpoint)
        interp = Interpreter(host=TestHost(), window=window)
        interp.run(src)
        traced_world = interp.env.get("current-world")
        deriv_count = count_reachable_derivs(traced_world.node)
        gc.collect()
        ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_bytes = ru_maxrss if sys.platform == "darwin" else ru_maxrss * 1024
        results[str(checkpoint)] = {
            "checkpointTick": checkpoint,
            "S": RETENTION_S,
            "window": window,
            "reachableDerivCount": deriv_count,
            "rssBytes": rss_bytes,
        }
        del interp, traced_world
        gc.collect()

    ticks = [results[str(c)]["checkpointTick"] for c in RETENTION_CHECKPOINTS]
    derivs = [results[str(c)]["reachableDerivCount"] for c in RETENTION_CHECKPOINTS]
    rss = [results[str(c)]["rssBytes"] for c in RETENTION_CHECKPOINTS]
    rss_baseline = rss[0]
    rss_growth = [v - rss_baseline for v in rss]
    deriv_slope, deriv_intercept = linear_fit(ticks, derivs)
    rss_slope, rss_intercept = linear_fit(ticks, rss_growth)

    soak_ticks = RETENTION_SOAK_SECONDS * RETENTION_TICKS_PER_SECOND
    extrapolated_bytes = rss_intercept + rss_slope * soak_ticks
    extrapolated_derivs = deriv_intercept + deriv_slope * soak_ticks

    return {
        "S": RETENTION_S,
        "window": window,
        "checkpoints": RETENTION_CHECKPOINTS,
        "results": results,
        "rssBaselineBytes": rss_baseline,
        "rssGrowthBytes": rss_growth,
        "derivCountPerTickSlope": deriv_slope,
        "rssGrowthBytesPerTickSlope": rss_slope,
        "soakSeconds": RETENTION_SOAK_SECONDS,
        "soakTicksPerSecond": RETENTION_TICKS_PER_SECOND,
        "soakTicks": soak_ticks,
        "extrapolatedRssGrowthBytes": extrapolated_bytes,
        "extrapolatedDerivCount": extrapolated_derivs,
    }


def run_subprocess(window):
    import subprocess

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    args = [sys.executable, os.path.abspath(__file__), "--retention-only", "--json"]
    if window is not None:
        args += ["--window", str(window)]
    proc = subprocess.run(args, cwd=repo, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)["retention"]


def _write_md(path, title, data, is_windowed):
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
    if is_windowed:
        lines.append(f"Window: **{data['window']} generations** (≈10 ticks of full "
                     "history at §5.4's measured 89 Deriv nodes/tick).")
    else:
        lines.append("Window: **unbounded** (no `window` argument — the literal "
                     "HEAD/main shape).")
    lines.append("")
    lines.append("| tick | reachable `Deriv` count | RSS growth from tick 1 |")
    lines.append("|---:|---:|---:|")
    for c in data["checkpoints"]:
        r = data["results"][str(c)]
        growth_mb = (r["rssBytes"] - data["rssBaselineBytes"]) / 1e6
        lines.append(f"| {c} | {r['reachableDerivCount']:,} | {growth_mb:.2f} MB |")
    lines.append("")
    lines.append(f"Fitted slope: **{data['derivCountPerTickSlope']:.2f} Deriv nodes/tick**, "
                 f"**{data['rssGrowthBytesPerTickSlope']:.1f} bytes/tick** RSS growth.")
    lines.append("")
    lines.append(f"Extrapolated to a {data['soakSeconds']//60}-minute soak at "
                 f"{data['soakTicksPerSecond']} ticks/second "
                 f"({data['soakTicks']:,} ticks) — EXTRAPOLATION, not measured directly:")
    lines.append("")
    lines.append(f"- extrapolated reachable `Deriv` count: "
                 f"**{data['extrapolatedDerivCount']:,.0f}**")
    lines.append(f"- extrapolated RSS growth: "
                 f"**{data['extrapolatedRssGrowthBytes']/1e6:,.1f} MB**")
    lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {path}")


def main():
    if "--retention-only" in sys.argv:
        window = None
        if "--window" in sys.argv:
            window = int(sys.argv[sys.argv.index("--window") + 1])
        print(json.dumps({"retention": run_checkpoints(window)}))
        return

    json_mode = "--json" in sys.argv

    unbounded = run_subprocess(None)
    windowed = run_subprocess(WINDOW)

    if json_mode:
        print(json.dumps({"unbounded": unbounded, "windowed": windowed}))
        return

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _write_md(
        os.path.join(repo, "reports",
                     "feat-retention-window-and-seals-benchmarks-pre.md"),
        "Pre — unbounded retention (HEAD/main shape)", unbounded, is_windowed=False)
    _write_md(
        os.path.join(repo, "reports",
                     "feat-retention-window-and-seals-benchmarks-post.md"),
        f"Post — retention window={WINDOW} (feat/retention-window-and-seals)",
        windowed, is_windowed=True)

    print()
    print("--- summary (tick=600) ---")
    u600 = unbounded["results"]["600"]
    w600 = windowed["results"]["600"]
    print(f"unbounded reachable Deriv count @ tick 600: {u600['reachableDerivCount']:,}")
    print(f"windowed  reachable Deriv count @ tick 600: {w600['reachableDerivCount']:,}")
    print(f"unbounded extrapolated ({unbounded['soakTicks']:,} ticks): "
          f"{unbounded['extrapolatedDerivCount']:,.0f} derivs, "
          f"{unbounded['extrapolatedRssGrowthBytes']/1e6:,.1f} MB")
    print(f"windowed  extrapolated ({windowed['soakTicks']:,} ticks): "
          f"{windowed['extrapolatedDerivCount']:,.0f} derivs, "
          f"{windowed['extrapolatedRssGrowthBytes']/1e6:,.1f} MB")


if __name__ == "__main__":
    main()
