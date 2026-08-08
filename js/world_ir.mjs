// js/world_ir.mjs — the JavaScript World IR (world-v1) parser/validator.
//
// Horizon Phase 0 Build 1. Mirrors world_ir.py field for field, refusal tag
// for refusal tag — the pair are read side by side in review, and
// test_world_ir_conformance.py is what holds them to actual byte-identical
// agreement rather than asserted agreement. Reads
// grammar/protocols/world-v1.json directly, the same as the Python side;
// grammar/world_ir.planes cannot (a .planes module has no way to read JSON),
// so its rules are hand-written there and checked against this file and
// world_ir.py by the same conformance gate.
//
// No coercion at the type boundary: a field whose value fails its declared
// type refuses, never converts.
//
// BROWSER-SAFE SINCE HORIZON PHASE 1 (renderer pipeline). This file used to
// read world-v1.json via node:fs at module load, which made it Node-only —
// invisible until the first build that needed a real browser (main thread or
// worker) to import it. The protocol is now a JSON module import, the same
// mechanism browser_main.mjs already uses for vocabulary.json/amber.json/
// core.json; PROTOCOL/SUPPORTED_VERSION/RECORDS hold the identical values
// this always produced under Node. Only the CLI mode at the bottom of this
// file (`node js/world_ir.mjs < envelope.json`, test_world_ir_conformance.py's
// shell-out target) still needs node:path/node:url, imported dynamically
// there so the static import list here stays browser-clean.

import PROTOCOL from "../grammar/protocols/world-v1.json" with { type: "json" };

export { PROTOCOL };
export const SUPPORTED_VERSION = PROTOCOL.version;
export const RECORDS = PROTOCOL.records;

// Fixed enumeration order — must match world_ir.py's FACET_ORDER exactly;
// the conformance gate's byte-identical comparison depends on it.
export const FACET_ORDER = Object.freeze([
  "identity", "situation", "relation", "behavior",
  "expression", "affordance", "lineage",
]);
export const FIELD_ORDER = Object.freeze(
  Object.fromEntries(
    FACET_ORDER.map((facet) => [facet, RECORDS[facet].fields.map((f) => f.name)]),
  ),
);

// A refusal naming the world-v1 rule it broke — the same three-part
// tag/detail/fix shape world_ir.py's WorldIRError carries.
export class WorldIRError extends Error {
  constructor(tag, detail, fix) {
    super(`${tag}: ${detail}`);
    this.tag = tag;
    this.detail = detail;
    this.fix = fix;
  }
}

