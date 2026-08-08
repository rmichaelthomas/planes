// js/test/world_renderer_main.test.mjs — Horizon Phase 1 renderer
// pipeline: MessageGate, foldDelta, and WorldClient (main.mjs), headless.
//
// All three are DOM/Worker-free by construction except WorldClient's own
// requestAnimationFrame use in pokeSubject's "wait for paint" step — that
// one global is stubbed locally (module_loader.test.mjs's own precedent
// for a browser-only global: stub it, restore it, never make callers thread
// it through). Nothing here imports Pixi, a canvas, or a real Worker.

import { test } from "node:test";
import assert from "node:assert/strict";
import { MessageGate, foldDelta, WorldClient } from "../world/runtime/main.mjs";

function withFakeRaf(fn) {
  const real = globalThis.requestAnimationFrame;
  let handle = 0;
  globalThis.requestAnimationFrame = (cb) => {
    handle += 1;
    setTimeout(() => cb(performance.now()), 0);
    return handle;
  };
  return fn().finally(() => {
    globalThis.requestAnimationFrame = real;
  });
}

// ---- MessageGate ------------------------------------------------------

test("MessageGate adopts the first message's cancellation token as its baseline", () => {
  const gate = new MessageGate();
  assert.equal(gate.activeCancellationToken, null);
  assert.equal(gate.admit({ sequence: 1, cancellationToken: "unset" }), true);
  assert.equal(gate.activeCancellationToken, "unset");
});

test("MessageGate discards a message whose sequence is not strictly greater than the last admitted", () => {
  const gate = new MessageGate();
  assert.equal(gate.admit({ sequence: 5, cancellationToken: "A" }), true);
  assert.equal(gate.admit({ sequence: 5, cancellationToken: "A" }), false, "exact replay");
  assert.equal(gate.admit({ sequence: 3, cancellationToken: "A" }), false, "delayed/reordered, arrives late");
  assert.equal(gate.admit({ sequence: 6, cancellationToken: "A" }), true);
  assert.equal(gate.lastAppliedSequence, 6);
  assert.equal(gate.discardedCount, 2);
});

test("MessageGate discards any message whose token does not match the active one", () => {
  const gate = new MessageGate();
  gate.admit({ sequence: 1, cancellationToken: "A" });
  assert.equal(gate.admit({ sequence: 2, cancellationToken: "STALE" }), false);
  assert.equal(gate.lastAppliedSequence, 1, "a wrong-token message must not advance the sequence counter either");
});

test("MessageGate.adoptCancellationToken moves the baseline immediately, so a stale in-flight message from before it is still discarded after it arrives", () => {
  const gate = new MessageGate();
  gate.admit({ sequence: 1, cancellationToken: "old" });
  gate.adoptCancellationToken("new");
  // an in-flight message stamped with the OLD token, arriving after the reset
  assert.equal(gate.admit({ sequence: 2, cancellationToken: "old" }), false);
  assert.equal(gate.admit({ sequence: 2, cancellationToken: "new" }), true);
});

// ---- foldDelta ----------------------------------------------------------

const ENVELOPE = {
  version: 1,
  identity: { id: "s1", kind: "character" },
  situation: { x: 0, y: 4, occupancy: 0 },
  behavior: { stateMachine: "resting" },
};

test("foldDelta applies facet patches onto a copy, leaving the input envelope untouched", () => {
  const delta = {
    createdSubjects: [],
    removedSubjects: [],
    facetPatches: [{ facet: "situation", id: "s1", field: "x", old: 0, new: 5 }],
    relationsAdded: [],
    relationsRemoved: [],
  };
  const next = foldDelta(ENVELOPE, delta);
  assert.equal(next.situation.x, 5);
  assert.equal(ENVELOPE.situation.x, 0, "input must not be mutated");
  assert.notEqual(next, ENVELOPE, "must return a new object");
});

test("foldDelta returns null when the delta replaces the subject (created/removed), rather than guessing a new envelope", () => {
  const delta = { createdSubjects: ["s2"], removedSubjects: ["s1"], facetPatches: [], relationsAdded: [], relationsRemoved: [] };
  assert.equal(foldDelta(ENVELOPE, delta), null);
});

test("foldDelta adds and removes the relation facet in step with relationsAdded/relationsRemoved", () => {
  const withRelation = foldDelta(ENVELOPE, {
    createdSubjects: [], removedSubjects: [],
    facetPatches: [], relationsAdded: [{ relationId: "r1", fromId: "s1", toId: "s2" }], relationsRemoved: [],
  });
  assert.deepEqual(withRelation.relation, { relationId: "r1", fromId: "s1", toId: "s2" });

  const withoutRelation = foldDelta(withRelation, {
    createdSubjects: [], removedSubjects: [],
    facetPatches: [], relationsAdded: [], relationsRemoved: [{ relationId: "r1", fromId: "s1", toId: "s2" }],
  });
  assert.equal("relation" in withoutRelation, false);
});

