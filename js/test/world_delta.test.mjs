// js/test/world_delta.test.mjs — Horizon Phase 0 Build 3, Phase 1.
//
// Mirrors test_world_delta.py's cases — Python-only correctness and
// determinism here; test_world_delta_conformance.py (Python) is the
// byte-identical-with-JS half of the gate.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { computeDelta, semanticHash, canonicalDeltaString } from "../world_delta.mjs";
import { parseWorldEnvelope } from "../world_ir.mjs";

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

const RELATION_A = {
  relationId: "rel-1", relationType: "near", fromId: "subject-1",
  toId: "landing-1", provenance: "authored",
};

const RELATION_B = {
  relationId: "rel-2", relationType: "far", fromId: "subject-1",
  toId: "landing-2", provenance: "authored",
};

function valid() {
  return structuredClone(VALID_ENVELOPE);
}

function normalized(envelope) {
  const { normalized: n, warnings } = parseWorldEnvelope(envelope);
  assert.deepEqual(warnings, []);
  return n;
}

test("identical envelopes produce an empty delta but advance revision", () => {
  const env = normalized(valid());
  const delta = computeDelta(env, env, 0);
  assert.equal(delta.revisionFrom, 0);
  assert.equal(delta.revisionTo, 1);
  assert.deepEqual(delta.createdSubjects, []);
  assert.deepEqual(delta.removedSubjects, []);
  assert.deepEqual(delta.facetPatches, []);
  assert.deepEqual(delta.relationsAdded, []);
  assert.deepEqual(delta.relationsRemoved, []);
  assert.equal(delta.semanticHash, semanticHash(env));
});

test("revision counter is monotonic across a chain", () => {
  const env = normalized(valid());
  let revision = 0;
  for (let i = 0; i < 5; i++) {
    const delta = computeDelta(env, env, revision);
    assert.equal(delta.revisionFrom, revision);
    assert.equal(delta.revisionTo, revision + 1);
    revision = delta.revisionTo;
  }
  assert.equal(revision, 5);
});

test("a changed field produces one facet patch", () => {
  const prev = normalized(valid());
  const nextEnv = valid();
  nextEnv.situation = { ...nextEnv.situation, x: 11 };
  const delta = computeDelta(prev, normalized(nextEnv), 0);
  assert.deepEqual(delta.facetPatches, [
    { facet: "situation", id: "subject-1", field: "x", old: 10, new: 11 },
  ]);
});

test("multiple changed fields are ordered by facet then field order", () => {
  const prev = normalized(valid());
  const nextEnv = valid();
  nextEnv.situation = { ...nextEnv.situation, y: 0, x: 11 };
  nextEnv.identity = { ...nextEnv.identity, displayName: "Reso II" };
  const delta = computeDelta(prev, normalized(nextEnv), 0);
  assert.deepEqual(delta.facetPatches, [
    { facet: "identity", id: "subject-1", field: "displayName", old: "Reso", new: "Reso II" },
    { facet: "situation", id: "subject-1", field: "x", old: 10, new: 11 },
    { facet: "situation", id: "subject-1", field: "y", old: -5, new: 0 },
  ]);
});

test("an optional facet appearing is a patch from absent (relation bucket)", () => {
  const prev = normalized(valid());
  const envWithRelation = valid();
  envWithRelation.relation = { ...RELATION_A };
  const delta = computeDelta(prev, normalized(envWithRelation), 0);
  assert.deepEqual(delta.relationsAdded, [{ ...RELATION_A }]);
  assert.deepEqual(delta.relationsRemoved, []);
  assert.deepEqual(delta.facetPatches, []);
});

test("an optional facet disappearing is a patch to absent (relation bucket)", () => {
  const envWithRelation = valid();
  envWithRelation.relation = { ...RELATION_A };
  const prev = normalized(envWithRelation);
  const nextEnv = normalized(valid());
  const delta = computeDelta(prev, nextEnv, 0);
  assert.deepEqual(delta.relationsRemoved, [{ ...RELATION_A }]);
  assert.deepEqual(delta.relationsAdded, []);
});

