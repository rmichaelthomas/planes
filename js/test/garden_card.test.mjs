// js/test/garden_card.test.mjs — the why card's two restatements, checked.
//
// garden.html answers a click on a flower with that flower's note. It has to
// COMPUTE that note, because `paint/garden.planes` only emits one when a bee
// lands — 25 ticks out of the scrubber's 300 — and a page that could only
// answer on those ticks is the silent page this suite exists because of.
//
// Computing it means restating the program's rule in the page:
//
//     let k = whole of (g * 5)
//     note of (pentatonic-n of k), (pentatonic-d of k), 1, 0, 1.6
//     pentatonic-n / pentatonic-d
//
// all inside `sing-bee`. The line number is DERIVED from the source below,
// not written down: editing a comment in garden.planes moves every line
// after it, and a suite pinned to 687 would start silently checking nothing
// the moment someone did.
//
// A restatement nobody checks is a page that will eventually lie about what
// the program does. So this reads the table OUT OF THE PAGE — there is no
// second copy here to drift from it — runs the real program across the whole
// span, and asserts that on every tick where a bee actually played, the
// page's rule reproduces the ratio and the octave the program emitted.
//
// If the scale in garden.planes ever changes, this goes red before anyone
// hears a wrong note.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { stepGraph } from "../paint/loop.mjs";
import { BrowserModuleLoader } from "../module_loader_browser.mjs";
import { markSink } from "../paint/marks.mjs";
import { walk } from "../paint/stream.mjs";
import { schedule } from "../sound/stream.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const PAINT = path.join(REPO, "paint");
const SEED = 481027;
const SPAN = 300;
// The bee's note line, found rather than remembered. The dawn, dusk and
// night notes are literals and are not this one.
function noteLineIn(src) {
  const lines = src.split("\n");
  const i = lines.findIndex((l) => /^\s*note of \(pentatonic-n of k\)/.test(l));
  assert.ok(i >= 0, "garden.planes no longer plays a note from the pentatonic table");
  return i + 1; // the interpreter counts from 1
}

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

const gardenSrc = () => fs.readFileSync(path.join(PAINT, "garden.planes"), "utf-8");
const pageSrc = () => fs.readFileSync(path.join(REPO, "garden.html"), "utf-8");

// THE PAGE'S OWN TABLE, not a copy of it.
function pageRule() {
  const html = pageSrc();
  const table = /const PENTATONIC = (\[\[[\d, [\]]+\]\]);/.exec(html);
  const octave = /const FLOWER_OCTAVE = (-?\d+);/.exec(html);
  assert.ok(table, "garden.html no longer declares PENTATONIC where this suite reads it");
  assert.ok(octave, "garden.html no longer declares FLOWER_OCTAVE where this suite reads it");
  const ratios = JSON.parse(table[1]);

  // The ROUNDING MODE is part of the rule, so it is read here too rather
  // than assumed. `whole of` is round-half-away-from-zero
  // (js/planes_num.mjs's roundTo), NOT truncation — the first version of
  // this suite and the first version of the page both got that wrong, and
  // this is where it was caught: g 0.708994 gives whole of 3.54 = 4, so the
  // flower plays 5/3 where truncation would have said 3/2.
  assert.match(html, /Math\.round\(g \* 5\)/,
    "garden.html must round to pick the interval — `whole of` rounds, it does not truncate");

  return {
    ratios,
    octave: Number(octave[1]),
    noteFor(g) {
      const k = Math.max(0, Math.min(ratios.length - 1, Math.round(g * 5)));
      return { numerator: ratios[k][0], denominator: ratios[k][1], octave: Number(octave[1]) };
    },
  };
}

// Every `name` node called `g` in a derivation chain, by value text — the
// same walk garden.html does to find the flower a note belongs to.
function gValues(node, found = new Set(), seen = new Set()) {
  if (!node || seen.has(node)) return found;
  seen.add(node);
  if (node.kind === "name" && node.label === "g") {
    const v = node.value;
    found.add(v && typeof v === "object" && typeof v.text === "function" ? v.text() : String(v));
  }
  for (const input of Array.isArray(node.inputs) ? node.inputs : []) {
    gValues(input, found, seen);
  }
  return found;
}

