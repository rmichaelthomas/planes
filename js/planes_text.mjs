// js/planes_text.mjs — Planes text: STRING literal escapes, their inverse, and
// the code-point semantics JavaScript's UTF-16 strings do not give for free.
//
// The JavaScript counterpart of planes_text.py. Two things live here:
//
// 1. The four escapes a STRING literal may contain (v9.0 §105) and their
//    inverse — identical to planes_text.py, no numeric escapes.
//
// 2. Code-point iteration. Planes text is a sequence of Unicode CODE POINTS
//    (v9.0 §105). Python strings are already code-point sequences, so
//    planes_text.py needs no helper; JavaScript strings are UTF-16, so "😀"
//    .length is 2, not 1. `count of` and `for each … in <text>` must see one
//    element per code point, matching interp.py's len()/iteration — so the
//    interpreter routes text length and text iteration through here. Surrogate
//    pairs are exactly where UTF-16 and code points differ, and the tests cover
//    them.

export const STRING_ESCAPES = { '"': '"', "\\": "\\", n: "\n", t: "\t" };

// The inverse of STRING_ESCAPES, for any path that prints a string value back
// as Planes source. A single character-at-a-time pass, each character mapped
// independently — no ordering hazard, since backslash is just another entry.
export const STRING_UNESCAPE = {};
for (const [k, v] of Object.entries(STRING_ESCAPES)) {
  STRING_UNESCAPE[v] = "\\" + k;
}

// Raised on a backslash not followed by one of the four legal escapes. Carries
// the offending character; the lexer catches it and adds source position, the
// way planes_text.py raises a bare ValueError(nxt) that lexer.py catches.
export class StringEscapeError extends Error {
  constructor(ch) {
    super(ch);
    this.name = "StringEscapeError";
    this.badChar = ch;
  }
}

// `raw` is a STRING token's content between the delimiting quotes, exactly as
// the STRING regex matched it (an escape is still the two raw source
// characters). The regex only ever matches a backslash paired with a following
// character, so a backslash is never the last character of `raw`. Throws
// StringEscapeError(nxt) if `raw` contains a backslash not followed by a legal
// escape.
export function resolveStringEscapes(raw) {
  const cps = [...raw];
  const out = [];
  let i = 0;
  const n = cps.length;
  while (i < n) {
    const c = cps[i];
    if (c === "\\") {
      const nxt = cps[i + 1];
      if (!(nxt in STRING_ESCAPES)) throw new StringEscapeError(nxt);
      out.push(STRING_ESCAPES[nxt]);
      i += 2;
    } else {
      out.push(c);
      i += 1;
    }
  }
  return out.join("");
}

// `s`, re-escaped as the content of a Planes STRING literal — the exact text
// between the delimiting quotes that the STRING regex would need to see to
// resolve back to `s`. Iterates by code point so an astral character passes
// through whole rather than as two lone surrogates.
export function escapeStringLiteral(s) {
  let out = "";
  for (const c of s) {
    out += STRING_UNESCAPE[c] ?? c;
  }
  return out;
}

// ---- code-point semantics

// The code points of `s`, one string element each. `[...s]` iterates by code
// point, so an astral character is one element, not two UTF-16 units. This is
// what `for each … in <text>` walks (interp.py:850) and what text indexing
// uses.
export function codePoints(s) {
  return [...s];
}

// The number of code points in `s` — Planes text length. `count of "😀"` is 1;
// `s.length` (UTF-16 units) would wrongly give 2 (interp.py:766 uses Python's
// len(), a code-point count).
export function codePointLength(s) {
  let n = 0;
  for (const _ of s) n += 1;
  return n;
}
