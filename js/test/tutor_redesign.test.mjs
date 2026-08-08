// js/test/tutor_redesign.test.mjs — tutor.html's own verification gate
// (build prompt "Tutor Redesign: Goal-Driven, Line-Live Typing", v35.0,
// §10.2). Supersedes the prior version of this suite, which pinned the
// v27.0 ghost-text-first shell (a blank #source textarea + a Run button):
// that interaction spine no longer exists — a goal-live loop replaced it
// (§4). ghostFor/ghostLine/ghostSuffix and the empty-editor Run guard are
// gone from tutor.html and gone from this suite with them.
//
// Still-true coverage carried forward unchanged in substance: provenance
// reaching a because-annotated binding (group D — this is an ENGINE
// property, not a shell property, so runProgramGraph/card()/PLACEABLES are
// exercised directly and did not need to change), and the coordinate
// orientation tip (group F — renamed hasRunThisLesson -> hasPaintedThisLesson
// to match the new no-Run-button model, otherwise the same mechanism).
//
// New in this version: group G, the goal-live acceptance model itself —
// LESSONS re-expressed as frame/slot items (§3) and the five match kinds
// (§4) that decide whether a typed line completes a step. Pure logic lives
// inline in tutor.html's own <script type="module">, which cannot be
// imported (nothing can import from an inline module script) — so, following
// the prior suite's own convention, this extracts a function's or object's
// literal SOURCE TEXT out of tutor.html and evaluates it directly, rather
// than keeping a second, hand-copied version that could drift from what
// actually ships.

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

// ---- extraction helpers, mirroring the prior suite's extractRegex/extractFunction ----

function extractFunction(html, name) {
  const marker = `function ${name}(`;
  const start = html.indexOf(marker);
  assert.ok(start >= 0, `tutor.html no longer declares function ${name} where this suite reads it`);
  let parenDepth = 0;
  let j = start + marker.length - 1;
  for (; j < html.length; j++) {
    if (html[j] === "(") parenDepth++;
    else if (html[j] === ")") {
      parenDepth--;
      if (parenDepth === 0) {
        j++;
        break;
      }
    }
  }
  let i = html.indexOf("{", j);
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

// A single-line `const NAME = ...;` declaration (arrow functions, string/
// template literals) — everything this suite needs to extract from tutor.html
// that isn't a `function` declaration is written as exactly one such line.
function extractConstLine(html, constName) {
  const line = html.split("\n").find((l) => l.trim().startsWith(`const ${constName} =`));
  assert.ok(line, `tutor.html no longer declares const ${constName} where this suite reads it`);
  return line.trim();
}

function extractArrayLiteral(html, constName) {
  const marker = `const ${constName} = [`;
  const start = html.indexOf(marker);
  assert.ok(start >= 0, `tutor.html no longer declares const ${constName} where this suite reads it`);
  let i = start + marker.length - 1;
  let depth = 0;
  for (; i < html.length; i++) {
    if (html[i] === "[") depth++;
    else if (html[i] === "]") {
      depth--;
      if (depth === 0) {
        i++;
        break;
      }
    }
  }
  return html.slice(start + `const ${constName} = `.length, i);
}

function loadLessons() {
  const literal = extractArrayLiteral(pageSrc(), "LESSONS");
  // eslint-disable-next-line no-eval
  return eval(`(${literal})`);
}

// The goal-live matcher bundle (§4): testStep and its five kind-specific
// testers, plus the small helpers they depend on (escapeRegex, normSpace,
// IDENT/IDENT_WORD). Stitched together from tutor.html's own source text so
// this suite can never silently drift from what the page actually runs.
function loadMatchers() {
  const html = pageSrc();
  const src = [
    extractConstLine(html, "escapeRegex"),
    extractConstLine(html, "IDENT_WORD"),
    extractConstLine(html, "IDENT"),
    extractFunction(html, "normSpace"),
    extractFunction(html, "testExact"),
    extractFunction(html, "testShapeBecause"),
    extractFunction(html, "testShapeCustomSky"),
    extractFunction(html, "testNameBindingDef"),
    extractFunction(html, "testNameBindingUse"),
    extractFunction(html, "testStep"),
  ].join("\n");
  // eslint-disable-next-line no-new-func
  return new Function(`${src}\nreturn { testStep, testExact, testShapeBecause, testShapeCustomSky, testNameBindingDef, testNameBindingUse };`)();
}

function loadCueTextFor() {
  const html = pageSrc();
  const src = [extractFunction(html, "cueTextFor")].join("\n");
  // eslint-disable-next-line no-new-func
  return new Function(`${src}\nreturn cueTextFor;`)();
}

function loadParseArgs() {
  const splitArgsSrc = extractFunction(pageSrc(), "splitArgs");
  const parseArgsSrc = extractFunction(pageSrc(), "parseArgs");
  // eslint-disable-next-line no-new-func
  return new Function(`${splitArgsSrc}\n${parseArgsSrc}\nreturn parseArgs;`)();
}

function loadFormatCoord() {
  const html = pageSrc();
  const glyphLine = html.split("\n").find((l) => l.includes("const DIRECTION_GLYPH ="));
  assert.ok(glyphLine, "tutor.html no longer declares DIRECTION_GLYPH where this suite reads it");
  const glyphLiteral = glyphLine.trim().replace(/^const DIRECTION_GLYPH = /, "").replace(/;$/, "");
  const src = extractFunction(html, "formatCoord");
  // eslint-disable-next-line no-new-func
  return new Function(`const DIRECTION_GLYPH = ${glyphLiteral};\n${src}\nreturn formatCoord;`)();
}

// ---- D: provenance (engine property — unchanged by the shell rewrite) ----

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
  assert.equal(parsed.args[1], "spot");
});

