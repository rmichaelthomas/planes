// js/test/reso_walk.test.mjs — Horizon's first movement slice, verification
// suite (build prompt §9.2), graduated directly into a committed test file
// rather than a one-off scripts/verify-*.mjs — this repo's own test_gate.py
// forbids a committed scripts/verify_*/verify-* file (any extension);
// durable checks belong in a real test suite this gate runs, or they get
// deleted when the build merges. js/test/crossing_port.test.mjs set this
// exact precedent for the crossing port (PR #95) and its own header
// explains the rule in full; this file is that same substitution for
// paint/reso_walk.planes, covering build prompt §9.2's checks:
//
//   A — fixture semantics through the browser-safe worker path: a scripted
//       move/touch sequence walks the body toward the market, clamps at
//       both dock ends, and the touch only latches within range.
//   B — the traced step: why on the final boy-x names the movement input.
//   C — determinism: the same (init, events) sequence produces byte-
//       identical scene-intent line/hash sequences across two fresh runs;
//       a saved snapshot self-verifies and event-log-driven replay
//       reproduces it byte-identically (crossing_persistence.mjs's own
//       replay path, generic over fixtureUrl — reused unmodified, pointed
//       at reso_walk.planes instead of a_crossing.planes).
//   D — scope integrity: paint/reso_walk.planes carries no persistent
//       "moving"/"is-walking" field and no role/authoring/second-
//       interactable code path. NOT included here: a `git diff
//       --name-only main` file-count assertion — this repo already fixed
//       a permanent suite member that diffed against the moving "main"
//       ref once (test_cut_cost_verification.py, PR #95's own project
//       memory) and a second instance of that exact bug shape is not
//       repeated here. The file-list check is a one-time, pre-merge
//       verification (see reso-walk-verification.md), not a permanent
//       assertion that can only ever pass once.
//
// Check E (no step-cost/input-latency regression vs the crossing) is a
// live-browser measurement (playwright-cli against a served page), not a
// node:test assertion — see feat-reso-walk-movement-benchmarks-*.md,
// mirroring crossing-port-verification.md's own precedent for why a
// render/perf capture check has no `node --test` counterpart by design.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SimulationWorkerHandle, BrowserWorldRuntime } from "../world/runtime/worker.mjs";
import { parseSceneIntent } from "../scene/ir.mjs";
import {
  replayCrossing, eventsByTickFromLog, verifyCrossingSnapshot, hashWorld,
} from "../world/runtime/crossing_persistence.mjs";
import { WorldEventLog } from "../world_event_log.mjs";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const FIXTURE_URL = "https://example.test/paint/reso_walk.planes";
const BASE = "https://example.test/paint/";
const FILES = {
  [FIXTURE_URL]: path.join(REPO_ROOT, "paint/reso_walk.planes"),
  [`${BASE}draw.planes`]: path.join(REPO_ROOT, "paint/draw.planes"),
  [`${BASE}sound.planes`]: path.join(REPO_ROOT, "paint/sound.planes"),
  [`${BASE}math.planes`]: path.join(REPO_ROOT, "paint/math.planes"),
};

const openHandles = [];
function registerHandle(handle) {
  openHandles.push(handle);
  return handle;
}

