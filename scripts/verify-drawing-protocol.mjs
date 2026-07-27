#!/usr/bin/env node
// scripts/verify-drawing-protocol.mjs — the feat/module-loader-and-drawing-
// protocol-v1 gate (§12.2).
//
// Five categories, A through E. Blocking: any failure in D (invariants), any
// failure in A (protocol) or C (modules) — those are the invariants and the
// contract this build exists to hold. B (painter) and E (programs) are
// reported the same way but do not fail the gate on their own.
//
// Usage: node scripts/verify-drawing-protocol.mjs
// Writes: reports/drawing-protocol-verification.md (same table as stdout)

import { readFileSync, existsSync } from "node:fs";
import * as fs from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import os from "node:os";
import { execSync } from "node:child_process";

const REPO = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const rel = (...p) => path.join(REPO, ...p);
const imp = (p) => import(pathToFileURL(rel(p)).href);

const { loadGrammar } = await imp("js/loader_node.mjs");
loadGrammar();

const { parseCommand, VERBS } = await imp("js/paint/protocol.mjs");
const { paint, oklchToRgb } = await imp("js/paint/painter.mjs");
const { load_graph, check_collisions, ModuleError } = await imp("js/modules.mjs");
const { createNodeModuleLoader } = await imp("js/module_loader_node.mjs");
const { BrowserModuleLoader } = await imp("js/module_loader_browser.mjs");
const { runProgramGraph, analyseProgramGraph } = await imp("js/browser_main.mjs");
const { parse } = await imp("js/parser.mjs");

const vocab = JSON.parse(readFileSync(rel("grammar/vocabulary.json"), "utf8"));

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
    strokeStyle: null, fillStyle: null, lineWidth: null, lineCap: null, lineJoin: null, font: null, textAlign: null,
    beginPath: record("beginPath"), moveTo: record("moveTo"), lineTo: record("lineTo"),
    arc: record("arc"), ellipse: record("ellipse"), rect: record("rect"), closePath: record("closePath"),
    bezierCurveTo: record("bezierCurveTo"), stroke: record("stroke"), fill: record("fill"),
    fillRect: record("fillRect"), fillText: record("fillText"),
    translate: record("translate"), rotate: record("rotate"), scale: record("scale"),
    getTransform() { return transform; },
    setTransform(t) { transform = t; },
    resetTransform() { transform = "identity"; },
  };
}
const DIMENSIONS = { width: 480, height: 360, background: "#ffffff" };

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

// ---------------------------------------------------------------- A. Protocol
// BLOCKING

const SAMPLES = {
  protocol: "draw protocol 1",
  stroke: "draw stroke 0.6 0.15 210 1",
  fill: "draw fill 0.5 0.1 30 0.8",
  width: "draw width 3",
  cap: "draw cap round",
  corner: "draw corner bevel",
  line: "draw line 0 0 10 10",
  rect: "draw rect 0 0 10 10",
  circle: "draw circle 5 5 3",
  ellipse: "draw ellipse 5 5 3 4",
  arc: "draw arc 5 5 3 0 90",
  triangle: "draw triangle 0 0 10 0 5 10",
  shape: "draw shape",
  vertex: "draw vertex 1 1",
  curve: "draw curve 1 1 2 2 3 3",
  close: "draw close",
  end: "draw end",
  push: "draw push",
  pop: "draw pop",
  translate: "draw translate 10 10",
  rotate: "draw rotate 45",
  scale: "draw scale 2 2",
  label: "draw label 8 16 score: 42",
  size: "draw size 20",
  align: "draw align center",
  background: "draw background 0.9 0.05 90",
  clear: "draw clear",
};

await check("A", "every verb (26) plus protocol parses at correct arity", () => {
  for (const verb of [...VERBS, "protocol"]) {
    assert(SAMPLES[verb], `no sample line for verb ${verb}`);
    const cmd = parseCommand(SAMPLES[verb]);
    assert(cmd.kind === "command" && cmd.verb === verb, `${verb} did not parse: ${JSON.stringify(cmd)}`);
  }
});

