// js/test/protocol_gen.test.mjs — scripts/protocol_gen.mjs generates
// protocol/protocol.json and protocol/errors.json from js/paint/protocol.mjs
// and js/paint/stream.mjs; it must never carry its own copy of the verb
// table, and --check must actually gate drift.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildProtocolJson,
  buildErrorsJson,
  protocolJsonFromModule,
  extractSpecGroups,
  probeArity,
  probeArgumentShape,
  VERB_GROUPS,
  GROUPS,
} from "../../scripts/protocol_gen.mjs";
import { VERBS, parseCommand } from "../paint/protocol.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "..", "..");

function readJson(relPath) {
  return JSON.parse(readFileSync(path.join(REPO, relPath), "utf-8"));
}

// ---- correspondence (§7.2 A) ------------------------------------------

test("protocol.json's verb set equals the real VERBS, no extras, no omissions", () => {
  const doc = readJson("protocol/protocol.json");
  const names = doc.verbs.map((v) => v.name);
  assert.deepEqual(names, [...VERBS]);
});

test("every verb's arity in protocol.json agrees with what parseCommand itself enforces", () => {
  const doc = readJson("protocol/protocol.json");
  for (const v of doc.verbs) {
    // label's declared arity is "2 plus trailing free text" (§3.2's one
    // named exception), and gradient's is "1 word, then a run of numbers
    // depending on the word" (a second exception, v2 §5.2) — neither fits
    // "exactly arity, or an error" at all; both get their own dedicated
    // tests below. A verb with an OPTIONAL tail (v2's `ellipse`/`rect`)
    // rejects one UNDER its base arity and one OVER its max, not one over
    // its base.
    if (v.trailing_text || v.variable_arity) continue;
    const over = v.arity + (v.optional || 0) + 1;
    const cases = v.arity === 0 ? [over] : [v.arity - 1, over];
    for (const argc of cases) {
      const args = Array.from({ length: argc }, () => "1").join(" ");
      const result = parseCommand(`draw ${v.name} ${args}`.trim());
      assert.equal(result.kind, "error", `${v.name} with ${argc} args should error`);
    }
  }
});

test("every word_arguments set in protocol.json agrees with parseCommand's own bad-word rejection", () => {
  const doc = readJson("protocol/protocol.json");
  for (const [verb, words] of Object.entries(doc.word_arguments)) {
    // gradient's word decides how many numbers follow it, so `draw gradient
    // <word>` alone is not a complete command — its own dedicated test below
    // covers this instead of the generic "word alone is a command" case.
    if (verb === "gradient") continue;
    for (const word of words) {
      const result = parseCommand(`draw ${verb} ${word}`);
      assert.equal(result.kind, "command", `${verb} ${word} should be accepted`);
    }
    const result = parseCommand(`draw ${verb} not-a-real-word`);
    assert.equal(result.tag, "bad-word");
  }
});

test("gradient's word_arguments entry (linear, radial) matches parseCommand's own kind check", () => {
  const doc = readJson("protocol/protocol.json");
  assert.deepEqual(doc.word_arguments.gradient, ["linear", "radial"]);
  const result = parseCommand("draw gradient conic 1 2 3 4 5 6 7 8 9 10 11 12");
  assert.equal(result.tag, "bad-word");
});

test("draw.planes has exactly one helper per verb, protocol excluded, no extras", () => {
  const src = readFileSync(path.join(REPO, "paint", "draw.planes"), "utf-8");
  const helpers = [...src.matchAll(/^to (\w+)/gm)].map((m) => m[1]);
  assert.deepEqual(new Set(helpers), new Set(VERBS));
  assert.ok(!helpers.includes("protocol"));
});

test("groups: every verb has exactly one group, every group is non-empty", () => {
  const doc = readJson("protocol/protocol.json");
  assert.deepEqual(doc.groups, GROUPS);
  const byGroup = new Map(GROUPS.map((g) => [g, 0]));
  for (const v of doc.verbs) {
    assert.ok(GROUPS.includes(v.group), `${v.name} has an unknown group "${v.group}"`);
    byGroup.set(v.group, byGroup.get(v.group) + 1);
  }
  for (const g of GROUPS) {
    assert.ok(byGroup.get(g) > 0, `group "${g}" has no verbs`);
  }
});

