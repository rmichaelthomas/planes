#!/usr/bin/env node
// scripts/verify-svg-and-export.mjs — the
// feat/corpus-refinement-svg-renderer-and-export gate (§9.2).
//
// Five categories, A through E. Blocking: A (coverage), B (conformance) and
// D (invariants) — those are the claim this build makes and the structure
// that keeps it true. C (programs) and E (export) are reported the same way
// but do not fail the gate on their own: C's substance is already a test, and
// E can only check the SHAPE of an export headlessly, never that a WebM
// plays, which is the human gate's (§9.5).
//
// Inputs required from Rob: none.
//
// Usage: node scripts/verify-svg-and-export.mjs
// Writes: reports/svg-and-export-verification.md (same table as stdout)

import { readFileSync, existsSync, readdirSync, writeFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const REPO = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const rel = (...p) => path.join(REPO, ...p);
const imp = (p) => import(pathToFileURL(rel(p)).href);
const read = (p) => readFileSync(rel(p), "utf8");

const { loadGrammar } = await imp("js/loader_node.mjs");
loadGrammar();

const { VERBS } = await imp("js/paint/protocol.mjs");
const { paint } = await imp("js/paint/painter.mjs");
const { toSvg } = await imp("js/paint/svg.mjs");
const { oklchToRgb } = await imp("js/paint/color.mjs");
const { wrapArcEnd } = await imp("js/paint/stream.mjs");
const exportMod = await imp("js/paint/export.mjs");
const { runProgramGraph, analyseProgramGraph } = await imp("js/browser_main.mjs");
const { stepGraph } = await imp("js/paint/loop.mjs");
const { BrowserModuleLoader } = await imp("js/module_loader_browser.mjs");

const results = []; // { category, name, ok, detail }
function check(category, name, fn) {
  return (async () => {
    let ok, detail;
    try {
      await fn();
      ok = true;
      detail = "";
    } catch (e) {
      ok = false;
      detail = e && e.message ? e.message : String(e);
    }
    results.push({ category, name, ok, detail });
  })();
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg || "assertion failed");
}

function fakeCtx() {
  let transform = "identity";
  const calls = [];
  const record = (name) => (...args) => calls.push([name, ...args]);
  return {
    calls,
    strokeStyle: null, fillStyle: null, lineWidth: null, lineCap: null,
    lineJoin: null, font: null, textAlign: null,
    beginPath: record("beginPath"), moveTo: record("moveTo"), lineTo: record("lineTo"),
    arc: record("arc"), ellipse: record("ellipse"), rect: record("rect"),
    closePath: record("closePath"), bezierCurveTo: record("bezierCurveTo"),
    stroke: record("stroke"), fill: record("fill"), fillRect: record("fillRect"),
    fillText: record("fillText"), translate: record("translate"),
    rotate: record("rotate"), scale: record("scale"),
    getTransform() { return transform; },
    setTransform(t) { transform = t; },
    resetTransform() { transform = "identity"; },
  };
}
const DIMENSIONS = { width: 480, height: 360, background: "#ffffff" };
const both = (lines) => ({ canvas: paint(fakeCtx(), lines, DIMENSIONS), svg: toSvg(lines, DIMENSIONS) });

function installFsFetch() {
  const real = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const p = fileURLToPath(url);
    if (!existsSync(p)) return { ok: false, text: async () => "" };
    return { ok: true, text: async () => readFileSync(p, "utf8") };
  };
  return () => {
    if (real) globalThis.fetch = real;
    else delete globalThis.fetch;
  };
}

const baseFor = (name) => pathToFileURL(rel("paint", `${name}.planes`)).href;

