// js/test/meta_browser.test.mjs — the metacircular stack in a browser, headless.
//
// js/meta_browser.mjs is DOM-free, so everything meta.html claims is checkable
// here, under Node, with no page open. The browser module loader runs against a
// stubbed global `fetch` that reads the repo from disk — the idiom
// js/test/module_loader.test.mjs already uses, so the REAL BrowserModuleLoader
// is exercised, not a substitute for it.
//
// This is the durable form, written first. Phase 1 of this sequence found the
// retirement rule the hard way: a verification script graduates into a suite or
// is deleted when its build merges, and `test_gate.py` fails the branch until it
// does. There is no scripts/verify-*.mjs for this build.
//
// WHAT IT PINS
//
//   A  byte-identity with `node js/cli.mjs meta <stage>` — the page's engine and
//      the Node path answer the same thing for the same program
//   B  byte-identity direct vs metacircular — one interpretive layer and two
//      agree, which is the whole claim the page makes visibly
//   C  stage reuse — N programs issue one fetch per module, not N
//   D  the timing split — stage load and per-program time are separate and real
//   E  graph resolution — interp.planes -> parser -> lexer, vocabulary, all
//      through the browser loader; `use file` / `use http` fetch nothing
//   F  anti-vacuity — each of the above fails when its subject is broken

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const BASE = pathToFileURL(REPO + "/").href;

// ---- the fetch stub ---------------------------------------------------------
//
// BrowserModuleLoader fetches; Node's fetch does not do file:// URLs. This
// serves the repo from disk under the same URL shapes a page would use, so the
// loader's own resolution, caching, cache-busting and error paths are the ones
// under test.
let fetches = [];
globalThis.fetch = async (url) => {
  fetches.push(String(url));
  const u = new URL(String(url));
  const p = fileURLToPath(new URL(u.pathname, BASE));
  if (!fs.existsSync(p)) {
    return { ok: false, status: 404, text: async () => "" };
  }
  return { ok: true, status: 200, text: async () => fs.readFileSync(p, "utf-8") };
};

const {
  STAGES,
  STAGE_NAMES,
  loadStage,
  throughStage,
  direct,
  compare,
  sameResult,
  recursionCeiling,
  stageLocation,
  measureRatio,
} = await import("../meta_browser.mjs");

// Five corpus programs, fixed, covering arithmetic, calls, records, lists and
// text. Small enough to run twice per stage in a suite; real enough that a pass
// means something.
const PROGRAMS = [
  "ordinary.planes",
  "corpus/factorial.planes",
  "corpus/word-count.planes",
  "corpus/slugify.planes",
  "corpus/discount-tiers.planes",
];

const source = (rel) => fs.readFileSync(path.join(REPO, rel), "utf-8");

function nodeMeta(stage, rel) {
  const out = execFileSync(
    "node",
    ["js/cli.mjs", "meta", stage, rel],
    { cwd: REPO, encoding: "utf-8", maxBuffer: 1 << 28 },
  );
  return JSON.parse(out)[0];
}

async function stage(name, opts = {}) {
  fetches = [];
  return await loadStage(name, { base: BASE, ...opts });
}

// ============================================================ A — vs the Node path

for (const name of STAGE_NAMES) {
  test(`A: ${name} — the page engine matches \`node js/cli.mjs meta ${name}\``, async () => {
    const loaded = await stage(name);
    for (const rel of PROGRAMS) {
      const mine = throughStage(loaded, source(rel));
      assert.equal(mine.error, null, `${rel}: ${JSON.stringify(mine.error)}`);
      assert.deepEqual(
        JSON.parse(JSON.stringify(mine.result)),
        nodeMeta(name, rel),
        `${name} disagreed with the Node path on ${rel}`,
      );
    }
  });
}

// ============================================================ B — direct vs meta

