// js/test/protocol_v3.test.mjs — version 3: `blur`, `gradient mid`, and the
// inner radius that is NOT a version feature (planes-drawing-protocol-v3.md
// §§1.1, 2, 6.1, 6.6, normative), headless.
//
// Three additions, and the interesting thing about them is that only two are
// gated. `blur` is a new verb and `mid` is a new kind word, so a stream that
// declares 1 or 2 and uses either is refused by name. `gradient radial`'s
// inner radius is an OPTIONAL ARGUMENT widening an existing verb, which is
// the same category as `ellipse`/`rect` rotation in v2 — there is nothing for
// a version to gate, because a renderer that had never heard of the argument
// would still have drawn the mark. §1.1 states that as a category rather than
// a list, and this file holds it to that: a v1 stream ACCEPTS a twelve-number
// radial.
//
// The error battery at the end asserts the same tags in the same order from
// both sinks, which is the mechanism that keeps a rule in stream.mjs rather
// than in a renderer.

import { test } from "node:test";
import assert from "node:assert/strict";
import { parseCommand } from "../paint/protocol.mjs";
import { paint } from "../paint/painter.mjs";
import { toSvg } from "../paint/svg.mjs";
import { walk, gradientStopsFrom, DEFAULTS } from "../paint/stream.mjs";

const DIMENSIONS = { width: 200, height: 160, background: "#ffffff" };

function fakeCtx() {
  const calls = [];
  const record = (name) => (...args) => calls.push([name, ...args]);
  let transform = "identity";
  const grad = () => ({ addColorStop: (...a) => calls.push(["addColorStop", ...a]) });
  return {
    calls,
    strokeStyle: null, fillStyle: null, lineWidth: null, lineCap: null,
    lineJoin: null, font: null, textAlign: null, filter: "none",
    shadowColor: null, shadowBlur: null, shadowOffsetX: null, shadowOffsetY: null,
    globalAlpha: 1, globalCompositeOperation: "source-over",
    beginPath: record("beginPath"), moveTo: record("moveTo"), lineTo: record("lineTo"),
    arc: record("arc"), ellipse: record("ellipse"), rect: record("rect"),
    closePath: record("closePath"), bezierCurveTo: record("bezierCurveTo"),
    stroke: record("stroke"), fill: record("fill"), fillRect: record("fillRect"),
    fillText: record("fillText"), translate: record("translate"),
    rotate: record("rotate"), scale: record("scale"),
    save: record("save"), restore: record("restore"), clip: record("clip"),
    drawImage: record("drawImage"), clearRect: record("clearRect"),
    setLineDash() {}, getLineDash() { return []; },
    createLinearGradient(...a) { calls.push(["createLinearGradient", ...a]); return grad(); },
    createRadialGradient(...a) { calls.push(["createRadialGradient", ...a]); return grad(); },
    getTransform() { return transform; },
    setTransform(t) { transform = t; },
    resetTransform() { transform = "identity"; },
  };
}

// A blurred or shadowed mark with BOTH fill and stroke visible goes through
// painter.mjs's offscreen composite (v3 §6.1, third semantic), and Node has
// no canvas of any kind — so one is injected. js/test/blur_parity.test.mjs is
// where that path is actually asserted; here it just has to not throw.
const offscreenCanvas = (w, h) => {
  const c = fakeCtx();
  return { width: w, height: h, getContext: () => c };
};

const bothRender = (lines) => ({
  canvas: paint(fakeCtx(), lines, { ...DIMENSIONS, offscreenCanvas }),
  svg: toSvg(lines, DIMENSIONS),
});

const tagsOf = (r) => r.errors.map((e) => e.tag);

// ---- A: the initial-state table gained one row ----------------------------

test("§5's reset table carries blur 0", () => {
  assert.equal(DEFAULTS.blur, 0);
  assert.ok(Object.isFrozen(DEFAULTS));
});

// ---- B: parsing ------------------------------------------------------------

test("blur takes exactly one number", () => {
  assert.deepEqual(parseCommand("draw blur 12"), { kind: "command", verb: "blur", args: [12] });
  assert.equal(parseCommand("draw blur").tag, "wrong-arity");
  assert.equal(parseCommand("draw blur 1 2").tag, "wrong-arity");
  assert.equal(parseCommand("draw blur wide").tag, "bad-number");
});

