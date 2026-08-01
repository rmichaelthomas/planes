// js/test/drawing_invariants.test.mjs — the structural invariants of the
// drawing stack, graduated out of three retired verification scripts.
//
// WHY THIS FILE EXISTS. Three builds in a row shipped a `scripts/verify-*.mjs`
// holding assertions like these, and nothing ever ran them: `ci.sh` runs
// `js/test/*.mjs` and the Python checkers, and none of those is a verification
// script. By the time this was counted, `verify-canvas-runtime.mjs` had been
// reporting BLOCKING FAILURE on green main for two builds — it still asserted
// the retired ten-verb whitelist — and nobody knew, because nobody ran it.
//
// That is the fifth instance of one failure class and the exact thing
// `scripts/ci.sh`'s RETIREMENT RULE names: a build's verification script
// GRADUATES INTO A SUITE OR IS DELETED WHEN ITS BUILD MERGES. This is the
// graduation. `test_gate.py` now catches the JavaScript shape of the problem
// as well as the Python one, so a sixth instance fails the gate rather than
// sitting in the repo being wrong.
//
// Everything here is a claim about SHAPE — what a file contains, what a module
// exports, how many methods an interface has. Nothing here runs a program;
// behaviour is tested by the suites named beside each claim.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { VERBS } from "../paint/protocol.mjs";
import { Host } from "../host.mjs";

const REPO = fileURLToPath(new URL("../../", import.meta.url));
const read = (p) => fs.readFileSync(path.join(REPO, p), "utf8");

function everyMjs() {
  const found = [];
  (function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (entry.name.endsWith(".mjs")) found.push(p);
    }
  })(path.join(REPO, "js"));
  return found;
}

// A file SAYING it does not emit a CSS oklch() string must not be mistaken for
// one that does, so comments come out before any of these scans.
const stripComments = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/[^\n]*/g, "$1");

// ---- the protocol and its library are the same thing written twice ----------
// (planes-drawing-protocol-v1.md §11 — "mechanically checkable", so checked.)

test("paint/draw.planes defines exactly one helper per verb, and nothing else", () => {
  const defined = [...read("paint/draw.planes").matchAll(/^to\s+([a-z-]+)\s*(?:of\b|:)/gm)].map((m) => m[1]);
  assert.equal(new Set(defined).size, defined.length, "a helper is defined twice");
  assert.deepEqual(
    defined.slice().sort(),
    VERBS.slice().sort(),
    "draw.planes and the verb table have drifted apart",
  );
});

test("VERBS is the thirty-four of protocol versions 1-3, exactly", () => {
  assert.deepEqual(VERBS.slice().sort(), [
    "align", "alpha", "arc", "background", "blend", "blur", "cap", "circle",
    "clear", "clip", "close", "corner", "curve", "dash", "ellipse", "end",
    "fill", "gradient", "label", "line", "pop", "push", "rect", "rotate",
    "scale", "shadow", "shape", "size", "stroke", "translate", "triangle",
    "unclip", "vertex", "width",
  ]);
});

test("no Planes source emits a raw draw string except paint/draw.planes and the protocol declaration", () => {
  // draw.planes deliberately carries no `protocol` helper (v2 §6.6's own
  // draw.planes header, and planes-drawing-protocol-v2.md §1.1): a program
  // states its version once, directly, as `show "draw protocol N"`. That
  // one exact shape is the only raw "draw " string any other program may
  // emit — anything else is a hand-assembled protocol line.
  const offenders = fs
    .readdirSync(path.join(REPO, "paint"))
    .filter((f) => f.endsWith(".planes") && f !== "draw.planes")
    .filter((f) => {
      const withoutDeclaration = read(path.join("paint", f)).replace(/show\s+"draw protocol \d+"/g, "");
      return /show\s+"draw\b/.test(withoutDeclaration);
    });
  assert.deepEqual(offenders, [], "a program assembled a protocol line by hand");
});

// ---- one stream walk, two renderers -----------------------------------------
// (Behaviour: js/test/paint_conformance.test.mjs. Shape: here.)

