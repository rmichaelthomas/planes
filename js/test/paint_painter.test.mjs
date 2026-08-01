// js/test/paint_painter.test.mjs — the painter (planes-drawing-protocol-v1.md
// §§4-8, normative), headless.
//
// paint() is a pure function of (ctx, lines, dimensions): it reads no globals
// and no DOM beyond the context handed to it, so a fake context recording the
// calls made against it is enough to test it without a real <canvas>.
// `getTransform`/`setTransform` are tracked separately from `calls` (a simple
// string-tagged snapshot, not a real matrix) since push/pop/background/clear
// use them as bookkeeping rather than visible drawing operations.

import { test } from "node:test";
import assert from "node:assert/strict";
import { paint, oklchToRgb } from "../paint/painter.mjs";
import { FONT_FAMILY } from "../paint/stream.mjs";

function fakeCtx() {
  const calls = [];
  const record = (name) => (...args) => calls.push([name, ...args]);
  let transform = "identity";
  return {
    calls,
    strokeStyle: null,
    fillStyle: null,
    lineWidth: null,
    lineCap: null,
    lineJoin: null,
    font: null,
    textAlign: null,
    beginPath: record("beginPath"),
    moveTo: record("moveTo"),
    lineTo: record("lineTo"),
    arc: record("arc"),
    ellipse: record("ellipse"),
    rect: record("rect"),
    closePath: record("closePath"),
    bezierCurveTo: record("bezierCurveTo"),
    stroke: record("stroke"),
    fill: record("fill"),
    fillRect: record("fillRect"),
    fillText: record("fillText"),
    translate(x, y) {
      transform = `${transform}>translate(${x},${y})`;
      calls.push(["translate", x, y]);
    },
    rotate(rad) {
      transform = `${transform}>rotate(${rad})`;
      calls.push(["rotate", rad]);
    },
    scale(sx, sy) {
      transform = `${transform}>scale(${sx},${sy})`;
      calls.push(["scale", sx, sy]);
    },
    getTransform() {
      return transform;
    },
    // setTransform is recorded — it is how pop's behaviour is observable
    // from outside (paint() always leaves the transform at identity on
    // return, so the post-call value alone can't distinguish a correct pop
    // from a no-op one; the value it was called with can).
    setTransform(t) {
      transform = t;
      calls.push(["setTransform", t]);
    },
    // resetTransform is bookkeeping (the reset table and the exit guarantee
    // both use it) — not a verb's own call, so not recorded.
    resetTransform() {
      transform = "identity";
    },
    save: record("save"),
    restore: record("restore"),
    clip: record("clip"),
    drawImage: record("drawImage"),
    clearRect: record("clearRect"),
    createLinearGradient(...args) {
      calls.push(["createLinearGradient", ...args]);
      return { addColorStop: (...a) => calls.push(["addColorStop", ...a]) };
    },
    createRadialGradient(...args) {
      calls.push(["createRadialGradient", ...args]);
      return { addColorStop: (...a) => calls.push(["addColorStop", ...a]) };
    },
    // Bookkeeping, like resetTransform above — not itself a verb's own
    // call, so not recorded into `calls`; dash's own tests read it back.
    setLineDash(d) {
      this._lineDash = d;
    },
    getLineDash() {
      return this._lineDash || [];
    },
  };
}

const DIMENSIONS = { width: 100, height: 100, background: "#fff" };

// ---- reset table (specification §5) ----------------------------------------

test("the reset table is applied at the start of every call", () => {
  const ctx = fakeCtx();
  paint(ctx, [], DIMENSIONS);
  assert.equal(ctx.strokeStyle, "rgba(0, 0, 0, 1)");
  assert.equal(ctx.fillStyle, "rgba(0, 0, 0, 0)");
  assert.equal(ctx.lineWidth, 1);
  assert.equal(ctx.lineCap, "butt");
  assert.equal(ctx.lineJoin, "miter");
  assert.equal(ctx.textAlign, "left");
});

test("state set by one call does not leak into the next", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw stroke 0.6 0.2 210 1", "draw width 9", "draw cap round", "draw align right"], DIMENSIONS);
  assert.equal(ctx.lineWidth, 9);
  assert.equal(ctx.lineCap, "round");
  assert.equal(ctx.textAlign, "right");

  const result = paint(ctx, [], DIMENSIONS);
  assert.equal(ctx.strokeStyle, "rgba(0, 0, 0, 1)");
  assert.equal(ctx.lineWidth, 1);
  assert.equal(ctx.lineCap, "butt");
  assert.equal(ctx.textAlign, "left");
  assert.deepEqual(result.errors, []);
});