test("gradient mid takes a stop position, four geometry numbers, then THREE whole stops — 17, always", () => {
  const r = parseCommand(
    "draw gradient mid 0.55 0 0 0 100  0.2 0.06 265 1  0.5 0.1 330 1  0.9 0.03 60 1");
  assert.equal(r.kind, "command");
  assert.deepEqual(r.args, ["mid", 0.55, 0, 0, 0, 100, 0.2, 0.06, 265, 1, 0.5, 0.1, 330, 1, 0.9, 0.03, 60, 1]);
  assert.equal(r.args.length - 1, 17);
});

test("gradient mid with sixteen or eighteen numbers is wrong-arity — fixed arity, not 'as many as you wrote'", () => {
  const short = parseCommand("draw gradient mid " + Array(16).fill("1").join(" "));
  const long = parseCommand("draw gradient mid " + Array(18).fill("1").join(" "));
  assert.equal(short.tag, "wrong-arity");
  assert.equal(long.tag, "wrong-arity");
  assert.match(short.message, /takes 17 numeric arguments/);
});

test("gradient mid's stop position must be strictly between 0 and 1", () => {
  const stops = " 0 0 0 100  0.2 0.06 265 1  0.5 0.1 330 1  0.9 0.03 60 1";
  for (const p of ["0", "1", "-0.2", "1.5"]) {
    const r = parseCommand(`draw gradient mid ${p}${stops}`);
    assert.equal(r.tag, "bad-number", `p=${p} should be refused`);
    assert.match(r.message, /not between 0 and 1/);
    assert.match(r.message, /above 0 and below 1/);
  }
  assert.equal(parseCommand(`draw gradient mid 0.001${stops}`).kind, "command");
  assert.equal(parseCommand(`draw gradient mid 0.999${stops}`).kind, "command");
});

test("gradient radial's inner radius must be smaller than its radius", () => {
  const stops = " 0.9 0.05 90 1 0.4 0.1 260 1";
  assert.equal(parseCommand(`draw gradient radial 50 50 40 12${stops}`).kind, "command");
  for (const inner of ["40", "41"]) {
    const r = parseCommand(`draw gradient radial 50 50 40 ${inner}${stops}`);
    assert.equal(r.tag, "bad-number");
    assert.match(r.message, /inner radius/);
  }
});

// ---- C: the version gate ---------------------------------------------------

for (const declared of [null, 1, 2]) {
  const label = declared === null ? "declaring nothing" : `declaring version ${declared}`;
  const head = declared === null ? [] : [`draw protocol ${declared}`];

  test(`a stream ${label} refuses blur with verb-not-in-version, naming draw protocol 3`, () => {
    const { canvas, svg } = bothRender([...head, "draw blur 4", "draw circle 10 10 5"]);
    assert.deepEqual(tagsOf(canvas), ["verb-not-in-version"]);
    assert.deepEqual(svg.errors, canvas.errors, "both sinks, same error");
    assert.match(canvas.errors[0].message, /"blur" is not part of protocol version/);
    assert.match(canvas.errors[0].message, /draw protocol 3/);
  });

  test(`a stream ${label} refuses gradient mid, naming the KIND WORD and draw protocol 3`, () => {
    const line = "draw gradient mid 0.5 0 0 0 100 0.2 0.06 265 1 0.5 0.1 330 1 0.9 0.03 60 1";
    const { canvas, svg } = bothRender([...head, line, "draw circle 10 10 5"]);
    assert.deepEqual(tagsOf(canvas), ["verb-not-in-version"]);
    assert.deepEqual(svg.errors, canvas.errors);
    assert.match(canvas.errors[0].message, /"gradient mid" is not part of protocol version/);
    assert.match(canvas.errors[0].message, /draw protocol 3/);
  });

  test(`a stream ${label} still ACCEPTS gradient linear and radial — the verb is v2, only the kind word is v3`, () => {
    if (declared === 2) {
      const { canvas, svg } = bothRender([
        ...head, "draw gradient linear 0 0 100 0 0.9 0.05 90 1 0.4 0.1 260 1"]);
      assert.deepEqual(canvas.errors, []);
      assert.deepEqual(svg.errors, []);
    }
  });

  test(`a stream ${label} ACCEPTS a twelve-number gradient radial — an arity widening is not gated`, () => {
    // The whole point of §1.1's exception being a CATEGORY: `radial` itself
    // is a v2 verb, so a v1 stream refuses it for being v2 — but never for
    // the count of numbers after it. A v2 stream must accept both forms.
    const eleven = "draw gradient radial 50 50 40 0.9 0.05 90 1 0.4 0.1 260 1";
    const twelve = "draw gradient radial 50 50 40 12 0.9 0.05 90 1 0.4 0.1 260 1";
    const a = bothRender([...head, eleven]);
    const b = bothRender([...head, twelve]);
    assert.deepEqual(tagsOf(b.canvas), tagsOf(a.canvas),
      "the optional inner radius changes nothing about whether the line is allowed");
    assert.deepEqual(b.svg.errors, b.canvas.errors);
    if (declared === 2) {
      assert.deepEqual(b.canvas.errors, [], "a v2 stream draws a twelve-number radial");
    }
  });
}

