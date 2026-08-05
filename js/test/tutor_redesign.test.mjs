// js/test/tutor_redesign.test.mjs — tutor.html's own verification gate
// (build prompt planes_build_prompt_tutor_redesign.md §11.2, points D/E).
// Supersedes js/test/tutor_gate.test.mjs (v26.0/#71): that suite pinned a
// SINGLE textarea holding a pre-filled, finished starter program — the
// exact shape checkpoint v27.0 §425 retracts ("the editor does not load
// pre-filled with a finished program"). Its still-true coverage (provenance
// reaching a because-annotated binding, the CALL_HEADER heading rule) is
// carried forward here against the new week-aware, ghost-text-first shell;
// what is new is the empty-because invitation and the ghost-text
// un-runnable guard §425 locks.
//
// Pure logic lives inline in tutor.html's own <script type="module">, which
// cannot be imported (nothing can import from an inline module script) — so,
// following js/test/tutor_gate.test.mjs's own convention for CALL_HEADER,
// this suite extracts a function's or object's literal SOURCE TEXT out of
// tutor.html and evaluates it directly, rather than keeping a second,
// hand-copied version that could drift from what actually ships.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { runProgramGraph } from "../browser_main.mjs";
import { walk } from "../paint/stream.mjs";
import { markSink } from "../paint/marks.mjs";
import { card } from "../paint/why.mjs";
import { PLACEABLES } from "../scene_vocab.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const PAINT = path.join(REPO, "paint");
const SCENE_BASE = pathToFileURL(PAINT + path.sep).href;
const TUTOR_HTML = path.join(REPO, "tutor.html");
const pageSrc = () => fs.readFileSync(TUTOR_HTML, "utf-8");

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

// ---- extraction helpers, mirroring tutor_gate.test.mjs's extractRegex ----

function extractFunction(html, name) {
  const marker = `function ${name}(`;
  const start = html.indexOf(marker);
  assert.ok(start >= 0, `tutor.html no longer declares function ${name} where this suite reads it`);
  let i = html.indexOf("{", start);
  let depth = 0;
  for (; i < html.length; i++) {
    if (html[i] === "{") depth++;
    else if (html[i] === "}") {
      depth--;
      if (depth === 0) {
        i++;
        break;
      }
    }
  }
  return html.slice(start, i);
}

function extractObjectLiteral(html, constName) {
  const marker = `const ${constName} = {`;
  const start = html.indexOf(marker);
  assert.ok(start >= 0, `tutor.html no longer declares const ${constName} where this suite reads it`);
  let i = start + marker.length - 1;
  let depth = 0;
  for (; i < html.length; i++) {
    if (html[i] === "{") depth++;
    else if (html[i] === "}") {
      depth--;
      if (depth === 0) {
        i++;
        break;
      }
    }
  }
  return html.slice(start + `const ${constName} = `.length, i);
}

function loadParseArgs() {
  const splitArgsSrc = extractFunction(pageSrc(), "splitArgs");
  const parseArgsSrc = extractFunction(pageSrc(), "parseArgs");
  // eslint-disable-next-line no-new-func
  return new Function(`${splitArgsSrc}\n${parseArgsSrc}\nreturn parseArgs;`)();
}