test("the transform is identity both before and after every call, even one that rotates", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw translate 50 50", "draw rotate 90"], DIMENSIONS);
  // paint() restores identity on its own exit (asserted directly below), which
  // is what guarantees the *next* call also starts clean — there is no
  // separate "leftover rotation" state to observe from outside a call.
  assert.equal(ctx.getTransform(), "identity");
  paint(ctx, [], DIMENSIONS);
  assert.equal(ctx.getTransform(), "identity");
});

// ---- each verb's context calls ----------------------------------------------

test("stroke sets strokeStyle from OKLCH", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw stroke 1 0 0 1"], DIMENSIONS);
  assert.equal(ctx.strokeStyle, "rgba(255, 255, 255, 1)");
});

test("fill sets fillStyle from OKLCH with alpha", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw fill 0.5 0 0 0.5"], DIMENSIONS);
  assert.equal(ctx.fillStyle, "rgba(99, 99, 99, 0.5)");
});

test("width sets lineWidth", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw width 4"], DIMENSIONS);
  assert.equal(ctx.lineWidth, 4);
});

test("cap and corner set lineCap/lineJoin verbatim", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw cap square", "draw corner bevel"], DIMENSIONS);
  assert.equal(ctx.lineCap, "square");
  assert.equal(ctx.lineJoin, "bevel");
});

test("line draws a single segment, filled then stroked", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw line 1 2 3 4"], DIMENSIONS);
  assert.deepEqual(ctx.calls, [
    ["beginPath"],
    ["moveTo", 1, 2],
    ["lineTo", 3, 4],
    ["fill"],
    ["stroke"],
  ]);
});

test("rect draws x y w h, filled then stroked", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw rect 1 2 3 4"], DIMENSIONS);
  assert.deepEqual(ctx.calls, [["beginPath"], ["rect", 1, 2, 3, 4], ["fill"], ["stroke"]]);
});

test("circle takes a radius, filled then stroked", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw circle 10 20 5"], DIMENSIONS);
  assert.deepEqual(ctx.calls, [
    ["beginPath"],
    ["arc", 10, 20, 5, 0, 2 * Math.PI],
    ["fill"],
    ["stroke"],
  ]);
});

test("ellipse takes rx and ry, filled then stroked", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw ellipse 10 20 5 8"], DIMENSIONS);
  assert.deepEqual(ctx.calls, [
    ["beginPath"],
    ["ellipse", 10, 20, 5, 8, 0, 0, 2 * Math.PI],
    ["fill"],
    ["stroke"],
  ]);
});

test("triangle closes back to its first point, filled then stroked", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw triangle 0 0 10 0 5 10"], DIMENSIONS);
  assert.deepEqual(ctx.calls, [
    ["beginPath"],
    ["moveTo", 0, 0],
    ["lineTo", 10, 0],
    ["lineTo", 5, 10],
    ["closePath"],
    ["fill"],
    ["stroke"],
  ]);
});

test("push saves the transform only, pop restores it", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["draw translate 10 0", "draw push", "draw rotate 90", "draw pop"], DIMENSIONS);
  assert.deepEqual(result.errors, []);
  // paint() itself always resets to identity on return (asserted elsewhere),
  // so pop's own effect is only observable in the setTransform call it made
  // — restoring exactly the state push captured, before the rotate.
  const setTransformCalls = ctx.calls.filter((c) => c[0] === "setTransform");
  assert.equal(setTransformCalls.length, 1, "pop makes exactly one setTransform call");
  assert.equal(setTransformCalls[0][1], "identity>translate(10,0)");
});

test("push/pop does not touch colour, width, cap, corner, size or align", () => {
  const ctx = fakeCtx();
  paint(
    ctx,
    [
      "draw stroke 0.9 0 0 1",
      "draw width 7",
      "draw push",
      "draw stroke 0 0 0 1",
      "draw width 1",
      "draw pop",
    ],
    DIMENSIONS,
  );
  // pop restored the transform, but stroke/width are whatever was last set —
  // push never captured them, so they are NOT rolled back.
  assert.equal(ctx.strokeStyle, "rgba(0, 0, 0, 1)");
  assert.equal(ctx.lineWidth, 1);
});

test("translate/rotate/scale call through with degrees converted to radians", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw translate 5 6", "draw rotate 90", "draw scale 2 -1"], DIMENSIONS);
  assert.deepEqual(ctx.calls, [
    ["translate", 5, 6],
    ["rotate", Math.PI / 2],
    ["scale", 2, -1],
  ]);
});

test("label draws text at x, y with the current fill", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw fill 0 0 0 1", "draw label 5 10 score: 42 points"], DIMENSIONS);
  assert.deepEqual(ctx.calls.filter((c) => c[0] === "fillText"), [
    ["fillText", "score: 42 points", 5, 10],
  ]);
});

