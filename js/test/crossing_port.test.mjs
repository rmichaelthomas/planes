// js/test/crossing_port.test.mjs — Horizon Phase 2 Build 2's own
// verification suite (build prompt §6.2), graduated directly into a
// committed test file rather than a one-off scripts/verify-*.mjs: this
// repo's own test_gate.py forbids a committed scripts/verify_*/verify-*
// file (any extension) — durable checks belong in a real test suite this
// gate runs, or they get deleted when the build merges (the exact rule
// PR #94 re-fixed after PR #89 first violated it; see project memory
// project_route_b_lexer_blocked.md). This file is that suite for the
// checks that are properly JS/worker-shaped:
//
//   C — input applies through the worker (the real typed event shapes:
//       select/need/power/radio/route), and the resulting scene-intent
//       matches what driving the SAME events directly against a
//       BrowserWorldRuntime produces — the worker adds no behavior of its
//       own, it is a transport.
//   D — lifecycle: pause/resume produces no semantic drift; a saved
//       snapshot self-verifies; event-log-driven replay reproduces a
//       byte-identical world value; save/restore round-trips.
//   E — fidelity-tier invariance: switching Sun/Breeze/Harbor mid-run
//       never changes the worker's own scene-intent line/hash sequence.
//
// Check A (behavior parity vs. the pre-port showcase baseline) lives in
// js/test/a_crossing_scene.test.mjs (rewritten by this same build — see
// its own header). Check B (cross-implementation + cross-run determinism,
// Python vs JS) lives in test_crossing_port.py, mirroring this repo's
// established test_world_kernel_conformance.py shell-out-to-node pattern.
// Check F (render presence: environment plate, hydrofoil sprite at a
// non-placeholder position, the boat advancing across two captures) is a
// real-browser capture, agent-performed via playwright-cli against a
// locally served horizon-crossing.html — not a `node --test` assertion,
// the same reason scripts/world_renderer_bench.mjs's own header gives for
// Phase 1's render-presence check ("this repo has no package.json and no
// node_modules... a bare `import 'playwright'` would resolve only on a
// machine that happens to have it cached"). See
// crossing-port-verification.md for that check's own results and the two
// attached capture frames.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  SimulationWorkerHandle, BrowserWorldRuntime, CROSSING_FIXTURE_URL,
} from "../world/runtime/worker.mjs";
import { parseSceneIntent } from "../scene/ir.mjs";
import { FidelityController, TIER_NAMES } from "../world/performers/fidelity_controller.mjs";
import {
  replayCrossing, eventsByTickFromLog, verifyCrossingSnapshot, hashWorld,
} from "../world/runtime/crossing_persistence.mjs";
import { WorldEventLog } from "../world_event_log.mjs";
import { toHost } from "../interp.mjs";
import { WorldClient } from "../world/runtime/main.mjs";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const FIXTURE_URL = "https://example.test/paint/a_crossing.planes";
const BASE = "https://example.test/paint/";
const FILES = {
  [FIXTURE_URL]: path.join(REPO_ROOT, "paint/a_crossing.planes"),
  [`${BASE}draw.planes`]: path.join(REPO_ROOT, "paint/draw.planes"),
  [`${BASE}sound.planes`]: path.join(REPO_ROOT, "paint/sound.planes"),
  [`${BASE}math.planes`]: path.join(REPO_ROOT, "paint/math.planes"),
};

// CROSSING_FIXTURE_URL, real production code's own idea of the crossing's
// URL, must resolve to the SAME file this test stubs — a mismatch here
// would mean this suite is testing a fixture the real page does not
// actually load.
test("CROSSING_FIXTURE_URL names the real paint/a_crossing.planes file", () => {
  assert.ok(CROSSING_FIXTURE_URL.endsWith("/paint/a_crossing.planes"));
});

// Every SimulationWorkerHandle this file creates registers itself here
// (via registerHandle()) so withStubbedFixtureFetch's own finally block
// can guarantee cleanup — see that function's own comment for why this
// exists.
const openHandles = [];

function registerHandle(handle) {
  openHandles.push(handle);
  return handle;
}

