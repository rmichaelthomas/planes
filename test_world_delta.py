"""test_world_delta.py — Horizon Phase 0 Build 3, Phase 1.

Covers the build prompt's §3 acceptance: `compute_delta` diffs two
normalized world-v1 envelopes (the shape `world_ir.parse_world_envelope`
already returns, and the shape `WorldRuntime.envelope` already produces per
tick) into a monotonic revision delta — created/removed subjects, per-facet
field patches, relation adds/removes, a revision counter, and a semantic
snapshot hash — in `FACET_ORDER`/`FIELD_ORDER`, so the result never depends
on dict iteration order. `test_world_delta_conformance.py` is the
byte-identical-with-JS half of this gate; this file is Python-only
correctness and determinism.
"""
import copy
import sys

import world_delta as d
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
    "lineage": {
        "corpusSource": "ala-eriri", "culturalStatus": "canonical",
        "author": "studio", "origin": "system", "because": "canonical corpus asset",
        "agreementFingerprint": "fp-1", "permittedTransformations": "remix",
        "publishingRestriction": "none", "systemBoundary": "immutable",
    },
}

RELATION_A = {
    "relationId": "rel-1", "relationType": "near", "fromId": "subject-1",
    "toId": "landing-1", "provenance": "authored",
}

RELATION_B = {
    "relationId": "rel-2", "relationType": "far", "fromId": "subject-1",
    "toId": "landing-2", "provenance": "authored",
}


def _valid():
    return copy.deepcopy(VALID_ENVELOPE)


def _normalized(envelope):
    normalized, warnings = w.parse_world_envelope(envelope)
    assert warnings == []
    return normalized


# ================================================================ no-op delta

def test_identical_envelopes_produce_an_empty_delta_but_advance_revision():
    env = _normalized(_valid())
    delta = d.compute_delta(env, env, 0)
    assert delta["revision_from"] == 0
    assert delta["revision_to"] == 1
    assert delta["created_subjects"] == []
    assert delta["removed_subjects"] == []
    assert delta["facet_patches"] == []
    assert delta["relations_added"] == []
    assert delta["relations_removed"] == []
    assert delta["semantic_hash"] == d.semantic_hash(env)


def test_revision_counter_is_monotonic_across_a_chain():
    env = _normalized(_valid())
    revision = 0
    for _ in range(5):
        delta = d.compute_delta(env, env, revision)
        assert delta["revision_from"] == revision
        assert delta["revision_to"] == revision + 1
        revision = delta["revision_to"]
    assert revision == 5


# ================================================================ facet patches

def test_a_changed_field_produces_one_facet_patch():
    prev = _normalized(_valid())
    next_env = _normalized(_valid())
    next_env["situation"] = dict(next_env["situation"], x=11)
    delta = d.compute_delta(prev, next_env, 0)
    assert delta["facet_patches"] == [
        {"facet": "situation", "id": "subject-1", "field": "x", "old": 10, "new": 11},
    ]


def test_multiple_changed_fields_are_ordered_by_facet_then_field_order():
    prev = _normalized(_valid())
    next_env = _normalized(_valid())
    next_env["situation"] = dict(next_env["situation"], y=0, x=11)
    next_env["identity"] = dict(next_env["identity"], displayName="Reso II")
    delta = d.compute_delta(prev, next_env, 0)
    # identity precedes situation in FACET_ORDER; within situation, x precedes y.
    assert delta["facet_patches"] == [
        {"facet": "identity", "id": "subject-1", "field": "displayName",
         "old": "Reso", "new": "Reso II"},
        {"facet": "situation", "id": "subject-1", "field": "x", "old": 10, "new": 11},
        {"facet": "situation", "id": "subject-1", "field": "y", "old": -5, "new": 0},
    ]


def test_an_optional_facet_appearing_is_a_patch_from_absent():
    prev = _normalized(_valid())
    env_with_relation = _valid()
    env_with_relation["relation"] = dict(RELATION_A)
    next_env = _normalized(env_with_relation)
    delta = d.compute_delta(prev, next_env, 0)
    assert delta["relations_added"] == [dict(RELATION_A)]
    assert delta["relations_removed"] == []
    assert delta["facet_patches"] == []


def test_an_optional_facet_disappearing_is_a_patch_to_absent():
    env_with_relation = _valid()
    env_with_relation["relation"] = dict(RELATION_A)
    prev = _normalized(env_with_relation)
    next_env = _normalized(_valid())
    delta = d.compute_delta(prev, next_env, 0)
    assert delta["relations_removed"] == [dict(RELATION_A)]
    assert delta["relations_added"] == []


