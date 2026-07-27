// js/planes_num.mjs — Planes numbers, exact rationals over BigInt.
//
// The JavaScript counterpart of planes_num.py. A number is exact: 0.1 + 0.2 is
// 0.3, not 0.30000000000000004, and 1 / 3 is one third, not
// 0.3333333333333333. why exists to answer "what combined to make this
// number", and a derivation with a silent rounding step does not answer that —
// so numbers never round. The cost is real and paid deliberately: denominators
// grow, and MAX_DENOMINATOR bounds that cost by refusing (visibly) rather than
// rounding (invisibly).
//
// JavaScript has no exact rational type and Number is a float — this is the
// single largest correctness risk in the port (A.3). The representation is a
// Fraction of two BigInts, always in lowest terms with a positive denominator,
// mirroring Python's fractions.Fraction. Every method is checked against
// planes_num.py in test_js_num.py.
//
// EXACT, AND APPROXIMATE. A number also carries whether it is exact: it is
// APPROXIMATE when the true result of the operation that produced it cannot be
// represented as a rational, and EXACT otherwise. `approx` is that property
// AND its provenance in one field — null when exact, an Approximation when not
// — because a flag saying "approximate" with no provenance beside it is a
// state the type should not be able to hold. Mirrors planes_num.py exactly.
//
// Two rules that look like exceptions and are not: `roundTo` on one third
// gives EXACTLY 0.33 (a deliberate, named reduction in precision is not
// approximation — if it were, every invoice in the corpus would come out
// flagged), and `eq` between two approximate values compares the underlying
// rationals with no epsilon and no tolerance (a tolerance nobody chose is the
// silent behaviour this design refuses).

// Roughly 4,000 bits — planes_num.py's MAX_DENOMINATOR = 2 ** 4000, unchanged.
export const MAX_DENOMINATOR = 2n ** 4000n;

function biAbs(a) {
  return a < 0n ? -a : a;
}

function gcd(a, b) {
  a = biAbs(a);
  b = biAbs(b);
  while (b) {
    [a, b] = [b, a % b];
  }
  return a;
}

// An exact rational of two BigInts, reduced, denominator positive. The subset
// of fractions.Fraction that Planes numbers use.
export class Fraction {
  constructor(num, den = 1n) {
    if (den === 0n) throw new RangeError("Fraction with zero denominator");
    if (den < 0n) {
      num = -num;
      den = -den;
    }
    const g = gcd(num, den) || 1n;
    this.n = num / g;
    this.d = den / g;
  }

  add(o) {
    return new Fraction(this.n * o.d + o.n * this.d, this.d * o.d);
  }
  sub(o) {
    return new Fraction(this.n * o.d - o.n * this.d, this.d * o.d);
  }
  mul(o) {
    return new Fraction(this.n * o.n, this.d * o.d);
  }
  div(o) {
    if (o.n === 0n) throw new RangeError("divided by zero");
    return new Fraction(this.n * o.d, this.d * o.n);
  }
  neg() {
    return new Fraction(-this.n, this.d);
  }
  // sign of (this - o): cross-multiply with positive denominators.
  cmp(o) {
    const l = this.n * o.d;
    const r = o.n * this.d;
    return l < r ? -1 : l > r ? 1 : 0;
  }
  eq(o) {
    return this.n === o.n && this.d === o.d;
  }
  lt(o) {
    return this.cmp(o) < 0;
  }
}

// Parse a decimal / integer / scientific / a-over-b string into an exact
// Fraction. Source NUMBER literals are only \d+(\.\d+)? — no sign, no exponent
// — but Number.of routes a foreign JS float here via String(v) (the shortest
// round-trip decimal, JS's analogue of Python's repr(float)), which may carry a
// sign and an exponent, so both forms are handled. Different textual formats of
// the same shortest-round-trip decimal (e.g. "1e+16" vs "10000000000000000")
// denote the same rational, so the parsed value matches Python regardless of
// whether JS's String and Python's repr chose the same notation.
export function fractionFromString(text) {
  let s = String(text).trim();
  if (s.includes("/")) {
    const [a, b] = s.split("/");
    return new Fraction(BigInt(a.trim()), BigInt(b.trim()));
  }
  let sign = 1n;
  if (s[0] === "+") s = s.slice(1);
  else if (s[0] === "-") {
    sign = -1n;
    s = s.slice(1);
  }
  let exp = 0n;
  const eIdx = s.search(/[eE]/);
  if (eIdx >= 0) {
    exp = BigInt(s.slice(eIdx + 1));
    s = s.slice(0, eIdx);
  }
  let intPart = s;
  let fracPart = "";
  if (s.includes(".")) {
    [intPart, fracPart] = s.split(".");
  }
  intPart = intPart === "" ? "0" : intPart;
  const digits = intPart + fracPart;
  let num = BigInt(digits === "" ? "0" : digits);
  let den = 10n ** BigInt(fracPart.length);
  if (exp >= 0n) num *= 10n ** exp;
  else den *= 10n ** -exp;
  return new Fraction(sign * num, den);
}

