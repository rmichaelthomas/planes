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
});

// A word-argument verb's permitted set. Renamed from p5-adjacent names
// (`text`, `join`) that collide with Planes builtins (specification §6.5).
const WORDS = Object.freeze({
  cap: new Set(["butt", "round", "square"]),
  corner: new Set(["miter", "round", "bevel"]),
  align: new Set(["left", "center", "right"]),
});

// The twenty-six drawing verbs, `protocol` excluded (specification §11 —
// draw.planes wraps every verb in this table once and nothing else; a test
// reads VERBS directly rather than carrying a second hardcoded list).
export const VERBS = Object.freeze(Object.keys(ARITY));

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

  if (!(verb in ARITY)) {
    return err(
      "unknown-verb",
      `unrecognised drawing verb "${verb}" in "${line}"`,
      `use one of: ${VERBS.slice().sort().join(", ")}, or protocol`,
    );
  }

  const args = tokens.slice(2);
  const arity = ARITY[verb];
  if (args.length !== arity) {
    return err(
      "wrong-arity",
      `"${verb}" takes ${arity} argument${arity === 1 ? "" : "s"} in "${line}", got ${args.length}`,
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
  return { kind: "command", verb, args: nums };
}
