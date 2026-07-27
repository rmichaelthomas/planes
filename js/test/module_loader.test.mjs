// js/test/module_loader.test.mjs — the two module loaders, headless.
//
// modules.mjs is pure; every host-bound operation comes from a loader. This
// covers module_loader_browser.mjs directly against a stubbed global fetch
// (resolution, per-run caching, cycle detection, collision detection, and
// message equality with module_loader_node.mjs's real-filesystem behaviour),
// plus module_loader_node.mjs itself against real temp files.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  load_graph,
  check_collisions,
  resolve,
  ModuleError,
} from "../modules.mjs";
import { createNodeModuleLoader } from "../module_loader_node.mjs";
import { BrowserModuleLoader } from "../module_loader_browser.mjs";
import { loadGrammar } from "../loader_node.mjs";

loadGrammar();

function tempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "planes-module-loader-"));
}

function writeFile(dir, name, text) {
  const p = path.join(dir, name);
  fs.writeFileSync(p, text, "utf-8");
  return p;
}

// ---- module_loader_node.mjs -------------------------------------------------

test("node loader: locate resolves relative to the importing file's directory", () => {
  const dir = tempDir();
  writeFile(dir, "main.planes", "use util\n");
  writeFile(dir, "util.planes", 'to helper of x:\n  give x\n');
  const loader = createNodeModuleLoader();
  const mainPath = path.join(dir, "main.planes");
  const located = loader.locate("util", mainPath);
  assert.equal(located, path.join(dir, "util.planes"));
});

test("node loader: locate throws a named error for a missing module", () => {
  const dir = tempDir();
  const mainPath = writeFile(dir, "main.planes", "use nope\n");
  const loader = createNodeModuleLoader();
  assert.throws(
    () => loader.locate("nope", mainPath),
    (e) => e instanceof ModuleError && /no module named 'nope'/.test(e.message),
  );
});

test("node loader: load_graph orders imports before importers and detects a cycle", async () => {
  const dir = tempDir();
  writeFile(dir, "a.planes", "use b\nto from-a of x:\n  give x\n");
  writeFile(dir, "b.planes", "use a\nto from-b of x:\n  give x\n");
  const loader = createNodeModuleLoader();
  await assert.rejects(
    load_graph(loader, path.join(dir, "a.planes")),
    (e) => e instanceof ModuleError && /module cycle/.test(e.message),
  );
});

test("node loader: check_collisions names both files when two define the same function", async () => {
  const dir = tempDir();
  writeFile(dir, "main.planes", "use a\nuse b\n");
  writeFile(dir, "a.planes", "to shared of x:\n  give x\n");
  writeFile(dir, "b.planes", "to shared of x:\n  give x + 1\n");
  const loader = createNodeModuleLoader();
  const graph = await load_graph(loader, path.join(dir, "main.planes"));
  assert.throws(
    () => check_collisions(graph, loader),
    (e) => e instanceof ModuleError && /'shared' is defined in a\.planes, b\.planes/.test(e.message),
  );
});

// ---- module_loader_browser.mjs ---------------------------------------------

function stubFetch(files) {
  return async (url) => {
    const key = String(url);
    if (Object.prototype.hasOwnProperty.call(files, key)) {
      return { ok: true, text: async () => files[key] };
    }
    return { ok: false, text: async () => "" };
  };
}

test("browser loader: locate resolves relative to fromLocation, or to base when absent", () => {
  const loader = new BrowserModuleLoader({ base: "https://example.test/paint/main.planes" });
  assert.equal(loader.locate("draw", null), "https://example.test/paint/draw.planes");
  assert.equal(
    loader.locate("util", "https://example.test/paint/sub/child.planes"),
    "https://example.test/paint/sub/util.planes",
  );
});

