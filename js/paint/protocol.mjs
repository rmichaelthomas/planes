// js/paint/protocol.mjs — the Planes Drawing Protocol, version 1 (A.5).
//
// Every drawing line begins with the word `draw`; anything else is prose and
// is never interpreted, so a program printing the word `end` or `close`
// cannot silently affect a picture, and a mistyped command is an error rather
// than a caption. See planes-drawing-protocol-v1.md §§1-7 (normative) —
// this file implements the twenty-six-verb table, the `~`-prefixed number
// grammar, and the refusal contract; the stream-level rules (the version
// declaration's ordering, path lifecycle, transform balance) live in
// painter.mjs, which is what actually walks a stream in order.

const ARITY = Object.freeze({
  stroke: 4,
  fill: 4,
  width: 1,
  cap: 1,
  corner: 1,
  line: 4,
  rect: 4,
  circle: 3,
  ellipse: 4,
  arc: 5,
  triangle: 6,
  shape: 0,
  vertex: 2,
  curve: 6,
  close: 0,
  end: 0,
  push: 0,
  pop: 0,
  translate: 2,
  rotate: 1,
  scale: 2,
  size: 1,
  align: 1,
  background: 3,
  clear: 0,
  // `label` is arity "2 + rest" and is parsed separately (parseLabel) — it
  // is still one of the twenty-six verbs, so it belongs in this table for
  // VERBS to be complete, but never reached through the generic numeric path.
  label: 2,
  // v2 additions (planes-drawing-protocol-v2.md §6.6, §6.2). `gradient` is
  // arity "1 word + variable numeric" and is parsed separately
  // (parseGradient), for the same reason `label` is — it still belongs here
  // for VERBS to be complete.
  gradient: 12,
  shadow: 6,
  blend: 1,
  clip: 0,
  unclip: 0,
  alpha: 1,
  dash: 2,
});

// A verb's ADDITIONAL numeric arguments beyond its base ARITY, each
// defaulting to 0 when omitted (v2 §9.1 — rotation on `ellipse` and `rect`).
// parseCommand pads a short call out to full (arity + OPTIONAL[verb]) length
// with zeros, so a sink's method always receives the same argument count
// regardless of whether the caller supplied the optional tail.
const OPTIONAL = Object.freeze({
  ellipse: 1,
  rect: 1,
});

// A word-argument verb's permitted set. Renamed from p5-adjacent names
// (`text`, `join`) that collide with Planes builtins (specification §6.5).
const WORDS = Object.freeze({
  cap: new Set(["butt", "round", "square"]),
  corner: new Set(["miter", "round", "bevel"]),
  align: new Set(["left", "center", "right"]),
  blend: new Set(["normal", "add"]),
});

// gradient's own word set — not in WORDS because gradient's shape (word,
// then a variable run of numbers depending on which word) does not fit the
// generic "N numbers, or one word" cases WORDS/ARITY already cover; it gets
// its own parse function, parseGradient, below (the second verb after
// `label` whose arity depends on its own content).
const GRADIENT_KINDS = Object.freeze({
  linear: 4, // x1 y1 x2 y2, then 8 stop numbers
  radial: 3, // x y r, then 8 stop numbers
});

// The thirty-three drawing verbs, `protocol` excluded (specification §11 —
// draw.planes wraps every verb in this table once and nothing else; a test
// reads VERBS directly rather than carrying a second hardcoded list).
export const VERBS = Object.freeze(Object.keys(ARITY));

// Exported so scripts/protocol_gen.mjs can read a verb's optional tail
// directly rather than re-deriving it from wrong-arity message text.
export { OPTIONAL };

function err(tag, headline, fix) {
  return { kind: "error", tag, message: fix ? `${headline}\n  try: ${fix}` : headline };
}

// An optional leading `-`, digits, optionally a `.` and more digits. No
// exponent notation. A leading `~` (an exact rational's inexact rendering
// elsewhere in the language) is accepted and discarded before parsing.
function parseNumber(token) {
  const stripped = token.startsWith("~") ? token.slice(1) : token;
  if (!/^-?\d+(\.\d+)?$/.test(stripped)) return null;
  return Number(stripped);
}

const DRAW_LINE = /^\s*draw\b/;

function parseProtocol(line, args) {
  if (args.length !== 1) {
    return err(
      "wrong-arity",
      `"protocol" takes exactly one argument (the version number) in "${line}", got ${args.length}`,
      `write draw protocol 1`,
    );
  }
  const n = parseNumber(args[0]);
  if (n === null || !Number.isInteger(n) || n <= 0) {
    return err(
      "bad-protocol-version",
      `"protocol" takes a positive whole number version in "${line}", got "${args[0]}"`,
      `write draw protocol 1`,
    );
  }
  return { kind: "command", verb: "protocol", args: [n] };
}

