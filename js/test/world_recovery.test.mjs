// js/test/world_recovery.test.mjs — Horizon Phase 0 Build 3, Phase 3.
//
// Mirrors test_world_recovery.py's cases. `recover` is async here (Node's
// module loader reads files over node:fs/promises, exactly as
// WorldRuntime.load() already is per Build 2) where the Python side is
// synchronous — the same asymmetry Build 2 already established.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { explain, whyTree, whyMachine } from "../interp.mjs";
import { canonicalOutcomeString } from "../world_ir.mjs";
import { recover, WorldRecoveryError } from "../world_recovery.mjs";
import { WorldRuntime } from "../world_runtime.mjs";
import { captureSnapshot } from "../world_snapshot.mjs";
import { TestHost } from "../host.mjs";

const DEMO = "world_runtime_demo.planes";

function derivation(traced) {
  return { card: explain(traced), prompt: whyTree(traced), machine: whyMachine(traced) };
}

async function loadedRuntime() {
  const rt = new WorldRuntime(DEMO, { host: new TestHost(), trace: true });
  await rt.load();
  return rt;
}

test("recovery reconstructs byte-identical canonical form and derivation", async () => {
  const rt = await loadedRuntime();
  rt.init();
  for (let i = 0; i < 4; i++) rt.advance();
  const { normalized: snapshotEnvelope, warnings: w1 } = rt.envelope();
  assert.deepEqual(w1, []);
  const snapshot = captureSnapshot(snapshotEnvelope, 4);

  for (let i = 0; i < 6; i++) rt.advance();   // tick 4 -> tick 10
  const { normalized: originalEnvelope, warnings: w2 } = rt.envelope();
  assert.deepEqual(w2, []);
  const originalDerivation = derivation(rt.world);

  const recoveredRt = await recover(DEMO, snapshot, 6);
  const { normalized: recoveredEnvelope, warnings: w3 } = recoveredRt.envelope();
  assert.deepEqual(w3, []);

  assert.equal(canonicalOutcomeString(recoveredEnvelope), canonicalOutcomeString(originalEnvelope));
  assert.deepEqual(derivation(recoveredRt.world), originalDerivation);
});

test("recovery from a snapshot taken at tick zero", async () => {
  const rt = await loadedRuntime();
  rt.init();
  const { normalized: tick0Envelope } = rt.envelope();
  const snapshot = captureSnapshot(tick0Envelope, 0);

  for (let i = 0; i < 3; i++) rt.advance();
  const { normalized: originalEnvelope } = rt.envelope();
  const originalDerivation = derivation(rt.world);

  const recoveredRt = await recover(DEMO, snapshot, 3);
  const { normalized: recoveredEnvelope } = recoveredRt.envelope();
  assert.equal(canonicalOutcomeString(recoveredEnvelope), canonicalOutcomeString(originalEnvelope));
  assert.deepEqual(derivation(recoveredRt.world), originalDerivation);
});

test("recovery with zero ticks after snapshot reproduces the snapshot itself", async () => {
  const rt = await loadedRuntime();
  rt.init();
  for (let i = 0; i < 5; i++) rt.advance();
  const { normalized: envelope } = rt.envelope();
  const snapshot = captureSnapshot(envelope, 5);

  const recoveredRt = await recover(DEMO, snapshot, 0);
  const { normalized: recoveredEnvelope } = recoveredRt.envelope();
  assert.equal(canonicalOutcomeString(recoveredEnvelope), canonicalOutcomeString(envelope));
});

test("recovery refuses on a corrupted snapshot hash", async () => {
  const rt = await loadedRuntime();
  rt.init();
  for (let i = 0; i < 2; i++) rt.advance();
  const { normalized: envelope } = rt.envelope();
  const snapshot = captureSnapshot(envelope, 2);
  snapshot.semanticHash = "0".repeat(64);
  await assert.rejects(() => recover(DEMO, snapshot, 1), (e) => {
    assert.match(e.message, /hash/);
    return true;
  });
});

test("recovery refuses when snapshot does not match what replay actually produces", async () => {
  const rt = await loadedRuntime();
  rt.init();
  for (let i = 0; i < 2; i++) rt.advance();
  const { normalized: realEnvelope } = rt.envelope();
  const forgedEnvelope = { ...realEnvelope, situation: { ...realEnvelope.situation, x: 999 } };
  const forgedSnapshot = captureSnapshot(forgedEnvelope, 2);   // self-consistent, but wrong
  await assert.rejects(() => recover(DEMO, forgedSnapshot, 1), (e) => {
    assert.ok(e instanceof WorldRecoveryError);
    assert.equal(e.tag, "snapshot-replay-divergence");
    return true;
  });
});

test("the gate is capable of failing", async () => {
  const rt = await loadedRuntime();
  rt.init();
  for (let i = 0; i < 2; i++) rt.advance();
  const { normalized: envelope } = rt.envelope();
  const snapshot = captureSnapshot(envelope, 2);
  const recoveredRt = await recover(DEMO, snapshot, 0);
  const { normalized: recoveredEnvelope } = recoveredRt.envelope();
  const real = canonicalOutcomeString(recoveredEnvelope);
  const tampered = real.replace("2", "9");
  assert.notEqual(real, tampered, "the comparison must be able to observe this divergence");
});
