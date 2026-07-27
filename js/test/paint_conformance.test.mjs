// js/test/paint_conformance.test.mjs — the two renderers, held against each
// other.
//
// One program, two renderers. Everything that is protocol rather than medium
// lives in js/paint/stream.mjs and is walked once, so agreement on the
// version declaration, the path lifecycle, transform balance, the error tags
// and their order is structural rather than coincidental. These tests exist
// to KEEP it structural: each one fails the moment someone re-implements a
// stream rule inside a renderer.
//
// The all-verbs fixture is generated from `VERBS` in protocol.mjs, not
// hand-listed, so a twenty-seventh verb cannot be silently skipped — it fails
// this file before it fails anything else.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { VERBS } from "../paint/protocol.mjs";
import { paint } from "../paint/painter.mjs";
import { toSvg } from "../paint/svg.mjs";
import { oklchToRgb } from "../paint/color.mjs";
import { runProgramGraph } from "../browser_main.mjs";
import { stepGraph } from "../paint/loop.mjs";
import { BrowserModuleLoader } from "../module_loader_browser.mjs";

const DIMENSIONS = { width: 200, height: 160, background: "#ffffff" };

function fakeCtx() {
  const calls = [];
  const record = (name) => (...args) => calls.push([name, ...args]);
  let transform = "identity";
  return {
    calls,
    strokeStyle: null, fillStyle: null, lineWidth: null, lineCap: null,
    lineJoin: null, font: null, textAlign: null,
    beginPath: record("beginPath"), moveTo: record("moveTo"), lineTo: record("lineTo"),
    arc: record("arc"), ellipse: record("ellipse"), rect: record("rect"),
    closePath: record("closePath"), bezierCurveTo: record("bezierCurveTo"),
    stroke: record("stroke"), fill: record("fill"), fillRect: record("fillRect"),
    fillText: record("fillText"), translate: record("translate"),
    rotate: record("rotate"), scale: record("scale"),
    getTransform() { return transform; },
    setTransform(t) { transform = t; },
    resetTransform() { transform = "identity"; },
  };
}

const bothRender = (lines) => ({
  canvas: paint(fakeCtx(), lines, DIMENSIONS),
  svg: toSvg(lines, DIMENSIONS),
});

// ---- the all-verbs fixture, generated from VERBS ------------------------------
//
// One sample line per verb. The map's keys are checked against VERBS below,
// so this cannot fall behind the protocol: adding a verb and not adding a
// sample fails, and so does naming a sample for a verb that does not exist.
const SAMPLE = {
  stroke: "draw stroke 0.55 0.14 210 0.8",
  fill: "draw fill 0.8 0.09 40 0.35",
  width: "draw width 2.5",
  cap: "draw cap round",
  corner: "draw corner bevel",
  background: "draw background 0.94 0.02 95",
  clear: "draw clear",
  size: "draw size 18",
  align: "draw align center",
  line: "draw line 10 10 60 40",
  rect: "draw rect 20 20 40 30",
  circle: "draw circle 90 60 18",
  ellipse: "draw ellipse 140 60 20 12",
  arc: "draw arc 100 100 30 300 40",
  triangle: "draw triangle 10 140 40 140 25 110",
  push: "draw push",
  translate: "draw translate 20 15",
  rotate: "draw rotate 25",
  scale: "draw scale 1.5 1.5",
  shape: "draw shape",
  vertex: "draw vertex 0 0",
  curve: "draw curve 10 -20 30 -20 40 0",
  close: "draw close",
  end: "draw end",
  pop: "draw pop",
  label: "draw label 8 18 score: 42",
};

// A valid stream order: the path block is opened before it is drawn into and
// closed before its enclosing push is popped. Asserted to be a permutation of
// VERBS, so it stays complete as the table changes.
const ORDER = [
  "stroke", "fill", "width", "cap", "corner",
  "background", "clear", "size", "align",
  "line", "rect", "circle", "ellipse", "arc", "triangle",
  "push", "translate", "rotate", "scale",
  "shape", "vertex", "curve", "close", "end",
  "pop", "label",
];

const ALL_VERBS_STREAM = ["draw protocol 1", ...ORDER.map((v) => SAMPLE[v])];

