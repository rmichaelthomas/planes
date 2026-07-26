// js/test/interp.test.mjs — pure-JS unit tests for the interpreter.
//
// The exhaustive cross-check against interp.py is test_js_interp.py; these are
// JS-side smoke tests over the load-bearing behaviours: exact arithmetic,
// records and lists, provenance (why), and the effect boundary via a TestHost.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { loadGrammar } from "../loader_node.mjs";
import { Interpreter, fmt } from "../interp.mjs";
import { TestHost } from "../host.mjs";

loadGrammar();

function run(src, opts = {}) {
  const itp = new Interpreter(opts);
  itp.run(src);
  return itp;
}

test("arithmetic stays exact — 0.1 + 0.2 is 0.3", () => {
  const itp = run('show text of (0.1 + 0.2)', { host: new TestHost() });
  assert.deepEqual(itp.output, ["0.3"]);
});

test("1 / 3 renders as a visible approximation", () => {
  const itp = run("show text of (1 / 3)", { host: new TestHost() });
  assert.deepEqual(itp.output, ["~0.333333333333"]);
});

test("records and field access and count", () => {
  const itp = run(
    'p = { name: "ada", tags: [1, 2, 3] }\nshow p.name\nshow text of count of p.tags\n',
    { host: new TestHost() },
  );
  assert.deepEqual(itp.output, ["ada", "3"]);
});

test("count of text counts code points, not UTF-16 units", () => {
  const itp = run('show text of count of "a😀b"', { host: new TestHost() });
  assert.deepEqual(itp.output, ["3"]);
});

test("why reports the arithmetic that happened", () => {
  const itp = run("x = 5\ny = 3\nz = x + y\nwhy z\n", { host: new TestHost() });
  assert.deepEqual(itp.output, ["8 from x (5) + y (3)"]);
});

test("the write effect goes through the host as indented JSON", () => {
  const host = new TestHost();
  run('use file\nwrite [1, 2] to "o.json"', { host });
  assert.equal(host.files["o.json"], "[\n  1,\n  2\n]");
});

test("a cross-type comparison refuses rather than answers", () => {
  const host = new TestHost();
  const itp = new Interpreter({ host });
  assert.throws(() => itp.run('z = 5 == "5"'), (e) => e.tag === "cannot-compare");
});

test("fmt renders each type distinctly", () => {
  assert.equal(fmt(true), "true");
  assert.equal(fmt(null), "nothing");
  assert.equal(fmt("s"), "s");
  assert.equal(fmt([1, 2]), "[2 items]");
});
