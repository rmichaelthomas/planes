// js/test/host.test.mjs — pure-JS unit tests for the host seam.
//
// The cross-implementation agreement against host.py lives in test_js_host.py.
// This file covers the two methods that are cleanest to check JS-side: show
// (emits a line) and the hermetic TestHost stubs (ask/read/write/clock), the
// analogue of host.py's TestHost that makes the agreement suite hermetic.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { Host, NodeHost, TestHost, HostError } from "../host.mjs";

test("the abstract host throws on every effect until implemented", () => {
  const h = new Host();
  for (const m of ["ask", "read", "write", "show", "clock", "resolve",
    "parseJson", "toJson"]) {
    assert.throws(() => h[m]("x", "y"), HostError, m);
  }
  // record is the optional no-op, not one of the eight — it must not throw.
  assert.doesNotThrow(() => h.record({ a: 1 }));
});

test("TestHost captures show output rather than printing it", () => {
  const h = new TestHost();
  h.show("one");
  h.show("two");
  assert.deepEqual(h.shown, ["one", "two"]);
});

test("TestHost serves stubbed responses and files, and stubs the clock", () => {
  const h = new TestHost({
    responses: { "https://x/y.json": '{"n": 1}' },
    files: { "in.json": "hello" },
    now: 42.0,
  });
  assert.equal(h.ask("https://x/y.json"), '{"n": 1}');
  assert.equal(h.read("in.json"), "hello");
  assert.equal(h.clock(), 42.0);
  h.write("o.json", "[1, 2]");
  assert.equal(h.files["o.json"], "[1, 2]");
});

test("TestHost raises HostError for an unstubbed response or missing file", () => {
  const h = new TestHost();
  assert.throws(() => h.ask("https://nope/x"), HostError);
  assert.throws(() => h.read("gone.json"), HostError);
});

test("TestHost inherits resolve and the JSON boundary from NodeHost", () => {
  const h = new TestHost();
  assert.deepEqual(h.resolve("builtins.sorted")([3, 1, 2]), [1, 2, 3]);
  assert.equal(h.toJson([1, 2]), "[\n  1,\n  2\n]");
  assert.deepEqual(h.parseJson('{"n": 1}'), { n: 1 });
});

test("NodeHost.show writes a line to stdout", () => {
  // Exercise the real path without capturing stdout: it must not throw and
  // must append a newline (checked via a spy on process.stdout.write).
  const h = new NodeHost();
  const written = [];
  const orig = process.stdout.write;
  process.stdout.write = (s) => {
    written.push(s);
    return true;
  };
  try {
    h.show("line");
  } finally {
    process.stdout.write = orig;
  }
  assert.deepEqual(written, ["line\n"]);
});