test("browser loader: read fetches once and caches for the life of the loader", async () => {
  let calls = 0;
  const base = "https://example.test/paint/main.planes";
  const files = { "https://example.test/paint/util.planes": "to helper of x:\n  give x\n" };
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    calls += 1;
    return stubFetch(files)(url);
  };
  try {
    const loader = new BrowserModuleLoader({ base });
    const loc = loader.locate("util", null);
    const first = await loader.read(loc);
    const second = await loader.read(loc);
    assert.equal(first, files["https://example.test/paint/util.planes"]);
    assert.equal(second, first);
    assert.equal(calls, 1, "a second read of an already-cached location issues no fetch");
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("browser loader: a failed fetch raises the same 'no module named' message Node raises", async () => {
  const base = "https://example.test/paint/main.planes";
  const realFetch = globalThis.fetch;
  globalThis.fetch = stubFetch({});
  try {
    const browserLoader = new BrowserModuleLoader({ base });
    const loc = browserLoader.locate("nope", null);
    await assert.rejects(
      browserLoader.read(loc),
      (e) => e instanceof ModuleError && /no module named 'nope'/.test(e.message),
    );

    // The node loader's message for the identically-named missing module.
    const dir = tempDir();
    const mainPath = writeFile(dir, "main.planes", "use nope\n");
    const nodeLoader = createNodeModuleLoader();
    let nodeMessage = null;
    try {
      nodeLoader.locate("nope", mainPath);
    } catch (e) {
      nodeMessage = e.message;
    }
    let browserMessage = null;
    try {
      await browserLoader.read(loc);
    } catch (e) {
      browserMessage = e.message;
    }
    assert.equal(browserMessage, nodeMessage, "the fix clause and message text match byte for byte");
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("browser loader: load_graph orders imports before importers and detects a cycle", async () => {
  const base = "https://example.test/paint/main.planes";
  const files = {
    "https://example.test/paint/a.planes": "use b\nto from-a of x:\n  give x\n",
    "https://example.test/paint/b.planes": "use a\nto from-b of x:\n  give x\n",
  };
  const realFetch = globalThis.fetch;
  globalThis.fetch = stubFetch(files);
  try {
    const loader = new BrowserModuleLoader({ base });
    const loc = loader.locate("a", null);
    await assert.rejects(
      load_graph(loader, loc),
      (e) => e instanceof ModuleError && /module cycle/.test(e.message),
    );
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("browser loader: check_collisions names both files when two define the same function", async () => {
  const base = "https://example.test/paint/main.planes";
  const files = {
    "https://example.test/paint/a.planes": "to shared of x:\n  give x\n",
    "https://example.test/paint/b.planes": "to shared of x:\n  give x + 1\n",
  };
  const realFetch = globalThis.fetch;
  globalThis.fetch = stubFetch(files);
  try {
    const loader = new BrowserModuleLoader({ base });
    const aGraph = await load_graph(loader, loader.locate("a", null));
    const bGraph = await load_graph(loader, loader.locate("b", null));
    const graph = [...aGraph, ...bGraph];
    assert.throws(
      () => check_collisions(graph, loader),
      (e) => e instanceof ModuleError && /'shared' is defined in a\.planes, b\.planes/.test(e.message),
    );
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("browser loader: resolve returns null for a builtin module without locating it", () => {
  const loader = new BrowserModuleLoader({ base: "https://example.test/paint/main.planes" });
  assert.equal(resolve(loader, "file", null), null);
  assert.equal(resolve(loader, "http", null), null);
});

test("browser loader: readIfCached and loadedModules reflect only real fetches, not lookups", async () => {
  const base = "https://example.test/paint/main.planes";
  const files = { "https://example.test/paint/util.planes": "to helper of x:\n  give x\n" };
  const realFetch = globalThis.fetch;
  globalThis.fetch = stubFetch(files);
  try {
    const loader = new BrowserModuleLoader({ base });
    const loc = loader.locate("util", null);
    assert.equal(loader.readIfCached(loc), undefined);
    await loader.read(loc);
    assert.equal(loader.readIfCached(loc), files["https://example.test/paint/util.planes"]);
    assert.deepEqual(
      loader.loadedModules().map((m) => m.name),
      ["util"],
    );
  } finally {
    globalThis.fetch = realFetch;
  }
});
