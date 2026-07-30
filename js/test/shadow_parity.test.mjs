// js/test/shadow_parity.test.mjs — the shadow single-cast guarantee and the
// canvas/SVG shadow-parameter agreement (planes-drawing-protocol-v2.md §6.1,
// §6.2), headless.
//
// Two defects §6 names explicitly, both fixed in js/paint/painter.mjs:
//
//   1. Canvas casts a shadow PER DRAWING OPERATION. Every shape here fills
//      then strokes, so a shape with both visible casts two overlapping
//      shadows unless the renderer composites it once first. These tests
//      hold "exactly one shadow" by watching the CALL SEQUENCE: the
//      offscreen-composite path is taken (an alloc + drawImage) if and only
//      if both fill and stroke are visible AND a shadow is set; a single
//      ctx.fill()+ctx.stroke() pass otherwise, which the browser itself
//      would only cast once for anyway (only one of the two paints anything
//      when the other's alpha is 0).
//   2. shadowBlur/OffsetX/OffsetY live in the BACKING STORE's pixel space,
//      which `scale` stretches (js/paint/export.mjs's supersampled PNG) but
//      a program's own coordinates never do — unhandled, an exported PNG's
//      shadows come out too small relative to the picture. Multiplying by
//      `scale` at the point they are set is the fix; these tests assert the
//      ratio holds across scale 1 and scale 4.
//
// SVG's feDropShadow needs no such fix (a filter is applied once, to the
// whole rendered element, by construction) — its own test here is that its
// dx/dy/stdDeviation match canvas's values at scale 1, per §6.3's stated
// acceptance criterion.

import { test } from "node:test";
import assert from "node:assert/strict";
import { paint } from "../paint/painter.mjs";
import { toSvg } from "../paint/svg.mjs";

const DIMENSIONS = { width: 200, height: 160, background: "#ffffff" };

function fakeCtx() {
  const calls = [];
  const record = (name) => (...args) => calls.push([name, ...args]);
  let transform = "identity";
  return {
    calls,
    strokeStyle: null, fillStyle: null, lineWidth: null, lineCap: null,
    lineJoin: null, font: null, textAlign: null,
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
    createLinearGradient() { return { addColorStop() {} }; },
    createRadialGradient() { return { addColorStop() {} }; },
    getTransform() { return transform; },
    setTransform(t) { transform = t; },
    resetTransform() { transform = "identity"; },
  };
}

// A canvas-shaped fake: `.getContext("2d")` returns its own fakeCtx, and it
// carries width/height like a real (Offscreen)Canvas would.
function fakeOffscreenFactory() {
  const created = [];
  const factory = (w, h) => {
    const ctx = fakeCtx();
    const canvas = { width: w, height: h, getContext: () => ctx };
    created.push({ canvas, ctx });
    return canvas;
  };
  factory.created = created;
  return factory;
}

// ---- A: exactly one shadow — offscreen composite iff both visible -------

test("fill only, stroke transparent, shadow set: single pass, no offscreen allocated", () => {
  const factory = fakeOffscreenFactory();
  const ctx = fakeCtx();
  const lines = [
    "draw protocol 2",
    "draw shadow 3 3 6 0.2 0.05 0",
    "draw fill 0.5 0.1 0 1",
    "draw stroke 0 0 0 0",
    "draw circle 50 50 10",
  ];
  const { errors } = paint(ctx, lines, { ...DIMENSIONS, offscreenCanvas: factory });
  assert.deepEqual(errors, []);
  assert.equal(factory.created.length, 0, "no offscreen ever allocated");
  assert.ok(ctx.calls.some((c) => c[0] === "fill"));
  assert.ok(ctx.calls.some((c) => c[0] === "stroke"));
  assert.ok(!ctx.calls.some((c) => c[0] === "drawImage"), "single pass: no compositing step");
});

test("both fill and stroke visible, no shadow: single pass, no offscreen allocated", () => {
  const factory = fakeOffscreenFactory();
  const ctx = fakeCtx();
  const lines = ["draw fill 0.5 0.1 0 1", "draw stroke 0.2 0.1 0 1", "draw circle 50 50 10"];
  const { errors } = paint(ctx, lines, { ...DIMENSIONS, offscreenCanvas: factory });
  assert.deepEqual(errors, []);
  assert.equal(factory.created.length, 0);
  assert.ok(!ctx.calls.some((c) => c[0] === "drawImage"));
});

