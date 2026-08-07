// js/test/world_ir.test.mjs — unit tests for js/world_ir.mjs, the
// JavaScript World IR (world-v1) parser/validator.
//
// Horizon Phase 0 Build 1. Mirrors test_world_ir.py's coverage: version
// checked first, missing/malformed critical records, malformed
// known-optional records, and unknown-optional warn-and-ignore as a
// distinct case from malformed.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parseWorldEnvelope,
  WorldIRError,
  FACET_ORDER,
} from "../world_ir.mjs";

function validEnvelope() {
  return {
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
    relation: {
      relationId: "rel-1", relationType: "near", fromId: "subject-1",
      toId: "landing-1", provenance: "authored",
    },
    behavior: {
      eventPattern: "arrival", transition: "docked", timerTicks: 100,
      condition: "always", stateMachine: "dock-cycle",
      emittedEvent: "docked", failurePath: "resync",
    },
    expression: {
      assetId: "asset-reso", layer: 2, depth: 0.5,
      animationState: "idle", material: "hull",
      lightingResponse: "standard", particleIntent: "none",
      colliderId: "collider-1", sensorId: "sensor-1",
      audioAnchor: "audio-anchor-1", fidelityVariant: "harbor",
      accessibleAlt: "reduced-motion",
    },
    affordance: {
      action: "board", precondition: "docked",
      valueShape: "boolean", preview: "highlight",
      inverse: "disembark", authorityRequired: "none",
      explanation: "board the hydrofoil", sourceMapTarget: "identity.status",
      fallback: "deny",
    },
    lineage: {
      corpusSource: "ala-eriri", culturalStatus: "canonical",
      author: "studio", origin: "system", because: "canonical corpus asset",
      agreementFingerprint: "fp-1", permittedTransformations: "remix",
      publishingRestriction: "none", systemBoundary: "immutable",
    },
  };
}

// ================================================================ acceptance

test("a fully populated valid envelope is accepted", () => {
  const { normalized, warnings } = parseWorldEnvelope(validEnvelope());
  assert.deepEqual(warnings, []);
  assert.equal(normalized.version, 1);
  assert.equal(normalized.identity.id, "subject-1");
  assert.deepEqual(new Set(Object.keys(normalized)), new Set(["version", ...FACET_ORDER]));
});

test("only the three critical facets is still accepted", () => {
  const env = validEnvelope();
  for (const facet of ["relation", "behavior", "expression", "affordance"]) delete env[facet];
  const { normalized, warnings } = parseWorldEnvelope(env);
  assert.deepEqual(warnings, []);
  assert.deepEqual(new Set(Object.keys(normalized)), new Set(["version", "identity", "situation", "lineage"]));
});

// ================================================================== refusals

test("an unsupported protocol version refuses before any record is checked", () => {
  const env = validEnvelope();
  env.version = 2;
  env.identity = { "this is": "deliberately malformed too" };
  assert.throws(() => parseWorldEnvelope(env), (e) => e instanceof WorldIRError
    && e.tag === "unsupported-world-protocol-version"
    && e.detail.includes("2") && e.detail.includes("1"));
});

test("a missing version field also refuses", () => {
  const env = validEnvelope();
  delete env.version;
  assert.throws(() => parseWorldEnvelope(env), (e) => e.tag === "unsupported-world-protocol-version");
});

test("a missing critical record refuses by name", () => {
  const env = validEnvelope();
  delete env.lineage;
  assert.throws(() => parseWorldEnvelope(env),
    (e) => e.tag === "missing-critical-record" && e.detail.includes("lineage"));
});

test("a malformed critical record field refuses and names the field", () => {
  const env = validEnvelope();
  env.identity.schemaVersion = "one";
  assert.throws(() => parseWorldEnvelope(env),
    (e) => e.tag === "malformed-critical-record"
      && e.detail.includes("identity") && e.detail.includes("schemaVersion"));
});

test("a critical record missing a required field refuses", () => {
  const env = validEnvelope();
  delete env.situation.x;
  assert.throws(() => parseWorldEnvelope(env),
    (e) => e.tag === "malformed-critical-record"
      && e.detail.includes("situation") && e.detail.includes("missing"));
});

test("a malformed known optional record refuses not warns", () => {
  const env = validEnvelope();
  env.behavior.timerTicks = "soon";
  assert.throws(() => parseWorldEnvelope(env),
    (e) => e.tag === "malformed-optional-record"
      && e.detail.includes("behavior") && e.detail.includes("timerTicks"));
});

test("a non-record envelope refuses", () => {
  assert.throws(() => parseWorldEnvelope([1, 2, 3]), (e) => e.tag === "malformed-world-envelope");
});

// ========================================================= warn-and-ignore

test("an unknown optional record warns and is dropped not refused", () => {
  const env = validEnvelope();
  env.annotation = { note: "not part of world-v1" };
  const { normalized, warnings } = parseWorldEnvelope(env);
  assert.deepEqual(warnings, ["unknown-optional-record:annotation"]);
  assert.equal("annotation" in normalized, false);
});

test("unknown and malformed are different cases", () => {
  const env = validEnvelope();
  env.annotation = { note: "unknown" };
  env.behavior.timerTicks = "soon";
  assert.throws(() => parseWorldEnvelope(env), (e) => e.tag === "malformed-optional-record");
});

// =============================================================== no coercion

test("a wrong-typed field is never coerced", () => {
  const env = validEnvelope();
  env.situation.occupancy = "0"; // text, not the declared integer
  assert.throws(() => parseWorldEnvelope(env), (e) => e.tag === "malformed-critical-record");
});

test("a boolean field rejects an integer look-alike", () => {
  const env = validEnvelope();
  env.situation.chunkActive = 1; // not true/false
  assert.throws(() => parseWorldEnvelope(env),
    (e) => e.tag === "malformed-critical-record" && e.detail.includes("chunkActive"));
});

test("an integer field rejects a true fraction", () => {
  const env = validEnvelope();
  env.identity.schemaVersion = 1.5;
  assert.throws(() => parseWorldEnvelope(env), (e) => e.detail.includes("schemaVersion"));
});

test("normalized-number rejects out of range", () => {
  const env = validEnvelope();
  env.expression.depth = 1.2;
  assert.throws(() => parseWorldEnvelope(env), (e) => e.detail.includes("depth"));
});
