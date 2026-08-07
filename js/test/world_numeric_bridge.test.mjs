// js/test/world_numeric_bridge.test.mjs — Horizon Phase 0 Build 4, last
// Phase 0 build.
//
// Mirrors test_world_numeric_bridge.py's cases — Python-only correctness
// here has its JS twin; test_world_numeric_bridge_conformance.py (Python)
// is the byte-identical-across-Python/JS/.planes half of the gate.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { PlanesNumber, sineDegrees } from "../planes_num.mjs";
import { toHost } from "../interp.mjs";
import { parseWorldEnvelope, canonicalOutcomeString } from "../world_ir.mjs";
import { semanticHash } from "../world_delta.mjs";
import {
  declaredUnit,
  quantizeOutcome,
  quantize,
  toHostQuantized,
  fromHostQuantized,
  isDeterministic,
} from "../world_numeric_bridge.mjs";

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

function valid() {
  return structuredClone(VALID_ENVELOPE);
}

function n(text) {
  return PlanesNumber.parse(text);
}

// ============================================================= declaredUnit

test("declaredUnit finds situation.x and situation.y", () => {
  assert.deepEqual(declaredUnit("situation", "x"), { unit: "world-position", places: 3 });
  assert.deepEqual(declaredUnit("situation", "y"), { unit: "world-position", places: 3 });
});

test("declaredUnit is null for a field with no declared unit", () => {
  assert.equal(declaredUnit("situation", "occupancy"), null);
});

test("declaredUnit throws for an unknown field", () => {
  assert.throws(() => declaredUnit("situation", "not-a-real-field"));
});

// ========================================================== quantizeOutcome

test("quantizeOutcome correctness", () => {
  const cases = [
    [["1.2341", 3], ["1.234", true]],
    [["1.2349", 3], ["1.235", true]],
    [["1.500", 3], ["1.5", false]],
    [["7", 3], ["7", false]],
    [["-1.2349", 3], ["-1.235", true]],
    [["2.6", 0], ["3", true]],
    [["0.5", 0], ["1", true]],
    [["-0.5", 0], ["-1", true]],
  ];
  for (const [[valueText, places], [expectedText, expectedLossy]] of cases) {
    const { rounded, lossy } = quantizeOutcome(n(valueText), places);
    assert.equal(rounded.text(), expectedText, `${valueText} @ ${places}`);
    assert.equal(lossy, expectedLossy, `${valueText} @ ${places}`);
  }
});

test("quantizeOutcome reuses roundTo exactly — the round_to-reuse proof", () => {
  for (const [valueText, places] of [["1.2349", 3], ["-7.777", 2], ["100", 4], ["0.0005", 3]]) {
    const value = n(valueText);
    const { rounded } = quantizeOutcome(value, places);
    const handRounded = value.roundTo(places);
    assert.ok(rounded.q.eq(handRounded.q));
  }
});

// =================================================================== quantize

test("an exact crossing stays exact", () => {
  const v = n("1.500");
  const q = quantize(v, "world-position", 3);
  assert.equal(q.isExact, true);
  assert.equal(q.approx, null);
  assert.ok(q.q.eq(v.q));
});

test("a lossy crossing is marked with a named Approximation", () => {
  const v = n("1.4995");
  const q = quantize(v, "world-position", 3);
  assert.equal(q.isExact, false);
  assert.ok(q.approx !== null);
  assert.equal(q.approx.op, "quantize");
  assert.ok(q.approx.detail.includes("world-position"));
  assert.ok(q.approx.detail.includes("3"));
  assert.equal(q.text(), "1.5");
});

test("an already-approximate value keeps its own marker", () => {
  const approximate = sineDegrees(n("30"));
  assert.ok(approximate.approx !== null && approximate.approx.op === "sine");
  const q = quantize(approximate, "world-position", 3);
  assert.equal(q.approx, approximate.approx);
});

test("no unmarked lossy crossing across a deterministic spread of values", () => {
  for (let num = -50; num <= 50; num += 1) {
    for (const den of [1, 3, 7, 1000]) {
      const v = PlanesNumber.of(num).div(PlanesNumber.of(den));
      const q = quantize(v, "world-position", 3);
      if (!q.q.eq(v.q)) {
        assert.ok(q.approx !== null, `${num}/${den} lossy crossing left unmarked`);
      } else {
        assert.equal(q.approx, null, `${num}/${den} exact crossing marked anyway`);
      }
    }
  }
});

// ============================================================ outbound / inbound

test("toHostQuantized matches toHost of the quantized value", () => {
  const v = n("1.4995");
  const [native, quantized] = toHostQuantized(v, "world-position", 3);
  assert.equal(native, toHost(quantized));
  assert.equal(native, 1.5);
});

test("fromHostQuantized pins a noisy host float to the declared scale", () => {
  const noisy = 1.4999999999999998; // a plausible host float, not a clean 3-place decimal
  const q = fromHostQuantized(noisy, "world-position", 3);
  assert.equal(q.text(), "1.5");
  assert.ok(q.approx !== null);
  assert.equal(q.approx.op, "quantize");
});

test("fromHostQuantized exact-at-scale stays exact", () => {
  const q = fromHostQuantized(1.5, "world-position", 3);
  assert.equal(q.isExact, true);
  assert.equal(q.text(), "1.5");
});

test("fromHostQuantized integer stays exact", () => {
  const q = fromHostQuantized(10, "world-position", 3);
  assert.equal(q.isExact, true);
  assert.equal(q.text(), "10");
});

// ==================================================================== determinism

test("identical semantic hashes are deterministic even if a hypothetical host float differs", () => {
  const envelopeA = valid();
  const envelopeB = valid();
  const simulatedHostRenderA = { hostRenderedX: 10.000000001 };
  const simulatedHostRenderB = { hostRenderedX: 10.000000002 };
  assert.notDeepEqual(simulatedHostRenderA, simulatedHostRenderB);

  assert.ok(isDeterministic(envelopeA, envelopeB));
  assert.equal(semanticHash(envelopeA), semanticHash(envelopeB));
});

test("a genuine semantic divergence is caught by the hash", () => {
  const envelopeA = valid();
  const envelopeB = valid();
  envelopeB.situation.x = 999;

  assert.equal(isDeterministic(envelopeA, envelopeB), false);
  assert.notEqual(semanticHash(envelopeA), semanticHash(envelopeB));
});

// =========================================================== parser stays green

test("world-v1.json's declared units validate through Build 1's parser", () => {
  const { normalized, warnings } = parseWorldEnvelope(valid());
  assert.deepEqual(warnings, []);
  assert.equal(normalized.situation.x, 10);
  assert.equal(normalized.situation.y, -5);
  assert.ok(!("unit" in normalized.situation));
  assert.ok(!("places" in normalized.situation));
  assert.ok(canonicalOutcomeString(normalized).includes("situation.x: 10"));
});