// An operation whose exact result cannot be represented in bounds. Mirrors
// planes_num.py's Inexact — a refusal, not a silent rounding.
export class Inexact extends Error {
  constructor(op) {
    super(
      `'${op}' would need more precision than a number can hold. This happens ` +
        `when many fractions with unrelated denominators are combined exactly`,
    );
    this.name = "Inexact";
    this.op = op;
  }
}

function terminates(denominator) {
  let d = denominator;
  for (const f of [2n, 5n]) {
    while (d % f === 0n) d /= f;
  }
  return d === 1n;
}

function exactDecimal(q) {
  let neg = q.n < 0n;
  let n = neg ? -q.n : q.n;
  const d = q.d;
  let places = 0;
  let dd = d;
  while (dd % 2n === 0n) {
    dd /= 2n;
    places += 1;
  }
  let p5 = 0;
  dd = d;
  while (dd % 5n === 0n) {
    dd /= 5n;
    p5 += 1;
  }
  places = Math.max(places, p5);
  const scaled = (n * 10n ** BigInt(places)) / d;
  const s = String(scaled).padStart(places + 1, "0");
  const whole = s.slice(0, s.length - places);
  let frac = s.slice(s.length - places).replace(/0+$/, "");
  const out = whole + (frac ? "." + frac : "");
  return (neg ? "-" : "") + out;
}

// Where a value stopped being exact, and with what parameters. Immutable and
// shared: an approximate value's arithmetic results carry the same record by
// reference, so a chain of a thousand operations off one `sine` allocates one
// of these, not a thousand. The JS analogue of planes_num.Approximation.
export class Approximation {
  constructor(op, detail = "") {
    this.op = op;
    this.detail = detail;
    Object.freeze(this);
  }
  eq(o) {
    return o instanceof Approximation && this.op === o.op && this.detail === o.detail;
  }
}

// A number, exact unless it says otherwise. Wraps a Fraction, renders like a
// person would write it, and carries `approx` — null when exact, an
// Approximation when not. The JS analogue of planes_num.Number (renamed to
// avoid colliding with JS's global Number).
export class PlanesNumber {
  constructor(q, approx = null) {
    this.q = q instanceof Fraction ? q : new Fraction(BigInt(q));
    this.approx = approx;
  }

  get isExact() {
    return this.approx === null;
  }

  // The same rational, carrying this approximation. The one place a value
  // becomes approximate; `sine` is currently its only caller.
  withApprox(approx) {
    return new PlanesNumber(this.q, approx);
  }

  // ---- construction
  static parse(text) {
    return new PlanesNumber(fractionFromString(text));
  }

  static of(v) {
    if (v instanceof PlanesNumber) return v;
    if (typeof v === "boolean") {
      throw new TypeError("a yes/no value is not a number");
    }
    if (typeof v === "bigint") return new PlanesNumber(new Fraction(v));
    if (v instanceof Fraction) return new PlanesNumber(v);
    if (typeof v === "number") {
      if (!Number.isFinite(v)) {
        throw new TypeError("a non-finite number cannot be exact");
      }
      // Shortest round-trip decimal, never the raw double bits — the analogue
      // of planes_num.py's Fraction(repr(v)). This keeps a JSON 0.1 exactly one
      // tenth and a JSON 1e23 exactly 10^23.
      return new PlanesNumber(fractionFromString(String(v)));
    }
    if (typeof v === "string") return new PlanesNumber(fractionFromString(v));
    throw new TypeError(`not a number: ${v}`);
  }

