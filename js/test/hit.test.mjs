// js/test/hit.test.mjs — the mark recorder and the hit test, headless.
//
// Both modules are pure arithmetic over numbers: no DOM, no canvas, no
// Path2D. That is the point of them being separate from the painter, and it
// is what lets every claim below be checked by multiplying three matrices by
// hand rather than by stepping through drawing code.

import { test } from "node:test";
import assert from "node:assert/strict";

import { walk } from "../paint/stream.mjs";
import { markSink, multiply, applyMatrix, translation, rotation, scaling } from "../paint/marks.mjs";
import { hitTest, containsPoint, invert, marksForLine, outlineOf } from "../paint/hit.mjs";

function record(lines) {
  const sink = markSink();
  const result = walk(lines, sink);
  return { marks: sink.marks, ...result };
}

// ---- the walk names the line -------------------------------------------------

test("every mark carries the index of the stream line that drew it", () => {
  const { marks } = record([
    "draw protocol 2",
    "draw fill 0.5 0.1 200 1",
    "draw circle 10 10 5",
    "this line is prose",
    "draw circle 30 30 5",
  ]);
  assert.equal(marks.length, 2);
  assert.equal(marks[0].line, 2);
  assert.equal(marks[1].line, 4);
});

test("the index counts prose and errors too — it is a line number, not a mark number", () => {
  const { marks } = record(["prose", "draw fill 0 0 0 1", "draw circle 1 1 1"]);
  assert.equal(marks[0].line, 2);
});

test("a sink with no `at` method still walks — every existing sink inherits a no-op", () => {
  const calls = [];
  const bare = new Proxy(
    {},
    {
      get: (_t, name) => (name === "at" ? undefined : (...args) => calls.push([name, ...args])),
    },
  );
  const { errors } = walk(["draw circle 1 2 3"], bare);
  assert.deepEqual(errors, []);
  assert.ok(calls.some(([name]) => name === "circle"));
});

// ---- the matrix stack --------------------------------------------------------

test("push and pop restore the transform exactly", () => {
  const { marks } = record([
    "draw fill 0 0 0 1",
    "draw push",
    "draw translate 100 50",
    "draw circle 0 0 5",
    "draw pop",
    "draw circle 0 0 5",
  ]);
  assert.deepEqual(marks[0].matrix, [1, 0, 0, 1, 100, 50]);
  assert.deepEqual(marks[1].matrix, [1, 0, 0, 1, 0, 0]);
});

test("translate then rotate rotates about the translated origin, not the canvas origin", () => {
  const { marks } = record([
    "draw fill 0 0 0 1",
    "draw translate 100 100",
    "draw rotate 90",
    "draw circle 10 0 2",
  ]);
  const [x, y] = applyMatrix(marks[0].matrix, 10, 0);
  // 90 degrees clockwise as pictured (y down): (10, 0) becomes (0, 10).
  assert.ok(Math.abs(x - 100) < 1e-9, `x was ${x}`);
  assert.ok(Math.abs(y - 110) < 1e-9, `y was ${y}`);
});

test("inverting a composed matrix returns the point it started from", () => {
  const m = multiply(multiply(translation(37, -12), rotation(23)), scaling(1.5, 0.5));
  const [fx, fy] = applyMatrix(m, 8, 19);
  const [bx, by] = applyMatrix(invert(m), fx, fy);
  assert.ok(Math.abs(bx - 8) < 1e-9);
  assert.ok(Math.abs(by - 19) < 1e-9);
});

test("a singular matrix has no interior and is skipped rather than throwing", () => {
  const { marks } = record(["draw fill 0 0 0 1", "draw scale 0 1", "draw circle 10 10 5"]);
  assert.equal(invert(marks[0].matrix), null);
  assert.equal(hitTest(marks, 10, 10), -1);
});

// ---- the tilted leaf ---------------------------------------------------------
//
// The case a naive implementation gets wrong: a rotated ellipse under
// push/translate/scale carries BOTH its own rotation (about its own centre,
// §6.2) and an enclosing CTM, and the two compose in an order that matters.

test("a tilted leaf's recorded matrix maps its tip to the expected point", () => {
  const { marks } = record([
    "draw fill 0.5 0.1 140 1",
    "draw push",
    "draw translate 200 150",
    "draw scale 2 2",
    "draw ellipse 0 0 10 3 90",
    "draw pop",
  ]);
  const leaf = marks[0];
  // The ellipse is 10 long, turned 90 degrees about its own centre, so its
  // tip sits at local (0, 10) — down, because positive degrees turn clockwise
  // as pictured and y increases downward. The CTM then scales by 2 and
  // translates by (200, 150): (200, 170).
  const tipLocal = [0, 10];
  const [tx, ty] = applyMatrix(leaf.matrix, ...tipLocal);
  assert.ok(Math.abs(tx - 200) < 1e-9, `tip x was ${tx}`);
  assert.ok(Math.abs(ty - 170) < 1e-9, `tip y was ${ty}`);

  // And the hit test agrees: the tip is inside the leaf, and the point the
  // UNROTATED ellipse would have reached — 10 units along x, so (220, 150) —
  // is outside it.
  assert.equal(hitTest(marks, 200, 168, { slack: 0 }), 0);
  assert.equal(hitTest(marks, 219, 150, { slack: 0 }), -1);
});

test("hit testing an ellipse honours its own rotation argument", () => {
  const { marks } = record(["draw fill 0 0 0 1", "draw ellipse 100 100 40 6 0"]);
  const { marks: turned } = record(["draw fill 0 0 0 1", "draw ellipse 100 100 40 6 90"]);
  assert.equal(hitTest(marks, 135, 100, { slack: 0 }), 0);
  assert.equal(hitTest(marks, 100, 135, { slack: 0 }), -1);
  assert.equal(hitTest(turned, 135, 100, { slack: 0 }), -1);
  assert.equal(hitTest(turned, 100, 135, { slack: 0 }), 0);
});

