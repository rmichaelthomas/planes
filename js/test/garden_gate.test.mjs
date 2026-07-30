// js/test/garden_gate.test.mjs — the garden build's own acceptance checks.
//
// WHY THIS IS A SUITE AND NOT `scripts/verify-garden.mjs`. The build that
// produced this file asked for a committed verification script. This
// repository forbids one, in either language, and gates on its absence
// (`test_gate.py`, and the retirement rule stated at length in
// `scripts/ci.sh`): a build's verification script graduates into a suite or
// is deleted when the build merges, and the last build to ignore that shipped
// a `scripts/verify-*.mjs` that reported BLOCKING FAILURE on green main for
// two builds because nothing ran it. So the assertions are written here, in
// the form the rule says they end up in anyway — where `node --test` runs
// them on every gate, forever, rather than where nothing runs them at all.
//
// The letters are the build's own:
//   A  scrubbing away and back gives a byte-identical frame and schedule
//   B  playing forward and scrubbing directly agree
//   C  every other paint/*.planes renders byte-identically to main
//   D  trace length equals output length for every corpus program
//   E  the JS and Python traces agree in canonical form  (test_js_interp.py)
//   F  a tilted leaf's matrix maps its tip where it should  (hit.test.mjs)
//   G  `dash` and `clip` appear zero times in the garden's output
//   H  nothing in grammar/ changed  (test_gate.py's own province, and here)
//   I  both protocol projections regenerate identically  (protocol_gen.test.mjs)

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

import { stepGraph } from "../paint/loop.mjs";
import { BrowserModuleLoader } from "../module_loader_browser.mjs";
import { toSvg } from "../paint/svg.mjs";
import { schedule } from "../sound/stream.mjs";
import { markSink } from "../paint/marks.mjs";
import { walk } from "../paint/stream.mjs";
import { runProgramGraph } from "../browser_main.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const PAINT = path.join(REPO, "paint");
const SEED = 481027;

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

const gardenSrc = () => fs.readFileSync(path.join(PAINT, "garden.planes"), "utf-8");
const gardenBase = () => pathToFileURL(path.join(PAINT, "garden.planes")).href;

async function frameAt(tick, { loader }) {
  const r = await stepGraph(
    gardenSrc(),
    { tick, keys: [], pointer: { x: 0, y: 0, down: false }, state: null, seed: SEED },
    { loader },
  );
  assert.equal(r.error, null, `tick ${tick}: ${r.error && r.error.message}`);
  return r;
}

// The frame as bytes. An SVG document is the exportable, byte-comparable form
// of exactly what the canvas painted — same stream, same shared walk — so it
// stands in for "the two PNGs are identical" without needing a canvas in Node.
const frameBytes = (lines) => toSvg(lines, { width: 480, height: 360 }).svg;
const scheduleBytes = (lines) => JSON.stringify(schedule(lines).notes);

// ---- A: scrub away and back -------------------------------------------------

test("A: scrubbing to 60, away to 5, and back to 60 gives a byte-identical frame", async () => {
  const restore = installFsFetch();
  try {
    const loader = new BrowserModuleLoader({ base: gardenBase() });
    const first = await frameAt(60, { loader });
    await frameAt(5, { loader });
    const again = await frameAt(60, { loader });
    assert.equal(frameBytes(again.lines), frameBytes(first.lines));
  } finally {
    restore();
  }
});

test("A: and a byte-identical sound schedule", async () => {
  const restore = installFsFetch();
  try {
    const loader = new BrowserModuleLoader({ base: gardenBase() });
    const first = await frameAt(25, { loader });
    await frameAt(5, { loader });
    const again = await frameAt(25, { loader });
    assert.equal(scheduleBytes(again.lines), scheduleBytes(first.lines));
  } finally {
    restore();
  }
});

// ---- B: played forward, or dragged straight there ---------------------------

test("B: playing forward to 60 and scrubbing straight to 60 produce identical frames", async () => {
  const restore = installFsFetch();
  try {
    const loader = new BrowserModuleLoader({ base: gardenBase() });
    // Played forward: every tick from 0, exactly as the loop would.
    let played = null;
    for (let t = 0; t <= 60; t++) played = await frameAt(t, { loader });
    const dragged = await frameAt(60, { loader });
    assert.equal(frameBytes(dragged.lines), frameBytes(played.lines));
    assert.equal(scheduleBytes(dragged.lines), scheduleBytes(played.lines));
  } finally {
    restore();
  }
});

