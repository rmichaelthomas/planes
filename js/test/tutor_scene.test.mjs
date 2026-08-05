// js/test/tutor_scene.test.mjs — the tutor.html build's own acceptance
// checks, over paint/scene.planes and the starter program §3.5 pins.
//
// WHY THIS IS A SUITE AND NOT `scripts/verify-tutor-page.mjs`. Same rule
// js/test/garden_gate.test.mjs states at length: a build's verification
// script graduates into a suite or is deleted when the build merges
// (`test_gate.py`'s retirement rule). These are the assertions §7 of the
// build prompt asked for, written where `node --test` runs them on every
// gate rather than in a script nothing runs after merge.
//
// The numbers are the build prompt's own (§7):
//   1  every scene.planes helper emits a stream `walk` accepts, zero errors
//   2  every sky/ground phrase produces a distinct background/fill line
//   3  an unrecognised sky phrase fails, naming the fix and the phrases
//   4  every mark in the starter program is hit-testable at its own centre
//   5  the starter program's analysed surface reports console and exact
//   6  no scene.planes name collides with vocabulary.json's reserved surface

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { runProgramGraph, analyseProgramGraph } from "../browser_main.mjs";
import { BrowserModuleLoader } from "../module_loader_browser.mjs";
import { walk } from "../paint/stream.mjs";
import { markSink } from "../paint/marks.mjs";
import { hitTest, outlineOf } from "../paint/hit.mjs";
import { scan_names } from "../parser.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const PAINT = path.join(REPO, "paint");
const SCENE_BASE = pathToFileURL(PAINT + path.sep).href;
const DIMENSIONS = { width: 480, height: 360 };

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

const sceneSrc = () => fs.readFileSync(path.join(PAINT, "scene.planes"), "utf-8");

async function run(src) {
  return runProgramGraph(src, { base: SCENE_BASE });
}

const SKY_PHRASES = [
  "early morning",
  "middle of the afternoon",
  "just before dark",
  "the middle of the night",
];
const GROUND_PHRASES = ["wet grass", "dry grass", "dirt"];

const STARTER_PROGRAM = `use scene

start
sky of "just before dark"
ground of "wet grass"

moon of 240, 90
star of 100, 60
firefly of 300, 200

let spot = 90 because "the corner gets the sun after noon, so it grows tallest"
flower of 120, spot
`;

// ---- 1: every helper emits a stream `walk` accepts, zero errors ------------

test("1: every scene.planes helper emits a stream walk accepts with zero errors", async () => {
  const restore = installFsFetch();
  try {
    const programs = {
      start: 'use scene\n\nstart\n',
      sky: 'use scene\n\nstart\nsky of "early morning"\n',
      ground: 'use scene\n\nstart\nground of "wet grass"\n',
      sun: 'use scene\n\nstart\nsun of 100, 50\n',
      moon: 'use scene\n\nstart\nmoon of 100, 50\n',
      star: 'use scene\n\nstart\nstar of 100, 50\n',
      flower: 'use scene\n\nstart\nflower of 100, 50\n',
      bee: 'use scene\n\nstart\nbee of 100, 50\n',
      firefly: 'use scene\n\nstart\nfirefly of 100, 50\n',
    };
    for (const [name, src] of Object.entries(programs)) {
      const r = await run(src);
      assert.equal(r.error, null, `${name}: ${r.error && r.error.message}`);
      const { errors } = walk(r.output, markSink());
      assert.deepEqual(errors, [], `${name} emitted a protocol error`);
    }
  } finally {
    restore();
  }
});

// ---- 2: every phrase produces a distinct line -------------------------------

test("2: every sky phrase produces a distinct background line", async () => {
  const restore = installFsFetch();
  try {
    const lines = new Set();
    for (const phrase of SKY_PHRASES) {
      const r = await run(`use scene\n\nstart\nsky of "${phrase}"\n`);
      assert.equal(r.error, null, `${phrase}: ${r.error && r.error.message}`);
      const bg = r.output.find((l) => l.startsWith("draw background "));
      assert.ok(bg, `${phrase} produced no background line`);
      lines.add(bg);
    }
    assert.equal(lines.size, SKY_PHRASES.length, "two sky phrases produced the same background");
  } finally {
    restore();
  }
});