test("the all-verbs fixture covers exactly the verb table, no more and no less", () => {
  assert.deepEqual(Object.keys(SAMPLE).slice().sort(), VERBS.slice().sort());
  assert.deepEqual(ORDER.slice().sort(), VERBS.slice().sort());
});

test("both renderers walk the all-verbs stream with no error", () => {
  const { canvas, svg } = bothRender(ALL_VERBS_STREAM);
  assert.deepEqual(canvas.errors, []);
  assert.deepEqual(svg.errors, []);
});

test("both renderers agree on drawn count, prose and errors for the all-verbs stream", () => {
  const { canvas, svg } = bothRender(ALL_VERBS_STREAM);
  assert.equal(canvas.drawn, svg.drawn);
  assert.deepEqual(canvas.text, svg.text);
  assert.deepEqual(canvas.errors, svg.errors);
  assert.equal(canvas.drawn, ORDER.length, "protocol itself is not a drawing command");
});

test("every verb in the fixture leaves a mark in the SVG document", () => {
  // Not every verb emits an element — the state verbs change how the next one
  // is written — so this checks the two kinds separately rather than pretending
  // they are one.
  const { svg } = toSvg(ALL_VERBS_STREAM, DIMENSIONS);
  for (const pattern of [/<line /, /<rect /, /<circle /, /<ellipse /, /<polygon /, /<path /, /<text /, /<g/]) {
    assert.match(svg, pattern, String(pattern));
  }
  assert.match(svg, /stroke-linecap="round"/);
  assert.match(svg, /stroke-linejoin="bevel"/);
  assert.match(svg, /stroke-width="2\.5"/);
  assert.match(svg, /font-size="18"/);
  assert.match(svg, /text-anchor="middle"/);
  assert.match(svg, /transform="translate\(20 15\)"/);
  assert.match(svg, /transform="rotate\(25\)"/);
  assert.match(svg, /transform="scale\(1\.5 1\.5\)"/);
});

// ---- the error battery -------------------------------------------------------
//
// Every tag protocol.mjs can raise, and every tag stream.mjs can raise, with
// the two renderers compared tag-for-tag AND in order. A renderer that
// carried its own copy of any of these rules would diverge here first.
const ERROR_CASES = [
  ["unknown-verb", ["draw wobble 1 2"]],
  ["unknown-verb (no verb at all)", ["draw"]],
  ["wrong-arity", ["draw circle 1 2"]],
  ["wrong-arity (label)", ["draw label 8"]],
  ["wrong-arity (protocol)", ["draw protocol"]],
  ["bad-number", ["draw circle x 2 3"]],
  ["bad-number (label)", ["draw label x 2 hello"]],
  ["bad-word", ["draw cap flat"]],
  ["bad-protocol-version", ["draw protocol one"]],
  ["protocol-late", ["draw circle 1 2 3", "draw protocol 1"]],
  ["protocol-repeated", ["draw protocol 1", "draw protocol 1"]],
  ["path-not-open (vertex)", ["draw vertex 1 1"]],
  ["path-not-open (curve)", ["draw curve 1 1 2 2 3 3"]],
  ["path-not-open (close)", ["draw close"]],
  ["path-not-open (end)", ["draw end"]],
  ["path-already-open", ["draw shape", "draw vertex 0 0", "draw shape", "draw end"]],
  ["path-unclosed", ["draw shape", "draw vertex 0 0"]],
  ["unmatched-pop", ["draw pop"]],
  ["unmatched-push", ["draw push", "draw rotate 10"]],
  ["several at once, in stream order", [
    "draw pop",
    "draw wobble",
    "draw circle 1 2",
    "draw vertex 3 3",
    "draw cap flat",
    "draw push",
  ]],
];

for (const [name, lines] of ERROR_CASES) {
  test(`both renderers report the same errors, in the same order: ${name}`, () => {
    const { canvas, svg } = bothRender(lines);
    assert.ok(canvas.errors.length > 0, "the case must actually provoke an error");
    assert.deepEqual(
      svg.errors.map((e) => e.tag),
      canvas.errors.map((e) => e.tag),
    );
    assert.deepEqual(svg.errors, canvas.errors, "message text agrees too, not only the tag");
    assert.equal(svg.drawn, canvas.drawn);
    assert.deepEqual(svg.text, canvas.text);
  });
}

