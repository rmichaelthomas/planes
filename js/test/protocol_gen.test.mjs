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
  probeArity,
  probeArgumentShape,
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
    // named exception) — it never rejects on an OVER count, only under.
    const cases = v.trailing_text ? [v.arity - 1] : v.arity === 0 ? [v.arity + 1] : [v.arity - 1, v.arity + 1];
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
    for (const word of words) {
      const result = parseCommand(`draw ${verb} ${word}`);
      assert.equal(result.kind, "command", `${verb} ${word} should be accepted`);
    }
    const result = parseCommand(`draw ${verb} not-a-real-word`);
    assert.equal(result.tag, "bad-word");
  }
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

test("a verb added to a stub module appears in the generated JSON with no edit to the generator", () => {
  const withoutExtra = protocolJsonFromModule(makeStubProtocolModule(null), STUB_SRC);
  assert.ok(!withoutExtra.verbs.some((v) => v.name === "wiggle"));

  const stubGroups = { ...Object.fromEntries(withoutExtra.verbs.map((v) => [v.name, v.group])), wiggle: "shapes" };
  const withExtra = protocolJsonFromModule(makeStubProtocolModule("wiggle"), STUB_SRC, { verbGroups: stubGroups });
  const wiggle = withExtra.verbs.find((v) => v.name === "wiggle");
  assert.ok(wiggle, "the added verb must appear in the generated JSON");
  assert.equal(wiggle.arity, 2);
  assert.deepEqual(wiggle.arguments, ["number", "number"]);
});

test("a verb with no group assignment fails loudly rather than being silently dropped", () => {
  assert.throws(
    () => protocolJsonFromModule(makeStubProtocolModule("wiggle"), STUB_SRC),
    /verb "wiggle" has no group assignment/,
  );
});

test("probeArity/probeArgumentShape agree with the real module for every real verb", async () => {
  const mod = await import(`file://${path.join(REPO, "js", "paint", "protocol.mjs")}`);
  for (const name of VERBS) {
    if (name === "label") continue; // §3.2's one named exception
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

test("errors.json reports the full tag list — 5 from protocol.mjs, 8 from stream.mjs, 13 total", () => {
  const doc = readJson("protocol/errors.json");
  const protocolTags = new Set(doc.entries.filter((e) => e.source.startsWith("js/paint/protocol.mjs")).map((e) => e.tag));
  const streamTags = new Set(doc.entries.filter((e) => e.source.startsWith("js/paint/stream.mjs")).map((e) => e.tag));
  assert.equal(protocolTags.size, 5, [...protocolTags].join(", "));
  assert.equal(streamTags.size, 8, [...streamTags].join(", "));
  assert.equal(Object.keys(doc.tags).length, 13);
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
