#!/usr/bin/env node
// scripts/protocol_gen.mjs — generates protocol/protocol.json and
// protocol/errors.json from the actual source (mirrors grammar_gen.py's
// ruling: generated, not hand-authored — see grammar/README.md's D2).
//
// The verb table (names, arities, word-argument sets) is read by IMPORTING
// js/paint/protocol.mjs and reading its live ARITY/WORDS/VERBS — this file
// carries no copy of the verb list, so a verb added to ARITY appears in
// protocol.json on the next run with no edit here.
//
// Error tags have no equivalent exported table (they are constructed inline
// at each `err(...)` / `errors.push({...})` call site), so they are found by
// a small source-level scanner — the JS analogue of grammar_gen.py's Python
// `ast.walk`, since this repo has no JS AST library and the drawing protocol
// is deliberately dependency-free. The scanner tracks JS lexical structure
// (strings, template literals, and `${ }` interpolation nesting) well enough
// to find every `err()`/`errors.push()` call and read its tag, message
// template, and (for protocol.mjs) fix clause — not a general JS parser, and
// it says so at every point it refuses rather than guesses.
//
// Verb groups are read directly out of planes-drawing-protocol-v1.md's own
// §6.1-§6.5 section structure (extractSpecGroups, below) — the one field in
// protocol.json with no source in protocol.mjs itself.
//
//   node scripts/protocol_gen.mjs            regenerate both files
//   node scripts/protocol_gen.mjs --check    regenerate into memory, diff
//                                             against the committed files,
//                                             exit non-zero on any difference
//
// protocol/protocol.json and protocol/errors.json are projections
// (protocol/README.md); neither is hand-edited.

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "..");

const PROTOCOL_SRC_PATH = path.join(REPO, "js", "paint", "protocol.mjs");
const STREAM_SRC_PATH = path.join(REPO, "js", "paint", "stream.mjs");
// planes-drawing-protocol-v1.md stays in place, unmodified (v2 §10.1) — the
// generator reads the v2 document, which is the v1 document plus its deltas,
// so a verb v1 already had keeps the same group it always had.
const SPEC_PATH = path.join(REPO, "planes-drawing-protocol-v2.md");
const PROTOCOL_JSON_PATH = path.join(REPO, "protocol", "protocol.json");
const ERRORS_JSON_PATH = path.join(REPO, "protocol", "errors.json");

// ================================================================ a small,
// scoped JS source scanner
//
// Not a general JS parser: it understands exactly enough JS lexical
// structure — line comments, single/double-quoted strings, template
// literals, and `${ }` interpolation nesting inside them — to correctly
// find where a bracketed span or a string/template literal ends despite
// nested parens, calls, and quotes inside an interpolation (e.g.
// `` `${[...WORDS[verb]].join(", ")}` ``). Every function below throws
// rather than guessing when it meets a shape it does not recognise.

function skipWs(src, i) {
  while (i < src.length && /\s/.test(src[i])) i += 1;
  return i;
}