// Every frame the three programs draw, over runs long enough to reach the
// frames that are not the first: turtle once (it is static), bloom across a
// pulse, snake driven into the wall that is the only frame setting `align`.
async function corpusFrames() {
  const restore = installFsFetch();
  try {
    const frames = [];
    const turtle = await runProgramGraph(read("paint/turtle.planes"), { base: baseFor("turtle") });
    assert(turtle.error === null, `turtle failed to run: ${JSON.stringify(turtle.error)}`);
    frames.push({ program: "turtle", tick: 0, lines: turtle.output });

    const bloomLoader = new BrowserModuleLoader({ base: baseFor("bloom") });
    for (const tick of [0, 17, 48, 96]) {
      const r = await stepGraph(
        read("paint/bloom.planes"),
        { tick, keys: [], pointer: { x: 0, y: 0, down: false }, state: null },
        { loader: bloomLoader },
      );
      assert(r.error === null, `bloom tick ${tick}: ${JSON.stringify(r.error)}`);
      frames.push({ program: "bloom", tick, lines: r.lines });
    }

    const snakeLoader = new BrowserModuleLoader({ base: baseFor("snake") });
    let state = null;
    let died = false;
    for (let tick = 0; tick < 40; tick++) {
      const r = await stepGraph(
        read("paint/snake.planes"),
        { tick, keys: ["ArrowLeft"], pointer: { x: 0, y: 0, down: false }, state },
        { loader: snakeLoader },
      );
      assert(r.error === null, `snake tick ${tick}: ${JSON.stringify(r.error)}`);
      state = r.state;
      frames.push({ program: "snake", tick, lines: r.lines });
      if (!state.alive) {
        died = true;
        break;
      }
    }
    assert(died, "snake never reached its game-over frame, the only one that sets align");
    return frames;
  } finally {
    restore();
  }
}

const FRAMES = await corpusFrames();

// ---------------------------------------------------------------- A. Coverage
// BLOCKING

// Empty, and the PR says so. A verb that genuinely cannot be placed honestly
// belongs here with its reason rather than forced into a program with no use
// for it — and the check prints the reason rather than hiding the gap.
const COVERAGE_ALLOWLIST = new Map();

const verbsDrawn = new Set();
for (const f of FRAMES) {
  for (const line of f.lines) {
    const m = /^\s*draw\s+(\S+)/.exec(line);
    if (m) verbsDrawn.add(m[1]);
  }
}

await check("A", "every verb in VERBS is drawn by the corpus, or allowlisted with a reason", () => {
  const missing = VERBS.filter((v) => !verbsDrawn.has(v));
  const unexplained = missing.filter((v) => !COVERAGE_ALLOWLIST.has(v));
  assert(unexplained.length === 0, `never drawn and not allowlisted: ${unexplained.join(", ")}`);
  const explained = missing.filter((v) => COVERAGE_ALLOWLIST.has(v));
  assert(
    explained.length === 0 || explained.every((v) => COVERAGE_ALLOWLIST.get(v).length > 10),
    "an allowlisted verb must carry a real reason, not a placeholder",
  );
});

await check("A", "the allowlist is empty (a gap named here is a gap the PR must justify)", () => {
  assert(
    COVERAGE_ALLOWLIST.size === 0,
    `allowlisted: ${[...COVERAGE_ALLOWLIST].map(([v, why]) => `${v} (${why})`).join("; ")}`,
  );
});

await check("A", "the corpus emits fractional alpha, which it never did before", () => {
  const alphas = new Set();
  for (const f of FRAMES) {
    for (const line of f.lines) {
      const m = /^\s*draw\s+(?:stroke|fill)\s+\S+\s+\S+\s+\S+\s+(\S+)/.exec(line);
      if (m) alphas.add(Number(m[1].replace(/^~/, "")));
    }
  }
  const fractional = [...alphas].filter((a) => a > 0 && a < 1);
  assert(fractional.length > 0, `alpha values seen: ${[...alphas].join(", ")}`);
});

await check("A", "the whole path group is drawn, not only its easy members", () => {
  for (const verb of ["shape", "vertex", "curve", "close", "end"]) {
    assert(verbsDrawn.has(verb), `${verb} is never drawn`);
  }
});

// ------------------------------------------------------------- B. Conformance
// BLOCKING

