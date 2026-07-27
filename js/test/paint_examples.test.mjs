// js/test/paint_examples.test.mjs — the three example programs, headless.
//
// A.3/A.6's whole point: each program's computed effect surface is exactly
// what the ruling says it is, checked against the real analyser — and none
// of the three ever touches network. These read the actual files under
// paint/, not copies, so the test guards what ships.
//
// All three now `use draw` (and math/bloom, math/snake) — a file-backed
// module graph, resolved the same way paint.html resolves it: through
// runProgramGraph/analyseProgramGraph/stepGraph with a BrowserModuleLoader,
// `fetch` stubbed to read straight off disk rather than stubbing out the
// module-loading machinery itself. A fresh loader per test (or per ticking
// sequence) mirrors "one loader per run" — paint.html's own rule.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { runProgramGraph, analyseProgramGraph } from "../browser_main.mjs";
import { stepGraph } from "../paint/loop.mjs";
import { BrowserModuleLoader } from "../module_loader_browser.mjs";

const PAINT_DIR = fileURLToPath(new URL("../../paint/", import.meta.url));

function readExample(name) {
  return fs.readFileSync(`${PAINT_DIR}${name}.planes`, "utf-8");
}

function baseFor(name) {
  return pathToFileURL(`${PAINT_DIR}${name}.planes`).href;
}

// A `fetch` stub resolving straight off disk — the same relative-to-file
// resolution BrowserModuleLoader always does, just answered from the
// filesystem instead of a network stack, so these tests exercise the real
// browser-facing entry points paint.html calls.
function installFsFetch() {
  const real = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const p = fileURLToPath(url);
    if (!fs.existsSync(p)) return { ok: false, text: async () => "" };
    return { ok: true, text: async () => fs.readFileSync(p, "utf-8") };
  };
  return () => {
    if (real) globalThis.fetch = real;
    else delete globalThis.fetch;
  };
}