// src[openIndex] is one of ( [ { — returns { end, splits } where `end` is
// the index of the matching close bracket and `splits` is the indices of
// every top-level (depth === 1) comma inside it. Treats a `${` inside a
// template literal as opening a nesting level ("interp") so a comma inside
// an interpolation's own nested string/call is never mistaken for one of
// this bracket's own separators.
function scanBracket(src, openIndex) {
  const pairs = { "(": ")", "[": "]", "{": "}" };
  const stack = [src[openIndex]];
  const splits = [];
  let mode = "code";
  let i = openIndex + 1;
  for (; i < src.length; i++) {
    const c = src[i];
    if (mode === "code") {
      if (c === "\\") { i += 1; continue; }
      if (c === '"') { mode = "dquote"; continue; }
      if (c === "'") { mode = "squote"; continue; }
      if (c === "`") { mode = "template"; continue; }
      if (c === "(" || c === "[" || c === "{") { stack.push(c); continue; }
      if (c === ")" || c === "]" || c === "}") {
        const top = stack.pop();
        if (top === "interp") { mode = "template"; continue; }
        const expected = { "(": ")", "[": "]", "{": "}" }[top];
        if (expected !== c) {
          throw new Error(`protocol_gen.mjs: mismatched bracket at index ${i} (expected '${expected}', found '${c}')`);
        }
        if (stack.length === 0) return { end: i, splits };
        continue;
      }
      if (stack.length === 1 && c === ",") { splits.push(i); continue; }
      continue;
    }
    if (mode === "dquote" || mode === "squote") {
      if (c === "\\") { i += 1; continue; }
      if ((mode === "dquote" && c === '"') || (mode === "squote" && c === "'")) mode = "code";
      continue;
    }
    // mode === "template"
    if (c === "\\") { i += 1; continue; }
    if (c === "`") { mode = "code"; continue; }
    if (c === "$" && src[i + 1] === "{") { stack.push("interp"); mode = "code"; i += 1; continue; }
    continue;
  }
  throw new Error(`protocol_gen.mjs: unterminated bracket starting at index ${openIndex}`);
}

// src[backtickIndex] === '`' — returns the index of the matching closing
// backtick, skipping over any `${ }` interpolation (via scanBracket) rather
// than stopping at a backtick that turns out to live inside one.
function scanTemplateLiteral(src, backtickIndex) {
  let i = backtickIndex + 1;
  for (; i < src.length; i++) {
    const c = src[i];
    if (c === "\\") { i += 1; continue; }
    if (c === "`") return i;
    if (c === "$" && src[i + 1] === "{") {
      const brace = scanBracket(src, i + 1);
      i = brace.end;
      continue;
    }
  }
  throw new Error(`protocol_gen.mjs: unterminated template literal starting at index ${backtickIndex}`);
}

// Renders a template literal's content as `text` with each `${expr}`
// replaced by `{expr}` (mirroring grammar/errors.json's template/slots
// shape) and `slots`, the list of interpolated expression source texts in
// order.
function readTemplateLiteral(src, backtickIndex) {
  const close = scanTemplateLiteral(src, backtickIndex);
  let text = "";
  const slots = [];
  let i = backtickIndex + 1;
  while (i < close) {
    const c = src[i];
    if (c === "\\") { text += src[i + 1]; i += 2; continue; }
    if (c === "$" && src[i + 1] === "{") {
      const brace = scanBracket(src, i + 1);
      const expr = src.slice(i + 2, brace.end).trim();
      text += "{" + expr + "}";
      slots.push(expr);
      i = brace.end + 1;
      continue;
    }
    text += c;
    i += 1;
  }
  return { text, slots, end: close + 1 };
}

function readQuoted(src, quoteIndex) {
  const q = src[quoteIndex];
  let i = quoteIndex + 1;
  for (; i < src.length; i++) {
    if (src[i] === "\\") { i += 1; continue; }
    if (src[i] === q) {
      const raw = src.slice(quoteIndex + 1, i);
      return { text: raw.replace(/\\(.)/g, "$1"), slots: [], end: i + 1 };
    }
  }
  throw new Error(`protocol_gen.mjs: unterminated string starting at index ${quoteIndex}`);
}

// Reads a string/template literal at `start`, optionally `+`-concatenated
// with further string/template literals (stream.mjs's unsupported-version
// message is built this way). Returns null — never guesses — when `start`
// is not the beginning of a string or template literal.
function readStringExpr(src, start) {
  let i = skipWs(src, start);
  let text = "";
  const slots = [];
  while (true) {
    if (src[i] === "`") {
      const r = readTemplateLiteral(src, i);
      text += r.text; slots.push(...r.slots); i = r.end;
    } else if (src[i] === '"' || src[i] === "'") {
      const r = readQuoted(src, i);
      text += r.text; i = r.end;
    } else {
      return null;
    }
    const afterLiteral = i;
    i = skipWs(src, i);
    if (src[i] === "+") { i = skipWs(src, i + 1); continue; }
    i = afterLiteral;
    break;
  }
  return { text, slots, end: i };
}

