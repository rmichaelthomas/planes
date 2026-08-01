// js/core_restrict.mjs — the core-restricted mode's policy, as pure data.
//
// grammar/core.json declares the PORT SURFACE: the keywords and builtins a
// second host must implement in order to run grammar/interp.planes. core_check.py
// enforces one direction of that claim — that interp.planes never MENTIONS a
// construct outside the declared core. It has never enforced the converse, which
// is the claim the file actually makes: THAT THE DECLARED CORE IS ENOUGH.
//
// A static pre-pass over the token stream would only reproduce core_check.py in a
// second language. Sufficiency is testable one way and one way only: build a host
// that implements the core and REFUSES everything else, then run interp.planes on
// it. That is what this module's map is for — it says which keywords a given AST
// node's construct spends, so the interpreter can refuse AT THE MOMENT OF
// EVALUATION rather than by reading the source.
//
// This file holds no copy of the core. `grammar/core.json`'s keyword and builtin
// lists are read at runtime (js/grammar_data.mjs's setCore/core, the same
// injection route the vocabulary takes) and never duplicated into a literal here
// — a second copy could disagree with the first, and then the checker would be
// measuring itself. What IS here is a different fact the core document does not
// carry: the association between an AST node kind and the keywords its construct
// is written with. Pure, no imports, browser-loadable.

// ================================================================ node -> keywords
//
// Every keyword a node kind can EVER carry, ignoring the node's own fields. The
// completeness check (coverageGaps, below) reads this: a keyword that appears in
// no entry here would be a construct the restricted mode is structurally blind
// to, and blindness is exactly how a sufficiency checker passes vacuously.
export const KEYWORDS_A_NODE_CAN_CARRY = {
  // --- statements
  Use: ["use", "with", "as"],
  Foreign: ["foreign", "from", "of", "doing"],
  Rule: ["rule", "not", "to"],
  FuncDef: ["to", "of"],
  Assign: ["let"],
  Give: ["give"],
  Show: ["show"],
  Why: ["why"],
  If: ["if", "else"],
  When: ["when", "else"],
  Fail: ["fail", "as"],
  ForEach: ["for", "each", "in", "where"],
  // --- expressions
  Num: [],
  Str: [],
  Var: [],
  Field: [],
  ListLit: [],
  RecordLit: [],
  Bool: ["true", "false"],
  Nothing: ["nothing"],
  IsNothing: ["nothing"],
  Not: ["not"],
  ListPlus: ["plus"],
  RecordUpdate: ["with"],
  BinOp: ["and", "or", "in", "first", "of"],
  Call: ["of"],
  Builtin: ["of"],
  Round: ["round", "to", "places"],
  WriteTo: ["write", "to"],
  OrFail: ["or", "fail", "as"],
  // --- parsed, never evaluated. `note:` and `because` are NAME tokens, not
  // reserved words, so neither carries a keyword; the nodes are listed so a
  // node kind reaching the checker is never an unknown one.
  Note: [],
  Because: [],
};

// `first N of L` is the one BinOp whose operator is spelled with two reserved
// words. The comparison operators (<, ==, ...) are OP tokens and no keyword.
const BINOP_KEYWORDS = {
  and: ["and"],
  or: ["or"],
  in: ["in"],
  first: ["first", "of"],
};

// One keyword is carried but NOT DISTINGUISHABLE at evaluation time, and saying
// so here is cheaper than discovering it from a wrong answer later. `round x to 2
// places` and `round x to 2` produce the identical Round node — parser.mjs's
// `this.accept("PLACES")` consumes the word and records nothing. Giving Round a
// field for it would change the AST's SHAPE, which grammar/parser.planes pins, so
// the honest reading is the conservative one: a Round node is treated as spending
// `places` whether the author wrote the word or not. `places` is in the core, so
// this over-reports nothing today; if it ever left the core, this is the entry
// that says the answer would be an over-approximation rather than an exact one.
export const APPROXIMATE_KEYWORDS = {
  places: "optional in the source and unrecorded in the AST; a Round node is " +
    "read as spending it either way",
};