  // ---- shape
  isWhole() {
    return this.q.d === 1n;
  }
  asInt() {
    if (!this.isWhole()) throw new RangeError(`${this.text()} is not a whole number`);
    return this.q.n;
  }
  toNumber() {
    return Number(this.q.n) / Number(this.q.d);
  }

  // ---- arithmetic, each refusing past the bound rather than rounding
  _check(r, op) {
    if (r.q.d > MAX_DENOMINATOR) throw new Inexact(op);
    return r;
  }
  // exact + exact is exact; anything touching an approximate value is
  // approximate, and inherits the FIRST entry point on the left-to-right
  // reading of the expression. `why` on a comparison still shows both sides,
  // because the derivation tree keeps both input branches and each branch's
  // own number carries its own entry.
  add(o) {
    const r = PlanesNumber.of(o);
    return this._check(new PlanesNumber(this.q.add(r.q), this.approx ?? r.approx), "+");
  }
  sub(o) {
    const r = PlanesNumber.of(o);
    return this._check(new PlanesNumber(this.q.sub(r.q), this.approx ?? r.approx), "-");
  }
  mul(o) {
    const r = PlanesNumber.of(o);
    return this._check(new PlanesNumber(this.q.mul(r.q), this.approx ?? r.approx), "*");
  }
  div(o) {
    const d = PlanesNumber.of(o);
    if (d.q.n === 0n) throw new RangeError("divided by zero");
    return this._check(new PlanesNumber(this.q.div(d.q), this.approx ?? d.approx), "/");
  }
  neg() {
    return new PlanesNumber(this.q.neg(), this.approx);
  }

  // ---- comparison
  eq(o) {
    return this.q.eq(PlanesNumber.of(o).q);
  }
  cmp(o) {
    return this.q.cmp(PlanesNumber.of(o).q);
  }
  lt(o) {
    return this.cmp(o) < 0;
  }
  le(o) {
    return this.cmp(o) <= 0;
  }
  gt(o) {
    return this.cmp(o) > 0;
  }
  ge(o) {
    return this.cmp(o) >= 0;
  }
  isZero() {
    return this.q.n === 0n;
  }

  // ---- rounding, only when asked; half away from zero, all integer
  // arithmetic. The result carries whatever the input carried: rounding an
  // exact value gives an exact one, and rounding an approximate one does not
  // launder it back to exact.
  roundTo(places) {
    const p = Number(places);
    if (p < 0) throw new RangeError("places cannot be negative");
    const scale = new Fraction(10n ** BigInt(p));
    const scaled = this.q.mul(scale);
    const n = scaled.n;
    const d = scaled.d;
    let rounded;
    if (d === 1n) {
      rounded = n;
    } else {
      const sign = n < 0n ? -1n : 1n;
      rounded = sign * ((biAbs(n) * 2n + d) / (d * 2n));
    }
    return new PlanesNumber(new Fraction(rounded).div(scale), this.approx);
  }

  // ---- rendering. A terminating expansion prints exactly; a non-terminating
  // one prints to max_places with a leading ~, so the approximation is visible.
  text(maxPlaces = 12) {
    const q = this.q;
    if (q.d === 1n) return String(q.n);
    if (terminates(q.d)) return exactDecimal(q);
    const neg = q.n < 0n;
    const nAbs = neg ? -q.n : q.n;
    const scale = 10n ** BigInt(maxPlaces);
    const scaled = (nAbs * scale) / q.d; // floor, since positive
    const digits = String(scaled).padStart(maxPlaces + 1, "0");
    const whole = digits.slice(0, digits.length - maxPlaces);
    let frac = digits.slice(digits.length - maxPlaces).replace(/0+$/, "");
    if (frac === "") frac = "0";
    return `~${neg ? "-" : ""}${whole}.${frac}`;
  }

  toString() {
    return this.text();
  }
}

// ---- sine (planes_checkpoint_v21_0 §§251-253) --------------------------------
//
// THE ALGORITHM, once. The port of planes_num.py's sine_degrees, on exactly the
// same integers — which is what makes the two bit-identical rather than merely
// close. grammar/interp.planes writes the same steps in Planes with `+ - * /`
// and `round ... to 0 places`. The full derivation, and why this is scaled
// integers rather than plain exact rationals, is in planes_num.py's comment;
// the short version is that the rational form refuses outright at `sine of 60`
// (a denominator of 10^1224, past MAX_DENOMINATOR) and costs ~3ms per call here
// even where it does not, because gcd over 2000-bit BigInts dominates
// everything.