await check("A", "every verb errors at wrong arity", () => {
  for (const verb of [...VERBS, "protocol"]) {
    // `label` has no fixed arity (2 numbers + the rest of the line as text),
    // so dropping its last token can still leave valid trailing text —
    // "draw label 8 16" (no text at all) is its actual wrong-arity case.
    if (verb === "label") {
      const cmd = parseCommand("draw label 8 16");
      assert(cmd.kind === "error" && cmd.tag === "wrong-arity", `label: expected wrong-arity, got ${JSON.stringify(cmd)}`);
      continue;
    }
    const line = SAMPLES[verb];
    const tokens = line.split(" ");
    const tooFew = tokens.slice(0, -1).join(" ");
    const cmd = parseCommand(tokens.length > 2 ? tooFew : `${line} extra`);
    assert(cmd.kind === "error" && cmd.tag === "wrong-arity", `${verb}: expected wrong-arity, got ${JSON.stringify(cmd)}`);
  }
});

await check("A", "all five error tags fire", () => {
  const cases = {
    "unknown-verb": "draw hexagon 1 2 3",
    "wrong-arity": "draw circle 1 2",
    "bad-number": "draw circle x 1 2",
    "bad-word": "draw cap wrongword",
    "bad-protocol-version": "draw protocol 1.5",
  };
  for (const [tag, line] of Object.entries(cases)) {
    const cmd = parseCommand(line);
    assert(cmd.kind === "error" && cmd.tag === tag, `${line}: expected ${tag}, got ${JSON.stringify(cmd)}`);
  }
});

await check("A", "every zero-arity verb name is prose when unprefixed", () => {
  const zeroArity = VERBS.filter((v) => SAMPLES[v] === `draw ${v}`);
  assert(zeroArity.length >= 6, `expected at least 6 zero-arity verbs, found ${zeroArity.length}`);
  for (const verb of zeroArity) {
    const cmd = parseCommand(verb);
    assert(cmd.kind === "prose" && cmd.text === verb, `bare "${verb}" was not prose: ${JSON.stringify(cmd)}`);
  }
});

await check("A", "a leading ~ is accepted and stripped from a number", () => {
  const cmd = parseCommand("draw circle ~66.666 100 40");
  assert(cmd.kind === "command" && cmd.args[0] === 66.666, JSON.stringify(cmd));
});

await check("A", "label preserves internal spaces and an embedded verb name", () => {
  const cmd = parseCommand("draw label 8 16 press draw circle to continue");
  assert(
    cmd.kind === "command" && cmd.verb === "label" && cmd.text === "press draw circle to continue",
    JSON.stringify(cmd),
  );
});

// ------------------------------------------------------------------ B. Painter

await check("B", "the reset table is applied at the start of every call", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw stroke 0.9 0 0 1", "draw width 9"], DIMENSIONS);
  const result = paint(ctx, [], DIMENSIONS);
  assert(ctx.strokeStyle === "rgba(0, 0, 0, 1)", ctx.strokeStyle);
  assert(ctx.lineWidth === 1, String(ctx.lineWidth));
  assert(result.errors.length === 0);
});

await check("B", "OKLCH matches fixed expected RGB triples, including a clamped case", () => {
  const white = oklchToRgb(1, 0, 0).map((c) => Math.round(c * 255));
  const black = oklchToRgb(0, 0, 0).map((c) => Math.round(c * 255));
  const grey = oklchToRgb(0.5, 0, 0).map((c) => Math.round(c * 255));
  const clamped = oklchToRgb(1, 0.5, 0).map((c) => Math.round(c * 255));
  assert(white.join(",") === "255,255,255", white.join(","));
  assert(black.join(",") === "0,0,0", black.join(","));
  assert(grey.join(",") === "99,99,99", grey.join(","));
  assert(grey[0] === grey[1] && grey[1] === grey[2], "grey must be achromatic");
  assert(clamped.join(",") === "255,0,241", clamped.join(","));
});

