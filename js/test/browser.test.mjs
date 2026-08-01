// js/test/browser.test.mjs — the browser engine, headless.
//
// runProgram() in browser_main.mjs is the deliverable's engine, pure of the
// DOM: it loads the grammar as JSON modules (the real grammar/*.json, no copy)
// and runs a program against the in-memory BrowserHost. Testing it under Node
// exercises the exact code path try.html runs in a browser — everything but
// the DOM rendering — so a green run here is strong evidence the page works.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { runProgram, analyseProgram, surfaceReport } from "../browser_main.mjs";

// The exact program the page ships with, read from try.html — so these tests
// guard the real demo, not a copy that can drift. (It was index.html until the
// demo moved there and index became the hub; the hub carries no program.)
function pageSample() {
  const html = fileURLToPath(new URL("../../try.html", import.meta.url));
  const src = fs.readFileSync(html, "utf-8");
  return src.split('<textarea id="source" spellcheck="false">')[1].split("</textarea>")[0];
}

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

test("the sample program in try.html runs clean and performs no network send", () => {
  // A regression guard on the actual demo: it must run without error, and the
  // ask hidden behind `fetch` must NOT execute at the top level.
  const r = runProgram(pageSample());
  assert.equal(r.error, null);
  assert.deepEqual(r.output, [
    "0.1 + 0.2 = 0.3",
    "wrote 5 readings to readings.json",
  ]);
  assert.ok(!r.effects.some((e) => e[0] === "ask"), "no network send runs");
  assert.equal(r.files["readings.json"] !== undefined, true);
});

// ================================================================ the effect surface (A.5)

test("analyseProgram reports the surface WITHOUT running the program", () => {
  // A program whose only effect is a network send that would throw if run
  // (no stubbed response) — the surface must still see it, proving nothing ran.
  const src = 'use http\nx = ask "https://example.com/a.json"\n';
  const { surface, error } = analyseProgram(src);
  assert.equal(error, null);
  assert.ok(surface.touches("network"));
  assert.deepEqual(surface.targets("ask"), ["https://example.com/a.json"]);
});

test("the surface sees a network reach hidden behind an uncalled function", () => {
  // The page's whole point: running the sample sends nothing, but the surface
  // sees fetch's ask.
  const { surface } = analyseProgram(pageSample());
  assert.ok(surface.touches("network"), "surface sees the hidden ask");
  assert.ok(surface.touches("file"), "and the file write");
  assert.ok(surface.touches("console"), "and the shows");
  const report = surfaceReport(surface);
  assert.match(report, /network:/);
  assert.match(report, /why → derives from: url/); // why shipped
});

test("analyseProgram reports a syntax error, not throws", () => {
  const { surface, error } = analyseProgram("x = = 5\n");
  assert.equal(surface, null);
  assert.equal(error.tag, "syntax");
});
