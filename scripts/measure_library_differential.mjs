#!/usr/bin/env node
// scripts/measure_library_differential.mjs — the library differential:
// run paint/bloom.planes and benchmarks/bloom_inline.planes over the same
// tick range under Node, assert their streams are byte-identical BEFORE
// timing anything (§3.2 — the twin's own staleness detector, not just a
// correctness check), then report per-tick wall clock for each arm, the
// absolute delta, the delta as a percentage of the library arm, and the
// delta divided by the number of helper calls per tick — the per-call
// library overhead, measured in the language's own terms.
//
// It changes nothing it measures: both arms run through the same
// stepGraph/BrowserModuleLoader path paint.html and the paint test suite
// already use (js/paint/loop.mjs, js/module_loader_browser.mjs), over an
// fs-backed `fetch` stub. Neither arm's interpreter, module loader, or
// painter is touched.
//
// Timer: process.hrtime.bigint(), not performance.now() (deliberately
// coarsened — see §4.2 of reports/REPORT_CALL_COST.md). The first
// WARMUP_TICKS ticks of each arm are run and included in the correctness
// check but discarded from the timing figures, so V8's JIT warm-up on the
// interpreter's hot call path is not in the reported medians.
//
// bloom only (not turtle, not snake): bloom has the highest drawing-call
// density of the three example programs, so it is the upper bound on
// library overhead, which is the decision-relevant figure. See
// reports/REPORT_CALL_COST.md §2 for the scoping argument in full.
//
// Usage: node scripts/measure_library_differential.mjs [--json]
//          [--library <path>] [--inline <path>] [--ticks <n>]
// --library/--inline let scripts/verify-call-cost.mjs point this at a
// deliberately perturbed copy to confirm the byte-identical assertion fails
// correctly, without touching the real files.
//
// A finding this script exists to surface, not to hide: `tick` is rendered
// into the entry source's own prelude (composePrelude, js/paint/loop.mjs),
// so the entry text differs every tick and is never a cache hit — every
// tick genuinely re-parses the whole entry, in the shipped page exactly as
// here. A `use`d file's own text does not change tick to tick and IS
// cache-hit (BrowserModuleLoader's astCache). So moving code out of the
// entry and into a `use`d library changes what gets re-parsed every tick,
// not just what gets called — this script additionally times parse-only
// cost for each arm's entry text so that effect is visible on its own,
// separate from call-dispatch cost (which the ladder, §4, isolates
// cleanly by parsing once and looping many calls inside one parsed run).

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { stepGraph, composePrelude } from "../js/paint/loop.mjs";
import { BrowserModuleLoader } from "../js/module_loader_browser.mjs";
import { parse } from "../js/parser.mjs";
import { uses_in, resolve, load_graph, names_in_graph } from "../js/modules.mjs";
import "../js/browser_main.mjs"; // side effect: loads grammar data (setVocabulary/setAmberTemplates)

const REPO_ROOT = fileURLToPath(new URL("..", import.meta.url));
const DEFAULT_LIBRARY = path.join(REPO_ROOT, "paint", "bloom.planes");
const DEFAULT_INLINE = path.join(REPO_ROOT, "benchmarks", "bloom_inline.planes");
// Both arms resolve `use math` against paint/'s own directory — the inline
// arm's physical location under benchmarks/ is irrelevant to module
// resolution here, since both are run as in-memory strings through a loader
// constructed with this base (checkpoint v21.0 §249: a module path resolves
// relative to the importing file's own location, which for an in-memory
// entry string is the loader's `base`).
const MODULE_BASE = pathToFileURL(path.join(REPO_ROOT, "paint", "bloom.planes")).href;

const DEFAULT_TICKS = 200;
const WARMUP_TICKS = 20;

function parseArgs(argv) {
  const opts = { library: DEFAULT_LIBRARY, inline: DEFAULT_INLINE, json: false, ticks: DEFAULT_TICKS };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--library") opts.library = argv[++i];
    else if (argv[i] === "--inline") opts.inline = argv[++i];
    else if (argv[i] === "--json") opts.json = true;
    else if (argv[i] === "--ticks") opts.ticks = Number(argv[++i]);
    else throw new Error(`unknown argument: ${argv[i]}`);
  }
  return opts;
}

// An fs-backed `fetch` stub — the same one js/test/paint_examples.test.mjs
// uses — so BrowserModuleLoader's real fetch-based resolution runs unchanged
// under Node, answered from disk instead of a network stack.
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

