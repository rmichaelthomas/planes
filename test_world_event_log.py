"""test_world_event_log.py — Horizon Phase 0 Build 3, Phase 2.

Covers the build prompt's §4 acceptance for the host-owned, append-only,
hash-chained committed-event log — the code half of the locked T-Q-Horizon
decision: NOT a Planes list, integrity computed at the host/driver layer
(this module), never by a language builtin.
"""
import copy
import sys

import world_delta as wd
import world_event_log as wel
import world_ir as w
from host import Host, TestHost

VALID_ENVELOPE = {
    "version": 1,
    "identity": {
        "id": "subject-1", "kind": "vehicle", "subkind": "hydrofoil",
        "displayName": "Reso", "status": "canonical", "schemaVersion": 1,
    },
    "situation": {
        "containingPlace": "landing-1", "space": "world", "x": 0, "y": 0,
        "state": "docked", "occupancy": 0, "anchorId": "anchor-1",
        "chunkActive": True, "physicsRef": "phys-1", "audioRef": "audio-1",
    },
    "lineage": {
        "corpusSource": "ala-eriri", "culturalStatus": "canonical",
        "author": "studio", "origin": "system", "because": "canonical corpus asset",
        "agreementFingerprint": "fp-1", "permittedTransformations": "remix",
        "publishingRestriction": "none", "systemBoundary": "immutable",
    },
}


def _norm():
    normalized, warnings = w.parse_world_envelope(copy.deepcopy(VALID_ENVELOPE))
    assert warnings == []
    return normalized


def _delta(x_from, x_to):
    prev = _norm()
    prev["situation"] = dict(prev["situation"], x=x_from)
    next_env = _norm()
    next_env["situation"] = dict(next_env["situation"], x=x_to)
    return wd.compute_delta(prev, next_env, x_from)


def _payload(tick, x_from, x_to, rationale="advance"):
    return {
        "tick": tick, "actor": "system", "delta": _delta(x_from, x_to),
        "affected_subjects": ["subject-1"], "rationale": rationale,
    }


# ================================================================ append / sequence / chain

def test_append_assigns_monotonic_sequence_numbers():
    log = wel.WorldEventLog()
    e0 = log.append(_payload(0, 0, 1), when=1000000.0)
    e1 = log.append(_payload(1, 1, 2), when=1000001.0)
    e2 = log.append(_payload(2, 2, 3), when=1000002.0)
    assert (e0["sequence"], e1["sequence"], e2["sequence"]) == (0, 1, 2)


def test_first_events_previous_hash_is_the_genesis_hash():
    log = wel.WorldEventLog()
    e0 = log.append(_payload(0, 0, 1), when=1000000.0)
    assert e0["previous_hash"] == wel.GENESIS_HASH


def test_each_events_previous_hash_is_the_priors_own_hash():
    log = wel.WorldEventLog()
    e0 = log.append(_payload(0, 0, 1), when=1000000.0)
    e1 = log.append(_payload(1, 1, 2), when=1000001.0)
    e2 = log.append(_payload(2, 2, 3), when=1000002.0)
    assert e1["previous_hash"] == e0["hash"]
    assert e2["previous_hash"] == e1["hash"]


def test_a_valid_chain_verifies():
    log = wel.WorldEventLog()
    for i in range(5):
        log.append(_payload(i, i, i + 1), when=1000000.0 + i)
    ok, bad_index = log.verify()
    assert ok is True
    assert bad_index is None


def test_receipt_is_opaque_and_passed_through_unchanged():
    log = wel.WorldEventLog()
    e0 = log.append(_payload(0, 0, 1), when=1000000.0, receipt="opaque-token-123")
    assert e0["receipt"] == "opaque-token-123"


def test_receipt_defaults_to_none():
    log = wel.WorldEventLog()
    e0 = log.append(_payload(0, 0, 1), when=1000000.0)
    assert e0["receipt"] is None


# ================================================================ tamper detection

def test_tampering_an_earlier_events_payload_is_caught_at_its_own_slot():
    """Editing an entry's content without recomputing its own `hash`
    (the naive tamper) is caught immediately at that entry's own index —
    its stored hash no longer matches its content."""
    log = wel.WorldEventLog()
    for i in range(4):
        log.append(_payload(i, i, i + 1), when=1000000.0 + i)
    tampered = copy.deepcopy(log.events())
    tampered[1]["payload"]["rationale"] = "forged"
    ok, bad_index = wel.verify_chain(tampered)
    assert ok is False
    assert bad_index == 1