test("the error battery reaches every tag either renderer can raise", () => {
  const seen = new Set();
  for (const [, lines] of ERROR_CASES) {
    for (const e of paint(fakeCtx(), lines, DIMENSIONS).errors) seen.add(e.tag);
  }
  seen.add("unsupported-version"); // its own test below — it refuses the stream whole
  assert.deepEqual(
    [...seen].sort(),
    [
      "bad-number", "bad-protocol-version", "bad-word", "path-already-open",
      "path-not-open", "path-unclosed", "protocol-late", "protocol-repeated",
      "unknown-verb", "unmatched-pop", "unmatched-push", "unsupported-version",
      "wrong-arity",
    ],
  );
});

// ---- version refusal ---------------------------------------------------------

test("both renderers refuse an unsupported version identically and emit nothing", () => {
  for (const version of [2, 7, 99]) {
    const lines = [`draw protocol ${version}`, "draw circle 10 10 5", "some prose", "draw rect 0 0 5 5"];
    const ctx = fakeCtx();
    const canvas = paint(ctx, lines, DIMENSIONS);
    const svg = toSvg(lines, DIMENSIONS);

    assert.deepEqual(svg.errors, canvas.errors);
    assert.equal(canvas.errors[0].tag, "unsupported-version");
    assert.equal(canvas.drawn, 0);
    assert.equal(svg.drawn, 0);
    assert.deepEqual(canvas.text, []);
    assert.deepEqual(svg.text, []);
    assert.deepEqual(ctx.calls, [], "the canvas is never touched");
    assert.equal(svg.svg, "", "no document at all, not an empty one");
  }
});

// ---- colour agreement --------------------------------------------------------

const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const canvasRgb = (style) => style.match(/rgba?\(([^)]*)\)/)[1].split(",").slice(0, 3).map((n) => Number(n.trim()));

const COLOURS = [
  [0, 0, 0, "black"],
  [1, 0, 0, "white"],
  [0.5, 0, 0, "mid grey"],
  [0.7, 0.1, 200, "teal"],
  [0.75, 0.12, 60, "orange"],
  [0.45, 0.2, 300, "violet"],
  [1, 0.5, 0, "out of gamut: L=1 at high chroma"],
  [0.05, 0.37, 140, "out of gamut: near-black at maximum chroma"],
];

for (const [L, C, H, label] of COLOURS) {
  test(`both renderers resolve the same sRGB for ${label}`, () => {
    const ctx = fakeCtx();
    paint(ctx, [`draw fill ${L} ${C} ${H} 1`, "draw rect 0 0 1 1"], DIMENSIONS);
    const { svg } = toSvg([`draw fill ${L} ${C} ${H} 1`, "draw rect 0 0 1 1"], DIMENSIONS);

    const fromSvg = hexToRgb(/<rect x="0" y="0" width="1"[^>]*fill="(#[0-9a-f]{6})"/.exec(svg)[1]);
    const fromCanvas = canvasRgb(ctx.fillStyle);
    const reference = oklchToRgb(L, C, H).map((c) => Math.round(c * 255));

    assert.deepEqual(fromSvg, fromCanvas);
    assert.deepEqual(fromSvg, reference);
    for (const c of fromSvg) assert.ok(c >= 0 && c <= 255, "clamped, never out of range or NaN");
  });
}

test("alpha crosses as canvas rgba and as an svg opacity attribute, same value", () => {
  for (const a of [0, 0.05, 0.5, 0.875, 1]) {
    const lines = [`draw fill 0.5 0.1 120 ${a}`, "draw rect 0 0 1 1"];
    const ctx = fakeCtx();
    paint(ctx, lines, DIMENSIONS);
    const { svg } = toSvg(lines, DIMENSIONS);
    assert.equal(Number(ctx.fillStyle.match(/,\s*([\d.]+)\)$/)[1]), a);
    assert.equal(Number(/<rect x="0" y="0" width="1"[^>]*fill-opacity="([\d.]+)"/.exec(svg)[1]), a);
  }
});

