// js/test/exactness.test.mjs — a value carries whether it is exact.
//
// A number is APPROXIMATE when the true result of the operation that produced
// it cannot be represented as a rational, and EXACT otherwise. The property
// rides on the value, not on the expression that read it, so it survives being
// stored in a list, pulled back out, and used in arithmetic a thousand
// operations later.
//
// Phase 1 landed the property INERT: it exists, it propagates, and nothing in
// the language produces an approximate value. The synthetic marker used here —
// `withApprox` — is the same one `sine` uses in Phase 2, so what these tests
// prove about propagation is what `sine`'s results actually get.

import { test } from "node:test";
import assert from "node:assert/strict";
import { PlanesNumber, Approximation, Fraction } from "../planes_num.mjs";

const n = (v) => PlanesNumber.of(v);
const MARK = new Approximation("sine", "test scaffolding");
const approx = (v) => n(v).withApprox(MARK);

// ---- exact is the default, and every operation preserves it ------------------

test("a number is exact unless it says otherwise", () => {
  for (const v of [0, 1, -7, "0.1", "1/3", "12.5"]) {
    assert.equal(n(v).isExact, true, String(v));
    assert.equal(n(v).approx, null, String(v));
  }
});

test("exact combined with exact stays exact, in every arithmetic operation", () => {
  const a = n(1).div(n(3));
  const b = n("0.1");
  for (const r of [a.add(b), a.sub(b), a.mul(b), a.div(b), a.neg(), b.neg()]) {
    assert.equal(r.isExact, true);
  }
  // and the arithmetic itself is unchanged: a third times three is one.
  assert.equal(a.mul(n(3)).text(), "1");
  assert.equal(n("0.1").add(n("0.2")).text(), "0.3");
});

// ---- approximate propagates through everything -------------------------------

test("anything touching an approximate value is approximate", () => {
  const a = approx("0.5");
  const e = n(4);
  const cases = {
    "approx + exact": a.add(e),
    "exact + approx": e.add(a),
    "approx - exact": a.sub(e),
    "exact - approx": e.sub(a),
    "approx * exact": a.mul(e),
    "exact * approx": e.mul(a),
    "approx / exact": a.div(e),
    "exact / approx": e.div(a),
    "negated": a.neg(),
    "approx + approx": a.add(a),
  };
  for (const [name, r] of Object.entries(cases)) {
    assert.equal(r.isExact, false, name);
    assert.ok(r.approx.eq(MARK), `${name} keeps the entry point`);
  }
});

test("the entry point survives a long chain of exact operations", () => {
  let v = approx("0.5");
  for (let i = 0; i < 200; i++) v = v.add(n(1)).mul(n(2)).div(n(2)).sub(n(1));
  assert.equal(v.isExact, false);
  assert.ok(v.approx.eq(MARK), "200 operations later, it still names where it entered");
});

test("the entry point is shared by reference, not copied per operation", () => {
  const a = approx("0.5");
  assert.equal(a.add(n(1)).approx, a.approx, "one record, however long the chain");
  assert.equal(a.mul(n(3)).div(n(7)).approx, a.approx);
});

test("an approximate value carried through a collection is still approximate", () => {
  const list = [n(1), approx("0.5"), n(3)];
  assert.deepEqual(list.map((x) => x.isExact), [true, false, true]);
  const copied = list.slice(1); // what `rest of` does
  assert.equal(copied[0].isExact, false);
  assert.ok(copied[0].approx.eq(MARK));
});

// ---- the two rules that look like exceptions ---------------------------------

test("round to N places returns an EXACT value — a named reduction is not approximation", () => {
  const third = n(1).div(n(3));
  assert.equal(third.isExact, true);
  const rounded = third.roundTo(2);
  assert.equal(rounded.isExact, true, "0.33 is the exact result of the operation asked for");
  assert.equal(rounded.text(), "0.33");
});

test("rounding money keeps it exact, which is the whole reason for the rule", () => {
  // Three items at 19.99 with 8.25% tax, rounded to the cent. If rounding
  // marked values approximate, every invoice in the corpus would come out
  // flagged and the exact-money claim would be destroyed by this feature.
  const subtotal = n("19.99").mul(n(3));
  const tax = subtotal.mul(n("0.0825")).roundTo(2);
  const total = subtotal.add(tax);
  assert.equal(subtotal.text(), "59.97");
  assert.equal(tax.text(), "4.95");
  assert.equal(total.text(), "64.92");
  for (const v of [subtotal, tax, total]) assert.equal(v.isExact, true);
});

test("rounding an approximate value does not launder it back to exact", () => {
  const r = approx("0.3333").roundTo(2);
  assert.equal(r.isExact, false);
  assert.ok(r.approx.eq(MARK));
});

test("== between two approximate values compares the rationals, with no tolerance", () => {
  const a = approx("0.5");
  const b = approx("0.5");
  const c = approx("0.5000000000000000000000000000001");
  assert.equal(a.eq(b), true, "equal rationals are equal");
  assert.equal(a.eq(c), false, "unequal rationals are unequal, however close");
  assert.equal(a.eq(n("0.5")), true, "and an approximate value equals an exact one of the same rational");
  assert.equal(a.cmp(c), -1, "ordering is the plain rational ordering too");
});

test("no epsilon or tolerance constant exists in the numeric tower", async () => {
  const fs = await import("node:fs");
  const { fileURLToPath } = await import("node:url");
  const src = fs.readFileSync(fileURLToPath(new URL("../planes_num.mjs", import.meta.url)), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
  assert.doesNotMatch(code, /epsilon|EPSILON|tolerance|1e-\d/i);
});

// ---- the property is not the rendering ----------------------------------------

test("the tilde in rendering means non-terminating, not approximate", () => {
  // A third is EXACT and prints with a leading ~ because its decimal expansion
  // does not terminate. Half is APPROXIMATE here and prints without one. The
  // two marks answer different questions and must not be conflated.
  const third = n(1).div(n(3));
  assert.equal(third.isExact, true);
  assert.match(third.text(), /^~/);

  const half = approx("0.5");
  assert.equal(half.isExact, false);
  assert.equal(half.text(), "0.5");
});

// ---- the bound still refuses rather than rounding -----------------------------

test("MAX_DENOMINATOR still refuses rather than silently approximating", async () => {
  const { Inexact, MAX_DENOMINATOR } = await import("../planes_num.mjs");
  let v = new PlanesNumber(new Fraction(1n, MAX_DENOMINATOR));
  assert.throws(() => v.div(n(3)), Inexact, "past the bound is a refusal, not a new kind of approximate");
});
