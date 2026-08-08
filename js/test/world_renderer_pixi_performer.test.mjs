// js/test/world_renderer_pixi_performer.test.mjs — Horizon Phase 1
// renderer pipeline: the pure, Pixi-free half of pixi_performer.mjs.
//
// mapWorldToScreen/colorForKind touch no Pixi object and no DOM, so they
// run directly under `node --test` (importing the module itself is also
// safe under Node — the vendored Pixi bundle has no top-level DOM access;
// see the build's own results report for how that was confirmed). Actual
// sprite/Graphics/Text rendering needs a real WebGL/Canvas context and is
// covered by this build's real-browser capture instead (see
// horizon-renderer-pipeline-results.md), not here.

import { test } from "node:test";
import assert from "node:assert/strict";
import { mapWorldToScreen, colorForKind } from "../world/performers/pixi_performer.mjs";

test("colorForKind is stable per kind and falls back to a default for an unknown kind", () => {
  const character = colorForKind("character");
  assert.equal(colorForKind("character"), character, "same kind, same color, every call");
  assert.notEqual(colorForKind("vehicle"), character);
  assert.equal(typeof colorForKind("nope-not-a-real-kind"), "number");
});

test("mapWorldToScreen wraps an unboundedly-drifting x into the viewport, never off-screen", () => {
  const viewport = { width: 1000, height: 600 };
  for (const x of [0, 5.999, 6, 11.999, 12, 13, 1000, 1000000.25]) {
    const { x: screenX } = mapWorldToScreen(x, 4, viewport);
    assert.ok(screenX >= 0 && screenX <= viewport.width, `x=${x} -> screenX=${screenX} out of viewport`);
  }
});

test("mapWorldToScreen is periodic in x with the same period the module documents (12 world units)", () => {
  const viewport = { width: 1000, height: 600 };
  const a = mapWorldToScreen(1.5, 4, viewport);
  const b = mapWorldToScreen(1.5 + 12, 4, viewport);
  const c = mapWorldToScreen(1.5 + 12 * 37, 4, viewport);
  assert.ok(Math.abs(a.x - b.x) < 1e-9);
  assert.ok(Math.abs(a.x - c.x) < 1e-9);
});

test("mapWorldToScreen amplifies y's tiny swing around the fixture's baseline (4) into a visible range", () => {
  const viewport = { width: 1000, height: 600 };
  const atBaseline = mapWorldToScreen(0, 4, viewport);
  const above = mapWorldToScreen(0, 4.02, viewport);
  const below = mapWorldToScreen(0, 3.98, viewport);
  assert.ok(Math.abs(above.y - atBaseline.y) > 5, "a 0.02-unit swing should be visually amplified, not sub-pixel");
  assert.ok(Math.abs(below.y - atBaseline.y) > 5);
  assert.ok(above.y < atBaseline.y, "larger y moves the sprite up the screen (smaller screen-y)");
  assert.ok(below.y > atBaseline.y, "smaller y moves the sprite down the screen (larger screen-y)");
});

test("mapWorldToScreen never divides by zero on a degenerate (zero) viewport", () => {
  assert.doesNotThrow(() => mapWorldToScreen(3, 4, { width: 0, height: 0 }));
  const { x, y } = mapWorldToScreen(3, 4, { width: 0, height: 0 });
  assert.ok(Number.isFinite(x) && Number.isFinite(y));
});
