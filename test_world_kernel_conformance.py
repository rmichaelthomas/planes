"""test_world_kernel_conformance.py — cross-implementation gate for
Horizon Phase 1's engine-kernel spike (build prompt §5; design doc §16
"semantic determinism", §23.3).

Extends test_world_runtime_conformance.py's byte-identical-agreement
discipline from raw envelopes to the KERNEL's own per-tick output: Python
(world_kernel.py + world_delta.py) and JavaScript (js/world_kernel.mjs +
js/world_delta.mjs) must produce the identical `canonical_delta_string`
sequence, tick for tick, over a soak of paint/world/kernel_spike_fixture.planes.

A divergence here is a determinism failure (build prompt §8 invariant 2),
not a rounding tolerance — this is exactly the gate that caught the
fixture's original bug (situation.x/y crossing unquantized, so the Python
and JavaScript `sine` approximation series disagreed in a low decimal
digit); the fixture now rounds both to the protocol's own declared 3
places via `round ... to N places` before the comparison below, and this
test is what keeps that fix honest.
"""
import json
import os
import subprocess
import sys

from host import TestHost
from world_delta import canonical_delta_string
from world_kernel import WorldKernel

REPO = os.path.dirname(os.path.abspath(__file__))
NODE = "node"
FIXTURE = "paint/world/kernel_spike_fixture.planes"
TICK_COUNT = 60  # >= 2 full cycles of the fixture's longest period (weather, 24)
NUDGE_TICK = 10  # Horizon Phase 2 Build 1: when the input-event nudge lands
DELIM = "\n===TICK===\n"


def python_tick_outcomes(n=TICK_COUNT, nudge_at_tick=None):
    k = WorldKernel(FIXTURE, host=TestHost())
    k.start()
    lines = []
    for i in range(n):
        events = [{"kind": "nudge"}] if i == nudge_at_tick else []
        delta, _elapsed = k.step(events)
        lines.append(canonical_delta_string(delta))
    return DELIM.join(lines)


def _js_ticks_script(n=TICK_COUNT, nudge_at_tick=None):
    nudge_at = "null" if nudge_at_tick is None else str(nudge_at_tick)
    return f"""
import {{ WorldKernel }} from "./js/world_kernel.mjs";
import {{ canonicalDeltaString }} from "./js/world_delta.mjs";
import {{ TestHost }} from "./js/host.mjs";

const k = new WorldKernel({json.dumps(FIXTURE)}, {{ host: new TestHost() }});
await k.start();
const lines = [];
const nudgeAtTick = {nudge_at};
for (let i = 0; i < {n}; i++) {{
  const events = i === nudgeAtTick ? [{{ kind: "nudge" }}] : [];
  const {{ delta }} = k.step(events);
  lines.push(canonicalDeltaString(delta));
}}
process.stdout.write(lines.join({json.dumps(DELIM)}));
"""


def js_tick_outcomes(n=TICK_COUNT, nudge_at_tick=None):
    script = _js_ticks_script(n=n, nudge_at_tick=nudge_at_tick)
    r = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        raise AssertionError(f"js kernel script exited {r.returncode}: {r.stderr}")
    return r.stdout


def test_python_and_js_agree_on_every_tick_of_a_kernel_soak():
    py = python_tick_outcomes()
    js = js_tick_outcomes()
    py_ticks = py.split(DELIM)
    js_ticks = js.split(DELIM)
    assert len(py_ticks) == TICK_COUNT
    assert len(js_ticks) == TICK_COUNT
    for i, (p, j) in enumerate(zip(py_ticks, js_ticks)):
        assert p == j, f"tick {i} diverges:\n--- python ---\n{p}\n--- js ---\n{j}"


def test_the_final_semantic_hash_matches_across_implementations():
    py = python_tick_outcomes()
    js = js_tick_outcomes()
    py_last = py.split(DELIM)[-1]
    js_last = js.split(DELIM)[-1]
    py_hash = [line for line in py_last.splitlines() if line.startswith("semantic-hash:")][0]
    js_hash = [line for line in js_last.splitlines() if line.startswith("semantic-hash:")][0]
    assert py_hash == js_hash


def test_python_and_js_agree_on_a_kernel_soak_with_a_nudge_event():
    """Horizon Phase 2 Build 1, graduating build prompt §6.2 check C: the
    same fixture, seed, and a non-empty event batch (one "nudge" event at
    NUDGE_TICK) must still produce byte-identical canonical delta strings
    across Python and JS — the input-event seam extends the existing
    determinism guarantee, it does not carve out an exception to it."""
    py = python_tick_outcomes(n=NUDGE_TICK + 5, nudge_at_tick=NUDGE_TICK)
    js = js_tick_outcomes(n=NUDGE_TICK + 5, nudge_at_tick=NUDGE_TICK)
    py_ticks = py.split(DELIM)
    js_ticks = js.split(DELIM)
    assert len(py_ticks) == NUDGE_TICK + 5
    assert len(js_ticks) == NUDGE_TICK + 5
    for i, (p, j) in enumerate(zip(py_ticks, js_ticks)):
        assert p == j, f"tick {i} diverges:\n--- python ---\n{p}\n--- js ---\n{j}"


def test_the_gate_is_capable_of_failing():
    """The failability proof (build prompt §N+3.2 convention this repo's
    other conformance gates carry) — the comparison is not vacuously true
    for mismatched strings."""
    py = python_tick_outcomes(n=1)
    tampered = py.replace("reso-tide-walker-1", "tampered-id")
    assert py != tampered, "the comparison must be able to observe this divergence"


if __name__ == "__main__":
    fails = []
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
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