test("both fill and stroke visible AND a shadow is set: the offscreen composite path is taken, exactly once", () => {
  const factory = fakeOffscreenFactory();
  const ctx = fakeCtx();
  const lines = [
    "draw protocol 2",
    "draw shadow 4 4 8 0.1 0.1 20",
    "draw fill 0.5 0.1 0 1",
    "draw stroke 0.2 0.1 0 1",
    "draw circle 50 50 10",
  ];
  const { errors } = paint(ctx, lines, { ...DIMENSIONS, offscreenCanvas: factory });
  assert.deepEqual(errors, []);
  assert.equal(factory.created.length, 1, "the offscreen canvas is allocated exactly once");
  const drawImageCalls = ctx.calls.filter((c) => c[0] === "drawImage");
  assert.equal(drawImageCalls.length, 1, "composited onto the main canvas exactly once — one shadow");
  // The offscreen itself received fill+stroke (the mark, painted once,
  // un-shadowed there) and never had shadowColor touched.
  const { ctx: off } = factory.created[0];
  assert.ok(off.calls.some((c) => c[0] === "fill"));
  assert.ok(off.calls.some((c) => c[0] === "stroke"));
  assert.equal(off.shadowColor, null, "the offscreen mark itself is never shadowed — only the composite is");
});

test("the offscreen canvas is allocated once per paint() call and reused across multiple shadowed marks", () => {
  const factory = fakeOffscreenFactory();
  const ctx = fakeCtx();
  const lines = [
    "draw protocol 2",
    "draw shadow 2 2 4 0.1 0.1 20",
    "draw fill 0.5 0.1 0 1",
    "draw stroke 0.2 0.1 0 1",
    "draw circle 20 20 5",
    "draw circle 60 60 5",
    "draw circle 100 100 5",
  ];
  const { errors } = paint(ctx, lines, { ...DIMENSIONS, offscreenCanvas: factory });
  assert.deepEqual(errors, []);
  assert.equal(factory.created.length, 1, "one allocation, reused for all three marks");
  assert.equal(ctx.calls.filter((c) => c[0] === "drawImage").length, 3, "one composite per mark, still one shadow each");
  const { ctx: off } = factory.created[0];
  assert.equal(off.calls.filter((c) => c[0] === "clearRect").length, 3, "cleared between marks");
});

test("a stream that never sets a shadow allocates no offscreen canvas at all", () => {
  const factory = fakeOffscreenFactory();
  const ctx = fakeCtx();
  const lines = ["draw fill 0.5 0.1 0 1", "draw stroke 0.2 0.1 0 1", "draw rect 0 0 10 10 0", "draw circle 50 50 5"];
  paint(ctx, lines, { ...DIMENSIONS, offscreenCanvas: factory });
  assert.equal(factory.created.length, 0);
});

test("the path block (shape/vertex/curve/end) gets the same single-shadow treatment as a shape", () => {
  const factory = fakeOffscreenFactory();
  const ctx = fakeCtx();
  const lines = [
    "draw protocol 2",
    "draw shadow 2 2 4 0.1 0.1 20",
    "draw fill 0.5 0.1 0 1",
    "draw stroke 0.2 0.1 0 1",
    "draw shape",
    "draw vertex 0 0",
    "draw vertex 10 0",
    "draw vertex 5 10",
    "draw close",
    "draw end",
  ];
  const { errors } = paint(ctx, lines, { ...DIMENSIONS, offscreenCanvas: factory });
  assert.deepEqual(errors, []);
  assert.equal(ctx.calls.filter((c) => c[0] === "drawImage").length, 1);
});

// ---- B: PNG-export scale multiplies shadow, matching every geometric ----
//        dimension the CTM already stretches

