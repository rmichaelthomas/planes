import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import assert from "node:assert/strict";

import { stepGraph } from "../paint/loop.mjs";
import { createNodeModuleLoader } from "../module_loader_node.mjs";
import { analyseProgramGraph } from "../browser_main.mjs";
import { card } from "../paint/why.mjs";
import { parseSceneIntent } from "../scene/ir.mjs";
import {
  crossingStatus,
  parseAtlas,
  replayCrossing,
  splitCrossingLines,
  subjectsFromResult,
} from "../paint/a_crossing.mjs";

const sourcePath = fileURLToPath(new URL("../../paint/a_crossing.planes", import.meta.url));
const source = readFileSync(sourcePath, "utf8");

async function runCrossing({ tick = 0, seed = 481027, state = null, event = null } = {}) {
  const loader = createNodeModuleLoader({ base: sourcePath });
  return stepGraph(source, {
    tick,
    seed,
    state,
    event,
    keys: [],
    pointer: { x: 0, y: 0, down: false },
  }, { loader, base: path.dirname(sourcePath) });
}

test("ready fixture emits state and an inspectable Passage line", async () => {
  const result = await runCrossing();
  assert.equal(result.error, null);
  assert.equal(result.state.status, "crossing-ready");
  assert.equal(result.state.need, "care");
  assert.equal(result.state.phase, "choosing");
  assert.equal(result.state.progress, 0);
  assert.ok(result.lines.some((line) => line.includes("crossing-ready")));
});

test("Planes emits a complete renderer-independent scene intent", async () => {
  const result = await runCrossing();
  const lines = splitCrossingLines(result.lines);
  const intent = parseSceneIntent(result.lines);
  assert.equal(crossingStatus(result.lines), "crossing-ready");
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
    const ready = await runCrossing();
    const result = await runCrossing({ state: ready.state, event: { kind: "route", choice } });
    assert.equal(result.error, null);
    assert.equal(result.state.status, status);
  });
}

test("care education and work are distinct Planes-owned crossing needs", async () => {
  const ready = await runCrossing();
  for (const [choice, selected] of [["care", "clinic-beacon"], ["education", "radio-mast"], ["work", "market"]]) {
    const result = await runCrossing({ state: ready.state, event: { kind: "need", choice } });
    assert.equal(result.error, null);
    assert.equal(result.state.need, choice);
    assert.equal(result.state.selected, selected);
    assert.equal(result.state.phase, "planning");
  }
});

test("an active crossing advances and arrives from Planes tick state", async () => {
  const ready = await runCrossing();
  const depart = await runCrossing({ state: ready.state, event: { kind: "route", choice: "depart" } });
  assert.equal(depart.state.status, "crossing-active");
  const underway = await runCrossing({ state: depart.state, tick: 80 });
  assert.equal(underway.state.phase, "crossing");
  assert.equal(underway.state.progress, "0.5");
  const arrived = await runCrossing({ state: underway.state, tick: 160 });
  assert.equal(arrived.state.status, "crossing-arrived");
  assert.equal(arrived.state.progress, 1);
});

test("power and radio events revise Planes-owned state", async () => {
  const ready = await runCrossing();
  const clinic = await runCrossing({ state: ready.state, event: { kind: "power", choice: "clinic" } });
  assert.equal(clinic.state.selected, "clinic-beacon");
  assert.equal(clinic.state.minutes, 84);
  const relayed = await runCrossing({ state: clinic.state, event: { kind: "radio", choice: "relay" } });
  assert.equal(relayed.state.radio, "relayed");
});

test("every emitted subject resolves to real marks and a source line", async () => {
  const result = await runCrossing({ tick: 7 });
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

test("static analysis reports effects without executing the crossing", async () => {
  const loader = createNodeModuleLoader({ base: sourcePath });
  const analysis = await analyseProgramGraph(source, { loader, base: path.dirname(sourcePath) });
  assert.equal(analysis.error, null);
  assert.ok(analysis.surface.effects.some(({ kind, target }) => kind === "write" && target === "state.json"));
});

test("atlas is parsed only from Planes-emitted observations", async () => {
  const result = await runCrossing();
  assert.deepEqual(parseAtlas(result.lines).map(({ id }) => id), [
    "eriri-ukwu", "anomabu", "sabel", "tado", "bonny", "vela", "marronde", "banta", "reso", "nkwo-eriri", "route-cord",
  ]);
});

test("ordered replay is deterministic at a fixed seed", async () => {
  const loader = () => createNodeModuleLoader({ base: sourcePath });
  const options = {
    source,
    base: path.dirname(sourcePath),
    seed: 481027,
    events: [{ kind: "power", choice: "clinic" }, { kind: "radio", choice: "relay" }],
  };
  const first = await replayCrossing({ ...options, loader: loader() });
  const second = await replayCrossing({ ...options, loader: loader() });
  assert.deepEqual(first.state, second.state);
  assert.deepEqual(first.lines, second.lines);
  assert.deepEqual(parseSceneIntent(first.lines), parseSceneIntent(second.lines));
  assert.deepEqual(first.events, options.events);
});
