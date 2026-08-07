"""world_snapshot.py — durable capture of a world value (Horizon Phase 0
Build 3, Phase 3 — spec §13.3, §22).

A snapshot bundles a normalized world-v1 envelope with the revision it is at
and a semantic-snapshot hash (reusing `world_delta.semantic_hash` — the same
SHA-256-over-canonical-form discipline Phase 1's deltas already use), and is
persisted through the host's existing, optional `snapshot` capability
(host.py) — off by default, a no-op on a host that keeps nothing, exactly as
`record` is. No new host method: `host.snapshot(fingerprint, entry)` already
takes an opaque fingerprint and an opaque entry, and a captured world
snapshot fits that shape without needing anything host.py does not already
provide.

Versioned by world-v1.json's version (spec §13.1's "unsupported protocol
version refuses" contract), not a second, parallel format-version field:
`restore_snapshot` re-validates the snapshot's own envelope through
`world_ir.parse_world_envelope`, so an unrecognized world-v1 protocol
version refuses exactly as it would refuse at first parse — reusing the one
version check that already exists instead of adding a duplicate. Refuse,
don't guess: a malformed snapshot wrapper, an unsupported protocol version,
or a semantic hash that no longer matches its own envelope's canonical form
all refuse, naming which — recovery (world_recovery.py) never trusts a
snapshot it cannot verify.
"""
from world_delta import semantic_hash
from world_ir import WorldIRError, parse_world_envelope

REQUIRED_KEYS = ("revision", "envelope", "semantic_hash")


class WorldSnapshotError(Exception):
    """A refusal naming the snapshot rule it broke — the same tag/detail/
    fix shape `world_ir.WorldIRError` and `world_event_log.WorldEventLogError`
    carry."""

    def __init__(self, tag, detail, fix):
        self.tag = tag
        self.detail = detail
        self.fix = fix
        super().__init__(f"{tag}: {detail}")


def capture_snapshot(envelope, revision, host=None):
    """Capture `envelope` (already normalized by `parse_world_envelope`) at
    `revision`, persisting through `host.snapshot` if `host` is given. The
    fingerprint host.snapshot receives is the envelope's own semantic
    hash — content-addressed, matching the retention window's own
    fingerprint-keyed `snapshot` calling convention (interp.py's `_seal`)."""
    h = semantic_hash(envelope)
    snap = {"revision": revision, "envelope": envelope, "semantic_hash": h}
    if host is not None:
        host.snapshot(h, snap)
    return snap


def restore_snapshot(snap):
    """Validate `snap` and return `(normalized_envelope, revision)`.

    Refuses (raises `WorldSnapshotError`) on: a malformed wrapper missing a
    required key; an envelope that fails world-v1 validation, including an
    unsupported protocol version; or a stored `semantic_hash` that no
    longer matches a freshly computed hash of the envelope — corruption
    detected the same way the event log's chain detects a tampered entry,
    by recomputing rather than trusting the stored value.
    """
    for key in REQUIRED_KEYS:
        if key not in snap:
            raise WorldSnapshotError(
                "malformed-snapshot",
                f"snapshot is missing '{key}'",
                f"a snapshot must carry all of {REQUIRED_KEYS} — regenerate it with "
                "capture_snapshot rather than hand-building the wrapper")

    try:
        normalized, _warnings = parse_world_envelope(snap["envelope"])
    except WorldIRError as e:
        raise WorldSnapshotError(
            "invalid-snapshot-envelope",
            f"snapshot's envelope fails world-v1 validation: {e.detail}",
            "recover from an earlier valid snapshot instead of trusting this one") from e

    if semantic_hash(normalized) != snap["semantic_hash"]:
        raise WorldSnapshotError(
            "snapshot-hash-mismatch",
            "snapshot's semantic_hash does not match its own envelope's canonical "
            "form — the snapshot may be corrupted",
            "recover from an earlier valid snapshot instead of trusting this one")

    return normalized, snap["revision"]
