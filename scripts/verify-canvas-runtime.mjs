#!/usr/bin/env node
// scripts/verify-canvas-runtime.mjs — the feat/canvas-runtime gate (§9.2).
//
// Five categories, A through E. Blocking: any failure in C (surfaces) or D
// (isolation) — those are the invariants this build exists to hold. A, B and
// E are reported the same way but do not fail the gate on their own; a
// regression there is still a real bug, just not one of this build's own
// closed invariants.
//
// Usage: node scripts/verify-canvas-runtime.mjs
// Writes: canvas-runtime-verification.md (same table as stdout)

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const REPO = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const rel = (...p) => path.join(REPO, ...p);

const { parseCommand, VERBS } = await import(path.join(REPO, "js/paint/protocol.mjs"));
const { composePrelude, step } = await import(path.join(REPO, "js/paint/loop.mjs"));
const { parse } = await import(path.join(REPO, "js/parser.mjs"));
const { runProgram, analyseProgram } = await import(path.join(REPO, "js/browser_main.mjs"));
const vocab = JSON.parse(readFileSync(rel("grammar/vocabulary.json"), "utf8"));

const results = []; // { category, name, ok, detail }
function check(category, name, fn) {
  let ok, detail;
  try {
    fn();
    ok = true;
    detail = "";
  } catch (e) {
    ok = false;
    detail = e.message;
  }
  results.push({ category, name, ok, detail });
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg || "assertion failed");
}

// ---------------------------------------------------------------- A. Protocol

check("A", "every verb in the A.5 whitelist parses", () => {
  const samples = {
    pen: "pen 0.2 0.4 0.9",
    width: "width 3",
    move: "move 10 20",
    line: "line 30 40",
    circle: "circle 100 100 25",
    dot: "dot 50 60 5",
    rect: "rect 0 0 100 50",
    box: "box 10 10 20 20",
    text: "text 5 10 hello world",
    clear: "clear",
  };
  for (const verb of VERBS) {
    assert(samples[verb], `no sample line for verb ${verb}`);
    const cmd = parseCommand(samples[verb]);
    assert(cmd && cmd.verb === verb, `${verb} did not parse: ${JSON.stringify(cmd)}`);
  }
});

check("A", "wrong arity returns null", () => {
  assert(parseCommand("pen 0.2 0.4") === null);
  assert(parseCommand("move 1 2 3") === null);
  assert(parseCommand("clear 1") === null);
});

check("A", "an unknown verb returns null", () => {
  assert(parseCommand("triangle 1 2 3") === null);
});

check("A", "a `~`-prefixed number is accepted and the ~ is dropped", () => {
  const cmd = parseCommand("move ~10 ~20.5");
  assert(cmd && cmd.args[0] === 10 && cmd.args[1] === 20.5, JSON.stringify(cmd));
});

// -------------------------------------------------------------------- B. Loop

check("B", "composePrelude's output parses as valid Planes", () => {
  const src = composePrelude({
    tick: 1,
    keys: [],
    pointer: { x: 0, y: 0, down: false },
    state: { a: 1 },
  });
  parse(src, new Set());
});

check("B", "a three-tick sequence threads state correctly", () => {
  const src = `use file
if state is nothing:
  let next = { count: 0 }
else:
  let next = state with count: state.count + 1

write next to "state.json"
show text of next.count
`;
  let state = null;
  const seen = [];
  for (let tick = 0; tick < 3; tick++) {
    const r = step(src, { tick, keys: [], pointer: { x: 0, y: 0, down: false }, state });
    assert(r.error === null, JSON.stringify(r.error));
    state = r.state;
    seen.push(r.lines[0]);
  }
  assert(seen.join(",") === "0,1,2", seen.join(","));
});

check("B", "a first tick with nothing state works", () => {
  const r = step('if state is nothing:\n  show "fresh"\nelse:\n  show "carried"\n', {
    tick: 0,
    keys: [],
    pointer: { x: 0, y: 0, down: false },
    state: null,
  });
  assert(r.error === null && r.lines[0] === "fresh", JSON.stringify(r));
});

check("B", "an erroring program returns the error rather than throwing", () => {
  const r = step('z = 5 + "x"\n', {
    tick: 0,
    keys: [],
    pointer: { x: 0, y: 0, down: false },
    state: null,
  });
  assert(r.error && r.error.tag === "cannot-combine", JSON.stringify(r.error));
});

check("B", "a recursion-too-deep error is reported as itself", () => {
  const src = `to recurse of n:
  if n <= 0:
    give 0
  else:
    give 1 + (recurse of (n - 1))

show text of (recurse of 100000)
`;
  const r = step(src, { tick: 0, keys: [], pointer: { x: 0, y: 0, down: false }, state: null });
  assert(r.error && r.error.tag === "recursion-too-deep", JSON.stringify(r.error));
});