test("groups and their verbs match planes-drawing-protocol-v2.md's §6.1-§6.6 tables directly", () => {
  const specSrc = readFileSync(path.join(REPO, "planes-drawing-protocol-v2.md"), "utf-8");
  const { groups, verbGroups } = extractSpecGroups(specSrc);
  assert.deepEqual(groups, GROUPS);
  assert.deepEqual(verbGroups, VERB_GROUPS);
  assert.equal(Object.keys(verbGroups).length, VERBS.length);
});

test("planes-drawing-protocol-v1.md is unmodified and still describes its own 26-verb, 5-group world", () => {
  const specSrc = readFileSync(path.join(REPO, "planes-drawing-protocol-v1.md"), "utf-8");
  const { groups, verbGroups } = extractSpecGroups(specSrc);
  assert.deepEqual(groups, ["colour-and-line", "shapes", "paths", "transforms", "text-and-canvas"]);
  assert.equal(Object.keys(verbGroups).length, 26);
  assert.ok(!("gradient" in verbGroups), "v1 has no v2 verbs");
});

test("a §6 section's group assignment does not leak past the last one into later document sections", () => {
  // Regression: the first version of extractSpecGroups bounded every §6.N
  // section by the NEXT §6.N heading, so the LAST section (§6.5) ran to end
  // of file and picked up single-word backtick-quoted table cells from later
  // sections (§10's p5-comparison table has rows like "| `cap` / `corner` |
  // ..." whose first cell collides with a real verb name), silently
  // overwriting the correct earlier group for `cap`, `shape`, `push`, and
  // `translate`.
  const stubSpec = [
    "### 6.1 Colour and line",
    "",
    "| Verb | Arguments | |",
    "|---|---|---|",
    "| `cap` | word | how a line's ends are drawn |",
    "",
    "### 6.5 Text and canvas",
    "",
    "| Verb | Arguments | |",
    "|---|---|---|",
    "| `label` | x y rest | draw text |",
    "",
    "## 10. Relationship to p5.js",
    "",
    "| This protocol | p5 |",
    "|---|---|",
    "| `cap` / `corner` | `strokeCap()` / `strokeJoin()` |",
    "",
  ].join("\n");
  const { verbGroups } = extractSpecGroups(stubSpec);
  assert.equal(verbGroups.cap, "colour-and-line", "the §10 table row must not overwrite §6.1's assignment");
  assert.equal(verbGroups.label, "text-and-canvas");
});

test("a verb appearing in two §6 sections fails loudly rather than silently picking one", () => {
  const stubSpec = [
    "### 6.1 Colour and line",
    "",
    "| `cap` | word |",
    "",
    "### 6.2 Shapes",
    "",
    "| `cap` | word |",
    "",
  ].join("\n");
  assert.throws(() => extractSpecGroups(stubSpec), /"cap" appears in more than one §6 section/);
});

// ---- generation (§7.2 B): no copy of the verb list ---------------------

