"""test_world_snapshot.py — Horizon Phase 0 Build 3, Phase 3.

Covers the build prompt's §5 acceptance for durable snapshot capture:
`capture_snapshot` bundles a normalized world-v1 envelope's revision and
semantic hash, persisted through the host's existing, optional `snapshot`
capability (host.py) exactly as `record` is; `restore_snapshot` is the
refuse-don't-guess reverse — an unrecognized world-v1 protocol version or a
hash that no longer matches its own envelope refuses rather than guessing.
"""
import copy
import sys

import world_ir as w
import world_snapshot as ws
from host import TestHost

VALID_ENVELOPE = {
    "version": 1,
    "identity": {
        "id": "subject-1", "kind": "vehicle", "subkind": "hydrofoil",
        "displayName": "Reso", "status": "canonical", "schemaVersion": 1,
    },
    "situation": {
        "containingPlace": "landing-1", "space": "world", "x": 10, "y": -5,
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


# ================================================================ capture

def test_capture_bundles_envelope_revision_and_semantic_hash():
    env = _norm()
    snap = ws.capture_snapshot(env, 7)
    assert snap["revision"] == 7
    assert snap["envelope"] == env
    assert snap["semantic_hash"] == ws.semantic_hash(env)


def test_capture_is_a_no_op_persistence_wise_with_no_host():
    env = _norm()
    ws.capture_snapshot(env, 0, host=None)   # must not raise


def test_capture_forwards_to_the_hosts_snapshot_capability():
    host = TestHost()
    env = _norm()
    snap = ws.capture_snapshot(env, 3, host=host)
    assert host.snapshots[snap["semantic_hash"]] == snap


# ================================================================ restore

def test_restore_round_trips_a_valid_snapshot():
    env = _norm()
    snap = ws.capture_snapshot(env, 5)
    restored_envelope, restored_revision = ws.restore_snapshot(snap)
    assert restored_envelope == env
    assert restored_revision == 5


def test_restore_refuses_an_unsupported_protocol_version():
    env = _norm()
    snap = ws.capture_snapshot(env, 0)
    snap["envelope"]["version"] = 2
    try:
        ws.restore_snapshot(snap)
        assert False, "expected a WorldSnapshotError"
    except ws.WorldSnapshotError as e:
        assert e.tag == "invalid-snapshot-envelope"


def test_restore_refuses_a_hash_that_no_longer_matches_its_envelope():
    env = _norm()
    snap = ws.capture_snapshot(env, 0)
    snap["envelope"] = dict(snap["envelope"])
    snap["envelope"]["situation"] = dict(snap["envelope"]["situation"], x=999)
    try:
        ws.restore_snapshot(snap)
        assert False, "expected a WorldSnapshotError"
    except ws.WorldSnapshotError as e:
        assert e.tag == "snapshot-hash-mismatch"


def test_restore_refuses_a_malformed_snapshot_missing_a_required_key():
    for missing in ("revision", "envelope", "semantic_hash"):
        env = _norm()
        snap = ws.capture_snapshot(env, 0)
        del snap[missing]
        try:
            ws.restore_snapshot(snap)
            assert False, f"expected a WorldSnapshotError for missing '{missing}'"
        except ws.WorldSnapshotError as e:
            assert e.tag == "malformed-snapshot"


def test_the_gate_is_capable_of_failing():
    """The failability proof named in the build prompt (§N+3.2)."""
    env = _norm()
    snap = ws.capture_snapshot(env, 0)
    ok_before, _ = ws.restore_snapshot(snap), None
    assert ok_before is not None
    snap["semantic_hash"] = "0" * 64
    try:
        ws.restore_snapshot(snap)
        assert False, "the verifier must be able to observe this divergence"
    except ws.WorldSnapshotError:
        pass


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
