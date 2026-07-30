// js/test/gradient_stops.test.mjs — the gradient stop computation
// (planes-drawing-protocol-v2.md §5.1, normative), headless.
//
// stream.mjs computes a gradient's sixteen OKLCH stops once, in degree space,
// and hands the SAME list to both sinks — this is what makes an OKLCH
// gradient actually an OKLCH gradient (canvas's addColorStop and SVG's
// <stop> both interpolate in sRGB, so if either sink computed its own
// stops, it would silently NOT be interpolating in OKLCH at all). These
// tests hold the computation itself, and the fact that both sinks are fed
// from it rather than each deriving their own.

import { test } from "node:test";
import assert from "node:assert/strict";
import { gradientStops } from "../paint/stream.mjs";
import { paint } from "../paint/painter.mjs";
import { toSvg } from "../paint/svg.mjs";
import { rgbHex } from "../paint/color.mjs";

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
    save: record("save"), restore: record("restore"), clip: record("clip"),
    drawImage: record("drawImage"), clearRect: record("clearRect"),
    setLineDash() {}, getLineDash() { return []; },
    createLinearGradient(...args) {
      calls.push(["createLinearGradient", ...args]);
      const stops = [];
      calls.push(["__stopsRef", stops]);
      return { addColorStop: (offset, color) => stops.push([offset, color]) };
    },
    createRadialGradient(...args) {
      calls.push(["createRadialGradient", ...args]);
      const stops = [];
      calls.push(["__stopsRef", stops]);
      return { addColorStop: (offset, color) => stops.push([offset, color]) };
    },
    getTransform() { return transform; },
    setTransform(t) { transform = t; },
    resetTransform() { transform = "identity"; },
  };
}

// ---- gradientStops itself ----------------------------------------------

test("sixteen stops, offsets 0, 1/15, ..., 1", () => {
  const stops = gradientStops(0.2, 0.05, 10, 1, 0.8, 0.15, 40, 1);
  assert.equal(stops.length, 16);
  assert.equal(stops[0].offset, 0);
  assert.equal(stops[15].offset, 1);
  for (let i = 0; i < 16; i++) {
    assert.ok(Math.abs(stops[i].offset - i / 15) < 1e-12, `stop ${i} offset`);
  }
});

test("L, C and A interpolate linearly between the two endpoints", () => {
  const stops = gradientStops(0.2, 0.1, 0, 0, 0.8, 0.3, 0, 1);
  for (let i = 0; i < 16; i++) {
    const t = i / 15;
    assert.ok(Math.abs(stops[i].L - (0.2 + (0.8 - 0.2) * t)) < 1e-9);
    assert.ok(Math.abs(stops[i].C - (0.1 + (0.3 - 0.1) * t)) < 1e-9);
    assert.ok(Math.abs(stops[i].A - (0 + (1 - 0) * t)) < 1e-9);
  }
});

test("endpoints are exact: stop 0 is the first colour, stop 15 is the second", () => {
  const stops = gradientStops(0.3, 0.12, 210, 0.6, 0.7, 0.2, 40, 0.9);
  assert.deepEqual([stops[0].L, stops[0].C, stops[0].H, stops[0].A], [0.3, 0.12, 210, 0.6]);
  assert.deepEqual([stops[15].L, stops[15].C, stops[15].H, stops[15].A], [0.7, 0.2, 40, 0.9]);
});

test("hue from 350 to 10 sweeps FORWARD 20 degrees through 0, never backward 340", () => {
  const stops = gradientStops(0.5, 0.1, 350, 1, 0.5, 0.1, 10, 1);
  // Monotonic forward progress: each stop's hue, unwrapped, is >= the last.
  let unwrapped = stops[0].H;
  let prevWrapped = stops[0].H;
  for (let i = 1; i < stops.length; i++) {
    let delta = stops[i].H - prevWrapped;
    if (delta < -180) delta += 360;
    unwrapped += delta;
    prevWrapped = stops[i].H;
  }
  assert.ok(Math.abs(unwrapped - 370) < 1e-6, `swept ${unwrapped - 350} degrees, expected 20`);
  assert.equal(stops[0].H, 350);
  assert.ok(Math.abs(stops[15].H - 10) < 1e-9);
  // The midpoint crosses 0, not sitting at (350+10)/2 = 180 (the long way).
  const mid = stops[7];
  assert.ok(mid.H > 355 || mid.H < 5, `midpoint hue ${mid.H} is not near the 0 crossing`);
});

test("hue wraps into [0, 360) at every stop", () => {
  const stops = gradientStops(0.5, 0.1, 10, 1, 0.5, 0.1, 350, 1);
  for (const s of stops) {
    assert.ok(s.H >= 0 && s.H < 360, `H=${s.H} out of range`);
  }
});

