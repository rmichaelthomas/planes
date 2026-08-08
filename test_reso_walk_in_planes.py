"""test_reso_walk_in_planes.py — paint/reso_walk.planes, Horizon's first
movement slice (Inception v2.0 §514-§520, build prompt §5).

Driven through the PERSISTENT-KERNEL calling convention exactly as
test_a_crossing_in_planes.py drives the crossing: world-init once, then
advance(world, tick, events) any number of times, reading each call's
show-line output back through take_output() (WorldRuntime's own gap-fix
from the crossing port, reused unmodified here).

Covers, in Planes-executed terms:
  - world-init produces a well-formed world at the initial dock position;
  - a scripted event sequence (move west x N, then touch) drives boy-x
    monotonically toward the market, clamps at the strip minimum, and
    fires the touch only within range (§3.6's fixture acceptance bar);
  - determinism: the same (init, events) sequence produces byte-identical
    world/line sequences across two fresh Python runs, and — mirroring
    test_crossing_port.py's own Python-vs-JS bar — the same sequence
    under js/world_runtime.mjs agrees tick for tick;
  - why on the final boy-x yields a rationale string naming the movement
    input (decision 3's traced-step guarantee, asserted here rather than
    assumed — see paint/reso_walk.planes's own header on why `why` is
    called on the bare local `next-boy-x`, not a record field).
"""
import hashlib
import json
import os
import subprocess
import sys

from host import TestHost
from interp import to_host
from world_runtime import WorldRuntime

REPO = os.path.dirname(os.path.abspath(__file__))
NODE = "node"
FIXTURE = "paint/reso_walk.planes"
WEST = {"kind": "move", "dir": "west"}
EAST = {"kind": "move", "dir": "east"}
TOUCH = {"kind": "touch"}


def boot():
    return WorldRuntime(FIXTURE, host=TestHost())


def init(rt):
    rt.init()
    lines, _trace = rt.take_output()
    return to_host(rt.world.value), lines


def step(rt, events=None):
    rt.advance(events)
    lines, _trace = rt.take_output()
    return to_host(rt.world.value), lines


def step_n(rt, n, events=None):
    state, lines = None, None
    for _ in range(n):
        state, lines = step(rt, events)
    return state, lines


# =========================================================== 1. world-init


def test_init_places_the_body_a_few_steps_from_the_market():
    state, lines = init(boot())
    assert state["boy-x"] == 0.2
    assert state["facing"] == "west"
    assert state["touched"] is False
    assert state["near-market"] is False
    assert "scene protocol 1" in lines
    assert any(line.startswith("scene subject boy boy 0.2 ") for line in lines)
    assert any(
        line.startswith("scene subject market market ") and line.endswith("untouched")
        for line in lines)


def test_init_output_is_a_well_formed_scene_intent():
    """Every emitted line the scene-intent protocol cares about carries the
    field counts js/scene/ir.mjs enforces — checked structurally here
    (arity by split-length) since this file has no JS import of its own;
    js/test/reso_walk.test.mjs runs the same lines through the real
    parseSceneIntent (§3.6's own "zero warnings" bar)."""
    _state, lines = init(boot())
    subject_lines = [line for line in lines if line.startswith("scene subject ")]
    assert len(subject_lines) >= 3
    for line in subject_lines:
        assert len(line.split()) == 9, line
    camera_lines = [line for line in lines if line.startswith("scene camera ")]
    assert len(camera_lines) == 1
    assert len(camera_lines[0].split()) == 6


# ==================================================== 2. movement + clamp


def test_walking_west_moves_the_body_monotonically_toward_the_market():
    rt = boot()
    init(rt)
    xs = []
    for _ in range(20):
        state, _lines = step(rt, [WEST])
        xs.append(state["boy-x"])
    assert all(b <= a for a, b in zip(xs, xs[1:])), xs
    assert xs[0] < 0.2


def test_walking_west_clamps_at_the_dock_minimum():
    rt = boot()
    init(rt)
    state, _lines = step_n(rt, 80, [WEST])
    assert state["boy-x"] == 0.05
    state, _lines = step(rt, [WEST])
    assert state["boy-x"] == 0.05, "the clamp must hold even while west is still held"


def test_walking_east_clamps_at_the_dock_maximum():
    rt = boot()
    init(rt)
    state, _lines = step_n(rt, 80, [EAST])
    assert state["boy-x"] == 0.24
    state, _lines = step(rt, [EAST])
    assert state["boy-x"] == 0.24, "the clamp must hold even while east is still held"


def test_releasing_the_key_for_one_tick_only_costs_that_one_tick():
    """The dropped-event-self-corrects guarantee (decision 2/invariant 3,
    failure mode #3): position is a pure function of (world, events), so a
    single tick with no events changes nothing and does not stall a later
    resumed walk."""
    rt = boot()
    init(rt)
    step_n(rt, 10, [WEST])
    before, _lines = step(rt, None)
    after, _lines = step(rt, [WEST])
    assert before["boy-x"] == 0.2 - 10 * 0.003
    assert after["boy-x"] < before["boy-x"]


