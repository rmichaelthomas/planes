// js/sound/protocol.mjs — the Planes Sound Protocol, version 1.
//
// Every sounding line begins with the word `sound`; anything else is prose and
// is never interpreted, so a stream that also carries `draw` lines (the whole
// reason both protocols use a prefix) reaches this parser as prose and is
// passed through untouched. See planes-sound-protocol-v1.md §§1-6 (normative)
// — this file implements the four-verb table, the `~`-prefixed number grammar,
// and the shape half of the refusal contract; the stream-level rules (the
// version declaration's ordering, the schedule, the domain refusals) live in
// stream.mjs, which is what actually walks a stream in order.
//
// Deliberately the same shape as js/paint/protocol.mjs, verb table and all:
// scripts/protocol_gen.mjs reads BOTH by importing VERBS/parseCommand and
// probing them, and by scanning both files for their error-construction call
// sites. A divergence in shape here would need a second generator, which the
// build this came from explicitly refuses. (That scanner is not comment-aware,
// which is why the name of the function it looks for is not written out in
// this paragraph — a mention in prose would be read as a call site.)

const ARITY = Object.freeze({
  wave: 1,
  gain: 1,
  // numerator denominator octave at lasts (§6.2). `lasts`, not `for`: `for`
  // is a reserved word in Planes and a helper parameter cannot be named it.
  note: 5,
  // `silence`, not `clear`: `clear` is already a drawing verb, and a program
  // emitting both protocols imports both helper libraries into one module
  // graph, where two helpers of one name is a collision the loader refuses.
  silence: 0,
});

// A word-argument verb's permitted set. Closed at three (§8): all three are
// exactly reproducible from a formula in both a live audio graph and a sample
// buffer, and anything band-limited would not be.
const WORDS = Object.freeze({
  wave: new Set(["sine", "triangle", "square"]),
});

// The four sounding verbs, `protocol` excluded — it is a stream directive, not
// a sounding verb, and a program states its version once, directly, as
// `show "sound protocol 1"`.
export const VERBS = Object.freeze(Object.keys(ARITY));

// No verb has an optional tail in version 1. Exported anyway, and empty, so
// scripts/protocol_gen.mjs reads the same three names off both protocol
// modules rather than branching on which one it is looking at.
export const OPTIONAL = Object.freeze({});

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

const SOUND_LINE = /^\s*sound\b/;

function parseProtocol(line, args) {
  if (args.length !== 1) {
    return err(
      "wrong-arity",
      `"protocol" takes exactly one argument (the version number) in "${line}", got ${args.length}`,
      `write sound protocol 1`,
    );
  }
  const n = parseNumber(args[0]);
  if (n === null || !Number.isInteger(n) || n <= 0) {
    return err(
      "bad-protocol-version",
      `"protocol" takes a positive whole number version in "${line}", got "${args[0]}"`,
      `write sound protocol 1`,
    );
  }
  return { kind: "command", verb: "protocol", args: [n] };
}

export function parseCommand(line) {
  if (!SOUND_LINE.test(line)) {
    return { kind: "prose", text: line };
  }

  const tokens = line.trim().split(/\s+/);
  const verb = tokens[1];

  if (verb === undefined) {
    return err(
      "unknown-verb",
      `"sound" with no verb in "${line}"`,
      `name a sounding verb after "sound", e.g. sound note 3 2 1 0 0.4`,
    );
  }

  if (verb === "protocol") {
    return parseProtocol(line, tokens.slice(2));
  }

  if (!(verb in ARITY)) {
    return err(
      "unknown-verb",
      `unrecognised sounding verb "${verb}" in "${line}"`,
      `use one of: ${VERBS.slice().sort().join(", ")}, or protocol`,
    );
  }

  const args = tokens.slice(2);
  const arity = ARITY[verb];
  if (args.length !== arity) {
    return err(
      "wrong-arity",
      `"${verb}" takes ${arity} argument${arity === 1 ? "" : "s"} in "${line}", got ${args.length}`,
      `check the argument count against the sound protocol's verb table`,
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
      `use digits with an optional leading - and a decimal point, e.g. 0.4 (no exponent notation; a leading ~ is fine)`,
    );
  }
  return { kind: "command", verb, args: nums };
}