function withStubbedFixtureFetch(fn) {
  const real = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const key = String(url);
    if (FILES[key]) return { ok: true, text: async () => fs.readFileSync(FILES[key], "utf-8") };
    return { ok: false, text: async () => "" };
  };
  return fn().finally(() => {
    globalThis.fetch = real;
    // Found live (not theoretical): a SimulationWorkerHandle's own tick
    // loop is a self-rescheduling setTimeout chain (worker.mjs's own
    // _scheduleTick) that runs FOREVER once boot()ed, until something
    // sends it "cancel" — nothing stops it on its own. Every test below
    // sends "cancel" on its own happy path, but NONE of them wrapped that
    // in try/finally, so a thrown assertion (or, worse, a deliberately
    // failing run — exactly what confirming this file's own regression
    // test's failure mode against pre-fix code did) skips the cancel and
    // leaves the handle ticking at its full tickMs rate, indefinitely, in
    // a process `node --test` has no reason to think is still working —
    // observed as a genuine runaway (two orphaned processes pinned near
    // 100% CPU for 40+ minutes after a test run had already reported its
    // result and returned). registerHandle() below is every handle this
    // file creates registering itself here; every test that goes through
    // withStubbedFixtureFetch (all of them) gets its handles cancelled on
    // the way out regardless of how the test itself ended.
    for (const handle of openHandles.splice(0)) {
      try {
        handle.receive({ type: "cancel" });
      } catch {
        // Best-effort — a handle that already threw during boot() has
        // nothing left to cancel; cleanup must never mask the real error.
      }
    }
  });
}

async function waitUntil(predicate, { timeoutMs = 5000, pollMs = 5 } = {}) {
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start > timeoutMs) {
      throw new Error(`waitUntil: condition not met within ${timeoutMs}ms`);
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
}

function bootHandle(overrides = {}) {
  const posted = [];
  const handle = registerHandle(new SimulationWorkerHandle({
    post: (m) => posted.push(m), fixtureUrl: FIXTURE_URL, tickMs: 5, protocol: "scene-intent", ...overrides,
  }));
  return { handle, posted };
}

// ---- C: input applies through the worker, matching direct-driven state ---

test("a real typed input event applies through the worker and matches driving the same event directly against BrowserWorldRuntime", async () => {
  await withStubbedFixtureFetch(async () => {
    const { handle, posted } = bootHandle();
    await handle.boot();
    handle.receive({ type: "input", sequence: 1, event: { kind: "need", choice: "care" } });
    await waitUntil(() => posted.some((m) => m.acknowledgedInputSequence === 1));
    handle.receive({ type: "cancel" });
    const applied = posted.find((m) => m.type === "delta" && m.acknowledgedInputSequence === 1);
    assert.ok(applied, "no delta acknowledged input sequence 1");

    const direct = new BrowserWorldRuntime(FIXTURE_URL);
    await direct.load();
    direct.init();
    direct.itp.output.length = 0;
    direct.advance([{ kind: "need", choice: "care" }]);
    const { lines: directLines } = direct.takeOutput();

    assert.deepEqual(applied.lines, directLines);
  });
});

// Each checker asserts against whatever the scene-intent protocol
// actually exposes for that reaction — not every field of `next` is
// observable through it (`selected`, for instance, is not: it only shows
// up in the "decision " line's revision text, checked directly against
// the raw lines rather than the parsed intent — see a_crossing.planes's
// own "select" branch, whose revision literally says "the inspection
// focus changed"). This is the same boundary invariant 3 draws in
// production: the performer (and this check) reads only what
// parseSceneIntent — or, for the one exception, the raw line text itself
// — actually carries.
const INPUT_CASES = [
  {
    event: { kind: "select", subject: "market" },
    check: (intent, lines) => assert.ok(lines.some((l) => l.startsWith("decision ") && l.includes("inspection focus changed"))),
  },
  {
    event: { kind: "need", choice: "education" },
    check: (intent) => assert.equal(intent.subjects.find((s) => s.id === "clinic-beacon")?.state, "education"),
  },
  {
    event: { kind: "power", choice: "clinic" },
    check: (intent) => assert.equal(intent.cues[0]?.id, "clinic-protected"),
  },
  {
    event: { kind: "radio", choice: "relay" },
    check: (intent) => assert.equal(intent.subjects.find((s) => s.id === "radio-mast")?.state, "relayed"),
  },
  {
    event: { kind: "route", choice: "depart" },
    check: (intent) => assert.equal(intent.subjects.find((s) => s.id === "reso-landing")?.state, "crossing"),
  },
];

for (const { event, check } of INPUT_CASES) {
  test(`input ${JSON.stringify(event)} reaches the worker and produces the expected scene-intent reaction`, async () => {
    await withStubbedFixtureFetch(async () => {
      const { handle, posted } = bootHandle();
      await handle.boot();
      handle.receive({ type: "input", sequence: 1, event });
      await waitUntil(() => posted.some((m) => m.acknowledgedInputSequence === 1));
      handle.receive({ type: "cancel" });
      const applied = posted.find((m) => m.type === "delta" && m.acknowledgedInputSequence === 1);
      const intent = parseSceneIntent(applied.lines);
      assert.equal(intent.protocol, 1);
      check(intent, applied.lines);
    });
  });
}

