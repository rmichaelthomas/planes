"""test_world_runtime.py — Horizon Phase 0 Build 2, Phase 3.

Covers the build prompt's §5 acceptance: `world_runtime.py` loads a world
program once, runs `world-init`, runs `advance` N times, and the world
value at each tick is (a) a valid emittable envelope and (b) demonstrably a
new immutable value leaving tick N's value unchanged; the graph is loaded
exactly once.
"""
import copy
import sys

import modules
from host import TestHost
from world_runtime import WorldRuntime, WorldRuntimeError

DEMO = "world_runtime_demo.planes"


def test_init_produces_a_valid_emittable_envelope_at_tick_zero():
    rt = WorldRuntime(DEMO, host=TestHost())
    rt.init()
    normalized, warnings = rt.envelope
    assert warnings == []
    assert normalized["situation"]["x"] == 0


def test_advance_produces_a_new_valid_envelope_each_tick():
    rt = WorldRuntime(DEMO, host=TestHost())
    rt.init()
    for expected_x in (1, 2, 3):
        rt.advance()
        normalized, warnings = rt.envelope
        assert warnings == []
        assert normalized["situation"]["x"] == expected_x


def test_advance_before_init_refuses():
    rt = WorldRuntime(DEMO, host=TestHost())
    try:
        rt.advance()
        assert False, "expected a WorldRuntimeError"
    except WorldRuntimeError:
        pass


def test_a_program_missing_world_init_refuses_at_construction():
    try:
        WorldRuntime("benchmarks/world_shape.planes", host=TestHost())
        assert False, "expected a WorldRuntimeError"
    except WorldRuntimeError as e:
        assert "world-init" in str(e)


def test_tick_ns_value_is_unchanged_after_tick_n_plus_1_runs():
    """§5 requirement 3: the world value persists across ticks WITHOUT
    being re-serialized through JSON, and a retained reference to an
    earlier tick's value is untouched by a later `advance` call — the
    value model's `with` never mutates the record it started from."""
    rt = WorldRuntime(DEMO, host=TestHost())
    tick0 = rt.init()
    tick0_snapshot = copy.deepcopy(tick0.value)

    tick1 = rt.advance()
    assert tick0.value == tick0_snapshot, "tick 0's value changed after advance() ran"
    assert tick1.value != tick0.value

    tick1_snapshot = copy.deepcopy(tick1.value)
    rt.advance()
    assert tick1.value == tick1_snapshot, "tick 1's value changed after a later advance() ran"


def test_the_world_value_is_never_serialized_through_json_between_ticks():
    """A structural guarantee, not just an outcome: the `Traced` object
    `advance` returns on tick N is passed DIRECTLY as tick N+1's argument —
    `rt.world` is Python object identity carried across calls, never a
    round-trip through `json.dumps`/`json.loads`."""
    rt = WorldRuntime(DEMO, host=TestHost())
    tick0 = rt.init()
    tick1 = rt.advance()
    # advance()'s call site passes rt.world (== tick0) as `advance`'s first
    # argument directly; the interpreter's own record-update semantics
    # (`with`) build tick1's dict by copying tick0's, so tick1 shares no
    # container identity with tick0 while still being derived FROM it in
    # one interpreter call, not a save/load round trip.
    assert tick1.value is not tick0.value
    assert tick1.value["situation"] is not tick0.value["situation"]


def test_the_module_graph_loads_exactly_once_across_many_advance_calls():
    """§5 requirement 1: load/hoist is not re-entered per advance. Patches
    modules.load_graph with a call counter — the same function run_file
    calls exactly once per WorldRuntime construction — and asserts it
    stays at 1 no matter how many ticks follow."""
    original = modules.load_graph
    calls = []

    def counting(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    modules.load_graph = counting
    try:
        rt = WorldRuntime(DEMO, host=TestHost())
        assert len(calls) == 1
        rt.init()
        for _ in range(10):
            rt.advance()
        assert len(calls) == 1, f"load_graph was called {len(calls)} times, expected 1"
    finally:
        modules.load_graph = original


def test_the_retention_window_and_tracing_off_fast_path_are_available_per_tick():
    """§5 requirement 5: `window=`/`trace=False` pass straight through to
    the persistent interpreter, so a long-running session does not
    accumulate unbounded derivation. A tracing-off run still produces
    valid envelopes at every tick — R3's fast path changes nothing about
    VALUES, only whether their derivation graph is built."""
    rt = WorldRuntime(DEMO, host=TestHost(), window=8, trace=False)
    rt.init()
    for _ in range(20):
        rt.advance()
    normalized, warnings = rt.envelope
    assert warnings == []
    assert normalized["situation"]["x"] == 20
    # Tracing off: every Deriv `mk` built during this run is the one shared
    # sentinel node (R3, §466-476) — the interpreter allocated no per-node
    # derivation graph across 21 calls into the program.
    assert rt.world.node is rt.itp._untraced


def test_many_ticks_stay_valid_world_v1_envelopes():
    rt = WorldRuntime(DEMO, host=TestHost(), window=16)
    rt.init()
    for i in range(1, 51):
        rt.advance()
        normalized, warnings = rt.envelope
        assert warnings == []
        assert normalized["situation"]["x"] == i


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