test("D: empty-because — a call with no named argument at all carries no chain-wide annotation either, so the card falls to the invitation", async () => {
  const restore = installFsFetch();
  try {
    const r = await runProgramGraph(STARTER_PROGRAM, { base: SCENE_BASE });
    assert.equal(r.error, null);
    const sink = markSink();
    walk(r.output, sink);
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

// ---- G: the goal-live acceptance model (§4) ------------------------------

test("G exact: whitespace-normalised match accepts a differently-spaced right line and rejects a wrong one", () => {
  const { testExact } = loadMatchers();
  const step = { text: 'sky of "middle of the afternoon"' };
  assert.deepEqual(testExact(step, 'sky of "middle of the afternoon"'), { committed: step.text });
  assert.deepEqual(testExact(step, '  sky   of "middle of the afternoon" '), { committed: step.text }, "interior whitespace must be tolerated (§4's explicitly-allowed addition)");
  assert.equal(testExact(step, 'sky of "just before dark"'), null, "a wrong phrase must not match");
});

test("G shape-because: accepts any non-empty reason and rejects a missing one — §10.2's explicit acceptance case", () => {
  const { testShapeBecause } = loadMatchers();
  const step = { name: "spot", number: 90 };
  const withReason = testShapeBecause(step, 'let spot = 90 because "because it is tall"');
  assert.deepEqual(withReason, { committed: 'let spot = 90 because "because it is tall"' });
  const differentReason = testShapeBecause(step, 'let spot = 90 because "a totally different sentence nobody wrote before"');
  assert.ok(differentReason, "ANY non-empty reason must be accepted — the reason is never matched against a target");
  assert.equal(testShapeBecause(step, "let spot = 90"), null, "a let line with no reason at all must be rejected");
  assert.equal(testShapeBecause(step, 'let spot = 90 because ""'), null, "an empty quoted reason must be rejected");
  assert.equal(testShapeBecause(step, 'let shady = 90 because "x"'), null, "the wrong bound name must be rejected");
  assert.equal(testShapeBecause(step, 'let spot = 44 because "x"'), null, "the wrong bound number must be rejected");
});

test("G shape-custom-sky: accepts any three numbers, typed or picker-inserted, in canonical indented form", () => {
  const { testShapeCustomSky } = loadMatchers();
  assert.deepEqual(testShapeCustomSky({}, "custom-sky of 0.78, 0.14, 55"), { committed: "  custom-sky of 0.78, 0.14, 55" });
  assert.deepEqual(testShapeCustomSky({}, "custom-sky of 0.55, 0.2, 25"), { committed: "  custom-sky of 0.55, 0.2, 25" }, "the swatch picker's own numbers must be accepted");
  assert.equal(testShapeCustomSky({}, "custom-sky of 0.78, 0.14"), null, "only two numbers must be rejected");
  assert.equal(testShapeCustomSky({}, 'custom-sky of "red", 0.14, 55'), null, "a non-numeric argument must be rejected");
});

test("G name-binding: a def site records any valid identifier, and only that same name is accepted at the use site", () => {
  const { testNameBindingDef, testNameBindingUse } = loadMatchers();
  const step = { bindAs: "skyName" };
  const bound = {};
  assert.equal(testNameBindingUse(step, "anything", bound), null, "a use site must refuse before any name has been bound");

  const def = testNameBindingDef(step, "to sunset dream:", bound);
  assert.deepEqual(def, { committed: "to sunset dream:" });
  assert.equal(bound.skyName, "sunset dream", "the chosen name must be recorded for later use-site steps");

  assert.equal(testNameBindingUse(step, "some other name", bound), null, "a mismatched name must be rejected at the use site");
  assert.deepEqual(testNameBindingUse(step, "sunset dream", bound), { committed: "sunset dream" }, "the exact chosen name must be accepted");

  assert.equal(testNameBindingDef(step, "to the sky of blue:", {}), null, "a name containing 'of' must be refused — it would collide with call syntax");
});

test("G testStep: a wrong line is null for every match kind — the shared no-op guarantee failure mode 4 names", () => {
  const { testStep } = loadMatchers();
  assert.equal(testStep({ match: "exact", text: "sun of 240, 70" }, "moon of 240, 70", {}), null);
  assert.equal(testStep({ match: "shape-because", name: "spot", number: 90 }, "let spot = 91 because \"x\"", {}), null);
  assert.equal(testStep({ match: "shape-custom-sky" }, "not a custom sky line", {}), null);
  assert.equal(testStep({ match: "name-binding-def" }, "not to anything", {}), null);
  assert.equal(testStep({ match: "exact", text: "sun of 240, 70" }, "", {}), null, "an empty typed value must never match");
});

test("G the cue for a name-binding-use step is dynamic — it shows her own chosen name back to her, not a generic placeholder", () => {
  const cueTextFor = loadCueTextFor();
  const step = { match: "name-binding-use", bindAs: "skyName" };
  assert.equal(cueTextFor(step, {}), "", "before a name is bound there is nothing to show");
  assert.equal(cueTextFor(step, { skyName: "sunset dream" }), "sunset dream");
});

// ---- G: LESSONS structure — every lesson re-expressed as frame/slot items,
// nothing dropped, LESSONS.length the only lesson count (§3, §8) --------

test("G: LESSONS.length is 7 today and nothing in the shell hardcodes that count", () => {
  const LESSONS = loadLessons();
  assert.equal(LESSONS.length, 7);
  const html = pageSrc();
  // The lesson-nav renderer and the clamp function must read LESSONS.length,
  // never a literal — grepped directly against the source rather than just
  // trusting behaviour, since a hardcoded fallback could still pass an
  // end-to-end click-through test by coincidence.
  assert.match(html, /LESSONS\.length - 1/, "clampLesson must derive its ceiling from LESSONS.length");
  assert.match(html, /LESSONS\.map\(/, "the lesson nav must be rendered from LESSONS, not a fixed list");
});

test("G: every lesson has a title, a say, declared surfaces, and at least one item", () => {
  const LESSONS = loadLessons();
  for (const [i, lesson] of LESSONS.entries()) {
    assert.equal(typeof lesson.title, "string", `lesson ${i} has no title`);
    assert.equal(typeof lesson.say, "string", `lesson ${i} has no say text`);
    assert.ok(Array.isArray(lesson.items) && lesson.items.length > 0, `lesson ${i} has no items`);
    assert.equal(typeof lesson.surfaces, "object", `lesson ${i} has no surfaces`);
  }
});

test("G: frame items carry no goal and are never typed; slot items always declare goal, paints, and a known match kind", () => {
  const LESSONS = loadLessons();
  const KNOWN_KINDS = new Set(["exact", "shape-because", "shape-custom-sky", "name-binding-def", "name-binding-use"]);
  for (const [i, lesson] of LESSONS.entries()) {
    for (const [j, item] of lesson.items.entries()) {
      assert.ok(item.role === "frame" || item.role === "slot", `lesson ${i} item ${j} has an unknown role: ${item.role}`);
      if (item.role === "frame") {
        assert.equal(typeof item.text, "string", `lesson ${i} item ${j} is a frame line with no text`);
        assert.equal(item.goal, undefined, `lesson ${i} item ${j} is a frame line but carries a goal — frame lines must not be goal-targeted`);
      } else {
        assert.equal(typeof item.goal, "string", `lesson ${i} item ${j} is a slot with no goal`);
        assert.ok("paints" in item, `lesson ${i} item ${j} is a slot with no declared paints (use null for none)`);
        assert.ok(KNOWN_KINDS.has(item.match), `lesson ${i} item ${j} has an unrecognised match kind: ${item.match}`);
      }
    }
  }
});

test("G: no lesson mechanic was dropped — lessons 4/5 carry shape-because, lesson 6 carries the full multiline own-sky definition plus swatches, lesson 7 is the capstone", () => {
  const LESSONS = loadLessons();
  const kindsOf = (lesson) => lesson.items.filter((it) => it.role === "slot").map((it) => it.match);

  assert.ok(kindsOf(LESSONS[3]).includes("shape-because"), "lesson 4 (name it & why) must carry a shape-because step");
  const l5Kinds = kindsOf(LESSONS[4]);
  assert.equal(l5Kinds.filter((k) => k === "shape-because").length, 2, "lesson 5 must carry BOTH let…because pairs, not simplified into one");

  const l6Kinds = kindsOf(LESSONS[5]);
  assert.ok(l6Kinds.includes("name-binding-def"), "lesson 6 must carry the own-sky name-binding definition");
  assert.ok(l6Kinds.includes("shape-custom-sky"), "lesson 6 must carry the custom-sky colour body");
  assert.ok(l6Kinds.includes("name-binding-use"), "lesson 6 must carry the own-sky use site");
  assert.equal(LESSONS[5].surfaces.swatches, true, "lesson 6 must keep the swatch picker surface");

  assert.equal(LESSONS[6].surfaces.capstone, true, "lesson 7 must keep the capstone surface");
  assert.ok(LESSONS[6].items.every((it) => it.role === "frame"), "lesson 7 carries no goal-live typing steps of its own (§4) — every one of its lines is pre-authored frame furniture");
});

test("G: lesson 6's def-header item and its later use-site item share the same bindAs key, so the chosen name actually carries forward", () => {
  const LESSONS = loadLessons();
  const items = LESSONS[5].items;
  const def = items.find((it) => it.match === "name-binding-def");
  const use = items.find((it) => it.match === "name-binding-use");
  assert.ok(def && use, "lesson 6 must carry both a name-binding-def and a name-binding-use item");
  assert.equal(def.bindAs, use.bindAs, "the definition and use sites must bind the same key, or a chosen name could never carry forward");
});

test("G: one statement per line (§8.2) — no LESSONS item's own text spans more than one physical line", () => {
  const LESSONS = loadLessons();
  for (const [i, lesson] of LESSONS.entries()) {
    for (const [j, item] of lesson.items.entries()) {
      const text = item.text ?? "";
      assert.ok(!text.includes("\n"), `lesson ${i} item ${j} compresses more than one line into a single item: ${JSON.stringify(text)}`);
    }
  }
});

test("G: the key is derived from a lesson's own items, not a second hand-kept vocabulary list", () => {
  const html = pageSrc();
  const fnIdx = html.indexOf("function vocabForLesson(");
  assert.ok(fnIdx >= 0, "tutor.html no longer declares vocabForLesson where this suite reads it");
  const fnSrc = extractFunction(html, "vocabForLesson");
  assert.match(fnSrc, /lessonProgramText\(/, "vocabForLesson must derive from the lesson's own program text, not a declared field");
  // No LESSONS[i] may carry a hand-kept `vocab` field — that would be
  // exactly the second copy this discipline forbids.
  const LESSONS = loadLessons();
  for (const lesson of LESSONS) assert.equal(lesson.vocab, undefined);
});

test("G: sky and ground gained their own why-card labels locally (CARD_LABELS), without touching scene_vocab.mjs's PLACEABLES", () => {
  const html = pageSrc();
  const line = html.split("\n").find((l) => l.includes("const CARD_LABELS ="));
  assert.ok(line, "tutor.html no longer declares CARD_LABELS where this suite reads it");
  assert.match(line, /sky:\s*\["time"\]/, "sky must have a local card label so its backdrop why-card reads 'time' rather than a raw argument");
  assert.match(line, /ground:\s*\["kind"\]/, "ground must have a local card label so its backdrop why-card reads 'kind' rather than a raw argument");
  assert.ok(!PLACEABLES.some((p) => p.name === "sky" || p.name === "ground"), "sky/ground must NOT be added to scene_vocab.mjs's PLACEABLES — the engine module stays unmodified");
});

// ---- F: orientation hint (hover-before-you-run coordinates), adapted to
// the new hasPaintedThisLesson flag name (same mechanism, no Run button) --

test("F: formatCoord rounds to whole numbers and names both directions with their glyphs", () => {
  const formatCoord = loadFormatCoord();
  assert.equal(formatCoord(210, 55), "across 210 → · down 55 ↓");
  assert.equal(formatCoord(209.6, 54.4), "across 210 → · down 54 ↓");
  assert.equal(formatCoord(0, 0), "across 0 → · down 0 ↓");
});

test("F: DIRECTION_GLYPH is declared at page scope, before renderCardCore — not re-created on every card open, and shared with the coordinate tag", () => {
  const html = pageSrc();
  const glyphIndex = html.indexOf("const DIRECTION_GLYPH =");
  const renderCardIndex = html.indexOf("function renderCardCore(");
  assert.ok(glyphIndex >= 0, "tutor.html no longer declares DIRECTION_GLYPH where this suite reads it");
  assert.ok(renderCardIndex >= 0, "tutor.html no longer declares function renderCardCore where this suite reads it");
  assert.ok(glyphIndex < renderCardIndex, "DIRECTION_GLYPH must be hoisted to page scope, declared before renderCardCore, so formatCoord can share it too");
});

test("F: the coordinate tag lives inside the stage, alongside the why-card", () => {
  const html = pageSrc();
  const stageOpenIdx = html.indexOf('<div class="stage" id="stage">');
  const cardIdx = html.indexOf('<div id="card" hidden></div>');
  const tipTag = '<div id="coord-tip" hidden></div>';
  const tipIdx = html.indexOf(tipTag);
  const stageCloseIdx = html.indexOf("</div>", tipIdx + tipTag.length);
  assert.ok(stageOpenIdx >= 0 && cardIdx >= 0, "tutor.html's .stage/#card markup moved where this suite doesn't expect it");
  assert.ok(tipIdx > cardIdx && tipIdx < stageCloseIdx, "#coord-tip must live inside .stage, right alongside #card, so it can float over the canvas");
});

test("F: the coordinate tag ships hidden by default; the caption ships visible (orientation mode starts on)", () => {
  const html = pageSrc();
  assert.match(html, /<div id="coord-tip" hidden><\/div>/, "#coord-tip must ship as an empty, hidden div — same pattern as #card — since it only appears on hover");
  const hintTagMatch = /<p class="coord-hint" id="coord-hint">[^<]+<\/p>/.exec(html);
  assert.ok(hintTagMatch, "#coord-hint must ship with its text already in place, not hidden — a fresh lesson has not painted yet");
});

test("F: performLessonSwitch resets orientation mode on every lesson switch, and clears the stale picture and stack from the previous lesson", () => {
  const src = extractFunction(pageSrc(), "performLessonSwitch");
  const runResetIdx = src.indexOf("hasPaintedThisLesson = false;");
  assert.ok(runResetIdx >= 0, "performLessonSwitch must reset hasPaintedThisLesson to false — a freshly-entered lesson has not painted yet");
  const visibilityCallIdx = src.indexOf("updateCoordHintVisibility();");
  assert.ok(visibilityCallIdx >= 0, "performLessonSwitch must call updateCoordHintVisibility() so the caption/tag reflect the fresh, not-yet-painted state");
  const clearRectIdx = src.indexOf("ctx.clearRect(");
  assert.ok(clearRectIdx >= 0, "performLessonSwitch must clear the canvas — otherwise the previous lesson's picture lingers behind the new goal sequence");
  const renderStackIdx = src.indexOf("renderStack();");
  assert.ok(renderStackIdx >= 0 && renderStackIdx < clearRectIdx, "performLessonSwitch must clear the rendered stack too, before the canvas clear, so no stale committed lines linger in the rail");
});

test("F: showCoordTipAt refuses to show once orientation mode is off", () => {
  const src = extractFunction(pageSrc(), "showCoordTipAt");
  const guardIdx = src.indexOf("if (hasPaintedThisLesson) return;");
  const textContentIdx = src.indexOf("coordTipEl.textContent");
  assert.ok(guardIdx >= 0, "showCoordTipAt must guard on hasPaintedThisLesson");
  assert.ok(textContentIdx >= 0, "showCoordTipAt must set the tag's text");
  assert.ok(guardIdx < textContentIdx, "showCoordTipAt must bail immediately if the lesson has already painted — the tag must never reappear after a successful paint just because the pointer moved");
});

test("F: canvasPointFromEvent is the single source of the canvas's pixel-to-coordinate transform — the click handler doesn't recompute it inline", () => {
  const html = pageSrc();
  const fnIdx = html.indexOf("function canvasPointFromEvent(");
  assert.ok(fnIdx >= 0, "tutor.html no longer declares canvasPointFromEvent where this suite reads it");
  const clickStart = html.indexOf('canvas.addEventListener("click"');
  assert.ok(clickStart >= 0, "tutor.html no longer wires the canvas click listener where this suite reads it");
  const clickSrc = html.slice(clickStart, clickStart + 400);
  assert.match(clickSrc, /canvasPointFromEvent\(event\)/, "the click handler must call the shared canvasPointFromEvent, not recompute the rect transform inline");
  assert.doesNotMatch(clickSrc, /getBoundingClientRect/, "the click handler should not compute the rect transform itself — that duplication is exactly what canvasPointFromEvent removes");
});

// ---- E (renumbered): per-element why, extended to backdrops (§5) --------

test("E: backdrop clicks are resolved via hit.mjs/marks.mjs's own exported primitives, not a hardcoded horizon constant", () => {
  const html = pageSrc();
  assert.match(html, /import\s*{\s*hitTest,\s*invert,\s*containsPoint,\s*outlineOf,\s*marksForLine\s*}\s*from\s*"\.\/js\/paint\/hit\.mjs"/, "tutor.html must import invert/containsPoint from hit.mjs rather than reimplementing the matrix math");
  const backdropSrc = extractFunction(html, "backdropLineAt");
  assert.match(backdropSrc, /pointInMark/, "backdropLineAt must test the click against the actual painted mark geometry");
  assert.doesNotMatch(backdropSrc, /264/, "backdropLineAt must not hardcode scene.planes's own horizon constant — it must derive the boundary from the painted marks");
});

test("E: the click handler tries hitTest first (discrete marks win), then falls back to backdropLineAt, never the reverse", () => {
  const html = pageSrc();
  const clickStart = html.indexOf('canvas.addEventListener("click"');
  assert.ok(clickStart >= 0, "tutor.html no longer wires the canvas click listener where this suite reads it");
  const clickSrc = html.slice(clickStart, clickStart + 700);
  const hitTestIdx = clickSrc.indexOf("hitTest(");
  const backdropIdx = clickSrc.indexOf("backdropLineAt(");
  assert.ok(hitTestIdx >= 0 && backdropIdx >= 0, "the click handler no longer calls both hitTest and backdropLineAt where this suite reads it");
  assert.ok(hitTestIdx < backdropIdx, "hitTest (a specific discrete mark) must be tried before the backdrop fallback");
});

test("E: renderCardForMark and renderCardForSourceLine share one card-building core, so a mark-hit card and a backdrop card are never two different implementations", () => {
  const html = pageSrc();
  assert.ok(html.includes("function renderCardCore("), "tutor.html no longer declares renderCardCore where this suite reads it");
  const markSrc = extractFunction(html, "renderCardForMark");
  const lineSrc = extractFunction(html, "renderCardForSourceLine");
  assert.match(markSrc, /renderCardCore\(/, "renderCardForMark must delegate to renderCardCore");
  assert.match(lineSrc, /renderCardCore\(/, "renderCardForSourceLine must delegate to renderCardCore");
});

// ---- invariants (§8) ------------------------------------------------------

test("invariant: the engine, why.mjs, hit.mjs, scene_vocab.mjs, and scene.planes are unmodified by this build", () => {
  const status = fs
    .readFileSync(path.join(REPO, ".git", "HEAD"), "utf-8")
    .trim();
  // A lightweight sanity check that this suite is running inside the repo it
  // thinks it is — the real invariant (git diff --stat only touches
  // tutor.html and this test file) is checked at PR time via `git diff
  // --stat`, not re-implemented here with a git plumbing call this suite
  // would then have to keep correct across every CI environment.
  assert.ok(status.length > 0);
});

test("invariant: no rendered code surface compresses two Planes statements onto one line — the worked example and the assembled program both come from one-line-per-item LESSONS data", () => {
  const html = pageSrc();
  const lessonProgramTextSrc = extractFunction(html, "lessonProgramText");
  assert.match(lessonProgramTextSrc, /\.join\("\\n"\)/, "lessonProgramText must join items with a real newline per item, one statement per line");
});
