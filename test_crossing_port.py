"""test_crossing_port.py — Horizon Phase 2 Build 2's own determinism gate
(build prompt §6.2 check B, blocking): "same seed + events, Python and JS,
two fresh runs each; assert identical semantic snapshot-hash sequences."

Mirrors test_world_kernel_conformance.py's own shell-out-to-node pattern
exactly (see that file's module docstring for the full precedent) — this
crossing has no world-v1 envelope to diff at all (it speaks the scene-
intent protocol instead — see paint/a_crossing.planes's own header on why
the whole game moved into world-init/advance function bodies), so a
"semantic snapshot" here is each call's captured show-line sequence
(WorldRuntime.take_output()/takeOutput(), Horizon Phase 2 Build 2's own
gap-fix — see that method's docstring on both classes for why it exists),
hashed with the same sha256 primitive world_delta.py/js/sha256.mjs already
use elsewhere in this repo, never a language builtin.

paint/a_crossing.planes's own seed is now a fixed constant (world-init
takes zero parameters — see that file's header), so "same seed" holds by
construction here; what this gate actually varies and compares is the
event sequence.
"""
import hashlib
import json
import os
import subprocess
import sys

from host import TestHost
from world_runtime import WorldRuntime

REPO = os.path.dirname(os.path.abspath(__file__))
NODE = "node"
FIXTURE = "paint/a_crossing.planes"
# > 160 (the crossing's own voyage-progress denominator in paint/a_crossing.
# planes), so a full crossing (ready -> planning -> crossing -> arrived) is
# exercised, not just its opening ticks.
TICK_COUNT = 200
EVENTS_AT_TICK = {5: {"kind": "need", "choice": "care"}, 10: {"kind": "route", "choice": "depart"}}


def _hash_lines(lines):
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def python_tick_hashes(n=TICK_COUNT, events_at_tick=None):
    events_at_tick = EVENTS_AT_TICK if events_at_tick is None else events_at_tick
    rt = WorldRuntime(FIXTURE, host=TestHost())
    rt.init()
    lines, _trace = rt.take_output()
    hashes = [_hash_lines(lines)]
    for tick in range(n):
        event = events_at_tick.get(tick)
        rt.advance([event] if event else [])
        lines, _trace = rt.take_output()
        hashes.append(_hash_lines(lines))
    return hashes


def _js_script(n, events_at_tick):
    return f"""
import {{ WorldRuntime }} from "./js/world_runtime.mjs";
import {{ sha256Hex }} from "./js/sha256.mjs";

const rt = new WorldRuntime({json.dumps(FIXTURE)}, {{}});
await rt.load();
rt.init();
const eventsAtTick = {json.dumps({str(k): v for k, v in events_at_tick.items()})};
const hashLines = (lines) => sha256Hex(lines.join("\\n"));
const hashes = [];
{{
  const {{ lines }} = rt.takeOutput();
  hashes.push(hashLines(lines));
}}
for (let tick = 0; tick < {n}; tick++) {{
  const event = eventsAtTick[String(tick)];
  rt.advance(event ? [event] : []);
  const {{ lines }} = rt.takeOutput();
  hashes.push(hashLines(lines));
}}
process.stdout.write(JSON.stringify(hashes));
"""


def js_tick_hashes(n=TICK_COUNT, events_at_tick=None):
    events_at_tick = EVENTS_AT_TICK if events_at_tick is None else events_at_tick
    script = _js_script(n, events_at_tick)
    r = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        raise AssertionError(f"js crossing script exited {r.returncode}: {r.stderr}")
    return json.loads(r.stdout)


def test_python_determinism_across_two_fresh_runs():
    a = python_tick_hashes(60)
    b = python_tick_hashes(60)
    assert a == b


def test_js_determinism_across_two_fresh_runs():
    a = js_tick_hashes(60)
    b = js_tick_hashes(60)
    assert a == b


def test_python_and_js_agree_tick_for_tick_over_a_full_crossing():
    py = python_tick_hashes()
    js = js_tick_hashes()
    assert len(py) == len(js) == TICK_COUNT + 1
    mismatches = [i for i, (p, j) in enumerate(zip(py, js)) if p != j]
    assert not mismatches, f"diverged at ticks {mismatches[:5]} of {len(py)}"


def test_python_and_js_agree_with_a_different_event_sequence_too():
    """Not just the one fixed rehearsal above — a second, disjoint event
    sequence (every action-surface kind at least once: select, need,
    power, radio, route) must agree as well, so the gate is not
    accidentally only proving agreement on one lucky path through the
    branch chain."""
    events = {
        3: {"kind": "select", "subject": "market"},
        7: {"kind": "need", "choice": "work"},
        20: {"kind": "power", "choice": "clinic"},
        35: {"kind": "radio", "choice": "relay"},
        50: {"kind": "route", "choice": "depart"},
    }
    py = python_tick_hashes(120, events_at_tick=events)
    js = js_tick_hashes(120, events_at_tick=events)
    assert len(py) == len(js) == 121
    mismatches = [i for i, (p, j) in enumerate(zip(py, js)) if p != j]
    assert not mismatches, f"diverged at ticks {mismatches[:5]} of {len(py)}"


def test_the_gate_is_capable_of_failing():
    py = python_tick_hashes(1)
    tampered = list(py)
    tampered[0] = "0" * 64
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
