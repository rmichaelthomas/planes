// js/test/paint_examples.test.mjs — the three example programs (§4), headless.
//
// A.3/A.6's whole point: each program's computed effect surface is exactly
// what the ruling says it is, checked against the real analyser — and none
// of the three ever touches network. These read the actual files under
// paint/, not copies, so the test guards what ships.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { runProgram, analyseProgram } from "../browser_main.mjs";
import { step } from "../paint/loop.mjs";

function readExample(name) {
  const p = fileURLToPath(new URL(`../../paint/${name}.planes`, import.meta.url));
  return fs.readFileSync(p, "utf-8");
}

for (const name of ["turtle", "bloom", "snake"]) {
  test(`${name}.planes contains no \`foreign\` declaration`, () => {
    const src = readExample(name);
    assert.doesNotMatch(src, /\bforeign\b\s+\S+\s+from\s+"/);
  });

  test(`${name}.planes's surface never touches network`, () => {
    const { surface, error } = analyseProgram(readExample(name));
    assert.equal(error, null);
    assert.equal(surface.touches("network"), false);
  });
}

test("turtle.planes's surface is console only", () => {
  const { surface, error } = analyseProgram(readExample("turtle"));
  assert.equal(error, null);
  assert.equal(surface.touches("console"), true);
  assert.equal(surface.touches("file"), false);
  assert.equal(surface.touches("ambient"), false);
});

test("turtle.planes is static: it runs the same with no prelude at all", () => {
  const r = runProgram(readExample("turtle"), {});
  assert.equal(r.error, null);
  assert.equal(r.output[0], "clear");
  assert.ok(r.output.length > 10);
});

test("bloom.planes's surface is console only", () => {
  const { surface, error } = analyseProgram(readExample("bloom"));
  assert.equal(error, null);
  assert.equal(surface.touches("console"), true);
  assert.equal(surface.touches("file"), false);
  assert.equal(surface.touches("ambient"), false);
});

test("bloom.planes runs across many ticks with no state and no error", () => {
  const src = readExample("bloom");
  for (const tick of [0, 1, 50, 5000]) {
    const r = step(src, { tick, keys: [], pointer: { x: 0, y: 0, down: false }, state: null });
    assert.equal(r.error, null);
    assert.ok(r.lines.includes("clear"));
  }
});

test("snake.planes's surface is exactly console and file:write state.json", () => {
  const { surface, error } = analyseProgram(readExample("snake"));
  assert.equal(error, null);
  assert.equal(surface.touches("console"), true);
  assert.equal(surface.touches("file"), true);
  assert.equal(surface.touches("ambient"), false);
  assert.deepEqual(surface.targets("write"), ["state.json"]);
});

test("snake.planes's first tick (nothing state) initialises a live game", () => {
  const src = readExample("snake");
  const r = step(src, { tick: 0, keys: [], pointer: { x: 0, y: 0, down: false }, state: null });
  assert.equal(r.error, null);
  assert.equal(r.state.alive, true);
  assert.equal(r.state.score, 0);
});

test("snake.planes grows and scores when it reaches the apple", () => {
  const src = readExample("snake");
  let state = null;
  const keySeq = [[], ...Array(6).fill(["ArrowRight"]), ...Array(5).fill(["ArrowUp"])];
  for (let tick = 0; tick < keySeq.length; tick++) {
    const r = step(src, { tick, keys: keySeq[tick], pointer: { x: 0, y: 0, down: false }, state });
    assert.equal(r.error, null);
    state = r.state;
  }
  assert.equal(state.score, 1);
  assert.equal(state.body.length, 3);
});

test("snake.planes ends the game on a wall collision and then freezes", () => {
  const src = readExample("snake");
  let state = null;
  for (let tick = 0; tick < 30; tick++) {
    const r = step(src, { tick, keys: ["ArrowLeft"], pointer: { x: 0, y: 0, down: false }, state });
    assert.equal(r.error, null);
    state = r.state;
    if (!state.alive) break;
  }
  assert.equal(state.alive, false);
  const before = JSON.stringify(state);
  const r2 = step(src, { tick: 999, keys: ["ArrowRight"], pointer: { x: 0, y: 0, down: false }, state });
  assert.equal(r2.error, null);
  assert.equal(JSON.stringify(r2.state), before, "a dead game stays frozen");
  assert.ok(r2.lines.some((l) => l.includes("GAME OVER")));
});
