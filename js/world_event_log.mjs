// js/world_event_log.mjs — the host-owned, append-only, hash-chained
// committed event log. Mirrors world_event_log.py field for field; see that
// file's module docstring for the full T-Q-Horizon decision rationale.
//
// Hashing reuses sha256Hex (js/sha256.mjs) — the same primitive
// js/interp.mjs's `_seal` mirror uses — never a language builtin.

import { sha256Hex } from "./sha256.mjs";
import { canonicalDeltaString } from "./world_delta.mjs";

export const EVENT_LOG_FORMAT_VERSION = 1;
export const GENESIS_HASH = "0".repeat(64);

export class WorldEventLogError extends Error {
  constructor(tag, detail, fix) {
    super(`${tag}: ${detail}`);
    this.tag = tag;
    this.detail = detail;
    this.fix = fix;
  }
}

// Deterministic, cross-implementation-stable text form of a plain
// JSON-shaped value: sorted object keys, no whitespace — mirrors Python's
// `json.dumps(value, sort_keys=True, separators=(",", ":"))` exactly (see
// world_event_log.py's own `_canonical_event_string`), so an identical
// logical event produces an identical string, and therefore an identical
// hash, in either implementation regardless of the two languages' own
// differing object/dict key-insertion-order conventions.
function canonicalEventString(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalEventString).join(",")}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalEventString(value[k])}`).join(",")}}`;
}

// Deterministic text form of everything in `entry` EXCEPT its own `hash`
// field — the hash is computed FROM this string. Reuses
// canonicalDeltaString for the payload's `delta` sub-object.
function canonicalEntryString(entry) {
  const p = entry.payload;
  const lines = [
    `format: ${entry.format}`,
    `sequence: ${entry.sequence}`,
    `previous-hash: ${entry.previousHash}`,
    `when: ${entry.when}`,
    `receipt: ${entry.receipt !== null && entry.receipt !== undefined ? entry.receipt : "<none>"}`,
    `tick: ${p.tick}`,
    `actor: ${p.actor}`,
    `affected-subjects: ${p.affectedSubjects.join(",")}`,
    `rationale: ${p.rationale}`,
  ];
  if (p.delta === null || p.delta === undefined) {
    lines.push("delta: <none>");
  } else {
    lines.push("delta:");
    for (const line of canonicalDeltaString(p.delta).split("\n")) lines.push(`  ${line}`);
  }
  // OPTIONAL, ADDITIVE (Horizon Phase 2 Build 2's own gap-fix). A world-v1
  // caller's payload always carries a real `delta` and never sets `event` —
  // for those payloads this line never appears, so their canonical string
  // and every hash it feeds is BYTE IDENTICAL to before this field existed.
  // The gap this closes: a scene-intent crossing's applied input has no
  // facet-patch delta to log (see main.mjs's own scene-intent path — there
  // is no fold, the program re-emits its full scene every tick), but replay
  // still needs the real typed event object back, not just a human-
  // readable rationale string, to feed the correct per-tick events batch
  // into `advance`. `event`, when present, is arbitrary JSON-shaped data
  // the caller controls the key order of — this is not a general
  // canonicalizer, callers must construct their event objects with a
  // consistent field order (as a_crossing.planes's own UI events already
  // do) for the hash to be reproducible across an identical event.
  if (p.event !== null && p.event !== undefined) {
    lines.push(`event: ${canonicalEventString(p.event)}`);
  }
  return lines.join("\n");
}

export function entryHash(entry) {
  return sha256Hex(canonicalEntryString(entry));
}

// Pure: given the existing ordered entry list (never mutated), builds and
// returns the NEXT entry — sequence and previous-hash derived from
// `events`' own last element.
export function appendEvent(events, payload, when, receipt = null) {
  const sequence = events.length;
  const previousHash = events.length > 0 ? events[events.length - 1].hash : GENESIS_HASH;
  const entry = {
    format: EVENT_LOG_FORMAT_VERSION,
    sequence,
    previousHash,
    when,
    receipt,
    payload,
  };
  entry.hash = entryHash(entry);
  return entry;
}

// Recompute the hash chain over `events` (any ordered list of entry
// objects). Returns [true, null] if consistent, else [false, index] naming
// the first entry where the chain breaks.
export function verifyChain(events) {
  let expectedPrevious = GENESIS_HASH;
  for (let i = 0; i < events.length; i++) {
    const entry = events[i];
    if (entry.previousHash !== expectedPrevious) return [false, i];
    const { hash, ...withoutHash } = entry;
    if (entryHash(withoutHash) !== hash) return [false, i];
    expectedPrevious = entry.hash;
  }
  return [true, null];
}

export function eventsToJson(events) {
  return { format: EVENT_LOG_FORMAT_VERSION, events };
}

export function eventsFromJson(doc) {
  const version = doc.format;
  if (version !== EVENT_LOG_FORMAT_VERSION) {
    throw new WorldEventLogError(
      "unrecognized-event-log-format",
      `event log format ${JSON.stringify(version ?? null)} is not ${EVENT_LOG_FORMAT_VERSION}`,
      "regenerate the event log with a version of planes matching this reader's "
        + "event log format — if the log is newer than what this reads, upgrade "
        + "planes instead of regenerating the log",
    );
  }
  return doc.events;
}

// The append-only ledger. `host` is optional (host.mjs's `appendEvent`, a
// no-op by default) — a host that keeps nothing still runs every existing
// test unchanged, the same tier record/snapshot already occupy.
export class WorldEventLog {
  constructor(host = null) {
    this._host = host;
    this._events = [];
  }

  append(payload, when, receipt = null) {
    const entry = appendEvent(this._events, payload, when, receipt);
    this._events.push(entry);
    if (this._host !== null) this._host.appendEvent(entry);
    return entry;
  }

  // A defensive deep copy — read-only by construction, not by convention.
  events() {
    return structuredClone(this._events);
  }

  verify() {
    return verifyChain(this._events);
  }
}
