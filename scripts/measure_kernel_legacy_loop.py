#!/usr/bin/env python3
"""scripts/measure_kernel_legacy_loop.py — the "before" half of Horizon
Phase 1's engine-kernel spike (build prompt §7).

Design doc §12's rejected path, made concrete: "composes source prelude
text, parses and runs the graph, renders output to text, writes state
through an in-memory JSON file, and repeats." This script drives
paint/world/kernel_spike_fixture.planes — the SAME fixture world_kernel.py
drives persistently — through exactly that loop instead: every tick gets a
brand-new `Interpreter`, the fixture's own source text re-parsed from
scratch, the previous tick's state re-injected as a composed prelude
literal (the js/paint/loop.mjs / test_a_crossing_in_planes.py convention),
and the result written to and read back from an in-memory "state.json" —
never held as an in-memory Traced value across ticks, unlike
`WorldRuntime.advance`.

Timed as a whole, per tick: compose the prelude, assemble the program text,
construct a fresh Interpreter, parse + run it (which re-hashes and re-loads
the fixture's own module graph every time — there are none here, the
fixture declares no `use`, but the parse/hoist cost is real and repeated
regardless), and read the written state back out of the host's in-memory
file table. This is the whole "before" cost world_kernel.py's persistent
path (Build 2's WorldRuntime, held once and called per tick) exists to cut.

Run:  .venv/bin/python3 scripts/measure_kernel_legacy_loop.py [--ticks N] [--out PATH]
"""
import argparse
import json
import math
import os
import platform
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from host import TestHost  # noqa: E402
from interp import Interpreter  # noqa: E402

FIXTURE = os.path.join(REPO, "paint", "world", "kernel_spike_fixture.planes")
DEFAULT_TICKS = 1000

DRIVER = """
use file

to legacy-next of prev-state, tick:
  if tick == 0:
    give world-init
  else:
    give advance of prev-state, (tick - 1)

let next = legacy-next of prev-state, tick
write next to "state.json"
"""


def planes_literal(value):
    """The prelude-injection convention js/paint/loop.mjs's own
    `planesLiteral` and test_a_crossing_in_planes.py's own
    `planes_literal` already establish — restated here rather than
    imported, since neither lives at an importable module boundary this
    script can reach (one is JS, the other a test file's private helper)."""
    if value is None:
        return "nothing"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(planes_literal(item) for item in value) + "]"
    return "{ " + ", ".join(
        f"{key}: {planes_literal(item)}" for key, item in value.items()
    ) + " }"


def _percentiles(values):
    ordered = sorted(values)
    n = len(ordered)

    def pct(p):
        idx = min(n - 1, max(0, math.ceil(p * n) - 1))
        return ordered[idx]

    return {
        "count": n, "min": ordered[0], "max": ordered[-1],
        "mean": sum(ordered) / n,
        "p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99), "p999": pct(0.999),
    }


def run(ticks=DEFAULT_TICKS):
    with open(FIXTURE, encoding="utf-8") as fh:
        fixture_source = fh.read()

    prev_state = None
    timings = []
    for tick in range(ticks):
        t0 = time.perf_counter()
        prelude = f"let tick = {tick}\nlet prev-state = {planes_literal(prev_state)}\n"
        program = prelude + fixture_source + "\n" + DRIVER
        host = TestHost()
        itp = Interpreter(host=host)
        itp.run(program)
        next_state = json.loads(host.files["state.json"])
        elapsed = time.perf_counter() - t0

        timings.append(elapsed)
        prev_state = next_state

    return _percentiles(timings)


def machine_specs():
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=DEFAULT_TICKS)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    specs = machine_specs()
    t0 = time.perf_counter()
    stats = run(args.ticks)
    wall = time.perf_counter() - t0

    if args.json:
        print(json.dumps({"machine": specs, "stats": stats, "wallSeconds": wall}))
        return

    print(f"machine: {specs['cpu']} / {specs['cores']} cores / {specs['platform']} / "
          f"python {specs['pythonVersion']}")
    print(f"ticks: {stats['count']}  wall: {wall:.2f}s")
    for key in ("min", "p50", "p95", "p99", "p999", "max", "mean"):
        print(f"  {key:>4}: {stats[key] * 1000:.3f} ms")


if __name__ == "__main__":
    main()
