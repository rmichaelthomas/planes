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

// B1 (Sprint B): a kind change on an unchanged destination is significant,
// even though newDestinations() alone misses it (the target is not new) —
// must agree with shapes.py's changed_kinds() and Rules.swift's Swift twin.
test("diff of a pure ask-to-send kind change is significant", () => {
  const before = analyse('foreign x from "m.post" doing ask "https://a.example.com"\nr = x\n');
  const after = analyse('foreign x from "m.post" doing send "https://a.example.com"\nr = x\n');
  const d = diff(before, after);
  assert.ok(!d.isEmpty());
  assert.deepEqual(d.newDestinations(), []);
  assert.equal(d.newBoundaries.length, 0);
  assert.ok(d.isSignificant());
  assert.match(d.render(), /KIND CHANGED: https:\/\/a\.example\.com \(ask -> send\)/);
});

test("diff kind change does not confuse different boundaries", () => {
  const before = analyse('use http\nx = ask "same-name"\n');
  const after = analyse('show "same-name"\n');
  const d = diff(before, after);
  assert.deepEqual(d.changedKinds(), []);
});

// B1: a foreign literally named after an effect kind (matches shapes.py's
// mirrored fix and test). Checking K.has(node.name) before the foreigns
// table would double-count the call site as a second, bare ambient/builtin
// effect on top of the one the foreign's own `doing` clause declares.
test("a foreign literally named send is not double-counted", () => {
  const s = analyse(
    'foreign send of payload from "mylib.post" doing send "https://api.example.com/events"\n' +
      "to report of data:\n  give send of data\n\nr = report of 1\n",
  );
  assert.equal(s.declared.length, 1);
  assert.equal(s.declared[0].kind, "send");
  assert.equal(s.declared[0].target, "https://api.example.com/events");
});

test("a foreign named clock is also not double-counted", () => {
  const s = analyse('foreign clock of x from "m.f" doing read "file.txt"\nr = clock of 1\n');
  assert.equal(s.declared.length, 1);
  assert.equal(s.declared[0].kind, "read");
  assert.equal(s.declared[0].target, "file.txt");
});
