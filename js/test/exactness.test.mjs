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
import {
  PlanesNumber, Approximation, Fraction, sineDegrees,
  PI_OVER_180_NUM, PI_OVER_180_DEN, PI_OVER_180_DIGITS,
  SERIES_TERMS, WORKING_PLACES, RESULT_PLACES,
} from "../planes_num.mjs";

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

// ---- `sine`, the eleventh builtin ---------------------------------------------

test("sine at the quarter turns", () => {
  // Three of these land EXACTLY on the right rational, because the fold
  // reaches them without running the series at all.
  assert.equal(sineDegrees(n(0)).text(), "0");
  assert.equal(sineDegrees(n(90)).text(), "1");
  assert.equal(sineDegrees(n(180)).text(), "0");
  assert.equal(sineDegrees(n(270)).text(), "-1");
  assert.equal(sineDegrees(n(360)).text(), "0");
});

test("every sine result is approximate, including the exact-looking ones", () => {
  // `sine of 0` is 0 and is APPROXIMATE. The operation's true result being
  // representable at one argument does not make the operation exact — the
  // opposite of what square root will do, and the cleanest illustration of
  // why square root is the harder case.
  for (const d of [0, 30, 45, 90, 180, 270, 360, -30, 1000000]) {
    const v = sineDegrees(n(d));
    assert.equal(v.isExact, false, `sine of ${d}`);
    assert.equal(v.approx.op, "sine");
    for (const part of ["40 significant digits", "8-term", "50 working decimal places", "rounded to 30"]) {
      assert.ok(v.approx.detail.includes(part), part);
    }
  }
});

test("sine symmetry: sine of -d is -(sine of d), and sine of (180-d) is sine of d", () => {
  for (const d of [0, 7, 30, 45, 60, 89, 90, 123, 179, 250, 359]) {
    assert.ok(sineDegrees(n(-d)).eq(sineDegrees(n(d)).neg()), `sine of -${d}`);
    assert.ok(sineDegrees(n(180 - d)).eq(sineDegrees(n(d))), `sine of (180 - ${d})`);
  }
});

test("argument reduction is exact at any magnitude", () => {
  // Math.sin(360000030 * Math.PI / 180) is 0.5000000001..., wrong in the tenth
  // decimal place. This is the same value as sine of 30, bit for bit — the
  // property a float implementation cannot offer.
  const base = sineDegrees(n(30));
  for (const k of [1, 2, 1000, 1000000, -1, -1000]) {
    assert.ok(sineDegrees(n(30 + 360 * k)).eq(base), `30 + 360*${k}`);
  }
  assert.ok(sineDegrees(n(360000030)).eq(base));
});

test("a sine result carries a bounded denominator", () => {
  const bound = 10n ** BigInt(RESULT_PLACES);
  for (const d of [30, 45, 60, 123, 359]) {
    assert.ok(sineDegrees(n(d)).q.d <= bound, `sine of ${d}`);
  }
});

test("the stated parameters are the ones the code uses", () => {
  assert.equal(PI_OVER_180_DIGITS, 40);
  assert.equal(String(PI_OVER_180_NUM).length, 40, "the constant has 40 significant digits");
  assert.equal(PI_OVER_180_DEN, 10n ** 41n);
  assert.equal(SERIES_TERMS, 8);
  assert.equal(WORKING_PLACES, 50);
  assert.equal(RESULT_PLACES, 30);
  // The constant is within 1.3e-42 of pi/180. Checked against a 50-digit
  // expansion held here as an integer, not against Math.PI, which is a double
  // and so knows only sixteen of the forty digits this constant carries.
  //   pi/180 = 0.0174532925199432957692369076848861271344287188854172545...
  const REF = 17453292519943295769236907684886127134428718885417n;  // * 10^-51
  const ours = PI_OVER_180_NUM * 10n ** 10n;                        // * 10^-51
  const diff = ours > REF ? ours - REF : REF - ours;
  assert.ok(diff < 13n * 10n ** 8n, `constant drifted: ${diff} * 10^-51`);
  assert.ok(diff > 10n ** 8n, "the check would pass for a wildly wrong constant too");
});

test("sine propagates: anything downstream of it is approximate", () => {
  const s = sineDegrees(n(30));
  assert.equal(s.add(n(1)).isExact, false);
  assert.equal(s.mul(n(100)).roundTo(2).isExact, false, "rounding does not launder it");
  assert.equal(n(1).sub(s).approx.op, "sine", "and the entry point is still named");
});

test("no host trigonometric function is reachable from the numeric tower", async () => {
  const fs = await import("node:fs");
  const { fileURLToPath } = await import("node:url");
  for (const rel of ["../planes_num.mjs", "../interp.mjs"]) {
    const src = fs.readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
    assert.doesNotMatch(src, /Math\.(sin|cos|tan|atan|asin|acos)\b/, rel);
  }
});
