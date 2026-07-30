// js/test/trace.test.mjs — the show/why trace, and the why card built on it.
//
// The trace is interpreter-level OBSERVATION: one entry per emitted output
// line, carrying the derivation of the expression that produced it and its
// source line. The two properties that matter are that it lines up with
// `output` exactly, and that having it changes nothing — `why` has always
// performed nothing (test_why_in_planes.py pins that for the language), and
// the same has to hold here.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { runProgram, runProgramGraph } from "../browser_main.mjs";
import { card, expand, reachesApproximation, originOf, annotationsInChain } from "../paint/why.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

function installFsFetch() {
  const real = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const p = fileURLToPath(url);
    if (!fs.existsSync(p)) return { ok: false, text: async () => "" };
    return { ok: true, text: async () => fs.readFileSync(p, "utf-8") };
  };
  return () => {
    if (real) globalThis.fetch = real;
    else delete globalThis.fetch;
  };
}

// ---- length and order --------------------------------------------------------

test("trace has exactly one entry per output line, in the same order", () => {
  const r = runProgram(`let a = 3
let b = a * 4
show text of b
why b
show "plain"
`);
  assert.equal(r.error, null);
  assert.equal(r.trace.length, r.output.length);
  assert.deepEqual(r.trace.map(([, line]) => line), [3, 0, 5]);
});

test("`why` gets a trace entry too — the two lists cannot drift apart", () => {
  const withWhy = runProgram(`let a = 1\nshow text of a\nwhy a\n`);
  const withoutWhy = runProgram(`let a = 1\nshow text of a\n`);
  assert.equal(withWhy.trace.length, withWhy.output.length);
  assert.equal(withoutWhy.trace.length, withoutWhy.output.length);
  assert.equal(withWhy.output.length - withoutWhy.output.length, 1);
  // Its line is 0, and deliberately: a `Why` node carries no line, and giving
  // it one is a change to the AST's shape — which grammar/parser.planes pins.
  assert.equal(withWhy.trace[1][1], 0);
});

test("a trace entry's derivation is the value that was shown", () => {
  const r = runProgram(`let a = 6\nshow text of (a * 7)\n`);
  const [node] = r.trace[0];
  assert.equal(r.output[0], "42");
  assert.equal(String(node.value), "42");
});

// ---- asking performs nothing -------------------------------------------------

test("the effect log is byte-identical with the trace present", () => {
  const src = `let a = 2\nshow text of a\nwhy a\nshow "done"\n`;
  const r = runProgram(src);
  const before = JSON.stringify(r.effects);
  assert.deepEqual(r.effects, [
    ["show", "2"],
    ["show", "done"],
  ]);
  // `why` produced an output line and no effect, which is the property this
  // trace had to preserve; reading the trace afterwards adds nothing either.
  assert.equal(r.output.length, 3);
  card(r.trace[0][0], { annotations: r.annotations });
  expand(r.trace[0][0], { annotations: r.annotations });
  assert.equal(JSON.stringify(r.effects), before);
});

test("a run that reads its own trace produces the same output as one that does not", () => {
  const src = `let a = 5\nshow text of (a + 1)\n`;
  const first = runProgram(src);
  first.trace.forEach(([node]) => card(node, { annotations: first.annotations }));
  const second = runProgram(src);
  assert.deepEqual(first.output, second.output);
  assert.deepEqual(first.effects, second.effects);
});

// ---- annotations -------------------------------------------------------------

test("annotations come back as a plain object of name to `because` text", () => {
  const r = runProgram(`let height = 40 because "tall enough to catch the light"\nshow text of height\n`);
  assert.equal(r.annotations.height, "tall enough to catch the light");
});

test("`because` outranks arithmetic — the author's words come first in the card", () => {
  const r = runProgram(`let g = 2 because "one number decides the whole plant"
let height = g * 30
show text of height
`);
  const c = card(r.trace[0][0], { annotations: r.annotations, title: "this plant" });
  assert.equal(c.because[0].name, "g");
  assert.equal(c.because[0].text, "one number decides the whole plant");
  assert.equal(c.value, "60");
});

// ---- the chain terminates, and the card says where ---------------------------

test("a chain that reaches the tick names the tick as its origin", () => {
  const r = runProgram(`let tick = 60\nlet phase = tick / 100\nshow text of phase\n`);
  const c = card(r.trace[0][0]);
  assert.equal(c.origin.kind, "input");
  assert.match(c.origin.text, /the tick/);
});