def test_a_non_relation_optional_facet_appearing_patches_every_field_from_absent():
    prev = _normalized(_valid())
    env_with_behavior = _valid()
    env_with_behavior["behavior"] = {
        "eventPattern": "arrival", "transition": "docked", "timerTicks": 100,
        "condition": "always", "stateMachine": "dock-cycle",
        "emittedEvent": "docked", "failurePath": "resync",
    }
    next_env = _normalized(env_with_behavior)
    delta = d.compute_delta(prev, next_env, 0)
    fields = {p["field"]: (p["old"], p["new"]) for p in delta["facet_patches"]}
    assert all(p["facet"] == "behavior" for p in delta["facet_patches"])
    assert fields["eventPattern"] == (None, "arrival")
    assert fields["timerTicks"] == (None, 100)
    assert len(delta["facet_patches"]) == 7


# ================================================================ relations

def test_relation_field_change_with_same_relation_id_is_a_facet_patch():
    env_a = _valid()
    env_a["relation"] = dict(RELATION_A)
    prev = _normalized(env_a)
    env_b = _valid()
    env_b["relation"] = dict(RELATION_A, provenance="derived")
    next_env = _normalized(env_b)
    delta = d.compute_delta(prev, next_env, 0)
    assert delta["relations_added"] == []
    assert delta["relations_removed"] == []
    assert delta["facet_patches"] == [
        {"facet": "relation", "id": "subject-1", "field": "provenance",
         "old": "authored", "new": "derived"},
    ]


def test_relation_id_change_is_remove_old_add_new_not_a_patch():
    env_a = _valid()
    env_a["relation"] = dict(RELATION_A)
    prev = _normalized(env_a)
    env_b = _valid()
    env_b["relation"] = dict(RELATION_B)
    next_env = _normalized(env_b)
    delta = d.compute_delta(prev, next_env, 0)
    assert delta["relations_removed"] == [dict(RELATION_A)]
    assert delta["relations_added"] == [dict(RELATION_B)]
    assert delta["facet_patches"] == []


# ================================================================ created/removed subjects

def test_a_changed_identity_id_is_a_subject_replace_not_a_patch():
    prev = _normalized(_valid())
    env_b = _valid()
    env_b["identity"] = dict(env_b["identity"], id="subject-2")
    next_env = _normalized(env_b)
    delta = d.compute_delta(prev, next_env, 0)
    assert delta["created_subjects"] == ["subject-2"]
    assert delta["removed_subjects"] == ["subject-1"]
    assert delta["facet_patches"] == []
    assert delta["relations_added"] == []
    assert delta["relations_removed"] == []


# ================================================================ semantic hash

def test_semantic_hash_matches_hash_of_next_envelopes_canonical_form():
    prev = _normalized(_valid())
    next_env = _normalized(_valid())
    next_env["situation"] = dict(next_env["situation"], x=99)
    delta = d.compute_delta(prev, next_env, 0)
    assert delta["semantic_hash"] == d.semantic_hash(next_env)
    assert delta["semantic_hash"] != d.semantic_hash(prev)


def test_semantic_hash_is_a_64_char_hex_sha256_digest():
    env = _normalized(_valid())
    h = d.semantic_hash(env)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ================================================================ canonical string / determinism

def test_canonical_delta_string_is_deterministic_regardless_of_dict_construction_order():
    prev = _normalized(_valid())
    next_a = _normalized(_valid())
    next_a["situation"] = dict(next_a["situation"], x=11)
    delta_a = d.compute_delta(prev, next_a, 0)

    # Build an equal-but-differently-ordered next envelope (dict insertion
    # order reversed) — the canonical string must not depend on it.
    env_b = _valid()
    env_b["situation"] = {k: env_b["situation"][k] for k in reversed(list(env_b["situation"]))}
    env_b["situation"]["x"] = 11
    next_b = _normalized(env_b)
    delta_b = d.compute_delta(prev, next_b, 0)

    assert d.canonical_delta_string(delta_a) == d.canonical_delta_string(delta_b)


def test_the_gate_is_capable_of_failing():
    """The failability proof named in the build prompt (§N+3.2): the
    comparison itself must be able to observe a real divergence, not
    vacuously agree on mismatched strings."""
    prev = _normalized(_valid())
    next_env = _normalized(_valid())
    next_env["situation"] = dict(next_env["situation"], x=11)
    delta = d.compute_delta(prev, next_env, 0)
    real = d.canonical_delta_string(delta)
    tampered = real.replace("x", "z", 1)
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