// ---- arc geometry ------------------------------------------------------------
//
// The place two renderers are most likely to disagree (specification §7), so
// this is analytic rather than a golden string: the SVG endpoints and flags
// are recomputed from the radian range the canvas was actually given.

function svgArcCommands(d) {
  const m = /^M ([-\d.]+) ([-\d.]+) (.*)$/.exec(d);
  const start = [Number(m[1]), Number(m[2])];
  const arcs = [...m[3].matchAll(/A ([-\d.]+) ([-\d.]+) 0 ([01]) ([01]) ([-\d.]+) ([-\d.]+)/g)].map((a) => ({
    rx: Number(a[1]),
    ry: Number(a[2]),
    largeArc: Number(a[3]),
    sweep: Number(a[4]),
    to: [Number(a[5]), Number(a[6])],
  }));
  return { start, arcs };
}

const near = (a, b, why) => assert.ok(Math.abs(a - b) < 1e-3, `${why}: ${a} vs ${b}`);

const ARC_CASES = [
  [0, 90, "a quarter turn from the positive x axis"],
  [0, 180, "a half turn, exactly on the large-arc boundary"],
  [0, 181, "just past the large-arc boundary"],
  [90, 270, "starting at the bottom of the circle"],
  [300, 10, "wrapping past 360"],
  [350, 349, "wrapping to very nearly a full turn"],
  [45, 45, "equal start and end: a full circle"],
  [0, 0, "zero to zero: a full circle from the x axis"],
  [-90, -45, "negative angles"],
];

for (const [start, end, why] of ARC_CASES) {
  test(`the two renderers sweep the same arc — ${why}`, () => {
    const line = `draw arc 100 80 30 ${start} ${end}`;
    const ctx = fakeCtx();
    paint(ctx, [line], DIMENSIONS);
    const { svg } = toSvg([line], DIMENSIONS);

    const [, cx, cy, r, startRad, endRad, anticlockwise] = ctx.calls.find((c) => c[0] === "arc");
    assert.equal(anticlockwise, false, "canvas always sweeps in the increasing-angle direction");
    assert.ok(endRad > startRad, "the wrap rule leaves end strictly above start");

    const { start: p0, arcs } = svgArcCommands(/<path d="([^"]+)"/.exec(svg)[1]);
    const at = (rad) => [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];

    const [x0, y0] = at(startRad);
    near(p0[0], x0, "start x");
    near(p0[1], y0, "start y");

    const sweptRad = endRad - startRad;
    if (sweptRad >= 2 * Math.PI - 1e-9) {
      assert.equal(arcs.length, 2, "a full circle is two half turns, not one degenerate A");
      const [hx, hy] = at(startRad + Math.PI);
      near(arcs[0].to[0], hx, "half-turn x");
      near(arcs[0].to[1], hy, "half-turn y");
      near(arcs[1].to[0], x0, "closing x");
      near(arcs[1].to[1], y0, "closing y");
      for (const a of arcs) {
        assert.equal(a.largeArc, 1);
        assert.equal(a.sweep, 1);
      }
    } else {
      assert.equal(arcs.length, 1);
      const [x1, y1] = at(endRad);
      near(arcs[0].to[0], x1, "end x");
      near(arcs[0].to[1], y1, "end y");
      assert.equal(arcs[0].largeArc, sweptRad > Math.PI ? 1 : 0, "large-arc follows the swept angle");
      assert.equal(arcs[0].sweep, 1, "clockwise as pictured, always");
      near(arcs[0].rx, r, "rx");
      near(arcs[0].ry, r, "ry");
    }
  });
}

test("an arc is a curve, not a wedge, in both renderers", () => {
  const line = "draw arc 100 80 30 0 120";
  const ctx = fakeCtx();
  paint(ctx, [line], DIMENSIONS);
  const { svg } = toSvg([line], DIMENSIONS);
  assert.ok(!ctx.calls.some((c) => c[0] === "lineTo"), "canvas adds no line to the centre");
  const d = /<path d="([^"]+)"/.exec(svg)[1];
  assert.doesNotMatch(d, /Z/, "svg does not close the arc back to anything");
  assert.doesNotMatch(d, new RegExp("L "), "svg adds no straight segment to the centre");
});