// Every top-level `function NAME(...) { ... }` span in `src`, by brace
// range — used the same way grammar_gen.py's `_enclosing_function` is, to
// name which function a call site sits inside.
function functionSpans(src) {
  const spans = [];
  const re = /function\s+(\w+)\s*\(/g;
  let m;
  while ((m = re.exec(src))) {
    const brace = src.indexOf("{", re.lastIndex);
    const { end } = scanBracket(src, brace);
    spans.push({ name: m[1], start: brace, end });
  }
  return spans;
}

function enclosingFunction(spans, pos) {
  let best = null;
  let bestSize = Infinity;
  for (const s of spans) {
    if (pos >= s.start && pos <= s.end && s.end - s.start < bestSize) {
      best = s.name;
      bestSize = s.end - s.start;
    }
  }
  return best;
}

function lineOf(src, pos) {
  let line = 1;
  for (let k = 0; k < pos; k++) if (src[k] === "\n") line += 1;
  return line;
}

// ================================================================ protocol.json

// The declaration verb (`protocol`) and the number grammar's descriptive
// prose are schema glue, not verb data — grammar_gen.py's own generators
// hand-author the equivalent ("A form inventory, not a formal grammar..." in
// generate_rules()) rather than deriving prose from source. The number
// pattern itself IS read from source below, not restated.
const DECLARATION = Object.freeze({
  verb: "protocol",
  arity: 1,
  argument: "positive integer version",
  note: "Recognised in version 1 so a version-1 consumer can refuse a version-2 stream. Not a drawing verb. Must precede the first drawing command.",
  example: "draw protocol 1",
});

// Groups come from planes-drawing-protocol-v1.md's own section 6 structure
// (§6.1 "Colour and line" through §6.5 "Text and canvas") — read here, not
// restated: each `### 6.N Title` heading names a group (slugified: lower-
// cased, spaces to hyphens) and its markdown table's rows name the verbs in
// it. If the spec gains a verb, moves one to a new section, or renames a
// section, this changes on the next run with no edit here.
//
// This document was not present anywhere in this repository when
// protocol_gen.mjs was first written — verified by a repo-wide search and
// `git log --all` at the time — so the first version of this generator
// derived groups from ARITY's own declared key order in js/paint/protocol.mjs
// instead. That derivation agreed with this file's real section order
// exactly, verb for verb, once the document became available.
function extractSpecGroups(specSrc) {
  const headingRe = /^### 6\.\d+ (.+)$/gm;
  const headings = [...specSrc.matchAll(headingRe)];
  if (headings.length === 0) {
    throw new Error(`protocol_gen.mjs: found no "### 6.N <title>" section headings in ${path.relative(REPO, SPEC_PATH)} — its shape changed; update the extractor`);
  }
  // The last §6.N section has no next §6.N heading to bound it, and the
  // document continues past it (§7 onward, including §10's p5-comparison
  // table, which also has single-word backtick-quoted cells) — without an
  // explicit outer bound the last section's body ran to end of file and
  // picked up stray matches from later sections that happened to start a
  // table row the same way. Bounded at the next level-2 (`## N.`) heading.
  const level2Re = /^## \d/gm;
  level2Re.lastIndex = headings[headings.length - 1].index;
  const nextLevel2 = level2Re.exec(specSrc);
  const afterSection6 = nextLevel2 ? nextLevel2.index : specSrc.length;

  const groups = [];
  const verbGroups = {};
  for (let i = 0; i < headings.length; i++) {
    const h = headings[i];
    const sectionStart = h.index + h[0].length;
    const sectionEnd = i + 1 < headings.length ? headings[i + 1].index : afterSection6;
    const body = specSrc.slice(sectionStart, sectionEnd);
    const group = h[1].trim().toLowerCase().replace(/\s+/g, "-");
    groups.push(group);
    const verbNames = [...body.matchAll(/^\|\s*`(\w+)`/gm)].map((vm) => vm[1]);
    if (verbNames.length === 0) {
      throw new Error(`protocol_gen.mjs: section "${h[1]}" in ${path.relative(REPO, SPEC_PATH)} names no verbs in backtick-quoted table cells — its shape changed; update the extractor`);
    }
    for (const v of verbNames) {
      if (v in verbGroups) {
        throw new Error(`protocol_gen.mjs: "${v}" appears in more than one §6 section (${verbGroups[v]} and ${group}) — its shape changed; update the extractor`);
      }
      verbGroups[v] = group;
    }
  }
  return { groups, verbGroups };
}

const { groups: GROUPS, verbGroups: VERB_GROUPS } = extractSpecGroups(readFileSync(SPEC_PATH, "utf-8"));

function extractNumberGrammar(src) {
  const m = src.match(/if \(!(\/(?:\\.|[^/])*\/)\.test\(stripped\)\) return null;/);
  if (!m) {
    throw new Error("protocol_gen.mjs: could not find parseNumber's validating regex in js/paint/protocol.mjs — its shape changed; update the extractor");
  }
  const pattern = m[1].slice(1, -1);
  return {
    pattern,
    tilde_prefix: "accepted and discarded; a rational whose decimal expansion does not terminate renders with a leading ~ elsewhere in the language",
    exponent_notation: false,
  };
}

// js/paint/protocol.mjs exports VERBS and parseCommand, but ARITY and WORDS
// are module-private (not exported) — the file is read-only this build, so
// a second export cannot be added to reach them directly. Rather than
// re-parsing the ARITY/WORDS object literals out of the source text, each
// verb's arity and argument shape is discovered by PROBING the real,
// exported, live parseCommand with crafted inputs and reading the answer
// back out of its own error messages — still the actual source's behaviour,
// still zero copies of the verb table, and it exercises the real function
// instead of a second reader of its internals.

// Comfortably above every real arity (max is 6, `triangle`) so the arity
// check always mismatches and returns "wrong-arity" naming the true count.
const ARITY_PROBE_ARGC = 64;

function probeArity(parseCommand, verb) {
  const dummy = Array.from({ length: ARITY_PROBE_ARGC }, (_, i) => String(i + 1)).join(" ");
  const result = parseCommand(`draw ${verb} ${dummy}`);
  if (result.kind !== "error" || result.tag !== "wrong-arity") {
    throw new Error(`protocol_gen.mjs: probing "${verb}" for arity did not produce wrong-arity (got ${JSON.stringify(result)}) — parseCommand's shape changed; update the prober`);
  }
  // A v2 verb with an optional tail (ellipse/rect) phrases this as "takes 4
  // to 5 arguments" rather than "takes 4 arguments" — the "to N" clause is
  // ignored here (OPTIONAL, read straight from the module below, is the
  // real source for it) and this still returns the BASE/required count.
  const m = result.message.match(/takes (\d+)(?: to \d+)? argument/);
  if (!m) throw new Error(`protocol_gen.mjs: could not read an argument count out of "${verb}"'s wrong-arity message: ${result.message}`);
  return Number(m[1]);
}

function probeArgumentShape(parseCommand, verb, arity) {
  if (arity === 0) return { arguments: [] };
  const tokens = Array.from({ length: arity }, () => "probe-token").join(" ");
  const result = parseCommand(`draw ${verb} ${tokens}`);
  if (result.kind !== "error") {
    throw new Error(`protocol_gen.mjs: probing "${verb}"'s argument shape unexpectedly succeeded on non-numeric, non-word tokens`);
  }
  if (result.tag === "bad-number") return { arguments: Array(arity).fill("number") };
  if (result.tag === "bad-word") {
    const m = result.message.match(/takes one of (.+?) in "/);
    if (!m) throw new Error(`protocol_gen.mjs: could not read the permitted word set out of "${verb}"'s bad-word message: ${result.message}`);
    return { arguments: ["word"], words: m[1].split(", ") };
  }
  throw new Error(`protocol_gen.mjs: probing "${verb}"'s argument shape produced an unrecognised tag "${result.tag}"`);
}

async function buildProtocolJson() {
  const src = readFileSync(PROTOCOL_SRC_PATH, "utf-8");
  const mod = await import(`file://${PROTOCOL_SRC_PATH}`);
  return protocolJsonFromModule(mod, src);
}

// Takes an already-imported protocol module (real or, in
// js/test/protocol_gen.test.mjs, a stub with the same VERBS/parseCommand
// shape) so invariant 5 — "a verb added to the source appears in the JSON
// with no edit here" — is testable without importing the real file twice.
// `verbGroups`/`groups` default to the real VERB_GROUPS/GROUPS but are
// overridable for the same reason: a test adding a verb to a stub module
// supplies a matching stub group map rather than editing the real one.
function protocolJsonFromModule(mod, src, { verbGroups = VERB_GROUPS, groups = GROUPS } = {}) {
  const { VERBS, parseCommand, OPTIONAL = {} } = mod;
  if (!VERBS || !parseCommand) {
    throw new Error("protocol_gen.mjs: module no longer exports VERBS/parseCommand — update the generator");
  }

  const verbs = VERBS.map((name) => {
    const group = verbGroups[name];
    if (!group) {
      throw new Error(`protocol_gen.mjs: verb "${name}" has no group assignment — add it to VERB_GROUPS`);
    }
    if (name === "label") {
      // label's arity is "2 + trailing free text", never reached through
      // the generic numeric probe below (parseCommand special-cases it
      // before the generic arity check) — the one exception §3.2 names
      // explicitly, not a copy of the verb table.
      return { name, arity: 2, arguments: ["number", "number"], trailing_text: true, group };
    }
    if (name === "gradient") {
      // gradient's arity depends on its own first (word) argument — a
      // second exception alongside label, for the same reason: never
      // reached through the generic numeric probe below, since probing it
      // with 64 numeric dummy tokens fails on the kind word, not on count.
      return {
        name,
        arity: 1,
        arguments: ["word"],
        variable_arity: true,
        variants: {
          linear: { arguments: Array(12).fill("number"), description: "x1 y1 x2 y2 L1 C1 H1 A1 L2 C2 H2 A2" },
          radial: { arguments: Array(11).fill("number"), description: "x y r L1 C1 H1 A1 L2 C2 H2 A2" },
        },
        group,
        _words: ["linear", "radial"],
      };
    }
    const arity = probeArity(parseCommand, name);
    const shape = probeArgumentShape(parseCommand, name, arity);
    const optional = OPTIONAL[name] || 0;
    if (optional > 0) {
      return {
        name,
        arity,
        arguments: [...shape.arguments, ...Array(optional).fill("number")],
        optional,
        group,
        _words: shape.words,
      };
    }
    return { name, arity, arguments: shape.arguments, group, _words: shape.words };
  });

  // Coverage: every verb exactly one group, every group non-empty
  // (§3.2's acceptance criterion, asserted here so a drift is a build
  // failure at generation time, not just at test time).
  const seenGroups = new Set(verbs.map((v) => v.group));
  for (const g of groups) {
    if (!seenGroups.has(g)) throw new Error(`protocol_gen.mjs: group "${g}" has no verbs assigned to it`);
  }
  for (const v of verbs) {
    if (!groups.includes(v.group)) throw new Error(`protocol_gen.mjs: verb "${v.name}" assigned to unknown group "${v.group}"`);
  }

  const word_arguments = {};
  for (const v of verbs) {
    if (v._words) word_arguments[v.name] = v._words;
    delete v._words;
  }

  return {
    format: 1,
    protocol: "planes-drawing",
    version: 2,
    prefix: "draw",
    prefix_note: "Every command line begins with this word. A line that does not is prose and is never interpreted.",
    line_shape: "draw <verb> <arg1> <arg2> ... <argN>",
    line_shape_note: "One command per line. Tokens (the prefix, the verb, and each argument) are separated by one or more whitespace characters. Each verb's own `arity` and `arguments` entry says how many argument tokens follow it and what kind each one is; for a verb listed in `word_arguments`, the permitted values for its `\"word\"`-typed argument are that entry, keyed by verb name.",
    declaration: DECLARATION,
    verbs,
    word_arguments,
    trailing_text_note: "The one verb with `trailing_text: true` (label) is the one exception to whitespace-tokenized arguments: its declared numeric arguments are followed by one whitespace run, then everything remaining on the line -- verbatim, including any further whitespace -- is the trailing argument. It is not itself tokenized.",
    number_grammar: extractNumberGrammar(src),
    groups: GROUPS,
  };
}

// ================================================================ errors.json

// Every `err("tag", \`headline\`, \`fix\`)` call site in protocol.mjs. The
// definition site itself (`function err(tag, headline, fix) {`) is excluded
// by checking what precedes the match.
function extractProtocolErrors(src, relPath) {
  const spans = functionSpans(src);
  const entries = [];
  const re = /\berr\(/g;
  let m;
  while ((m = re.exec(src))) {
    if (src.slice(Math.max(0, m.index - 9), m.index) === "function ") continue;

    let i = skipWs(src, m.index + 4); // right after "err("
    const tag = readStringExpr(src, i);
    if (!tag) throw new Error(`protocol_gen.mjs: err() at ${relPath}:${lineOf(src, m.index)} — tag argument is not a string literal`);
    i = skipWs(src, tag.end);
    if (src[i] !== ",") throw new Error(`protocol_gen.mjs: err() at ${relPath}:${lineOf(src, m.index)} — expected ',' after tag`);
    i = skipWs(src, i + 1);

    const headline = readStringExpr(src, i);
    if (!headline) throw new Error(`protocol_gen.mjs: err() at ${relPath}:${lineOf(src, m.index)} — headline argument is not a string/template literal`);
    i = skipWs(src, headline.end);

    let fix = null;
    if (src[i] === ",") {
      i = skipWs(src, i + 1);
      if (src[i] !== ")") {
        fix = readStringExpr(src, i);
        if (!fix) throw new Error(`protocol_gen.mjs: err() at ${relPath}:${lineOf(src, m.index)} — fix argument is not a string/template literal`);
      }
    }

    entries.push({
      kind: "error",
      tag: tag.text,
      source: `${relPath}:${lineOf(src, m.index)}`,
      raised_in: enclosingFunction(spans, m.index),
      template: headline.text,
      slots: headline.slots,
      fix: fix ? fix.text : undefined,
    });
  }
  return entries;
}

// Every `tag: "literal-tag"` site in stream.mjs paired with its object
// literal's `message:` value. `tag: cmd.tag` (line 83, re-pushing an already
// classified protocol.mjs error) is not a literal and is correctly skipped
// by the regex requiring a quoted string right after `tag:`.
function extractStreamErrors(src, relPath) {
  const spans = functionSpans(src);
  const entries = [];
  const re = /\btag:\s*"([a-zA-Z0-9_-]+)"/g;
  let m;
  while ((m = re.exec(src))) {
    const tag = m[1];
    const afterTag = m.index + m[0].length;
    const window = src.slice(afterTag, afterTag + 60);
    const rel = window.indexOf("message:");
    if (rel === -1) {
      throw new Error(`protocol_gen.mjs: tag "${tag}" at ${relPath}:${lineOf(src, m.index)} has no nearby "message:" — extraction assumption broken`);
    }
    const valueStart = skipWs(src, afterTag + rel + "message:".length);
    const message = readStringExpr(src, valueStart);
    if (!message) throw new Error(`protocol_gen.mjs: tag "${tag}" at ${relPath}:${lineOf(src, m.index)} — message is not a string/template literal`);

    entries.push({
      kind: "error",
      tag,
      source: `${relPath}:${lineOf(src, m.index)}`,
      raised_in: enclosingFunction(spans, m.index),
      template: message.text,
      slots: message.slots,
    });
  }
  return entries;
}

function assignIds(entries, fileStem) {
  entries.sort((a, b) => {
    const la = Number(a.source.split(":")[1]);
    const lb = Number(b.source.split(":")[1]);
    return la - lb;
  });
  for (const e of entries) {
    e.id = e.raised_in ? `${fileStem}.${e.tag}.${e.raised_in}` : `${fileStem}.${e.tag}`;
  }
  const counts = {};
  for (const e of entries) counts[e.id] = (counts[e.id] || 0) + 1;
  const seen = {};
  for (const e of entries) {
    if (counts[e.id] > 1) {
      seen[e.id] = (seen[e.id] || 0) + 1;
      e.id = `${e.id}-${seen[e.id]}`;
    }
  }
  return entries;
}

function buildErrorsJson() {
  const protocolSrc = readFileSync(PROTOCOL_SRC_PATH, "utf-8");
  const streamSrc = readFileSync(STREAM_SRC_PATH, "utf-8");

  const protocolEntries = assignIds(extractProtocolErrors(protocolSrc, "js/paint/protocol.mjs"), "protocol");
  const streamEntries = assignIds(extractStreamErrors(streamSrc, "js/paint/stream.mjs"), "stream");
  const entries = [...protocolEntries, ...streamEntries];

  const tags = {};
  for (const e of entries) {
    tags[e.tag] = tags[e.tag] || [];
    tags[e.tag].push(e.source);
  }

  return {
    format: 1,
    generated_by: "scripts/protocol_gen.mjs",
    source_files: ["js/paint/protocol.mjs", "js/paint/stream.mjs"],
    count: entries.length,
    entries,
    tags,
  };
}

// ================================================================ CLI

function serialize(doc) {
  return JSON.stringify(doc, null, 2) + "\n";
}

function readExisting(p) {
  return existsSync(p) ? readFileSync(p, "utf-8") : null;
}

function firstDiffLine(a, b) {
  const al = (a || "").split("\n");
  const bl = b.split("\n");
  for (let i = 0; i < Math.max(al.length, bl.length); i++) {
    if (al[i] !== bl[i]) {
      return `  line ${i + 1}:\n    committed:  ${JSON.stringify(al[i] ?? "<eof>")}\n    generated:  ${JSON.stringify(bl[i] ?? "<eof>")}`;
    }
  }
  return null;
}

async function main() {
  const check = process.argv.includes("--check");

  const protocolDoc = await buildProtocolJson();
  const errorsDoc = buildErrorsJson();
  const protocolText = serialize(protocolDoc);
  const errorsText = serialize(errorsDoc);

  if (!check) {
    writeFileSync(PROTOCOL_JSON_PATH, protocolText);
    writeFileSync(ERRORS_JSON_PATH, errorsText);
    console.log(`wrote ${path.relative(REPO, PROTOCOL_JSON_PATH)} (${protocolDoc.verbs.length} verbs)`);
    console.log(`wrote ${path.relative(REPO, ERRORS_JSON_PATH)} (${errorsDoc.count} entries, ${Object.keys(errorsDoc.tags).length} distinct tags)`);
    return 0;
  }

  let diffs = 0;
  for (const [p, generated, label] of [
    [PROTOCOL_JSON_PATH, protocolText, "protocol/protocol.json"],
    [ERRORS_JSON_PATH, errorsText, "protocol/errors.json"],
  ]) {
    const existing = readExisting(p);
    if (existing === generated) {
      console.log(`${label}: up to date`);
      continue;
    }
    diffs += 1;
    console.log(`${label}: OUT OF DATE — regenerate with node scripts/protocol_gen.mjs`);
    const d = firstDiffLine(existing, generated);
    if (d) console.log(d);
  }
  if (diffs) console.log(`\n${diffs} check(s) failed.`);
  return diffs;
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  main().then((code) => process.exit(code));
}

export {
  scanBracket,
  readStringExpr,
  extractProtocolErrors,
  extractStreamErrors,
  extractSpecGroups,
  buildProtocolJson,
  protocolJsonFromModule,
  buildErrorsJson,
  probeArity,
  probeArgumentShape,
  VERB_GROUPS,
  GROUPS,
};
