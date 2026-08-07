"""Tests for world_ir.py — the Python World IR (world-v1) parser/validator.

Horizon Phase 0 Build 1. Covers the parser's contract stated in the build
prompt: version-first refusal, missing/malformed critical records, malformed
known-optional records, and unknown-optional warn-and-ignore — each a
distinct case, never conflated.
"""
import copy
import sys

import world_ir as w

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
    "relation": {
        "relationId": "rel-1", "relationType": "near", "fromId": "subject-1",
        "toId": "landing-1", "provenance": "authored",
    },
    "behavior": {
        "eventPattern": "arrival", "transition": "docked", "timerTicks": 100,
        "condition": "always", "stateMachine": "dock-cycle",
        "emittedEvent": "docked", "failurePath": "resync",
    },
    "expression": {
        "assetId": "asset-reso", "layer": 2, "depth": 0.5,
        "animationState": "idle", "material": "hull",
        "lightingResponse": "standard", "particleIntent": "none",
        "colliderId": "collider-1", "sensorId": "sensor-1",
        "audioAnchor": "audio-anchor-1", "fidelityVariant": "harbor",
        "accessibleAlt": "reduced-motion",
    },
    "affordance": {
        "action": "board", "precondition": "docked",
        "valueShape": "boolean", "preview": "highlight",
        "inverse": "disembark", "authorityRequired": "none",
        "explanation": "board the hydrofoil", "sourceMapTarget": "identity.status",
        "fallback": "deny",
    },
    "lineage": {
        "corpusSource": "ala-eriri", "culturalStatus": "canonical",
        "author": "studio", "origin": "system", "because": "canonical corpus asset",
        "agreementFingerprint": "fp-1", "permittedTransformations": "remix",
        "publishingRestriction": "none", "systemBoundary": "immutable",
    },
}


def _valid():
    return copy.deepcopy(VALID_ENVELOPE)


# ============================================================== acceptance

def test_a_fully_populated_valid_envelope_is_accepted():
    normalized, warnings = w.parse_world_envelope(_valid())
    assert warnings == []
    assert normalized["version"] == 1
    assert normalized["identity"]["id"] == "subject-1"
    assert set(normalized) == {"version"} | set(w.FACET_ORDER)


def test_only_the_three_critical_facets_is_still_accepted():
    env = _valid()
    for facet in ("relation", "behavior", "expression", "affordance"):
        del env[facet]
    normalized, warnings = w.parse_world_envelope(env)
    assert warnings == []
    assert set(normalized) == {"version", "identity", "situation", "lineage"}


# ================================================================ refusals

def test_an_unsupported_protocol_version_refuses_before_any_record_is_checked():
    env = _valid()
    env["version"] = 2
    env["identity"] = {"this is": "deliberately malformed too"}
    try:
        w.parse_world_envelope(env)
        assert False, "expected a WorldIRError"
    except w.WorldIRError as e:
        assert e.tag == "unsupported-world-protocol-version"
        assert "2" in e.detail and "1" in e.detail


def test_a_missing_version_field_also_refuses():
    env = _valid()
    del env["version"]
    try:
        w.parse_world_envelope(env)
        assert False, "expected a WorldIRError"
    except w.WorldIRError as e:
        assert e.tag == "unsupported-world-protocol-version"


def test_a_missing_critical_record_refuses_by_name():
    env = _valid()
    del env["lineage"]
    try:
        w.parse_world_envelope(env)
        assert False, "expected a WorldIRError"
    except w.WorldIRError as e:
        assert e.tag == "missing-critical-record"
        assert "lineage" in e.detail


def test_a_malformed_critical_record_field_refuses_and_names_the_field():
    env = _valid()
    env["identity"]["schemaVersion"] = "one"
    try:
        w.parse_world_envelope(env)
        assert False, "expected a WorldIRError"
    except w.WorldIRError as e:
        assert e.tag == "malformed-critical-record"
        assert "identity" in e.detail and "schemaVersion" in e.detail


def test_a_critical_record_missing_a_required_field_refuses():
    env = _valid()
    del env["situation"]["x"]
    try:
        w.parse_world_envelope(env)
        assert False, "expected a WorldIRError"
    except w.WorldIRError as e:
        assert e.tag == "malformed-critical-record"
        assert "situation" in e.detail and "missing" in e.detail


def test_a_malformed_known_optional_record_refuses_not_warns():
    env = _valid()
    env["behavior"]["timerTicks"] = "soon"
    try:
        w.parse_world_envelope(env)
        assert False, "expected a WorldIRError"
    except w.WorldIRError as e:
        assert e.tag == "malformed-optional-record"
        assert "behavior" in e.detail and "timerTicks" in e.detail


def test_a_non_record_envelope_refuses():
    try:
        w.parse_world_envelope([1, 2, 3])
        assert False, "expected a WorldIRError"
    except w.WorldIRError as e:
        assert e.tag == "malformed-world-envelope"


# ============================================================= warn-and-ignore

def test_an_unknown_optional_record_warns_and_is_dropped_not_refused():
    env = _valid()
    env["annotation"] = {"note": "not part of world-v1"}
    normalized, warnings = w.parse_world_envelope(env)
    assert warnings == ["unknown-optional-record:annotation"]
    assert "annotation" not in normalized


def test_unknown_and_malformed_are_different_cases():
    """An unknown record and a malformed known-optional record must not be
    conflated: the first warns, the second refuses, even in the same
    envelope."""
    env = _valid()
    env["annotation"] = {"note": "unknown"}
    env["behavior"]["timerTicks"] = "soon"
    try:
        w.parse_world_envelope(env)
        assert False, "expected a WorldIRError from the malformed optional record"
    except w.WorldIRError as e:
        assert e.tag == "malformed-optional-record"


# ================================================================= no coercion

def test_a_wrong_typed_field_is_never_coerced():
    env = _valid()
    env["situation"]["occupancy"] = "0"  # text, not the declared integer
    try:
        w.parse_world_envelope(env)
        assert False, "expected a WorldIRError"
    except w.WorldIRError as e:
        assert e.tag == "malformed-critical-record"


def test_a_boolean_field_rejects_an_integer_look_alike():
    env = _valid()
    env["situation"]["chunkActive"] = 1  # not True/False
    try:
        w.parse_world_envelope(env)
        assert False, "expected a WorldIRError"
    except w.WorldIRError as e:
        assert e.tag == "malformed-critical-record"
        assert "chunkActive" in e.detail


def test_an_integer_field_rejects_a_true_fraction():
    env = _valid()
    env["identity"]["schemaVersion"] = 1.5
    try:
        w.parse_world_envelope(env)
        assert False, "expected a WorldIRError"
    except w.WorldIRError as e:
        assert "schemaVersion" in e.detail


def test_normalized_number_rejects_out_of_range():
    env = _valid()
    env["expression"]["depth"] = 1.2
    try:
        w.parse_world_envelope(env)
        assert False, "expected a WorldIRError"
    except w.WorldIRError as e:
        assert "depth" in e.detail


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
