// js/meta_browser.mjs — the metacircular stack, in a browser, timed.
//
// `test_js_metacircular.py` runs grammar/lexer.planes, grammar/parser.planes and
// grammar/interp.planes — a Planes implementation written in Planes — on top of
// js/interp.mjs, and checks the result against the Python implementation across
// the corpus. It is the strongest conformance evidence in this repo, and it has
// only ever run under Node, behind a shell command. This is the same stack, in a
// page, with a clock on it.
//
// WHAT IT IS FOR. v11.0 §136 ruled that the metacircular route gives the worst
// performance of any implementation option. That ruling has stood on reasoning
// alone, with no figure attached. This module produces the figure: the cost of
// the SECOND INTERPRETIVE LAYER, in milliseconds, split into what you pay once
// (loading the stage) and what you pay per program (running through it). §225
// found JSC roughly 4x JIT-cold Chrome, so the engine is a variable and a
// one-engine number describes a browser rather than an architecture — the caller
// records which engine produced each figure.
//
// DOM-FREE, exactly as browser_main.mjs's runProgram is, so every claim it makes
// is testable headless under Node (js/test/meta_browser.test.mjs). The page does
// the wiring; this does the work.

import { Interpreter, PlanesError, lit } from "./interp.mjs";
import { PlanesSyntaxError, tokenize } from "./lexer.mjs";
import { parse, PlanesAmbiguity } from "./parser.mjs";
import { canonicalProgram } from "./canonical.mjs";
import { PlanesNumber } from "./planes_num.mjs";
import { BrowserHost } from "./host_browser.mjs";
import { BrowserModuleLoader } from "./module_loader_browser.mjs";
import { loadGraphInto } from "./browser_main.mjs";

// The three stages, and the function each one is entered through.
//
// These names and call shapes are js/cli.mjs's `meta` subcommand, followed
// rather than reinvented: the Python oracle compares this stack's answers
// against interp.py through exactly these calls, so a second protocol here
// would be a second thing to keep in agreement. `label` is what the page shows.
// `file` is relative to THIS MODULE, and is resolved against `import.meta.url`
// rather than against the page's base. Those are the same directory today —
// meta.html sits at the repo root — and would silently stop being the same the
// moment a page in a subdirectory, or a second page with a different base,
// imported this module: the stage fetch would go looking for
// `<that page's dir>/grammar/interp.planes` and 404.
//
// The deploy-surface checker found this before a page did. It resolves a quoted
// `*.planes` reference the way a browser resolves a module-relative fetch —
// from the file that names it — so `"grammar/interp.planes"` in `js/` meant
// `js/grammar/interp.planes`, which does not exist. The checker was reading it
// correctly and the code was the odd one out.
export const STAGES = {
  lex: {
    file: "../grammar/lexer.planes",
    fn: "tokenize",
    label: "lex",
    describe: "token stream",
  },
  parse: {
    file: "../grammar/parser.planes",
    fn: "canonical-of-program-source",
    label: "parse",
    describe: "canonical AST",
  },
  run: {
    file: "../grammar/interp.planes",
    fn: "execute-program",
    label: "run",
    describe: "output",
  },
};

// A stage's location, absolute, independent of whoever imported this module.
export const stageLocation = (spec) => new URL(spec.file, import.meta.url).href;

export const STAGE_NAMES = Object.keys(STAGES);

// A monotonic clock where there is one. performance.now() in every browser and
// in Node >= 16; Date.now() is the floor, and a floor that never fires in the
// environments this actually runs in.
const now = () =>
  typeof performance !== "undefined" && performance.now
    ? performance.now()
    : Date.now();

function isStage(stage) {
  if (!Object.prototype.hasOwnProperty.call(STAGES, stage)) {
    throw new Error(
      `unknown stage '${stage}' — one of ${STAGE_NAMES.join(", ")}`,
    );
  }
  return STAGES[stage];
}

// ============================================================ loading a stage
//
// ONCE PER SESSION, NOT ONCE PER PROGRAM. `meta` amortises the stage load across
// every corpus file it processes, and so does this: reloading the graph per
// program would make every measurement below a measurement of fetch and hoist,
// and the ratio would come out absurd (§N+2 failure mode 6).
//
// The returned object holds the loaded interpreter. Hand it to `throughStage`
// as many times as you like.
export async function loadStage(
  stage,
  { base, loader = null, coreOnly = false, cacheBust = null } = {},
) {
  const spec = isStage(stage);
  // `cacheBust` is a page-load token appended to each `.planes` fetch and to
  // nothing else. A `.planes` module is a LEAF fetch — nothing resolves relative
  // to it — so a query string is a complete fix for a stale copy here, which is
  // exactly what it is not on the `.mjs` graph (staleModuleWarning covers that
  // half, and the page calls it).
  const ldr = loader ?? new BrowserModuleLoader({ base, cacheBust });
  const itp = new Interpreter({ host: new BrowserHost({}), coreOnly });

  const t0 = now();
  await loadGraphInto(itp, stageLocation(spec), { base, loader: ldr });
  const loadMs = now() - t0;

  return {
    stage,
    spec,
    itp,
    loader: ldr,
    loadMs,
    coreOnly,
    modules: ldr.loadedModules(),
  };
}

