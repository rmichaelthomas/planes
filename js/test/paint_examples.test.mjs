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
import { VERBS } from "../paint/protocol.mjs";
import { paint } from "../paint/painter.mjs";

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

// A no-op 2D context: `paint` is a pure function of what it is handed, so a
// recording-nothing stub is enough to collect the errors a stream provokes.
function silentCtx() {
  let transform = "identity";
  return {
    strokeStyle: null, fillStyle: null, lineWidth: null, lineCap: null,
    lineJoin: null, font: null, textAlign: null,
    beginPath() {}, moveTo() {}, lineTo() {}, arc() {}, ellipse() {}, rect() {},
    closePath() {}, bezierCurveTo() {}, stroke() {}, fill() {}, fillRect() {},
    fillText() {}, translate() {}, rotate() {}, scale() {},
    getTransform() { return transform; },
    setTransform(t) { transform = t; },
    resetTransform() { transform = "identity"; },
    save() {}, restore() {}, clip() {}, drawImage() {}, clearRect() {},
    setLineDash() {},
    createLinearGradient() { return { addColorStop() {} }; },
    createRadialGradient() { return { addColorStop() {} }; },
  };
}
const DIMENSIONS = { width: 480, height: 360, background: "#ffffff" };

// An offscreen-canvas factory for the shadow single-cast path (v2 §6.1):
// Node has neither OffscreenCanvas nor document.createElement, so a mark
// with both fill and stroke visible under an active `shadow` (garden's bees
// and fireflies) needs one injected, the same way js/test/shadow_parity.test.mjs
// does for its own dedicated coverage.
function offscreenCanvasFactory() {
  const ctx = silentCtx();
  return { width: 0, height: 0, getContext: () => ctx };
}

// Every `draw`-prefixed line the corpus emits, over a run of each program
// long enough to reach the frames that are not the first one. snake is driven
// into a wall on purpose: `align` is only ever set on the game-over frame,
// and a coverage test that never dies would report it missing. garden is a
// pure function of tick alone (v2 §11) and is sampled across a full day
// cycle so every v2 verb — day-only (`gradient`, `alpha`, `dash`, `clip`,
// `unclip`), and night-only (`blend`, and `shadow` on more than one mark) —
// is reached by at least one sampled tick.
async function collectCorpusStream() {
  const verbs = new Set();
  const errors = [];
  const record = (label, lines) => {
    for (const line of lines) {
      const m = /^\s*draw\s+(\S+)/.exec(line);
      if (m) verbs.add(m[1]);
    }
    const dims = { ...DIMENSIONS, offscreenCanvas: offscreenCanvasFactory };
    for (const e of paint(silentCtx(), lines, dims).errors) {
      errors.push(`${label}: ${e.tag}: ${e.message}`);
    }
  };
  const ctx = (tick, keys, state) => ({ tick, keys, pointer: { x: 0, y: 0, down: false }, state });

  const turtle = await runProgramGraph(readExample("turtle"), { base: baseFor("turtle") });
  assert.equal(turtle.error, null);
  record("turtle", turtle.output);

  const bloomSrc = readExample("bloom");
  const bloomLoader = new BrowserModuleLoader({ base: baseFor("bloom") });
  for (const tick of [0, 17, 96]) {
    const r = await stepGraph(bloomSrc, ctx(tick, [], null), { loader: bloomLoader });
    assert.equal(r.error, null);
    record(`bloom tick ${tick}`, r.lines);
  }

  const snakeSrc = readExample("snake");
  const snakeLoader = new BrowserModuleLoader({ base: baseFor("snake") });
  let state = null;
  for (let tick = 0; tick < 40; tick++) {
    const r = await stepGraph(snakeSrc, ctx(tick, ["ArrowLeft"], state), { loader: snakeLoader });
    assert.equal(r.error, null);
    state = r.state;
    record(`snake tick ${tick}`, r.lines);
    if (!state.alive) break;
  }
  assert.equal(state.alive, false, "snake must reach its game-over frame, which is the only one that sets align");

  const gardenSrc = readExample("garden");
  const gardenLoader = new BrowserModuleLoader({ base: baseFor("garden") });
  // Three days of 100 ticks (paint/garden.planes's own `day-length`), sampled
  // every 20 — enough to cross dawn and dusk twice each, so the day-only and
  // night-only branches are both walked.
  for (let tick = 0; tick < 300; tick += 20) {
    const r = await stepGraph(gardenSrc, ctx(tick, [], null), { loader: gardenLoader });
    assert.equal(r.error, null);
    record(`garden tick ${tick}`, r.lines);
  }

  return { verbs, errors };
}

