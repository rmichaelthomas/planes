// js/test/browser.test.mjs — the browser engine, headless.
//
// runProgram() in browser_main.mjs is the deliverable's engine, pure of the
// DOM: it loads the grammar as JSON modules (the real grammar/*.json, no copy)
// and runs a program against the in-memory BrowserHost. Testing it under Node
// exercises the exact code path index.html runs in a browser — everything but
// the DOM rendering — so a green run here is strong evidence the page works.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { runProgram } from "../browser_main.mjs";

test("the browser engine runs a program and returns its output", () => {
  const r = runProgram('show "hello from the browser"\nshow text of (0.1 + 0.2)');
  assert.equal(r.error, null);
  assert.deepEqual(r.output, ["hello from the browser", "0.3"]);
});

test("exact arithmetic and why work in the browser engine", () => {
  const r = runProgram("x = 5\ny = 3\nz = x * y + 2\nwhy z");
  assert.equal(r.error, null);
  assert.deepEqual(r.output, ["17 from x (5) * y (3) + 2"]);
});

test("a program error is reported, not thrown", () => {
  const r = runProgram('z = 5 + "x"');
  assert.equal(r.error.tag, "cannot-combine");
});

test("the browser VFS seeds files and captures writes", () => {
  const r = runProgram(
    'use file\nc = read "in.txt"\nshow c\nwrite [1, 2] to "out.json"',
    { files: { "in.txt": "seeded" } },
  );
  assert.equal(r.error, null);
  assert.deepEqual(r.output, ["seeded"]);
  assert.equal(r.files["out.json"], "[\n  1,\n  2\n]");
});

test("the sample program in index.html runs clean", () => {
  // The exact sample the page ships with — a regression guard on the demo.
  const sample = [
    'price = 0.1 + 0.2',
    'show "0.1 + 0.2 = " + text of price',
    'third = 1 / 3',
    'show "1 / 3   = " + text of third',
    'readings = [23, 8, 41, 15, 4]',
    'show "readings: " + text of count of readings + " values"',
    'x = 5',
    'y = 3',
    'z = x * y + 2',
    'why z',
  ].join("\n");
  const r = runProgram(sample);
  assert.equal(r.error, null);
  assert.deepEqual(r.output, [
    "0.1 + 0.2 = 0.3",
    "1 / 3   = ~0.333333333333",
    "readings: 5 values",
    "17 from x (5) * y (3) + 2",
  ]);
});