const WALK_OWNED_TAGS = [
  "protocol-repeated", "protocol-late", "unsupported-version",
  "path-already-open", "path-not-open", "path-unclosed",
  "unmatched-pop", "unmatched-push",
  // v2 additions.
  "verb-not-in-version", "unmatched-unclip", "clip-unclosed",
];

test("every stream-level error tag is raised by stream.mjs", () => {
  const stream = read("js/paint/stream.mjs");
  for (const tag of WALK_OWNED_TAGS) {
    assert.match(stream, new RegExp(`tag: "${tag}"`), `stream.mjs does not raise ${tag}`);
  }
});

test("neither renderer carries its own copy of the walk", () => {
  for (const file of ["js/paint/painter.mjs", "js/paint/svg.mjs"]) {
    const src = read(file);
    for (const tag of WALK_OWNED_TAGS) {
      assert.doesNotMatch(src, new RegExp(`tag: "${tag}"`), `${file} raises ${tag} itself`);
    }
    assert.doesNotMatch(src, /parseCommand/, `${file} reads the stream itself`);
    assert.match(src, /from "\.\/stream\.mjs"/, `${file} does not drive the shared walk`);
  }
});

// ---- one colour conversion ---------------------------------------------------

test("oklchToRgb is defined once, in js/paint/color.mjs", () => {
  const defining = everyMjs().filter((f) => /function\s+oklchToRgb\s*\(/.test(fs.readFileSync(f, "utf8")));
  assert.deepEqual(
    defining.map((f) => path.relative(REPO, f)),
    ["js/paint/color.mjs"],
  );
});

test("both renderers import the shared colour module rather than reimplementing it", () => {
  for (const file of ["js/paint/painter.mjs", "js/paint/svg.mjs"]) {
    assert.match(read(file), /from "\.\/color\.mjs"/, file);
  }
});

test("no CSS oklch() string appears in any renderer .mjs", () => {
  // js/test/ is excluded: a test NAMED "no CSS oklch() string is ever emitted"
  // is the opposite of a violation, and a check that cannot tell naming a
  // thing from doing it is not a check.
  const offenders = everyMjs()
    .filter((f) => !f.startsWith(path.join(REPO, "js", "test") + path.sep))
    .filter((f) => /oklch\s*\(/.test(stripComments(fs.readFileSync(f, "utf8"))));
  assert.deepEqual(offenders.map((f) => path.relative(REPO, f)), []);
});

// ---- the seams that must not grow -------------------------------------------

test("the Host interface is the same seven methods, plus record and targetHint", () => {
  const declared = Object.getOwnPropertyNames(Host.prototype)
    .filter((n) => n !== "constructor")
    // `name` is an accessor, not part of the seam.
    .filter((n) => typeof Object.getOwnPropertyDescriptor(Host.prototype, n).value === "function")
    .sort();
  const SEVEN = ["ask", "clock", "parseJson", "read", "resolve", "show", "write"];
  for (const m of SEVEN) assert.ok(declared.includes(m), `host.mjs lost ${m}`);
  assert.deepEqual(declared, [...SEVEN, "record", "targetHint"].sort());
});

test("js/modules.mjs is pure: it imports nothing from node:", () => {
  // The module loader was made host-agnostic so the same resolution runs in a
  // browser; a single `node:fs` import would take that back.
  assert.doesNotMatch(read("js/modules.mjs"), /from\s+"node:/);
});

test("the language's counts: 32 keywords, 13 builtins, 7 effect kinds", () => {
  const vocab = JSON.parse(read("grammar/vocabulary.json"));
  assert.equal(vocab.keywords.length, 32);
  assert.equal(vocab.builtins.length, 13);
  assert.equal(vocab.effect_kinds.length, 7);
});

// ---- the page reaches for nothing off-origin ---------------------------------

const offOrigin = (u) => /^(https?:)?\/\//.test(u);

// DERIVED, NOT LISTED. This was `["paint.html", "index.html", "garden.html"]`,
// and a hardcoded set of pages that all exist always passes — so try.html was
// added to the site and checked by nothing. Every root page is a served page
// (the deploy is `cp ./*.html _site/`), so every root page is checked.
const ROOT_PAGES = fs.readdirSync(new URL("../../", import.meta.url))
  .filter((f) => f.endsWith(".html")).sort();

for (const page of ROOT_PAGES) {
  test(`${page} loads nothing off-origin: no CDN, no npm package, no bundler`, () => {
    const html = read(page);
    // What counts is what the page FETCHES. A `src` always does. A `<link>`
    // does only for the rels below — `rel="canonical"` is a statement to a
    // search engine and is never requested, and an `<a href>` is somewhere a
    // reader can choose to go. index.html has both, and neither is a
    // dependency.
    const FETCHING_REL = /\brel\s*=\s*"(stylesheet|preload|modulepreload|prefetch|icon|shortcut icon|apple-touch-icon|manifest)"/i;
    const fetched = [
      ...[...html.matchAll(/\bsrc\s*=\s*"([^"]+)"/g)].map((m) => m[1]),
      ...[...html.matchAll(/<link\b([^>]*)>/g)]
        .filter((m) => FETCHING_REL.test(m[1]))
        .map((m) => (/\bhref\s*=\s*"([^"]+)"/.exec(m[1]) || [])[1])
        .filter(Boolean),
    ].filter(offOrigin);
    assert.deepEqual(fetched, []);
    assert.doesNotMatch(html, /from ["']https?:/, "an ES import reaches off-origin");
    assert.doesNotMatch(html, /require\(/, "a CommonJS require appears in a page with no bundler");
  });
}

test("paint.html says what each export means, under the buttons", () => {
  const html = read("paint.html");
  for (const id of ["paint-save-svg", "paint-save-png", "paint-record", "paint-export-hint"]) {
    assert.ok(html.includes(`id="${id}"`), `no ${id}`);
  }
  // Specification §8.1: a still-image renderer captures ONE STREAM, and a
  // learner expecting an animated SVG must be told rather than surprised.
  assert.match(html, /SVG and PNG save the frame on screen now\. Video records ten seconds\./);
});

test("paint.html carries no garden entry, no day scrubber — garden.html is its own page", () => {
  const html = read("paint.html");
  assert.doesNotMatch(html, /garden/i);
  assert.doesNotMatch(html, /day scrubber|paint-day/i);
});

test("garden.html exists as a sibling of paint.html, fetches garden.planes rather than inlining it, and says how to serve itself", () => {
  const html = read("garden.html");
  // The program is loaded via createProgramSession's own fetch (asserted
  // against program_session.mjs directly below), never pasted into the
  // page — garden.html's <textarea> is populated at runtime from that
  // fetch, not from a literal copy of the source in this file.
  assert.doesNotMatch(html, /let canvas-width = 480/, "the program is fetched, not pasted into the page");
  assert.match(html, /createProgramSession\(\{\s*file:\s*"paint\/garden\.planes"/s, "loads its program through the shared session module, by file path");
  assert.match(html, /python3 -m http\.server/, "states how to serve itself, so the requirement is not rediscovered");
  for (const id of [
    "garden-day", "garden-day-back", "garden-day-forward", "garden-seed",
    "garden-save-svg", "garden-save-png", "garden-surface",
    // The source is shown as a LINE-ADDRESSABLE VIEW, not the editable
    // textarea this page used to carry. Two reasons, and the second is the
    // one that forced it: a textarea cannot highlight one line, and hovering
    // a source line to light up every mark it drew is the whole point of the
    // map running both ways. The first is that the textarea was never
    // editable in the sense it advertised — nothing read it back, and only
    // "Reload modules" re-fetched the file.
    "garden-source-view",
    // A scene that lives: play, a speed toggle, a clock, a weather readout,
    // sound, and a card to answer a click with.
    //
    // ONE TOGGLE, NOT THREE BUTTONS. The 1x/4x/16x triple this list used to
    // name was replaced by `garden-fast` when the page was built to its
    // spec (garden-page-spec.md §3.4): three buttons to express two states
    // is the mockup's grammar refused, and a control nobody moved off 1x is
    // a control that was measuring nothing.
    "garden-play", "garden-fast",
    "garden-sound", "garden-clock", "garden-weather", "garden-card",
  ]) {
    assert.ok(html.includes(`id="${id}"`), `no ${id}`);
  }
  for (const gone of ["garden-speed-1", "garden-speed-4", "garden-speed-16"]) {
    assert.ok(!html.includes(`id="${gone}"`), `${gone} came back`);
  }
});

test("garden.html's play loop, hit testing and why panel come from shared modules, not inline reimplementations", () => {
  const html = read("garden.html");
  for (const mod of ["loop", "marks", "hit", "why", "stream"]) {
    assert.match(html, new RegExp(`from ["']\\./js/paint/${mod}\\.mjs["']`), `garden.html does not import ${mod}.mjs`);
  }
  assert.match(html, /from ["']\.\/js\/sound\/audio\.mjs["']/);
  assert.match(html, /from ["']\.\/js\/sound\/stream\.mjs["']/);
});

test("sound fires while playing or on a click that landed on a flower — never on a scrub, never on the export path", () => {
  const html = read("garden.html");
  // The loop's call is guarded by all three of: this frame came from the
  // loop, sound is on, and a player exists.
  assert.match(html, /if \(playing && soundOn && player\) \{/);

  // THE SECOND SOURCE IS NEW AND IS NOT A LOOSENING. garden-page-spec.md
  // §3.8 makes a click on a mark play that mark's note, so "exactly one
  // place plays" stopped being the invariant — but the shape of the old
  // assertion (a literal `player.play(` count) would have kept passing
  // anyway, because the new call goes through `ensurePlayer()`. A check that
  // survives the change it was meant to notice is worse than no check, so it
  // is replaced rather than left to keep reporting green.
  const playSites = html.match(/\bplay\(\s*(lastLines|lines)\s*\)/g) ?? [];
  assert.equal(playSites.length, 2, `expected the loop and the click, got ${playSites.length}`);
  assert.match(html, /function playOneNote\(note\)/, "the click's note goes through one named path");
  // The click path is reached only from the card, which is reached only from
  // a hit on one of the six clickable subjects — and it builds its own
  // four-line stream rather than replaying the frame, so clicking cannot
  // sound the whole tick.
  assert.match(html, /if \(note\) playOneNote\(note\);/);
  assert.match(html, /sound note \$\{note\.numerator\} \$\{note\.denominator\}/);

  // Neither the scrubber nor either exporter reaches a player.
  const scrubBody = html.slice(html.indexOf("onChange: (tick)"), html.indexOf("const loop = createSceneLoop"));
  assert.ok(!/play\(/.test(scrubBody), "scrubbing must not play");
  const svgHandler = html.slice(html.indexOf('$("garden-save-svg")'), html.indexOf('$("garden-save-png")'));
  const pngHandler = html.slice(html.indexOf('$("garden-save-png")'), html.indexOf("// ---- the surface, summarized"));
  assert.ok(!/playOneNote|\.play\(/.test(svgHandler), "SVG export must not play");
  assert.ok(!/playOneNote|\.play\(/.test(pngHandler), "PNG export must not play");
});

test("js/paint/program_session.mjs loads its program by fetch, not by inlining it", () => {
  const src = read("js/paint/program_session.mjs");
  assert.match(src, /fetch\(`\$\{file\}/);
});

test("garden.html imports the shared program-load/scrubber/surface modules rather than reimplementing them inline", () => {
  const html = read("garden.html");
  assert.match(html, /from ["']\.\/js\/paint\/program_session\.mjs["']/);
  assert.match(html, /from ["']\.\/js\/paint\/tick_scrubber\.mjs["']/);
  assert.match(html, /from ["']\.\/js\/paint\/surface_pane\.mjs["']/);
});
