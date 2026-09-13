// js/python_unicode.mjs — Python's case mapping and NFC, at Python's Unicode version.
//
// shapes.py folds `lower of`, `upper of` and `normalize of` a known value with
// Python's str.lower, str.upper and unicodedata.normalize("NFC", ...), and
// interp.py runs the same three. JavaScript's toLowerCase, toUpperCase and
// normalize are the engine's ICU tables, a Unicode version ahead of Python 3.14
// in Node 22 (so `upper of` U+A7CE reads differently) and behind it in an older
// browser. The data is Python's own,
// generated into python_unicode_data.mjs by scripts/python_unicode_gen.py; this
// file is the algorithms over it, as CPython runs them — the same algorithms as
// swift/Sources/Planes/PythonUnicode.swift. test_js_shapes.py and
// test_js_interp.py drive every code point through all three against the running
// Python.

import * as D from "./python_unicode_data.mjs";

// ================================================================ lookups

// Is `v` inside one of the inclusive (low, high) pairs of `flat`?
function inPairs(flat, v) {
  let lo = 0;
  let hi = flat.length >> 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (v < flat[2 * mid]) hi = mid;
    else if (v > flat[2 * mid + 1]) lo = mid + 1;
    else return true;
  }
  return false;
}

// Appends the code points `v` maps to in a (keys, starts, values) table to
// `out` and returns true, or returns false when `v` is not a key.
function appendMapped(out, keys, starts, values, v) {
  let lo = 0;
  let hi = keys.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (v < keys[mid]) hi = mid;
    else if (v > keys[mid]) lo = mid + 1;
    else {
      for (let i = starts[mid]; i < starts[mid + 1]; i++) out.push(values[i]);
      return true;
    }
  }
  return false;
}

function fromCodePoints(cps) {
  let s = "";
  for (let i = 0; i < cps.length; i += 4096) {
    s += String.fromCodePoint(...cps.slice(i, i + 4096));
  }
  return s;
}

function codePointsOf(s) {
  const out = [];
  for (const c of s) out.push(c.codePointAt(0));
  return out;
}

// ================================================================ case

const isCaseIgnorable = (v) => inPairs(D.caseIgnorable, v);
const isCased = (v) => inPairs(D.cased, v);

// CPython's `handle_capital_sigma`: U+03A3 lowers to final sigma when a cased
// character precedes it, past any case-ignorable ones, and none follows it.
function finalSigma(cps, i) {
  let j = i - 1;
  let c = 0;
  while (j >= 0) {
    c = cps[j];
    if (!isCaseIgnorable(c)) break;
    j--;
  }
  let final = j >= 0 && isCased(c);
  if (final && i + 1 < cps.length) {
    j = i + 1;
    while (j < cps.length) {
      c = cps[j];
      if (!isCaseIgnorable(c)) break;
      j++;
    }
    final = j === cps.length || !isCased(c);
  }
  return final;
}

// Python's `str.lower()`.
export function pythonLower(s) {
  const cps = codePointsOf(s);
  const out = [];
  for (let i = 0; i < cps.length; i++) {
    const v = cps[i];
    if (v === 0x3a3) out.push(finalSigma(cps, i) ? 0x3c2 : 0x3c3);
    else if (!appendMapped(out, D.lowerKeys, D.lowerStarts, D.lowerValues, v)) out.push(v);
  }
  return fromCodePoints(out);
}

// Python's `str.upper()`.
export function pythonUpper(s) {
  const out = [];
  for (const c of s) {
    const v = c.codePointAt(0);
    if (!appendMapped(out, D.upperKeys, D.upperStarts, D.upperValues, v)) out.push(v);
  }
  return fromCodePoints(out);
}

// ================================================================ NFC

const S_BASE = 0xac00;
const L_BASE = 0x1100;
const V_BASE = 0x1161;
const T_BASE = 0x11a7;
const L_COUNT = 19;
const V_COUNT = 21;
const T_COUNT = 28;
const N_COUNT = V_COUNT * T_COUNT;
const S_COUNT = L_COUNT * N_COUNT;

function combiningClass(v) {
  const flat = D.combiningClass;
  let lo = 0;
  let hi = flat.length / 3;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (v < flat[3 * mid]) hi = mid;
    else if (v > flat[3 * mid + 1]) lo = mid + 1;
    else return flat[3 * mid + 2];
  }
  return 0;
}

function primaryComposite(a, b) {
  // Hangul: L + V -> LV, LV + T -> LVT.
  if (a >= L_BASE && a < L_BASE + L_COUNT && b >= V_BASE && b < V_BASE + V_COUNT) {
    return S_BASE + ((a - L_BASE) * V_COUNT + (b - V_BASE)) * T_COUNT;
  }
  if (a >= S_BASE && a < S_BASE + S_COUNT && (a - S_BASE) % T_COUNT === 0 &&
      b > T_BASE && b < T_BASE + T_COUNT) {
    return a + (b - T_BASE);
  }
  const flat = D.composites;
  let lo = 0;
  let hi = flat.length / 3;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    const x = flat[3 * mid];
    const y = flat[3 * mid + 1];
    if (a < x || (a === x && b < y)) hi = mid;
    else if (a > x || b > y) lo = mid + 1;
    else return flat[3 * mid + 2];
  }
  return null;
}

// Python's `unicodedata.normalize("NFC", s)`: full canonical decomposition,
// canonical ordering, then canonical composition, each as UAX #15 defines it.
export function pythonNFC(s) {
  // Decompose.
  const d = [];
  for (const c of s) {
    const v = c.codePointAt(0);
    if (v >= S_BASE && v < S_BASE + S_COUNT) {
      const i = v - S_BASE;
      d.push(L_BASE + Math.floor(i / N_COUNT));
      d.push(V_BASE + Math.floor((i % N_COUNT) / T_COUNT));
      if (i % T_COUNT !== 0) d.push(T_BASE + (i % T_COUNT));
    } else if (!appendMapped(d, D.decompositionKeys, D.decompositionStarts, D.decompositionValues, v)) {
      d.push(v);
    }
  }

  // Order each run of non-starters by class, stably.
  const classes = d.map(combiningClass);
  let i = 0;
  while (i < d.length) {
    if (classes[i] === 0) {
      i++;
      continue;
    }
    let j = i;
    while (j < d.length && classes[j] !== 0) j++;
    if (j - i > 1) {
      const run = [];
      for (let k = i; k < j; k++) run.push(k);
      run.sort((a, b) => (classes[a] !== classes[b] ? classes[a] - classes[b] : a - b));
      const reordered = run.map((k) => d[k]);
      for (let k = i; k < j; k++) d[k] = reordered[k - i];
    }
    i = j;
  }

  // Compose: a character joins the last starter unless something between
  // them blocks it — a starter, or a character of the same or higher class.
  const out = [];
  let starter = null;
  let lastClass = 0;
  for (const v of d) {
    const cls = combiningClass(v);
    if (starter !== null) {
      const adjacent = out.length - 1 === starter;
      if (adjacent || (lastClass !== 0 && lastClass < cls)) {
        const composite = primaryComposite(out[starter], v);
        if (composite !== null) {
          out[starter] = composite;
          continue;
        }
      }
    }
    if (cls === 0) starter = out.length;
    lastClass = cls;
    out.push(v);
  }
  return fromCodePoints(out);
}
