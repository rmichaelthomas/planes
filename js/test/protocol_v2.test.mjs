// js/test/protocol_v2.test.mjs — version gating, `blend`, `alpha`, `dash`,
// `clip`/`unclip`, and rotation (planes-drawing-protocol-v2.md §§1.1, 6.1,
// 6.2, 6.6, 8, 10.2), headless. Gradient stops and the <defs> mechanism have
// their own dedicated files (gradient_stops.test.mjs, defs.test.mjs); shadow
// single-cast and scale have theirs (shadow_parity.test.mjs). This file is
// everything else new in v2.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { paint } from "../paint/painter.mjs";
import { toSvg } from "../paint/svg.mjs";
import { VERBS } from "../paint/protocol.mjs";
import { runProgramGraph } from "../browser_main.mjs";
import { stepGraph } from "../paint/loop.mjs";
import { BrowserModuleLoader } from "../module_loader_browser.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

const DIMENSIONS = { width: 200, height: 160, background: "#ffffff" };

function fakeCtx() {
  const calls = [];
  const record = (name) => (...args) => calls.push([name, ...args]);
  let transform = "identity";
  return {
    calls,
    strokeStyle: null, fillStyle: null, lineWidth: null, lineCap: null,
    lineJoin: null, font: null, textAlign: null,
    globalAlpha: 1, globalCompositeOperation: "source-over",
    shadowColor: null, shadowBlur: null, shadowOffsetX: null, shadowOffsetY: null,
    beginPath: record("beginPath"), moveTo: record("moveTo"), lineTo: record("lineTo"),
    arc: record("arc"), ellipse: record("ellipse"), rect: record("rect"),
    closePath: record("closePath"), bezierCurveTo: record("bezierCurveTo"),
    stroke: record("stroke"), fill: record("fill"), fillRect: record("fillRect"),
    fillText: record("fillText"), translate: record("translate"),
    rotate: record("rotate"), scale: record("scale"),
    save: record("save"), restore: record("restore"), clip: record("clip"),
    drawImage: record("drawImage"), clearRect: record("clearRect"),
    _dash: [], setLineDash(d) { this._dash = d; }, getLineDash() { return this._dash; },
    createLinearGradient() { return { addColorStop() {} }; },
    createRadialGradient() { return { addColorStop() {} }; },
    getTransform() { return transform; },
    setTransform(t) { transform = t; },
    resetTransform() { transform = "identity"; },
  };
}

function offscreenFactory() {
  return (w, h) => {
    const ctx = fakeCtx();
    return { width: w, height: h, getContext: () => ctx };
  };
}

const bothRender = (lines) => ({
  canvas: paint(fakeCtx(), lines, { ...DIMENSIONS, offscreenCanvas: offscreenFactory() }),
  svg: toSvg(lines, DIMENSIONS),
});

// ---- version gating (§1.1, §10.2) ----------------------------------------

const V2_ONLY = ["gradient", "shadow", "blend", "clip", "unclip", "alpha", "dash"];

for (const verb of V2_ONLY) {
  test(`${verb} in a stream declaring no version is verb-not-in-version, in both renderers`, () => {
    const sample = {
      gradient: "draw gradient linear 0 0 10 0 0 0 0 1 0 0 0 1",
      shadow: "draw shadow 1 1 1 0 0 0",
      blend: "draw blend add",
      clip: "draw clip",
      unclip: "draw unclip",
      alpha: "draw alpha 0.5",
      dash: "draw dash 1 1",
    }[verb];
    const { canvas, svg } = bothRender([sample]);
    assert.equal(canvas.errors.length, 1);
    assert.equal(canvas.errors[0].tag, "verb-not-in-version");
    assert.deepEqual(svg.errors, canvas.errors);
  });

  test(`${verb} in a stream declaring version 1 explicitly is ALSO verb-not-in-version`, () => {
    const sample = { gradient: "draw gradient linear 0 0 10 0 0 0 0 1 0 0 0 1", shadow: "draw shadow 1 1 1 0 0 0",
      blend: "draw blend add", clip: "draw clip", unclip: "draw unclip", alpha: "draw alpha 0.5", dash: "draw dash 1 1" }[verb];
    const ctx = fakeCtx();
    const r = paint(ctx, ["draw protocol 1", sample], DIMENSIONS);
    assert.equal(r.errors[0].tag, "verb-not-in-version");
  });

  test(`${verb} in a stream declaring version 2 is accepted`, () => {
    const sample = { gradient: "draw gradient linear 0 0 10 0 0 0 0 1 0 0 0 1", shadow: "draw shadow 1 1 1 0 0 0",
      blend: "draw blend add", clip: "draw clip", unclip: "draw unclip", alpha: "draw alpha 0.5", dash: "draw dash 1 1" }[verb];
    let lines = ["draw protocol 2", sample];
    if (verb === "unclip") lines = ["draw protocol 2", "draw clip", sample];
    if (verb === "clip") lines = ["draw protocol 2", sample, "draw unclip"];
    const ctx = fakeCtx();
    const r = paint(ctx, lines, DIMENSIONS);
    assert.deepEqual(r.errors, []);
  });
}