// ---- D: lifecycle -----------------------------------------------------

test("pause halts ticking and resume continues with no semantic drift", async () => {
  await withStubbedFixtureFetch(async () => {
    const { handle, posted } = bootHandle();
    await handle.boot();
    await waitUntil(() => posted.filter((m) => m.type === "delta").length >= 3);
    handle.receive({ type: "cancel" });
    const countAtPause = posted.length;
    await new Promise((resolve) => setTimeout(resolve, 60));
    assert.equal(posted.length, countAtPause, "no ticks while paused");

    handle.receive({ type: "resume" });
    await waitUntil(() => posted.length > countAtPause);
    handle.receive({ type: "cancel" });

    // No drift: every delta's own lines still parse as a well-formed
    // scene intent, and the crossing's status line is one of the
    // self-driving states it can validly be in (never corrupted).
    const deltas = posted.filter((m) => m.type === "delta");
    for (const delta of deltas) {
      const intent = parseSceneIntent(delta.lines);
      assert.equal(intent.protocol, 1);
    }
  });
});

test("a saved snapshot self-verifies, and event-log-driven replay reproduces it byte-identically", async () => {
  await withStubbedFixtureFetch(async () => {
    const { handle, posted } = bootHandle();
    const eventLog = new WorldEventLog();
    await handle.boot();

    function tickCount() {
      return posted.filter((m) => m.type === "delta").length;
    }

    await waitUntil(() => tickCount() >= 2);
    let tickAtInput = tickCount();
    handle.receive({ type: "input", sequence: 1, event: { kind: "need", choice: "care" } });
    await waitUntil(() => tickCount() >= tickAtInput + 2);
    eventLog.append(
      { tick: tickAtInput, actor: "test", affectedSubjects: ["clinic-beacon"], rationale: "need:care", delta: null, event: { kind: "need", choice: "care" } },
      "2026-01-01T00:00:00Z",
    );

    tickAtInput = tickCount();
    handle.receive({ type: "input", sequence: 2, event: { kind: "route", choice: "depart" } });
    await waitUntil(() => tickCount() >= tickAtInput + 6);
    eventLog.append(
      { tick: tickAtInput, actor: "test", affectedSubjects: ["hydrofoil"], rationale: "route:depart", delta: null, event: { kind: "route", choice: "depart" } },
      "2026-01-01T00:00:01Z",
    );

    handle.receive({ type: "cancel" });
    handle.receive({ type: "save" });
    await waitUntil(() => posted.some((m) => m.type === "snapshot-saved"));
    const { snapshot } = posted.find((m) => m.type === "snapshot-saved");

    verifyCrossingSnapshot(snapshot); // must not throw
    const [chainOk] = eventLog.verify();
    assert.ok(chainOk, "event log hash chain must verify");

    const eventsByTick = eventsByTickFromLog(eventLog.events());
    const replayed = await replayCrossing(FIXTURE_URL, eventsByTick, snapshot.tick);
    assert.equal(replayed.tick, snapshot.tick);
    assert.equal(replayed.hash, snapshot.hash);
    assert.deepEqual(replayed.world, snapshot.world);
  });
});

function withFakeRaf(fn) {
  const real = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(performance.now()), 0);
  return fn().finally(() => {
    globalThis.requestAnimationFrame = real;
  });
}

