// js/test/paint_dom_guard.test.mjs — the browser_main.mjs DOM guard (§2), headless.
//
// browser_main.mjs's DOM wiring now requires all four of #run/#surface/
// #source/#output to be present, not just `document` to exist — because
// paint.html imports runProgram/analyseProgram/surfaceReport from the same
// module under its own, different element ids, and must not trip index.html's
// wiring in the process. Each case imports the module fresh (a cache-busting
// query string forces a new module instance per Node's ESM loader) against a
// minimal stubbed `document`, so the guard's branch runs for real.

import { test } from "node:test";
import assert from "node:assert/strict";

function makeEl() {
  return { value: "", textContent: "", classList: { toggle() {} }, addEventListener() {} };
}

function stubDocument(presentIds) {
  const present = new Set(presentIds);
  return { getElementById: (id) => (present.has(id) ? makeEl() : null) };
}

let counter = 0;
function freshImport() {
  counter += 1;
  return import(`../browser_main.mjs?paint-dom-guard-case=${counter}`);
}

test("all four elements present: wiring runs and does not throw", async () => {
  globalThis.document = stubDocument(["run", "surface", "source", "output"]);
  try {
    await assert.doesNotReject(freshImport());
  } finally {
    delete globalThis.document;
  }
});

test("none of the four elements present (paint.html's own ids): import does not throw", async () => {
  globalThis.document = stubDocument(["paint-run", "paint-source", "paint-output"]);
  try {
    await assert.doesNotReject(freshImport());
  } finally {
    delete globalThis.document;
  }
});

test("only some of the four present: import does not throw (all-or-nothing guard)", async () => {
  globalThis.document = stubDocument(["run", "source"]);
  try {
    await assert.doesNotReject(freshImport());
  } finally {
    delete globalThis.document;
  }
});