// ---------------------------------------------------------------- C. Surfaces
// BLOCKING

const EXAMPLES = ["turtle", "bloom", "snake"];
const surfaces = {};
for (const name of EXAMPLES) {
  const src = readFileSync(rel("paint", `${name}.planes`), "utf8");
  check("C", `${name}.planes's surface computes without error`, () => {
    const { surface, error } = analyseProgram(src);
    assert(error === null, JSON.stringify(error));
    surfaces[name] = surface;
  });
}

check("C", "turtle.planes's surface is console only", () => {
  const s = surfaces.turtle;
  assert(s.touches("console") && !s.touches("file") && !s.touches("network") && !s.touches("ambient"));
});

check("C", "bloom.planes's surface is console only", () => {
  const s = surfaces.bloom;
  assert(s.touches("console") && !s.touches("file") && !s.touches("network") && !s.touches("ambient"));
});

check("C", "snake.planes's surface is exactly console and file:write state.json", () => {
  const s = surfaces.snake;
  assert(s.touches("console") && s.touches("file") && !s.touches("network") && !s.touches("ambient"));
  const targets = s.targets("write");
  assert(targets.length === 1 && targets[0] === "state.json", JSON.stringify(targets));
});

check("C", "no example program's surface touches network", () => {
  for (const name of EXAMPLES) {
    assert(!surfaces[name].touches("network"), `${name} touches network`);
  }
});

// ---------------------------------------------------------------- D. Isolation
// BLOCKING

check("D", "no third-party origin appears in a src/href in paint.html", () => {
  const html = readFileSync(rel("paint.html"), "utf8");
  const attrRefs = [...html.matchAll(/\b(?:src|href)\s*=\s*["']([^"']+)["']/g)].map((m) => m[1]);
  for (const ref of attrRefs) {
    assert(!/^https?:\/\//.test(ref), `third-party-looking src/href: ${ref}`);
  }
});

check("D", "no `foreign` declaration in any paint/*.planes file", () => {
  for (const name of EXAMPLES) {
    const src = readFileSync(rel("paint", `${name}.planes`), "utf8");
    assert(!/^\s*foreign\s+\S+\s+from\s+"/m.test(src), `${name}.planes declares foreign`);
  }
});

check("D", "reserved words / builtins / effect kinds are unchanged at 32 / 10 / 7", () => {
  assert(vocab.keywords.length === 32, `keywords: ${vocab.keywords.length}`);
  assert(vocab.builtins.length === 10, `builtins: ${vocab.builtins.length}`);
  assert(vocab.effect_kinds.length === 7, `effect_kinds: ${vocab.effect_kinds.length}`);
});

check("D", "the host surface is unchanged at 7 methods", () => {
  const hostSrc = readFileSync(rel("js/host.mjs"), "utf8");
  const REQUIRED = ["ask", "read", "write", "show", "clock", "resolve", "parseJson"];
  for (const m of REQUIRED) {
    assert(new RegExp(`\\b${m}\\s*\\(`).test(hostSrc), `host.mjs missing ${m}`);
  }
  assert(!/\btoJson\s*\(/.test(hostSrc), "host.mjs has toJson back on the surface");
});

// ---------------------------------------------------------------- E. Regression

check("E", "index.html's sample program runs and matches its expected output", () => {
  const html = readFileSync(rel("index.html"), "utf8");
  const src = html.split('<textarea id="source" spellcheck="false">')[1].split("</textarea>")[0];
  const r = runProgram(src, {});
  assert(r.error === null, JSON.stringify(r.error));
  assert(
    r.output.join("|") === ["0.1 + 0.2 = 0.3", "wrote 5 readings to readings.json"].join("|"),
    JSON.stringify(r.output),
  );
});

// ------------------------------------------------------------------- report

const CATEGORY_NAME = { A: "Protocol", B: "Loop", C: "Surfaces", D: "Isolation", E: "Regression" };
const BLOCKING = new Set(["C", "D"]);

const lines = [];
lines.push("# Canvas Runtime Verification (§9.2)");
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
    ? "**BLOCKING FAILURE** — a Surfaces (C) or Isolation (D) check failed."
    : anyFail
      ? "Non-blocking failure(s) in A, B, or E — investigate, but this does not fail the gate on its own."
      : "All checks passed, including both blocking categories (C, D).",
);

const report = lines.join("\n") + "\n";
console.log(report);

const fs = await import("node:fs");
fs.writeFileSync(rel("canvas-runtime-verification.md"), report);

if (blockingFail) {
  process.exit(1);
}