test("B: and the seed is the only other input — the same seed twice is the same garden", async () => {
  const restore = installFsFetch();
  try {
    const loader = new BrowserModuleLoader({ base: gardenBase() });
    const a = await frameAt(120, { loader });
    const b = await frameAt(120, { loader });
    assert.equal(frameBytes(a.lines), frameBytes(b.lines));
    const other = await stepGraph(
      gardenSrc(),
      { tick: 120, keys: [], pointer: { x: 0, y: 0, down: false }, state: null, seed: SEED + 1 },
      { loader },
    );
    assert.notEqual(frameBytes(other.lines), frameBytes(a.lines), "a different seed is a different garden");
  } finally {
    restore();
  }
});

// ---- C: the rest of the corpus is untouched ---------------------------------
//
// NOT `git diff main`. Three checks in this file were first written that way,
// and the merge caught them the same hour: a check phrased against a diff with
// `main` asserts NOTHING the moment the build becomes `main` — two of them
// passed vacuously and one failed outright on the merge commit. That is the
// retirement rule's own lesson met one layer in, and the answer is the same
// one: a build-time assertion either becomes a durable one or it goes.
//
// The durable form of "turtle, bloom and snake are untouched" is that they
// still emit the streams the committed pre-v2 baselines captured — frames
// fixed since protocol v2 shipped, which stay true a year from now and are
// what the claim actually means.

const BENCH = path.join(REPO, "benchmarks", "protocol-v2-pre");

// WHERE C ACTUALLY LIVES, AND WHY IT IS NOT DUPLICATED HERE.
// `js/test/protocol_v2.test.mjs` compares turtle, bloom and snake against the
// committed pre-v2 baselines on every gate, and it compares the RENDERED
// PICTURE — the SVG document — not the raw stream. Writing a second copy of
// that comparison here against the `.lines.txt` files looked equivalent and is
// not: PR #51 gave `rect` its explicit rotation argument, so snake now emits
// `draw rect 201 181 18 18 0` where the captured stream has four numbers. The
// picture is identical, which is exactly why the SVG check has stayed green
// and a stream check goes red.
//
// So this asserts the part that is NOT already asserted over there — that the
// three programs still run clean at every tick the baselines cover, and that
// the frame count has not quietly shrunk — and names the suite that owns the
// byte-identity rather than keeping a second copy of it to drift.

test("C: the baselines still cover the three programs, and every one of them runs clean", async () => {
  const restore = installFsFetch();
  try {
    const labels = fs
      .readdirSync(BENCH)
      .filter((f) => f.endsWith(".lines.txt"))
      .map((f) => f.replace(/\.lines\.txt$/, ""))
      .sort();
    assert.ok(labels.length >= 10, `only ${labels.length} baseline frames`);
    assert.ok(labels.includes("turtle"));
    assert.ok(labels.some((l) => l.startsWith("bloom")));
    assert.ok(labels.some((l) => l.startsWith("snake")));
    for (const label of labels) {
      const lines = await baselineStream(label);
      const sink = markSink();
      const { errors } = walk(lines, sink);
      assert.deepEqual(errors, [], `${label} emitted a protocol error`);
      assert.ok(lines.length > 5, `${label} drew almost nothing`);
    }
  } finally {
    restore();
  }
});

// The three programs, replayed exactly as the baselines were captured.
async function baselineStream(label) {
  if (label === "turtle") {
    const r = await runProgramGraph(fs.readFileSync(path.join(PAINT, "turtle.planes"), "utf-8"), {
      base: pathToFileURL(path.join(PAINT, "turtle.planes")).href,
    });
    assert.equal(r.error, null);
    return r.output;
  }
  const program = label.startsWith("bloom") ? "bloom" : "snake";
  const tick = Number(/-tick-(\d+)/.exec(label)[1]);
  const loader = new BrowserModuleLoader({
    base: pathToFileURL(path.join(PAINT, `${program}.planes`)).href,
  });
  const src = fs.readFileSync(path.join(PAINT, `${program}.planes`), "utf-8");
  if (program === "bloom") {
    const r = await stepGraph(src, { tick, keys: [], pointer: { x: 0, y: 0, down: false }, state: null }, { loader });
    assert.equal(r.error, null);
    return r.lines;
  }
  let state = null;
  let lines = null;
  for (let t = 0; t <= tick; t++) {
    const r = await stepGraph(
      src,
      { tick: t, keys: ["ArrowLeft"], pointer: { x: 0, y: 0, down: false }, state },
      { loader },
    );
    assert.equal(r.error, null);
    state = r.state;
    lines = r.lines;
  }
  return lines;
}

