// js/world_snapshot.mjs — durable capture of a world value. Mirrors
// world_snapshot.py field for field; see that file's module docstring for
// the full rationale (why there is no second, parallel format-version
// field, and why a captured snapshot fits host.mjs's existing, optional
// `snapshot` capability without needing anything new there).

import { semanticHash } from "./world_delta.mjs";
import { WorldIRError, parseWorldEnvelope } from "./world_ir.mjs";

const REQUIRED_KEYS = ["revision", "envelope", "semanticHash"];

export class WorldSnapshotError extends Error {
  constructor(tag, detail, fix) {
    super(`${tag}: ${detail}`);
    this.tag = tag;
    this.detail = detail;
    this.fix = fix;
  }
}

// Capture `envelope` (already normalized by parseWorldEnvelope) at
// `revision`, persisting through host.snapshot if `host` is given.
export function captureSnapshot(envelope, revision, host = null) {
  const h = semanticHash(envelope);
  const snap = { revision, envelope, semanticHash: h };
  if (host !== null) host.snapshot(h, snap);
  return snap;
}

// Validate `snap` and return { normalized, revision }. Refuses (throws
// WorldSnapshotError) on a malformed wrapper, an envelope that fails
// world-v1 validation (including an unsupported protocol version), or a
// stored semanticHash that no longer matches a freshly computed hash.
export function restoreSnapshot(snap) {
  for (const key of REQUIRED_KEYS) {
    if (!(key in snap)) {
      throw new WorldSnapshotError(
        "malformed-snapshot",
        `snapshot is missing '${key}'`,
        `a snapshot must carry all of ${REQUIRED_KEYS.join(", ")} — regenerate it `
          + "with captureSnapshot rather than hand-building the wrapper",
      );
    }
  }

  let normalized;
  try {
    ({ normalized } = parseWorldEnvelope(snap.envelope));
  } catch (e) {
    if (!(e instanceof WorldIRError)) throw e;
    throw new WorldSnapshotError(
      "invalid-snapshot-envelope",
      `snapshot's envelope fails world-v1 validation: ${e.detail}`,
      "recover from an earlier valid snapshot instead of trusting this one",
    );
  }

  if (semanticHash(normalized) !== snap.semanticHash) {
    throw new WorldSnapshotError(
      "snapshot-hash-mismatch",
      "snapshot's semanticHash does not match its own envelope's canonical form "
        + "— the snapshot may be corrupted",
      "recover from an earlier valid snapshot instead of trusting this one",
    );
  }

  return { normalized, revision: snap.revision };
}
