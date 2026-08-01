// js/test/blur_parity.test.mjs — the three semantics §6.1 pins for `blur`,
// asserted identically in both sinks (planes-drawing-protocol-v3.md §6.1,
// normative), headless.
//
// A soft edge is the first thing in this protocol whose meaning is not
// obvious from the verb alone. Three questions have more than one defensible
// answer, and two renderers that each picked their own would disagree about a
// cloud:
//
//   1. If a mark is both blurred and shadowed, is the shadow cast from the
//      BLURRED mark or from the crisp one? A raster context's drawing model
//      answers "from the blurred one" natively — `ctx.filter` is applied to
//      the source before the shadow is derived from it — and an SVG filter
//      chain can be written either way round. The specification takes the
//      canvas answer, so svg.mjs builds feGaussianBlur -> feDropShadow.
//
//   2. Does an enclosing `clip` crop the blur, or does it crop the blurred
//      result? Blur first, clip second — which for SVG means the filter
//      REGION has to be declared big enough that the blur is not already lost
//      by the time the clipPath applies. The default region is a proportion
//      of the filtered element's own bounding box, which would crop a
//      two-pixel firefly's seven-pixel glow and leave a cloud's intact.
//
//   3. How many times is one mark blurred? Once — the same rule §6.6 states
//      for `shadow`, and for the same reason: canvas filters PER DRAWING
//      OPERATION, so a shape that fills and strokes would be blurred twice
//      and composite darker along its own outline. The offscreen composite
//      the shadow already used is the mechanism; blur widens the condition
//      that reaches for it.
//
// Every test here asserts the canvas answer and the SVG answer, in that
// order, so a divergence names itself.

import { test } from "node:test";
import assert from "node:assert/strict";
import { paint } from "../paint/painter.mjs";
import { toSvg } from "../paint/svg.mjs";

const DIMENSIONS = { width: 200, height: 160, background: "#ffffff" };

// Like shadow_parity's fake, plus a `filter` property — and every drawing
// call records a SNAPSHOT of the paint state in force at the moment it was
// made. Which properties were set eventually is not the question; which were
// set when the mark was drawn is.
function fakeCtx() {
  const calls = [];
  const ctx = {
    calls,
    strokeStyle: null, fillStyle: null, lineWidth: null, lineCap: null,
    lineJoin: null, font: null, textAlign: null,
    shadowColor: null, shadowBlur: null, shadowOffsetX: null, shadowOffsetY: null,
    globalAlpha: 1, globalCompositeOperation: "source-over",
    filter: "none",
    setLineDash() {}, getLineDash() { return []; },
    createLinearGradient() { return { addColorStop() {} }; },
    createRadialGradient() { return { addColorStop() {} }; },
    getTransform() { return this._t ?? "identity"; },
    setTransform(t) { this._t = t; },
    resetTransform() { this._t = "identity"; },
  };
  const snap = (name) => (...args) => calls.push({
    name, args, filter: ctx.filter, shadowBlur: ctx.shadowBlur,
    shadowOffsetX: ctx.shadowOffsetX,
  });
  for (const name of [
    "beginPath", "moveTo", "lineTo", "arc", "ellipse", "rect", "closePath",
    "bezierCurveTo", "stroke", "fill", "fillRect", "fillText", "translate",
    "rotate", "scale", "save", "restore", "clip", "drawImage", "clearRect",
  ]) ctx[name] = snap(name);
  return ctx;
}

function fakeOffscreenFactory() {
  const created = [];
  const factory = (w, h) => {
    const c = fakeCtx();
    const canvas = { width: w, height: h, getContext: () => c };
    created.push({ canvas, ctx: c });
    return canvas;
  };
  factory.created = created;
  return factory;
}

const only = (ctx, name) => ctx.calls.filter((c) => c.name === name);

// ---- 1: the mark is blurred, THEN the shadow is cast from the result ------

test("canvas sets the blur filter and the shadow on the SAME drawing operation", () => {
  const ctx = fakeCtx();
  paint(ctx, [
    "draw protocol 3",
    "draw blur 5",
    "draw shadow 3 4 8 0.2 0.1 40",
    "draw fill 0.5 0.1 0 1",
    "draw stroke 0 0 0 0",
    "draw circle 50 50 10",
  ], DIMENSIONS);
  const [filled] = only(ctx, "fill");
  assert.ok(filled, "the circle was filled");
  assert.equal(filled.filter, "blur(5px)");
  assert.equal(filled.shadowBlur, 8);
  assert.equal(filled.shadowOffsetX, 3);
});