// pi/180 to 40 significant decimal digits, correctly rounded:
//   0.01745329251994329576923690768488612713443
// The error against the true value is under 1.3e-42. Byte-identical to
// planes_num.py's literal.
export const PI_OVER_180_NUM = 1745329251994329576923690768488612713443n;
export const PI_OVER_180_DEN = 10n ** 41n;
export const PI_OVER_180_DIGITS = 40;

// Eight terms: x - x^3/3! + ... - x^15/15!. After the fold the series argument
// is at most pi/4, where the first omitted term (x^17/17!) is 4.62e-17. That is
// the accuracy of the answer; RESULT_PLACES is how much of it is kept, not a
// claim about how much of it is right.
export const SERIES_TERMS = 8;
export const WORKING_PLACES = 50;
const WORKING_SCALE = 10n ** BigInt(WORKING_PLACES);
export const RESULT_PLACES = 30;
const RESULT_SCALE = 10n ** BigInt(RESULT_PLACES);

// Round n/d to the nearest integer, half away from zero. Integers only — the
// same rule `round x to N places` uses, so a program that rounds by hand and
// this series agree about what "nearest" means.
function divRound(n, d) {
  const sign = (n < 0n) !== (d < 0n) ? -1n : 1n;
  const an = biAbs(n);
  const ad = biAbs(d);
  return sign * ((an * 2n + ad) / (ad * 2n));
}

// sin of (an/ad) degrees, as an integer scaled by WORKING_SCALE. `an/ad` is
// already folded into [0, 45].
function seriesScaled(an, ad) {
  const x = divRound(an * PI_OVER_180_NUM * WORKING_SCALE, ad * PI_OVER_180_DEN);
  const x2 = divRound(x * x, WORKING_SCALE);
  let term = x;
  let total = x;
  for (let k = 1n; k < BigInt(SERIES_TERMS); k++) {
    term = -divRound(term * x2, WORKING_SCALE * (2n * k) * (2n * k + 1n));
    total += term;
  }
  return total;
}

// One record, shared by every value `sine` ever returns: the operation, and the
// four numbers that decide how good the answer is.
export const SINE_APPROXIMATION = new Approximation(
  "sine",
  `pi/180 to ${PI_OVER_180_DIGITS} significant digits, ` +
    `an ${SERIES_TERMS}-term Taylor series, ` +
    `${WORKING_PLACES} working decimal places, ` +
    `a result rounded to ${RESULT_PLACES}`,
);

// `sine of d` — d in degrees, exact in, approximate out.
//
// Steps 1 and 2 are exact: `sine of 360000030` reduces to `sine of 30` with no
// additional error at all, which is the property a float implementation cannot
// offer.
export function sineDegrees(value) {
  const an = value.q.n;
  const ad = value.q.d;

  // 1. into [0, 360), FLOORED (BigInt division truncates toward zero, so the
  //    negative case is stepped down explicitly), exactly
  const m = 360n * ad;
  let q = an / m;
  if (an < 0n && q * m !== an) q -= 1n;
  let rn = an - m * q;

  // 2. into [0, 45], exactly — sign flips and subtractions only
  let sign = 1n;
  if (rn >= 180n * ad) {
    rn -= 180n * ad;
    sign = -1n;
  }
  if (rn > 90n * ad) rn = 180n * ad - rn;

  // 3 and 4. the series, at the stated precisions
  let s;
  if (rn <= 45n * ad) {
    s = seriesScaled(rn, ad);
  } else {
    // sin(a) = cos(90 - a) = 1 - 2 * sin((90 - a)/2)^2, and (90-a)/2 <= 22.5
    const h = seriesScaled(90n * ad - rn, ad * 2n);
    s = WORKING_SCALE - divRound(2n * h * h, WORKING_SCALE);
  }

  const scaled = divRound(sign * s * RESULT_SCALE, WORKING_SCALE);
  return new PlanesNumber(new Fraction(scaled, RESULT_SCALE), SINE_APPROXIMATION);
}
