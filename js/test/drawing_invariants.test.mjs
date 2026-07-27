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

test("VERBS is the twenty-six of protocol version 1, exactly", () => {
  assert.deepEqual(VERBS.slice().sort(), [
    "align", "arc", "background", "cap", "circle", "clear", "close", "corner",
    "curve", "ellipse", "end", "fill", "label", "line", "pop", "push", "rect",
    "rotate", "scale", "shape", "size", "stroke", "translate", "triangle",
    "vertex", "width",
  ]);
});

test("no Planes source emits a raw draw string except paint/draw.planes", () => {
  const offenders = fs
    .readdirSync(path.join(REPO, "paint"))
    .filter((f) => f.endsWith(".planes") && f !== "draw.planes")
    .filter((f) => /show\s+"draw\b/.test(read(path.join("paint", f))));
  assert.deepEqual(offenders, [], "a program assembled a protocol line by hand");
});

// ---- one stream walk, two renderers -----------------------------------------
// (Behaviour: js/test/paint_conformance.test.mjs. Shape: here.)

const WALK_OWNED_TAGS = [
  "protocol-repeated", "protocol-late", "unsupported-version",
  "path-already-open", "path-not-open", "path-unclosed",
  "unmatched-pop", "unmatched-push",
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

test("the language's counts: 32 keywords, 11 builtins, 7 effect kinds", () => {
  const vocab = JSON.parse(read("grammar/vocabulary.json"));
  assert.equal(vocab.keywords.length, 32);
  assert.equal(vocab.builtins.length, 11);
  assert.equal(vocab.effect_kinds.length, 7);
});

// ---- the page reaches for nothing off-origin ---------------------------------

const offOrigin = (u) => /^(https?:)?\/\//.test(u);

for (const page of ["paint.html", "index.html"]) {
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