await check("B", "arc converts degrees to radians with no flip, and wraps end past start", () => {
  const ctx = fakeCtx();
  paint(ctx, ["draw arc 50 50 20 0 90"], DIMENSIONS);
  const call1 = ctx.calls.find((c) => c[0] === "arc");
  assert(call1[4] === 0 && Math.abs(call1[5] - Math.PI / 2) < 1e-9 && call1[6] === false, JSON.stringify(call1));

  const ctx2 = fakeCtx();
  paint(ctx2, ["draw arc 50 50 20 300 10"], DIMENSIONS);
  const call2 = ctx2.calls.find((c) => c[0] === "arc");
  const expectedEnd = (370 * Math.PI) / 180;
  assert(Math.abs(call2[5] - expectedEnd) < 1e-9, `expected wrapped end ${expectedEnd}, got ${call2[5]}`);
});

await check("B", "all four path-lifecycle errors fire", () => {
  const scenarios = [
    ["draw vertex 1 1"],
    ["draw end"],
    ["draw shape", "draw vertex 0 0", "draw shape", "draw end"],
    ["draw shape", "draw vertex 0 0", "draw vertex 1 1"],
  ];
  const expectedTags = ["path-not-open", "path-not-open", "path-already-open", "path-unclosed"];
  scenarios.forEach((lines, i) => {
    const result = paint(fakeCtx(), lines, DIMENSIONS);
    assert(
      result.errors.some((e) => e.tag === expectedTags[i]),
      `scenario ${i}: expected ${expectedTags[i]}, got ${JSON.stringify(result.errors)}`,
    );
  });
});

await check("B", "both transform-balance errors fire", () => {
  const popResult = paint(fakeCtx(), ["draw pop"], DIMENSIONS);
  assert(popResult.errors.some((e) => e.tag === "unmatched-pop"), JSON.stringify(popResult.errors));
  const pushResult = paint(fakeCtx(), ["draw push"], DIMENSIONS);
  assert(pushResult.errors.some((e) => e.tag === "unmatched-push"), JSON.stringify(pushResult.errors));
});

await check("B", "an unsupported protocol version refuses the whole stream: nothing is drawn", () => {
  const ctx = fakeCtx();
  const result = paint(ctx, ["draw protocol 2", "draw circle 1 1 1"], DIMENSIONS);
  assert(result.drawn === 0 && ctx.calls.length === 0, JSON.stringify(result));
  assert(result.errors.length === 1 && result.errors[0].tag === "unsupported-version", JSON.stringify(result.errors));
});

// ------------------------------------------------------------------- C. Modules
// BLOCKING

function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "planes-verify-drawing-protocol-"));
}
function writeFile(dir, name, text) {
  const p = path.join(dir, name);
  fs.writeFileSync(p, text, "utf8");
  return p;
}

await check("C", "Node and browser loaders produce identical graphs for the same tree", async () => {
  const dir = makeTempDir();
  writeFile(dir, "main.planes", "use a\nto entry-fn of x:\n  give x\n");
  writeFile(dir, "a.planes", "to helper of x:\n  give x + 1\n");
  const nodeLoader = createNodeModuleLoader();
  const nodeGraph = await load_graph(nodeLoader, path.join(dir, "main.planes"));

  const restore = installFsFetch();
  try {
    const base = pathToFileURL(path.join(dir, "main.planes")).href;
    const browserLoader = new BrowserModuleLoader({ base });
    const browserGraph = await load_graph(browserLoader, base);
    assert(nodeGraph.length === browserGraph.length, `${nodeGraph.length} vs ${browserGraph.length}`);
    for (let i = 0; i < nodeGraph.length; i++) {
      assert(nodeGraph[i][1] === browserGraph[i][1], `source text differs at index ${i}`);
      assert(
        nodeLoader.label(nodeGraph[i][0]) === browserLoader.label(browserGraph[i][0]),
        `label differs at index ${i}: ${nodeLoader.label(nodeGraph[i][0])} vs ${browserLoader.label(browserGraph[i][0])}`,
      );
    }
  } finally {
    restore();
  }
});