test("SVG chains feGaussianBlur AHEAD of feDropShadow, in one filter, and the shadow reads the blur's result", () => {
  const { svg, errors } = toSvg([
    "draw protocol 3",
    "draw blur 5",
    "draw shadow 3 4 8 0.2 0.1 40",
    "draw fill 0.5 0.1 0 1",
    "draw circle 50 50 10",
  ], DIMENSIONS);
  assert.deepEqual(errors, []);
  const filters = [...svg.matchAll(/<filter [^>]*>([\s\S]*?)<\/filter>/g)].map((m) => m[1]);
  assert.equal(filters.length, 1, "one filter chain, not two");
  const chain = filters[0];
  const blurAt = chain.indexOf("<feGaussianBlur");
  const dropAt = chain.indexOf("<feDropShadow");
  assert.ok(blurAt !== -1 && dropAt !== -1, chain);
  assert.ok(blurAt < dropAt, "feGaussianBlur must precede feDropShadow");
  assert.match(chain, /<feGaussianBlur in="SourceGraphic" stdDeviation="5" result="blurred"\/>/);
  assert.match(chain, /<feDropShadow in="blurred" dx="3" dy="4" stdDeviation="8"/);
  // One `filter` attribute on the element, never two.
  const el = /<circle [^>]*\/>/.exec(svg)[0];
  assert.equal([...el.matchAll(/ filter=/g)].length, 1, el);
});

test("a shadow with no blur ahead of it emits exactly the element v2 emitted — no `in`", () => {
  const { svg } = toSvg([
    "draw protocol 3",
    "draw shadow 3 4 8 0.2 0.1 40",
    "draw fill 0.5 0.1 0 1",
    "draw circle 50 50 10",
  ], DIMENSIONS);
  assert.match(svg, /<feDropShadow dx="3" dy="4" stdDeviation="8"/);
  assert.doesNotMatch(svg, /<feGaussianBlur/);
});

// ---- 2: blur first, clip second ------------------------------------------

test("canvas clips the blurred mark: the clip is established and the filter is still in force when it paints", () => {
  const factory = fakeOffscreenFactory();
  const ctx = fakeCtx();
  paint(ctx, [
    "draw protocol 3",
    "draw blur 6",
    "draw fill 0.5 0.1 0 1",
    "draw stroke 0.2 0.1 0 1",
    "draw clip",
    "draw rect 10 10 40 40 0",
    "draw circle 30 30 25",
    "draw unclip",
  ], { ...DIMENSIONS, offscreenCanvas: factory });
  assert.equal(only(ctx, "clip").length, 1, "the region was established once");
  // Both the region-defining rect and the mark inside it reach the canvas
  // through the composite, with the blur in force — the clip constrains the
  // blurred result, it does not turn the blur off. The clip is set up on the
  // real context before the composited mark lands on it, which is what makes
  // the order "blur, then clip".
  const composites = only(ctx, "drawImage");
  assert.equal(composites.length, 2, "the rect and the circle both composited");
  for (const c of composites) assert.equal(c.filter, "blur(6px)");
  const clipAt = ctx.calls.findIndex((c) => c.name === "clip");
  const firstComposite = ctx.calls.findIndex((c) => c.name === "drawImage");
  assert.ok(clipAt !== -1 && clipAt < firstComposite, "the region is in force before anything is composited into it");
});

test("SVG states its filter region in user units, wide enough that a clip cannot crop the blur first", () => {
  const { svg, errors } = toSvg([
    "draw protocol 3",
    "draw blur 6",
    "draw fill 0.5 0.1 0 1",
    "draw clip",
    "draw rect 10 10 40 40 0",
    "draw circle 30 30 25",
    "draw unclip",
  ], DIMENSIONS);
  assert.deepEqual(errors, []);
  const m = /<filter id="[^"]+" filterUnits="userSpaceOnUse" x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"/.exec(svg);
  assert.ok(m, `no userSpaceOnUse filter region found in:\n${svg}`);
  const [, x, y, w, h] = m.map(Number);
  // NOT a percentage of the element's own bounding box: a 25-pixel circle and
  // a 2-pixel firefly must get the same room to spread into.
  assert.ok(x <= -DIMENSIONS.width && y <= -DIMENSIONS.height, `region origin ${x},${y}`);
  assert.ok(w >= DIMENSIONS.width * 3 && h >= DIMENSIONS.height * 3, `region size ${w}x${h}`);
  // The blurred element sits INSIDE the clip group — filter on the element,
  // clip-path on the enclosing <g> — which is what makes the order "blur,
  // then clip" rather than the other way round.
  const gAt = svg.indexOf('<g clip-path=');
  const circleAt = svg.indexOf("<circle");
  assert.ok(gAt !== -1 && gAt < circleAt, "the clip group opens before the mark it constrains");
  assert.match(svg.slice(circleAt), /^<circle [^>]*filter="url\(#[^"]+\)"/);
});

