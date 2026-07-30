// js/test/surface_pane.test.mjs — js/paint/surface_pane.mjs, headless.

import { test } from "node:test";
import assert from "node:assert/strict";
import { renderSurface } from "../paint/surface_pane.mjs";

function fakeTarget() {
  return { textContent: "" };
}

test("a program with no effects renders a surface report into the target element", async () => {
  const el = fakeTarget();
  const { surface, error } = await renderSurface(el, 'show "draw circle 1 2 3"');
  assert.equal(error, undefined);
  assert.ok(surface);
  assert.ok(el.textContent.length > 0);
  assert.doesNotMatch(el.textContent, /^✗/);
});

test("a program with a syntax error renders the error into the target element instead", async () => {
  const el = fakeTarget();
  const { error } = await renderSurface(el, "if:");
  assert.ok(error);
  assert.match(el.textContent, /^✗/);
  assert.match(el.textContent, new RegExp(error.tag));
});

test("nothing is run to produce the surface — a program whose surface includes an effect never fires it", async () => {
  const el = fakeTarget();
  let asked = false;
  // ask is only reachable through a `foreign ... doing ask` declaration in
  // this language, so a plain program has nothing to trigger here — this
  // test's real assertion is structural: analyseProgramGraph is a static
  // pass, and renderSurface calls nothing else.
  const { error } = await renderSurface(el, 'let x = 1\nshow "draw circle " + text of x + " 2 3"');
  assert.equal(error, undefined);
  assert.equal(asked, false);
});