test("2: every ground phrase produces a distinct fill line", async () => {
  const restore = installFsFetch();
  try {
    const lines = new Set();
    for (const phrase of GROUND_PHRASES) {
      const r = await run(`use scene\n\nstart\nground of "${phrase}"\n`);
      assert.equal(r.error, null, `${phrase}: ${r.error && r.error.message}`);
      const fill = r.output.find((l) => l.startsWith("draw fill "));
      assert.ok(fill, `${phrase} produced no fill line`);
      lines.add(fill);
    }
    assert.equal(lines.size, GROUND_PHRASES.length, "two ground phrases produced the same fill");
  } finally {
    restore();
  }
});

// ---- 3: an unrecognised sky phrase refuses, naming the fix -----------------

test("3: an unrecognised sky phrase fails with a message naming the fix and listing the recognised phrases", async () => {
  const restore = installFsFetch();
  try {
    const r = await run('use scene\n\nstart\nsky of "a stormy tuesday"\n');
    assert.ok(r.error, "an unrecognised sky phrase must refuse, not draw a default");
    assert.equal(r.error.tag, "unknown-sky-feeling");
    for (const phrase of SKY_PHRASES) {
      assert.ok(r.error.message.includes(phrase), `message does not list "${phrase}"`);
    }
    assert.match(r.error.message, /try one of/, "message does not name the fix");
  } finally {
    restore();
  }
});

test("3: and an unrecognised ground phrase does too", async () => {
  const restore = installFsFetch();
  try {
    const r = await run('use scene\n\nstart\nground of "a muddy puddle"\n');
    assert.ok(r.error, "an unrecognised ground phrase must refuse, not draw a default");
    assert.equal(r.error.tag, "unknown-ground-feeling");
    for (const phrase of GROUND_PHRASES) {
      assert.ok(r.error.message.includes(phrase), `message does not list "${phrase}"`);
    }
    assert.match(r.error.message, /try one of/, "message does not name the fix");
  } finally {
    restore();
  }
});

// ---- 4: every mark in the starter program is hit-testable at its own centre

// A mark's own centre, as a point ON the visible shape — the centroid of
// outlineOf's own sampled points. Exact for a circle or a rect (symmetric
// sampling averages to the true centre) and the midpoint for a line, which
// is exactly what "hit-testable at its own centre" needs for every mark kind
// scene.planes actually emits.
function centreOf(mark) {
  const pts = outlineOf(mark);
  const cx = pts.reduce((s, [x]) => s + x, 0) / pts.length;
  const cy = pts.reduce((s, [, y]) => s + y, 0) / pts.length;
  return [cx, cy];
}

test("4: the starter program's marks are each hit-testable at their own centre", async () => {
  const restore = installFsFetch();
  try {
    const r = await run(STARTER_PROGRAM);
    assert.equal(r.error, null, r.error && r.error.message);
    const sink = markSink();
    const { errors } = walk(r.output, sink);
    assert.deepEqual(errors, []);
    assert.ok(sink.marks.length > 0, "the starter program drew no marks");
    for (const mark of sink.marks) {
      if (!mark.visible) continue;
      const [cx, cy] = centreOf(mark);
      const found = hitTest(sink.marks, cx, cy, { area: DIMENSIONS });
      assert.ok(found >= 0, `mark kind=${mark.kind} on line ${mark.line} is not hit-testable at its own centre`);
    }
  } finally {
    restore();
  }
});

// ---- 5: the starter program's analysed surface reports console and exact ---

test("5: the starter program's static surface reports console and exact, without running it", async () => {
  const restore = installFsFetch();
  try {
    const { surface, error } = await analyseProgramGraph(STARTER_PROGRAM, { base: SCENE_BASE });
    assert.equal(error, null);
    assert.ok(!surface.isPure(), "a program that draws is not pure");
    assert.deepEqual(surface.boundaries(), ["console"]);
    assert.ok(!surface.producesApproximate(), "the starter program never reaches sine or an irrational root");
  } finally {
    restore();
  }
});

// ---- 6: no scene.planes name collides with the 45-word reserved surface ----

test("6: no name defined in scene.planes appears in vocabulary.json's keywords or builtins", () => {
  const vocab = JSON.parse(fs.readFileSync(path.join(REPO, "grammar", "vocabulary.json"), "utf-8"));
  const reserved = new Set([
    ...vocab.keywords.map((k) => k.word),
    ...vocab.builtins.map((b) => b.name),
  ]);
  assert.equal(reserved.size, 45, `expected 45 reserved words, computed ${reserved.size}`);
  const defined = scan_names(sceneSrc());
  const collisions = [...defined.keys()].filter((name) => reserved.has(name));
  assert.deepEqual(collisions, [], `scene.planes defines a reserved word: ${collisions.join(", ")}`);
  assert.ok(defined.size >= 9, `expected at least 9 names defined in scene.planes, found ${defined.size}`);
});