for (const name of STAGE_NAMES) {
  test(`B: ${name} — direct and metacircular agree on all five programs`, async () => {
    const loaded = await stage(name);
    for (const rel of PROGRAMS) {
      const c = compare(loaded, source(rel));
      assert.equal(c.direct.error, null, `${rel} direct: ${JSON.stringify(c.direct.error)}`);
      assert.equal(
        c.metacircular.error,
        null,
        `${rel} metacircular: ${JSON.stringify(c.metacircular.error)}`,
      );
      assert.ok(
        c.identical,
        `${name}/${rel}: the two paths disagreed\n` +
          `  direct: ${JSON.stringify(c.direct.result).slice(0, 300)}\n` +
          `  meta:   ${JSON.stringify(c.metacircular.result).slice(0, 300)}`,
      );
    }
  });
}

// The whole standalone corpus, through the browser stack, in one loaded stage.
//
// The five programs above are a sample; this is the population. It is the
// browser counterpart of test_js_metacircular.py's corpus sweep, and it exists
// because the report's strongest claim — that the page reproduces the Node
// stack's behaviour exactly, including its one documented gap — is worth a gate
// assertion rather than a paragraph. The three non-agreement classes are the
// ones that suite already names; anything else is new and fails here.
test("the whole standalone corpus agrees, with only the documented exceptions", async () => {
  const all = [];
  const walk = (d) => {
    for (const e of fs.readdirSync(path.join(REPO, d), { withFileTypes: true })) {
      const rel = d === "." ? e.name : `${d}/${e.name}`;
      if (e.isDirectory()) {
        if ([".venv", ".git", "node_modules", ".playwright-cli"].includes(e.name)) continue;
        walk(rel);
      } else if (e.name.endsWith(".planes")) all.push(rel);
    }
  };
  walk(".");
  const standalone = all
    .sort()
    .filter((f) => !source(f).split("\n").some((l) => l.trim().startsWith("use ")));
  assert.ok(standalone.length > 60, `only ${standalone.length} standalone programs found`);

  const loaded = await stage("run");
  // The refusal tags test_js_metacircular.py already treats as agreement: a
  // parse refusal both sides make, and the two spellings of "this host cannot
  // resolve a foreign target" — interp.planes has no dynamic host.resolve.
  const PARSE_REFUSALS = new Set(["ambiguity", "parse-error", "syntax"]);
  const FOREIGN_REFUSALS = new Set(["foreign-needs-host", "foreign-not-found"]);
  const unexplained = [];
  for (const f of standalone) {
    const c = compare(loaded, source(f));
    if (c.identical) continue;
    if (c.metacircular.error && PARSE_REFUSALS.has(c.metacircular.error.tag)) continue;
    const dTag = c.direct.result && c.direct.result.tag;
    const mTag = c.metacircular.result && c.metacircular.result.tag;
    if (FOREIGN_REFUSALS.has(mTag) && (FOREIGN_REFUSALS.has(dTag) || f === "foreign.planes")) {
      continue;
    }
    unexplained.push(`${f}: direct=${dTag} meta=${mTag} err=${JSON.stringify(c.metacircular.error)}`);
  }
  assert.deepEqual(
    unexplained,
    [],
    "new divergence(s) between the browser stack and the direct one:\n  " +
      unexplained.join("\n  "),
  );
});

// ============================================================ C — stage reuse

test("C: N programs issue one fetch per module, not N", async () => {
  const loaded = await stage("run");
  const afterLoad = fetches.length;
  const modules = loaded.loader.loadedModules().length;
  assert.equal(
    afterLoad,
    modules,
    `${afterLoad} fetch(es) for ${modules} module(s) — the loader cache is not holding`,
  );
  for (const rel of PROGRAMS) throughStage(loaded, source(rel));
  assert.equal(
    fetches.length,
    afterLoad,
    `${PROGRAMS.length} programs added ${fetches.length - afterLoad} fetch(es); ` +
      "the stage is being reloaded per program",
  );
});

test("C: the host resets between programs, so output does not bleed", async () => {
  const loaded = await stage("run");
  const first = throughStage(loaded, 'show "one"\n');
  const second = throughStage(loaded, 'show "two"\n');
  assert.deepEqual(first.result.output, ["one"]);
  assert.deepEqual(second.result.output, ["two"], "the first program's output leaked");
});

