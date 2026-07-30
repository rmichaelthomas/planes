// js/test/defs.test.mjs — the SVG sink's <defs> collection (planes-drawing-
// protocol-v2.md §4, normative), headless.
//
// A resource collection, content-keyed: two identical gradients (or shadows,
// or clip regions) emit one <defs> entry and every reference just points at
// it. It survives `wipe()` (background/clear) — a def is a resource, not a
// mark — and document() emits it immediately after the opening <svg> tag,
// before the background rect, only when non-empty.
//
// Phase 1 shipped the infrastructure generic (defRef, kind-scoped id
// counters); these tests exercise it through `gradient`, the first and
// simplest of its three consumers (shadow and clip get their own dedicated
// coverage in shadow_parity.test.mjs and js/test/paint_conformance.test.mjs's
// clip/unclip cases).

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { toSvg } from "../paint/svg.mjs";
import { runProgramGraph } from "../browser_main.mjs";
import { stepGraph } from "../paint/loop.mjs";
import { BrowserModuleLoader } from "../module_loader_browser.mjs";

const DIMENSIONS = { width: 200, height: 160, background: "#ffffff" };

const GRADIENT = "draw gradient linear 0 0 100 0  0.9 0.05 90 1  0.4 0.1 260 1";

// ---- dedup and placement -------------------------------------------------

test("a stream with two identical gradients produces one def", () => {
  const lines = ["draw protocol 2", GRADIENT, "draw rect 0 0 10 10 0", GRADIENT, "draw circle 5 5 2"];
  const { svg, errors } = toSvg(lines, DIMENSIONS);
  assert.deepEqual(errors, []);
  assert.equal((svg.match(/<linearGradient/g) || []).length, 1);
  assert.equal((svg.match(/id="p-gradient-1"/g) || []).length, 1, "one definition");
  assert.equal((svg.match(/url\(#p-gradient-1\)/g) || []).length, 2, "two references");
});

test("<defs> is emitted immediately after the opening <svg> tag, before the background rect", () => {
  const lines = ["draw protocol 2", GRADIENT, "draw rect 0 0 10 10 0"];
  const { svg } = toSvg(lines, DIMENSIONS);
  const svgOpenEnd = svg.indexOf(">") + 1;
  const defsStart = svg.indexOf("<defs>");
  const bgRectStart = svg.indexOf("<rect x=\"0\" y=\"0\" width=\"200\" height=\"160\"");
  assert.ok(defsStart === svgOpenEnd, "defs starts right after <svg ...>");
  assert.ok(defsStart < bgRectStart, "defs comes before the background rect");
});

test("document() with no defs at all is byte-identical to a plain rect stream", () => {
  const withoutGradient = toSvg(["draw rect 0 0 10 10 0"], DIMENSIONS).svg;
  assert.doesNotMatch(withoutGradient, /<defs>/);
  // Same document a plain rect always produced, unaffected by defs ever
  // existing as a concept.
  assert.match(withoutGradient, /^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" width="200" height="160" viewBox="0 0 200 160">\n<rect/);
});

// ---- survives wipe() (background / clear) --------------------------------

test("a clear after a gradient keeps the def", () => {
  const lines = ["draw protocol 2", GRADIENT, "draw rect 0 0 10 10 0", "draw clear", "draw circle 5 5 2"];
  const { svg, errors } = toSvg(lines, DIMENSIONS);
  assert.deepEqual(errors, []);
  // The rect drawn before clear is gone (clear discards marks)...
  assert.doesNotMatch(svg, /<rect x="0" y="0" width="10"/);
  // ...but the gradient definition survives, since it is a resource, not a
  // mark, and nothing after the clear needs to re-declare it.
  assert.match(svg, /<linearGradient id="p-gradient-1"/);
  assert.equal((svg.match(/<linearGradient/g) || []).length, 1);
});

test("a background after a gradient also keeps the def", () => {
  const lines = ["draw protocol 2", GRADIENT, "draw rect 0 0 10 10 0", "draw background 0.5 0 0", "draw circle 5 5 2"];
  const { svg, errors } = toSvg(lines, DIMENSIONS);
  assert.deepEqual(errors, []);
  assert.match(svg, /<linearGradient id="p-gradient-1"/);
});

test("a def created, then the stream cleared, then the SAME gradient used again still dedupes to the original id", () => {
  const lines = ["draw protocol 2", GRADIENT, "draw rect 0 0 10 10 0", "draw clear", GRADIENT, "draw circle 5 5 2"];
  const { svg, errors } = toSvg(lines, DIMENSIONS);
  assert.deepEqual(errors, []);
  assert.equal((svg.match(/<linearGradient/g) || []).length, 1, "still one def, not a second");
  assert.match(svg, /url\(#p-gradient-1\)/);
});

// ---- id scheme ------------------------------------------------------------

test("def ids are p-{kind}-{n}, n assigned in first-emission order within that kind", () => {
  const a = "draw gradient linear 0 0 10 0  0.9 0.05 90 1  0.4 0.1 260 1";
  const b = "draw gradient linear 0 0 20 0  0.9 0.05 90 1  0.4 0.1 261 1";
  const lines = ["draw protocol 2", a, "draw rect 0 0 1 1 0", b, "draw rect 1 1 1 1 0"];
  const { svg, errors } = toSvg(lines, DIMENSIONS);
  assert.deepEqual(errors, []);
  assert.match(svg, /id="p-gradient-1"/);
  assert.match(svg, /id="p-gradient-2"/);
});

// ---- reset() clears defs at the start of a fresh stream ------------------

test("a fresh toSvg() call starts with no carried-over defs from a previous one", () => {
  const first = toSvg(["draw protocol 2", GRADIENT, "draw rect 0 0 1 1 0"], DIMENSIONS);
  assert.match(first.svg, /id="p-gradient-1"/);
  const second = toSvg(["draw rect 0 0 1 1 0"], DIMENSIONS);
  assert.doesNotMatch(second.svg, /<defs>/, "a new toSvg() call is a fresh sink, not a continuation");
});

// ---- every program in paint/: no defs, no change ------------------------
//
// None of turtle/bloom/snake ever uses a v2 verb, so their documents must be
// byte-identical whether or not the defs mechanism exists at all — this is
// v1 invariance (v2 §12, invariant 1) restated at the <defs> layer
// specifically.

const PAINT_DIR = fileURLToPath(new URL("../../paint/", import.meta.url));
const readExample = (name) => fs.readFileSync(`${PAINT_DIR}${name}.planes`, "utf-8");
const baseFor = (name) => pathToFileURL(`${PAINT_DIR}${name}.planes`).href;

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
  test(`${name}.planes's document has no <defs> at all — no v2 verb, no resources`, async () => {
    const restore = installFsFetch();
    try {
      let lines;
      if (name === "turtle") {
        const r = await runProgramGraph(readExample("turtle"), { base: baseFor("turtle") });
        assert.equal(r.error, null);
        lines = r.output;
      } else {
        const loader = new BrowserModuleLoader({ base: baseFor(name) });
        const r = await stepGraph(
          readExample(name),
          { tick: 13, keys: ["ArrowLeft"], pointer: { x: 0, y: 0, down: false }, state: null },
          { loader },
        );
        assert.equal(r.error, null);
        lines = r.lines;
      }
      const { svg, errors } = toSvg(lines, { width: 480, height: 360, background: "#ffffff" });
      assert.deepEqual(errors, []);
      assert.doesNotMatch(svg, /<defs>/, `${name} draws no v2 verb, so it must carry no <defs>`);
    } finally {
      restore();
    }
  });
}
