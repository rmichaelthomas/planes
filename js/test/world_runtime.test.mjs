// js/test/world_runtime.test.mjs — Horizon Phase 0 Build 2, Phases 2 and 3.
//
// Phase 2 (source maps): every emitted record's sourceMapTarget resolves
// to real Planes source, mirroring test_world_source_map.py.
// Phase 3 (persistence): mirrors test_world_runtime.py — load once,
// init once, advance N times, valid envelope + immutability at every tick.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { WorldRuntime, WorldRuntimeError } from "../world_runtime.mjs";
import {
  formatSourceMapPath,
  resolveSourceMapPath,
  SourceMapError,
} from "../world_source_map.mjs";
import { toHost } from "../interp.mjs";
import { parseWorldEnvelope } from "../world_ir.mjs";
import { TestHost } from "../host.mjs";

function normalizedOf(traced) {
  return parseWorldEnvelope(toHost(traced.value)).normalized;
}

const DEMO = "world_runtime_demo.planes";

// ---- Phase 2: source maps ---------------------------------------------

test("formatSourceMapPath is repo-relative", () => {
  const p = formatSourceMapPath("/Users/x/planes/world_runtime_demo.planes", 59);
  assert.ok(p.endsWith("world_runtime_demo.planes:59"));
  assert.ok(!p.startsWith("/"));
});

test("formatSourceMapPath is null with no entry file", () => {
  assert.equal(formatSourceMapPath(null, 5), null);
});

test("the demo program's emitted affordance source map resolves to real source", async () => {
  const rt = new WorldRuntime(DEMO, { host: new TestHost() });
  await rt.load();
  rt.init();
  const target = rt.itp.worldEnvelopes[0].normalized.affordance.sourceMapTarget;
  assert.equal(resolveSourceMapPath(target), "show demo-world");
  assert.notEqual(target, "pending");
});

test("a path outside the repo refuses", () => {
  assert.throws(() => resolveSourceMapPath("/etc/hosts:1"), SourceMapError);
});

test("a path naming a nonexistent file refuses", () => {
  assert.throws(
    () => resolveSourceMapPath("demo/does_not_exist_at_all.planes:1"),
    SourceMapError,
  );
});

test("a path naming a line past the end of the file refuses", () => {
  assert.throws(
    () => resolveSourceMapPath("world_runtime_demo.planes:999999"),
    SourceMapError,
  );
});

test("a malformed path with no colon refuses", () => {
  assert.throws(() => resolveSourceMapPath("no-line-number-here"), SourceMapError);
});

test("a malformed path with a non-numeric line refuses", () => {
  assert.throws(
    () => resolveSourceMapPath("world_runtime_demo.planes:soon"),
    SourceMapError,
  );
});

test("format then resolve round-trips for every line of a real file", () => {
  const lines = fs.readFileSync(DEMO, "utf-8").split("\n");
  const body = lines[lines.length - 1] === "" ? lines.slice(0, -1) : lines;
  body.forEach((expected, i) => {
    const path = formatSourceMapPath(DEMO, i + 1);
    assert.equal(resolveSourceMapPath(path), expected);
  });
});

// ---- Phase 3: persistent invocation ------------------------------------

test("init produces a valid emittable envelope at tick zero", async () => {
  const rt = new WorldRuntime(DEMO, { host: new TestHost() });
  await rt.load();
  rt.init();
  const { normalized, warnings } = rt.envelope();
  assert.deepEqual(warnings, []);
  assert.equal(normalized.situation.x, 0);
});

test("advance produces a new valid envelope each tick", async () => {
  const rt = new WorldRuntime(DEMO, { host: new TestHost() });
  await rt.load();
  rt.init();
  for (const expectedX of [1, 2, 3]) {
    rt.advance();
    const { normalized, warnings } = rt.envelope();
    assert.deepEqual(warnings, []);
    assert.equal(normalized.situation.x, expectedX);
  }
});

test("advance before init refuses", async () => {
  const rt = new WorldRuntime(DEMO, { host: new TestHost() });
  await rt.load();
  assert.throws(() => rt.advance(), WorldRuntimeError);
});

