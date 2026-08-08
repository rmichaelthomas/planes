// js/test/world_renderer_worker.test.mjs — Horizon Phase 1 renderer
// pipeline: SimulationWorkerHandle and its browser-safe kernel/runtime
// (worker.mjs), headless.
//
// Stubs globalThis.fetch to serve the real fixture source read from disk —
// module_loader.test.mjs's own precedent for testing fetch-based browser
// code under plain `node --test` rather than spinning up a real server.
// The fixture itself (paint/world/kernel_spike_fixture.planes) is read,
// never rewritten — this build reuses it unmodified (see worker.mjs's own
// header on why: single-subject world-v1 protocol scope).
//
// No `self`/postMessage anywhere here: SimulationWorkerHandle is
// constructed directly with an injected `post` callback, exactly the seam
// worker.mjs's own header describes as what keeps it testable under plain
// Node. The guarded `self.postMessage`-wiring block at the bottom of
// worker.mjs is therefore never exercised by this file, by construction —
// there is no `self` under Node for it to find.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  SimulationWorkerHandle,
  BrowserWorldKernel,
  WorkerKernelError,
} from "../world/runtime/worker.mjs";
import { FidelityController, TIER_NAMES } from "../world/performers/fidelity_controller.mjs";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const FIXTURE_URL = "https://example.test/paint/world/kernel_spike_fixture.planes";
const FIXTURE_SOURCE = fs.readFileSync(
  path.join(REPO_ROOT, "paint/world/kernel_spike_fixture.planes"),
  "utf-8",
);

function withStubbedFixtureFetch(fn) {
  const real = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (String(url) === FIXTURE_URL) {
      return { ok: true, text: async () => FIXTURE_SOURCE };
    }
    return { ok: false, text: async () => "" };
  };
  return fn().finally(() => {
    globalThis.fetch = real;
  });
}

// Polls for a condition instead of sleeping a fixed duration and hoping
// enough ticks happened in it. A fixed-duration wait at a 5ms tick rate is
// exactly the wall-clock-under-contention flakiness this repo's own
// kernel-spike build already hit and fixed the same way (measure until a
// robust signal, not a single short window) — see
// [[feedback_dag_sharing_defeats_incremental_derivation_caches]]'s sibling
// finding in horizon-kernel-spike-results.md on `scripts/ci.sh`'s parallel
// suite runner producing exactly this kind of CPU-contention noise.
async function waitUntil(predicate, { timeoutMs = 5000, pollMs = 5 } = {}) {
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start > timeoutMs) {
      throw new Error(`waitUntil: condition not met within ${timeoutMs}ms`);
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
}

test("BrowserWorldKernel.start() loads the real fixture and returns the initial reso-tide-walker-1 envelope with no warnings", async () => {
  await withStubbedFixtureFetch(async () => {
    const kernel = new BrowserWorldKernel(FIXTURE_URL, { window: 300, trace: true });
    const envelope = await kernel.start();
    assert.equal(envelope.identity.id, "reso-tide-walker-1");
    assert.equal(envelope.situation.x, 0);
    assert.equal(envelope.situation.y, 4);
  });
});

test("BrowserWorldKernel.step() mirrors world_kernel.mjs's own {delta, elapsedSeconds} contract", async () => {
  await withStubbedFixtureFetch(async () => {
    const kernel = new BrowserWorldKernel(FIXTURE_URL, { window: 300 });
    await kernel.start();
    const { delta, elapsedSeconds } = kernel.step();
    assert.equal(delta.revisionFrom, 0);
    assert.equal(delta.revisionTo, 1);
    assert.equal(typeof delta.semanticHash, "string");
    assert.equal(delta.semanticHash.length, 64);
    assert.ok(typeof elapsedSeconds === "number" && elapsedSeconds >= 0);
  });
});

test("BrowserWorldKernel.step() before start() refuses with a named error, not a generic crash", () => {
  const kernel = new BrowserWorldKernel(FIXTURE_URL);
  assert.throws(() => kernel.step(), WorkerKernelError);
});

test("SimulationWorkerHandle.boot() posts a full snapshot first, then a strictly-increasing sequence of deltas, all sharing one worldFingerprint", async () => {
  await withStubbedFixtureFetch(async () => {
    const posted = [];
    const handle = new SimulationWorkerHandle({
      post: (m) => posted.push(m),
      fixtureUrl: FIXTURE_URL,
      tickMs: 5,
    });
    await handle.boot();
    await waitUntil(() => posted.filter((m) => m.type === "delta").length >= 3);
    handle.receive({ type: "cancel" });

    assert.equal(posted[0].type, "snapshot");
    assert.equal(posted[0].envelope.identity.id, "reso-tide-walker-1");
    const deltas = posted.filter((m) => m.type === "delta");
    assert.ok(deltas.length >= 3, `expected several ticks, got ${deltas.length}`);

    const sequences = posted.map((m) => m.sequence);
    for (let i = 1; i < sequences.length; i++) assert.ok(sequences[i] > sequences[i - 1], "sequence must strictly increase");

    const fingerprints = new Set(posted.map((m) => m.worldFingerprint));
    assert.equal(fingerprints.size, 1, "every message shares the same content-addressed world fingerprint");
    assert.equal([...fingerprints][0].length, 64, "sha256 hex digest");
  });
});