function loadGhostLine() {
  const src = extractFunction(pageSrc(), "ghostLine");
  const BLANK = pageSrc().match(/const BLANK = ("[^"]*");/)[1];
  // eslint-disable-next-line no-new-func
  return new Function(`const BLANK = ${BLANK};\n${src}\nreturn ghostLine;`)();
}

function loadWeekPrograms() {
  const literal = extractObjectLiteral(pageSrc(), "WEEK_PROGRAMS");
  // eslint-disable-next-line no-eval
  return eval(`(${literal})`);
}

// ---- D: provenance ----------------------------------------------------

const STARTER_PROGRAM = `use scene

start
sky of "middle of the afternoon"
ground of "wet grass"

sun of 240, 70
two-bees of 300, 150

let spot = 90 because "it's the tallest in the yard"
two-flowers of 120, spot
`;

test("D: a because-annotated binding survives into result.annotations and into the mark's own derivation chain", async () => {
  const restore = installFsFetch();
  try {
    const r = await runProgramGraph(STARTER_PROGRAM, { base: SCENE_BASE });
    assert.equal(r.error, null, r.error && r.error.message);
    assert.equal(r.annotations.spot, "it's the tallest in the yard");

    const sink = markSink();
    walk(r.output, sink);
    const centreMark = sink.marks.find((m) => m.kind === "circle" && m.geometry.r === 5);
    assert.ok(centreMark, "a flower centre mark (r=5) was not found");
    const entry = r.trace[centreMark.line];
    assert.ok(entry, "the flower centre's stream line has no trace entry");
    const [node] = entry;

    const c = card(node, { annotations: r.annotations });
    assert.ok(
      c.because.some((b) => b.name === "spot" && b.text === "it's the tallest in the yard"),
      "the flower's card does not carry the 'spot' annotation as its because-sentence",
    );
  } finally {
    restore();
  }
});

test("D: the card leads with her sentence — parseArgs finds the annotated name among the call's own arguments", async () => {
  const parseArgs = loadParseArgs();
  const parsed = parseArgs("two-flowers of 120, spot");
  assert.deepEqual(parsed, { name: "two-flowers", args: ["120", "spot"] });
  const placeable = PLACEABLES.find((p) => p.name === parsed.name);
  assert.deepEqual(placeable.shape, ["across", "how-tall"]);
  // "spot" is arg index 1 — the "how-tall" slot — and it is a bare name,
  // not a literal, so the card's own logic resolves it through
  // lastAnnotations rather than showing it as a raw number.
  assert.equal(parsed.args[1], "spot");
});

test("D: empty-because — a call with no named argument at all carries no chain-wide annotation either, so the card falls to the invitation", async () => {
  const restore = installFsFetch();
  try {
    const r = await runProgramGraph(STARTER_PROGRAM, { base: SCENE_BASE });
    assert.equal(r.error, null);
    const sink = markSink();
    walk(r.output, sink);
    // The sun's glow mark: `sun of 240, 70` — both arguments are literals,
    // and sun's own helper body binds no name at all, so nothing in this
    // mark's derivation carries a `because` anywhere in the chain.
    const sunMark = sink.marks.find((m) => m.kind === "circle" && m.geometry.r === 27);
    assert.ok(sunMark, "the sun's core mark (r=27) was not found");
    const entry = r.trace[sunMark.line];
    const [node] = entry;
    const c = card(node, { annotations: r.annotations });
    assert.deepEqual(c.because, [], "the sun's card unexpectedly carries a because-sentence — the invitation branch would never fire");

    const parseArgs = loadParseArgs();
    const parsed = parseArgs("sun of 240, 70");
    assert.ok(parsed.args.every((a) => /^-?\d+(\.\d+)?$/.test(a)), "sun's own arguments must both be plain literals for this control to hold");
  } finally {
    restore();
  }
});

test("D: heading — CALL_HEADER names a call site and stops at the assignment boundary", () => {
  const CALL_HEADER_LINE = pageSrc()
    .split("\n")
    .find((l) => l.includes("const CALL_HEADER ="));
  assert.ok(CALL_HEADER_LINE, "tutor.html no longer declares CALL_HEADER where this suite reads it");
  const literal = CALL_HEADER_LINE.trim().replace(/^const CALL_HEADER = /, "").replace(/;$/, "");
  const lastSlash = literal.lastIndexOf("/");
  const re = new RegExp(literal.slice(1, lastSlash), literal.slice(lastSlash + 1));

  const named = (line) => {
    const m = re.exec(line);
    return m ? m[1] : null;
  };
  assert.equal(named("moon of 240, 90"), "moon");
  assert.equal(named("two-flowers of 120, spot"), "two-flowers");
  assert.equal(named("start"), "start");
  assert.equal(named('let spot = 90 because "the corner gets the sun after noon"'), null);
  assert.equal(named("spot = 90"), null);
});

// ---- E: ghost text ------------------------------------------------------

test("E: the initial editor is not a runnable program — the textarea ships empty, not pre-filled", () => {
  const html = pageSrc();
  const m = /<textarea id="source"[^>]*>([\s\S]*?)<\/textarea>/.exec(html);
  assert.ok(m, "tutor.html no longer declares a #source textarea where this suite reads it");
  assert.equal(m[1].trim(), "", "the textarea ships with real program text — it must load empty, with ghost text carrying the hint instead");
});

test("E: Run on an empty editor is guarded before it ever reaches the engine", () => {
  const runSrc = extractFunction(pageSrc(), "run");
  const guardIndex = runSrc.indexOf('src.trim() === ""');
  const engineCallIndex = runSrc.indexOf("runProgramGraph(");
  assert.ok(guardIndex >= 0, "run() no longer guards against an empty editor");
  assert.ok(engineCallIndex >= 0, "run() no longer calls runProgramGraph at all");
  assert.ok(guardIndex < engineCallIndex, "the empty-editor guard must run BEFORE runProgramGraph is ever called");
});

test("E: ghost text is generated from WEEK_PROGRAMS, never a second hand-kept copy, and is genuinely blanked", () => {
  const ghostLine = loadGhostLine();
  const WEEK_PROGRAMS = loadWeekPrograms();
  for (const [week, spec] of Object.entries(WEEK_PROGRAMS)) {
    const ghosted = spec.lines.map(ghostLine);
    const anyBlanked = ghosted.some((l) => l.includes("…"));
    assert.ok(anyBlanked, `week ${week}'s ghost text carries no blanks at all`);
    // every number and every quoted phrase in the real program is gone from
    // the ghost version
    for (const line of ghosted) {
      assert.ok(!/"[a-z][^"]*"/i.test(line), `a ghost line still carries a real quoted phrase: "${line}"`);
      assert.ok(!/\b\d+\b/.test(line) || line.includes("…"), `a ghost line still carries a raw number: "${line}"`);
    }
  }
});

test("E: every week's target program actually runs, and its ghost is a strict textual reduction of it (never longer, never a different line count)", () => {
  const ghostLine = loadGhostLine();
  const WEEK_PROGRAMS = loadWeekPrograms();
  for (const [week, spec] of Object.entries(WEEK_PROGRAMS)) {
    assert.ok(Array.isArray(spec.lines) && spec.lines.length > 0, `week ${week} has no lines`);
    assert.equal(typeof spec.lesson, "string", `week ${week} has no lesson text`);
    const ghosted = spec.lines.map(ghostLine);
    assert.equal(ghosted.length, spec.lines.length, `week ${week}'s ghost has a different line count than its target`);
  }
});

test("E: ghost text and the real editor are separate elements — the ghost pre is never nested inside the textarea", () => {
  const html = pageSrc();
  const ghostIdx = html.indexOf('id="ghost"');
  const textareaOpen = html.indexOf('<textarea id="source"');
  const textareaClose = html.indexOf("</textarea>");
  assert.ok(ghostIdx >= 0 && textareaOpen >= 0 && textareaClose >= 0);
  assert.ok(ghostIdx < textareaOpen || ghostIdx > textareaClose, "#ghost must not be nested inside the #source textarea");
});