for (const name of ["turtle", "bloom", "snake"]) {
  test(`${name}.planes contains no \`foreign\` declaration`, () => {
    const src = readExample(name);
    assert.doesNotMatch(src, /\bforeign\b\s+\S+\s+from\s+"/);
  });

  test(`${name}.planes emits no raw "draw " string of its own`, () => {
    // The drawing library is what emits "draw ..." lines now; a program
    // written against it never assembles one by hand (specification §11).
    const src = readExample(name);
    assert.doesNotMatch(src, /show\s+"draw\b/);
  });

  test(`${name}.planes's surface never touches network`, async () => {
    const restore = installFsFetch();
    try {
      const { surface, error } = await analyseProgramGraph(readExample(name), { base: baseFor(name) });
      assert.equal(error, null);
      assert.equal(surface.touches("network"), false);
    } finally {
      restore();
    }
  });
}

test("turtle.planes's surface is console only", async () => {
  const restore = installFsFetch();
  try {
    const { surface, error } = await analyseProgramGraph(readExample("turtle"), { base: baseFor("turtle") });
    assert.equal(error, null);
    assert.equal(surface.touches("console"), true);
    assert.equal(surface.touches("file"), false);
    assert.equal(surface.touches("ambient"), false);
  } finally {
    restore();
  }
});

test("turtle.planes is static: it runs the same with no prelude at all", async () => {
  const restore = installFsFetch();
  try {
    const r = await runProgramGraph(readExample("turtle"), { base: baseFor("turtle") });
    assert.equal(r.error, null);
    assert.equal(r.output[0], "draw clear");
    assert.ok(r.output.length > 10);
  } finally {
    restore();
  }
});

test("bloom.planes's surface is console only", async () => {
  const restore = installFsFetch();
  try {
    const { surface, error } = await analyseProgramGraph(readExample("bloom"), { base: baseFor("bloom") });
    assert.equal(error, null);
    assert.equal(surface.touches("console"), true);
    assert.equal(surface.touches("file"), false);
    assert.equal(surface.touches("ambient"), false);
  } finally {
    restore();
  }
});

test("bloom.planes runs across many ticks with no state and no error", async () => {
  const restore = installFsFetch();
  try {
    const src = readExample("bloom");
    const loader = new BrowserModuleLoader({ base: baseFor("bloom") });
    for (const tick of [0, 1, 50, 5000]) {
      const r = await stepGraph(src, { tick, keys: [], pointer: { x: 0, y: 0, down: false }, state: null }, { loader });
      assert.equal(r.error, null);
      assert.ok(r.lines.includes("draw clear"));
    }
  } finally {
    restore();
  }
});

test("snake.planes's surface is exactly console and file:write state.json", async () => {
  const restore = installFsFetch();
  try {
    const { surface, error } = await analyseProgramGraph(readExample("snake"), { base: baseFor("snake") });
    assert.equal(error, null);
    assert.equal(surface.touches("console"), true);
    assert.equal(surface.touches("file"), true);
    assert.equal(surface.touches("ambient"), false);
    assert.deepEqual(surface.targets("write"), ["state.json"]);
  } finally {
    restore();
  }
});

test("snake.planes's first tick (nothing state) initialises a live game", async () => {
  const restore = installFsFetch();
  try {
    const src = readExample("snake");
    const loader = new BrowserModuleLoader({ base: baseFor("snake") });
    const r = await stepGraph(src, { tick: 0, keys: [], pointer: { x: 0, y: 0, down: false }, state: null }, { loader });
    assert.equal(r.error, null);
    assert.equal(r.state.alive, true);
    assert.equal(r.state.score, 0);
  } finally {
    restore();
  }
});

test("snake.planes grows and scores when it reaches the apple", async () => {
  const restore = installFsFetch();
  try {
    const src = readExample("snake");
    const loader = new BrowserModuleLoader({ base: baseFor("snake") });
    let state = null;
    const keySeq = [[], ...Array(6).fill(["ArrowRight"]), ...Array(5).fill(["ArrowUp"])];
    for (let tick = 0; tick < keySeq.length; tick++) {
      const r = await stepGraph(src, { tick, keys: keySeq[tick], pointer: { x: 0, y: 0, down: false }, state }, { loader });
      assert.equal(r.error, null);
      state = r.state;
    }
    assert.equal(state.score, 1);
    assert.equal(state.body.length, 3);
  } finally {
    restore();
  }
});

test("snake.planes ends the game on a wall collision and then freezes", async () => {
  const restore = installFsFetch();
  try {
    const src = readExample("snake");
    const loader = new BrowserModuleLoader({ base: baseFor("snake") });
    let state = null;
    for (let tick = 0; tick < 30; tick++) {
      const r = await stepGraph(src, { tick, keys: ["ArrowLeft"], pointer: { x: 0, y: 0, down: false }, state }, { loader });
      assert.equal(r.error, null);
      state = r.state;
      if (!state.alive) break;
    }
    assert.equal(state.alive, false);
    const before = JSON.stringify(state);
    const r2 = await stepGraph(
      src,
      { tick: 999, keys: ["ArrowRight"], pointer: { x: 0, y: 0, down: false }, state },
      { loader },
    );
    assert.equal(r2.error, null);
    assert.equal(JSON.stringify(r2.state), before, "a dead game stays frozen");
    assert.ok(r2.lines.some((l) => l.includes("GAME OVER")));
  } finally {
    restore();
  }
});

test("one loader issues exactly one fetch per module across many ticks", async () => {
  const restore = installFsFetch();
  try {
    const realFetch = globalThis.fetch;
    let fetches = 0;
    globalThis.fetch = async (...args) => {
      fetches += 1;
      return realFetch(...args);
    };
    const src = readExample("bloom");
    const loader = new BrowserModuleLoader({ base: baseFor("bloom") });
    for (let tick = 0; tick < 10; tick++) {
      const r = await stepGraph(src, { tick, keys: [], pointer: { x: 0, y: 0, down: false }, state: null }, { loader });
      assert.equal(r.error, null);
    }
    // bloom.planes uses draw and math — two file-backed modules, so two
    // fetches for the whole run, however many ticks.
    assert.equal(fetches, 2);
  } finally {
    restore();
  }
});