test("size sets the font size in pixels", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw size 24"], DIMENSIONS);
  assert.equal(ctx.font, `24px ${FONT_FAMILY}`);
});

test("align sets textAlign verbatim", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw align center"], DIMENSIONS);
  assert.equal(ctx.textAlign, "center");
});

test("background fills the whole area immediately and becomes clear's target", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw background 1 0 0", "draw clear"], DIMENSIONS);
  const fillRects = ctx.calls.filter((c) => c[0] === "fillRect");
  assert.equal(fillRects.length, 2);
  assert.deepEqual(fillRects[0], ["fillRect", 0, 0, 100, 100]);
  assert.deepEqual(fillRects[1], ["fillRect", 0, 0, 100, 100]);
});

test("clear with no prior background falls back to the dimensions option", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw clear"], DIMENSIONS);
  const fillRect = ctx.calls.find((c) => c[0] === "fillRect");
  assert.ok(fillRect);
  assert.equal(ctx.fillStyle, "rgba(0, 0, 0, 0)", "clear does not permanently change fillStyle");
});

// ---- OKLCH conversion --------------------------------------------------------

test("oklchToRgb: white, black and an achromatic mid-grey", () => {
  assert.deepEqual(oklchToRgb(1, 0, 0).map((c) => Math.round(c * 255)), [255, 255, 255]);
  assert.deepEqual(oklchToRgb(0, 0, 0).map((c) => Math.round(c * 255)), [0, 0, 0]);
  const grey = oklchToRgb(0.5, 0, 0).map((c) => Math.round(c * 255));
  assert.deepEqual(grey, [99, 99, 99]);
  assert.equal(grey[0], grey[1]);
  assert.equal(grey[1], grey[2]);
});

test("oklchToRgb: an unclamped saturated colour matches its computed reference", () => {
  const teal = oklchToRgb(0.7, 0.1, 200).map((c) => Math.round(c * 255));
  assert.deepEqual(teal, [64, 177, 183]);
  const orange = oklchToRgb(0.75, 0.12, 60).map((c) => Math.round(c * 255));
  assert.deepEqual(orange, [229, 155, 91]);
});

test("oklchToRgb: an out-of-gamut request clamps each channel independently, silently", () => {
  const [r, g, b] = oklchToRgb(1, 0.5, 0);
  // Every channel lands in [0, 1] — nothing NaN, nothing out of range — and
  // this request (L=1, high chroma) is genuinely out of gamut: it clamps to
  // a value distinct from plain white, which is what "silently" means (no
  // error, no flag — just a computed, in-range pixel).
  for (const c of [r, g, b]) {
    assert.ok(c >= 0 && c <= 1);
  }
  assert.deepEqual([r, g, b].map((c) => Math.round(c * 255)), [255, 0, 241]);
});

// ---- arc direction and the wrap rule (specification §7) --------------------

test("arc converts degrees to radians directly (0 at positive x, clockwise)", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw arc 50 50 20 0 90"], DIMENSIONS);
  const call = ctx.calls.find((c) => c[0] === "arc");
  assert.deepEqual(call, ["arc", 50, 50, 20, 0, Math.PI / 2, false]);
});

test("arc wraps end by adding 360 until it exceeds start", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw arc 50 50 20 300 10"], DIMENSIONS);
  const call = ctx.calls.find((c) => c[0] === "arc");
  // end=10 <= start=300, so end becomes 370.
  assert.deepEqual(call, ["arc", 50, 50, 20, (300 * Math.PI) / 180, (370 * Math.PI) / 180, false]);
});

test("arc with end exactly equal to start wraps a full circle", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw arc 50 50 20 45 45"], DIMENSIONS);
  const call = ctx.calls.find((c) => c[0] === "arc");
  assert.deepEqual(call, ["arc", 50, 50, 20, (45 * Math.PI) / 180, (405 * Math.PI) / 180, false]);
});

test("an arc is filled then stroked but never closed to the centre", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw arc 50 50 20 0 90"], DIMENSIONS);
  assert.deepEqual(
    ctx.calls.map((c) => c[0]),
    ["beginPath", "arc", "fill", "stroke"],
  );
  assert.ok(!ctx.calls.some((c) => c[0] === "lineTo"), "no line to the centre is ever added");
});

// ---- path lifecycle: all four path errors -----------------------------------

test("vertex/curve/close outside a shape are path-not-open", () => {
  for (const line of ["draw vertex 1 1", "draw curve 1 1 2 2 3 3", "draw close"]) {
    const ctx = fakeCtx();
    const result = paint(ctx, [line], DIMENSIONS);
    assert.equal(result.errors.length, 1);
    assert.equal(result.errors[0].tag, "path-not-open");
    assert.equal(result.drawn, 0);
  }
});