test("shadow offset and blur scale linearly with `scale` — the ratio holds at 1 and at 4", () => {
  const lines = [
    "draw protocol 2",
    "draw shadow 3 5 8 0.2 0.1 40",
    "draw fill 0.5 0.1 0 0", // fill invisible: single-pass path, shadow set directly on ctx
    "draw stroke 0.2 0.1 0 1",
    "draw circle 50 50 10",
  ];
  const ctx1 = fakeCtx();
  paint(ctx1, lines, { ...DIMENSIONS, scale: 1 });
  const ctx4 = fakeCtx();
  paint(ctx4, lines, { ...DIMENSIONS, scale: 4 });

  assert.equal(ctx1.shadowOffsetX, 3);
  assert.equal(ctx1.shadowOffsetY, 5);
  assert.equal(ctx1.shadowBlur, 8);
  assert.equal(ctx4.shadowOffsetX, 12, "3 * scale 4");
  assert.equal(ctx4.shadowOffsetY, 20, "5 * scale 4");
  assert.equal(ctx4.shadowBlur, 32, "8 * scale 4");

  const ratioX = ctx4.shadowOffsetX / ctx1.shadowOffsetX;
  const ratioY = ctx4.shadowOffsetY / ctx1.shadowOffsetY;
  const ratioBlur = ctx4.shadowBlur / ctx1.shadowBlur;
  assert.equal(ratioX, 4);
  assert.equal(ratioY, 4);
  assert.equal(ratioBlur, 4);
});

test("a glow (dx 0, dy 0) still scales its blur", () => {
  const lines = [
    "draw protocol 2",
    "draw shadow 0 0 6 0.9 0.1 60",
    "draw fill 0.5 0.1 0 0",
    "draw stroke 0.2 0.1 0 1",
    "draw circle 50 50 10",
  ];
  const ctx1 = fakeCtx();
  paint(ctx1, lines, { ...DIMENSIONS, scale: 1 });
  const ctx4 = fakeCtx();
  paint(ctx4, lines, { ...DIMENSIONS, scale: 4 });
  assert.equal(ctx1.shadowOffsetX, 0);
  assert.equal(ctx1.shadowOffsetY, 0);
  assert.equal(ctx4.shadowBlur / ctx1.shadowBlur, 4);
});

// ---- C: SVG's feDropShadow matches canvas at scale 1 ---------------------

test("SVG's feDropShadow dx/dy/stdDeviation match canvas's shadow values at scale 1", () => {
  const lines = [
    "draw protocol 2",
    "draw shadow 3 5 8 0.2 0.1 40",
    "draw fill 0.5 0.1 0 0",
    "draw stroke 0.2 0.1 0 1",
    "draw circle 50 50 10",
  ];
  const ctx = fakeCtx();
  paint(ctx, lines, { ...DIMENSIONS, scale: 1 });
  const { svg, errors } = toSvg(lines, DIMENSIONS);
  assert.deepEqual(errors, []);
  const m = /<feDropShadow dx="([-\d.]+)" dy="([-\d.]+)" stdDeviation="([\d.]+)"/.exec(svg);
  assert.ok(m, "no feDropShadow found");
  assert.equal(Number(m[1]), ctx.shadowOffsetX);
  assert.equal(Number(m[2]), ctx.shadowOffsetY);
  assert.equal(Number(m[3]), ctx.shadowBlur);
});

test("the shadow's alpha comes from the current `alpha` state, in both renderers", () => {
  const lines = [
    "draw protocol 2",
    "draw shadow 2 2 4 0.5 0.1 20",
    "draw alpha 0.4",
    "draw fill 0.5 0.1 0 0",
    "draw stroke 0.2 0.1 0 1",
    "draw circle 50 50 10",
  ];
  const ctx = fakeCtx();
  paint(ctx, lines, DIMENSIONS);
  assert.match(ctx.shadowColor, /rgba\(.*,\s*0\.4\)$/);
  const { svg } = toSvg(lines, DIMENSIONS);
  assert.match(svg, /flood-opacity="0\.4"/);
});

test("dx 0, dy 0 is a glow, not a special verb — shadow's own arity covers it", () => {
  const lines = ["draw protocol 2", "draw shadow 0 0 10 0.9 0.05 60"];
  const r = parseAndCheck(lines);
  assert.deepEqual(r.errors, []);
});

function parseAndCheck(lines) {
  const ctx = fakeCtx();
  return paint(ctx, lines, DIMENSIONS);
}