test("a program missing world-init refuses at load", async () => {
  const rt = new WorldRuntime("benchmarks/world_shape.planes", { host: new TestHost() });
  await assert.rejects(() => rt.load(), WorldRuntimeError);
});

test("tick N's value is unchanged after tick N+1 runs", async () => {
  // Snapshots are taken through parseWorldEnvelope(toHost(...)) rather than
  // structuredClone: toHost already converts every PlanesNumber/Map to
  // plain JS values (numbers/objects), which is what a value-based
  // deepEqual can compare without tripping over class-instance identity —
  // structuredClone preserves Map/BigInt shape but not custom prototypes,
  // so a strict deepEqual against a cloned PlanesNumber fails on class
  // identity even when every field is equal.
  const rt = new WorldRuntime(DEMO, { host: new TestHost() });
  await rt.load();
  const tick0 = rt.init();
  const tick0Before = normalizedOf(tick0);

  const tick1 = rt.advance();
  const tick0After = normalizedOf(tick0);
  assert.deepEqual(tick0After, tick0Before, "tick 0's value changed after advance() ran");
  assert.notDeepEqual(normalizedOf(tick1), tick0Before);

  const tick1Before = normalizedOf(tick1);
  rt.advance();
  const tick1After = normalizedOf(tick1);
  assert.deepEqual(tick1After, tick1Before, "tick 1's value changed after a later advance() ran");
});

test("the world value is never serialized through JSON between ticks", async () => {
  const rt = new WorldRuntime(DEMO, { host: new TestHost() });
  await rt.load();
  const tick0 = rt.init();
  const tick1 = rt.advance();
  assert.notEqual(tick1.value, tick0.value);
  assert.notEqual(tick1.value.get("situation"), tick0.value.get("situation"));
});

test("the module graph loads exactly once across many advance calls", async () => {
  // js/modules.mjs's exported `load_graph` binding is a non-configurable
  // property of its module namespace object (an ES module invariant — it
  // cannot be reassigned from outside, unlike Python's `modules.load_graph`
  // which the equivalent test in test_world_runtime.py patches directly).
  // module_loader_node.mjs's `read()` is what load_graph actually calls
  // into the filesystem through, via node:fs's CommonJS-interop default
  // export — a real mutable object every importer shares — so patching
  // `fs.readFileSync` there observes the same fact from one layer down:
  // no file is read outside the one `load()` call, at any tick.
  const original = fs.readFileSync;
  let calls = 0;
  fs.readFileSync = (...args) => {
    calls += 1;
    return original(...args);
  };
  try {
    const rt = new WorldRuntime(DEMO, { host: new TestHost() });
    await rt.load();
    assert.ok(calls >= 1, "load() itself must have read the file at least once");
    const afterLoad = calls;
    rt.init();
    for (let i = 0; i < 10; i++) rt.advance();
    assert.equal(calls, afterLoad, `readFileSync was called ${calls - afterLoad} more time(s) during init/advance, expected 0`);
  } finally {
    fs.readFileSync = original;
  }
});

test("the retention window and tracing-off fast path are available per tick", async () => {
  const rt = new WorldRuntime(DEMO, { host: new TestHost(), window: 8, trace: false });
  await rt.load();
  rt.init();
  for (let i = 0; i < 20; i++) rt.advance();
  const { normalized, warnings } = rt.envelope();
  assert.deepEqual(warnings, []);
  assert.equal(normalized.situation.x, 20);
  assert.equal(rt.world.node, rt.itp._untraced);
});

test("many ticks stay valid world-v1 envelopes", async () => {
  const rt = new WorldRuntime(DEMO, { host: new TestHost(), window: 16 });
  await rt.load();
  rt.init();
  for (let i = 1; i <= 50; i++) {
    rt.advance();
    const { normalized, warnings } = rt.envelope();
    assert.deepEqual(warnings, []);
    assert.equal(normalized.situation.x, i);
  }
});