await check("C", "the three ModuleError messages are byte-identical across loaders", async () => {
  // 1. missing module
  const dir = makeTempDir();
  const mainPath = writeFile(dir, "main.planes", "use nope\n");
  const nodeLoader = createNodeModuleLoader();
  let nodeMsg = null;
  try {
    nodeLoader.locate("nope", mainPath);
  } catch (e) {
    nodeMsg = e.message;
  }
  const restore = installFsFetch();
  let browserMsg = null;
  try {
    const base = pathToFileURL(mainPath).href;
    const browserLoader = new BrowserModuleLoader({ base });
    const loc = browserLoader.locate("nope", null);
    try {
      await browserLoader.read(loc);
    } catch (e) {
      browserMsg = e.message;
    }
  } finally {
    restore();
  }
  assert(nodeMsg !== null && nodeMsg === browserMsg, `missing-module: node=${nodeMsg} browser=${browserMsg}`);

  // 2. cycle
  const cdir = makeTempDir();
  writeFile(cdir, "a.planes", "use b\nto fa of x:\n  give x\n");
  writeFile(cdir, "b.planes", "use a\nto fb of x:\n  give x\n");
  let nodeCycleMsg = null;
  try {
    await load_graph(createNodeModuleLoader(), path.join(cdir, "a.planes"));
  } catch (e) {
    nodeCycleMsg = e.message.replace(/^module cycle: .*/, (m) => m.split(" -> ").map((s) => s.split("/").pop()).join(" -> "));
    nodeCycleMsg = e.message;
  }
  const restore2 = installFsFetch();
  let browserCycleMsg = null;
  try {
    const base = pathToFileURL(path.join(cdir, "a.planes")).href;
    const browserLoader = new BrowserModuleLoader({ base });
    try {
      await load_graph(browserLoader, base);
    } catch (e) {
      browserCycleMsg = e.message;
    }
  } finally {
    restore2();
  }
  assert(nodeCycleMsg && nodeCycleMsg.startsWith("module cycle:"), nodeCycleMsg);
  assert(browserCycleMsg && browserCycleMsg.startsWith("module cycle:"), browserCycleMsg);
  const nodeCycleNames = nodeCycleMsg.split(": ")[1];
  const browserCycleNames = browserCycleMsg.split(": ")[1];
  assert(nodeCycleNames === browserCycleNames, `node="${nodeCycleNames}" browser="${browserCycleNames}"`);

  // 3. collision
  const xdir = makeTempDir();
  writeFile(xdir, "main.planes", "use a\nuse b\n");
  writeFile(xdir, "a.planes", "to shared of x:\n  give x\n");
  writeFile(xdir, "b.planes", "to shared of x:\n  give x + 1\n");
  const nodeLoader2 = createNodeModuleLoader();
  const nodeGraph2 = await load_graph(nodeLoader2, path.join(xdir, "main.planes"));
  let nodeCollMsg = null;
  try {
    check_collisions(nodeGraph2, nodeLoader2);
  } catch (e) {
    nodeCollMsg = e.message;
  }
  const restore3 = installFsFetch();
  let browserCollMsg = null;
  try {
    const base = pathToFileURL(path.join(xdir, "main.planes")).href;
    const browserLoader2 = new BrowserModuleLoader({ base });
    const browserGraph2 = await load_graph(browserLoader2, base);
    try {
      check_collisions(browserGraph2, browserLoader2);
    } catch (e) {
      browserCollMsg = e.message;
    }
  } finally {
    restore3();
  }
  assert(nodeCollMsg !== null && nodeCollMsg === browserCollMsg, `collision: node=${nodeCollMsg} browser=${browserCollMsg}`);
});

await check("C", "a cycle is caught (already exercised above; re-asserted standalone)", async () => {
  const dir = makeTempDir();
  writeFile(dir, "a.planes", "use b\nto fa of x:\n  give x\n");
  writeFile(dir, "b.planes", "use a\nto fb of x:\n  give x\n");
  let threw = false;
  try {
    await load_graph(createNodeModuleLoader(), path.join(dir, "a.planes"));
  } catch (e) {
    threw = e instanceof ModuleError && /module cycle/.test(e.message);
  }
  assert(threw, "cycle was not caught");
});