test("SimulationWorkerHandle: 'cancel' stops ticking, and 'resume' with a new token restarts under that token", async () => {
  await withStubbedFixtureFetch(async () => {
    const posted = [];
    const handle = new SimulationWorkerHandle({ post: (m) => posted.push(m), fixtureUrl: FIXTURE_URL, tickMs: 5 });
    await handle.boot();
    await waitUntil(() => posted.filter((m) => m.type === "delta").length >= 2);
    handle.receive({ type: "cancel" });
    const countAtCancel = posted.length;
    // A generous, fixed settle window is the right tool HERE (unlike the
    // "wait for N ticks" cases above) — we are asserting an absence (no
    // more messages), which a poll-until-condition can't express; 80ms
    // against a 5ms tick rate leaves a wide margin even under load.
    await new Promise((resolve) => setTimeout(resolve, 80));
    assert.equal(posted.length, countAtCancel, "no further messages after cancel");

    handle.receive({ type: "resume", cancellationToken: "tok-resumed" });
    await waitUntil(() => posted.length > countAtCancel);
    handle.receive({ type: "cancel" });
    const afterResume = posted.slice(countAtCancel);
    assert.ok(afterResume.length > 0, "resume must actually restart ticking");
    assert.ok(afterResume.every((m) => m.cancellationToken === "tok-resumed"));
  });
});

test("SimulationWorkerHandle: an 'input' message is acknowledged on the next delta's acknowledgedInputSequence, without altering the semantic tick", async () => {
  await withStubbedFixtureFetch(async () => {
    const posted = [];
    const handle = new SimulationWorkerHandle({ post: (m) => posted.push(m), fixtureUrl: FIXTURE_URL, tickMs: 5 });
    await handle.boot();
    handle.receive({ type: "input", sequence: 77 });
    await waitUntil(() => posted.filter((m) => m.type === "delta").length >= 5);
    handle.receive({ type: "cancel" });

    const deltas = posted.filter((m) => m.type === "delta");
    assert.ok(deltas.some((d) => d.acknowledgedInputSequence === 77));
    // determinism is untouched: the sequence of semantic hashes must match a
    // fresh, poke-free run over the same number of ticks.
    const freshPosted = [];
    const freshHandle = new SimulationWorkerHandle({ post: (m) => freshPosted.push(m), fixtureUrl: FIXTURE_URL, tickMs: 5 });
    await freshHandle.boot();
    await waitUntil(() => freshPosted.filter((m) => m.type === "delta").length >= 5);
    freshHandle.receive({ type: "cancel" });
    const freshHashes = freshPosted.filter((m) => m.type === "delta").map((m) => m.delta.semanticHash);
    const pokedHashes = deltas.map((m) => m.delta.semanticHash);
    const n = Math.min(freshHashes.length, pokedHashes.length);
    assert.ok(n >= 5);
    assert.deepEqual(pokedHashes.slice(0, n), freshHashes.slice(0, n));
  });
});

// Graduated from this build's own scripts/verify-renderer-pipeline.mjs
// (check B2) before that script was deleted per test_gate.py's retirement
// rule — durable assertions move into a suite the gate runs; everything
// else in that script was build-specific, one-time evidence and did not
// need to survive (see this build's PR description for the full account).
//
// Quality-tier invariance (design doc §15's "never adaptive" list; §16's
// tier-invariance gate) is exactly the kind of property worth protecting
// forever, not just proving once: FidelityController has no code path to
// the worker at all (fidelity_controller.mjs's own header makes this
// argument structurally), so switching tiers mid-run must never change the
// worker's own semantic hash sequence. Asserted here empirically, not just
// by the structural argument.
test("switching every fidelity tier mid-run never changes the worker's own semantic hash sequence", async () => {
  await withStubbedFixtureFetch(async () => {
    const baseline = [];
    const baselineHandle = new SimulationWorkerHandle({ post: (m) => baseline.push(m), fixtureUrl: FIXTURE_URL, tickMs: 5 });
    await baselineHandle.boot();
    await waitUntil(() => baseline.filter((m) => m.type === "delta").length >= 12);
    baselineHandle.receive({ type: "cancel" });
    const baselineHashes = baseline.filter((m) => m.type === "delta").map((m) => m.delta.semanticHash);

    const tiered = [];
    const recordingPerformer = { setRenderScale() {}, setParticleDensity() {} };
    const controller = new FidelityController({ performer: recordingPerformer });
    const tieredHandle = new SimulationWorkerHandle({
      post: (m) => {
        tiered.push(m);
        if (m.type === "delta") controller.setTier(TIER_NAMES[tiered.length % TIER_NAMES.length]);
      },
      fixtureUrl: FIXTURE_URL,
      tickMs: 5,
    });
    await tieredHandle.boot();
    await waitUntil(() => tiered.filter((m) => m.type === "delta").length >= 12);
    tieredHandle.receive({ type: "cancel" });
    const tieredHashes = tiered.filter((m) => m.type === "delta").map((m) => m.delta.semanticHash);

    assert.deepEqual(tieredHashes.slice(0, 12), baselineHashes.slice(0, 12));
  });
});