test("a v3 stream accepts all three, and both sinks agree there is nothing to report", () => {
  const { canvas, svg } = bothRender([
    "draw protocol 3",
    "draw blur 4",
    "draw gradient mid 0.55 0 0 0 100 0.2 0.06 265 1 0.5 0.1 330 1 0.9 0.03 60 1",
    "draw rect 0 0 100 100 0",
    "draw gradient radial 50 50 40 12 0.9 0.05 90 1 0.4 0.1 260 1",
    "draw circle 50 50 20",
  ]);
  assert.deepEqual(canvas.errors, []);
  assert.deepEqual(svg.errors, []);
});

test("version 4 is still refused whole — the ceiling moved by one, it did not disappear", () => {
  const { canvas, svg } = bothRender(["draw protocol 4", "draw circle 1 2 3"]);
  assert.equal(canvas.errors[0].tag, "unsupported-version");
  assert.match(canvas.errors[0].message, /versions 1-3/);
  assert.equal(canvas.drawn, 0);
  assert.deepEqual(svg.errors, canvas.errors);
});

// ---- D: what the shared walk computes, once, for both sinks ---------------

test("a mid's stops are two independently interpolated segments meeting at p", () => {
  const stops = gradientStopsFrom(
    [[0.2, 0.06, 265, 1], [0.5, 0.1, 330, 1], [0.9, 0.03, 60, 1]], [0, 0.55, 1]);
  // Sixteen samples per segment, the shared colour emitted once: 31.
  assert.equal(stops.length, 31);
  assert.equal(stops[0].offset, 0);
  assert.equal(stops[stops.length - 1].offset, 1);
  const middle = stops[15];
  assert.ok(Math.abs(middle.offset - 0.55) < 1e-12, `middle at ${middle.offset}`);
  assert.ok(Math.abs(middle.L - 0.5) < 1e-12);
  assert.ok(Math.abs(middle.H - 330) < 1e-9);
  // Offsets never go backwards.
  for (let i = 1; i < stops.length; i++) {
    assert.ok(stops[i].offset > stops[i - 1].offset, `offset ${i} did not advance`);
  }
  // Hue takes the SHORTER arc per segment: 265 -> 330 climbs, and 330 -> 60
  // climbs through 0 rather than falling back through 180.
  assert.ok(stops[8].H > 265 && stops[8].H < 330, `first segment hue ${stops[8].H}`);
  const second = stops[22].H;
  assert.ok(second > 330 || second < 60, `second segment hue ${second} took the long way`);
});

test("a two-stop gradient still produces exactly what version 2 produced", () => {
  const stops = gradientStopsFrom([[0.9, 0.05, 90, 1], [0.4, 0.1, 260, 1]], [0, 1]);
  assert.equal(stops.length, 16);
  assert.equal(stops[0].offset, 0);
  assert.equal(stops[15].offset, 1);
  assert.equal(stops[0].L, 0.9);
  assert.equal(stops[15].L, 0.4);
});

test("a mid reaches a sink as a LINEAR gradient with four geometry numbers — the third stop is in the stops", () => {
  const seen = [];
  const sink = new Proxy({
    gradient(kind, geom, stops) { seen.push({ kind, geom, count: stops.length }); },
  }, {
    get: (t, k) => (k in t ? t[k] : () => {}),
    has: () => true,
  });
  walk(["draw protocol 3",
        "draw gradient mid 0.55 0 0 0 100 0.2 0.06 265 1 0.5 0.1 330 1 0.9 0.03 60 1"], sink);
  assert.deepEqual(seen, [{ kind: "linear", geom: [0, 0, 0, 100], count: 31 }]);
});

// ---- E: both sinks express the inner radius natively ----------------------

test("canvas passes the inner radius as createRadialGradient's third argument", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw protocol 3",
              "draw gradient radial 50 60 40 12 0.9 0.05 90 1 0.4 0.1 260 1",
              "draw rect 0 0 100 100 0"], DIMENSIONS);
  const call = ctx.calls.find((c) => c[0] === "createRadialGradient");
  assert.deepEqual(call, ["createRadialGradient", 50, 60, 12, 50, 60, 40]);
});