test("end without a preceding shape is path-not-open", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["draw end"], DIMENSIONS);
  assert.equal(result.errors.length, 1);
  assert.equal(result.errors[0].tag, "path-not-open");
});

test("shape while one is already open is path-already-open", () => {
  const ctx = fakeCtx();
  // The redundant `shape` is ignored (its own error recorded) rather than
  // reopening the path, so `end` still closes the original one cleanly —
  // otherwise this stream would also report path-unclosed, muddying the
  // assertion this test is actually making.
  const result = paint(ctx, ["draw shape", "draw vertex 0 0", "draw shape", "draw end"], DIMENSIONS);
  assert.equal(result.errors.length, 1);
  assert.equal(result.errors[0].tag, "path-already-open");
});

test("a shape still open at the end of the stream is path-unclosed", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["draw shape", "draw vertex 0 0", "draw vertex 10 10"], DIMENSIONS);
  assert.equal(result.errors.length, 1);
  assert.equal(result.errors[0].tag, "path-unclosed");
});

test("a full shape/vertex/curve/close/end lifecycle draws and closes cleanly", () => {
  const ctx = fakeCtx();
  const result = paint(
    ctx,
    ["draw shape", "draw vertex 100 100", "draw vertex 160 140", "draw curve 10 10 20 20 120 200", "draw close", "draw end"],
    DIMENSIONS,
  );
  assert.deepEqual(result.errors, []);
  assert.deepEqual(ctx.calls, [
    ["beginPath"],
    ["moveTo", 100, 100],
    ["lineTo", 160, 140],
    ["bezierCurveTo", 10, 10, 20, 20, 120, 200],
    ["closePath"],
    ["fill"],
    ["stroke"],
  ]);
});

// ---- transform save/restore: both unmatched errors --------------------------

test("pop without a matching push is unmatched-pop", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["draw pop"], DIMENSIONS);
  assert.equal(result.errors.length, 1);
  assert.equal(result.errors[0].tag, "unmatched-pop");
});

test("a push still unmatched at the end of the stream is unmatched-push", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["draw push", "draw rotate 10"], DIMENSIONS);
  assert.equal(result.errors.length, 1);
  assert.equal(result.errors[0].tag, "unmatched-push");
});

test("the transform is restored on return even after an unmatched push", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw push", "draw rotate 45"], DIMENSIONS);
  paint(ctx, [], DIMENSIONS);
  assert.equal(ctx.getTransform(), "identity", "a later call is not left rotated by the earlier one");
});

// ---- the protocol version declaration ----------------------------------------

test("an absent protocol declaration behaves as version 1", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["draw circle 10 10 5"], DIMENSIONS);
  assert.deepEqual(result.errors, []);
  assert.equal(result.drawn, 1);
});

test("draw protocol 1 as the first line is accepted and does not itself draw", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["draw protocol 1", "draw circle 10 10 5"], DIMENSIONS);
  assert.deepEqual(result.errors, []);
  assert.equal(result.drawn, 1, "protocol itself is not a drawing command");
});

test("an unsupported version refuses the whole stream: nothing is drawn", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["draw protocol 4", "draw circle 10 10 5", "some prose"], DIMENSIONS);
  assert.equal(result.drawn, 0);
  assert.deepEqual(result.text, []);
  assert.equal(result.errors.length, 1);
  assert.equal(result.errors[0].tag, "unsupported-version");
  assert.deepEqual(ctx.calls, [], "no drawing method is ever called");
});

test("a second protocol declaration is protocol-repeated", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["draw protocol 1", "draw protocol 1"], DIMENSIONS);
  assert.equal(result.errors.length, 1);
  assert.equal(result.errors[0].tag, "protocol-repeated");
});

test("a protocol declaration after a drawing command is protocol-late", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["draw circle 10 10 5", "draw protocol 1"], DIMENSIONS);
  assert.equal(result.errors.length, 1);
  assert.equal(result.errors[0].tag, "protocol-late");
});

// ---- prose and errors from protocol.mjs pass through unchanged --------------

test("prose lines are collected as text, in order", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["draw circle 1 2 3", "hello", "world"], DIMENSIONS);
  assert.deepEqual(result.text, ["hello", "world"]);
});

test("a malformed draw line from protocol.mjs is reported, not drawn", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["draw circle 1 2"], DIMENSIONS);
  assert.equal(result.drawn, 0);
  assert.equal(result.errors.length, 1);
  assert.equal(result.errors[0].tag, "wrong-arity");
});
