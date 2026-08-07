// js/test/world_event_log.test.mjs — Horizon Phase 0 Build 3, Phase 2.
//
// Mirrors test_world_event_log.py's cases for the host-owned, append-only,
// hash-chained committed-event log.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  WorldEventLog, appendEvent, verifyChain, eventsToJson, eventsFromJson,
  entryHash, GENESIS_HASH, WorldEventLogError,
} from "../world_event_log.mjs";
import { computeDelta } from "../world_delta.mjs";
import { parseWorldEnvelope } from "../world_ir.mjs";
import { Host, TestHost } from "../host.mjs";

const VALID_ENVELOPE = {
  version: 1,
  identity: {
    id: "subject-1", kind: "vehicle", subkind: "hydrofoil",
    displayName: "Reso", status: "canonical", schemaVersion: 1,
  },
  situation: {
    containingPlace: "landing-1", space: "world", x: 0, y: 0,
    state: "docked", occupancy: 0, anchorId: "anchor-1",
    chunkActive: true, physicsRef: "phys-1", audioRef: "audio-1",
  },
  lineage: {
    corpusSource: "ala-eriri", culturalStatus: "canonical",
    author: "studio", origin: "system", because: "canonical corpus asset",
    agreementFingerprint: "fp-1", permittedTransformations: "remix",
    publishingRestriction: "none", systemBoundary: "immutable",
  },
};

function norm() {
  const { normalized, warnings } = parseWorldEnvelope(structuredClone(VALID_ENVELOPE));
  assert.deepEqual(warnings, []);
  return normalized;
}

function delta(xFrom, xTo) {
  const prev = norm();
  prev.situation = { ...prev.situation, x: xFrom };
  const nextEnv = norm();
  nextEnv.situation = { ...nextEnv.situation, x: xTo };
  return computeDelta(prev, nextEnv, xFrom);
}

function payload(tick, xFrom, xTo, rationale = "advance") {
  return {
    tick, actor: "system", delta: delta(xFrom, xTo),
    affectedSubjects: ["subject-1"], rationale,
  };
}

// ---- append / sequence / chain ----------------------------------------

test("append assigns monotonic sequence numbers", () => {
  const log = new WorldEventLog();
  const e0 = log.append(payload(0, 0, 1), 1000000.0);
  const e1 = log.append(payload(1, 1, 2), 1000001.0);
  const e2 = log.append(payload(2, 2, 3), 1000002.0);
  assert.deepEqual([e0.sequence, e1.sequence, e2.sequence], [0, 1, 2]);
});

test("first event's previous hash is the genesis hash", () => {
  const log = new WorldEventLog();
  const e0 = log.append(payload(0, 0, 1), 1000000.0);
  assert.equal(e0.previousHash, GENESIS_HASH);
});

test("each event's previous hash is the prior's own hash", () => {
  const log = new WorldEventLog();
  const e0 = log.append(payload(0, 0, 1), 1000000.0);
  const e1 = log.append(payload(1, 1, 2), 1000001.0);
  const e2 = log.append(payload(2, 2, 3), 1000002.0);
  assert.equal(e1.previousHash, e0.hash);
  assert.equal(e2.previousHash, e1.hash);
});

test("a valid chain verifies", () => {
  const log = new WorldEventLog();
  for (let i = 0; i < 5; i++) log.append(payload(i, i, i + 1), 1000000.0 + i);
  const [ok, badIndex] = log.verify();
  assert.equal(ok, true);
  assert.equal(badIndex, null);
});

test("receipt is opaque and passed through unchanged", () => {
  const log = new WorldEventLog();
  const e0 = log.append(payload(0, 0, 1), 1000000.0, "opaque-token-123");
  assert.equal(e0.receipt, "opaque-token-123");
});

test("receipt defaults to null", () => {
  const log = new WorldEventLog();
  const e0 = log.append(payload(0, 0, 1), 1000000.0);
  assert.equal(e0.receipt, null);
});

// ---- tamper detection ---------------------------------------------------

test("tampering an earlier event's payload is caught at its own slot", () => {
  const log = new WorldEventLog();
  for (let i = 0; i < 4; i++) log.append(payload(i, i, i + 1), 1000000.0 + i);
  const tampered = structuredClone(log.events());
  tampered[1].payload.rationale = "forged";
  const [ok, badIndex] = verifyChain(tampered);
  assert.equal(ok, false);
  assert.equal(badIndex, 1);
});

