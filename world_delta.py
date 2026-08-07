"""world_delta.py — the Python monotonic delta between two world-v1 envelopes.

Horizon Phase 0 Build 3, Phase 1 (spec §9.3). `compute_delta` takes two
envelopes already normalized by `world_ir.parse_world_envelope` — the exact
shape `WorldRuntime.envelope` returns per tick — and produces a delta record:
created/removed subjects, per-facet field patches, relation adds/removes, a
revision counter, and a semantic-snapshot hash of the next envelope's
canonical form.

Single-subject scope. Build 1/2's actual world-v1 shape is one subject per
envelope (`identity` is critical and carries exactly one `id`), not a
collection of many subjects — `grammar/protocols/world-v1.json`'s records are
flat, not keyed lists. "Created subject" / "removed subject" therefore means
the envelope's own `identity.id` changing between tick N and N+1: the same id
on both sides is one subject continuing (facet patches apply); a different id
is that subject replaced wholesale (no field-level correspondence between two
different subjects, so no patches are computed for that transition — only the
create/remove pair). This generalizes cleanly to a future multi-subject
envelope without inventing behavior this build has no data to test.

Determinism. Every walk is in `FACET_ORDER`/`FIELD_ORDER` (world_ir.py's own
fixed tuples), never raw dict iteration — the same discipline that makes
`canonical_outcome_string` byte-identical across implementations extends here
via `canonical_delta_string`, and `test_world_delta_conformance.py` is what
holds Python and JS (js/world_delta.mjs) to actual agreement rather than
asserted agreement.

Hashing reuses `hashlib.sha256` — the same primitive `interp.py`'s `_seal`
already uses and `js/sha256.mjs` mirrors — over `canonical_outcome_string`'s
text form, not a JSON structure. No `hash` builtin: this module runs at the
host/driver layer, outside the language the interpreter evaluates.
"""
import hashlib

from world_ir import FACET_ORDER, FIELD_ORDER

RELATION_FACET = "relation"


def _format_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def semantic_hash(envelope):
    """SHA-256 hex digest over `envelope`'s canonical outcome string —
    the "semantic snapshot hash" spec §9.3 asks a delta to declare after
    application. Full 64-char digest, not a truncated fingerprint: this
    hash feeds the event log's hash chain and the snapshot's corruption
    check (Phases 2-3), where collision resistance matters in a way
    `_seal`'s in-run comparison fingerprint does not need to."""
    from world_ir import canonical_outcome_string
    return hashlib.sha256(canonical_outcome_string(envelope).encode()).hexdigest()


def _subject_id(envelope):
    return envelope["identity"]["id"]


def _facet_field_patches(facet, subject_id, prev_fields, next_fields):
    """Field-level patches for one facet present (however partially, via
    the absent sentinel) on at least one side. `prev_fields`/`next_fields`
    are `None` when the facet is absent on that side — every field
    transitions from/to the absent sentinel uniformly, so a whole facet
    appearing or disappearing is represented by the same per-field patch
    shape a single changed field is, not a second bucket."""
    patches = []
    for field in FIELD_ORDER[facet]:
        old = prev_fields[field] if prev_fields is not None else None
        new = next_fields[field] if next_fields is not None else None
        if prev_fields is not None and next_fields is not None and old == new:
            continue
        if prev_fields is None and next_fields is None:
            continue
        patches.append({"facet": facet, "id": subject_id, "field": field, "old": old, "new": new})
    return patches


def compute_delta(prev_envelope, next_envelope, prev_revision):
    """Diff two normalized world-v1 envelopes into a monotonic delta.

    `prev_revision` is the revision number `prev_envelope` is at; the
    returned delta's `revision_to` is always `prev_revision + 1`,
    regardless of whether anything actually changed — advancing the
    counter is the driver's job (one delta per tick), not a function of
    content.
    """
    prev_id = _subject_id(prev_envelope)
    next_id = _subject_id(next_envelope)

    delta = {
        "revision_from": prev_revision,
        "revision_to": prev_revision + 1,
        "created_subjects": [],
        "removed_subjects": [],
        "facet_patches": [],
        "relations_added": [],
        "relations_removed": [],
        "semantic_hash": semantic_hash(next_envelope),
    }

    if prev_id != next_id:
        delta["created_subjects"] = [next_id]
        delta["removed_subjects"] = [prev_id]
        return delta

    for facet in FACET_ORDER:
        prev_fields = prev_envelope.get(facet)
        next_fields = next_envelope.get(facet)
        if facet == RELATION_FACET:
            if prev_fields is None and next_fields is not None:
                delta["relations_added"].append(dict(next_fields))
            elif prev_fields is not None and next_fields is None:
                delta["relations_removed"].append(dict(prev_fields))
            elif prev_fields is not None and next_fields is not None:
                if prev_fields["relationId"] != next_fields["relationId"]:
                    delta["relations_removed"].append(dict(prev_fields))
                    delta["relations_added"].append(dict(next_fields))
                else:
                    delta["facet_patches"].extend(
                        _facet_field_patches(facet, next_id, prev_fields, next_fields))
            continue
        delta["facet_patches"].extend(
            _facet_field_patches(facet, next_id, prev_fields, next_fields))

    return delta


def _format_relation(record):
    return ",".join(
        f"{field}={_format_value(record[field])}" for field in FIELD_ORDER[RELATION_FACET])


def canonical_delta_string(delta):
    """The cross-implementation comparison form
    `test_world_delta_conformance.py` checks byte-for-byte — a hand-built,
    fixed-order text form, the same discipline `canonical_outcome_string`
    established for envelopes."""
    lines = [
        f"revision: {delta['revision_from']} -> {delta['revision_to']}",
        f"created-subjects: {','.join(delta['created_subjects'])}",
        f"removed-subjects: {','.join(delta['removed_subjects'])}",
    ]
    for patch in delta["facet_patches"]:
        lines.append(
            f"facet-patch: {patch['facet']}.{patch['field']} id={patch['id']} "
            f"old={_format_value(patch['old']) if patch['old'] is not None else '<absent>'} "
            f"new={_format_value(patch['new']) if patch['new'] is not None else '<absent>'}")
    for record in delta["relations_added"]:
        lines.append(f"relation-added: {_format_relation(record)}")
    for record in delta["relations_removed"]:
        lines.append(f"relation-removed: {_format_relation(record)}")
    lines.append(f"semantic-hash: {delta['semantic_hash']}")
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    import sys

    payload = json.load(sys.stdin)
    result = compute_delta(payload["prev"], payload["next"], payload["revision"])
    sys.stdout.write(canonical_delta_string(result))