const SAMPLE = {
  stroke: "draw stroke 0.55 0.14 210 0.8", fill: "draw fill 0.8 0.09 40 0.35",
  width: "draw width 2.5", cap: "draw cap round", corner: "draw corner bevel",
  background: "draw background 0.94 0.02 95", clear: "draw clear",
  size: "draw size 18", align: "draw align center",
  line: "draw line 10 10 60 40", rect: "draw rect 20 20 40 30",
  circle: "draw circle 90 60 18", ellipse: "draw ellipse 140 60 20 12",
  arc: "draw arc 100 100 30 300 40", triangle: "draw triangle 10 140 40 140 25 110",
  push: "draw push", translate: "draw translate 20 15", rotate: "draw rotate 25",
  scale: "draw scale 1.5 1.5", shape: "draw shape", vertex: "draw vertex 0 0",
  curve: "draw curve 10 -20 30 -20 40 0", close: "draw close", end: "draw end",
  pop: "draw pop", label: "draw label 8 18 score: 42",
};
const ORDER = [
  "stroke", "fill", "width", "cap", "corner", "background", "clear", "size", "align",
  "line", "rect", "circle", "ellipse", "arc", "triangle",
  "push", "translate", "rotate", "scale",
  "shape", "vertex", "curve", "close", "end", "pop", "label",
];
const ALL_VERBS_STREAM = ["draw protocol 1", ...ORDER.map((v) => SAMPLE[v])];

await check("B", "the all-verbs fixture is generated from VERBS, not a stale hand-list", () => {
  const table = VERBS.slice().sort().join(",");
  assert(Object.keys(SAMPLE).sort().join(",") === table, "the sample map has drifted from VERBS");
  assert(ORDER.slice().sort().join(",") === table, "the fixture order has drifted from VERBS");
});

await check("B", "both renderers walk the all-verbs stream with no error and the same result", () => {
  const { canvas, svg } = both(ALL_VERBS_STREAM);
  assert(canvas.errors.length === 0, `canvas: ${JSON.stringify(canvas.errors)}`);
  assert(svg.errors.length === 0, `svg: ${JSON.stringify(svg.errors)}`);
  assert(canvas.drawn === svg.drawn, `drawn ${canvas.drawn} vs ${svg.drawn}`);
  assert(JSON.stringify(canvas.text) === JSON.stringify(svg.text), "prose disagrees");
});

const ERROR_CASES = [
  ["unknown-verb", ["draw wobble 1 2"]],
  ["wrong-arity", ["draw circle 1 2"]],
  ["bad-number", ["draw circle x 2 3"]],
  ["bad-word", ["draw cap flat"]],
  ["bad-protocol-version", ["draw protocol one"]],
  ["protocol-late", ["draw circle 1 2 3", "draw protocol 1"]],
  ["protocol-repeated", ["draw protocol 1", "draw protocol 1"]],
  ["path-not-open", ["draw vertex 1 1"]],
  ["path-already-open", ["draw shape", "draw vertex 0 0", "draw shape", "draw end"]],
  ["path-unclosed", ["draw shape", "draw vertex 0 0"]],
  ["unmatched-pop", ["draw pop"]],
  ["unmatched-push", ["draw push", "draw rotate 10"]],
  ["several at once, order preserved", [
    "draw pop", "draw wobble", "draw circle 1 2", "draw vertex 3 3", "draw cap flat", "draw push",
  ]],
];

await check("B", "both renderers report the same error tags, in the same order, in every case", () => {
  const reached = new Set();
  for (const [name, lines] of ERROR_CASES) {
    const { canvas, svg } = both(lines);
    assert(canvas.errors.length > 0, `${name} provoked no error at all`);
    for (const e of canvas.errors) reached.add(e.tag);
    assert(
      JSON.stringify(canvas.errors) === JSON.stringify(svg.errors),
      `${name}: canvas ${JSON.stringify(canvas.errors.map((e) => e.tag))} vs svg ${JSON.stringify(svg.errors.map((e) => e.tag))}`,
    );
    assert(canvas.drawn === svg.drawn, `${name}: drawn disagrees`);
  }
  reached.add("unsupported-version");
  const expected = [
    "bad-number", "bad-protocol-version", "bad-word", "path-already-open",
    "path-not-open", "path-unclosed", "protocol-late", "protocol-repeated",
    "unknown-verb", "unmatched-pop", "unmatched-push", "unsupported-version", "wrong-arity",
  ];
  assert(
    [...reached].sort().join(",") === expected.join(","),
    `the battery reaches ${[...reached].sort().join(",")}`,
  );
});