function median(xs) {
  const s = [...xs].sort((a, b) => a - b);
  const n = s.length;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

// The names a graph makes known to its entry's parser — the same
// resolve/load_graph/names_in_graph sequence runProgramGraph runs
// internally (js/browser_main.mjs), reused here only to drive `parse`
// directly for the parse-only timing below. Read-only: this never executes
// anything, only parses.
async function knownNamesFor(entryText, base) {
  const loader = new BrowserModuleLoader({ base });
  const used = uses_in(entryText);
  const deps = [];
  for (const mod of used) {
    const target = resolve(loader, mod, null);
    // eslint-disable-next-line no-await-in-loop
    if (target !== null) deps.push(...(await load_graph(loader, target)));
  }
  const graph = [...deps, ["__entry__", entryText]];
  return names_in_graph(graph, loader);
}

const PARSE_SAMPLE_TICKS = 30;
const PARSE_TRIALS = 7;

// Median nanoseconds to parse ONE entry text (prelude + program source, the
// same string stepGraph builds and hands to `parse` on every real tick),
// averaged over a sample of ticks per trial and reduced by median across
// trials — isolates the parse-size effect named in the header comment from
// the call-dispatch effect the total per-tick figure conflates it with.
function parseOnlyMedianNs(entryTexts, known) {
  for (const text of entryTexts) parse(text, known); // warm-up, discarded
  const perTrial = [];
  for (let t = 0; t < PARSE_TRIALS; t++) {
    const t0 = process.hrtime.bigint();
    for (const text of entryTexts) parse(text, known);
    const t1 = process.hrtime.bigint();
    perTrial.push(Number(t1 - t0) / entryTexts.length);
  }
  return median(perTrial);
}

async function collect(srcPath, ticks) {
  const src = fs.readFileSync(srcPath, "utf-8");
  const loader = new BrowserModuleLoader({ base: MODULE_BASE });
  const streams = [];
  const nsPerTick = [];
  const callsPerTick = [];
  for (let tick = 0; tick < ticks; tick++) {
    const ctx = { tick, keys: [], pointer: { x: 0, y: 0, down: false }, state: null };
    const t0 = process.hrtime.bigint();
    // eslint-disable-next-line no-await-in-loop
    const r = await stepGraph(src, ctx, { loader });
    const t1 = process.hrtime.bigint();
    if (r.error) {
      throw new Error(`${srcPath} tick ${tick}: ${r.error.tag}: ${r.error.message}`);
    }
    streams.push(r.lines.join("\n"));
    nsPerTick.push(Number(t1 - t0));
    callsPerTick.push(r.lines.filter((l) => /^draw /.test(l)).length);
  }
  return { streams, nsPerTick, callsPerTick };
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const restoreFetch = installFsFetch();
  try {
    const library = await collect(opts.library, opts.ticks);
    const inline = await collect(opts.inline, opts.ticks);

    // §3.2 — the correctness anchor and staleness detector, checked over the
    // WHOLE tick range, before any timing figure is computed or printed.
    let firstMismatch = -1;
    for (let tick = 0; tick < opts.ticks; tick++) {
      if (library.streams[tick] !== inline.streams[tick]) {
        firstMismatch = tick;
        break;
      }
    }
    const identical = firstMismatch === -1;

    if (!identical) {
      console.error(`STREAMS_IDENTICAL=false`);
      console.error(`FIRST_MISMATCH_TICK=${firstMismatch}`);
      console.error(`--- library (tick ${firstMismatch}) ---`);
      console.error(library.streams[firstMismatch]);
      console.error(`--- inline (tick ${firstMismatch}) ---`);
      console.error(inline.streams[firstMismatch]);
      process.exitCode = 1;
      return;
    }

    const warmup = opts.ticks > WARMUP_TICKS ? WARMUP_TICKS : 0;
    const callsPerTick = library.callsPerTick[0];
    const callsConstant =
      library.callsPerTick.every((c) => c === callsPerTick) &&
      inline.callsPerTick.every((c) => c === callsPerTick);

    const libTimed = library.nsPerTick.slice(warmup);
    const inlTimed = inline.nsPerTick.slice(warmup);

    const libraryMedianNs = median(libTimed);
    const inlineMedianNs = median(inlTimed);
    const deltaNs = libraryMedianNs - inlineMedianNs;
    const deltaPctOfLibrary = (deltaNs / libraryMedianNs) * 100;
    const perCallLibraryOverheadNs = callsConstant ? deltaNs / callsPerTick : null;

    // Parse-only breakdown (see the header note): sample a few post-warmup
    // ticks' actual entry texts and time `parse` on them directly, so the
    // total-per-tick delta above can be split into "bigger source to
    // re-parse every tick" vs "more calls to dispatch every tick."
    const libSrc = fs.readFileSync(opts.library, "utf-8");
    const inlSrc = fs.readFileSync(opts.inline, "utf-8");
    const sampleTicks = Array.from(
      { length: Math.min(PARSE_SAMPLE_TICKS, opts.ticks - warmup) },
      (_, i) => warmup + i,
    );
    const libEntryTexts = sampleTicks.map(
      (tick) => composePrelude({ tick, keys: [], pointer: { x: 0, y: 0, down: false }, state: null }) + "\n" + libSrc,
    );
    const inlEntryTexts = sampleTicks.map(
      (tick) => composePrelude({ tick, keys: [], pointer: { x: 0, y: 0, down: false }, state: null }) + "\n" + inlSrc,
    );
    const libKnown = await knownNamesFor(libEntryTexts[0], MODULE_BASE);
    const inlKnown = await knownNamesFor(inlEntryTexts[0], MODULE_BASE);
    const libraryParseMedianNs = parseOnlyMedianNs(libEntryTexts, libKnown);
    const inlineParseMedianNs = parseOnlyMedianNs(inlEntryTexts, inlKnown);
    const libraryExecMedianNs = libraryMedianNs - libraryParseMedianNs;
    const inlineExecMedianNs = inlineMedianNs - inlineParseMedianNs;
    const execDeltaNs = libraryExecMedianNs - inlineExecMedianNs;
    const execPerCallLibraryOverheadNs = callsConstant ? execDeltaNs / callsPerTick : null;

    const result = {
      implementation: "js",
      streamsIdentical: identical,
      ticks: opts.ticks,
      warmupTicksDiscarded: warmup,
      callsPerTick: callsConstant ? callsPerTick : null,
      callsConstantAcrossTicks: callsConstant,
      libraryMedianNsPerTick: libraryMedianNs,
      inlineMedianNsPerTick: inlineMedianNs,
      deltaNs,
      deltaPctOfLibrary,
      perCallLibraryOverheadNs,
      libraryParseMedianNs,
      inlineParseMedianNs,
      libraryExecMedianNs,
      inlineExecMedianNs,
      execDeltaNs,
      execPerCallLibraryOverheadNs,
    };

    if (opts.json) {
      console.log(JSON.stringify(result));
    } else {
      console.log("# The library differential — paint/bloom.planes vs benchmarks/bloom_inline.planes (JS, Node)");
      console.log(`IMPLEMENTATION=js`);
      console.log(`STREAMS_IDENTICAL=${identical}`);
      console.log(`TICKS=${opts.ticks}`);
      console.log(`WARMUP_TICKS_DISCARDED=${warmup}`);
      console.log(`CALLS_PER_TICK=${result.callsPerTick}`);
      console.log(`CALLS_CONSTANT_ACROSS_TICKS=${callsConstant}`);
      console.log(`LIBRARY_MEDIAN_NS_PER_TICK=${libraryMedianNs.toFixed(1)}`);
      console.log(`INLINE_MEDIAN_NS_PER_TICK=${inlineMedianNs.toFixed(1)}`);
      console.log(`DELTA_NS_PER_TICK=${deltaNs.toFixed(1)}`);
      console.log(`DELTA_PCT_OF_LIBRARY=${deltaPctOfLibrary.toFixed(2)}`);
      console.log(
        `PER_CALL_LIBRARY_OVERHEAD_NS=${perCallLibraryOverheadNs !== null ? perCallLibraryOverheadNs.toFixed(1) : "n/a"}`,
      );
      console.log(`LIBRARY_PARSE_MEDIAN_NS=${libraryParseMedianNs.toFixed(1)}`);
      console.log(`INLINE_PARSE_MEDIAN_NS=${inlineParseMedianNs.toFixed(1)}`);
      console.log(`LIBRARY_EXEC_MEDIAN_NS=${libraryExecMedianNs.toFixed(1)}`);
      console.log(`INLINE_EXEC_MEDIAN_NS=${inlineExecMedianNs.toFixed(1)}`);
      console.log(`EXEC_DELTA_NS_PER_TICK=${execDeltaNs.toFixed(1)}`);
      console.log(
        `EXEC_PER_CALL_LIBRARY_OVERHEAD_NS=${execPerCallLibraryOverheadNs !== null ? execPerCallLibraryOverheadNs.toFixed(1) : "n/a"}`,
      );
    }
  } finally {
    restoreFetch();
  }
}

main().catch((e) => {
  console.error(e.stack || String(e));
  process.exitCode = 1;
});