// ============================================================ D — the timing split

test("D: stage load and per-program time are separate, and both are real", async () => {
  const loaded = await stage("run");
  assert.ok(loaded.loadMs > 0, `stage load measured ${loaded.loadMs} ms`);
  const c = compare(loaded, source("ordinary.planes"));
  assert.ok(c.metacircular.ms > 0, "per-program time is zero");
  assert.ok(c.direct.ms > 0, "direct time is zero");
  assert.equal(c.loadMs, loaded.loadMs, "the load time reported is the load time measured");
  // THE TIMER MUST NOT BE MEASURING THE FETCH (§N+2 failure mode 7). Asserted
  // directly — no fetch happens during a timed call — rather than through a
  // proxy like "per-program is smaller than stage load", which is not true and
  // was never going to be: the Node baseline has per-program at 115 ms against a
  // 122 ms load, so the two are the same order and either can be larger.
  const before = fetches.length;
  const timed = throughStage(loaded, source("corpus/factorial.planes"));
  assert.equal(
    fetches.length,
    before,
    `${fetches.length - before} fetch(es) happened inside a timed call`,
  );
  assert.ok(timed.ms > 0);
  assert.ok(c.ratio > 1, `the second layer came out free or negative: ratio ${c.ratio}`);
});

test("D: the ratio survives a coarsened clock, which a single-shot timing does not", async () => {
  // THE DEFECT THIS PINS. WebKit coarsens performance.now() to 1 ms, so the
  // direct path — ~0.03 ms — measures 0.0 there on every single press, and the
  // page's headline number came out as a dash in Safari every time. Batch
  // timing is the fix; this is the assertion that it stays fixed.
  const loaded = await stage("run");
  const warm = measureRatio(loaded, source("ordinary.planes"), { budgetMs: 25 });
  assert.ok(warm.directMs > 0, "the direct side still measures zero");
  assert.ok(warm.ratio !== null && warm.ratio > 1, `ratio came out ${warm.ratio}`);
  assert.ok(
    warm.iterations.direct > 1,
    `only ${warm.iterations.direct} direct call(s) — that is a single-shot timing again`,
  );
});

// ============================================================ E — graph resolution

test("E: interp.planes resolves its whole graph through the browser loader", async () => {
  const loaded = await stage("run");
  const names = loaded.loader.loadedModules().map((m) => m.name).sort();
  // Five files, not four: `use parser` reaches lexer and vocabulary beneath it,
  // and `use json` is a fifth sibling. This is the same graph core_check.py
  // follows, and the same five the port surface is measured over.
  assert.deepEqual(names, ["interp", "json", "lexer", "parser", "vocabulary"]);
});

test("E: `use file` and `use http` are builtin capability modules and fetch nothing", async () => {
  const loaded = await stage("run");
  const asked = fetches.map((u) => new URL(u).pathname);
  for (const builtin of ["file", "http"]) {
    assert.ok(
      !asked.some((p) => p.endsWith(`/${builtin}.planes`)),
      `${builtin}.planes was fetched; it is a builtin capability module`,
    );
  }
  // grammar/interp.planes really does declare them — otherwise this passes
  // because the subject is absent rather than because the rule holds.
  const src = source("grammar/interp.planes");
  assert.match(src, /^use file$/m);
  assert.match(src, /^use http$/m);
});

test("E: each stage loads only the graph it needs", async () => {
  const lex = await stage("lex");
  assert.deepEqual(
    lex.loader.loadedModules().map((m) => m.name).sort(),
    ["lexer", "vocabulary"],
  );
  const parse = await stage("parse");
  assert.deepEqual(
    parse.loader.loadedModules().map((m) => m.name).sort(),
    ["lexer", "parser", "vocabulary"],
  );
});

// ============================================================ the ceiling (§5.2)

