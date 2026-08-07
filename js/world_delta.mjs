// js/world_delta.mjs — the JavaScript monotonic delta between two world-v1
// envelopes. Mirrors world_delta.py field for field; see that file's module
// docstring for the full single-subject-scope rationale and the
// determinism/hashing discipline. test_world_delta_conformance.py (Python)
// holds the two to actual byte-identical agreement.

import path from "node:path";
import { fileURLToPath } from "node:url";
import { sha256Hex } from "./sha256.mjs";
import { FACET_ORDER, FIELD_ORDER, canonicalOutcomeString } from "./world_ir.mjs";

const RELATION_FACET = "relation";

function formatValue(value) {
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

// SHA-256 hex digest over `envelope`'s canonical outcome string — see
// world_delta.py's `semantic_hash` for why this is the full digest, not a
// truncated fingerprint.
export function semanticHash(envelope) {
  return sha256Hex(canonicalOutcomeString(envelope));
}

function subjectId(envelope) {
  return envelope.identity.id;
}

// Field-level patches for one facet present (however partially, via the
// absent sentinel `null`) on at least one side. See world_delta.py's
// `_facet_field_patches` for the absent-sentinel rationale.
function facetFieldPatches(facet, subjectIdValue, prevFields, nextFields) {
  const patches = [];
  for (const field of FIELD_ORDER[facet]) {
    const old = prevFields !== null && prevFields !== undefined ? prevFields[field] : null;
    const next = nextFields !== null && nextFields !== undefined ? nextFields[field] : null;
    const prevAbsent = prevFields === null || prevFields === undefined;
    const nextAbsent = nextFields === null || nextFields === undefined;
    if (!prevAbsent && !nextAbsent && old === next) continue;
    if (prevAbsent && nextAbsent) continue;
    patches.push({ facet, id: subjectIdValue, field, old, new: next });
  }
  return patches;
}

// Diff two normalized world-v1 envelopes into a monotonic delta.
// `prevRevision` is the revision `prevEnvelope` is at; `revisionTo` is
// always `prevRevision + 1` regardless of whether anything changed —
// advancing the counter is the driver's job (one delta per tick).
export function computeDelta(prevEnvelope, nextEnvelope, prevRevision) {
  const prevId = subjectId(prevEnvelope);
  const nextId = subjectId(nextEnvelope);

  const delta = {
    revisionFrom: prevRevision,
    revisionTo: prevRevision + 1,
    createdSubjects: [],
    removedSubjects: [],
    facetPatches: [],
    relationsAdded: [],
    relationsRemoved: [],
    semanticHash: semanticHash(nextEnvelope),
  };

  if (prevId !== nextId) {
    delta.createdSubjects = [nextId];
    delta.removedSubjects = [prevId];
    return delta;
  }

  for (const facet of FACET_ORDER) {
    const prevFields = Object.prototype.hasOwnProperty.call(prevEnvelope, facet) ? prevEnvelope[facet] : null;
    const nextFields = Object.prototype.hasOwnProperty.call(nextEnvelope, facet) ? nextEnvelope[facet] : null;
    if (facet === RELATION_FACET) {
      if (prevFields === null && nextFields !== null) {
        delta.relationsAdded.push({ ...nextFields });
      } else if (prevFields !== null && nextFields === null) {
        delta.relationsRemoved.push({ ...prevFields });
      } else if (prevFields !== null && nextFields !== null) {
        if (prevFields.relationId !== nextFields.relationId) {
          delta.relationsRemoved.push({ ...prevFields });
          delta.relationsAdded.push({ ...nextFields });
        } else {
          delta.facetPatches.push(...facetFieldPatches(facet, nextId, prevFields, nextFields));
        }
      }
      continue;
    }
    delta.facetPatches.push(...facetFieldPatches(facet, nextId, prevFields, nextFields));
  }

  return delta;
}

function formatRelation(record) {
  return FIELD_ORDER[RELATION_FACET].map((field) => `${field}=${formatValue(record[field])}`).join(",");
}

// The cross-implementation comparison form test_world_delta_conformance.py
// checks byte-for-byte — must stay textually identical to world_delta.py's
// canonical_delta_string.
export function canonicalDeltaString(delta) {
  const lines = [
    `revision: ${delta.revisionFrom} -> ${delta.revisionTo}`,
    `created-subjects: ${delta.createdSubjects.join(",")}`,
    `removed-subjects: ${delta.removedSubjects.join(",")}`,
  ];
  for (const patch of delta.facetPatches) {
    lines.push(
      `facet-patch: ${patch.facet}.${patch.field} id=${patch.id} `
        + `old=${patch.old !== null ? formatValue(patch.old) : "<absent>"} `
        + `new=${patch.new !== null ? formatValue(patch.new) : "<absent>"}`,
    );
  }
  for (const record of delta.relationsAdded) lines.push(`relation-added: ${formatRelation(record)}`);
  for (const record of delta.relationsRemoved) lines.push(`relation-removed: ${formatRelation(record)}`);
  lines.push(`semantic-hash: ${delta.semanticHash}`);
  return lines.join("\n");
}

// CLI mode — `node js/world_delta.mjs < {"prev":...,"next":...,"revision":N}`
// — so test_world_delta_conformance.py (Python) can shell out to this
// implementation exactly as test_world_ir_conformance.py does for world_ir.
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const chunks = [];
  process.stdin.on("data", (c) => chunks.push(c));
  process.stdin.on("end", () => {
    const payload = JSON.parse(Buffer.concat(chunks).toString("utf-8"));
    const result = computeDelta(payload.prev, payload.next, payload.revision);
    process.stdout.write(canonicalDeltaString(result));
  });
}