test("the page's flower-note rule reproduces every note the program actually plays", async () => {
  const restore = installFsFetch();
  try {
    const loader = new BrowserModuleLoader({ base: pathToFileURL(path.join(PAINT, "garden.planes")).href });
    const rule = pageRule();
    const noteLine = noteLineIn(gardenSrc());
    assert.deepEqual(rule.ratios, [[1, 1], [9, 8], [5, 4], [3, 2], [5, 3]],
      "the page's table is no longer the program's five just ratios");

    let checked = 0;
    for (let tick = 0; tick < SPAN; tick++) {
      const r = await stepGraph(
        gardenSrc(),
        { tick, keys: [], pointer: { x: 0, y: 0, down: false }, state: null, seed: SEED },
        { loader },
      );
      assert.equal(r.error, null, `tick ${tick}: ${r.error && r.error.message}`);
      const trace = r.trace ?? [];
      const notes = schedule(r.lines).notes;
      const indices = [];
      r.lines.forEach((l, i) => {
        if (l.startsWith("sound note ")) indices.push(i);
      });
      for (let i = 0; i < indices.length && i < notes.length; i++) {
        const entry = trace[indices[i]];
        if (!entry || entry[1] !== noteLine) continue; // dawn/dusk/night are literals
        const gs = [...gValues(entry[0])];
        assert.equal(gs.length, 1, `tick ${tick}: expected one g in the bee's chain, got ${gs.length}`);
        const predicted = rule.noteFor(Number(gs[0]));
        assert.deepEqual(
          { numerator: notes[i].numerator, denominator: notes[i].denominator, octave: notes[i].octave },
          predicted,
          `tick ${tick}: the page would play ${predicted.numerator}/${predicted.denominator} ` +
            `at octave ${predicted.octave}, the program played ` +
            `${notes[i].numerator}/${notes[i].denominator} at octave ${notes[i].octave} for g ${gs[0]}`,
        );
        checked += 1;
      }
    }
    // A pass with nothing checked is the failure mode this guards against.
    assert.ok(checked >= 20, `only ${checked} bee notes found across ${SPAN} ticks — nothing was proven`);
  } finally {
    restore();
  }
});

test("only the six named subjects are clickable, and the leaves and sky are not", () => {
  const html = pageSrc();
  const block = /const SUBJECTS = new Map\(\[(.*?)\]\);/s.exec(html);
  assert.ok(block, "garden.html no longer declares the clickable subjects");
  const defs = [...block[1].matchAll(/\["([a-z-]+)",\s*"([a-z-]+)"\]/g)].map((m) => m[1]);

  // Every definition named here must exist in the program, or the page is
  // gating clicks on a function that was renamed out from under it.
  const src = gardenSrc();
  for (const def of defs) {
    assert.match(src, new RegExp(`^to ${def}\\b`, "m"), `garden.planes has no \`to ${def}\``);
  }

  // And the things a click must NOT answer stay out.
  for (const excluded of ["plant-leaf", "draw-grass", "draw-hill", "draw-ground",
                          "sky-top", "sky-middle", "sky-low", "draw-cloud", "draw-star"]) {
    assert.ok(!defs.includes(excluded),
      `${excluded} became clickable — the sky, the ground and the leaves are not subjects`);
  }
  assert.ok(defs.includes("plant-petal") && defs.includes("draw-plant"), "the flower must be clickable");
  assert.ok(defs.includes("tree-branch"), "the tree must be clickable");
});

test("a click marks the source line without repainting outlines onto the picture", () => {
  const html = pageSrc();
  // The two paths are separate functions, and the click path takes the one
  // that leaves `litLine` at -1 so `drawHighlights` has nothing to draw.
  assert.match(html, /function markSourceLine\(sourceLine\) \{\s*litLine = -1;/);
  assert.match(html, /function highlightSourceLine\(sourceLine\) \{\s*litLine = sourceLine;/);
  assert.match(html, /markSourceLine\(sourceLine\);/, "the card marks the line the quiet way");
  // Hover still gets the outlines — that is the map read backwards.
  assert.match(html, /if \(line !== litLine\) highlightSourceLine\(line\);/);
  // And nothing scrolls the document out from under the reader.
  assert.ok(!/\.scrollIntoView\(/.test(html), "a scrollIntoView call jumps the whole page");
});

test("the card can always be dismissed", () => {
  const html = pageSrc();
  assert.match(html, /class="close"/, "there is a close control");
  assert.match(html, /cardEl\.querySelector\("\.close"\)\.addEventListener\("click", hideCard\)/);
  assert.match(html, /event\.key === "Escape"\) hideCard\(\)/, "Escape closes it");
  assert.match(html, /if \(found < 0\) \{\s*hideCard\(\);/, "a click on nothing closes it");
  assert.match(html, /if \(canvas\.contains\(event\.target\) \|\| cardEl\.contains\(event\.target\)\) return;/,
    "a click off the picture closes it");
  // pointer-events:none would make every one of those unreachable.
  assert.ok(!/#garden-card\{[^}]*pointer-events:none/.test(html),
    "the card cannot be click-through and dismissable at the same time");
});