function isPlainObject(v) {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

// No coercion: a value either already matches `typeName` or it does not.
// `typeof true === "boolean"` is checked first for the same reason
// world_ir.py checks `bool` before its numeric types — nothing here treats
// a boolean as a number.
function typeOk(value, typeName) {
  if (typeName === "boolean") return typeof value === "boolean";
  if (typeof value === "boolean") return false;
  if (typeName === "identifier" || typeName === "semantic-id" || typeName === "source-map-path") {
    return typeof value === "string" && value.length > 0;
  }
  if (typeName === "text") return typeof value === "string";
  if (typeName === "integer") return typeof value === "number" && Number.isFinite(value) && Number.isInteger(value);
  if (typeName === "number") return typeof value === "number" && Number.isFinite(value);
  if (typeName === "normalized-number") {
    return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
  }
  throw new WorldIRError(
    "unknown-field-type",
    `world-v1.json declares field type '${typeName}', which this parser does not know`,
    "add a case for the new type to typeOk in js/world_ir.mjs, in the same commit that adds it to world-v1.json",
  );
}

// Returns { normalized, reason }. Presence is checked all at once (matching
// grammar/world_ir.planes's `when r is { f1, f2, ... }:` — a single shape
// match, not a per-field presence test, since `when` cannot test a field
// whose name is itself a runtime value). Once presence holds, `reason` names
// the first wrong-typed field, in the facet's declared order.
function validateRecord(facet, recordValue) {
  if (!isPlainObject(recordValue)) {
    return { normalized: null, reason: "the record is not a record of fields" };
  }
  const fieldSpecs = RECORDS[facet].fields;
  const allPresent = fieldSpecs.every((f) => Object.prototype.hasOwnProperty.call(recordValue, f.name));
  if (!allPresent) {
    return { normalized: null, reason: "the record is missing one or more required fields" };
  }
  const normalized = {};
  for (const field of fieldSpecs) {
    const { name, type: typeName } = field;
    const value = recordValue[name];
    if (!typeOk(value, typeName)) {
      return { normalized: null, reason: `field '${name}' fails its declared type '${typeName}'` };
    }
    normalized[name] = value;
  }
  return { normalized, reason: null };
}

// Validate `envelope` against world-v1. Returns { normalized, warnings } on
// success; throws WorldIRError on refusal. See world_ir.py's
// parse_world_envelope for the full contract — the two are kept identical.
export function parseWorldEnvelope(envelope) {
  if (!isPlainObject(envelope)) {
    throw new WorldIRError(
      "malformed-world-envelope",
      "the world envelope is not a record of fields",
      "provide the envelope as a record whose fields are 'version' plus the world-v1 facet names",
    );
  }

  const version = Object.prototype.hasOwnProperty.call(envelope, "version") ? envelope.version : undefined;
  if (version !== SUPPORTED_VERSION) {
    throw new WorldIRError(
      "unsupported-world-protocol-version",
      `world envelope declares protocol version ${JSON.stringify(version ?? null)}, which is not ${SUPPORTED_VERSION}`,
      "regenerate the envelope with a world-v1 protocol matching this parser's version — "
        + "if the envelope is newer than what this parser reads, upgrade the parser instead "
        + "of regenerating the envelope",
    );
  }

  const normalized = { version: SUPPORTED_VERSION };
  for (const facet of FACET_ORDER) {
    const spec = RECORDS[facet];
    if (!Object.prototype.hasOwnProperty.call(envelope, facet)) {
      if (spec.critical) {
        throw new WorldIRError(
          "missing-critical-record",
          `critical record '${facet}' is missing from the world envelope`,
          `add the '${facet}' record — ${facet} is a critical facet and the `
            + "envelope cannot be applied without it",
        );
      }
      continue;
    }
    const { normalized: fields, reason } = validateRecord(facet, envelope[facet]);
    if (reason !== null) {
      const tag = spec.critical ? "malformed-critical-record" : "malformed-optional-record";
      throw new WorldIRError(
        tag,
        `record '${facet}' is malformed: ${reason}`,
        `correct '${facet}' so every field world-v1.json declares for it is present `
          + "and matches its declared type",
      );
    }
    normalized[facet] = fields;
  }

  const knownKeys = new Set([...FACET_ORDER, "version"]);
  const warnings = Object.keys(envelope)
    .filter((key) => !knownKeys.has(key))
    .map((key) => `unknown-optional-record:${key}`)
    .sort();

  return { normalized, warnings };
}

function formatValue(value) {
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

// The cross-implementation comparison form test_world_ir_conformance.py
// checks byte-for-byte against world_ir.py's canonical_outcome_string and
// grammar/world_ir.planes's own rendering.
export function canonicalOutcomeString(envelope) {
  let normalized;
  let warnings;
  try {
    ({ normalized, warnings } = parseWorldEnvelope(envelope));
  } catch (e) {
    if (!(e instanceof WorldIRError)) throw e;
    return [
      "world-ir-outcome: refuse",
      `tag: ${e.tag}`,
      `detail: ${e.detail}`,
      `fix: ${e.fix}`,
    ].join("\n");
  }
  const lines = [
    "world-ir-outcome: accept",
    `version: ${normalized.version}`,
    `warnings: ${warnings.join(",")}`,
  ];
  for (const facet of FACET_ORDER) {
    if (!(facet in normalized)) continue;
    for (const name of FIELD_ORDER[facet]) {
      lines.push(`${facet}.${name}: ${formatValue(normalized[facet][name])}`);
    }
  }
  return lines.join("\n");
}

// CLI mode — `node js/world_ir.mjs < envelope.json` — reads a JSON envelope
// from stdin and prints its canonical outcome string. Exists so
// test_world_ir_conformance.py (Python) can shell out to this
// implementation exactly as the existing test_js_*.py suites shell out to
// js/cli.mjs.
//
// node:path/node:url are imported dynamically, only inside this Node-only
// branch — a static top-level import of either would fail module resolution
// in a browser regardless of whether this branch ever runs (see the module
// docstring). `typeof process !== "undefined"` is false in every browser, so
// the dynamic imports are never even attempted there.
if (typeof process !== "undefined" && process.argv[1]) {
  const [{ default: path }, { fileURLToPath }] = await Promise.all([
    import("node:path"),
    import("node:url"),
  ]);
  if (path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    const chunks = [];
    process.stdin.on("data", (c) => chunks.push(c));
    process.stdin.on("end", () => {
      const envelope = JSON.parse(Buffer.concat(chunks).toString("utf-8"));
      process.stdout.write(canonicalOutcomeString(envelope));
    });
  }
}
