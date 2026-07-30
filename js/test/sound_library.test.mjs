// js/test/sound_library.test.mjs — paint/sound.planes IS the verb table,
// written twice (planes-sound-protocol-v1.md §10).
//
// The correspondence is checked mechanically, against the live VERBS export
// rather than a second hardcoded list — exactly the way
// js/test/protocol_v2.test.mjs checks paint/draw.planes against the drawing
// table. A verb added to one and not the other fails here.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { VERBS } from "../sound/protocol.mjs";
import { schedule } from "../sound/stream.mjs";
import { runProgramGraph } from "../browser_main.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const SOUND_PLANES = path.join(REPO, "paint", "sound.planes");

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

test("sound.planes's helper set is exactly VERBS — one per verb, protocol excluded", () => {
  const src = fs.readFileSync(SOUND_PLANES, "utf-8");
  const helpers = [...src.matchAll(/^to ([\w-]+)/gm)].map((m) => m[1]);
  assert.deepEqual(new Set(helpers), new Set(VERBS));
  assert.ok(!helpers.includes("protocol"));
});

test("no helper shadows a drawing helper — a program may import both libraries", () => {
  const soundHelpers = [...fs.readFileSync(SOUND_PLANES, "utf-8").matchAll(/^to ([\w-]+)/gm)].map((m) => m[1]);
  const drawHelpers = [
    ...fs.readFileSync(path.join(REPO, "paint", "draw.planes"), "utf-8").matchAll(/^to ([\w-]+)/gm),
  ].map((m) => m[1]);
  const mathHelpers = [
    ...fs.readFileSync(path.join(REPO, "paint", "math.planes"), "utf-8").matchAll(/^to ([\w-]+)/gm),
  ].map((m) => m[1]);
  const clash = soundHelpers.filter((h) => drawHelpers.includes(h) || mathHelpers.includes(h));
  assert.deepEqual(clash, [], `sound.planes collides with another library: ${clash.join(", ")}`);
});

test("`silence`, not `clear`, and the drawing library still has its own `clear`", () => {
  const soundSrc = fs.readFileSync(SOUND_PLANES, "utf-8");
  const drawSrc = fs.readFileSync(path.join(REPO, "paint", "draw.planes"), "utf-8");
  assert.match(soundSrc, /^to silence/m);
  assert.doesNotMatch(soundSrc, /^to clear/m);
  assert.match(drawSrc, /^to clear/m);
});

test("`lasts`, not `for` — a parameter cannot be named a reserved word", () => {
  const src = fs.readFileSync(SOUND_PLANES, "utf-8");
  assert.match(src, /^to note of numerator, denominator, octave, at, lasts:/m);
});

test("every helper emits a line the protocol's own parser accepts", async () => {
  const restore = installFsFetch();
  try {
    const program = `use sound
show "sound protocol 1"
wave of "triangle"
gain of 0.4
note of 3, 2, 1, 0.5, 0.4
silence
note of 5, 3, -1, 0, 1.25
`;
    const r = await runProgramGraph(program, {
      base: pathToFileURL(path.join(REPO, "paint", "entry.planes")).href,
    });
    assert.equal(r.error, null);
    const { errors, notes } = schedule(r.output);
    assert.deepEqual(errors, []);
    assert.equal(notes.length, 1);
    assert.equal(notes[0].numerator, 5);
    assert.equal(notes[0].denominator, 3);
    assert.equal(notes[0].octave, -1);
    assert.equal(notes[0].wave, "triangle");
    assert.equal(notes[0].gain, 0.4);
  } finally {
    restore();
  }
});

test("the garden's own stream is well-formed sound, on every frame it makes one", async () => {
  const restore = installFsFetch();
  try {
    const src = fs.readFileSync(path.join(REPO, "paint", "garden.planes"), "utf-8");
    const base = pathToFileURL(path.join(REPO, "paint", "garden.planes")).href;
    let ticksWithNotes = 0;
    let total = 0;
    for (let tick = 0; tick < 300; tick += 7) {
      const prelude = `let tick = ${tick}\nlet keys = []\nlet pointer = { x: 0, y: 0, down: false }\nlet state = nothing\nlet seed = 481027\n`;
      const r = await runProgramGraph(prelude + src, { base });
      assert.equal(r.error, null, `tick ${tick}`);
      const { errors, notes } = schedule(r.output);
      assert.deepEqual(errors, [], `tick ${tick} sound errors`);
      if (notes.length) ticksWithNotes += 1;
      total += notes.length;
      // Pentatonic just ratios only, so it cannot sound wrong.
      for (const n of notes) {
        const ratio = `${n.numerator}/${n.denominator}`;
        assert.ok(
          ["1/1", "9/8", "5/4", "3/2", "5/3", "6/5"].includes(ratio),
          `tick ${tick} played ${ratio}, which is not in the garden's scale`,
        );
      }
    }
    assert.ok(ticksWithNotes > 0, "the garden sings at least sometimes");
    assert.ok(ticksWithNotes < 43, "and is sparse — not on every frame");
    assert.ok(total > 0);
  } finally {
    restore();
  }
});

test("the same tick twice gives the identical schedule — the notes are pure too", async () => {
  const restore = installFsFetch();
  try {
    const src = fs.readFileSync(path.join(REPO, "paint", "garden.planes"), "utf-8");
    const base = pathToFileURL(path.join(REPO, "paint", "garden.planes")).href;
    const at = async (tick) => {
      const prelude = `let tick = ${tick}\nlet keys = []\nlet pointer = { x: 0, y: 0, down: false }\nlet state = nothing\nlet seed = 481027\n`;
      const r = await runProgramGraph(prelude + src, { base });
      return JSON.stringify(schedule(r.output).notes);
    };
    const first = await at(25);
    await at(5);
    const again = await at(25);
    assert.equal(first, again);
  } finally {
    restore();
  }
});