test("tampering an earlier event and recomputing its own hash still breaks the chain", () => {
  const log = new WorldEventLog();
  for (let i = 0; i < 4; i++) log.append(payload(i, i, i + 1), 1000000.0 + i);
  const tampered = structuredClone(log.events());
  tampered[1].payload.rationale = "forged";
  const { hash: _drop, ...withoutHash } = tampered[1];
  tampered[1].hash = entryHash(withoutHash);
  const [ok, badIndex] = verifyChain(tampered);
  assert.equal(ok, false);
  assert.equal(badIndex, 2);
});

test("tampering the last event's own hash is detected", () => {
  const log = new WorldEventLog();
  for (let i = 0; i < 3; i++) log.append(payload(i, i, i + 1), 1000000.0 + i);
  const tampered = structuredClone(log.events());
  tampered[tampered.length - 1].hash = "0".repeat(64);
  const [ok, badIndex] = verifyChain(tampered);
  assert.equal(ok, false);
  assert.equal(badIndex, tampered.length - 1);
});

test("reordering two events is detected", () => {
  const log = new WorldEventLog();
  for (let i = 0; i < 3; i++) log.append(payload(i, i, i + 1), 1000000.0 + i);
  const events = structuredClone(log.events());
  [events[0], events[1]] = [events[1], events[0]];
  const [ok] = verifyChain(events);
  assert.equal(ok, false);
});

test("the gate is capable of failing", () => {
  const log = new WorldEventLog();
  for (let i = 0; i < 3; i++) log.append(payload(i, i, i + 1), 1000000.0 + i);
  const [okBefore] = log.verify();
  assert.equal(okBefore, true);
  const tampered = structuredClone(log.events());
  tampered[0].payload.tick = 999;
  const [okAfter] = verifyChain(tampered);
  assert.equal(okAfter, false, "the verifier must be able to observe this divergence");
});

// ---- append-only surface -------------------------------------------------

test("the public surface has no mutate or delete method", () => {
  const proto = WorldEventLog.prototype;
  const publicNames = Object.getOwnPropertyNames(proto)
    .filter((n) => n !== "constructor");
  assert.deepEqual(new Set(publicNames), new Set(["append", "events", "verify"]));
  for (const forbidden of ["update", "delete", "remove", "mutate", "set", "clear", "pop", "truncate"]) {
    assert.equal(forbidden in proto, false);
  }
});

test("events returns a defensive copy — mutation does not reach the log", () => {
  const log = new WorldEventLog();
  log.append(payload(0, 0, 1), 1000000.0);
  const snapshot = log.events();
  snapshot[0].payload.rationale = "mutated after the fact";
  snapshot.push({ sequence: 99 });
  const fresh = log.events();
  assert.equal(fresh[0].payload.rationale, "advance");
  assert.equal(fresh.length, 1);
});

// ---- versioning -----------------------------------------------------------

test("eventsToJson round trips through eventsFromJson", () => {
  const log = new WorldEventLog();
  for (let i = 0; i < 3; i++) log.append(payload(i, i, i + 1), 1000000.0 + i);
  const doc = eventsToJson(log.events());
  const restored = eventsFromJson(doc);
  assert.deepEqual(restored, log.events());
});

test("eventsFromJson refuses an unrecognized format version", () => {
  assert.throws(() => eventsFromJson({ format: 9999, events: [] }), WorldEventLogError);
});

// ---- optional host capability ----------------------------------------------

test("appendEvent is optional — a bare host still works", () => {
  class BareHost extends Host {}
  const log = new WorldEventLog(new BareHost());
  const e0 = log.append(payload(0, 0, 1), 1000000.0);
  assert.equal(e0.sequence, 0);
});

test("append forwards each entry to the host's appendEvent", () => {
  const host = new TestHost();
  const log = new WorldEventLog(host);
  log.append(payload(0, 0, 1), 1000000.0);
  log.append(payload(1, 1, 2), 1000001.0);
  assert.equal(host.events.length, 2);
  assert.equal(host.events[0].sequence, 0);
  assert.equal(host.events[1].sequence, 1);
});

test("appendEvent exists as an optional no-op on the abstract Host", () => {
  const h = new Host();
  h.appendEvent({ anything: true });   // must not throw
});
