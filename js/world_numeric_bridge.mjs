// js/world_numeric_bridge.mjs — Horizon Phase 0 Build 4: the numeric bridge
// (spec §9.4). Mirrors world_numeric_bridge.py function for function; see
// that file's module docstring for the full discipline this implements —
// a declared fixed-point unit convention layered on the EXISTING
// toHost/fromForeign seam, not a new numeric mechanism.
//
// `quantizeOutcome` is the REACHABLE half (round via roundTo, report
// lossiness) — grammar/world_numeric_bridge.planes mirrors exactly this.
// `quantize` adds the `approx`-marking half, which is Python+JS only (see
// that file's docstring for why a .planes program cannot do this itself).

import path from "node:path";
import { fileURLToPath } from "node:url";
import { Approximation, PlanesNumber } from "./planes_num.mjs";
import { toHost, fromForeign } from "./interp.mjs";
import { RECORDS } from "./world_ir.mjs";
import { semanticHash } from "./world_delta.mjs";

// (unit, places) declared for `facet.fieldName` in world-v1.json's own field
// spec (Phase 1's boundary metadata), or `null` when the field carries no
// declared unit and crosses via `toHost` exactly as Builds 1-3 already do,
// unquantized. Throws if `facet.fieldName` names no world-v1 field at all.
export function declaredUnit(facet, fieldName) {
  const fieldSpecs = RECORDS[facet].fields;
  for (const field of fieldSpecs) {
    if (field.name === fieldName) {
      if ("unit" in field && "places" in field) return { unit: field.unit, places: field.places };
      return null;
    }
  }
  throw new Error(`${facet}.${fieldName} is not a world-v1 field`);
}

// Round `value` to `places` decimal places via the existing `roundTo`, and
// report whether that changed the value. Returns { rounded, lossy }.
export function quantizeOutcome(value, places) {
  const rounded = value.roundTo(places);
  return { rounded, lossy: !rounded.q.eq(value.q) };
}

// Same shape as planes_num.mjs's SINE_APPROXIMATION/ROOT_APPROXIMATION: an
// Approximation naming exactly what happened and at what precision.
function quantizationApproximation(unit, places) {
  return new Approximation(
    "quantize",
    `fixed-point boundary quantization to unit '${unit}' at ${places} `
      + `decimal place(s), rounded half away from zero via round_to `
      + `(numeric bridge, spec §9.4)`,
  );
}

// The bridge's one quantization rule (§9.4 requirements 1-2 both run
// through this). See world_numeric_bridge.py's `quantize` for the full
// contract: unmarked when exact-at-scale or already approximate, marked
// with a named Approximation otherwise.
export function quantize(value, unit, places) {
  const { rounded, lossy } = quantizeOutcome(value, places);
  if (!lossy || value.approx !== null) return rounded;
  return rounded.withApprox(quantizationApproximation(unit, places));
}

// Outbound (§9.4 requirement 1): quantize, then cross through the existing
// toHost, unchanged. Returns [native, quantized].
export function toHostQuantized(value, unit, places) {
  const quantized = quantize(value, unit, places);
  return [toHost(quantized), quantized];
}

// Inbound (§9.4 requirement 2): read `raw` back as an exact rational via the
// existing fromForeign, then pin it to its declared scale before it is
// usable as a Planes value.
export function fromHostQuantized(raw, unit, places) {
  return quantize(fromForeign(raw), unit, places);
}

// §9.4 requirement 3: two runs are compared for determinism on the semantic
// canonical form, never on host-rendered floats. Reuses world_delta.mjs's
// semanticHash, the same hash Build 3's delta/event log already uses.
export function isDeterministic(envelopeA, envelopeB) {
  return semanticHash(envelopeA) === semanticHash(envelopeB);
}

// The cross-implementation comparison form
// test_world_numeric_bridge_conformance.py checks byte-for-byte against
// world_numeric_bridge.py's canonical_quantize_outcome_string and
// grammar/world_numeric_bridge.planes's own rendering.
export function canonicalQuantizeOutcomeString(value, places) {
  const { rounded, lossy } = quantizeOutcome(value, places);
  return `quantize-outcome: value=${value.text()} places=${places} `
    + `quantized=${rounded.text()} lossy=${lossy ? "true" : "false"}`;
}

// CLI mode — `node js/world_numeric_bridge.mjs < {"value":"1.4995","places":3}`
// — so test_world_numeric_bridge_conformance.py (Python) can shell out to
// this implementation exactly as test_world_ir_conformance.py does for
// js/world_ir.mjs.
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const chunks = [];
  process.stdin.on("data", (c) => chunks.push(c));
  process.stdin.on("end", () => {
    const payload = JSON.parse(Buffer.concat(chunks).toString("utf-8"));
    const value = PlanesNumber.parse(payload.value);
    process.stdout.write(canonicalQuantizeOutcomeString(value, payload.places));
  });
}