// ---- topmost wins ------------------------------------------------------------

test("the topmost mark wins — the list is walked backward", () => {
  const { marks } = record([
    "draw fill 0 0 0 1",
    "draw circle 100 100 50",
    "draw circle 100 100 10",
  ]);
  assert.equal(hitTest(marks, 100, 100), 1);
  assert.equal(hitTest(marks, 100, 140), 0);
});

test("an invisible mark is not clickable — what is under it is", () => {
  const { marks } = record([
    "draw fill 0.5 0.1 200 1",
    "draw circle 100 100 50",
    "draw fill 0 0 0 0",
    "draw stroke 0 0 0 0",
    "draw circle 100 100 10",
  ]);
  assert.equal(marks.length, 2);
  assert.equal(marks[1].visible, false);
  assert.equal(hitTest(marks, 100, 100), 0);
});

test("alpha zero makes a mark unclickable too", () => {
  const { marks } = record([
    "draw protocol 2",
    "draw fill 0.5 0.1 200 1",
    "draw alpha 0",
    "draw circle 100 100 20",
  ]);
  assert.equal(marks[0].visible, false);
});

test("a gradient fill counts as visible even though no fill alpha was set", () => {
  const { marks } = record([
    "draw protocol 2",
    "draw fill 0 0 0 0",
    "draw gradient linear 0 0 10 10 0.5 0.1 200 1 0.8 0.1 60 1",
    "draw rect 0 0 50 50 0",
  ]);
  assert.equal(marks[0].visible, true);
});

// ---- every shape kind --------------------------------------------------------

test("each shape kind answers a point inside and a point outside", () => {
  const cases = [
    ["draw circle 50 50 20", [50, 50], [50, 90]],
    ["draw ellipse 50 50 20 5 0", [60, 50], [50, 70]],
    ["draw rect 10 10 40 20 0", [30, 20], [80, 20]],
    ["draw triangle 0 0 40 0 20 40", [20, 10], [39, 39]],
    ["draw line 0 0 100 100", [50, 50], [10, 80]],
  ];
  for (const [line, inside, outside] of cases) {
    const { marks } = record(["draw fill 0.4 0.1 200 1", line]);
    assert.equal(hitTest(marks, ...inside, { slack: 1 }), 0, `${line} inside`);
    assert.equal(hitTest(marks, ...outside, { slack: 1 }), -1, `${line} outside`);
  }
});

test("a path is hit along its own outline, and inside it when it is filled", () => {
  const { marks } = record([
    "draw fill 0.4 0.1 200 1",
    "draw shape",
    "draw vertex 10 10",
    "draw vertex 90 10",
    "draw vertex 50 90",
    "draw close",
    "draw end",
  ]);
  assert.equal(marks.length, 1);
  assert.equal(marks[0].kind, "path");
  assert.equal(hitTest(marks, 50, 30, { slack: 0 }), 0);
  assert.equal(hitTest(marks, 5, 80, { slack: 0 }), -1);
});

test("a curve in a path is followed, not treated as a straight line", () => {
  const { marks } = record([
    "draw fill 0 0 0 0",
    "draw stroke 0.2 0.1 200 1",
    "draw shape",
    "draw vertex 0 100",
    "draw curve 0 0 100 0 100 100",
    "draw end",
  ]);
  // The cubic bulges upward to about y = 25 at its midpoint; a straight line
  // between the endpoints would sit flat at y = 100.
  assert.equal(hitTest(marks, 50, 25, { slack: 4 }), 0);
  assert.equal(hitTest(marks, 50, 100, { slack: 4 }), -1);
});

// ---- background wipes the hit list too ---------------------------------------

test("`clear` empties the hit list, exactly as it empties the canvas", () => {
  const { marks } = record([
    "draw fill 0 0 0 1",
    "draw circle 10 10 5",
    "draw clear",
    "draw circle 40 40 5",
  ]);
  assert.equal(marks.length, 1);
  assert.equal(marks[0].line, 3);
});

// ---- the map, read backwards -------------------------------------------------

test("marksForLine finds every mark one source line drew", () => {
  const { marks } = record([
    "draw fill 0 0 0 1",
    "draw circle 10 10 5",
    "draw circle 20 20 5",
  ]);
  assert.deepEqual(marksForLine(marks, 1), [0]);
  assert.deepEqual(marksForLine(marks, 2), [1]);
  assert.deepEqual(marksForLine(marks, 99), []);
});

test("an outline comes back in drawing-area coordinates, through the mark's matrix", () => {
  const { marks } = record([
    "draw fill 0 0 0 1",
    "draw push",
    "draw translate 100 100",
    "draw rect 0 0 20 10 0",
    "draw pop",
  ]);
  const pts = outlineOf(marks[0]);
  assert.equal(pts.length, 4);
  for (const [x, y] of pts) {
    assert.ok(x >= 99 && x <= 121, `x ${x} is in the translated box`);
    assert.ok(y >= 99 && y <= 111, `y ${y} is in the translated box`);
  }
});

// ---- containsPoint is the tested primitive -----------------------------------

test("containsPoint widens a stroke-only mark by half its own width", () => {
  const mark = { kind: "line", geometry: { x1: 0, y1: 0, x2: 100, y2: 0 }, filled: false, strokeWidth: 20 };
  assert.equal(containsPoint(mark, 50, 9, 0), true);
  assert.equal(containsPoint(mark, 50, 11, 0), false);
});