// ---- WorldClient ----------------------------------------------------------

function fakePerformer() {
  const applied = [];
  const removed = [];
  return {
    applied,
    removed,
    applyEnvelope(env) {
      applied.push(structuredClone(env));
    },
    removeSubject(id) {
      removed.push(id);
    },
    spriteCount() {
      return new Set(applied.map((e) => e.identity.id)).size - new Set(removed).size;
    },
  };
}

test("WorldClient constructor validates its worker and performer", () => {
  assert.throws(() => new WorldClient({ performer: fakePerformer() }), TypeError);
  assert.throws(() => new WorldClient({ worker: { postMessage() {} } }), TypeError);
});

test("WorldClient applies an admitted snapshot then folds an admitted delta onto it, and never applies a discarded (stale/reordered) delta", () => {
  const performer = fakePerformer();
  const client = new WorldClient({ worker: { postMessage() {} }, performer });

  client.handleWorkerMessage({ type: "snapshot", envelope: ENVELOPE, revision: 0, sequence: 1, cancellationToken: "tok" });
  client.handleWorkerMessage({
    type: "delta",
    delta: { createdSubjects: [], removedSubjects: [], facetPatches: [{ facet: "situation", id: "s1", field: "x", old: 0, new: 7 }], relationsAdded: [], relationsRemoved: [] },
    revision: 1, sequence: 2, cancellationToken: "tok", stepMs: 3.5, acknowledgedInputSequence: 0,
  });
  // deliberately reordered/stale: same sequence again, with a poisoned value
  client.handleWorkerMessage({
    type: "delta",
    delta: { createdSubjects: [], removedSubjects: [], facetPatches: [{ facet: "situation", id: "s1", field: "x", old: 7, new: 999 }], relationsAdded: [], relationsRemoved: [] },
    revision: 1, sequence: 2, cancellationToken: "tok", stepMs: 3.5, acknowledgedInputSequence: 0,
  });

  assert.deepEqual(performer.applied.map((e) => e.situation.x), [0, 7], "999 must never reach the performer");
  assert.equal(client.envelopes.get("s1").situation.x, 7);
  assert.equal(client.metrics.snapshotsApplied, 1);
  assert.equal(client.metrics.deltasApplied, 1);
  assert.equal(client.metrics.discarded, 1);
  assert.deepEqual(client.metrics.stepMsSamples, [3.5]);
});

test("WorldClient logs (does not throw or silently drop) a delta that arrives for a subject with no snapshot on file yet", () => {
  const performer = fakePerformer();
  const client = new WorldClient({ worker: { postMessage() {} }, performer });
  client.handleWorkerMessage({
    type: "delta",
    delta: { createdSubjects: [], removedSubjects: [], facetPatches: [{ facet: "situation", id: "unknown-subject", field: "x", old: 0, new: 1 }], relationsAdded: [], relationsRemoved: [] },
    revision: 1, sequence: 1, cancellationToken: "tok",
  });
  assert.equal(performer.applied.length, 0);
  assert.equal(client.metrics.errors.length, 1);
  assert.match(client.metrics.errors[0], /unknown-subject/);
});

test("WorldClient.setPerformer re-hydrates the new performer with every envelope already known", () => {
  const performerA = fakePerformer();
  const client = new WorldClient({ worker: { postMessage() {} }, performer: performerA });
  client.handleWorkerMessage({ type: "snapshot", envelope: ENVELOPE, revision: 0, sequence: 1, cancellationToken: "tok" });

  const performerB = fakePerformer();
  client.setPerformer(performerB);
  assert.equal(performerB.applied.length, 1);
  assert.equal(performerB.applied[0].identity.id, "s1");
});

test("WorldClient.pokeSubject resolves only once the worker acknowledges it AND a frame has been scheduled to paint", async () => {
  await withFakeRaf(async () => {
    const posted = [];
    const performer = fakePerformer();
    const client = new WorldClient({ worker: { postMessage: (m) => posted.push(m) }, performer });

    const pending = client.pokeSubject();
    assert.equal(posted[0].type, "input");
    assert.equal(posted[0].sequence, 1);

    client.handleWorkerMessage({
      type: "delta",
      delta: { createdSubjects: [], removedSubjects: [], facetPatches: [], relationsAdded: [], relationsRemoved: [] },
      revision: 1, sequence: 1, cancellationToken: null, acknowledgedInputSequence: 1,
    });

    const ms = await pending;
    assert.ok(typeof ms === "number" && ms >= 0);
  });
});