function makeStubProtocolModule(extraVerb) {
  const ARITY = {
    stroke: 4, fill: 4, width: 1, cap: 1, corner: 1, line: 4, rect: 4, circle: 3,
    ellipse: 4, arc: 5, triangle: 6, shape: 0, vertex: 2, curve: 6, close: 0, end: 0,
    push: 0, pop: 0, translate: 2, rotate: 1, scale: 2, size: 1, align: 1,
    background: 3, clear: 0, label: 2,
  };
  if (extraVerb) ARITY[extraVerb] = 2;
  const WORDS = {
    cap: new Set(["butt", "round", "square"]),
    corner: new Set(["miter", "round", "bevel"]),
    align: new Set(["left", "center", "right"]),
  };
  const stubVERBS = Object.freeze(Object.keys(ARITY));

  function err(tag, headline, fix) {
    return { kind: "error", tag, message: fix ? `${headline}\n  try: ${fix}` : headline };
  }
  function parseNumber(t) {
    const s = t.startsWith("~") ? t.slice(1) : t;
    if (!/^-?\d+(\.\d+)?$/.test(s)) return null;
    return Number(s);
  }
  function stubParseCommand(line) {
    const tokens = line.trim().split(/\s+/);
    const verb = tokens[1];
    if (!(verb in ARITY)) {
      return err("unknown-verb", `unrecognised drawing verb "${verb}" in "${line}"`, `use one of: ${stubVERBS.join(", ")}`);
    }
    const args = tokens.slice(2);
    const arity = ARITY[verb];
    if (args.length !== arity) {
      return err("wrong-arity", `"${verb}" takes ${arity} argument${arity === 1 ? "" : "s"} in "${line}", got ${args.length}`, "check the argument count");
    }
    if (verb in WORDS) {
      const word = args[0];
      if (!WORDS[verb].has(word)) {
        return err("bad-word", `"${verb}" takes one of ${[...WORDS[verb]].join(", ")} in "${line}", got "${word}"`, `use one of: ${[...WORDS[verb]].join(", ")}`);
      }
      return { kind: "command", verb, args: [word] };
    }
    const nums = args.map(parseNumber);
    const bad = nums.findIndex((n) => n === null);
    if (bad !== -1) {
      return err("bad-number", `"${args[bad]}" is not a valid number in "${line}"`, "use digits");
    }
    return { kind: "command", verb, args: nums };
  }

  return { VERBS: stubVERBS, parseCommand: stubParseCommand };
}

const STUB_SRC = 'if (!/^-?\\d+(\\.\\d+)?$/.test(stripped)) return null;';

// Self-contained, independent of the real GROUPS/VERB_GROUPS (which now span
// six groups and thirty-three verbs) — the stub module only ever has the
// twenty-six verbs makeStubProtocolModule declares, so it gets its own
// five-group world rather than depending on the real one's exact shape.
const STUB_GROUPS = ["colour-and-line", "shapes", "paths", "transforms", "text-and-canvas"];
const STUB_VERB_GROUPS = {
  stroke: "colour-and-line", fill: "colour-and-line", width: "colour-and-line", cap: "colour-and-line", corner: "colour-and-line",
  line: "shapes", rect: "shapes", circle: "shapes", ellipse: "shapes", arc: "shapes", triangle: "shapes",
  shape: "paths", vertex: "paths", curve: "paths", close: "paths", end: "paths",
  push: "transforms", pop: "transforms", translate: "transforms", rotate: "transforms", scale: "transforms",
  size: "text-and-canvas", align: "text-and-canvas", background: "text-and-canvas", clear: "text-and-canvas", label: "text-and-canvas",
};

test("a verb added to a stub module appears in the generated JSON with no edit to the generator", () => {
  const withoutExtra = protocolJsonFromModule(makeStubProtocolModule(null), STUB_SRC, {
    verbGroups: STUB_VERB_GROUPS,
    groups: STUB_GROUPS,
  });
  assert.ok(!withoutExtra.verbs.some((v) => v.name === "wiggle"));

  const stubGroups = { ...STUB_VERB_GROUPS, wiggle: "shapes" };
  const withExtra = protocolJsonFromModule(makeStubProtocolModule("wiggle"), STUB_SRC, {
    verbGroups: stubGroups,
    groups: STUB_GROUPS,
  });
  const wiggle = withExtra.verbs.find((v) => v.name === "wiggle");
  assert.ok(wiggle, "the added verb must appear in the generated JSON");
  assert.equal(wiggle.arity, 2);
  assert.deepEqual(wiggle.arguments, ["number", "number"]);
});

test("a verb with no group assignment fails loudly rather than being silently dropped", () => {
  assert.throws(
    () => protocolJsonFromModule(makeStubProtocolModule("wiggle"), STUB_SRC, {
      verbGroups: STUB_VERB_GROUPS,
      groups: STUB_GROUPS,
    }),
    /verb "wiggle" has no group assignment/,
  );
});