test("a chain that reaches the seed names the seed, and says nothing outside was touched", () => {
  const r = runProgram(`let seed = 481027\nlet x = seed * 2\nshow text of x\n`);
  const c = card(r.trace[0][0]);
  assert.match(c.origin.text, /Nothing outside the program was touched/);
});

test("a chain of pure literals ends at a literal, not at an input", () => {
  const r = runProgram(`show text of (2 + 3)\n`);
  const o = originOf(r.trace[0][0]);
  assert.equal(o.kind, "literal");
});

// ---- approximate is a badge --------------------------------------------------

test("a chain that reaches sine is badged approximate, and says so honestly", async () => {
  const restore = installFsFetch();
  try {
    const r = await runProgramGraph(`use math\nlet a = cosine of 37\nshow text of a\n`, {
      base: pathToFileURL(path.join(REPO, "paint", "entry.planes")).href,
    });
    assert.equal(r.error, null);
    const c = card(r.trace[0][0], { annotations: r.annotations });
    assert.equal(c.approximate, true);
    assert.equal(c.approximateNote, "approximate, and identical on every machine");
  } finally {
    restore();
  }
});

test("exact arithmetic is not badged", () => {
  const r = runProgram(`show text of (1 / 4)\n`);
  assert.equal(reachesApproximation(r.trace[0][0]), false);
  assert.equal(card(r.trace[0][0]).approximate, false);
});

// ---- one step, then expand ---------------------------------------------------

test("the card shows one step, and expand walks exactly one level further", () => {
  const r = runProgram(`let a = 2
let b = a * 3
let c = b + 10
show text of c
`);
  const c = card(r.trace[0][0], { annotations: r.annotations });
  // The step is the ARITHMETIC that produced the number, not the `text of`
  // that turned it into a line: a reader clicking a mark is asking about the
  // number, and the string assembly around it is the protocol's business.
  assert.equal(c.step.label, "+");
  assert.equal(c.value, "16");
  assert.deepEqual(c.rows.map((row) => row.value), ["16"]);
  const deeper = expand(r.trace[0][0], { annotations: r.annotations });
  assert.equal(deeper.length, 2);
  assert.deepEqual(deeper.map((d) => d.value), ["6", "10"]);
});

// ---- the real thing ----------------------------------------------------------

test("the garden's own trace lines up with its own output, and every draw line has one", async () => {
  const restore = installFsFetch();
  try {
    const src = fs.readFileSync(path.join(REPO, "paint", "garden.planes"), "utf-8");
    const prelude = `let tick = 60\nlet keys = []\nlet pointer = { x: 0, y: 0, down: false }\nlet state = nothing\nlet seed = 481027\n`;
    const r = await runProgramGraph(prelude + src, {
      base: pathToFileURL(path.join(REPO, "paint", "garden.planes")).href,
    });
    assert.equal(r.error, null);
    assert.equal(r.trace.length, r.output.length);
    assert.ok(r.output.length > 500, "the garden emits a real frame");
    // Every line has a source line inside the file, and the annotations the
    // scene's `because` clauses set are all present.
    for (const [node, line] of r.trace) {
      assert.ok(node, "every entry carries a derivation");
      assert.ok(line > 0, "every entry names a source line");
    }
    assert.ok(Object.keys(r.annotations).length >= 5, "the scene annotates its own numbers");
  } finally {
    restore();
  }
});

test("a drawing line's card has one row per number in it, not one for the string", () => {
  const r = runProgram(`let x = 12\nlet y = 34\nshow "draw circle " + text of x + " " + text of y + " 5"\n`);
  const c = card(r.trace[0][0]);
  assert.deepEqual(c.rows.map((row) => row.value), ["12", "34"]);
});

test("a garden mark's chain reaches the tick or the seed and the card names it", async () => {
  const restore = installFsFetch();
  try {
    const src = fs.readFileSync(path.join(REPO, "paint", "garden.planes"), "utf-8");
    const prelude = `let tick = 60\nlet keys = []\nlet pointer = { x: 0, y: 0, down: false }\nlet state = nothing\nlet seed = 481027\n`;
    const r = await runProgramGraph(prelude + src, {
      base: pathToFileURL(path.join(REPO, "paint", "garden.planes")).href,
    });
    const origins = r.trace.map(([node]) => originOf(node).kind);
    assert.ok(origins.includes("input"), "some mark derives from tick or seed");
    const annotated = r.trace.filter(([node]) => annotationsInChain(node, r.annotations).length > 0);
    assert.ok(annotated.length > 0, "some mark's chain passes through an annotated name");
  } finally {
    restore();
  }
});