// ---- 3: a mark casts exactly one blur ------------------------------------

test("fill AND stroke visible with a blur set: the offscreen composite runs, and the offscreen is never itself blurred", () => {
  const factory = fakeOffscreenFactory();
  const ctx = fakeCtx();
  paint(ctx, [
    "draw protocol 3",
    "draw blur 4",
    "draw fill 0.5 0.1 0 1",
    "draw stroke 0.2 0.1 0 1",
    "draw circle 50 50 10",
  ], { ...DIMENSIONS, offscreenCanvas: factory });

  assert.equal(factory.created.length, 1, "one offscreen canvas, allocated on first need");
  const off = factory.created[0].ctx;
  // The mark is painted ONCE onto the offscreen, un-blurred...
  assert.equal(off.filter, "none", "the offscreen is never given a filter");
  for (const c of off.calls) assert.equal(c.filter, "none", `${c.name} was blurred on the offscreen`);
  assert.equal(only(off, "fill").length, 1);
  assert.equal(only(off, "stroke").length, 1);
  // ...and blurred once, on the way onto the real canvas.
  const [composite] = only(ctx, "drawImage");
  assert.ok(composite, "the composited mark reached the main canvas");
  assert.equal(composite.filter, "blur(4px)");
  // And it is NOT also filled/stroked directly — that would be the double
  // blur this whole path exists to prevent.
  assert.equal(only(ctx, "fill").length, 0);
  assert.equal(only(ctx, "stroke").length, 0);
});

test("blur with only one of fill/stroke visible takes the cheap path — one paint is already one blur", () => {
  const factory = fakeOffscreenFactory();
  const ctx = fakeCtx();
  paint(ctx, [
    "draw protocol 3",
    "draw blur 4",
    "draw fill 0.5 0.1 0 1",
    "draw stroke 0 0 0 0",
    "draw circle 50 50 10",
  ], { ...DIMENSIONS, offscreenCanvas: factory });
  assert.equal(factory.created.length, 0, "nothing allocated when there is nothing to composite");
  assert.equal(only(ctx, "drawImage").length, 0);
  assert.equal(only(ctx, "fill")[0].filter, "blur(4px)");
});

test("SVG blurs a filled-and-stroked mark once by construction: one element, one filter", () => {
  const { svg } = toSvg([
    "draw protocol 3",
    "draw blur 4",
    "draw fill 0.5 0.1 0 1",
    "draw stroke 0.2 0.1 0 1",
    "draw circle 50 50 10",
  ], DIMENSIONS);
  assert.equal([...svg.matchAll(/<circle /g)].length, 1);
  assert.equal([...svg.matchAll(/<feGaussianBlur/g)].length, 1);
});

// ---- the blur radius scales with the backing store, exactly as shadow does -

test("blur is multiplied by `scale`, so a supersampled export softens by the same amount relative to the picture", () => {
  for (const scale of [1, 2, 4]) {
    const ctx = fakeCtx();
    paint(ctx, [
      "draw protocol 3", "draw blur 7", "draw fill 0.5 0.1 0 1",
      "draw stroke 0 0 0 0", "draw circle 50 50 10",
    ], { ...DIMENSIONS, scale });
    assert.equal(only(ctx, "fill")[0].filter, `blur(${7 * scale}px)`);
  }
});

test("blur 0 writes `none`, not `blur(0px)` — a zero-radius filter still puts the context on the filtered path", () => {
  const ctx = fakeCtx();
  paint(ctx, [
    "draw protocol 3", "draw blur 7", "draw blur 0",
    "draw fill 0.5 0.1 0 1", "draw stroke 0 0 0 0", "draw circle 50 50 10",
  ], DIMENSIONS);
  assert.equal(only(ctx, "fill")[0].filter, "none");
});

test("background and clear are not softened by a blur in force, in either sink", () => {
  const ctx = fakeCtx();
  paint(ctx, [
    "draw protocol 3", "draw blur 9", "draw background 0.9 0.02 95", "draw clear",
  ], DIMENSIONS);
  for (const c of only(ctx, "fillRect")) assert.equal(c.filter, "none");
  // svg.mjs's background rect carries no filter attribute at all, which is
  // what the canvas side is being held to.
  const { svg } = toSvg([
    "draw protocol 3", "draw blur 9", "draw background 0.9 0.02 95",
  ], DIMENSIONS);
  const bg = /<rect x="0" y="0"[^>]*\/>/.exec(svg)[0];
  assert.doesNotMatch(bg, /filter=/);
});