def test_facing_tracks_the_last_horizontal_direction_and_holds_on_no_input():
    rt = boot()
    init(rt)
    state, _lines = step(rt, [EAST])
    assert state["facing"] == "east"
    state, _lines = step(rt, None)
    assert state["facing"] == "east", "facing must not reset when nothing is held"
    state, _lines = step(rt, [WEST])
    assert state["facing"] == "west"


# ============================================================ 3. the touch


def test_touch_out_of_range_is_a_no_op_with_an_honest_revision():
    rt = boot()
    init(rt)
    state, _lines = step(rt, [TOUCH])
    assert state["touched"] is False
    assert "not close enough" in state["revision"]


def test_touch_in_range_latches_touched_and_emits_the_response():
    rt = boot()
    init(rt)
    state, _lines = step_n(rt, 25, [WEST])
    assert state["near-market"] is True
    assert state["touched"] is False

    state, lines = step(rt, [TOUCH])
    assert state["touched"] is True
    assert state["serial"] == 1
    assert any(
        line.startswith("scene subject market") and line.endswith("greeted")
        for line in lines)
    assert any(line.startswith("scene action") for line in lines) is False, (
        "the approach prompt must not still be offered once touched")

    # A second touch is a no-op: touched (and serial) do not change again.
    state2, _lines2 = step(rt, [TOUCH])
    assert state2["touched"] is True
    assert state2["serial"] == 1
    assert "already" in state2["revision"]


def test_the_approach_prompt_only_appears_within_range_and_before_touch():
    rt = boot()
    init(rt)
    _state, lines_far = step(rt, None)
    assert not any(line.startswith("scene action") for line in lines_far)
    _state, lines_near = step_n(rt, 25, [WEST])
    assert any(line.startswith("scene action market touch approach") for line in lines_near)


def test_program_never_trusts_a_touch_the_page_did_not_earn():
    """The fixture re-checks range itself (belt and suspenders, §3.4) — a
    touch sent while genuinely out of range never latches, regardless of
    what a page might (incorrectly) believe."""
    rt = boot()
    init(rt)
    step_n(rt, 5, [WEST])  # nowhere near the market yet
    state, _lines = step(rt, [TOUCH])
    assert state["touched"] is False


# =============================================== 4. the traced step (why)


def test_why_on_the_final_position_names_the_movement_input():
    rt = boot()
    init(rt)
    _state, lines = step(rt, [WEST])
    why_line = next(line for line in lines if " from " in line and "because" in line)
    assert "because" in why_line
    assert "west" in why_line
    assert not why_line.strip().replace(".", "").replace("-", "").isdigit(), (
        "why must return a sentence, not a bare number")


def test_why_names_the_clamp_when_the_edge_is_reached():
    rt = boot()
    init(rt)
    step_n(rt, 79, [WEST])
    _state, lines = step(rt, [WEST])
    why_line = next(line for line in lines if " from " in line and "because" in line)
    assert "clamp" in why_line


def test_why_names_no_input_when_nothing_is_held():
    rt = boot()
    init(rt)
    _state, lines = step(rt, None)
    why_line = next(line for line in lines if " from " in line and "because" in line)
    assert "no movement key was held" in why_line


# ================================================== 5. determinism (Python)


def _hash_lines(lines):
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


SCRIPT_EVENTS = {5: WEST, 6: WEST, 7: WEST, 44: TOUCH, 50: EAST, 51: EAST}
TICK_COUNT = 90


def python_tick_hashes(n=TICK_COUNT, events_at_tick=None):
    events_at_tick = SCRIPT_EVENTS if events_at_tick is None else events_at_tick
    rt = boot()
    rt.init()
    lines, _trace = rt.take_output()
    hashes = [_hash_lines(lines)]
    for tick in range(n):
        event = events_at_tick.get(tick)
        rt.advance([event] if event else [])
        lines, _trace = rt.take_output()
        hashes.append(_hash_lines(lines))
    return hashes


def test_python_determinism_across_two_fresh_runs():
    a = python_tick_hashes()
    b = python_tick_hashes()
    assert a == b


def test_the_gate_is_capable_of_failing():
    a = python_tick_hashes(5)
    tampered = list(a)
    tampered[0] = "0" * 64
    assert a != tampered


# ============================================ 6. cross-implementation (JS)


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
    events_at_tick = SCRIPT_EVENTS if events_at_tick is None else events_at_tick
    script = _js_script(n, events_at_tick)
    r = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        raise AssertionError(f"js reso_walk script exited {r.returncode}: {r.stderr}")
    return json.loads(r.stdout)


def test_python_and_js_agree_tick_for_tick_over_the_scripted_walk():
    py = python_tick_hashes()
    js = js_tick_hashes()
    assert len(py) == len(js) == TICK_COUNT + 1
    mismatches = [i for i, (p, j) in enumerate(zip(py, js)) if p != j]
    assert not mismatches, f"diverged at ticks {mismatches[:5]} of {len(py)}"


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
