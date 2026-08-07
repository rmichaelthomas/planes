"""world_event_log.py — the host-owned, append-only, hash-chained committed
event log (Horizon Phase 0 Build 3, Phase 2 — spec §13.1-13.2).

THE LOCKED T-Q-HORIZON DECISION, in code: the committed-event log is a
host-owned, append-only, hash-chained store, NOT a Planes list. The value
plane has no `hash` builtin and cannot chain events by content — that is the
whole finding behind the decision. Each event's semantic PAYLOAD (tick,
actor, delta, affected subjects, rationale) is ordinary data derived from a
traced world value; its integrity ENVELOPE (monotonic sequence, previous-
event hash, an opaque authorization receipt, a witnessed `when`) is added
here, entirely outside the language the interpreter evaluates. This module
computes the hash chain in Python, reusing `hashlib.sha256` — the same
primitive `interp.py`'s `_seal` already uses and `js/sha256.mjs` mirrors —
never a language builtin.

Two layers:
  - `append_event`/`verify_chain` — pure functions over a plain list of
    entry dicts, so a host's durably-persisted log can be re-verified after
    reload, independent of any particular `WorldEventLog` instance's
    lifetime (Phase 3's recovery reads a log this way).
  - `WorldEventLog` — the stateful convenience wrapper most callers use: an
    in-memory ordered ledger, appending through the pure functions above and
    forwarding each new entry to the OPTIONAL `host.append_event` (host.py)
    for durability, the same tier `record`/`snapshot` already occupy. Its
    public surface is exactly `append`/`events`/`verify` — no update, no
    delete, no mutate. Undo/redo (§13.3) are appended inverse events plus
    snapshot-and-replay recovery, never destructive history deletion.
"""
import copy
import hashlib

from world_delta import canonical_delta_string

EVENT_LOG_FORMAT_VERSION = 1
GENESIS_HASH = "0" * 64


class WorldEventLogError(Exception):
    """A refusal naming the event-log rule it broke — the same tag/detail/
    fix shape `world_ir.WorldIRError` and `interp.py`'s `PlanesError`
    carry."""

    def __init__(self, tag, detail, fix):
        self.tag = tag
        self.detail = detail
        self.fix = fix
        super().__init__(f"{tag}: {detail}")


def _canonical_entry_string(entry):
    """Deterministic text form of everything in `entry` EXCEPT its own
    `hash` field — the hash is computed FROM this string, so it cannot be
    an input to itself. Reuses `canonical_delta_string` for the payload's
    `delta` sub-object rather than a second serializer."""
    payload = entry["payload"]
    lines = [
        f"format: {entry['format']}",
        f"sequence: {entry['sequence']}",
        f"previous-hash: {entry['previous_hash']}",
        f"when: {entry['when']}",
        f"receipt: {entry['receipt'] if entry['receipt'] is not None else '<none>'}",
        f"tick: {payload['tick']}",
        f"actor: {payload['actor']}",
        f"affected-subjects: {','.join(payload['affected_subjects'])}",
        f"rationale: {payload['rationale']}",
    ]
    if payload["delta"] is None:
        lines.append("delta: <none>")
    else:
        lines.append("delta:")
        lines.extend(f"  {line}" for line in canonical_delta_string(payload["delta"]).splitlines())
    return "\n".join(lines)


def _entry_hash(entry):
    return hashlib.sha256(_canonical_entry_string(entry).encode()).hexdigest()


def append_event(events, payload, when, receipt=None):
    """Pure: given the existing ordered entry list (never mutated), builds
    and returns the NEXT entry — sequence and previous-hash derived from
    `events`' own last element, never from external bookkeeping. The
    caller appends the returned entry; this function never does, which is
    what keeps it usable both by `WorldEventLog.append` and directly by a
    recovery path re-deriving a log's expected next entry."""
    sequence = len(events)
    previous_hash = events[-1]["hash"] if events else GENESIS_HASH
    entry = {
        "format": EVENT_LOG_FORMAT_VERSION,
        "sequence": sequence,
        "previous_hash": previous_hash,
        "when": when,
        "receipt": receipt,
        "payload": payload,
    }
    entry["hash"] = _entry_hash(entry)
    return entry


def verify_chain(events):
    """Recompute the hash chain over `events` (any ordered list of entry
    dicts — not necessarily one a live `WorldEventLog` produced, so a
    host's reloaded, persisted log can be checked too). Returns
    `(True, None)` if every entry's `previous_hash` links to the prior
    entry's own recomputed hash and every entry's own `hash` matches its
    recomputed content; otherwise `(False, index)` naming the first entry
    where the chain breaks — a mutated earlier entry breaks its own slot
    (hash mismatch) or the next one (previous-hash mismatch), whichever
    comes first in sequence order."""
    expected_previous = GENESIS_HASH
    for i, entry in enumerate(events):
        if entry["previous_hash"] != expected_previous:
            return False, i
        recomputed = _entry_hash({k: v for k, v in entry.items() if k != "hash"})
        if recomputed != entry["hash"]:
            return False, i
        expected_previous = entry["hash"]
    return True, None


def events_to_json(events):
    return {"format": EVENT_LOG_FORMAT_VERSION, "events": events}


def events_from_json(doc):
    """The refuse-don't-guess half of the contract, mirroring
    `interp.py`'s `records_from_json`: an unrecognized format version is
    rejected, not silently reinterpreted."""
    version = doc.get("format")
    if version != EVENT_LOG_FORMAT_VERSION:
        raise WorldEventLogError(
            "unrecognized-event-log-format",
            f"event log format {version!r} is not {EVENT_LOG_FORMAT_VERSION}",
            "regenerate the event log with a version of planes matching this "
            "reader's event log format — if the log is newer than what this "
            "reads, upgrade planes instead of regenerating the log")
    return doc["events"]


class WorldEventLog:
    """The append-only ledger. `host` is optional (host.py's
    `append_event`, a no-op by default) — a host that keeps nothing still
    runs every existing test unchanged, the same tier `record`/`snapshot`
    already occupy."""

    def __init__(self, host=None):
        self._host = host
        self._events = []

    def append(self, payload, when, receipt=None):
        entry = append_event(self._events, payload, when, receipt)
        self._events.append(entry)
        if self._host is not None:
            self._host.append_event(entry)
        return entry

    def events(self):
        """A defensive deep copy — the returned list is not a window onto
        `self._events`, so nothing reachable from this call can mutate the
        log. Read-only by construction, not by convention."""
        return copy.deepcopy(self._events)

    def verify(self):
        return verify_chain(self._events)