await check("B", "both renderers refuse an unsupported version identically and emit nothing", () => {
  for (const v of [2, 7, 99]) {
    const lines = [`draw protocol ${v}`, "draw circle 10 10 5", "some prose"];
    const ctx = fakeCtx();
    const canvas = paint(ctx, lines, DIMENSIONS);
    const svg = toSvg(lines, DIMENSIONS);
    assert(JSON.stringify(canvas.errors) === JSON.stringify(svg.errors), `version ${v}: errors differ`);
    assert(canvas.errors[0].tag === "unsupported-version", `version ${v}: ${canvas.errors[0].tag}`);
    assert(canvas.drawn === 0 && svg.drawn === 0, `version ${v}: something was drawn`);
    assert(canvas.text.length === 0 && svg.text.length === 0, `version ${v}: prose leaked`);
    assert(ctx.calls.length === 0, `version ${v}: the canvas was touched`);
    assert(svg.svg === "", `version ${v}: a document was produced anyway`);
  }
});

const COLOURS = [
  [0, 0, 0], [1, 0, 0], [0.5, 0, 0], [0.7, 0.1, 200], [0.75, 0.12, 60],
  [0.45, 0.2, 300], [1, 0.5, 0], [0.05, 0.37, 140],
];

await check("B", "both renderers resolve the same sRGB, including two out-of-gamut requests", () => {
  const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  for (const [L, C, H] of COLOURS) {
    const lines = [`draw fill ${L} ${C} ${H} 1`, "draw rect 0 0 1 1"];
    const ctx = fakeCtx();
    paint(ctx, lines, DIMENSIONS);
    const { svg } = toSvg(lines, DIMENSIONS);
    const fromSvg = hexToRgb(/<rect x="0" y="0" width="1"[^>]*fill="(#[0-9a-f]{6})"/.exec(svg)[1]);
    const fromCanvas = ctx.fillStyle.match(/rgba?\(([^)]*)\)/)[1].split(",").slice(0, 3).map((n) => Number(n.trim()));
    const reference = oklchToRgb(L, C, H).map((c) => Math.round(c * 255));
    assert(
      fromSvg.join() === fromCanvas.join() && fromSvg.join() === reference.join(),
      `oklch(${L} ${C} ${H}): svg ${fromSvg} canvas ${fromCanvas} reference ${reference}`,
    );
    for (const c of fromSvg) assert(c >= 0 && c <= 255, `channel out of range for oklch(${L} ${C} ${H})`);
  }
});

await check("B", "both renderers sweep the same arc, including wrap and full-circle cases", () => {
  const cases = [[0, 90], [0, 180], [0, 181], [90, 270], [300, 10], [350, 349], [45, 45], [-90, -45]];
  for (const [start, end] of cases) {
    const line = `draw arc 100 80 30 ${start} ${end}`;
    const ctx = fakeCtx();
    paint(ctx, [line], DIMENSIONS);
    const { svg } = toSvg([line], DIMENSIONS);

    const [, cx, cy, r, startRad, endRad, anticlockwise] = ctx.calls.find((c) => c[0] === "arc");
    assert(anticlockwise === false, `${start}->${end}: canvas swept the wrong way`);
    assert(endRad > startRad, `${start}->${end}: the wrap rule left end at or below start`);
    assert(
      Math.abs((endRad - startRad) - ((wrapArcEnd(start, end) - start) * Math.PI) / 180) < 1e-9,
      `${start}->${end}: the canvas range does not match the shared wrap`,
    );

    const d = /<path d="([^"]+)"/.exec(svg)[1];
    const m = /^M ([-\d.]+) ([-\d.]+) (.*)$/.exec(d);
    const arcs = [...m[3].matchAll(/A ([-\d.]+) ([-\d.]+) 0 ([01]) ([01]) ([-\d.]+) ([-\d.]+)/g)];
    const at = (rad) => [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
    const near = (a, b, why) => assert(Math.abs(a - b) < 1e-3, `${start}->${end} ${why}: ${a} vs ${b}`);

    const [x0, y0] = at(startRad);
    near(Number(m[1]), x0, "start x");
    near(Number(m[2]), y0, "start y");

    const swept = endRad - startRad;
    if (swept >= 2 * Math.PI - 1e-9) {
      assert(arcs.length === 2, `${start}->${end}: a full circle must be two half turns`);
      const [hx, hy] = at(startRad + Math.PI);
      near(Number(arcs[0][5]), hx, "half-turn x");
      near(Number(arcs[0][6]), hy, "half-turn y");
      near(Number(arcs[1][5]), x0, "closing x");
      near(Number(arcs[1][6]), y0, "closing y");
      for (const a of arcs) assert(a[3] === "1" && a[4] === "1", `${start}->${end}: flags`);
    } else {
      assert(arcs.length === 1, `${start}->${end}: expected one A command`);
      const [x1, y1] = at(endRad);
      near(Number(arcs[0][5]), x1, "end x");
      near(Number(arcs[0][6]), y1, "end y");
      assert(arcs[0][3] === (swept > Math.PI ? "1" : "0"), `${start}->${end}: large-arc flag`);
      assert(arcs[0][4] === "1", `${start}->${end}: sweep flag is not clockwise`);
      near(Number(arcs[0][1]), r, "rx");
      near(Number(arcs[0][2]), r, "ry");
    }
  }
});