// The keywords THIS node spends, given its own fields. A subset of
// KEYWORDS_A_NODE_CAN_CARRY[kind] by construction (asserted by the suite).
export function keywordsOf(node) {
  switch (node.__node) {
    case "Use":
      return node.renames.length ? ["use", "with", "as"] : ["use"];
    case "Foreign": {
      const out = ["foreign", "from"];
      if (node.params.length) out.push("of");
      if (node.declared) out.push("doing");
      return out;
    }
    case "Rule": {
      const out = ["rule"];
      if (node.assertion === "forbid") out.push("not");
      if (node.target !== null) out.push("to");
      return out;
    }
    case "FuncDef":
      return node.params.length ? ["to", "of"] : ["to"];
    case "Assign":
      return node.is_let ? ["let"] : [];
    case "Give":
      return ["give"];
    case "Show":
      return ["show"];
    case "Why":
      return ["why"];
    case "If":
      return node.els.length ? ["if", "else"] : ["if"];
    case "When":
      return node.els.length ? ["when", "else"] : ["when"];
    case "Fail":
      return ["fail", "as"];
    case "ForEach":
      return node.where !== null
        ? ["for", "each", "in", "where"]
        : ["for", "each", "in"];
    case "Bool":
      return node.value ? ["true"] : ["false"];
    case "Nothing":
    case "IsNothing":
      return ["nothing"];
    case "Not":
      return ["not"];
    case "ListPlus":
      return ["plus"];
    case "RecordUpdate":
      return ["with"];
    case "BinOp":
      return BINOP_KEYWORDS[node.op] ?? [];
    case "Call":
      return node.args.length ? ["of"] : [];
    case "Builtin":
      return ["of"];
    case "Round":
      return ["round", "to", "places"];
    case "WriteTo":
      return ["write", "to"];
    case "OrFail":
      return ["or", "fail", "as"];
    default:
      return [];
  }
}

// ================================================================ completeness
//
// A restricted mode is only worth running if it can SEE every construct it might
// have to refuse. This is the check that says so: hand it the language's own
// keyword list and it names the ones no node kind carries. The suite asserts the
// answer is empty. Failure mode 10 in reverse — an assertion whose subject cannot
// go missing without the assertion noticing.
export function coverageGaps(allKeywords) {
  const carried = new Set();
  for (const words of Object.values(KEYWORDS_A_NODE_CAN_CARRY)) {
    for (const w of words) carried.add(w);
  }
  return [...allKeywords].filter((k) => !carried.has(k)).sort();
}

// The node kinds that could possibly spend a keyword outside `coreKeywords`.
// Everything else takes the fast path in the interpreter and is never inspected.
// Derived from the core document, not hand-listed: widen or narrow core.json and
// this set follows, with no second place to edit.
export function suspectKinds(coreKeywords) {
  const out = new Set();
  for (const [kind, words] of Object.entries(KEYWORDS_A_NODE_CAN_CARRY)) {
    if (words.some((w) => !coreKeywords.has(w))) out.add(kind);
  }
  return out;
}

// ================================================================ source lines
//
// A refusal names the construct, the file and the LINE. Most AST nodes carry no
// line: `When`, `Assign` and `Why` — three of the four non-core keywords' carriers
// — have no `line` field at all, and giving them one would change the AST's shape,
// which grammar/parser.planes pins and invariant 3 forbids moving.
//
// So the line rides beside the AST rather than in it: a WeakMap the parser stamps
// at the one choke point every statement passes through. Off unless a restricted
// interpreter turns it on, so a normal run pays a single already-false boolean
// test per statement parsed and stores nothing.
const NODE_LINES = new WeakMap();
let recording = false;

export function recordLines(on) {
  recording = on;
}
export function recordingLines() {
  return recording;
}

// First write wins: the innermost parse that produced the node knows its own
// start token, and an enclosing rule that happens to return the same object
// must not overwrite it with a line further left.
export function noteLine(node, line) {
  if (!recording) return node;
  if (node !== null && typeof node === "object" && !NODE_LINES.has(node)) {
    NODE_LINES.set(node, line);
  }
  return node;
}

// The node's own start line where one was stamped, then its own `line` field for
// the nodes that have one, then null — the caller falls back to the enclosing
// statement's line and says which it used.
export function lineOf(node) {
  if (node === null || typeof node !== "object") return null;
  const stamped = NODE_LINES.get(node);
  if (stamped !== undefined) return stamped;
  return typeof node.line === "number" && node.line > 0 ? node.line : null;
}
