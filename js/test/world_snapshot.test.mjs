// js/test/world_snapshot.test.mjs — Horizon Phase 0 Build 3, Phase 3.
//
// Mirrors test_world_snapshot.py's cases.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { captureSnapshot, restoreSnapshot, WorldSnapshotError, } from "../world_snapshot.mjs";
import { semanticHash } from "../world_delta.mjs";
import { parseWorldEnvelope } from "../world_ir.mjs";
import { TestHost } from "../host.mjs";

const VALID_ENVELOPE = {
  version: 1,
  identity: {
    id: "subject-1", kind: "vehicle", subkind: "hydrofoil",
    displayName: "Reso", status: "canonical", schemaVersion: 1,
  },
  situation: {
    containingPlace: "landing-1", space: "world", x: 10, y: -5,
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

test("capture bundles envelope, revision, and semantic hash", () => {
  const env = norm();
  const snap = captureSnapshot(env, 7);
  assert.equal(snap.revision, 7);
  assert.deepEqual(snap.envelope, env);
  assert.equal(snap.semanticHash, semanticHash(env));
});

test("capture is a no-op persistence-wise with no host", () => {
  captureSnapshot(norm(), 0, null);   // must not throw
});

test("capture forwards to the host's snapshot capability", () => {
  const host = new TestHost();
  const env = norm();
  const snap = captureSnapshot(env, 3, host);
  assert.deepEqual(host.snapshots[snap.semanticHash], snap);
});

test("restore round trips a valid snapshot", () => {
  const env = norm();
  const snap = captureSnapshot(env, 5);
  const { normalized, revision } = restoreSnapshot(snap);
  assert.deepEqual(normalized, env);
  assert.equal(revision, 5);
});

test("restore refuses an unsupported protocol version", () => {
  const env = norm();
  const snap = captureSnapshot(env, 0);
  snap.envelope.version = 2;
  assert.throws(() => restoreSnapshot(snap), (e) => {
    assert.ok(e instanceof WorldSnapshotError);
    assert.equal(e.tag, "invalid-snapshot-envelope");
    return true;
  });
});

test("restore refuses a hash that no longer matches its envelope", () => {
  const env = norm();
  const snap = captureSnapshot(env, 0);
  snap.envelope = { ...snap.envelope, situation: { ...snap.envelope.situation, x: 999 } };
  assert.throws(() => restoreSnapshot(snap), (e) => {
    assert.ok(e instanceof WorldSnapshotError);
    assert.equal(e.tag, "snapshot-hash-mismatch");
    return true;
  });
});

test("restore refuses a malformed snapshot missing a required key", () => {
  for (const missing of ["revision", "envelope", "semanticHash"]) {
    const snap = captureSnapshot(norm(), 0);
    delete snap[missing];
    assert.throws(() => restoreSnapshot(snap), (e) => {
      assert.ok(e instanceof WorldSnapshotError);
      assert.equal(e.tag, "malformed-snapshot");
      return true;
    });
  }
});

test("the gate is capable of failing", () => {
  const snap = captureSnapshot(norm(), 0);
  snap.semanticHash = "0".repeat(64);
  assert.throws(() => restoreSnapshot(snap), WorldSnapshotError);
});
