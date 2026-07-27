// js/test/paint_svg.test.mjs — the SVG renderer, on its own.
//
// What is here is what is SVG about the SVG renderer: element choice,
// attribute names, group nesting for the transform verbs, path data, text
// escaping, and the document envelope. Everything the two renderers must
// AGREE on is in paint_conformance.test.mjs instead — testing agreement here
// would test svg.mjs against itself.

import { test } from "node:test";
import assert from "node:assert/strict";
import { toSvg } from "../paint/svg.mjs";
import { FONT_FAMILY } from "../paint/stream.mjs";
import { rgbHex } from "../paint/color.mjs";

const DIMENSIONS = { width: 100, height: 80, background: "#ffffff" };

const render = (lines, dims = DIMENSIONS) => toSvg(lines, dims);

// ---- the document envelope ---------------------------------------------------

test("an empty stream is a well-formed svg carrying only the background", () => {
  const { svg, drawn, errors } = render([]);
  assert.deepEqual(errors, []);
  assert.equal(drawn, 0);
  assert.match(svg, /^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" width="100" height="80" viewBox="0 0 100 80">/);
  assert.match(svg, /<\/svg>\n$/);
  assert.match(svg, /<rect x="0" y="0" width="100" height="80" fill="#ffffff"\/>/);
});

test("the dimensions' background colour seeds the document", () => {
  const { svg } = render([], { width: 10, height: 10, background: "#123456" });
  assert.match(svg, /fill="#123456"/);
});

test("a refused version produces no document at all", () => {
  const { svg, drawn, text, errors } = render(["draw protocol 9", "draw circle 1 2 3", "prose"]);
  assert.equal(svg, "");
  assert.equal(drawn, 0);
  assert.deepEqual(text, []);
  assert.equal(errors.length, 1);
  assert.equal(errors[0].tag, "unsupported-version");
});

// ---- element choice ----------------------------------------------------------

test("each shape verb maps to its native element", () => {
  const cases = [
    ["draw line 1 2 3 4", /<line x1="1" y1="2" x2="3" y2="4"/],
    ["draw rect 1 2 3 4", /<rect x="1" y="2" width="3" height="4"/],
    ["draw circle 5 6 7", /<circle cx="5" cy="6" r="7"/],
    ["draw ellipse 5 6 7 8", /<ellipse cx="5" cy="6" rx="7" ry="8"/],
    ["draw triangle 0 0 10 0 5 10", /<polygon points="0,0 10,0 5,10"/],
  ];
  for (const [line, pattern] of cases) {
    assert.match(render([line]).svg, pattern, line);
  }
});

test("a radius stays a radius — <circle r> is not a diameter", () => {
  const { svg } = render(["draw circle 50 40 12"]);
  assert.match(svg, /r="12"/);
  assert.doesNotMatch(svg, /r="24"/);
});

// ---- presentation attributes -------------------------------------------------

test("stroke and fill become colour plus a separate opacity attribute", () => {
  const { svg } = render(["draw stroke 0.6 0.15 210 0.25", "draw fill 0.8 0.1 40 0.75", "draw circle 1 1 1"]);
  assert.match(svg, new RegExp(`fill="${rgbHex(0.8, 0.1, 40)}"`));
  assert.match(svg, /fill-opacity="0\.75"/);
  assert.match(svg, new RegExp(`stroke="${rgbHex(0.6, 0.15, 210)}"`));
  assert.match(svg, /stroke-opacity="0\.25"/);
});

test("no CSS oklch() string is ever emitted", () => {
  const { svg } = render(["draw fill 0.5 0.2 120 1", "draw stroke 0.5 0.2 300 1", "draw circle 1 1 1"]);
  assert.doesNotMatch(svg, /oklch/i);
});

test("width, cap and corner become stroke-width, -linecap and -linejoin", () => {
  const { svg } = render(["draw width 4.5", "draw cap square", "draw corner bevel", "draw rect 0 0 1 1"]);
  assert.match(svg, /stroke-width="4\.5"/);
  assert.match(svg, /stroke-linecap="square"/);
  assert.match(svg, /stroke-linejoin="bevel"/);
});

test("the reset table's values are what an unstyled element carries", () => {
  const { svg } = render(["draw rect 0 0 1 1"]);
  assert.match(svg, /fill="#000000" fill-opacity="0"/);
  assert.match(svg, /stroke="#000000" stroke-opacity="1"/);
  assert.match(svg, /stroke-width="1" stroke-linecap="butt" stroke-linejoin="miter"/);
});

// ---- transforms as nested groups ---------------------------------------------

test("push opens a group and pop closes it", () => {
  const { svg } = render(["draw push", "draw circle 1 1 1", "draw pop", "draw circle 2 2 2"]);
  const body = svg.split("\n").filter((l) => l.startsWith("<g") || l.startsWith("</g") || l.startsWith("<circle"));
  assert.deepEqual(body.map((l) => (l.startsWith("<circle") ? "circle" : l.startsWith("</g") ? "close" : "open")), [
    "open",
    "circle",
    "close",
    "circle",
  ]);
});

test("translate, rotate and scale each open a transform group", () => {
  const { svg } = render(["draw translate 5 6", "draw rotate 30", "draw scale 2 -1", "draw circle 0 0 1"]);
  assert.match(svg, /<g transform="translate\(5 6\)">/);
  assert.match(svg, /<g transform="rotate\(30\)">/);
  assert.match(svg, /<g transform="scale\(2 -1\)">/);
});

test("pop closes every transform group opened since its push", () => {
  const { svg, errors } = render([
    "draw push",
    "draw translate 5 5",
    "draw rotate 45",
    "draw circle 0 0 1",
    "draw pop",
    "draw circle 9 9 9",
  ]);
  assert.deepEqual(errors, []);
  // The second circle is outside every group the push opened.
  const lines = svg.split("\n");
  const lastCircle = lines.findIndex((l) => l.includes('cx="9"'));
  const opens = lines.slice(0, lastCircle).filter((l) => l.startsWith("<g")).length;
  const closes = lines.slice(0, lastCircle).filter((l) => l.startsWith("</g")).length;
  assert.equal(opens, closes, "every group opened before the second circle is closed before it");
});

test("groups still open at the end of the stream are closed by the document", () => {
  const { svg } = render(["draw translate 10 10", "draw circle 0 0 1"]);
  const opens = (svg.match(/<g[ >]/g) || []).length;
  const closes = (svg.match(/<\/g>/g) || []).length;
  assert.equal(opens, 1);
  assert.equal(closes, 1);
});

// ---- paths -------------------------------------------------------------------

test("a shape block becomes one path with M, L, C and Z", () => {
  const { svg, errors } = render([
    "draw shape",
    "draw vertex 10 10",
    "draw vertex 20 30",
    "draw curve 1 2 3 4 40 50",
    "draw close",
    "draw end",
  ]);
  assert.deepEqual(errors, []);
  assert.match(svg, /<path d="M 10 10 L 20 30 C 1 2 3 4 40 50 Z"/);
  assert.equal((svg.match(/<path/g) || []).length, 1, "one path element, not four");
});

test("a curve as the first point of a path moves rather than curving", () => {
  const { svg } = render(["draw shape", "draw curve 1 2 3 4 40 50", "draw end"]);
  assert.match(svg, /<path d="M 40 50"/);
});

test("a path that received no points emits no element", () => {
  const { svg, errors } = render(["draw shape", "draw end"]);
  assert.deepEqual(errors, []);
  assert.doesNotMatch(svg, /<path/);
});

// ---- text --------------------------------------------------------------------

test("label becomes text with the font family both renderers name", () => {
  const { svg } = render(["draw label 5 10 hello there"]);
  assert.match(svg, new RegExp(`font-family="${FONT_FAMILY}"`));
  assert.match(svg, /font-size="16"/);
  assert.match(svg, />hello there<\/text>/);
});

test("size and align become font-size and text-anchor", () => {
  for (const [word, anchor] of [["left", "start"], ["center", "middle"], ["right", "end"]]) {
    const { svg } = render(["draw size 22", `draw align ${word}`, "draw label 1 2 hi"]);
    assert.match(svg, /font-size="22"/);
    assert.match(svg, new RegExp(`text-anchor="${anchor}"`));
  }
});

test("text is escaped, and carries fill but never stroke", () => {
  const { svg } = render(["draw stroke 1 0 0 1", "draw width 9", "draw label 1 2 a < b & c > d"]);
  assert.match(svg, />a &lt; b &amp; c &gt; d<\/text>/);
  assert.match(svg, /<text[^>]*stroke="none"/);
});

// ---- background and clear ----------------------------------------------------

test("background replaces the document's opening rect and discards what came before", () => {
  const { svg } = render(["draw circle 1 1 1", "draw background 0.5 0 0"]);
  assert.doesNotMatch(svg, /<circle/, "the circle drawn before the background is gone, as on canvas");
  assert.match(svg, new RegExp(`<rect x="0" y="0" width="100" height="80" fill="${rgbHex(0.5, 0, 0)}"/>`));
});

test("clear discards the picture but keeps the open groups balanced", () => {
  const { svg, errors } = render([
    "draw push",
    "draw translate 4 4",
    "draw circle 1 1 1",
    "draw clear",
    "draw circle 2 2 2",
    "draw pop",
  ]);
  assert.deepEqual(errors, []);
  assert.doesNotMatch(svg, /cx="1"/);
  assert.match(svg, /cx="2"/);
  const opens = (svg.match(/<g[ >]/g) || []).length;
  const closes = (svg.match(/<\/g>/g) || []).length;
  assert.equal(opens, 2);
  assert.equal(closes, 2);
});

test("clear repaints the last background colour, not the document default", () => {
  const { svg } = render(["draw background 0.3 0.1 200", "draw circle 1 1 1", "draw clear"]);
  assert.match(svg, new RegExp(`fill="${rgbHex(0.3, 0.1, 200)}"`));
  assert.doesNotMatch(svg, /fill="#ffffff"/);
});

// ---- numbers -----------------------------------------------------------------

test("a tilde-prefixed number renders as a plain decimal", () => {
  const { svg, errors } = render(["draw circle ~66.666 10 5"]);
  assert.deepEqual(errors, []);
  assert.match(svg, /cx="66\.666"/);
});

test("no coordinate is ever emitted in exponent notation", () => {
  const { svg } = render(["draw circle 0.0000001 0.0000002 1", "draw rect -0 0 1 1"]);
  assert.doesNotMatch(svg, /e[+-]\d/);
  assert.doesNotMatch(svg, /"-0"/);
});