test("the recursion ceiling is measurable both ways, and the second layer lowers it", async () => {
  const loaded = await stage("run");
  const directCeiling = recursionCeiling((src) => direct("run", src), { cap: 4096 });
  const metaCeiling = recursionCeiling((src) => throughStage(loaded, src), { cap: 4096 });
  assert.ok(directCeiling.ceiling > 0, "no direct ceiling found");
  assert.ok(metaCeiling.ceiling > 0, "no metacircular ceiling found");
  assert.ok(
    metaCeiling.ceiling < directCeiling.ceiling,
    `metacircular ceiling ${metaCeiling.ceiling} is not below direct ${directCeiling.ceiling} ` +
      "— the second layer is costing no frames, which cannot be right",
  );
});

// ============================================================ F — anti-vacuity
//
// Each assertion group, broken deliberately, must fail. Without these, a suite
// that never ran its subject would look exactly like a suite that passed —
// the class caught at e2ef26a (#53) and again in Phase 1.

test("F/A: comparing against the WRONG stage's Node output fails", async () => {
  const loaded = await stage("lex");
  const mine = throughStage(loaded, source("ordinary.planes"));
  assert.notDeepEqual(
    JSON.parse(JSON.stringify(mine.result)),
    nodeMeta("parse", "ordinary.planes"),
    "lex and parse produced the same artifact — A cannot be distinguishing stages",
  );
});

test("F/B: a program whose two paths differ is reported as differing", async () => {
  const loaded = await stage("run");
  const c = compare(loaded, 'show "x"\n');
  assert.ok(c.identical);
  // Same comparison function, one side perturbed: the verdict must flip.
  assert.equal(
    sameResult(c.direct.result, { output: ["y"], tag: null }),
    false,
    "sameResult() cannot tell two different results apart",
  );
});

test("F/C: a FRESH loader per program does refetch — so C's subject is real", async () => {
  // Deliberately NOT through `stage()`, which zeroes the counter this measures.
  // C says a reused stage adds no fetches; that only means something if a
  // fresh one adds some, and this is the half that shows it does.
  fetches = [];
  await loadStage("run", { base: BASE });
  const afterFirst = fetches.length;
  assert.ok(afterFirst > 0, "the first stage load fetched nothing at all");
  await loadStage("run", { base: BASE }); // a second loadStage, hence a second loader
  assert.equal(
    fetches.length,
    afterFirst * 2,
    "a brand-new stage load reused the previous loader's cache — the C " +
      "assertion is measuring nothing",
  );
});

test("F/D: the ratio is withheld when a side fails, rather than invented", async () => {
  const loaded = await stage("run");
  const c = compare(loaded, "this is not a planes program (((\n");
  assert.equal(c.ratio, null, "a ratio was reported for a run that did not finish");
  assert.equal(c.identical, false);
});

test("F/E: a module that is genuinely absent fails the fetch, so E's loader is live", async () => {
  const loaded = await stage("run");
  await assert.rejects(
    () => loaded.loader.read(new URL("grammar/definitely-not-here.planes", BASE).href),
    /no module named 'definitely-not-here'/,
  );
});

// ============================================================ the core, in a browser

test("the 29-keyword core carries the metacircular stack in a browser too", async () => {
  const loaded = await stage("run", { coreOnly: true });
  const c = compare(loaded, source("ordinary.planes"));
  assert.equal(
    c.metacircular.error,
    null,
    `the restricted stack refused: ${JSON.stringify(c.metacircular.error)}`,
  );
  assert.ok(c.identical, "restricted and direct disagreed");
});

test("STAGES names the file and entry function each stage is driven through", () => {
  assert.deepEqual(STAGE_NAMES, ["lex", "parse", "run"]);
  assert.equal(STAGES.run.file, "../grammar/interp.planes");
  // module-relative, resolved against import.meta.url — not page-relative
  assert.ok(stageLocation(STAGES.run).endsWith("/grammar/interp.planes"));
  assert.equal(STAGES.run.fn, "execute-program");
  assert.equal(STAGES.parse.fn, "canonical-of-program-source");
  assert.equal(STAGES.lex.fn, "tokenize");
});
