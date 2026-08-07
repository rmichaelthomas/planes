// js/test/world_emission.test.mjs — Horizon Phase 0 Build 2, Phase 1.
//
// Mirrors test_world_emission.py: a program emitting the three critical
// facets round-trips emit -> parse -> accept, and an existing corpus
// program's text output and effect log match a pre-build capture
// byte-for-byte.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { Interpreter } from "../interp.mjs";
import { runFile } from "../run_file.mjs";
import { parseWorldEnvelope, canonicalOutcomeString, WorldIRError } from "../world_ir.mjs";
import { emitWorld } from "../world_emit_node.mjs";
import { loadGrammar } from "../loader_node.mjs";
import { TestHost } from "../host.mjs";

loadGrammar();

const DEMO = "world_runtime_demo.planes";

// The pre-build capture (§N+3.2): benchmarks/world_shape.planes run against
// js/interp.mjs BEFORE this build's Show-case changes. See
// test_world_emission.py for the matching Python capture and
// reports/REPORT_WORLD_RUNTIME.md for how both were taken.
const PRE_BUILD_OUTPUT = [
  "FINAL-TICK=31", "SUBJECT-COUNT=64", "EVENTS-LENGTH=32",
  "FACET-FIELD-COUNT=4", "SUBJECT-FIELD-COUNT=7", "WORLD-FIELD-COUNT=3",
];
const PRE_BUILD_EFFECTS = PRE_BUILD_OUTPUT.map((t) => ["show", t]);

test("an existing corpus program shows no world content and emits nothing", async () => {
  const itp = new Interpreter({ host: new TestHost(), emitWorld });
  await runFile(itp, "benchmarks/world_shape.planes");
  assert.deepEqual(itp.output, PRE_BUILD_OUTPUT);
  assert.deepEqual(itp.effects, PRE_BUILD_EFFECTS);
  assert.deepEqual(itp.worldEnvelopes, []);
});

test("without emitWorld set, a world-shaped show still emits nothing (default is a no-op)", async () => {
  const itp = new Interpreter({ host: new TestHost() });
  await runFile(itp, DEMO);
  assert.deepEqual(itp.worldEnvelopes, []);
  assert.equal(itp.output.length, 1);
});

test("the demo world program emits exactly one world envelope", async () => {
  const itp = new Interpreter({ host: new TestHost(), emitWorld });
  await runFile(itp, DEMO);
  assert.equal(itp.worldEnvelopes.length, 1);
});

test("the emitted envelope parses clean through world_ir.mjs's own parser", async () => {
  const itp = new Interpreter({ host: new TestHost(), emitWorld });
  await runFile(itp, DEMO);
  const emission = itp.worldEnvelopes[0];
  const { normalized, warnings } = parseWorldEnvelope(structuredClone(emission.raw));
  assert.deepEqual(warnings, []);
  assert.deepEqual(normalized, emission.normalized);
});

test("the emitted envelope normalizes to the expected canonical form", async () => {
  const itp = new Interpreter({ host: new TestHost(), emitWorld });
  await runFile(itp, DEMO);
  const outcome = canonicalOutcomeString(itp.worldEnvelopes[0].raw);
  assert.ok(outcome.startsWith("world-ir-outcome: accept"));
  assert.ok(outcome.includes("identity.id: wayfinder-1"));
  assert.ok(outcome.includes("situation.x: 0"));
  assert.ok(outcome.includes("lineage.corpusSource: ala-eriri"));
});

test("emission never touches output/effects/trace length", async () => {
  const itp = new Interpreter({ host: new TestHost(), emitWorld });
  await runFile(itp, DEMO);
  assert.equal(itp.output.length, 1);
  assert.equal(itp.trace.length, 1);
  assert.deepEqual(itp.effects, [["show", "{record}"]]);
});

test("a shown record with no version field emits nothing", async () => {
  const itp = new Interpreter({ host: new TestHost(), emitWorld });
  itp.run(
    'let x = { identity: { id: "a", kind: "b", subkind: "c", displayName: "d", status: "e", schemaVersion: 1 } }\nshow x\n',
  );
  assert.deepEqual(itp.worldEnvelopes, []);
});

test("a shown record with version but no critical facet emits nothing", async () => {
  const itp = new Interpreter({ host: new TestHost(), emitWorld });
  itp.run('let x = { version: 1, note: "not world content" }\nshow x\n');
  assert.deepEqual(itp.worldEnvelopes, []);
});

test("a malformed world content attempt refuses rather than silently dropping", async () => {
  const itp = new Interpreter({ host: new TestHost(), emitWorld });
  assert.throws(
    () => itp.run(
      'let x = { version: 1, identity: { this: "is not a valid identity record" } }\nshow x\n',
    ),
    WorldIRError,
  );
  assert.deepEqual(itp.output, ["{record}"]);
  assert.deepEqual(itp.effects, [["show", "{record}"]]);
});