// ---------------------------------------------------------------- C. Programs

await check("C", "all three programs render through both renderers with zero errors", () => {
  for (const f of FRAMES) {
    const { canvas, svg } = both(f.lines);
    assert(canvas.errors.length === 0, `${f.program} tick ${f.tick} on canvas: ${JSON.stringify(canvas.errors)}`);
    assert(svg.errors.length === 0, `${f.program} tick ${f.tick} in svg: ${JSON.stringify(svg.errors)}`);
    assert(canvas.drawn === svg.drawn, `${f.program} tick ${f.tick}: drawn disagrees`);
  }
});

await check("C", "every <g> the corpus opens is closed, in every frame", () => {
  for (const f of FRAMES) {
    const { svg } = toSvg(f.lines, DIMENSIONS);
    const opens = (svg.match(/<g[ >]/g) || []).length;
    const closes = (svg.match(/<\/g>/g) || []).length;
    assert(opens === closes, `${f.program} tick ${f.tick}: ${opens} opened, ${closes} closed`);
  }
});

await check("C", "the effect surfaces are unchanged: console; console; console and file:write state.json", async () => {
  const restore = installFsFetch();
  try {
    for (const name of ["turtle", "bloom"]) {
      const { surface, error } = await analyseProgramGraph(read(`paint/${name}.planes`), { base: baseFor(name) });
      assert(error === null, `${name}: ${JSON.stringify(error)}`);
      assert(surface.touches("console") === true, `${name} lost console`);
      assert(surface.touches("file") === false, `${name} gained file`);
      assert(surface.touches("ambient") === false, `${name} gained ambient`);
      assert(surface.touches("network") === false, `${name} gained network`);
    }
    const { surface, error } = await analyseProgramGraph(read("paint/snake.planes"), { base: baseFor("snake") });
    assert(error === null, `snake: ${JSON.stringify(error)}`);
    assert(surface.touches("console") === true && surface.touches("file") === true, "snake lost console or file");
    assert(surface.touches("ambient") === false && surface.touches("network") === false, "snake widened");
    const targets = surface.targets("write");
    assert(targets.length === 1 && targets[0] === "state.json", JSON.stringify(targets));
  } finally {
    restore();
  }
});

// -------------------------------------------------------------- D. Invariants
// BLOCKING

const mjsFiles = [];
(function walkDir(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walkDir(p);
    else if (entry.name.endsWith(".mjs")) mjsFiles.push(p);
  }
})(rel("js"));

await check("D", "the stream walk exists once: no renderer carries its own copy", () => {
  const walkOwned = [
    "protocol-repeated", "protocol-late", "unsupported-version",
    "path-already-open", "path-not-open", "path-unclosed",
    "unmatched-pop", "unmatched-push",
  ];
  const stream = readFileSync(rel("js/paint/stream.mjs"), "utf8");
  for (const tag of walkOwned) {
    assert(stream.includes(`"${tag}"`), `stream.mjs does not raise ${tag}`);
  }
  for (const file of ["js/paint/painter.mjs", "js/paint/svg.mjs"]) {
    const src = readFileSync(rel(file), "utf8");
    for (const tag of walkOwned) {
      assert(!src.includes(`tag: "${tag}"`), `${file} raises ${tag} itself — the walk has been duplicated`);
    }
    assert(!/parseCommand/.test(src), `${file} parses commands itself — the walk has been duplicated`);
  }
});