test("C: paint.html is still its own page, with no garden entry and no day scrubber", () => {
  const html = fs.readFileSync(path.join(REPO, "paint.html"), "utf-8");
  assert.doesNotMatch(html, /garden/i);
  assert.doesNotMatch(html, /day scrubber|paint-day/i);
});

// ---- D: the trace lines up with the output ----------------------------------

test("D: trace length equals output length for every corpus program that runs", async () => {
  const restore = installFsFetch();
  try {
    const corpus = fs
      .readdirSync(path.join(REPO, "corpus"))
      .filter((f) => f.endsWith(".planes"))
      .sort();
    let checked = 0;
    for (const name of corpus) {
      const file = path.join(REPO, "corpus", name);
      const r = await runProgramGraph(fs.readFileSync(file, "utf-8"), {
        base: pathToFileURL(file).href,
      });
      // A program that refuses (a `fail`, an unavailable `ask`) still has to
      // line up as far as it got.
      assert.equal(r.trace.length, r.output.length, name);
      checked += 1;
    }
    assert.ok(checked > 20, `only ${checked} corpus programs checked`);
  } finally {
    restore();
  }
});

test("D: the effect log is unchanged by the trace — asking still performs nothing", async () => {
  const restore = installFsFetch();
  try {
    const loader = new BrowserModuleLoader({ base: gardenBase() });
    const r = await frameAt(60, { loader });
    // The garden's declared surface is `console` and nothing else: every
    // effect a frame performs is a `show`, and the trace — which carries the
    // derivation of each of those shows — adds none of its own.
    const kinds = new Set(r.effects ? r.effects.map(([kind]) => kind) : []);
    assert.deepEqual([...kinds].sort(), []);
    // `stepResult` reports lines rather than effects, so the effect check
    // goes through the entry point that does report them, on the same source.
    const direct = await runProgramGraph(
      `let tick = 60\nlet keys = []\nlet pointer = { x: 0, y: 0, down: false }\nlet state = nothing\nlet seed = ${SEED}\n\n` +
        gardenSrc(),
      { base: gardenBase() },
    );
    assert.equal(direct.error, null);
    assert.deepEqual([...new Set(direct.effects.map(([kind]) => kind))], ["show"]);
    assert.equal(direct.trace.length, direct.output.length);
  } finally {
    restore();
  }
});

// ---- G: no dash, no clip ----------------------------------------------------

test("G: `dash`, `clip` and `unclip` appear zero times in the garden's output, at every tick sampled", async () => {
  const restore = installFsFetch();
  try {
    const loader = new BrowserModuleLoader({ base: gardenBase() });
    for (let tick = 0; tick < 300; tick += 13) {
      const { lines } = await frameAt(tick, { loader });
      for (const forbidden of ["draw dash", "draw clip", "draw unclip"]) {
        const found = lines.filter((l) => l.startsWith(forbidden));
        assert.deepEqual(found, [], `tick ${tick} emitted ${forbidden}`);
      }
    }
  } finally {
    restore();
  }
});

test("G: and the source never calls them either", () => {
  const src = gardenSrc();
  for (const helper of [/\bdash of\b/, /\bclip\b(?! opens)/, /\bunclip\b/]) {
    const withoutComments = src
      .split("\n")
      .filter((l) => !l.trimStart().startsWith("#"))
      .join("\n");
    assert.doesNotMatch(withoutComments, helper, `garden.planes calls ${helper}`);
  }
});

// ---- H: nothing in grammar/ changed -----------------------------------------

