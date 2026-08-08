// js/test/world_kernel.test.mjs — Horizon Phase 1: the engine-kernel spike.
//
// Mirrors test_world_kernel.py's acceptance coverage for the JS-side
// kernel/sink pair: a start()-before-step() requirement, a hundred-tick run
// with a percentile table and an unbroken hash chain, and the retention
// discipline (identity/lineage never in a facet-patch).
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { WorldKernel, WorldKernelError } from "../world_kernel.mjs";
import { TestSink } from "../world_test_sink.mjs";
import { TestHost } from "../host.mjs";

const FIXTURE = "paint/world/kernel_spike_fixture.planes";

async function kernel(opts = {}) {
  const k = new WorldKernel(FIXTURE, { host: new TestHost(), ...opts });
  await k.start();
  return k;
}

test("start() before step() is required", () => {
  const k = new WorldKernel(FIXTURE, { host: new TestHost() });
  assert.throws(() => k.step(), WorldKernelError);
});

test("a hundred ticks produce a percentile table and an unbroken chain", async () => {
  const k = await kernel();
  const sink = new TestSink();
  for (let i = 0; i < 100; i++) {
    const { delta, elapsedSeconds } = k.step();
    sink.consume(delta, elapsedSeconds);
  }
  const p = sink.percentiles();
  assert.equal(p.count, 100);
  assert.equal(sink.count, 100);
  assert.ok(p.min <= p.p50 && p.p50 <= p.p95 && p.p95 <= p.p99 && p.p99 <= p.p999 && p.p999 <= p.max);
  assert.equal(p.distribution.length, 100);
  assert.deepEqual(p.distribution, [...p.distribution].sort((a, b) => a - b));
  assert.equal(sink.chainHash.length, 64);
  assert.match(sink.chainHash, /^[0-9a-f]{64}$/);
  assert.equal(k.revision, 100);
});

test("step() returns delta and elapsedSeconds only", async () => {
  const k = await kernel();
  const result = k.step();
  assert.ok("delta" in result && "elapsedSeconds" in result);
  assert.equal(typeof result.elapsedSeconds, "number");
  assert.ok(result.elapsedSeconds >= 0);
});

test("revision counter advances monotonically from start", async () => {
  const k = await kernel();
  assert.equal(k.revision, 0);
  for (let expected = 1; expected <= 20; expected++) {
    const { delta } = k.step();
    assert.equal(delta.revisionFrom, expected - 1);
    assert.equal(delta.revisionTo, expected);
    assert.equal(k.revision, expected);
  }
});

test("identity and lineage never appear in a facet-patch", async () => {
  const k = await kernel();
  for (let i = 0; i < 80; i++) {
    const { delta } = k.step();
    for (const patch of delta.facetPatches) {
      assert.notEqual(patch.facet, "identity");
      assert.notEqual(patch.facet, "lineage");
    }
  }
});

// ---- Horizon Phase 2 Build 1: the input-event seam ---------------------

test("step() with no events matches step([]) with an explicit empty list", async () => {
  const k1 = await kernel();
  const k2 = await kernel();
  for (let i = 0; i < 20; i++) {
    const { delta: d1 } = k1.step();
    const { delta: d2 } = k2.step([]);
    assert.deepEqual(d1, d2);
  }
});

test("a nudge event changes exactly situation.x, deterministically", async () => {
  const without = await kernel();
  for (let i = 0; i < 10; i++) without.step();
  const envWithout = without.prevEnvelope;

  async function withNudge() {
    const k = await kernel();
    for (let i = 0; i < 9; i++) k.step();
    k.step([{ kind: "nudge" }]);
    return k;
  }
  const withA = await withNudge();
  const withB = await withNudge();
  assert.deepEqual(withA.prevEnvelope, withB.prevEnvelope, "the nudge reaction is not deterministic");

  const envWith = withA.prevEnvelope;
  const topDiffs = Object.keys(envWithout).filter(
    (k) => JSON.stringify(envWithout[k]) !== JSON.stringify(envWith[k]),
  );
  assert.deepEqual(topDiffs, ["situation"], `expected only situation to differ, got: ${topDiffs}`);
  const situationDiffs = Object.keys(envWithout.situation).filter(
    (k) => envWithout.situation[k] !== envWith.situation[k],
  );
  assert.deepEqual(situationDiffs, ["x"], `expected only situation.x to differ, got: ${situationDiffs}`);

  // A true one-tick effect: an empty batch on the very next tick shows no
  // lingering influence from the nudge.
  withA.step([]);
  without.step([]);
  assert.equal(withA.prevEnvelope.situation.x, without.prevEnvelope.situation.x);
});
