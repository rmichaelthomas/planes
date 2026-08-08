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
  // The body's opening "{" is the first one AFTER the parameter list's own
  // matching ")" — not just the first "{" anywhere after the name. A
  // destructured-default parameter like `{ pushUrl = true } = {}`
  // (setLesson's own signature) has its own "{"/"}" pair INSIDE the
  // parameter list, before the body even starts; naively taking the first
  // "{" after the marker would stop at that pair instead.
  let parenDepth = 0;
  let j = start + marker.length - 1; // at the opening "("
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

function loadGhostFor() {
  const html = pageSrc();
  const BLANK = html.match(/const BLANK = ("[^"]*");/)[1];
  const ghostLineSrc = extractFunction(html, "ghostLine");
  const ghostSuffixSrc = extractFunction(html, "ghostSuffix");
  const ghostForSrc = extractFunction(html, "ghostFor");
  const lessonsLiteral = extractArrayLiteral(html, "LESSONS");
  // eslint-disable-next-line no-new-func
  return new Function(
    `const BLANK = ${BLANK};\nconst LESSONS = ${lessonsLiteral};\n${ghostLineSrc}\n${ghostSuffixSrc}\n${ghostForSrc}\nreturn ghostFor;`,
  )();
}

function loadLessons() {
  const literal = extractArrayLiteral(pageSrc(), "LESSONS");
  // eslint-disable-next-line no-eval
  return eval(`(${literal})`);
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

test("E: ghost text is generated from LESSONS, never a second hand-kept copy, and is genuinely blanked", () => {
  const ghostLine = loadGhostLine();
  const LESSONS = loadLessons();
  LESSONS.forEach((spec, i) => {
    const ghosted = spec.lines.map(ghostLine);
    const anyBlanked = ghosted.some((l) => l.includes("…"));
    assert.ok(anyBlanked, `lesson ${i}'s ghost text carries no blanks at all`);
    // every number and every quoted phrase in the real program is gone from
    // the ghost version
    for (const line of ghosted) {
      assert.ok(!/"[a-z][^"]*"/i.test(line), `a ghost line still carries a real quoted phrase: "${line}"`);
      assert.ok(!/\b\d+\b/.test(line) || line.includes("…"), `a ghost line still carries a raw number: "${line}"`);
    }
  });
});

test("E: every lesson's target program actually runs, and its ghost is a strict textual reduction of it (never longer, never a different line count)", () => {
  const ghostLine = loadGhostLine();
  const LESSONS = loadLessons();
  LESSONS.forEach((spec, i) => {
    assert.ok(Array.isArray(spec.lines) && spec.lines.length > 0, `lesson ${i} has no lines`);
    assert.equal(typeof spec.lesson, "string", `lesson ${i} has no lesson text`);
    assert.equal(typeof spec.title, "string", `lesson ${i} has no title`);
    const ghosted = spec.lines.map(ghostLine);
    assert.equal(ghosted.length, spec.lines.length, `lesson ${i}'s ghost has a different line count than its target`);
  });
});

test("E: ghost text and the real editor are separate elements — the ghost pre is never nested inside the textarea", () => {
  const html = pageSrc();
  const ghostIdx = html.indexOf('id="ghost"');
  const textareaOpen = html.indexOf('<textarea id="source"');
  const textareaClose = html.indexOf("</textarea>");
  assert.ok(ghostIdx >= 0 && textareaOpen >= 0 && textareaClose >= 0);
  assert.ok(ghostIdx < textareaOpen || ghostIdx > textareaClose, "#ghost must not be nested inside the #source textarea");
});

// She types OVER the ghost, not "before" it: it must keep showing whatever
// she has not reached yet on every keystroke, never vanish wholesale after
// the first one (a from-scratch first-time coder cannot be expected to
// memorise the whole shape from a single glance before she starts typing).

test("E: an untouched line still shows its full hint — the ghost does not require a first keystroke to appear", () => {
  const ghostFor = loadGhostFor();
  const full = ghostFor(0, "");
  assert.ok(full.includes('sky of "'), "lesson 0's ghost is empty before she has typed anything");
});

test("E: the ghost recedes exactly as far as she has typed on a line, and keeps hinting the rest", () => {
  const ghostFor = loadGhostFor();
  // She has typed the literal part of line 4 ('sky of "') but nothing of
  // her own phrase yet — the remaining hint (the blank and closing quote)
  // must still be there, padded out to start right where her text ends.
  const typed = 'use scene\n\nstart\nsky of "';
  const lines = ghostFor(0, typed).split("\n");
  assert.equal(lines[3].slice(0, 8), "        ", "the hint must not sit underneath what she already typed");
  assert.ok(lines[3].trim().length > 0, "the rest of line 4's hint vanished after only a partial keystroke");
});

test("E: once she has typed past a line's own hint, that line stops hinting (no overlap, nothing left to show)", () => {
  const ghostFor = loadGhostFor();
  const typed = 'use scene\n\nstart\nsky of "middle of the afternoon and then some more"';
  const lines = ghostFor(0, typed).split("\n");
  assert.equal(lines[3], "", "a line she has typed past its own target length must show no leftover hint");
});

test("E: a full, correct lesson-0 program leaves nothing left to hint on any of its own lines", () => {
  const ghostFor = loadGhostFor();
  const LESSONS = loadLessons();
  const typed = LESSONS[0].lines.join("\n");
  const remaining = ghostFor(0, typed);
  assert.equal(remaining.trim(), "", `finished lines still show a hint: ${JSON.stringify(remaining)}`);
});

test("E: ghostFor given text shaped like a different lesson still shows a live hint somewhere (the mechanism reads per-line, not all-or-nothing)", () => {
  // ghostFor is a pure function of (lessonIndex, typedText) — it has no
  // idea whether the browser's own reset-on-switch (setLesson, §6) put
  // that text there. Lessons no longer carry text forward between each
  // other in the live page, but the pure function must still degrade
  // sanely on a mismatched pairing: it must not go uniformly blank just
  // because SOME text is present — only a line whose own hint that text
  // actually covers should go blank.
  const ghostFor = loadGhostFor();
  const LESSONS = loadLessons();
  const typed = LESSONS[0].lines.join("\n");
  const otherGhost = ghostFor(2, typed).split("\n");
  const anyHint = otherGhost.some((l) => l.trim().length > 0);
  assert.ok(anyHint, "a mismatched lesson/text pairing shows nothing at all — the mechanism went uniformly blank");
});

// ---- F: orientation hint (hover-before-you-run coordinates) -----------

test("F: formatCoord rounds to whole numbers and names both directions with their glyphs", () => {
  const formatCoord = loadFormatCoord();
  assert.equal(formatCoord(210, 55), "across 210 → · down 55 ↓");
  assert.equal(formatCoord(209.6, 54.4), "across 210 → · down 54 ↓");
  assert.equal(formatCoord(0, 0), "across 0 → · down 0 ↓");
});

test("F: DIRECTION_GLYPH is declared at page scope, before renderCard — not re-created on every card open, and shared with the coordinate tag", () => {
  const html = pageSrc();
  const glyphIndex = html.indexOf("const DIRECTION_GLYPH =");
  const renderCardIndex = html.indexOf("function renderCard(");
  assert.ok(glyphIndex >= 0, "tutor.html no longer declares DIRECTION_GLYPH where this suite reads it");
  assert.ok(renderCardIndex >= 0, "tutor.html no longer declares function renderCard where this suite reads it");
  assert.ok(glyphIndex < renderCardIndex, "DIRECTION_GLYPH must be hoisted to page scope, declared before renderCard, so formatCoord can share it too");
});

test("F: the coordinate tag lives inside the stage, and the orientation caption sits just under it", () => {
  const html = pageSrc();
  const stageOpenIdx = html.indexOf('<div class="stage">');
  const cardIdx = html.indexOf('<div id="card" hidden></div>');
  const tipTag = '<div id="coord-tip" hidden></div>';
  const tipIdx = html.indexOf(tipTag);
  // #card and #coord-tip are each self-closing on one line, so the first
  // </div> AFTER coord-tip's own tag is .stage's real closing tag — the
  // first </div> after cardIdx would just be #card's own immediate close.
  const stageCloseIdx = html.indexOf("</div>", tipIdx + tipTag.length);
  const hintIdx = html.indexOf('id="coord-hint"');
  const canvasFootIdx = html.indexOf('class="canvas-foot"');
  assert.ok(stageOpenIdx >= 0 && cardIdx >= 0, "tutor.html's .stage/#card markup moved where this suite doesn't expect it");
  assert.ok(tipIdx > cardIdx && tipIdx < stageCloseIdx, "#coord-tip must live inside .stage, right alongside #card, so it can float over the canvas");
  assert.ok(hintIdx > stageCloseIdx && hintIdx < canvasFootIdx, "#coord-hint must sit between the stage and the canvas-foot buttons, as a caption under the picture");
});

test("F: the coordinate tag ships hidden by default; the caption ships visible (orientation mode starts on)", () => {
  const html = pageSrc();
  assert.match(html, /<div id="coord-tip" hidden><\/div>/, "#coord-tip must ship as an empty, hidden div — same pattern as #card — since it only appears on hover");
  const hintTagMatch = /<p class="coord-hint" id="coord-hint">[^<]+<\/p>/.exec(html);
  assert.ok(hintTagMatch, "#coord-hint must ship with its text already in place, not hidden — a fresh lesson has not been run yet");
});

test("F: performLessonSwitch resets orientation mode on every lesson switch, alongside the ghost/key reset", () => {
  // setLesson only guards (deferring to the in-page lesson-advance dialog
  // when there's unsaved text); performLessonSwitch is what actually
  // performs the switch and is where this suite's resets live.
  const src = extractFunction(pageSrc(), "performLessonSwitch");
  const ghostResetIdx = src.indexOf("ghostHidden = false;");
  const runResetIdx = src.indexOf("hasRunThisLesson = false;");
  assert.ok(ghostResetIdx >= 0, "performLessonSwitch no longer resets ghostHidden where this suite expects it");
  assert.ok(runResetIdx >= 0, "performLessonSwitch must reset hasRunThisLesson to false — a freshly-entered lesson has not been run yet");
  const visibilityCallIdx = src.indexOf("updateCoordHintVisibility();");
  assert.ok(visibilityCallIdx >= 0, "performLessonSwitch must call updateCoordHintVisibility() so the caption/tag reflect the fresh, not-yet-run state");
});

test("F: run() only turns off orientation mode on the genuine success path, after every early-return guard", () => {
  const src = extractFunction(pageSrc(), "run");
  const lastReturnIdx = src.lastIndexOf("return;");
  const setTrueIdx = src.indexOf("hasRunThisLesson = true;");
  assert.ok(setTrueIdx >= 0, "run() must set hasRunThisLesson = true on success — otherwise orientation mode never turns off");
  assert.ok(setTrueIdx > lastReturnIdx, "hasRunThisLesson = true must come after every early-return guard, so a failed run leaves orientation mode on");
  const visibilityCallIdx = src.indexOf("updateCoordHintVisibility();", setTrueIdx);
  assert.ok(visibilityCallIdx > setTrueIdx, "run() must call updateCoordHintVisibility() right after flipping hasRunThisLesson, so the tag/caption actually update");
});

test("F: updateCoordHintVisibility ties both the tag and the caption to the same hasRunThisLesson flag", () => {
  const src = extractFunction(pageSrc(), "updateCoordHintVisibility");
  assert.match(src, /coordHintEl\.hidden = hasRunThisLesson/, "the caption's hidden state must mirror hasRunThisLesson directly");
  assert.match(src, /hideCoordTip\(\)/, "once a run succeeds, any tag still showing (pointer resting over the canvas) must be force-hidden too");
});

test("F: canvasPointFromEvent is the single source of the canvas's pixel-to-coordinate transform — the click handler no longer computes it inline", () => {
  const html = pageSrc();
  const fnIdx = html.indexOf("function canvasPointFromEvent(");
  assert.ok(fnIdx >= 0, "tutor.html no longer declares canvasPointFromEvent where this suite reads it");
  const clickStart = html.indexOf('canvas.addEventListener("click"');
  assert.ok(clickStart >= 0, "tutor.html no longer wires the canvas click listener where this suite reads it");
  const clickSrc = html.slice(clickStart, clickStart + 400);
  assert.match(clickSrc, /canvasPointFromEvent\(event\)/, "the click handler must call the shared canvasPointFromEvent, not recompute the rect transform inline");
  assert.doesNotMatch(clickSrc, /getBoundingClientRect/, "the click handler should no longer compute the rect transform itself — that duplication is exactly what canvasPointFromEvent removes");
});

test("F: hovering the stage is wired to the shared transform and to showCoordTipAt, and leaving it hides the tag", () => {
  const html = pageSrc();
  assert.match(
    html,
    /canvas\.addEventListener\("pointermove",[\s\S]{0,200}canvasPointFromEvent\(event\)[\s\S]{0,200}showCoordTipAt/,
    "pointermove on the canvas must compute the point via canvasPointFromEvent and show the tag via showCoordTipAt",
  );
  assert.match(html, /canvas\.addEventListener\("pointerleave",\s*hideCoordTip\)/, "leaving the canvas must hide the coordinate tag");
});

test("F: showCoordTipAt refuses to show once orientation mode is off", () => {
  const src = extractFunction(pageSrc(), "showCoordTipAt");
  const guardIdx = src.indexOf("if (hasRunThisLesson) return;");
  const textContentIdx = src.indexOf("coordTipEl.textContent");
  assert.ok(guardIdx >= 0, "showCoordTipAt must guard on hasRunThisLesson");
  assert.ok(textContentIdx >= 0, "showCoordTipAt must set the tag's text");
  assert.ok(guardIdx < textContentIdx, "showCoordTipAt must bail immediately if the lesson has already been run — the tag must never reappear after a successful run just because the pointer moved");
});