await check("C", "a collision is caught (already exercised above; re-asserted standalone)", async () => {
  const dir = makeTempDir();
  writeFile(dir, "main.planes", "use a\nuse b\n");
  writeFile(dir, "a.planes", "to shared of x:\n  give x\n");
  writeFile(dir, "b.planes", "to shared of x:\n  give x + 1\n");
  const loader = createNodeModuleLoader();
  const graph = await load_graph(loader, path.join(dir, "main.planes"));
  let threw = false;
  try {
    check_collisions(graph, loader);
  } catch (e) {
    threw = e instanceof ModuleError && /two modules define the same name/.test(e.message);
  }
  assert(threw, "collision was not caught");
});

await check("C", "the browser loader issues exactly one fetch per module per run", async () => {
  const restore = installFsFetch();
  try {
    let fetches = 0;
    const real = globalThis.fetch;
    globalThis.fetch = async (...args) => {
      fetches += 1;
      return real(...args);
    };
    const base = pathToFileURL(rel("paint/bloom.planes")).href;
    const src = readFileSync(rel("paint/bloom.planes"), "utf8");
    const loader = new BrowserModuleLoader({ base });
    for (let tick = 0; tick < 10; tick++) {
      const wrapped = `let tick = ${tick}\nlet keys = []\nlet pointer = { x: 0, y: 0, down: false }\nlet state = nothing\n${src}`;
      const r = await runProgramGraph(wrapped, { loader });
      assert(r.error === null, JSON.stringify(r.error));
    }
    assert(fetches === 2, `expected exactly 2 fetches (draw, math) across 10 ticks, got ${fetches}`);
  } finally {
    restore();
  }
});

// --------------------------------------------------------------- D. Invariants
// BLOCKING

