// js/test/shapes.test.mjs — pure-JS unit tests for the analyser (Phase 2).
//
// The cross-implementation agreement against shapes.py lives in test_js_shapes.py
// and test_js_shapes_derivation.py. This file covers the JS side directly: the
// library-is-not-pure distinction, totality on a partially-resolvable program,
// the computed-target host survival, and diff detecting a new boundary.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { loadGrammar } from "../loader_node.mjs";
import { analyse, diff } from "../shapes.mjs";

loadGrammar();

test("a genuinely pure program is pure", () => {
  const s = analyse("to add of a, b:\n  give a + b\n\nr = add of 2, 3");
  assert.ok(s.isPure());
  assert.equal(s.render().startsWith("pure"), true);
});

test("a library is not pure — its network call lives one function deep", () => {
  const s = analyse("use http\nto get of url:\n  give ask url");
  assert.deepEqual(s.effects, []); // nothing runs at load
  assert.ok(!s.isPure());
  assert.ok(s.isLibrary());
  assert.ok(s.touches("network"));
});

test("the analyser is total on a partially-resolvable program", () => {
  // A call to a function that does not exist must not throw.
  let s;
  assert.doesNotThrow(() => {
    s = analyse("r = mystery of 1");
  });
  assert.ok(s.unresolved.length > 0);
});

test("an undeclared foreign contributes unknown, not a raise", () => {
  const s = analyse('foreign x of a from "m.f"\nr = x of 1');
  assert.ok(s.hasUnknowns());
});

test("a computed target keeps the host visible", () => {
  const s = analyse(
    'use http\nto f of n:\n' +
      '  give ask "https://example.com/item/" + text of n + ".json"\n\n' +
      "xs = for each i in [1, 2]: f of i",
  );
  const e = s.at("network")[0];
  assert.ok(e.computed);
  assert.ok(e.target.includes("https://example.com/item/"));
  assert.ok(e.target.includes("{...}"));
});

test("diff detects a new network boundary", () => {
  const before = analyse('use file\nwrite [1] to "out.json"');
  const after = analyse(
    'use file\nuse http\nx = ask "https://tracker.example.com/collect"\n' +
      'write [1] to "out.json"',
  );
  const d = diff(before, after);
  assert.ok(!d.isEmpty());
  assert.ok(d.newBoundaries.includes("network"));
});