function parseLabel(line) {
  const afterLabel = line.replace(/^\s*draw\s+label\s*/, "");
  const m = /^(\S+)\s+(\S+)\s+(\S.*)$/.exec(afterLabel);
  if (!m) {
    return err(
      "wrong-arity",
      `"label" takes two numbers and text to draw in "${line}"`,
      `write draw label 8 16 score: 42`,
    );
  }
  const [, xTok, yTok, text] = m;
  const x = parseNumber(xTok);
  const y = parseNumber(yTok);
  if (x === null || y === null) {
    const bad = x === null ? xTok : yTok;
    return err(
      "bad-number",
      `"${bad}" is not a valid number in "${line}"`,
      `use digits with an optional leading - and a decimal point, e.g. 12.5 (no exponent notation; a leading ~ is fine)`,
    );
  }
  return { kind: "command", verb: "label", args: [x, y], text };
}

// gradient's kind word decides how many numbers follow it (§5.2): `linear`
// takes 4 geometry numbers then 8 stop numbers, `radial` takes 3 then 8. Both
// endpoints are OKLCH: L1 C1 H1 A1 L2 C2 H2 A2 — stream.mjs interpolates them
// into sixteen stops (§5.1); this function only validates shape and reads
// the raw numbers through.
function parseGradient(line) {
  const afterVerb = line.replace(/^\s*draw\s+gradient\s*/, "");
  const tokens = afterVerb.trim().length ? afterVerb.trim().split(/\s+/) : [];
  const kindWord = tokens[0];
  if (kindWord === undefined || !(kindWord in GRADIENT_KINDS)) {
    return err(
      "bad-word",
      `"gradient" takes one of ${Object.keys(GRADIENT_KINDS).join(", ")} in "${line}", got "${kindWord ?? ""}"`,
      `use one of: ${Object.keys(GRADIENT_KINDS).join(", ")}`,
    );
  }
  const rest = tokens.slice(1);
  const expected = GRADIENT_KINDS[kindWord] + 8;
  if (rest.length !== expected) {
    return err(
      "wrong-arity",
      `"gradient ${kindWord}" takes ${expected} numeric arguments in "${line}", got ${rest.length}`,
      `write draw gradient ${kindWord} ${Array(expected).fill("N").join(" ")}`,
    );
  }
  const nums = rest.map(parseNumber);
  const badIndex = nums.findIndex((n) => n === null);
  if (badIndex !== -1) {
    return err(
      "bad-number",
      `"${rest[badIndex]}" is not a valid number in "${line}"`,
      `use digits with an optional leading - and a decimal point, e.g. 12.5 (no exponent notation; a leading ~ is fine)`,
    );
  }
  return { kind: "command", verb: "gradient", args: [kindWord, ...nums] };
}

export function parseCommand(line) {
  if (!DRAW_LINE.test(line)) {
    return { kind: "prose", text: line };
  }

  const tokens = line.trim().split(/\s+/);
  const verb = tokens[1];

  if (verb === undefined) {
    return err(
      "unknown-verb",
      `"draw" with no verb in "${line}"`,
      `name a drawing verb after "draw", e.g. draw circle 200 100 40`,
    );
  }

  if (verb === "protocol") {
    return parseProtocol(line, tokens.slice(2));
  }

  if (verb === "label") {
    return parseLabel(line);
  }

  if (verb === "gradient") {
    return parseGradient(line);
  }

  if (!(verb in ARITY)) {
    return err(
      "unknown-verb",
      `unrecognised drawing verb "${verb}" in "${line}"`,
      `use one of: ${VERBS.slice().sort().join(", ")}, or protocol`,
    );
  }

  const args = tokens.slice(2);
  const arity = ARITY[verb];
  const optional = OPTIONAL[verb] || 0;
  const maxArity = arity + optional;
  if (optional === 0 && args.length !== arity) {
    return err(
      "wrong-arity",
      `"${verb}" takes ${arity} argument${arity === 1 ? "" : "s"} in "${line}", got ${args.length}`,
      `check the argument count against the drawing protocol's verb table`,
    );
  }
  if (optional > 0 && (args.length < arity || args.length > maxArity)) {
    return err(
      "wrong-arity",
      `"${verb}" takes ${arity} to ${maxArity} arguments in "${line}", got ${args.length}`,
      `check the argument count against the drawing protocol's verb table`,
    );
  }

  if (verb in WORDS) {
    const word = args[0];
    if (!WORDS[verb].has(word)) {
      return err(
        "bad-word",
        `"${verb}" takes one of ${[...WORDS[verb]].join(", ")} in "${line}", got "${word}"`,
        `use one of: ${[...WORDS[verb]].join(", ")}`,
      );
    }
    return { kind: "command", verb, args: [word] };
  }

  const nums = args.map(parseNumber);
  const badIndex = nums.findIndex((n) => n === null);
  if (badIndex !== -1) {
    return err(
      "bad-number",
      `"${args[badIndex]}" is not a valid number in "${line}"`,
      `use digits with an optional leading - and a decimal point, e.g. 12.5 (no exponent notation; a leading ~ is fine)`,
    );
  }
  // A caller who omitted the optional tail gets it back defaulted to 0
  // (v2 section 9.1), so a sink method always receives (arity + optional)
  // arguments and never has to branch on how many were actually written.
  while (nums.length < maxArity) nums.push(0);
  return { kind: "command", verb, args: nums };
}