await check("D", "the host surface is unchanged at 7 methods", () => {
  const hostSrc = readFileSync(rel("js/host.mjs"), "utf8");
  const REQUIRED = ["ask", "read", "write", "show", "clock", "resolve", "parseJson"];
  for (const m of REQUIRED) {
    assert(new RegExp(`\\b${m}\\s*\\(`).test(hostSrc), `host.mjs missing ${m}`);
  }
  assert(!/\btoJson\s*\(/.test(hostSrc), "host.mjs has toJson back on the surface");
});

await check("D", "grammar/vocabulary.json is unchanged from b7adc34", () => {
  const sha = execSync(`git hash-object "${rel("grammar/vocabulary.json")}"`, { cwd: REPO }).toString().trim();
  assert(sha.startsWith("b7adc34"), `grammar/vocabulary.json blob is ${sha}, expected to start with b7adc34`);
});

await check("D", "builtin count is unchanged at 10", () => {
  assert(vocab.builtins.length === 10, `builtins: ${vocab.builtins.length}`);
});

await check("D", "js/modules.mjs imports nothing from node:", () => {
  const src = readFileSync(rel("js/modules.mjs"), "utf8");
  assert(!/\bnode:/.test(src), "js/modules.mjs references node:");
});

await check("D", "draw.planes's function set equals the protocol verb table minus protocol", () => {
  const drawSrc = readFileSync(rel("paint/draw.planes"), "utf8");
  const defined = new Set([...drawSrc.matchAll(/^to ([a-z-]+)/gm)].map((m) => m[1]));
  const verbSet = new Set(VERBS);
  const missing = VERBS.filter((v) => !defined.has(v));
  const extra = [...defined].filter((d) => !verbSet.has(d));
  assert(missing.length === 0, `missing from draw.planes: ${missing.join(", ")}`);
  assert(extra.length === 0, `extra in draw.planes: ${extra.join(", ")}`);
  assert(defined.size === 26, `draw.planes defines ${defined.size} functions, expected 26`);
});

await check("D", 'no show "draw outside draw.planes', () => {
  const planesFiles = fs.readdirSync(rel("paint")).filter((f) => f.endsWith(".planes") && f !== "draw.planes");
  for (const f of planesFiles) {
    const src = readFileSync(rel("paint", f), "utf8");
    assert(!/show\s+"draw\b/.test(src), `${f} emits a raw "draw " string`);
  }
});

// ---------------------------------------------------------------- E. Programs

const EXAMPLES = ["turtle", "bloom", "snake"];

await check("E", "all three programs parse", () => {
  for (const name of EXAMPLES) {
    const src = readFileSync(rel("paint", `${name}.planes`), "utf8");
    parse(src);
  }
});

await check("E", "all three programs run and emit zero protocol/painter errors", async () => {
  const restore = installFsFetch();
  try {
    for (const name of EXAMPLES) {
      const src = readFileSync(rel("paint", `${name}.planes`), "utf8");
      const base = pathToFileURL(rel("paint", `${name}.planes`)).href;
      const wrapped = `let tick = 0\nlet keys = []\nlet pointer = { x: 0, y: 0, down: false }\nlet state = nothing\n${src}`;
      const r = await runProgramGraph(wrapped, { base });
      assert(r.error === null, `${name}: ${JSON.stringify(r.error)}`);
      const result = paint(fakeCtx(), r.output, DIMENSIONS);
      assert(result.errors.length === 0, `${name}: painter errors ${JSON.stringify(result.errors)}`);
    }
  } finally {
    restore();
  }
});

await check("E", "effect surfaces match main (console for turtle/bloom; console+file for snake)", async () => {
  const restore = installFsFetch();
  try {
    const surfaces = {};
    for (const name of EXAMPLES) {
      const src = readFileSync(rel("paint", `${name}.planes`), "utf8");
      const base = pathToFileURL(rel("paint", `${name}.planes`)).href;
      const { surface, error } = await analyseProgramGraph(src, { base });
      assert(error === null, `${name}: ${JSON.stringify(error)}`);
      surfaces[name] = surface;
    }
    for (const name of ["turtle", "bloom"]) {
      const s = surfaces[name];
      assert(
        s.touches("console") && !s.touches("file") && !s.touches("network") && !s.touches("ambient"),
        `${name}: unexpected surface`,
      );
    }
    const snake = surfaces.snake;
    assert(
      snake.touches("console") && snake.touches("file") && !snake.touches("network") && !snake.touches("ambient"),
      "snake: unexpected surface",
    );
    const targets = snake.targets("write");
    assert(targets.length === 1 && targets[0] === "state.json", JSON.stringify(targets));
  } finally {
    restore();
  }
});

// ------------------------------------------------------------------- report

const CATEGORY_NAME = { A: "Protocol", B: "Painter", C: "Modules", D: "Invariants", E: "Programs" };
const BLOCKING = new Set(["A", "C", "D"]);

const lines = [];
lines.push("# Drawing Protocol Verification (§12.2)");
lines.push("");
lines.push(`Run at commit \`${process.env.GIT_COMMIT || "(uncommitted)"}\`.`);
lines.push("");
lines.push("| Category | Check | Result | Detail |");
lines.push("|---|---|---|---|");

let anyFail = false;
let blockingFail = false;
for (const r of results) {
  const mark = r.ok ? "PASS" : "FAIL";
  if (!r.ok) {
    anyFail = true;
    if (BLOCKING.has(r.category)) blockingFail = true;
  }
  lines.push(
    `| ${CATEGORY_NAME[r.category]} | ${r.name} | ${mark} | ${r.ok ? "" : r.detail.replace(/\|/g, "\\|")} |`,
  );
}

lines.push("");
const total = results.length;
const passed = results.filter((r) => r.ok).length;
lines.push(`**${passed}/${total} checks passed.**`);
lines.push("");
lines.push(
  blockingFail
    ? "**BLOCKING FAILURE** — a Protocol (A), Modules (C), or Invariants (D) check failed."
    : anyFail
      ? "Non-blocking failure(s) in B or E — investigate, but this does not fail the gate on its own."
      : "All checks passed, including the three blocking categories (A, C, D).",
);
lines.push("");
lines.push(
  "Note: the per-tick benchmark regression (§12.1) is tracked separately in " +
    "`reports/feat-module-loader-and-drawing-protocol-v1-benchmarks-post.md` — it is also a blocking " +
    "item per §12.1, independent of the checks in this file.",
);

const report = lines.join("\n") + "\n";
console.log(report);

fs.writeFileSync(rel("reports", "drawing-protocol-verification.md"), report);

if (blockingFail) {
  process.exit(1);
}
