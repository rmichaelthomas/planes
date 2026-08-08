// js/test/a_crossing_scene.test.mjs — paint/a_crossing.planes, driven
// through the PERSISTENT-KERNEL calling convention (Horizon Phase 2
// Build 2's own port: world-init/advance, not the showcase path's
// stepGraph/composePrelude single-pass re-interpretation).
//
// REWRITTEN, NOT JUST PATCHED. Every test here existed before this build,
// driving the OLD `stepGraph(source, {tick, seed, state, event, ...})`
// convention paint/a_crossing.planes no longer supports at all — the port
// moved every bit of that top-level logic into world-init/advance
// function bodies (see the .planes file's own header), so the old
// `runCrossing` helper's fresh-stepGraph-per-call shape has no equivalent
// entry point anymore. This file preserves every ORIGINAL assertion's
// intent (ready state, complete scene intent, every route/need/power/
// radio branch, tick-driven arrival, subject provenance, atlas parsing,
// determinism) against the new calling convention, plus one assertion
// that changed on purpose: the static effect surface (see that test's own
// comment for why).

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import assert from "node:assert/strict";

import { WorldRuntime } from "../world_runtime.mjs";
import { toHost } from "../interp.mjs";
import { createNodeModuleLoader } from "../module_loader_node.mjs";
import { analyseProgramGraph } from "../browser_main.mjs";
import { card } from "../paint/why.mjs";
import { parseSceneIntent } from "../scene/ir.mjs";
import { crossingStatus, parseAtlas, splitCrossingLines, subjectsFromResult } from "../paint/a_crossing.mjs";

const sourcePath = fileURLToPath(new URL("../../paint/a_crossing.planes", import.meta.url));
const source = readFileSync(sourcePath, "utf8");

async function boot() {
  const rt = new WorldRuntime(sourcePath, {});
  await rt.load();
  return rt;
}

// One capture per call: the state (plain JSON, via toHost) plus that
// call's own show-line output and trace — takeOutput() (Horizon Phase 2
// Build 2's own gap-fix on WorldRuntime) is what makes this possible at
// all, draining exactly the lines/trace THIS call produced.
function capture(rt) {
  const { lines, trace } = rt.takeOutput();
  return { state: toHost(rt.world.value), lines, trace, annotations: rt.itp.annotations };
}

function init(rt) {
  rt.init();
  return capture(rt);
}

function step(rt, events = []) {
  rt.advance(events);
  return capture(rt);
}

function stepN(rt, n, events = []) {
  let result;
  for (let i = 0; i < n; i += 1) result = step(rt, events);
  return result;
}

test("ready fixture emits state and an inspectable Passage line", async () => {
  const ready = init(await boot());
  assert.equal(ready.state.status, "crossing-ready");
  assert.equal(ready.state.need, "care");
  assert.equal(ready.state.phase, "choosing");
  assert.equal(ready.state.progress, 0);
  assert.ok(ready.lines.some((line) => line.includes("crossing-ready")));
});

test("Planes emits a complete renderer-independent scene intent", async () => {
  const ready = init(await boot());
  const lines = splitCrossingLines(ready.lines);
  const intent = parseSceneIntent(ready.lines);
  assert.equal(crossingStatus(ready.lines), "crossing-ready");
  assert.equal(lines.drawing[0], "draw protocol 3");
  assert.ok(lines.drawing.length > 12);
  assert.equal(lines.sound[0], "sound protocol 1");
  assert.equal(intent.environment.id, "bright-passage");
  assert.equal(intent.subjects.find(({ id }) => id === "hydrofoil").asset, "hydrofoil-main");
  assert.equal(intent.routes[0].progress, 0);
  assert.deepEqual(intent.actions.slice(0, 3).map(({ kind, choice }) => `${kind}:${choice}`), ["need:care", "need:education", "need:work"]);
  assert.equal(intent.audio.beds[0].id, "channel-day");
});

for (const [choice, status] of [
  ["shelter", "crossing-delayed"],
  ["reserve", "crossing-refused"],
  ["depart", "crossing-active"],
]) {
  test(`fixture reaches ${status}`, async () => {
    const rt = await boot();
    init(rt);
    const result = step(rt, [{ kind: "route", choice }]);
    assert.equal(result.state.status, status);
  });
}

test("care education and work are distinct Planes-owned crossing needs", async () => {
  for (const [choice, selected] of [["care", "clinic-beacon"], ["education", "radio-mast"], ["work", "market"]]) {
    const rt = await boot();
    init(rt);
    const result = step(rt, [{ kind: "need", choice }]);
    assert.equal(result.state.need, choice);
    assert.equal(result.state.selected, selected);
    assert.equal(result.state.phase, "planning");
  }
});