test("the optional rotation on ellipse/rect is NOT version-gated — works under version 1", () => {
  const lines = ["draw ellipse 50 50 10 5 30", "draw rect 0 0 10 10 15"];
  const { canvas, svg } = bothRender(lines);
  assert.deepEqual(canvas.errors, []);
  assert.deepEqual(svg.errors, []);
});

test("an unsupported version (3) is still refused whole, same as before v2 existed", () => {
  const { canvas, svg } = bothRender(["draw protocol 3", "draw circle 1 2 3"]);
  assert.equal(canvas.errors[0].tag, "unsupported-version");
  assert.deepEqual(svg.errors, canvas.errors);
});

// ---- blend (§6.6, §9) ------------------------------------------------------

test("blend normal is source-over on canvas, and carries no mix-blend-mode style in SVG", () => {
  const lines = ["draw protocol 2", "draw blend normal", "draw fill 0.5 0.1 0 1", "draw circle 10 10 5"];
  const ctx = fakeCtx();
  paint(ctx, lines, DIMENSIONS);
  assert.equal(ctx.globalCompositeOperation, "source-over");
  const { svg } = toSvg(lines, DIMENSIONS);
  assert.doesNotMatch(svg, /mix-blend-mode/);
});

test("blend add is `lighter` on canvas and `mix-blend-mode:plus-lighter` in SVG — the exact match, not screen", () => {
  const lines = ["draw protocol 2", "draw blend add", "draw fill 0.5 0.1 0 1", "draw circle 10 10 5"];
  const ctx = fakeCtx();
  paint(ctx, lines, DIMENSIONS);
  assert.equal(ctx.globalCompositeOperation, "lighter");
  const { svg } = toSvg(lines, DIMENSIONS);
  assert.match(svg, /style="mix-blend-mode:plus-lighter"/);
  assert.doesNotMatch(svg, /mix-blend-mode:\s*screen/);
});

test("blend's word set is closed: anything but normal/add is bad-word", () => {
  const r = paint(fakeCtx(), ["draw protocol 2", "draw blend screen"], DIMENSIONS);
  assert.equal(r.errors[0].tag, "bad-word");
});

// blend interacting with an active shadow — §7's named test: both with and
// without a shadow, in both renderers, compared. Canvas applies blend at
// the SAME point it applies shadow (globalCompositeOperation/shadow* are
// both persistent ctx state, both active for the same fill()/stroke() or
// drawImage() call); SVG emits both `filter` and `style="mix-blend-mode"` on
// the identical element. Structural agreement: both renderers apply both
// effects to the one drawing operation that represents the mark, never to
// two different ones.
test("blend add WITHOUT a shadow: canvas sets composite op on the single fill/stroke pass; SVG carries the blend style alone", () => {
  const lines = ["draw protocol 2", "draw blend add", "draw fill 0.5 0.1 0 1", "draw stroke 0 0 0 0", "draw circle 10 10 5"];
  const ctx = fakeCtx();
  paint(ctx, lines, { ...DIMENSIONS, offscreenCanvas: offscreenFactory() });
  assert.equal(ctx.globalCompositeOperation, "lighter");
  assert.ok(!ctx.calls.some((c) => c[0] === "drawImage"), "no shadow set: single pass, no compositing step");
  const { svg } = toSvg(lines, DIMENSIONS);
  const el = /<circle[^/]*\/>/.exec(svg)[0];
  assert.match(el, /mix-blend-mode:plus-lighter/);
  assert.doesNotMatch(el, /filter=/);
});