test("H: the language did not change — grammar/ regenerates identically from its own sources", () => {
  // THE INVARIANT IS "THE LANGUAGE DID NOT CHANGE", and the check that stood
  // for it during the build was `git diff --stat main -- grammar/` being
  // empty. That is not the same check twice over.
  //
  // It is too STRICT for a build that edits Python: `grammar/errors.json` is a
  // projection of the source and records `file.py:line` for every error it
  // catalogues, so adding a field and a paragraph of comment to interp.py
  // moves a hundred line numbers without touching a single tag, template or
  // fix. And it is too WEAK once the build merges: a diff against `main`, on
  // `main`, is empty, and the check passes without asserting anything at all.
  //
  // What is durable is that grammar/ is a faithful projection of the sources
  // it is generated from and that the counts the language is measured by are
  // where they were. `grammar_gen.py --check` is the same check `ci.sh` runs
  // as its own step; running it here too is deliberate, so the letter of the
  // gate lives with the rest of the gate rather than only in a shell script.
  const r = execFileSync("python3", ["grammar_gen.py", "--check"], {
    cwd: REPO,
    encoding: "utf-8",
  });
  assert.match(r, /up to date/);
});

test("H: the counts are where they were — 32 keywords, 12 builtins, 7 effect kinds", () => {
  const vocab = JSON.parse(fs.readFileSync(path.join(REPO, "grammar", "vocabulary.json"), "utf-8"));
  assert.equal(vocab.keywords.length, 32);
  assert.equal(vocab.builtins.length, 12);
  assert.equal(Object.keys(vocab.effect_kinds).length, 7);
});

// ---- the density budget, as a fact rather than a threshold ------------------

test("the scene stays inside the frame budget it was sized against", async () => {
  const restore = installFsFetch();
  try {
    const loader = new BrowserModuleLoader({ base: gardenBase() });
    let worst = 0;
    for (let tick = 0; tick < 300; tick += 17) {
      const { lines } = await frameAt(tick, { loader });
      worst = Math.max(worst, lines.filter((l) => l.startsWith("draw ")).length);
    }
    // benchmarks/density.md measured 877 commands at 60ms on the machine this
    // was written on. The number here is deliberately looser than that
    // measurement — a slower machine's budget is smaller and this suite must
    // not fail on one — but a scene that doubled would trip it, which is what
    // it is for: the version of this program before this build spent 3,200 to
    // 4,200 commands a frame and could not be played at all.
    assert.ok(worst < 1200, `the densest frame sampled spends ${worst} commands`);
  } finally {
    restore();
  }
});

// ---- the marks the page clicks on -------------------------------------------

test("every visible mark in a real frame is reachable, and the vignette is not the answer to everything", async () => {
  const restore = installFsFetch();
  try {
    const loader = new BrowserModuleLoader({ base: gardenBase() });
    const { lines, trace } = await frameAt(60, { loader });
    const sink = markSink();
    const { errors } = walk(lines, sink);
    assert.deepEqual(errors, []);
    assert.ok(sink.marks.length > 100, "a real frame records real marks");
    // Every mark names a stream line that has a trace entry, and that entry
    // names a line in garden.planes — not in draw.planes, which is the file
    // the reader is not looking at.
    const source = gardenSrc().split("\n");
    for (const mark of sink.marks) {
      const entry = trace[mark.line];
      assert.ok(entry, `mark on stream line ${mark.line} has no trace entry`);
      const [, sourceLine] = entry;
      assert.ok(sourceLine > 0 && sourceLine <= source.length, `line ${sourceLine} is outside garden.planes`);
    }
  } finally {
    restore();
  }
});

test("the sound schedule's own lines trace back into garden.planes too", async () => {
  const restore = installFsFetch();
  try {
    const loader = new BrowserModuleLoader({ base: gardenBase() });
    // Tick 25 crosses dawn, which is when the chord fires.
    const { lines, trace } = await frameAt(25, { loader });
    const noteLines = lines.map((l, i) => [l, i]).filter(([l]) => l.startsWith("sound note "));
    assert.ok(noteLines.length > 0, "the dawn chord fires at this tick");
    const source = gardenSrc().split("\n");
    for (const [, i] of noteLines) {
      const [, sourceLine] = trace[i];
      assert.ok(sourceLine > 0 && sourceLine <= source.length);
      assert.match(source[sourceLine - 1], /note of/);
    }
  } finally {
    restore();
  }
});