// Mirrors crossing_port.test.mjs's own withStubbedFixtureFetch exactly,
// including the runaway-tick-loop cleanup rationale documented there — a
// SimulationWorkerHandle's own tick loop is a self-rescheduling setTimeout
// chain that runs forever until "cancel" arrives, so every handle this file
// creates registers itself for guaranteed cleanup regardless of how a test
// ends.
function withStubbedFixtureFetch(fn) {
  const real = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const key = String(url);
    if (FILES[key]) return { ok: true, text: async () => fs.readFileSync(FILES[key], "utf-8") };
    return { ok: false, text: async () => "" };
  };
  return fn().finally(() => {
    globalThis.fetch = real;
    for (const handle of openHandles.splice(0)) {
      try {
        handle.receive({ type: "cancel" });
      } catch {
        // best-effort — see crossing_port.test.mjs's own comment
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

function subjectOf(intent, id) {
  return intent.subjects.find((s) => s.id === id);
}

async function driveEvents(handle, posted, events) {
  let sequence = 0;
  for (const event of events) {
    sequence += 1;
    const seq = sequence;
    handle.receive({ type: "input", sequence: seq, event });
    // eslint-disable-next-line no-await-in-loop
    await waitUntil(() => posted.some((m) => m.acknowledgedInputSequence >= seq));
  }
}

// ---- A: fixture semantics through the worker path ------------------------

test("holding west through the worker walks the body toward the market and clamps at the dock minimum", async () => {
  await withStubbedFixtureFetch(async () => {
    const { handle, posted } = bootHandle();
    await handle.boot();
    const events = Array.from({ length: 80 }, () => ({ kind: "move", dir: "west" }));
    await driveEvents(handle, posted, events);
    handle.receive({ type: "cancel" });
    const deltas = posted.filter((m) => m.type === "delta");
    const xs = deltas.map((m) => subjectOf(parseSceneIntent(m.lines), "boy").x);
    for (let i = 1; i < xs.length; i += 1) assert.ok(xs[i] <= xs[i - 1], `x increased at step ${i}`);
    assert.equal(xs.at(-1), 0.05);
  });
});

test("holding east through the worker clamps at the dock maximum", async () => {
  await withStubbedFixtureFetch(async () => {
    const { handle, posted } = bootHandle();
    await handle.boot();
    const events = Array.from({ length: 80 }, () => ({ kind: "move", dir: "east" }));
    await driveEvents(handle, posted, events);
    handle.receive({ type: "cancel" });
    const last = posted.filter((m) => m.type === "delta").at(-1);
    assert.equal(subjectOf(parseSceneIntent(last.lines), "boy").x, 0.24);
  });
});

test("a touch only latches within range, and only once", async () => {
  await withStubbedFixtureFetch(async () => {
    const { handle, posted } = bootHandle();
    await handle.boot();

    // Far from the market: touch is a no-op.
    handle.receive({ type: "input", sequence: 1, event: { kind: "touch" } });
    await waitUntil(() => posted.some((m) => m.acknowledgedInputSequence >= 1));
    let latest = posted.filter((m) => m.type === "delta").at(-1);
    assert.equal(subjectOf(parseSceneIntent(latest.lines), "market").state, "untouched");

    // Walk into range, then touch.
    const westEvents = Array.from({ length: 25 }, () => ({ kind: "move", dir: "west" }));
    await driveEvents(handle, posted, westEvents);
    handle.receive({ type: "input", sequence: 27, event: { kind: "touch" } });
    await waitUntil(() => posted.some((m) => m.acknowledgedInputSequence >= 27));
    latest = posted.filter((m) => m.type === "delta").at(-1);
    let intent = parseSceneIntent(latest.lines);
    assert.equal(subjectOf(intent, "market").state, "greeted");
    assert.equal(intent.actions.some((a) => a.subject === "market"), false, "the approach prompt must clear once touched");

    // Touching again does not re-fire the response cue: the "scene cue"
    // line is unconditional every tick (a_crossing.planes's own idiom —
    // it always names the CURRENT cue, "dock-quiet" absent a fresh event),
    // so the meaningful assertion is that it is not market-greet again and
    // no new "audio cue" line accompanies it.
    handle.receive({ type: "input", sequence: 28, event: { kind: "touch" } });
    await waitUntil(() => posted.some((m) => m.acknowledgedInputSequence >= 28));
    handle.receive({ type: "cancel" });
    latest = posted.filter((m) => m.type === "delta").at(-1);
    intent = parseSceneIntent(latest.lines);
    assert.notEqual(intent.cues[0]?.id, "market-greet", "no repeated market-greet cue on a second touch");
    assert.equal(intent.audio.cues.length, 0, "no repeated audio cue on a second touch");
  });
});

// ---- B: the traced step ---------------------------------------------------

test("why on the final boy-x names the movement input that produced it (the traced step)", async () => {
  await withStubbedFixtureFetch(async () => {
    const direct = new BrowserWorldRuntime(FIXTURE_URL);
    await direct.load();
    direct.init();
    direct.itp.output.length = 0;
    direct.advance([{ kind: "move", dir: "west" }]);
    const { lines } = direct.takeOutput();
    const whyLine = lines.find((l) => l.includes(" from ") && l.includes("because"));
    assert.ok(whyLine, "no why-line found in this tick's output");
    assert.match(whyLine, /west/);
    assert.doesNotMatch(whyLine.split("\n")[0].trim(), /^-?\d+(\.\d+)?$/, "why must return a sentence, not a bare number");
  });
});

// ---- C: determinism + replay ----------------------------------------------

test("the same (init, events) sequence produces byte-identical scene-intent hashes across two fresh runs", async () => {
  await withStubbedFixtureFetch(async () => {
    async function hashesFor() {
      const rt = new BrowserWorldRuntime(FIXTURE_URL);
      await rt.load();
      rt.init();
      const out = [];
      const { lines: initLines } = rt.takeOutput();
      out.push(initLines.join("\n"));
      for (let tick = 0; tick < 60; tick += 1) {
        const event = tick % 3 === 0 ? { kind: "move", dir: "west" } : null;
        rt.advance(event ? [event] : []);
        const { lines } = rt.takeOutput();
        out.push(lines.join("\n"));
      }
      return out;
    }
    const a = await hashesFor();
    const b = await hashesFor();
    assert.deepEqual(a, b);
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
    handle.receive({ type: "input", sequence: 1, event: { kind: "move", dir: "west" } });
    await waitUntil(() => tickCount() >= tickAtInput + 1);
    eventLog.append(
      { tick: tickAtInput, actor: "test", affectedSubjects: ["boy"], rationale: "move:west", delta: null, event: { kind: "move", dir: "west" } },
      "2026-01-01T00:00:00Z",
    );

    tickAtInput = tickCount();
    handle.receive({ type: "input", sequence: 2, event: { kind: "move", dir: "west" } });
    await waitUntil(() => tickCount() >= tickAtInput + 1);
    eventLog.append(
      { tick: tickAtInput, actor: "test", affectedSubjects: ["boy"], rationale: "move:west", delta: null, event: { kind: "move", dir: "west" } },
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
    assert.equal(hashWorld(replayed.world), snapshot.hash);
  });
});

// ---- D: scope integrity ----------------------------------------------------

test("the fixture carries no persistent movement/role/authoring/second-interactable code path", () => {
  const src = fs.readFileSync(path.join(REPO_ROOT, "paint/reso_walk.planes"), "utf-8");
  // CODE only — this file's own header comments necessarily discuss (in
  // order to disclaim) exactly the words this check forbids ("no dialogue,
  // no inventory", "no 'moving'/'is-walking' field"), so a whole-file grep
  // would false-positive on its own documentation. Planes line comments
  // start with `#` (every .planes file in this corpus).
  const code = src.split("\n").filter((line) => !line.trim().startsWith("#")).join("\n");

  // No persistent "is moving"/"is walking" field on the WORLD RECORD
  // specifically — `moving` is deliberately used as a per-call render
  // PARAMETER (render-reso-walk's own third argument, transient, never
  // stored, decision 2's own render-time exception) — so this inspects
  // only the two `let next = { ... }` world-record literals, not every
  // occurrence of the word "moving" in the file.
  const recordLiterals = code.match(/^\s*let next = \{.*\}$/gm) ?? [];
  assert.ok(recordLiterals.length >= 2, "expected to find the world-record literals in world-init and advance");
  for (const literal of recordLiterals) {
    assert.doesNotMatch(literal, /\bmoving\s*:/, "a persistent 'moving' world-record field would violate decision 2/invariant 3");
    assert.doesNotMatch(literal, /\bis-walking\s*:|\bis-moving\s*:/, "a persistent is-walking/is-moving field would violate decision 2/invariant 3");
  }

  // Scope floor (invariant 5, failure mode #6): no second interactable, no
  // dialogue/inventory/role/authoring/descent code path.
  for (const forbidden of ["inventory", "dialogue", "role-of", "build-mode", "descend", "author-mode"]) {
    assert.doesNotMatch(code, new RegExp(forbidden, "i"), `unexpected scope-inflating token: ${forbidden}`);
  }
});

// ---- gate failability proof -------------------------------------------------

test("the worker-driven comparison is capable of failing", async () => {
  await withStubbedFixtureFetch(async () => {
    const direct = new BrowserWorldRuntime(FIXTURE_URL);
    await direct.load();
    direct.init();
    direct.itp.output.length = 0;
    direct.advance([{ kind: "move", dir: "west" }]);
    const { lines } = direct.takeOutput();
    const tampered = [...lines];
    tampered[0] = "tampered";
    assert.notDeepEqual(lines, tampered);
  });
});