def test_tampering_an_earlier_event_and_recomputing_its_own_hash_still_breaks_the_chain():
    """The chain property, not just per-entry checksums: even a
    sophisticated tamper that edits entry 1's content AND recomputes
    entry 1's own `hash` to match is still caught — at entry 2, whose
    `previous_hash` was fixed to entry 1's ORIGINAL hash and cannot agree
    with entry 1's new one without also being rewritten (and so on for
    every entry after it)."""
    log = wel.WorldEventLog()
    for i in range(4):
        log.append(_payload(i, i, i + 1), when=1000000.0 + i)
    tampered = copy.deepcopy(log.events())
    tampered[1]["payload"]["rationale"] = "forged"
    tampered[1]["hash"] = wel._entry_hash(
        {k: v for k, v in tampered[1].items() if k != "hash"})
    ok, bad_index = wel.verify_chain(tampered)
    assert ok is False
    assert bad_index == 2


def test_tampering_the_last_events_own_hash_is_detected():
    log = wel.WorldEventLog()
    for i in range(3):
        log.append(_payload(i, i, i + 1), when=1000000.0 + i)
    tampered = copy.deepcopy(log.events())
    tampered[-1]["hash"] = "0" * 64
    ok, bad_index = wel.verify_chain(tampered)
    assert ok is False
    assert bad_index == len(tampered) - 1


def test_reordering_two_events_is_detected():
    log = wel.WorldEventLog()
    for i in range(3):
        log.append(_payload(i, i, i + 1), when=1000000.0 + i)
    events = copy.deepcopy(log.events())
    events[0], events[1] = events[1], events[0]
    ok, bad_index = wel.verify_chain(events)
    assert ok is False


def test_the_gate_is_capable_of_failing():
    """The failability proof named in the build prompt (§N+3.2)."""
    log = wel.WorldEventLog()
    for i in range(3):
        log.append(_payload(i, i, i + 1), when=1000000.0 + i)
    ok_before, _ = log.verify()
    assert ok_before is True
    tampered = copy.deepcopy(log.events())
    tampered[0]["payload"]["tick"] = 999
    ok_after, _ = wel.verify_chain(tampered)
    assert ok_after is False, "the verifier must be able to observe this divergence"


# ================================================================ append-only surface

def test_the_public_surface_has_no_mutate_or_delete_method():
    public = {name for name in dir(wel.WorldEventLog) if not name.startswith("_")}
    assert public == {"append", "events", "verify"}, public
    for forbidden in ("update", "delete", "remove", "mutate", "set", "clear", "pop", "truncate"):
        assert not hasattr(wel.WorldEventLog, forbidden)


def test_events_returns_a_defensive_copy_mutation_does_not_reach_the_log():
    log = wel.WorldEventLog()
    log.append(_payload(0, 0, 1), when=1000000.0)
    snapshot = log.events()
    snapshot[0]["payload"]["rationale"] = "mutated after the fact"
    snapshot.append({"sequence": 99})
    fresh = log.events()
    assert fresh[0]["payload"]["rationale"] == "advance"
    assert len(fresh) == 1


# ================================================================ versioning

def test_events_to_json_round_trips_through_events_from_json():
    log = wel.WorldEventLog()
    for i in range(3):
        log.append(_payload(i, i, i + 1), when=1000000.0 + i)
    doc = wel.events_to_json(log.events())
    restored = wel.events_from_json(doc)
    assert restored == log.events()


def test_events_from_json_refuses_an_unrecognized_format_version():
    doc = {"format": 9999, "events": []}
    try:
        wel.events_from_json(doc)
        assert False, "expected a WorldEventLogError"
    except wel.WorldEventLogError as e:
        assert e.tag == "unrecognized-event-log-format"


# ================================================================ optional host capability

def test_append_event_is_optional_a_bare_host_still_works():
    class BareHost(Host):
        name = "bare"

    log = wel.WorldEventLog(host=BareHost())
    e0 = log.append(_payload(0, 0, 1), when=1000000.0)   # must not raise
    assert e0["sequence"] == 0


def test_append_forwards_each_entry_to_the_hosts_append_event():
    host = TestHost()
    log = wel.WorldEventLog(host=host)
    log.append(_payload(0, 0, 1), when=1000000.0)
    log.append(_payload(1, 1, 2), when=1000001.0)
    assert len(host.events) == 2
    assert host.events[0]["sequence"] == 0
    assert host.events[1]["sequence"] == 1


def test_seven_required_host_methods_unchanged_and_append_event_optional():
    required = {"ask", "read", "write", "show", "clock", "resolve", "parse_json"}
    assert len(required) == 7
    for m in required:
        assert hasattr(Host, m), f"a host must provide {m}"
    assert "append_event" not in required
    assert hasattr(Host, "append_event"), "append_event should exist as an optional no-op"


def test_python_host_does_not_override_append_event():
    """PythonHost inherits the no-op default, exactly as it does for
    record/snapshot — a host that keeps nothing is still complete."""
    from host import PythonHost
    assert "append_event" not in PythonHost.__dict__


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