// ============================================================ running a program
//
// THE RESET DISCIPLINE, from js/cli.mjs's meta loop: a fresh host per program so
// show output does not bleed across programs, and `output`/`effects` cleared —
// but the interpreter, its loaded functions, and the whole stage graph are
// REUSED. That is what makes the per-program number a per-program number.
function resetHost(loaded) {
  loaded.itp.host = new BrowserHost({});
  loaded.itp.output = [];
  loaded.itp.effects = [];
}

const asNumber = (v) => (v instanceof PlanesNumber ? Number(v.asInt()) : v);

// Run `src` THROUGH the loaded stage — js/interp.mjs evaluating
// grammar/<stage>.planes evaluating `src`. Two interpretive layers.
//
// Returns { result, ms, error }. `result` is in the same shape `node js/cli.mjs
// meta <stage>` emits for one file, so the two are comparable byte for byte
// (invariant 9); `ms` excludes the stage load, which happened once, in
// loadStage.
export function throughStage(loaded, src) {
  const { itp, spec } = loaded;
  resetHost(loaded);
  const t0 = now();
  try {
    const r = itp.call(spec.fn, [lit(src)], itp.env);
    const ms = now() - t0;
    if (loaded.stage === "lex") {
      return {
        result: r.value.map((m) => [
          m.get("kind"),
          m.get("text"),
          asNumber(m.get("line")),
        ]),
        ms,
        error: null,
      };
    }
    if (loaded.stage === "parse") {
      return { result: r.value, ms, error: null };
    }
    // run — a status record; a failure names its tag exactly as `meta` reports it
    const status = r.value.get("status");
    let tag = null;
    if (status === "fail") {
      const err = r.value.get("error");
      tag = err && err.get ? err.get("tag") : String(err);
    }
    return {
      result: { output: itp.host.shown, tag },
      ms,
      error: null,
    };
  } catch (e) {
    return { result: null, ms: now() - t0, error: describeError(e) };
  }
}

// ============================================================ the direct path
//
// The SAME question asked of js/interp.mjs alone — one interpretive layer. The
// comparison only means something if both sides are asked for the same artifact,
// so each stage's direct form produces the shape its metacircular form produces:
// tokens for lex, the canonical program for parse, output and tag for run.
export function direct(stage, src) {
  isStage(stage);
  const t0 = now();
  try {
    if (stage === "lex") {
      const result = tokenize(src).map((t) => [t.kind, t.value, t.line]);
      return { result, ms: now() - t0, error: null };
    }
    if (stage === "parse") {
      const result = canonicalProgram(parse(src));
      return { result, ms: now() - t0, error: null };
    }
    const itp = new Interpreter({ host: new BrowserHost({}) });
    let tag = null;
    try {
      itp.run(src);
    } catch (e) {
      if (e instanceof PlanesError) tag = e.tag;
      else if (e instanceof PlanesSyntaxError) tag = "PARSE";
      else if (e instanceof RangeError) tag = "recursion-too-deep";
      else throw e;
    }
    return {
      result: { output: itp.output, tag },
      ms: now() - t0,
      error: null,
    };
  } catch (e) {
    return { result: null, ms: now() - t0, error: describeError(e) };
  }
}

function describeError(e) {
  if (e instanceof PlanesError) return { tag: e.tag, message: e.message };
  if (e instanceof PlanesAmbiguity) return { tag: "ambiguity", message: e.message };
  if (e instanceof PlanesSyntaxError) return { tag: "syntax", message: e.message };
  if (e instanceof RangeError) {
    return { tag: "recursion-too-deep", message: String(e.message) };
  }
  if (e && e.name === "CoreRestrictionError") {
    return { tag: "core-restricted", message: String(e.message) };
  }
  if (e && e.name === "ModuleError") return { tag: "module-error", message: e.message };
  return { tag: "internal", message: String((e && e.message) || e) };
}