// ---- the three refined programs through both renderers -----------------------

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

test("turtle renders through both renderers with no error, and agrees", async () => {
  const restore = installFsFetch();
  try {
    const r = await runProgramGraph(readExample("turtle"), { base: baseFor("turtle") });
    assert.equal(r.error, null);
    const { canvas, svg } = bothRender(r.output);
    assert.deepEqual(canvas.errors, []);
    assert.deepEqual(svg.errors, []);
    assert.equal(canvas.drawn, svg.drawn);
    assert.deepEqual(canvas.text, svg.text);
    assert.match(svg.svg, /^<svg /);
    assert.ok(svg.svg.includes("<ellipse"), "the leaves are ellipses in both");
  } finally {
    restore();
  }
});

for (const [name, keys] of [["bloom", []], ["snake", ["ArrowLeft"]]]) {
  test(`${name} renders through both renderers with no error on every tick, and agrees`, async () => {
    const restore = installFsFetch();
    try {
      const src = readExample(name);
      const loader = new BrowserModuleLoader({ base: baseFor(name) });
      let state = null;
      for (let tick = 0; tick < 20; tick++) {
        const r = await stepGraph(src, { tick, keys, pointer: { x: 0, y: 0, down: false }, state }, { loader });
        assert.equal(r.error, null);
        state = r.state;
        const { canvas, svg } = bothRender(r.lines);
        assert.deepEqual(canvas.errors, [], `${name} tick ${tick} on canvas`);
        assert.deepEqual(svg.errors, [], `${name} tick ${tick} in svg`);
        assert.equal(canvas.drawn, svg.drawn);
        assert.deepEqual(canvas.text, svg.text);
        assert.match(svg.svg, /^<svg [\s\S]*<\/svg>\n$/);
      }
    } finally {
      restore();
    }
  });
}

test("the SVG each program produces is well-formed and fully escaped", async () => {
  const restore = installFsFetch();
  try {
    const turtle = await runProgramGraph(readExample("turtle"), { base: baseFor("turtle") });
    const streams = [["turtle", turtle.output]];
    for (const name of ["bloom", "snake"]) {
      const loader = new BrowserModuleLoader({ base: baseFor(name) });
      const r = await stepGraph(
        readExample(name),
        { tick: 13, keys: ["ArrowLeft"], pointer: { x: 0, y: 0, down: false }, state: null },
        { loader },
      );
      streams.push([name, r.lines]);
    }
    for (const [name, lines] of streams) {
      const { svg } = toSvg(lines, DIMENSIONS);
      assert.ok(svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg"'), `${name}: root is not <svg>`);
      assert.ok(svg.trimEnd().endsWith("</svg>"), `${name}: document is not closed`);
      // Nothing outside a tag carries a raw angle bracket or a bare ampersand
      // — the two ways text content makes a document unparseable.
      const textContent = svg.replace(/<[^>]*>/g, "");
      assert.doesNotMatch(textContent, /[<>]/, `${name}: unescaped angle bracket in text`);
      assert.doesNotMatch(textContent, /&(?!amp;|lt;|gt;|quot;|apos;|#)/, `${name}: bare ampersand`);
    }
  } finally {
    restore();
  }
});

test("every group the corpus opens is closed, in every frame of every program", async () => {
  const restore = installFsFetch();
  try {
    const turtle = await runProgramGraph(readExample("turtle"), { base: baseFor("turtle") });
    const streams = [turtle.output];
    for (const name of ["bloom", "snake"]) {
      const loader = new BrowserModuleLoader({ base: baseFor(name) });
      const r = await stepGraph(
        readExample(name),
        { tick: 13, keys: [], pointer: { x: 0, y: 0, down: false }, state: null },
        { loader },
      );
      streams.push(r.lines);
    }
    for (const lines of streams) {
      const { svg } = toSvg(lines, DIMENSIONS);
      assert.equal((svg.match(/<g[ >]/g) || []).length, (svg.match(/<\/g>/g) || []).length);
    }
  } finally {
    restore();
  }
});
