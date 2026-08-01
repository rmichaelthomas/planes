// js/test/square_root.test.mjs — `root`, on the JavaScript side.
//
// The cross-implementation agreement lives in test_square_root.py, which runs
// all three. This file covers what only exists here: the BigInt integer square
// root, and the fact that `rootOf` decides exactness rather than assuming it.

import { test } from "node:test";
import assert from "node:assert/strict";
import { PlanesNumber, isqrt, rootOf, ROOT_APPROXIMATION } from "../planes_num.mjs";
import { Interpreter, PlanesError } from "../interp.mjs";
import { loadGrammar } from "../loader_node.mjs";
import { TestHost } from "../host.mjs";

loadGrammar();

// One program, run the way js/cli.mjs runs one, reduced to what these tests
// need: the output lines, or the error.
function run(src) {
  const it = new Interpreter(new TestHost());
  try {
    it.run(src);
    return { output: it.output, error: null };
  } catch (e) {
    if (e instanceof PlanesError) return { output: it.output ?? [], error: e };
    throw e;
  }
}

const num = (s) => PlanesNumber.parse(s);

test("isqrt is the floor of the square root, exactly, at every size", () => {
  for (let n = 0n; n < 200n; n++) {
    const r = isqrt(n);
    assert.ok(r * r <= n && (r + 1n) * (r + 1n) > n, `isqrt(${n}) = ${r}`);
  }
  // The sizes the approximate path actually reaches: n * 4 * 10^60.
  for (const n of [10n ** 60n, 10n ** 61n, 2n * 10n ** 60n, (10n ** 30n + 1n) ** 2n]) {
    const r = isqrt(n);
    assert.ok(r * r <= n && (r + 1n) * (r + 1n) > n, `isqrt(${n})`);
  }
  assert.equal(isqrt(10n ** 60n), 10n ** 30n);
  assert.equal(isqrt((10n ** 30n + 1n) ** 2n), 10n ** 30n + 1n);
});

test("isqrt refuses a negative integer rather than looping", () => {
  assert.throws(() => isqrt(-1n), RangeError);
});

test("a perfect square of a ratio is exact; anything else is approximate", () => {
  for (const s of ["0", "1", "4", "9", "0.25", "2.25", "0.0001", "12321"]) {
    const r = rootOf(num(s));
    assert.equal(r.approx, null, `root of ${s} came back approximate`);
  }
  for (const s of ["2", "3", "5", "10", "0.5", "1.1"]) {
    const r = rootOf(num(s));
    assert.equal(r.approx, ROOT_APPROXIMATION, `root of ${s} claimed to be exact`);
  }
});

test("a reduced ratio of two perfect squares is exact — the case a naive port misses", () => {
  // 1/9 -> 1/3. Neither numerator nor denominator is a power of ten, so an
  // implementation that worked in fixed point would call this approximate.
  const r = rootOf(num("1").div(num("9")));
  assert.equal(r.approx, null, "root of 1/9 is exactly 1/3");
  assert.equal(r.mul(r).cmp(num("1").div(num("9"))), 0, "and it squares back exactly");
});

test("an approximate argument gives an approximate result down both branches", () => {
  const approx = new PlanesNumber(num("9").q, ROOT_APPROXIMATION);
  const r = rootOf(approx);
  assert.notEqual(r.approx, null, "the exact branch laundered an approximate argument");
  assert.equal(r.text(), "3", "and the value is still right");
});

test("the interpreter refuses a negative radicand and names the fix", () => {
  const r = run("show text of (root of (0 - 9))\n");
  assert.equal(r.error.tag, "not-a-number");
  assert.match(r.error.message, /cannot take the square root of -9/);
  assert.match(r.error.fix, /no imaginary number/);
});

test("the interpreter refuses a non-number and names the fix", () => {
  const r = run('show text of (root of "9")\n');
  assert.equal(r.error.tag, "not-a-number");
  assert.match(r.error.fix, /convert it first with number of/);
});

test("a user function named root shadows the builtin", () => {
  const r = run("to root of x:\n  give 99\nshow text of (root of 9)\n");
  assert.equal(r.error, null);
  assert.deepEqual(r.output, ["99"]);
});