// ============================================================ the comparison
//
// IDENTITY IS COMPUTED, NEVER EYEBALLED (invariant 6). A page that renders two
// panes and lets a reader compare them has asserted nothing. This is the
// assertion, and it is the same function the page renders its verdict from and
// the suite checks — not a second opinion about the same question.
//
// JSON.stringify is the comparison because every stage's result is already a
// JSON-shaped value chosen to match what `node js/cli.mjs meta` emits: arrays of
// [kind, text, line], a canonical string, or {output, tag}. Key ORDER is fixed
// by construction on both sides, so a false difference would need the two paths
// to build the same record differently, which is itself a finding.
export function sameResult(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

// Run one program both ways and report both, the verdict, and the split timings.
// The single call a page needs.
export function compare(loaded, src) {
  const meta = throughStage(loaded, src);
  const one = direct(loaded.stage, src);
  const identical =
    meta.error === null && one.error === null && sameResult(meta.result, one.result);
  return {
    stage: loaded.stage,
    direct: one,
    metacircular: meta,
    identical,
    // null when either side failed — a ratio against a run that did not finish
    // is a number with no meaning, and reporting one would be worse than
    // reporting none.
    ratio:
      meta.error === null && one.error === null && one.ms > 0
        ? meta.ms / one.ms
        : null,
    loadMs: loaded.loadMs,
  };
}

// ============================================================ timing that resolves
//
// A SINGLE-SHOT TIMING CANNOT MEASURE THE DIRECT PATH, and this is not a detail.
// `performance.now()` is deliberately coarsened in every browser as a Spectre
// mitigation — to about 0.1 ms in V8 and a full 1 ms in JSC — and a direct run of
// a small program takes ~0.03 ms. So `compare()` alone reports 0.0 ms on the
// direct side, and the ratio, which is this page's entire reason to exist, comes
// out as a dash. In WebKit it came out as a dash EVERY time.
//
// The fix is to time a batch and divide. Both sides get identical treatment, so
// the ratio stays a ratio of like measurements — and the iteration counts are
// returned so a reader can see the measurement was not one lucky call.
// `minIterations` is not a nicety. A metacircular call costs ~30 ms, so a
// 40 ms budget alone stops after TWO calls — and two samples against JSC's 1 ms
// clock is not a measurement, it is a coin toss with a decimal point. The floor
// makes the slow side sample enough to mean something; the budget still stops
// the fast side from spinning for a second.
export function perIteration(
  fn,
  { budgetMs = 40, minIterations = 5, maxIterations = 20000 } = {},
) {
  let n = 0;
  const t0 = now();
  let elapsed = 0;
  while (n < maxIterations) {
    fn();
    n += 1;
    elapsed = now() - t0;
    if (elapsed >= budgetMs && n >= minIterations) break;
  }
  return { ms: elapsed / n, iterations: n, totalMs: elapsed };
}

// The warm, steady-state cost of both paths, and the ratio between them.
//
// Separate from `compare` on purpose. `compare` answers "do the two agree, and
// what did this press cost" — one call each, which is what a reader experiences.
// This answers "what does the second layer cost", which needs many calls and is
// the architectural number. A page wants both: the first is the honest report of
// what just happened, the second is the honest report of what it means.
export function measureRatio(loaded, src, opts = {}) {
  const meta = perIteration(() => throughStage(loaded, src), opts);
  const one = perIteration(() => direct(loaded.stage, src), opts);
  return {
    directMs: one.ms,
    metacircularMs: meta.ms,
    ratio: one.ms > 0 ? meta.ms / one.ms : null,
    iterations: { direct: one.iterations, metacircular: meta.iterations },
  };
}

// ============================================================ the ceiling
//
// §225 measured recursion depth at 639 under Node, with `turtle` using 9. The
// metacircular stack puts a second interpretive layer under every user frame, so
// the ceiling falls by whatever that layer costs in frames — a factor nobody has
// measured, and the one number that decides whether the stack is usable at all
// rather than merely slow.
//
// Binary search rather than a climb: each probe is a whole program run, and
// through the stage that is expensive enough that a linear walk to the ceiling
// would dominate the page. `cap` bounds the search so a direct run cannot spend
// the session looking for a limit far above anything a program uses.
export function recursionCeiling(runner, { cap = 1024 } = {}) {
  const depthProgram = (n) =>
    `to down of n:\n` +
    `  if n <= 0:\n` +
    `    give 0\n` +
    `  give down of (n - 1)\n` +
    `show text of (down of ${n})\n`;

  const survives = (n) => {
    const r = runner(depthProgram(n));
    if (r.error !== null) return false;
    const tag = r.result && r.result.tag;
    return tag === null || tag === undefined;
  };

  if (!survives(1)) return { ceiling: 0, capped: false };
  let lo = 1;
  let hi = 2;
  while (hi <= cap && survives(hi)) {
    lo = hi;
    hi *= 2;
  }
  if (hi > cap) return { ceiling: lo, capped: true };
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (survives(mid)) lo = mid;
    else hi = mid;
  }
  return { ceiling: lo, capped: false };
}