test("an omitted inner radius reaches canvas as 0 — exactly what radial has always meant", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw protocol 3",
              "draw gradient radial 50 60 40 0.9 0.05 90 1 0.4 0.1 260 1",
              "draw rect 0 0 100 100 0"], DIMENSIONS);
  const call = ctx.calls.find((c) => c[0] === "createRadialGradient");
  assert.deepEqual(call, ["createRadialGradient", 50, 60, 0, 50, 60, 40]);
});

test("SVG carries the inner radius as `fr`, and omits it when it is 0", () => {
  const withInner = toSvg(["draw protocol 3",
    "draw gradient radial 50 60 40 12 0.9 0.05 90 1 0.4 0.1 260 1",
    "draw rect 0 0 100 100 0"], DIMENSIONS).svg;
  assert.match(withInner, /<radialGradient [^>]*cx="50" cy="60" r="40" fr="12"/);

  const without = toSvg(["draw protocol 3",
    "draw gradient radial 50 60 40 0.9 0.05 90 1 0.4 0.1 260 1",
    "draw rect 0 0 100 100 0"], DIMENSIONS).svg;
  assert.match(without, /<radialGradient [^>]*cx="50" cy="60" r="40">/);
  assert.doesNotMatch(without, /fr=/);
});

test("SVG emits three distinct stop colours for a mid, in offset order", () => {
  const { svg } = toSvg(["draw protocol 3",
    "draw gradient mid 0.55 0 0 0 100 0.2 0.06 265 1 0.5 0.1 330 1 0.9 0.03 60 1",
    "draw rect 0 0 100 100 0"], DIMENSIONS);
  const offsets = [...svg.matchAll(/<stop offset="([\d.]+)"/g)].map((m) => Number(m[1]));
  assert.equal(offsets.length, 31);
  assert.equal(offsets[0], 0);
  assert.equal(offsets[15], 0.55);
  assert.equal(offsets[30], 1);
  assert.match(svg, /<linearGradient /, "a mid is a linear gradient in the markup too");
});

// ---- F: the error battery, both sinks, same tags in the same order --------

test("every v3 refusal reaches both sinks with the same tag in the same order", () => {
  const lines = [
    "draw protocol 3",
    "draw blur",                                                   // wrong-arity
    "draw blur soft",                                              // bad-number
    "draw gradient mid 0 0 0 0 100 1 1 1 1 1 1 1 1 1 1 1 1",       // bad-number (p at 0)
    "draw gradient mid 0.5 0 0 0 100 1 1 1 1 1 1 1 1",             // wrong-arity
    "draw gradient radial 50 50 40 40 1 1 1 1 1 1 1 1",            // bad-number (inner >= r)
    "draw gradient conic 1 2 3 4 5 6 7 8 9 10 11 12",              // bad-word
    "draw blurr 4",                                                // unknown-verb
  ];
  const { canvas, svg } = bothRender(lines);
  assert.deepEqual(tagsOf(canvas), [
    "wrong-arity", "bad-number", "bad-number", "wrong-arity",
    "bad-number", "bad-word", "unknown-verb",
  ]);
  assert.deepEqual(svg.errors, canvas.errors, "same tags AND same messages, in the same order");
  // Nothing was drawn by any of them, and the stream was not refused whole —
  // a bad line is an error, not the end of the picture.
  assert.equal(canvas.drawn, 0);
});

test("blur is not a per-mark argument: it persists until changed, in both sinks", () => {
  const lines = [
    "draw protocol 3", "draw fill 0.5 0.1 0 1", "draw blur 5",
    "draw circle 20 20 5", "draw circle 60 20 5", "draw blur 0", "draw circle 100 20 5",
  ];
  const ctx = fakeCtx();
  paint(ctx, lines, { ...DIMENSIONS, offscreenCanvas });
  assert.equal(ctx.calls.filter((c) => c[0] === "drawImage").length, 2,
    "the two blurred marks each composited once; the third, unblurred, did not");
  const { svg } = toSvg(lines, DIMENSIONS);
  const circles = [...svg.matchAll(/<circle [^>]*\/>/g)].map((m) => m[0]);
  assert.equal(circles.length, 3);
  assert.match(circles[0], /filter="url\(#/);
  assert.match(circles[1], /filter="url\(#/);
  assert.doesNotMatch(circles[2], /filter=/, "cleared by `draw blur 0`");
  // Two marks under one blur share ONE def — a resource, content-keyed.
  assert.equal([...svg.matchAll(/<feGaussianBlur/g)].length, 1);
});
