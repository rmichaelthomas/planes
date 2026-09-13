// js/test/record_entry.test.mjs — the record plane (Interpreter.records)
// across a structured-clone or JSON boundary (sprint 2026-09, F6).
//
// Reported downstream: 5xFive's Cloudflare Workflow `step.do()` structured-
// clones its argument, and every automation failed until 5xFive hand-
// sanitized a record entry first. The two tests under "the raw entry is not
// safe to cross either boundary" pin exactly what went wrong (no exception
// from structuredClone, just a silently stripped prototype; a hard throw
// from JSON.stringify, from the BigInt inside an exact Fraction). The tests
// under "toPlain" verify the fix in js/interp.mjs: a plain-data form that
// round-trips cleanly through both.
//
// Run: node --test js/test/record_entry.test.mjs

import { test } from "node:test";
import assert from "node:assert/strict";
import { loadGrammar } from "../loader_node.mjs";
import { Interpreter, Deriv, toPlain } from "../interp.mjs";
import { TestHost } from "../host.mjs";

loadGrammar();

function recordedRun(src, opts = {}) {
  const itp = new Interpreter({ record: true, host: new TestHost(), ...opts });
  itp.run(src);
  return itp;
}

// ================================================================ the raw entry is not safe to cross either boundary

test("a raw record entry's derivation loses its Deriv/PlanesNumber class across structuredClone", () => {
  // "why (1/4)" — genuine provenance for an exact non-whole rational.
  const itp = recordedRun("y = 1 / 4\nshow text of y\n");
  const entry = itp.records[0];
  assert.ok(entry.derivation instanceof Deriv);

  const cloned = structuredClone(entry); // must not throw
  assert.equal(cloned.derivation instanceof Deriv, false);

  // The exact rational three levels down (op "/" -> name "y") clones as a
  // plain object: the BigInt numerator/denominator survive, but the class
  // and its methods do not — `instanceof` fails and `.text()` is gone. A
  // consumer that still assumes a PlanesNumber, as 5xFive's did, throws here.
  const innerValue = cloned.derivation.inputs[0].value;
  assert.equal(typeof innerValue.q.n, "bigint");
  assert.equal(typeof innerValue.text, "undefined");
});

test("a raw record entry throws under JSON.stringify when its derivation carries an exact number", () => {
  const itp = recordedRun("y = 1 / 4\nshow text of y\n");
  const entry = itp.records[0];
  assert.throws(() => JSON.stringify(entry), /BigInt/);
});

// ================================================================ toPlain

test("toPlain converts an exact whole number to a JS number and a non-whole one to its text", () => {
  const itp = recordedRun("y = 1 / 4\nshow text of y\n");
  const plain = toPlain(itp.records[0]);
  // derivation: "text of" -> name "y" -> op "/" -> literal "1", literal "4"
  const nonWhole = plain.derivation.inputs[0].inputs[0]; // the "/" op, value 0.25
  const whole = nonWhole.inputs[0]; // the literal "1"
  assert.equal(whole.value, 1);
  assert.equal(typeof whole.value, "number");
  assert.equal(nonWhole.value, "0.25");
  assert.equal(typeof nonWhole.value, "string");
});

test("toPlain converts a Planes record (Map) inside a derivation to a plain object", () => {
  const itp = recordedRun("p = { x: 1, y: 1 / 4 }\nshow p\n");
  const entry = itp.records[0];
  assert.ok(entry.derivation.value instanceof Map); // pre-condition: still a Map

  const plain = toPlain(entry);
  assert.equal(plain.derivation.value.constructor, Object);
  assert.deepEqual(plain.derivation.value, { x: 1, y: "0.25" });
});

test("toPlain round-trips through structuredClone with no loss", () => {
  const itp = recordedRun('p = { x: 1, y: 1 / 4 }\nshow p\nuse file\nwrite [1, 2] to "o.json"\n', { fs: {} });
  for (const entry of itp.records) {
    const plain = toPlain(entry);
    const cloned = structuredClone(plain); // must not throw
    assert.deepEqual(cloned, plain);
  }
});

test("toPlain round-trips through JSON.stringify with no loss", () => {
  const itp = recordedRun('p = { x: 1, y: 1 / 4 }\nshow p\nuse file\nwrite [1, 2] to "o.json"\n', { fs: {} });
  for (const entry of itp.records) {
    const plain = toPlain(entry);
    const roundTripped = JSON.parse(JSON.stringify(plain)); // must not throw
    assert.deepEqual(roundTripped, plain);
  }
});

test("toPlain preserves the fields a consumer reads: kind, target, anchor, when, format", () => {
  const itp = recordedRun('use file\nwrite [1, 2] to "o.json"\n', { fs: {} });
  const plain = toPlain(itp.records[0]);
  assert.equal(plain.kind, "write");
  assert.equal(plain.boundary, "file");
  assert.equal(plain.target, "o.json");
  assert.equal(plain.computed, false);
  assert.deepEqual(plain.anchor, { kind: "host", identity: "test" });
  assert.equal(typeof plain.when, "number");
  assert.equal(plain.format, 1);
});

test("toPlain of a null derivation (recording with tracing off) stays null", () => {
  const itp = recordedRun("show text of 1\n", { trace: false });
  const plain = toPlain(itp.records[0]);
  // Tracing off still records the shared untraced sentinel, not null — this
  // pins that toPlain handles it like any other Deriv rather than assuming
  // one is always present with real provenance.
  assert.equal(plain.derivation.kind, "untraced");
  assert.equal(plain.derivation.value, null);
  const cloned = structuredClone(plain);
  assert.deepEqual(cloned, plain);
});