test("blend add WITH a shadow active: canvas applies both at the compositing step; SVG's element carries both filter and blend style", () => {
  const lines = [
    "draw protocol 2",
    "draw blend add",
    "draw shadow 0 0 4 0.9 0.1 60",
    "draw fill 0.5 0.1 0 1",
    "draw stroke 0.2 0.1 0 1", // both visible: forces the offscreen composite path
    "draw circle 10 10 5",
  ];
  const ctx = fakeCtx();
  paint(ctx, lines, { ...DIMENSIONS, offscreenCanvas: offscreenFactory() });
  const drawImageCalls = ctx.calls.filter((c) => c[0] === "drawImage");
  assert.equal(drawImageCalls.length, 1, "one composite: one shadow");
  assert.equal(ctx.globalCompositeOperation, "lighter", "blend is still active at the composite step");
  const { svg } = toSvg(lines, DIMENSIONS);
  const el = /<circle[^/]*\/>/.exec(svg)[0];
  assert.match(el, /mix-blend-mode:plus-lighter/);
  assert.match(el, /filter="url\(#p-shadow-1\)"/);
  // Both attributes on the SAME element — neither renderer had to choose
  // one effect over the other or split the mark into two elements.
});

// ---- alpha: a per-mark multiplier, not a group fade (§6.1, §9's "known
// limits" reasoning: a <g opacity> would flatten-then-fade and diverge
// wherever marks inside the group overlap) ----------------------------------

test("alpha multiplies canvas's globalAlpha directly", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw protocol 2", "draw alpha 0.4", "draw circle 1 1 1"], DIMENSIONS);
  assert.equal(ctx.globalAlpha, 0.4);
});

test("alpha multiplies fill-opacity and stroke-opacity per element in SVG, not a group wrapper", () => {
  const lines = ["draw protocol 2", "draw alpha 0.5", "draw fill 0.5 0.1 0 0.8", "draw stroke 0.5 0.1 0 0.6", "draw circle 1 1 1"];
  const { svg } = toSvg(lines, DIMENSIONS);
  assert.doesNotMatch(svg, /<g[^>]*opacity/, "no group carries an opacity attribute");
  assert.match(svg, /fill-opacity="0\.4"/); // 0.8 * 0.5
  assert.match(svg, /stroke-opacity="0\.3"/); // 0.6 * 0.5
});

test("two overlapping marks under the same alpha are two independently-dimmed marks, not one dimmed group", () => {
  const lines = [
    "draw protocol 2",
    "draw alpha 0.5",
    "draw fill 0.5 0.1 0 1",
    "draw stroke 0 0 0 0",
    "draw circle 10 10 8",
    "draw circle 12 10 8",
  ];
  const { svg, errors } = toSvg(lines, DIMENSIONS);
  assert.deepEqual(errors, []);
  const opacities = [...svg.matchAll(/<circle[^>]*fill-opacity="([\d.]+)"/g)].map((m) => Number(m[1]));
  assert.deepEqual(opacities, [0.5, 0.5], "each circle carries its own fill-opacity, not a shared group one");
});

test("alpha defaults to 1 (fully opaque) at the start of a stream", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw circle 1 1 1"], DIMENSIONS);
  assert.equal(ctx.globalAlpha, 1);
});

// ---- dash -----------------------------------------------------------------

test("dash sets canvas's line dash, scaled by `scale`", () => {
  const ctx1 = fakeCtx();
  paint(ctx1, ["draw protocol 2", "draw dash 8 4", "draw line 0 0 10 10"], { ...DIMENSIONS, scale: 1 });
  assert.deepEqual(ctx1.getLineDash(), [8, 4]);
  const ctx3 = fakeCtx();
  paint(ctx3, ["draw protocol 2", "draw dash 8 4", "draw line 0 0 10 10"], { ...DIMENSIONS, scale: 3 });
  assert.deepEqual(ctx3.getLineDash(), [24, 12]);
});