test("an ordinary same-direction hue sweep (say 100 to 200) is just linear, no wrap needed", () => {
  const stops = gradientStops(0.5, 0.1, 100, 1, 0.5, 0.1, 200, 1);
  for (let i = 0; i < 16; i++) {
    const t = i / 15;
    assert.ok(Math.abs(stops[i].H - (100 + 100 * t)) < 1e-9);
  }
});

// ---- both sinks are fed the identical list ------------------------------

const LINEAR = ["draw protocol 2", "draw gradient linear 0 0 100 0  0.9 0.05 90 1  0.4 0.1 260 1"];

test("canvas's addColorStop calls match stream.mjs's own computed stops exactly", () => {
  const ctx = fakeCtx();
  paint(ctx, LINEAR, DIMENSIONS);
  const stopsRef = ctx.calls.find((c) => c[0] === "__stopsRef")[1];
  const expected = gradientStops(0.9, 0.05, 90, 1, 0.4, 0.1, 260, 1);
  assert.equal(stopsRef.length, 16);
  for (let i = 0; i < 16; i++) {
    const [offset, color] = stopsRef[i];
    assert.ok(Math.abs(offset - expected[i].offset) < 1e-9);
    const m = /rgba\((\d+), (\d+), (\d+), ([\d.]+)\)/.exec(color);
    assert.ok(m, `not an rgba() string: ${color}`);
    assert.ok(Math.abs(Number(m[4]) - expected[i].A) < 1e-9, `stop ${i} alpha`);
  }
});

test("SVG's <stop> elements match stream.mjs's own computed stops exactly", () => {
  const { svg } = toSvg(LINEAR, DIMENSIONS);
  const expected = gradientStops(0.9, 0.05, 90, 1, 0.4, 0.1, 260, 1);
  const stopEls = [...svg.matchAll(/<stop offset="([\d.]+)" stop-color="(#[0-9a-f]{6})" stop-opacity="([\d.]+)"\/>/g)];
  assert.equal(stopEls.length, 16);
  for (let i = 0; i < 16; i++) {
    const [, offset, color, opacity] = stopEls[i];
    assert.ok(Math.abs(Number(offset) - expected[i].offset) < 1e-6, `stop ${i} offset`);
    assert.equal(color, rgbHex(expected[i].L, expected[i].C, expected[i].H));
    assert.ok(Math.abs(Number(opacity) - expected[i].A) < 1e-6, `stop ${i} opacity`);
  }
});

test("canvas and SVG resolve the identical sRGB at every stop — one computation, two consumers", () => {
  const ctx = fakeCtx();
  paint(ctx, LINEAR, DIMENSIONS);
  const stopsRef = ctx.calls.find((c) => c[0] === "__stopsRef")[1];
  const { svg } = toSvg(LINEAR, DIMENSIONS);
  const svgColors = [...svg.matchAll(/stop-color="(#[0-9a-f]{6})"/g)].map((m) => m[1]);
  const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  for (let i = 0; i < 16; i++) {
    const [, color] = stopsRef[i];
    const m = /rgba\((\d+), (\d+), (\d+),/.exec(color);
    const fromCanvas = [Number(m[1]), Number(m[2]), Number(m[3])];
    const fromSvg = hexToRgb(svgColors[i]);
    assert.deepEqual(fromCanvas, fromSvg, `stop ${i}`);
  }
});

// ---- dedup: a gradient emitted twice produces one def -------------------

test("a gradient emitted twice (identical arguments) produces one def, referenced twice", () => {
  const gradientLine = LINEAR[1];
  const lines = [
    ...LINEAR,
    "draw rect 0 0 10 10 0",
    gradientLine,
    "draw circle 50 50 5",
  ];
  const { svg, errors } = toSvg(lines, DIMENSIONS);
  assert.deepEqual(errors, []);
  assert.equal((svg.match(/<linearGradient/g) || []).length, 1, "one def, not two");
  assert.equal((svg.match(/fill="url\(#p-gradient-1\)"/g) || []).length, 2, "two references to it");
});

test("two DIFFERENT gradients produce two distinct defs", () => {
  const other = "draw gradient linear 0 0 100 0  0.9 0.05 90 1  0.4 0.1 261 1";
  const lines = [...LINEAR, "draw rect 0 0 1 1 0", other, "draw rect 1 1 1 1 0"];
  const { svg, errors } = toSvg(lines, DIMENSIONS);
  assert.deepEqual(errors, []);
  assert.equal((svg.match(/<linearGradient/g) || []).length, 2);
  assert.match(svg, /id="p-gradient-1"/);
  assert.match(svg, /id="p-gradient-2"/);
});

test("radial and linear gradients get independent, correctly-shaped defs", () => {
  const radial = ["draw protocol 2", "draw gradient radial 50 50 40  0.9 0.05 90 1  0.4 0.1 260 1"];
  const { svg, errors } = toSvg(radial, DIMENSIONS);
  assert.deepEqual(errors, []);
  assert.match(svg, /<radialGradient id="p-gradient-1" gradientUnits="userSpaceOnUse" cx="50" cy="50" r="40">/);
});