test("a non-relation optional facet appearing patches every field from absent", () => {
  const prev = normalized(valid());
  const envWithBehavior = valid();
  envWithBehavior.behavior = {
    eventPattern: "arrival", transition: "docked", timerTicks: 100,
    condition: "always", stateMachine: "dock-cycle",
    emittedEvent: "docked", failurePath: "resync",
  };
  const delta = computeDelta(prev, normalized(envWithBehavior), 0);
  assert.ok(delta.facetPatches.every((p) => p.facet === "behavior"));
  assert.equal(delta.facetPatches.length, 7);
  const byField = Object.fromEntries(delta.facetPatches.map((p) => [p.field, [p.old, p.new]]));
  assert.deepEqual(byField.eventPattern, [null, "arrival"]);
  assert.deepEqual(byField.timerTicks, [null, 100]);
});

test("relation field change with same relation id is a facet patch", () => {
  const envA = valid();
  envA.relation = { ...RELATION_A };
  const prev = normalized(envA);
  const envB = valid();
  envB.relation = { ...RELATION_A, provenance: "derived" };
  const delta = computeDelta(prev, normalized(envB), 0);
  assert.deepEqual(delta.relationsAdded, []);
  assert.deepEqual(delta.relationsRemoved, []);
  assert.deepEqual(delta.facetPatches, [
    { facet: "relation", id: "subject-1", field: "provenance", old: "authored", new: "derived" },
  ]);
});

test("relation id change is remove old, add new, not a patch", () => {
  const envA = valid();
  envA.relation = { ...RELATION_A };
  const prev = normalized(envA);
  const envB = valid();
  envB.relation = { ...RELATION_B };
  const delta = computeDelta(prev, normalized(envB), 0);
  assert.deepEqual(delta.relationsRemoved, [{ ...RELATION_A }]);
  assert.deepEqual(delta.relationsAdded, [{ ...RELATION_B }]);
  assert.deepEqual(delta.facetPatches, []);
});

test("a changed identity id is a subject replace, not a patch", () => {
  const prev = normalized(valid());
  const envB = valid();
  envB.identity = { ...envB.identity, id: "subject-2" };
  const delta = computeDelta(prev, normalized(envB), 0);
  assert.deepEqual(delta.createdSubjects, ["subject-2"]);
  assert.deepEqual(delta.removedSubjects, ["subject-1"]);
  assert.deepEqual(delta.facetPatches, []);
  assert.deepEqual(delta.relationsAdded, []);
  assert.deepEqual(delta.relationsRemoved, []);
});

test("semantic hash matches hash of next envelope's canonical form", () => {
  const prev = normalized(valid());
  const nextEnv = valid();
  nextEnv.situation = { ...nextEnv.situation, x: 99 };
  const nextN = normalized(nextEnv);
  const delta = computeDelta(prev, nextN, 0);
  assert.equal(delta.semanticHash, semanticHash(nextN));
  assert.notEqual(delta.semanticHash, semanticHash(prev));
});

test("semantic hash is a 64-char hex sha256 digest", () => {
  const h = semanticHash(normalized(valid()));
  assert.equal(h.length, 64);
  assert.ok(/^[0-9a-f]{64}$/.test(h));
});

test("canonical delta string is deterministic regardless of object construction order", () => {
  const prev = normalized(valid());
  const nextA = valid();
  nextA.situation = { ...nextA.situation, x: 11 };
  const deltaA = computeDelta(prev, normalized(nextA), 0);

  const envB = valid();
  const reversedSituation = {};
  for (const k of Object.keys(envB.situation).reverse()) reversedSituation[k] = envB.situation[k];
  reversedSituation.x = 11;
  envB.situation = reversedSituation;
  const deltaB = computeDelta(prev, normalized(envB), 0);

  assert.equal(canonicalDeltaString(deltaA), canonicalDeltaString(deltaB));
});

test("the gate is capable of failing", () => {
  const prev = normalized(valid());
  const nextEnv = valid();
  nextEnv.situation = { ...nextEnv.situation, x: 11 };
  const delta = computeDelta(prev, normalized(nextEnv), 0);
  const real = canonicalDeltaString(delta);
  const tampered = real.replace("x", "z");
  assert.notEqual(real, tampered, "the comparison must be able to observe this divergence");
});
