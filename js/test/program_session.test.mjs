// js/test/program_session.test.mjs — js/paint/program_session.mjs, headless.
//
// Runs against paint/garden.planes for real (the fetch stub reads straight
// off disk, the same pattern paint_examples.test.mjs and
// paint_conformance.test.mjs already use) so this exercises the real
// module-loader wiring, not a fake of it.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createProgramSession } from "../paint/program_session.mjs";

const PAINT_DIR = fileURLToPath(new URL("../../paint/", import.meta.url));

function installFsFetch() {
  const real = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const p = typeof url === "string" && !url.startsWith("file:") ? path_from_relative(url) : fileURLToPath(url);
    if (!fs.existsSync(p)) return { ok: false, status: 404, text: async () => "" };
    return { ok: true, text: async () => fs.readFileSync(p, "utf-8") };
  };
  return () => {
    if (real) globalThis.fetch = real;
    else delete globalThis.fetch;
  };
}
function path_from_relative(url) {
  // program_session.mjs fetches `${file}?v=${cacheBust}` — a relative path
  // plus a query string, not a full URL — so this resolves it the same way
  // a browser would against window.location.href.
  const clean = url.split("?")[0];
  return fileURLToPath(new URL(clean, pathToFileURL(PAINT_DIR + "index.html")));
}

function installWindow() {
  const real = globalThis.window;
  globalThis.window = { location: { href: pathToFileURL(PAINT_DIR + "index.html").href } };
  return () => {
    if (real) globalThis.window = real;
    else delete globalThis.window;
  };
}

test("load() fetches the source and runAt() runs it at a given tick with no error", async () => {
  const restoreFetch = installFsFetch();
  const restoreWindow = installWindow();
  try {
    const session = createProgramSession({ file: "garden.planes", cacheBust: "t1" });
    const src = await session.load();
    assert.match(src, /paint\/garden\.planes/);
    const result = await session.runAt(30, 0);
    assert.equal(result.error, null);
    assert.ok(result.lines.length > 0);
    assert.ok(result.lines[0].includes("draw protocol 3"));
  } finally {
    restoreWindow();
    restoreFetch();
  }
});

test("runAt() with the same tick and seed is deterministic — repeated calls agree", async () => {
  const restoreFetch = installFsFetch();
  const restoreWindow = installWindow();
  try {
    const session = createProgramSession({ file: "garden.planes", cacheBust: "t2" });
    await session.load();
    const a = await session.runAt(30, 733);
    const b = await session.runAt(5, 733);
    const c = await session.runAt(30, 733);
    assert.deepEqual(a.lines, c.lines, "returning to day 30 reproduces the exact same stream");
    assert.notDeepEqual(a.lines, b.lines);
  } finally {
    restoreWindow();
    restoreFetch();
  }
});

test("runAt() with a different seed at the same tick produces a different stream", async () => {
  const restoreFetch = installFsFetch();
  const restoreWindow = installWindow();
  try {
    const session = createProgramSession({ file: "garden.planes", cacheBust: "t3" });
    await session.load();
    const seedA = await session.runAt(60, 733);
    const seedB = await session.runAt(60, 42);
    assert.notDeepEqual(seedA.lines, seedB.lines);
  } finally {
    restoreWindow();
    restoreFetch();
  }
});

test("runAt() auto-loads if called before load()", async () => {
  const restoreFetch = installFsFetch();
  const restoreWindow = installWindow();
  try {
    const session = createProgramSession({ file: "garden.planes", cacheBust: "t4" });
    const result = await session.runAt(10, 0);
    assert.equal(result.error, null);
  } finally {
    restoreWindow();
    restoreFetch();
  }
});

test("loadedModules() reports the file-backed modules garden.planes uses", async () => {
  const restoreFetch = installFsFetch();
  const restoreWindow = installWindow();
  try {
    const session = createProgramSession({ file: "garden.planes", cacheBust: "t5" });
    await session.load();
    await session.runAt(0, 0);
    const names = session.loadedModules().map((m) => m.name);
    assert.ok(names.includes("draw"));
    assert.ok(names.includes("math"));
  } finally {
    restoreWindow();
    restoreFetch();
  }
});

test("a fresh session for a second load() gets a new loader (one loader per run)", async () => {
  const restoreFetch = installFsFetch();
  const restoreWindow = installWindow();
  try {
    const session = createProgramSession({ file: "garden.planes", cacheBust: "t6" });
    await session.load();
    const loaderA = session.getLoader();
    await session.load();
    const loaderB = session.getLoader();
    assert.notEqual(loaderA, loaderB);
  } finally {
    restoreWindow();
    restoreFetch();
  }
});
