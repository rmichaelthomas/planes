// js/paint/why.mjs — an answer card from a derivation.
//
// Given the derivation node the interpreter kept for one emitted line
// (js/interp.mjs's `trace`), this builds the small structure a page renders:
// what the value is, the one step it came from, the author's own words where
// a name carries them, whether the chain reaches an approximation, and where
// it ends.
//
// ONE STEP, THEN EXPAND. The language's own `why` shows one step, and so does
// this. A derivation graph for a single garden mark is hundreds of nodes deep
// and rendering all of it answers a question nobody asked; `expand` walks one
// level further on request, which is the same discipline, offered twice.
//
// `because` OUTRANKS ARITHMETIC. Where a step names a variable and that
// variable carries a `because`, the author's sentence is the first row of the
// card and the arithmetic is underneath it. The annotation is not part of the
// derivation graph — it never was, deliberately (interp.py: "display text
// beside it — never an input the derivation graph carries") — so it is looked
// up by name here, from the annotations the run reported.
//
// ASKING PERFORMS NOTHING. Everything below reads a value the run already
// produced. Nothing here runs a program, and the page proves it: the effect
// surface beside the canvas is computed from the source and does not change
// when a question is asked.

// The kinds of node that end a chain — nothing derived them, they entered the
// program.
const ORIGIN_KINDS = new Set(["literal", "effect"]);

// A name whose derivation is the whole answer: the tick and the seed are what
// the page put in, and a chain that reaches one has reached the edge of the
// program.
const INPUT_NAMES = new Set(["tick", "seed", "keys", "pointer", "state", "event"]);

function fmtNumber(v) {
  if (typeof v !== "number") return String(v);
  if (Number.isInteger(v)) return String(v);
  return String(Math.round(v * 1000) / 1000);
}

export function valueText(node) {
  const v = node && node.value;
  if (v === null || v === undefined) return "nothing";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "string") return v.length > 40 ? `${v.slice(0, 39)}…` : v;
  if (typeof v === "number") return fmtNumber(v);
  // A Planes number carries its own text(); a list or record is described by
  // shape, the same way the interpreter's own `fmt` does.
  if (typeof v === "object" && typeof v.text === "function") return v.text();
  if (Array.isArray(v)) return `[${v.length} items]`;
  return "{record}";
}

// A node's inputs, tolerant of both shapes: interp.py's Deriv is a dataclass
// and interp.mjs's is a class, and both expose `inputs`.
const inputsOf = (node) => (node && Array.isArray(node.inputs) ? node.inputs : []);

// Does anything in this chain carry an approximation? `sine` is the only
// source in the language, and the property propagates through arithmetic —
// which is the whole point of the property, so the badge is honest about the
// whole chain rather than about the last step.
export function reachesApproximation(node, seen = new Set()) {
  if (!node || seen.has(node)) return false;
  seen.add(node);
  const v = node.value;
  if (v && typeof v === "object" && v.approx) return true;
  if (typeof node.label === "string" && node.label.startsWith("sine of")) return true;
  return inputsOf(node).some((n) => reachesApproximation(n, seen));
}

// THE PARTS OF A DRAWN LINE. A drawing command reaches the trace as one
// string: `"draw ellipse " + text of px + " " + text of py + ...`. Following
// the first input down that tree arrives at the literal `"draw ellipse "` and
// answers nothing — the interesting derivations are the NUMBERS hanging off
// each `text of`, and they are what a reader is pointing at when they click a
// petal.
//
// This finds them, in the order they appear in the line, so a card can say
// "x 314.2, from the plant's lean" rather than "a string, from a string".
export function numericParts(node, found = [], seen = new Set()) {
  if (!node || seen.has(node)) return found;
  seen.add(node);
  if (node.kind === "op" && node.label === "text of") {
    const inner = inputsOf(node)[0];
    if (inner) found.push(inner);
    return found;
  }
  // Only descend through string assembly. Anything else is already a value,
  // not a line being built out of values.
  if (node.kind === "op" && node.label === "+") {
    for (const n of inputsOf(node)) numericParts(n, found, seen);
  }
  return found;
}