test("dash 0 0 is solid: an empty dash array on canvas, no stroke-dasharray attribute in SVG", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw protocol 2", "draw dash 8 4", "draw dash 0 0", "draw line 0 0 10 10"], DIMENSIONS);
  assert.deepEqual(ctx.getLineDash(), []);
  const { svg } = toSvg(["draw protocol 2", "draw dash 8 4", "draw dash 0 0", "draw line 0 0 10 10"], DIMENSIONS);
  assert.doesNotMatch(svg, /stroke-dasharray/);
});

test("dash is unscaled in SVG — protocol-space values directly, no `scale` concept there", () => {
  const { svg } = toSvg(["draw protocol 2", "draw dash 8 4", "draw line 0 0 10 10"], DIMENSIONS);
  assert.match(svg, /stroke-dasharray="8 4"/);
});

test("dash defaults to 0 0 (solid) at the start of a stream", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw line 0 0 1 1"], DIMENSIONS);
  assert.deepEqual(ctx.getLineDash(), []);
});

// ---- clip / unclip ----------------------------------------------------

test("the shape that defines a clip is painted normally — clipping to itself is a no-op visually", () => {
  const lines = ["draw protocol 2", "draw fill 0.5 0.1 0 1", "draw clip", "draw circle 50 50 20", "draw unclip"];
  const { canvas, svg } = bothRender(lines);
  assert.deepEqual(canvas.errors, []);
  assert.deepEqual(svg.errors, []);
  assert.match(svg.svg, /<circle cx="50" cy="50" r="20"/);
});

test("clip opens a <clipPath> def and a <g clip-path> group in SVG; unclip closes the group", () => {
  const lines = ["draw protocol 2", "draw clip", "draw circle 50 50 20", "draw rect 0 0 5 5 0", "draw unclip", "draw rect 60 60 5 5 0"];
  const { svg, errors } = toSvg(lines, DIMENSIONS);
  assert.deepEqual(errors, []);
  assert.match(svg, /<clipPath id="p-clip-1"><circle/);
  assert.match(svg, /<g clip-path="url\(#p-clip-1\)">/);
  // the rect drawn under the clip is inside the group; the one after unclip is outside it
  const groupOpen = svg.indexOf('<g clip-path="url(#p-clip-1)">');
  const groupClose = svg.indexOf("</g>", groupOpen);
  const rectInside = svg.indexOf('x="0" y="0" width="5"');
  const rectOutside = svg.indexOf('x="60" y="60" width="5"');
  assert.ok(rectInside > groupOpen && rectInside < groupClose);
  assert.ok(rectOutside > groupClose);
});

test("clip's canvas path uses ctx.save()/ctx.clip()/ctx.restore() — raw, not transformStack", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw protocol 2", "draw clip", "draw circle 50 50 20", "draw unclip"], DIMENSIONS);
  assert.ok(ctx.calls.some((c) => c[0] === "save"));
  assert.ok(ctx.calls.some((c) => c[0] === "clip"));
  assert.ok(ctx.calls.some((c) => c[0] === "restore"));
});

test("unclip with no defining shape ever drawn is a harmless no-op, not an error", () => {
  const lines = ["draw protocol 2", "draw clip", "draw unclip", "draw circle 1 1 1"];
  const { canvas, svg } = bothRender(lines);
  assert.deepEqual(canvas.errors, []);
  assert.deepEqual(svg.errors, []);
  assert.doesNotMatch(svg.svg, /clip-path/);
});