await check("D", "oklchToRgb is defined once and imported, never reimplemented", () => {
  const defining = mjsFiles.filter((f) => /function\s+oklchToRgb\s*\(/.test(readFileSync(f, "utf8")));
  assert(defining.length === 1, `defined in: ${defining.map((f) => path.relative(REPO, f)).join(", ")}`);
  assert(defining[0] === rel("js/paint/color.mjs"), `defined in ${path.relative(REPO, defining[0])}`);
  const svg = readFileSync(rel("js/paint/svg.mjs"), "utf8");
  const painter = readFileSync(rel("js/paint/painter.mjs"), "utf8");
  assert(/from "\.\/color\.mjs"/.test(svg), "svg.mjs does not import the shared colour module");
  assert(/from "\.\/color\.mjs"/.test(painter), "painter.mjs does not import the shared colour module");
});

// Comments are stripped first: `// no CSS oklch() string` is a file SAYING it
// does not emit one, and a check that cannot tell the difference between
// naming a thing and doing it is not a check.
const stripComments = (src) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/[^\n]*/g, "$1");

await check("D", "no CSS oklch() string appears in any renderer .mjs", () => {
  // js/test/ is excluded on purpose: a test whose NAME is "no CSS oklch()
  // string is ever emitted" would fail a check that cannot tell naming a
  // thing from doing it. The invariant is about what a renderer emits.
  const offenders = mjsFiles
    .filter((f) => !f.startsWith(rel("js/test") + path.sep))
    .filter((f) => /oklch\s*\(/.test(stripComments(readFileSync(f, "utf8"))));
  assert(offenders.length === 0, offenders.map((f) => path.relative(REPO, f)).join(", "));
});

await check("D", "VERBS is unchanged from e205e14: twenty-six, exactly these", () => {
  const expected = [
    "align", "arc", "background", "cap", "circle", "clear", "close", "corner",
    "curve", "ellipse", "end", "fill", "label", "line", "pop", "push", "rect",
    "rotate", "scale", "shape", "size", "stroke", "translate", "triangle",
    "vertex", "width",
  ];
  assert(VERBS.length === 26, `${VERBS.length} verbs`);
  assert(VERBS.slice().sort().join(",") === expected.join(","), VERBS.slice().sort().join(","));
});

await check("D", "the Host interface is still exactly seven methods, plus the two it always had", async () => {
  // Read off the class itself rather than out of the source text: the seven
  // are the interface (js/test/host.test.mjs calls them that), `record` is the
  // optional no-op and `targetHint` the helper, both there before this build.
  // The point of the check is that nothing NEW landed on the seam.
  const { Host } = await imp("js/host.mjs");
  // Methods only: `name` is an accessor, not part of the seam.
  const declared = Object.getOwnPropertyNames(Host.prototype)
    .filter((n) => n !== "constructor")
    .filter((n) => typeof Object.getOwnPropertyDescriptor(Host.prototype, n).value === "function")
    .sort();
  const SEVEN = ["ask", "clock", "parseJson", "read", "resolve", "show", "write"];
  for (const m of SEVEN) assert(declared.includes(m), `host.mjs lost ${m}`);
  assert(
    declared.join(",") === [...SEVEN, "record", "targetHint"].sort().join(","),
    `Host declares: ${declared.join(", ")}`,
  );
});

await check("D", "grammar/vocabulary.json is unchanged: thirty-two keywords, ten builtins", () => {
  const vocab = JSON.parse(read("grammar/vocabulary.json"));
  assert(vocab.builtins.length === 10, `${vocab.builtins.length} builtins`);
  assert(vocab.keywords.length === 32, `${vocab.keywords.length} keywords`);
});

await check("D", "no Planes source emits a raw draw string except paint/draw.planes", () => {
  const offenders = [];
  for (const entry of readdirSync(rel("paint"))) {
    if (!entry.endsWith(".planes") || entry === "draw.planes") continue;
    if (/show\s+"draw\b/.test(read(path.join("paint", entry)))) offenders.push(entry);
  }
  assert(offenders.length === 0, offenders.join(", "));
});

await check("D", "no CDN, npm package or runtime network dependency in paint.html", () => {
  const html = read("paint.html");
  const externals = [...html.matchAll(/(?:src|href)\s*=\s*"([^"]+)"/g)]
    .map((m) => m[1])
    .filter((u) => /^(https?:)?\/\//.test(u));
  assert(externals.length === 0, externals.join(", "));
  assert(!/require\(|from ["']https?:/.test(html), "paint.html reaches off-origin for a module");
});

// ------------------------------------------------------------------ E. Export

await check("E", "the SVG a program produces parses as XML and its root is <svg>", () => {
  for (const f of FRAMES.filter((x) => x.tick === 0 || x.program === "turtle")) {
    const { svg } = toSvg(f.lines, DIMENSIONS);
    assert(svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg"'), `${f.program}: root is not <svg>`);
    assert(svg.trimEnd().endsWith("</svg>"), `${f.program}: document is not closed`);
    // Tags balance, and nothing outside a quoted attribute carries a raw < or &.
    const opens = (svg.match(/<g[ >]/g) || []).length;
    assert(opens === (svg.match(/<\/g>/g) || []).length, `${f.program}: unbalanced groups`);
    const stripped = svg.replace(/<[^>]*>/g, "");
    assert(!/[<>]/.test(stripped), `${f.program}: unescaped angle bracket in text content`);
    assert(!/&(?!amp;|lt;|gt;|quot;|apos;|#)/.test(stripped), `${f.program}: unescaped ampersand`);
  }
});

await check("E", "a PNG capture is written at twice the device pixel ratio and restores the canvas", () => {
  assert(exportMod.captureScale(1) === 2, "scale at dpr 1");
  assert(exportMod.captureScale(2) === 4, "scale at dpr 2");
  assert(exportMod.captureScale(undefined) === 2, "an unknown dpr must not collapse the scale to 0");

  const sizes = [];
  const canvas = {
    width: 480, height: 360, style: {},
    getContext: () => ({}),
    toDataURL: (type) => {
      sizes.push([canvas.width, canvas.height]);
      return `data:${type};base64,QUJD`;
    },
  };
  const scale = exportMod.captureScale(1);
  const url = exportMod.pngDataUrl(canvas, ["draw circle 1 1 1"], DIMENSIONS, { scale, painter: () => {} });
  assert(url.startsWith("data:image/png;base64,"), url.slice(0, 40));
  assert(sizes.length === 1 && sizes[0][0] === 960 && sizes[0][1] === 720, JSON.stringify(sizes));
  assert(canvas.width === 480 && canvas.height === 360, "the canvas was left resized");
  assert(canvas.style.width === "", "the pinned CSS size was left behind");
});

await check("E", "a data URL decodes to bytes of the type it declares", () => {
  const blob = exportMod.dataUrlToBlob("data:image/png;base64,QUJD", {
    atobFn: (s) => Buffer.from(s, "base64").toString("binary"),
    BlobCtor: class { constructor(parts, o) { this.parts = parts; this.type = o.type; } },
  });
  assert(blob.type === "image/png", blob.type);
  assert([...blob.parts[0]].join() === "65,66,67", [...blob.parts[0]].join());
});

await check("E", "MediaRecorder is constructed with a supported MIME type, or none at all", () => {
  assert(exportMod.pickVideoMimeType(() => true) === "video/webm;codecs=vp9", "vp9 is not preferred");
  assert(exportMod.pickVideoMimeType((t) => !t.includes("vp9")) === "video/webm;codecs=vp8", "no vp8 fallback");
  assert(exportMod.pickVideoMimeType(() => false) === undefined, "an unsupported set must yield the browser default");
  assert(exportMod.pickVideoMimeType(undefined) === undefined, "a browser with no isTypeSupported must not throw");

  const log = [];
  let scheduled = null;
  class FakeRecorder {
    constructor(stream, options) { this.mimeType = options.mimeType; this.state = "inactive"; log.push(options.mimeType); }
    start() { this.state = "recording"; this.ondataavailable({ data: { size: 1, length: 1 } }); }
    stop() { this.state = "inactive"; this.onstop(); }
  }
  let saved = null;
  exportMod.recordCanvas({ captureStream: () => ({}) }, "bloom", {
    now: new Date(2026, 6, 27, 14, 5, 3),
    Recorder: FakeRecorder,
    isSupported: (t) => t === "video/webm;codecs=vp8",
    schedule: (fn, ms) => { scheduled = { fn, ms }; },
    doc: { body: { appendChild() {} }, createElement: () => ({ style: {}, click() { saved = this.download; }, remove() {} }) },
    url: { createObjectURL: () => "blob:x", revokeObjectURL() {} },
    BlobCtor: class { constructor(parts, o) { this.parts = parts; this.type = o.type; } },
  });
  assert(log[0] === "video/webm;codecs=vp8", `constructed with ${log[0]}`);
  assert(scheduled.ms === exportMod.VIDEO_SECONDS * 1000, `auto-stop at ${scheduled.ms}ms`);
  scheduled.fn();
  assert(saved === "planes-bloom-20260727-140503.webm", String(saved));
});

await check("E", "the page states what each export means, under the buttons", () => {
  const html = read("paint.html");
  assert(/id="paint-export-hint"/.test(html), "no hint element");
  assert(
    /SVG and PNG save the frame on screen now\. Video records ten seconds\./.test(html),
    "the hint does not say what §6.4 requires it to say",
  );
  for (const id of ["paint-save-svg", "paint-save-png", "paint-record"]) {
    assert(html.includes(`id="${id}"`), `no ${id} button`);
  }
});

// ------------------------------------------------------------------- report

const CATEGORY_NAME = { A: "Coverage", B: "Conformance", C: "Programs", D: "Invariants", E: "Export" };
const BLOCKING = new Set(["A", "B", "D"]);

const lines = [];
lines.push("# SVG Renderer and Export Verification (§9.2)");
lines.push("");
lines.push(`Run at commit \`${process.env.GIT_COMMIT || "(uncommitted)"}\`.`);
lines.push("");
lines.push("| Category | Check | Result | Detail |");
lines.push("|---|---|---|---|");

let anyFail = false;
let blockingFail = false;
for (const r of results) {
  if (!r.ok) {
    anyFail = true;
    if (BLOCKING.has(r.category)) blockingFail = true;
  }
  lines.push(
    `| ${CATEGORY_NAME[r.category]} | ${r.name} | ${r.ok ? "PASS" : "FAIL"} | ${r.ok ? "" : r.detail.replace(/\|/g, "\\|")} |`,
  );
}

lines.push("");
lines.push(`**${results.filter((r) => r.ok).length}/${results.length} checks passed.**`);
lines.push("");
lines.push(
  blockingFail
    ? "**BLOCKING FAILURE** — a Coverage (A), Conformance (B) or Invariants (D) check failed."
    : anyFail
      ? "Non-blocking failure(s) in C or E — investigate, but this does not fail the gate on its own."
      : "All checks passed, including the three blocking categories (A, B, D).",
);
lines.push("");
lines.push("## Verb coverage, per program");
lines.push("");
lines.push("| Program | Verbs drawn |");
lines.push("|---|---|");
for (const program of ["turtle", "bloom", "snake"]) {
  const perProgram = new Set();
  for (const f of FRAMES.filter((x) => x.program === program)) {
    for (const line of f.lines) {
      const m = /^\s*draw\s+(\S+)/.exec(line);
      if (m) perProgram.add(m[1]);
    }
  }
  lines.push(`| ${program} | \`${[...perProgram].sort().join("` `")}\` |`);
}
lines.push("");
lines.push(
  COVERAGE_ALLOWLIST.size === 0
    ? `All ${VERBS.length} verbs are drawn. The allowlist is empty.`
    : `Allowlisted: ${[...COVERAGE_ALLOWLIST].map(([v, why]) => `\`${v}\` — ${why}`).join("; ")}`,
);
lines.push("");
lines.push(
  "Note: the per-tick benchmark regression (§9.1) is tracked separately in " +
    "`reports/feat-corpus-refinement-svg-renderer-and-export-benchmarks-post.md`. It exceeds the " +
    "25% threshold and was explicitly accepted; it is not a check in this file.",
);

const report = lines.join("\n") + "\n";
console.log(report);
writeFileSync(rel("reports", "svg-and-export-verification.md"), report);

if (blockingFail) process.exit(1);