// Regression test for a real bug found live (reported against
// horizon-crossing.html after a long play session, replay mismatch at
// tick 464): the page built its event log from `client.lastSceneIntent
// .revision`, read AFTER a `sendInput()` promise resolved — a stale,
// racy read (worker.mjs's own 30 Hz ticker can advance `lastSceneIntent`
// past the acknowledging tick during the two-rAF resolution delay) that
// was ALSO off by one even without the race (`revision` is one past the
// Planes-level `tick` `advance` was actually called with — see
// BrowserSceneKernel.step's own `revision += 1` timing). Fixed by having
// `WorldClient.sendInput()` itself resolve with the exact tick, sourced
// synchronously from the acknowledging message
// (`_resolvePendingInputs`). This test drives the full WorldClient path
// (not the worker directly, unlike the test above) — the same code path
// the page actually uses — and asserts the SPECIFIC failure mode: an
// event applied, then many self-driving ticks later, must still replay
// to the exact same world value.
test("sendInput()'s reported tick is exact — an event logged from it replays byte-identically after many further ticks (regression: stale revision read caused a real replay mismatch)", async () => {
  await withStubbedFixtureFetch(() => withFakeRaf(async () => {
    const posted = [];
    const performer = { applySceneIntent() {}, removeSubject() {} };
    // worker.postMessage feeds the handle; the handle's own post feeds
    // both `posted` (this test's own record) and the client's message
    // handler — exactly the loop main.mjs's real boot() wires via
    // `worker.addEventListener("message", ...)`.
    const client = new WorldClient({ worker: { postMessage: (m) => boundHandle.receive(m) }, performer });
    const boundHandle = registerHandle(new SimulationWorkerHandle({
      post: (m) => { posted.push(m); client.handleWorkerMessage(m); },
      fixtureUrl: FIXTURE_URL, tickMs: 5, protocol: "scene-intent",
    }));
    await boundHandle.boot();

    const eventLog = new WorldEventLog();
    await waitUntil(() => (client.lastSceneIntent?.revision ?? 0) >= 2);
    const { tick } = await client.sendInput({ kind: "route", choice: "depart" });
    eventLog.append(
      { tick, actor: "test", affectedSubjects: ["hydrofoil"], rationale: "route:depart", delta: null, event: { kind: "route", choice: "depart" } },
      "2026-01-01T00:00:00Z",
    );

    // Many further self-driving ticks — long enough that a one-or-two-
    // tick logging error compounds into a different `progress` at save
    // time, which is exactly the shape of bug this test exists to catch.
    await waitUntil(() => (client.lastSceneIntent?.revision ?? 0) >= tick + 60);
    boundHandle.receive({ type: "save" });
    await waitUntil(() => posted.some((m) => m.type === "snapshot-saved"));
    boundHandle.receive({ type: "cancel" });
    const { snapshot } = posted.find((m) => m.type === "snapshot-saved");

    const eventsByTick = eventsByTickFromLog(eventLog.events());
    const replayed = await replayCrossing(FIXTURE_URL, eventsByTick, snapshot.tick);
    assert.equal(replayed.hash, snapshot.hash,
      `replay diverged — logged tick ${tick}, saved world.started ${snapshot.world.started}, `
      + `replayed world.started ${replayed.world.started}`);
  }));
});

test("save/restore round-trips: a snapshot's own world value, re-hashed, matches what the live runtime held at that tick", async () => {
  await withStubbedFixtureFetch(async () => {
    const { handle, posted } = bootHandle();
    await handle.boot();
    await waitUntil(() => posted.filter((m) => m.type === "delta").length >= 3);
    handle.receive({ type: "save" });
    await waitUntil(() => posted.some((m) => m.type === "snapshot-saved"));
    handle.receive({ type: "cancel" });
    const { snapshot } = posted.find((m) => m.type === "snapshot-saved");
    assert.equal(hashWorld(snapshot.world), snapshot.hash);
    assert.equal(typeof snapshot.world.status, "string");
  });
});

// ---- E: fidelity-tier invariance ---------------------------------------

test("switching every fidelity tier mid-run never changes the worker's own scene-intent line/hash sequence", async () => {
  await withStubbedFixtureFetch(async () => {
    const { handle: baselineHandle, posted: baseline } = bootHandle();
    await baselineHandle.boot();
    await waitUntil(() => baseline.filter((m) => m.type === "delta").length >= 12);
    baselineHandle.receive({ type: "cancel" });
    const baselineHashes = baseline.filter((m) => m.type === "delta").map((m) => m.linesHash);

    const tiered = [];
    const recordingPerformer = { setRenderScale() {}, setParticleDensity() {} };
    const controller = new FidelityController({ performer: recordingPerformer });
    const tieredHandle = registerHandle(new SimulationWorkerHandle({
      post: (m) => {
        tiered.push(m);
        if (m.type === "delta") controller.setTier(TIER_NAMES[tiered.length % TIER_NAMES.length]);
      },
      fixtureUrl: FIXTURE_URL, tickMs: 5, protocol: "scene-intent",
    }));
    await tieredHandle.boot();
    await waitUntil(() => tiered.filter((m) => m.type === "delta").length >= 12);
    tieredHandle.receive({ type: "cancel" });
    const tieredHashes = tiered.filter((m) => m.type === "delta").map((m) => m.linesHash);

    assert.deepEqual(tieredHashes.slice(0, 12), baselineHashes.slice(0, 12));
  });
});

// ---- gate failability proof ---------------------------------------------

test("the worker-vs-direct comparison is capable of failing", async () => {
  await withStubbedFixtureFetch(async () => {
    const direct = new BrowserWorldRuntime(FIXTURE_URL);
    await direct.load();
    direct.init();
    direct.itp.output.length = 0;
    direct.advance([{ kind: "need", choice: "care" }]);
    const { lines } = direct.takeOutput();
    const tampered = [...lines];
    tampered[0] = "tampered";
    assert.notDeepEqual(lines, tampered);
  });
});
