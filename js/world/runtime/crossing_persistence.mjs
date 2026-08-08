// js/world/runtime/crossing_persistence.mjs — Horizon Phase 2 Build 2's
// own lifecycle substrate for the scene-intent protocol (build prompt
// §3.4: "the crossing's existing lifecycle ... through the Phase 1
// substrate").
//
// A REAL, DISCLOSED GAP, NOT A WORKAROUND (build prompt §2: "read their
// public shape; do not modify unless a real gap appears — report it").
// world_snapshot.mjs's captureSnapshot/restoreSnapshot and
// world_recovery.mjs's recover() are single-subject-world-v1-envelope-
// specific by construction: restoreSnapshot calls parseWorldEnvelope,
// which throws on a_crossing.planes's `advance` return value (a flat
// status/route/phase record with none of identity/situation/behavior).
// world_recovery.mjs is ALSO Node-only — it imports loader_node.mjs and
// run_file.mjs, both of which touch node:fs — so it cannot be imported
// into a browser Worker at all, regardless of protocol. Neither file is
// modified here; this module is a small, protocol-appropriate sibling
// satisfying §3.4's own acceptance bar (snapshot + logged events replays
// to a byte-identical world value; save/restore round-trips) without
// forcing the crossing's raw world value through machinery built for a
// different shape.
//
// SAVE HAPPENS IN THE WORKER, NOT HERE. Only the worker's live kernel
// holds the current Traced world value — main.mjs never sees it
// (invariant 3: the performer consumes parseSceneIntent output, never the
// worker's internal world value). worker.mjs's own "save"/"snapshot-saved"
// message pair (SimulationWorkerHandle.receive) computes a snapshot
// in-process there, using the same canonicalJSON/hashWorld this module
// exports, and posts it back for the page to persist. This module's own
// job is REPLAY — reconstructing a world value from scratch, which needs
// no live worker at all (a fresh BrowserWorldRuntime does the whole job),
// so it can run on the main thread, in a test, or anywhere else.

import { sha256Hex } from "../../sha256.mjs";
import { toHost } from "../../interp.mjs";
import { canonicalJSON } from "./canonical_json.mjs";
import { BrowserWorldRuntime } from "./worker.mjs";

export class CrossingSnapshotError extends Error {
  constructor(tag, detail) {
    super(`${tag}: ${detail}`);
    this.tag = tag;
    this.detail = detail;
  }
}

export function hashWorld(worldPlain) {
  return sha256Hex(canonicalJSON(worldPlain));
}

// The crossing's own analogue of world_snapshot.mjs's captureSnapshot,
// over a raw plain-JSON world value instead of a world-v1 envelope.
export function captureCrossingSnapshot(worldPlain, revision, tick) {
  return { revision, tick, world: worldPlain, hash: hashWorld(worldPlain) };
}

// The crossing's own analogue of world_snapshot.mjs's restoreSnapshot,
// minus the world-v1 envelope validation that does not apply here: checks
// only that the snapshot's own stored hash matches a freshly recomputed
// one over its own world value.
export function verifyCrossingSnapshot(snapshot) {
  const recomputed = hashWorld(snapshot.world);
  if (recomputed !== snapshot.hash) {
    throw new CrossingSnapshotError(
      "snapshot-hash-mismatch",
      "snapshot's hash does not match its own world value — the snapshot may be corrupted",
    );
  }
  return snapshot;
}

// Deterministic replay = recovery (build prompt §3.4): re-runs
// world-init/advance from tick 0 through `eventsByTick` — a plain object
// keyed by tick number (as a string, JSON's own key convention), each
// value the events batch APPLIED at that tick. This is exactly what the
// event log's own per-entry `payload.tick`/`payload.event` fields
// reconstruct (see world_event_log.mjs's own additive `event` field) —
// group logged entries by tick, in sequence order, and this is the input
// shape. Produces the world value at `targetTick`. A fresh
// BrowserWorldRuntime each call — no shared interpreter state with any
// live worker — the same "one Interpreter, several run-shaped calls in
// sequence" BrowserWorldRuntime already is, just driven to a target tick
// instead of ticking forever.
export async function replayCrossing(fixtureUrl, eventsByTick, targetTick, opts = {}) {
  const runtime = new BrowserWorldRuntime(fixtureUrl, opts);
  await runtime.load();
  runtime.init();
  for (let tick = 0; tick < targetTick; tick += 1) {
    const events = eventsByTick[String(tick)] ?? eventsByTick[tick] ?? [];
    runtime.advance(events);
  }
  const world = toHost(runtime.world.value);
  return { tick: runtime.tick, world, hash: hashWorld(world) };
}

// Convenience: builds replayCrossing's own `eventsByTick` argument from an
// event log's entries() (world_event_log.mjs's WorldEventLog, reused
// UNMODIFIED — see the module header). Entries with no `event` on their
// payload (a bare-sequence input, or any world-v1-shaped entry) contribute
// nothing to a tick's batch, matching worker.mjs's own "a bare-sequence
// input message is a true no-op on the semantic tick" rule.
export function eventsByTickFromLog(entries) {
  const byTick = {};
  for (const entry of entries) {
    const event = entry.payload?.event;
    if (event === null || event === undefined) continue;
    const key = String(entry.payload.tick);
    (byTick[key] ??= []).push(event);
  }
  return byTick;
}