test("probeArity/probeArgumentShape agree with the real module for every real verb", async () => {
  const mod = await import(`file://${path.join(REPO, "js", "paint", "protocol.mjs")}`);
  for (const name of VERBS) {
    // §3.2's one named exception (label) and v2's second one (gradient) —
    // neither has an arity a 64-numeric-argument probe can read: label is
    // never reached through the generic path at all, and gradient rejects
    // 64 numbers on its first (word) argument before arity is ever checked.
    if (name === "label" || name === "gradient") continue;
    const arity = probeArity(mod.parseCommand, name);
    const shape = probeArgumentShape(mod.parseCommand, name, arity);
    assert.ok(Number.isInteger(arity) && arity >= 0);
    assert.equal(shape.arguments.length, arity === 0 ? 0 : arity === 1 && shape.arguments[0] === "word" ? 1 : arity);
  }
});

// ---- --check gate (§7.2 B) ---------------------------------------------

test("node scripts/protocol_gen.mjs --check passes on the committed files", () => {
  execFileSync("node", ["scripts/protocol_gen.mjs", "--check"], { cwd: REPO });
});

test("--check fails on a hand-edited protocol.json and passes again after regeneration", () => {
  const p = path.join(REPO, "protocol", "protocol.json");
  const original = readFileSync(p, "utf-8");
  try {
    writeFileSync(p, original.replace('"draw"', '"paint"'));
    assert.throws(() => execFileSync("node", ["scripts/protocol_gen.mjs", "--check"], { cwd: REPO, stdio: "pipe" }));
  } finally {
    writeFileSync(p, original);
  }
  execFileSync("node", ["scripts/protocol_gen.mjs", "--check"], { cwd: REPO });
});

// ---- errors.json (§7.2 C) -----------------------------------------------

test("errors.json's entry count matches an independent count of err()/tag: sites in source", () => {
  const protocolSrc = readFileSync(path.join(REPO, "js", "paint", "protocol.mjs"), "utf-8");
  const streamSrc = readFileSync(path.join(REPO, "js", "paint", "stream.mjs"), "utf-8");

  // Independent of protocol_gen.mjs's own scanner: a plain count of call
  // sites, so a bug shared between the generator and its own extractor
  // cannot hide from this test.
  const errCallCount = [...protocolSrc.matchAll(/\berr\(/g)].filter((m) => protocolSrc.slice(Math.max(0, m.index - 9), m.index) !== "function ").length;
  const literalTagCount = [...streamSrc.matchAll(/\btag:\s*"[a-zA-Z0-9_-]+"/g)].length;

  const doc = readJson("protocol/errors.json");
  const protocolEntries = doc.entries.filter((e) => e.source.startsWith("js/paint/protocol.mjs"));
  const streamEntries = doc.entries.filter((e) => e.source.startsWith("js/paint/stream.mjs"));

  assert.equal(protocolEntries.length, errCallCount);
  assert.equal(streamEntries.length, literalTagCount);
});

test("errors.json reports the full tag list — 5 from protocol.mjs, 11 from stream.mjs, 16 total", () => {
  const doc = readJson("protocol/errors.json");
  const protocolTags = new Set(doc.entries.filter((e) => e.source.startsWith("js/paint/protocol.mjs")).map((e) => e.tag));
  const streamTags = new Set(doc.entries.filter((e) => e.source.startsWith("js/paint/stream.mjs")).map((e) => e.tag));
  assert.equal(protocolTags.size, 5, [...protocolTags].join(", "));
  assert.equal(streamTags.size, 11, [...streamTags].join(", "));
  assert.equal(Object.keys(doc.tags).length, 16);
  assert.equal(doc.count, doc.entries.length);
});

test("every fix clause in errors.json is present only for protocol.mjs entries (stream.mjs names none)", () => {
  const doc = readJson("protocol/errors.json");
  for (const e of doc.entries) {
    if (e.source.startsWith("js/paint/stream.mjs")) {
      assert.equal(e.fix, undefined, `${e.id} unexpectedly has a fix clause`);
    }
  }
});

// ---- fresh regeneration reproduces the committed files exactly ---------

test("buildProtocolJson()/buildErrorsJson() reproduce the committed files byte for byte", async () => {
  const protocolDoc = await buildProtocolJson();
  const errorsDoc = buildErrorsJson();
  assert.deepEqual(protocolDoc, readJson("protocol/protocol.json"));
  assert.deepEqual(errorsDoc, readJson("protocol/errors.json"));
});