test("an active crossing advances and arrives from Planes tick state", async () => {
  const rt = await boot();
  init(rt);
  const depart = step(rt, [{ kind: "route", choice: "depart" }]); // tick 0 -> 1
  assert.equal(depart.state.status, "crossing-active");
  // Self-driving ticks (empty events) — advance() auto-increments rt.tick
  // by exactly 1 per call, exactly as the real worker's fixed-step
  // schedule does; a persistent kernel has no "jump to tick N" the old
  // per-call stepGraph model did, so this walks there one tick at a time
  // (79 more calls to reach the underway sample below at absolute tick 80).
  const underway = stepN(rt, 80); // tick 1 .. 80
  assert.equal(underway.state.phase, "crossing");
  // A plain JS number here, not the "0.5" STRING the original (showcase-
  // path) version of this test asserted: that version's state crossed
  // through `write ... to "state.json"`'s JSON serialization, which
  // stringifies an exact non-integer Planes rational to preserve it
  // exactly through the round-trip. toHost() (used here, and by every
  // other consumer of a persistent-kernel world value — computeDelta,
  // the world-v1 envelope, etc.) converts the same exact value straight
  // to a JS double instead; 1/2 has a perfect IEEE-754 representation, so
  // nothing is actually lost, only the wire shape differs.
  assert.equal(underway.state.progress, 0.5);
  const arrived = stepN(rt, 80); // tick 81 .. 160
  assert.equal(arrived.state.status, "crossing-arrived");
  assert.equal(arrived.state.progress, 1);
});

test("power and radio events revise Planes-owned state", async () => {
  const rt = await boot();
  init(rt);
  const clinic = step(rt, [{ kind: "power", choice: "clinic" }]);
  assert.equal(clinic.state.selected, "clinic-beacon");
  assert.equal(clinic.state.minutes, 84);
  const relayed = step(rt, [{ kind: "radio", choice: "relay" }]);
  assert.equal(relayed.state.radio, "relayed");
});

test("every emitted subject resolves to real marks and a source line", async () => {
  const rt = await boot();
  init(rt);
  // Self-driving ticks to reach tick 7 (paint/a_crossing.planes's phase
  // stays "choosing" the whole way — no event fires, and the self-drive
  // branch only moves anything once phase is "crossing"), matching the
  // original test's intent of sampling a non-zero tick's animation phase,
  // not a semantically different state.
  const result = stepN(rt, 7);
  const subjects = subjectsFromResult(result);
  assert.ok(subjects.length >= 10);
  const hydrofoil = subjects.find(({ id }) => id === "hydrofoil");
  assert.ok(hydrofoil.sourceLine > 0);
  assert.match(result.lines[hydrofoil.outputIndex], /^scene subject hydrofoil /);
  assert.match(source.split("\n")[hydrofoil.sourceLine - 1], /scene subject hydrofoil/);
  assert.equal(typeof hydrofoil.node.kind, "string");
  assert.equal(result.trace[hydrofoil.outputIndex][1], hydrofoil.sourceLine);
  assert.equal(card(hydrofoil.node, { annotations: result.annotations }).origin.kind, "input");
});

// Horizon Phase 2 Build 2's own change, not a preserved assertion: the
// showcase-path program's static effect surface named `write ... to
// "state.json"` because the whole file executed at top level every tick.
// The ported program's real effects (show, the drawing/sound protocol)
// only become reachable once something actually CALLS world-init/advance
// — nothing is invoked at the file's own top level anymore (every world
// program built on this convention has the same empty top-level surface;
// this is not a regression, it is what "the kernel calls it" means
// statically). `write` is gone outright: the build prompt's own
// instruction ("the kernel's own snapshot substrate replaces it") — see
// paint/a_crossing.planes's header and js/world/runtime/crossing_
// persistence.mjs for where that snapshot responsibility actually lives
// now.
test("the ported program's static effect surface is empty at the top level — write is gone, not merely unreachable", async () => {
  const loader = createNodeModuleLoader({ base: sourcePath });
  const analysis = await analyseProgramGraph(source, { loader, base: sourcePath });
  assert.equal(analysis.error, null);
  assert.deepEqual(analysis.surface.effects, []);
});

test("atlas is parsed only from Planes-emitted observations", async () => {
  const ready = init(await boot());
  assert.deepEqual(parseAtlas(ready.lines).map(({ id }) => id), [
    "eriri-ukwu", "anomabu", "sabel", "tado", "bonny", "vela", "marronde", "banta", "reso", "nkwo-eriri", "route-cord",
  ]);
});

test("two fresh runtimes, the same fixed seed and event sequence, produce byte-identical state and scene intent", async () => {
  const events = [{ kind: "power", choice: "clinic" }, { kind: "radio", choice: "relay" }];
  async function run() {
    const rt = await boot();
    init(rt);
    let last;
    for (const event of events) last = step(rt, [event]);
    return last;
  }
  const first = await run();
  const second = await run();
  assert.deepEqual(first.state, second.state);
  assert.deepEqual(first.lines, second.lines);
  assert.deepEqual(parseSceneIntent(first.lines), parseSceneIntent(second.lines));
});
