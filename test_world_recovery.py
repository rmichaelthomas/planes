"""test_world_recovery.py — Horizon Phase 0 Build 3, Phase 3.

Covers the build prompt's §5 acceptance for recovery: reconstruct a world
value from the newest valid snapshot plus the ticks after it, by
deterministic re-execution (R3's replay discipline — `ReplayHost` plus
`trace=True`, reused at world scale via `WorldRuntime`'s own `host=`
constructor parameter, since `replay()` itself replays SOURCE STEPS and
`WorldRuntime` ticks via FUNCTION CALLS against one persistent interpreter —
an incompatible calling shape `world_recovery.py`'s module docstring
explains in full). The standing gate (v30.0 §474): the replayed
derivation must agree byte-for-byte with the eager pre-crash run, not only
the envelope's canonical form.

Scope: `world_runtime_demo.planes`'s `advance` is pure (no ambient clock or
random, spec §8.4); its one host effect — the top-level `show demo-world`
Build 2's own Phase 1 emission gate exercises — is handled transparently by
`world_recovery.py`'s `_module_load_effect_log` (see that module's docstring
for why this is still exact replay, not a workaround). Recovering a
world program whose `advance` ITSELF performs a host effect is out of this
build's reach — `WorldRuntime` always constructs its interpreter with
`record=False` (Build 2), so it never accumulates a tick-level effect log
during real operation — and is not exercised below; see
REPORT_WORLD_EVENT_LOG.md.
"""
import sys

from host import TestHost
from interp import explain, why_machine, why_tree
from world_ir import canonical_outcome_string
from world_recovery import WorldRecoveryError, recover
from world_runtime import WorldRuntime
from world_snapshot import capture_snapshot

DEMO = "world_runtime_demo.planes"


def _derivation(traced):
    return {"card": explain(traced), "prompt": why_tree(traced), "machine": why_machine(traced)}


# ================================================================ recovery = replay

def test_recovery_reconstructs_byte_identical_canonical_form_and_derivation():
    rt = WorldRuntime(DEMO, host=TestHost(), trace=True)
    rt.init()
    for _ in range(4):
        rt.advance()
    snapshot_envelope, warnings = rt.envelope
    assert warnings == []
    snapshot = capture_snapshot(snapshot_envelope, 4)

    for _ in range(6):   # tick 4 -> tick 10
        rt.advance()
    original_envelope, warnings = rt.envelope
    assert warnings == []
    original_derivation = _derivation(rt.world)

    recovered_rt = recover(DEMO, snapshot, 6)
    recovered_envelope, warnings = recovered_rt.envelope
    assert warnings == []

    assert (canonical_outcome_string(recovered_envelope)
            == canonical_outcome_string(original_envelope))
    assert _derivation(recovered_rt.world) == original_derivation


def test_recovery_from_a_snapshot_taken_at_tick_zero():
    rt = WorldRuntime(DEMO, host=TestHost(), trace=True)
    rt.init()
    tick0_envelope, warnings = rt.envelope
    assert warnings == []
    snapshot = capture_snapshot(tick0_envelope, 0)

    for _ in range(3):
        rt.advance()
    original_envelope, _ = rt.envelope
    original_derivation = _derivation(rt.world)

    recovered_rt = recover(DEMO, snapshot, 3)
    recovered_envelope, _ = recovered_rt.envelope
    assert (canonical_outcome_string(recovered_envelope)
            == canonical_outcome_string(original_envelope))
    assert _derivation(recovered_rt.world) == original_derivation


def test_recovery_with_zero_ticks_after_snapshot_reproduces_the_snapshot_itself():
    rt = WorldRuntime(DEMO, host=TestHost(), trace=True)
    rt.init()
    for _ in range(5):
        rt.advance()
    envelope, _ = rt.envelope
    snapshot = capture_snapshot(envelope, 5)

    recovered_rt = recover(DEMO, snapshot, 0)
    recovered_envelope, _ = recovered_rt.envelope
    assert canonical_outcome_string(recovered_envelope) == canonical_outcome_string(envelope)


# ================================================================ refusals

def test_recovery_refuses_on_a_corrupted_snapshot_hash():
    rt = WorldRuntime(DEMO, host=TestHost(), trace=True)
    rt.init()
    for _ in range(2):
        rt.advance()
    envelope, _ = rt.envelope
    snapshot = capture_snapshot(envelope, 2)
    snapshot["semantic_hash"] = "0" * 64
    try:
        recover(DEMO, snapshot, 1)
        assert False, "expected a refusal on a hash-corrupted snapshot"
    except Exception as e:
        assert "hash" in str(e)


def test_recovery_refuses_when_snapshot_does_not_match_what_replay_actually_produces():
    """A snapshot that is internally hash-consistent (its stored hash
    matches its own envelope) but describes a state the real program never
    reached at that revision — a deeper corruption than a broken hash, and
    the reason recovery re-derives rather than merely trusts a snapshot's
    self-consistency."""
    rt = WorldRuntime(DEMO, host=TestHost(), trace=True)
    rt.init()
    for _ in range(2):
        rt.advance()
    real_envelope, _ = rt.envelope
    forged_envelope = dict(real_envelope)
    forged_envelope["situation"] = dict(real_envelope["situation"], x=999)
    forged_snapshot = capture_snapshot(forged_envelope, 2)   # self-consistent, but wrong
    try:
        recover(DEMO, forged_snapshot, 1)
        assert False, "expected a WorldRecoveryError"
    except WorldRecoveryError as e:
        assert e.tag == "snapshot-replay-divergence"


def test_the_gate_is_capable_of_failing():
    """The failability proof named in the build prompt (§N+3.2)."""
    rt = WorldRuntime(DEMO, host=TestHost(), trace=True)
    rt.init()
    for _ in range(2):
        rt.advance()
    envelope, _ = rt.envelope
    snapshot = capture_snapshot(envelope, 2)
    recovered_rt = recover(DEMO, snapshot, 0)
    recovered_envelope, _ = recovered_rt.envelope
    real = canonical_outcome_string(recovered_envelope)
    tampered = real.replace("2", "9")
    assert real != tampered, "the comparison must be able to observe this divergence"


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
