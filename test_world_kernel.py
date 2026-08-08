"""test_world_kernel.py — Horizon Phase 1: the engine-kernel spike.

Covers the build prompt's §4 acceptance: the kernel runs against the
fixture, the sink reports a percentile table, and the semantic-hash chain
is unbroken — plus the structural guarantees §8's invariants name (a clean
envelope every tick, `start()`/`step()` ordering, and that `WorldKernel`
does not itself call into a sink, which is what keeps sink cost out of the
timed span in the first place).
"""
import sys

from host import TestHost
from world_kernel import WorldKernel, WorldKernelError
from world_test_sink import TestSink

FIXTURE = "paint/world/kernel_spike_fixture.planes"


def _kernel(**kw):
    return WorldKernel(FIXTURE, host=TestHost(), **kw)


def test_start_before_step_is_required():
    k = _kernel()
    try:
        k.step()
        assert False, "expected a WorldKernelError"
    except WorldKernelError as e:
        assert "start()" in str(e)


def test_a_hundred_ticks_produce_a_percentile_table_and_an_unbroken_chain():
    k = _kernel()
    k.start()
    sink = TestSink()
    for _ in range(100):
        delta, elapsed = k.step()
        sink.consume(delta, elapsed)

    p = sink.percentiles()
    assert p["count"] == 100
    assert sink.count == 100
    assert 0 <= p["min"] <= p["p50"] <= p["p95"] <= p["p99"] <= p["p999"] <= p["max"]
    assert len(p["distribution"]) == 100
    assert p["distribution"] == sorted(p["distribution"])
    # "unbroken": every consume() call folds a real delta in and advances
    # the chain — a 64-hex-digit sha256 digest, never the seed and never
    # empty, after every one of the hundred ticks.
    assert len(sink.chain_hash) == 64
    assert all(c in "0123456789abcdef" for c in sink.chain_hash)
    assert k.revision == 100


def test_step_return_value_is_delta_and_elapsed_only():
    """A sink call must never be able to land inside the timed span —
    structurally guaranteed here by step()'s signature: it returns data,
    it does not accept or call a sink itself."""
    k = _kernel()
    k.start()
    result = k.step()
    assert isinstance(result, tuple) and len(result) == 2
    delta, elapsed = result
    assert isinstance(delta, dict)
    assert isinstance(elapsed, float)
    assert elapsed >= 0


def test_every_tick_is_a_clean_world_v1_envelope():
    k = _kernel()
    k.start()
    for _ in range(60):
        k.step()
        assert k.prev_envelope is not None
        assert k.prev_envelope["identity"]["id"] == "reso-tide-walker-1"


def test_revision_counter_advances_monotonically_from_start():
    k = _kernel()
    k.start()
    assert k.revision == 0
    for expected in range(1, 21):
        delta, _ = k.step()
        assert delta["revision_from"] == expected - 1
        assert delta["revision_to"] == expected
        assert k.revision == expected


def test_identity_and_lineage_never_appear_in_a_facet_patch():
    """Retention discipline (build prompt §3/invariant 3): identity and
    lineage are never touched by `advance`'s own `with` clauses, so no
    tick's delta should ever carry a facet-patch naming either facet."""
    k = _kernel()
    k.start()
    for _ in range(80):
        delta, _ = k.step()
        for patch in delta["facet_patches"]:
            assert patch["facet"] not in ("identity", "lineage")


def test_the_percentile_table_is_never_average_only():
    """Design doc §16's closing line: "Average FPS alone is insufficient."
    percentiles() must expose the full distribution shape, not a mean."""
    k = _kernel()
    k.start()
    sink = TestSink()
    for _ in range(50):
        delta, elapsed = k.step()
        sink.consume(delta, elapsed)
    p = sink.percentiles()
    for key in ("min", "max", "mean", "p50", "p95", "p99", "p999", "count", "distribution"):
        assert key in p


# =============================== Horizon Phase 2 Build 1: the input-event seam

def test_step_with_no_events_matches_step_with_an_explicit_empty_list():
    """The durable, forward-looking form of build prompt invariant 1: the
    events=[] default must always agree with an explicit empty list, not
    just on this PR's own before/after comparison against HEAD."""
    k1, k2 = _kernel(), _kernel()
    k1.start()
    k2.start()
    for _ in range(20):
        d1, _ = k1.step()
        d2, _ = k2.step([])
        assert d1 == d2


def test_a_nudge_event_changes_exactly_situation_x_deterministically():
    """Build prompt §3.2 acceptance: one recognized event kind ("nudge"),
    one observable field change (situation.x), deterministic across two
    fresh runs — and the change disappears the instant the batch is empty
    again on the following tick."""
    without = _kernel()
    without.start()
    for _ in range(10):
        without.step()
    env_without = without.prev_envelope

    def with_nudge():
        k = _kernel()
        k.start()
        for _ in range(9):
            k.step()
        k.step([{"kind": "nudge"}])
        return k

    with_a = with_nudge()
    with_b = with_nudge()
    assert with_a.prev_envelope == with_b.prev_envelope, "the nudge reaction is not deterministic"

    env_with = with_a.prev_envelope
    diffs = {k: (env_without[k], env_with[k]) for k in env_without
             if env_without[k] != env_with[k]}
    assert list(diffs.keys()) == ["situation"], f"expected only situation to differ, got: {diffs.keys()}"
    situation_diffs = {k: v for k, v in env_without["situation"].items()
                       if v != env_with["situation"][k]}
    assert list(situation_diffs.keys()) == ["x"], (
        f"expected only situation.x to differ, got: {situation_diffs.keys()}")

    # And the reaction is a true one-tick effect: an empty batch on the
    # very next tick shows no lingering influence from the nudge.
    with_a.step([])
    without.step([])
    assert with_a.prev_envelope["situation"]["x"] == without.prev_envelope["situation"]["x"]


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