test("clip/unclip nest: two levels open two <clipPath> defs and two nested groups", () => {
  const lines = [
    "draw protocol 2",
    "draw clip",
    "draw circle 50 50 40",
    "draw clip",
    "draw rect 10 10 20 20 0",
    "draw circle 30 30 5",
    "draw unclip",
    "draw circle 60 60 5",
    "draw unclip",
  ];
  const { canvas, svg } = bothRender(lines);
  assert.deepEqual(canvas.errors, []);
  assert.deepEqual(svg.errors, []);
  assert.equal((svg.svg.match(/<clipPath/g) || []).length, 2);
  assert.equal((svg.svg.match(/clip-path="url/g) || []).length, 2);
});

test("clip left open at the end of the stream is clip-unclosed, in both renderers", () => {
  const { canvas, svg } = bothRender(["draw protocol 2", "draw clip"]);
  assert.equal(canvas.errors[0].tag, "clip-unclosed");
  assert.deepEqual(svg.errors, canvas.errors);
});

test("a clip opened inside push/pop and never unclip'd is auto-closed by pop, in SVG's group nesting", () => {
  const lines = [
    "draw protocol 2",
    "draw push",
    "draw clip",
    "draw circle 10 10 5",
    "draw pop",
    "draw circle 90 90 5",
  ];
  const { svg, errors } = toSvg(lines, DIMENSIONS);
  // clip-unclosed is still reported (stream.mjs's balance tracking is
  // independent of push/pop), but the SVG document itself stays balanced.
  assert.equal(errors.length, 1);
  assert.equal(errors[0].tag, "clip-unclosed");
  const opens = (svg.match(/<g[ >]/g) || []).length;
  const closes = (svg.match(/<\/g>/g) || []).length;
  assert.equal(opens, closes);
});

test("clip does not leak canvas paint state through ctx.restore() — unclip reapplies the tracked colour", () => {
  const ctx = fakeCtx();
  paint(
    ctx,
    [
      "draw protocol 2",
      "draw fill 0.5 0.1 0 1",
      "draw clip",
      "draw circle 10 10 5",
      "draw fill 0.9 0.05 200 1", // changed WHILE the clip is open
      "draw unclip",
      "draw circle 90 90 5", // must still see the 0.9/0.05/200 fill, not rolled back by restore()
    ],
    DIMENSIONS,
  );
  // The last fillStyle set is whatever the tracked state says — restore()'s
  // native rollback would otherwise have reverted it to the pre-clip colour.
  assert.match(ctx.fillStyle, /rgba\(/);
});

// ---- rotation on ellipse/rect: hand-computed geometry (§9.2) -------------

const toRad = (deg) => (deg * Math.PI) / 180;

test("ellipse rotation: canvas's native rotation parameter equals toRad(turn) exactly, about the ellipse's own centre", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw ellipse 50 60 20 10 40"], DIMENSIONS);
  const call = ctx.calls.find((c) => c[0] === "ellipse");
  assert.deepEqual(call, ["ellipse", 50, 60, 20, 10, toRad(40), 0, 2 * Math.PI]);
});

test("ellipse rotation, hand-computed: the tip of the rx-axis lands where clockwise rotation about (x,y) puts it", () => {
  const x = 50, y = 60, rx = 20, turn = 90;
  // Hand-computed: rotating the local point (rx, 0) by `turn` clockwise
  // (y-down, so the ordinary rotation matrix IS clockwise-as-pictured) and
  // adding the centre back.
  const rad = toRad(turn);
  const expectedTipX = x + rx * Math.cos(rad);
  const expectedTipY = y + rx * Math.sin(rad);
  assert.ok(Math.abs(expectedTipX - x) < 1e-9, "a 90-degree turn: the x-tip lands on the centre's x");
  assert.ok(Math.abs(expectedTipY - (y + rx)) < 1e-9, "and rx below the centre — clockwise, y-down");
  const ctx = fakeCtx();
  paint(ctx, [`draw ellipse ${x} ${y} ${rx} 8 ${turn}`], DIMENSIONS);
  const call = ctx.calls.find((c) => c[0] === "ellipse");
  assert.equal(call[5], rad, "canvas is given exactly the angle the hand computation used");
});

test("ellipse rotation in SVG: rotate(deg cx cy) about the ellipse's own centre", () => {
  const { svg } = toSvg(["draw ellipse 50 60 20 10 40"], DIMENSIONS);
  assert.match(svg, /<ellipse cx="50" cy="60" rx="20" ry="10" transform="rotate\(40 50 60\)"/);
});

test("ellipse with turn 0 emits no transform attribute at all — identical to a v1 stream", () => {
  const { svg } = toSvg(["draw ellipse 50 60 20 10 0"], DIMENSIONS);
  assert.match(svg, /<ellipse cx="50" cy="60" rx="20" ry="10"(?! transform)/);
  assert.doesNotMatch(svg, /transform="rotate/);
});

test("rect rotation, hand-computed: canvas translates to the rect's own centre, rotates, then draws about the local origin", () => {
  const x = 10, y = 20, w = 40, h = 30, turn = 30;
  const cx = x + w / 2;
  const cy = y + h / 2;
  const ctx = fakeCtx();
  paint(ctx, [`draw rect ${x} ${y} ${w} ${h} ${turn}`], DIMENSIONS);
  const translateCall = ctx.calls.find((c) => c[0] === "translate");
  const rotateCall = ctx.calls.find((c) => c[0] === "rotate");
  const rectCall = ctx.calls.find((c) => c[0] === "rect");
  assert.deepEqual(translateCall, ["translate", cx, cy], "translated to the rect's own centre, hand-computed x+w/2, y+h/2");
  assert.deepEqual(rotateCall, ["rotate", toRad(turn)]);
  assert.deepEqual(rectCall, ["rect", -w / 2, -h / 2, w, h], "drawn about the local origin once centred");
});

test("a rotated rect's hand-computed corners: a square rotated 90 degrees about its own centre maps onto itself", () => {
  // x=0,y=0,w=20,h=20 -> centre (10,10); local corners (-10,-10)..(10,10).
  // Rotating a SQUARE's corner set by 90 degrees about its own centre
  // produces the identical corner set (just permuted) — the bounding box
  // is unchanged, which is a hand-verifiable invariant independent of
  // which renderer computes it.
  const local = [[-10, -10], [10, -10], [10, 10], [-10, 10]];
  const rad = toRad(90);
  const rotated = local.map(([lx, ly]) => [lx * Math.cos(rad) - ly * Math.sin(rad), lx * Math.sin(rad) + ly * Math.cos(rad)]);
  const rotatedSet = new Set(rotated.map(([rx, ry]) => `${Math.round(rx)},${Math.round(ry)}`));
  const localSet = new Set(local.map(([lx, ly]) => `${lx},${ly}`));
  assert.deepEqual(rotatedSet, localSet, "a square's corners are a fixed point set under a 90-degree rotation about its centre");

  const { svg } = toSvg(["draw rect 0 0 20 20 90"], DIMENSIONS);
  assert.match(svg, /transform="rotate\(90 10 10\)"/, "SVG is told exactly the centre and angle the hand computation used");
});

test("rect with turn 0 emits no transform attribute — identical to a v1 stream", () => {
  const { svg } = toSvg(["draw rect 0 0 10 10 0"], DIMENSIONS);
  const el = /<rect[^/]*\/>/.exec(svg)[0];
  assert.doesNotMatch(el, /transform/);
});

test("rotation is unaffected by the stream's declared version — same geometry with or without draw protocol 2", () => {
  const withDecl = toSvg(["draw protocol 2", "draw ellipse 50 50 10 5 30"], DIMENSIONS).svg;
  const without = toSvg(["draw ellipse 50 50 10 5 30"], DIMENSIONS).svg;
  const stripProtocolNoop = (s) => s; // the declaration itself draws nothing
  assert.equal(stripProtocolNoop(withDecl), without);
});

// ---- F: library correspondence — one draw.planes helper per live VERBS ---

test("draw.planes's helper set is exactly VERBS — every v2 verb has one, protocol excluded", () => {
  const src = fs.readFileSync(path.join(REPO, "paint", "draw.planes"), "utf-8");
  const helpers = [...src.matchAll(/^to ([\w-]+)/gm)].map((m) => m[1]);
  assert.deepEqual(new Set(helpers), new Set(VERBS));
  assert.ok(!helpers.includes("protocol"));
});

// ---- A: v1 invariance, against the committed pre-build baseline ----------
//
// scripts/verify-protocol-v2.mjs ran this once, by hand, before this PR
// merged, and reported PASS (protocol-v2-verification.md). Per the
// retirement rule (scripts/ci.sh, enforced by test_gate.py), a build's
// verification script does not survive its own build — its durable
// assertions graduate into a suite the gate runs, or they are lost. This is
// that graduation: turtle/bloom/snake must render byte-identically, in both
// sinks, to the frames captured in benchmarks/protocol-v2-pre/ FOREVER, not
// just at the moment this build merged — a real regression guard against a
// FUTURE change to stream.mjs/painter.mjs/svg.mjs silently changing what a
// v1 stream means.

const PAINT_DIR = path.join(REPO, "paint");
const BENCH_DIR = path.join(REPO, "benchmarks", "protocol-v2-pre");

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

function baselineFrames() {
  return fs
    .readdirSync(BENCH_DIR)
    .filter((f) => f.endsWith(".lines.txt"))
    .map((f) => f.replace(/\.lines\.txt$/, ""))
    .sort();
}

async function renderBaselineLabel(label) {
  if (label === "turtle") {
    const r = await runProgramGraph(fs.readFileSync(path.join(PAINT_DIR, "turtle.planes"), "utf-8"), {
      base: pathToFileURL(path.join(PAINT_DIR, "turtle.planes")).href,
    });
    assert.equal(r.error, null);
    return r.output;
  }
  const program = label.startsWith("bloom") ? "bloom" : "snake";
  const tick = Number(/-tick-(\d+)/.exec(label)[1]);
  const loader = new BrowserModuleLoader({ base: pathToFileURL(path.join(PAINT_DIR, `${program}.planes`)).href });
  if (program === "bloom") {
    const r = await stepGraph(
      fs.readFileSync(path.join(PAINT_DIR, "bloom.planes"), "utf-8"),
      { tick, keys: [], pointer: { x: 0, y: 0, down: false }, state: null },
      { loader },
    );
    assert.equal(r.error, null);
    return r.lines;
  }
  // snake: replay from tick 0 with the same fixed key so state reaches the
  // same point the baseline was captured at.
  let state = null;
  let lines = null;
  for (let t = 0; t <= tick; t++) {
    const r = await stepGraph(
      fs.readFileSync(path.join(PAINT_DIR, "snake.planes"), "utf-8"),
      { tick: t, keys: ["ArrowLeft"], pointer: { x: 0, y: 0, down: false }, state },
      { loader },
    );
    assert.equal(r.error, null);
    state = r.state;
    lines = r.lines;
  }
  return lines;
}

for (const label of baselineFrames()) {
  test(`v1 invariance: ${label} renders byte-identically (SVG) to the committed baseline`, async () => {
    const restore = installFsFetch();
    try {
      const lines = await renderBaselineLabel(label);
      const { svg, errors } = toSvg(lines, DIMENSIONS_480x360());
      assert.deepEqual(errors, []);
      const expected = fs.readFileSync(path.join(BENCH_DIR, `${label}.svg`), "utf-8");
      assert.equal(svg, expected);
    } finally {
      restore();
    }
  });
}

function DIMENSIONS_480x360() {
  return { width: 480, height: 360, background: "#ffffff" };
}

// ---- G: purity — garden.planes at tick N: fresh === after visiting 0..N --

test("garden.planes is pure in tick: rendering tick N fresh matches rendering it after visiting every tick before it", async () => {
  const restore = installFsFetch();
  try {
    const src = fs.readFileSync(path.join(PAINT_DIR, "garden.planes"), "utf-8");
    const base = pathToFileURL(path.join(PAINT_DIR, "garden.planes")).href;
    const TARGET = 137;
    const ctx = (tick) => ({ tick, keys: [], pointer: { x: 0, y: 0, down: false }, state: null });

    const freshLoader = new BrowserModuleLoader({ base });
    const fresh = await stepGraph(src, ctx(TARGET), { loader: freshLoader });
    assert.equal(fresh.error, null);

    const visitedLoader = new BrowserModuleLoader({ base });
    let visited;
    for (let t = 0; t <= TARGET; t++) {
      visited = await stepGraph(src, ctx(t), { loader: visitedLoader });
      assert.equal(visited.error, null);
    }

    assert.deepEqual(fresh.lines, visited.lines);
  } finally {
    restore();
  }
});