// A verb that genuinely cannot be placed honestly belongs here with the
// reason it could not, rather than forced into a program that has no use for
// it. The Phase A refinement emptied this map; the garden rewrite put three
// entries back, and the three share one reason.
//
// The garden was the ONLY program that drew `clip`, `unclip` and `dash`, and
// it drew them because the corpus needed the coverage rather than because the
// picture did — a masked region and a dashed outline in a scene with neither
// a window nor a dotted line in it. The build that rewrote it forbids all
// three outright and gates on their absence, which settles the contradiction
// in the picture's favour: a corpus that keeps a verb alive by planting it
// somewhere it does not belong is measuring itself, not the protocol.
//
// The three are not untested. js/test/protocol_v2.test.mjs exercises every
// one of them directly, in both sinks, including the nesting rules and every
// refusal — what is missing is a REAL PROGRAM that reaches for them, and this
// map is the honest place to say so rather than the place to hide it.
// A MAP OF WHAT NO PICTURE WANTS, not a list of what is broken. An entry here
// is a verb both sinks implement and every unit test covers, that no program
// in the corpus reaches for — which is a fact worth keeping visible, not a
// gap to be closed by writing a program that exists to tick a box.
const COVERAGE_ALLOWLIST = new Map([
  ["clip", "no program in this corpus masks a region; the garden's masked region existed for this test and the scene rewrite removed it. A DECISION, not a wait: neither garden mockup masks anything and no picture in the corpus wants a mask"],
  ["unclip", "same as clip — it has nothing to release"],
  ["dash", "no .planes program in this corpus draws a dashed outline — but garden.html does, as a page-composed overlay stream: its selection indicator is `draw dash 7 7` + `draw rect` run through the same painter over the same context. It stays listed here because the map is of what the CORPUS draws, and the page is a consumer of the format rather than a program in it. Moving the indicator into paint/garden.planes would mean feeding the program a click index, which would break the (tick, seed) purity the PNG-hash gate exists to prove"],
  // v3 orphaned both of these, and the reason is the point rather than an
  // oversight: the garden's six `shadow 0 0 r` glows and the `alpha` set/reset
  // that gave them their opacity were both standing in for `blur`, which
  // softens a mark's own edge. Given the verb they wanted, the picture stopped
  // wanting these two. `shadow` is still a shadow and `alpha` is still a
  // dimmer; no picture here casts one or needs the other.
  ["shadow", "no program in this corpus casts a shadow. The garden's six uses were all `0 0 r` glows — never once an actual shadow — and v3's `blur` is what they were reaching for. Cast shadows were built and measured for this build and refused on the number (56-68ms of paint, the whole frame budget; benchmarks/density.md)"],
  ["alpha", "no program in this corpus dims a mark with the multiplier. The garden's only use wrapped its clouds so their SHADOWS had an opacity — §6.6 gives `shadow` no alpha of its own — and with `blur` in place of the shadow the 0.95 lives in the cloud's own fill, which is where it belongs"],
]);

test("every drawing verb is exercised somewhere in the corpus", async () => {
  const restore = installFsFetch();
  try {
    const { verbs } = await collectCorpusStream();
    const missing = VERBS.filter((v) => !verbs.has(v) && !COVERAGE_ALLOWLIST.has(v));
    assert.deepEqual(missing, [], `verbs the corpus never draws: ${missing.join(", ")}`);
  } finally {
    restore();
  }
});

test("the corpus emits no protocol error on any frame", async () => {
  const restore = installFsFetch();
  try {
    const { errors } = await collectCorpusStream();
    assert.deepEqual(errors, []);
  } finally {
    restore();
  }
});

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
