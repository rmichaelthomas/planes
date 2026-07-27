// js/test/paint_painter.test.mjs — the painter (§1), headless.
//
// paint() is a pure function of (ctx, lines, dimensions): it reads no globals
// and no DOM beyond the context handed to it, so a fake context recording the
// calls made against it is enough to test it without a real <canvas>.

import { test } from "node:test";
import assert from "node:assert/strict";
import { paint } from "../paint/painter.mjs";

function fakeCtx() {
  const calls = [];
  const record = (name) => (...args) => calls.push([name, ...args]);
  return {
    calls,
    strokeStyle: null,
    fillStyle: null,
    lineWidth: null,
    beginPath: record("beginPath"),
    moveTo: record("moveTo"),
    lineTo: record("lineTo"),
    arc: record("arc"),
    stroke: record("stroke"),
    fill: record("fill"),
    strokeRect: record("strokeRect"),
    fillRect: record("fillRect"),
    fillText: record("fillText"),
  };
}

test("paint walks lines once, drawing recognised verbs and collecting the rest as text", () => {
  const ctx = fakeCtx();
  const lines = [
    "pen 1 0 0",
    "move 10 10",
    "line 20 20",
    "not a command",
    "circle 50 50 5",
    "dot 60 60 3",
    "rect 0 0 10 10",
    "box 5 5 10 10",
    "text 1 1 hello",
    "another stray line",
    "clear",
  ];
  const result = paint(ctx, lines, { width: 100, height: 100, background: "#fff" });
  assert.equal(result.drawn, 9);
  assert.deepEqual(result.text, ["not a command", "another stray line"]);
});

test("pen sets stroke and fill colour from 0-1 rgb", () => {
  const ctx = fakeCtx();
  paint(ctx, ["pen 1 0 0"], { width: 10, height: 10 });
  assert.equal(ctx.strokeStyle, "rgb(255, 0, 0)");
  assert.equal(ctx.fillStyle, "rgb(255, 0, 0)");
});

test("width sets lineWidth", () => {
  const ctx = fakeCtx();
  paint(ctx, ["width 4"], { width: 10, height: 10 });
  assert.equal(ctx.lineWidth, 4);
});

test("move sets the cursor without drawing", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["move 5 6"], { width: 10, height: 10 });
  assert.equal(result.drawn, 1);
  assert.equal(ctx.calls.length, 0);
});

test("line draws from the current cursor to the given point and updates the cursor", () => {
  const ctx = fakeCtx();
  paint(ctx, ["move 1 2", "line 3 4", "line 5 6"], { width: 10, height: 10 });
  assert.deepEqual(ctx.calls, [
    ["beginPath"],
    ["moveTo", 1, 2],
    ["lineTo", 3, 4],
    ["stroke"],
    ["beginPath"],
    ["moveTo", 3, 4],
    ["lineTo", 5, 6],
    ["stroke"],
  ]);
});

test("line with no prior move starts from the default cursor (0, 0)", () => {
  const ctx = fakeCtx();
  paint(ctx, ["line 9 9"], { width: 10, height: 10 });
  assert.deepEqual(ctx.calls, [
    ["beginPath"],
    ["moveTo", 0, 0],
    ["lineTo", 9, 9],
    ["stroke"],
  ]);
});

test("circle strokes an arc", () => {
  const ctx = fakeCtx();
  paint(ctx, ["circle 10 20 5"], { width: 100, height: 100 });
  assert.deepEqual(ctx.calls, [
    ["beginPath"],
    ["arc", 10, 20, 5, 0, 2 * Math.PI],
    ["stroke"],
  ]);
});

test("dot fills an arc", () => {
  const ctx = fakeCtx();
  paint(ctx, ["dot 10 20 5"], { width: 100, height: 100 });
  assert.deepEqual(ctx.calls, [
    ["beginPath"],
    ["arc", 10, 20, 5, 0, 2 * Math.PI],
    ["fill"],
  ]);
});

test("rect strokes a rectangle", () => {
  const ctx = fakeCtx();
  paint(ctx, ["rect 1 2 3 4"], { width: 100, height: 100 });
  assert.deepEqual(ctx.calls, [["strokeRect", 1, 2, 3, 4]]);
});

test("box fills a rectangle", () => {
  const ctx = fakeCtx();
  paint(ctx, ["box 1 2 3 4"], { width: 100, height: 100 });
  assert.deepEqual(ctx.calls, [["fillRect", 1, 2, 3, 4]]);
});

test("text draws the string at the point", () => {
  const ctx = fakeCtx();
  paint(ctx, ["text 5 10 score: 42 points"], { width: 100, height: 100 });
  assert.deepEqual(ctx.calls, [["fillText", "score: 42 points", 5, 10]]);
});

test("clear fills the canvas with the background colour", () => {
  const ctx = fakeCtx();
  paint(ctx, ["clear"], { width: 200, height: 150, background: "#123456" });
  assert.equal(ctx.fillStyle, "#123456");
  assert.deepEqual(ctx.calls, [["fillRect", 0, 0, 200, 150]]);
});

test("pen colour, width and cursor are local state reset on every call", () => {
  const ctx = fakeCtx();
  paint(ctx, ["pen 1 0 0", "width 9", "move 50 50"], { width: 10, height: 10 });
  // A fresh call with none of that state re-set starts from the defaults again.
  const calls = ctx.calls.length;
  paint(ctx, ["line 1 1"], { width: 10, height: 10 });
  assert.deepEqual(ctx.calls.slice(calls), [
    ["beginPath"],
    ["moveTo", 0, 0],
    ["lineTo", 1, 1],
    ["stroke"],
  ]);
  assert.equal(ctx.lineWidth, 1);
  assert.equal(ctx.strokeStyle, "rgb(0, 0, 0)");
});