// Where the chain ends. A BREADTH-first search, not a walk down first
// inputs: a drawing line's first input is the literal `"draw ellipse "` and
// following it says only that a string is a string. The question is whether
// ANYTHING in the chain came from outside the arithmetic, and the answer is
// the tick, the seed, an effect, or nothing at all.
export function originOf(node) {
  const seen = new Set();
  const queue = [node];
  let literal = null;
  while (queue.length) {
    const current = queue.shift();
    if (!current || seen.has(current)) continue;
    seen.add(current);
    if (current.kind === "name" && INPUT_NAMES.has(current.label)) {
      return { kind: "input", name: current.label, node: current };
    }
    if (current.kind === "effect") return { kind: "effect", node: current };
    if (current.kind === "literal" && literal === null) literal = current;
    queue.push(...inputsOf(current));
  }
  if (literal) return { kind: "literal", node: literal };
  return { kind: "leaf", node };
}

// The one step: what this value came from, said once. A `name` node's own
// input is the expression that produced it, and that is the interesting step
// — the same unwrapping `explain` does before printing.
function stepOf(node) {
  const inner = node && node.kind === "name" && inputsOf(node).length ? inputsOf(node)[0] : node;
  if (!inner) return null;
  return {
    label: inner.label,
    kind: inner.kind,
    value: valueText(inner),
    inputs: inputsOf(inner).map((n) => ({ label: n.label, kind: n.kind, value: valueText(n) })),
  };
}

// Every name in the chain that carries a `because`, nearest first. The
// author's words for the thing being asked about come before the author's
// words for something it happens to be built out of.
export function annotationsInChain(node, annotations, limit = 3) {
  const found = [];
  const seen = new Set();
  const queue = [node];
  while (queue.length && found.length < limit) {
    const current = queue.shift();
    if (!current || seen.has(current)) continue;
    seen.add(current);
    if (current.kind === "name" && annotations && annotations[current.label] !== undefined) {
      found.push({ name: current.label, text: annotations[current.label], value: valueText(current) });
    }
    queue.push(...inputsOf(current));
  }
  return found;
}

// The card. `title` is the page's business (it knows a bee from a flower);
// everything else here is read off the derivation.
export function card(node, { annotations = {}, title = null, line = null, sourceText = null } = {}) {
  // A drawing line is answered by its NUMBERS, one row each. Anything else is
  // answered by itself.
  const parts = numericParts(node);
  const subject = parts.length ? parts[parts.length - 1] : node;
  const step = stepOf(subject);
  const origin = originOf(node);
  const because = annotationsInChain(node, annotations);
  const approximate = reachesApproximation(node);

  const originText =
    origin.kind === "input"
      ? origin.name === "seed"
        ? `the seed — you chose this. Nothing outside the program was touched.`
        : origin.name === "tick"
          ? `the tick — the day on the scrubber, and nothing else.`
          : `${origin.name} — an input this page handed the program.`
      : origin.kind === "literal"
        ? `a number written in the program: ${valueText(origin.node)}`
        : origin.kind === "effect"
          ? `${origin.node.label} — something outside the program`
          : `${origin.node ? origin.node.label : "nothing outside the program"}`;

  return {
    title,
    line,
    sourceText,
    value: valueText(node),
    // One row per number in the line, each with the one step it came from —
    // the shape the card actually renders.
    rows: parts.map((p) => ({ value: valueText(p), step: stepOf(p), approximate: reachesApproximation(p) })),
    step,
    because,
    approximate,
    approximateNote: approximate
      ? "approximate, and identical on every machine"
      : null,
    origin: { kind: origin.kind, text: originText },
  };
}

// One level further down, on request: the inputs of the step already shown,
// each as its own small card. This is `expand`, and it is deliberately not
// recursive — a reader who wants two levels asks twice.
export function expand(node, { annotations = {} } = {}) {
  const parts = numericParts(node);
  const subject = parts.length ? parts[parts.length - 1] : node;
  const inner =
    subject && subject.kind === "name" && inputsOf(subject).length ? inputsOf(subject)[0] : subject;
  return inputsOf(inner).map((n) => card(n, { annotations }));
}
