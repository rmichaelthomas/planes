#!/usr/bin/env node
// scripts/measure_update_cost.mjs — the update-cost ladder, JavaScript
// implementation. Mirror of scripts/measure_update_cost.py: same rung
// labels, same widths, same lengths, same calibration protocol, same
// output schema under --json (invariant 3, build prompt §8).
//
// Decomposes the cost of one functional update (`with`, record update;
// `plus`, list append — v5.0 §72) by subtraction, in the same discipline
// scripts/measure_call_cost.mjs uses for calls: each rung is a tiny program
// that adds ONE thing to an otherwise-identical loop body, run inside a
// nested `for each`, timed as a whole, with a control subtracted to isolate
// what that one rung adds. It changes nothing it measures: every rung and
// the control run through the ordinary `runProgram` entry point
// (js/browser_main.mjs); nothing here reaches into the interpreter.
//
// Two arms:
//
//   THE with ARM. For each record width W in WITH_WIDTHS, a control
//   (touches the base record, no update) and three rungs: rung 1
//   (`r with f0: 1`, one field written, one copy), rung 2
//   (`r with f0: 1 with f1: 2`, a SECOND chained `with` — a second copy),
//   rung 3 (`r with f0: 1, f1: 2`, two fields written in ONE `with` — one
//   copy, two field writes). Rung 3 minus rung 1 isolates the marginal cost
//   of a field write with the copy held constant; rung 2 minus rung 3
//   isolates the cost of the second copy.
//
//   THE plus ARM. For each list length L in PLUS_LENGTHS, a control (reads
//   the base list, appends nothing) and one rung (`xs plus i`, one append
//   at length L).
//
// Plus a CUMULATIVE measurement: build a list to length CUMULATIVE_L by
// CUMULATIVE_L repeated `plus` reassignments in a single program run,
// reporting total wall time and the implied O(L^2) constant, with an
// extrapolation to EXTRAPOLATE_TO events stated as an extrapolation.
//
// WHY A NESTED for-each LOOP, NOT RECURSION — identical reasoning to
// scripts/measure_call_cost.mjs. `L_iter` (the loop iteration-count
// parameter) is distinct from W (record width) and L (list length under
// test) and is calibrated per rung exactly as measure_call_cost.mjs
// calibrates its own L.
//
// Timer: process.hrtime.bigint() — NOT performance.now(), matching
// scripts/measure_call_cost.mjs.
//
// Usage: node scripts/measure_update_cost.mjs [--json]

import os from "node:os";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { runProgram } from "../js/browser_main.mjs";
import { parse } from "../js/parser.mjs";
import { Interpreter } from "../js/interp.mjs";
import { BrowserHost } from "../js/host_browser.mjs";

const TRIALS = 7;
const TARGET_NS = 200_000_000; // 200ms floor, matching measure_call_cost.mjs
const MAX_L = 4000;
const MAX_CALIBRATION_STEPS = 25;

const WITH_WIDTHS = [4, 8, 16, 32, 64, 128];
const PLUS_LENGTHS = [64, 256, 1024, 4096, 16384];

const CUMULATIVE_BASE = 128; // 128*128 = 16384 sequential `plus` appends
const CUMULATIVE_L = CUMULATIVE_BASE * CUMULATIVE_BASE;
const EXTRAPOLATE_TO = 100_000;

const WITH_RUNG_NAMES = ["rung1_single", "rung2_chained", "rung3_multi"];
const WITH_RUNG_LABELS = {
  rung1_single: "rung 1 — let r2 = r with f0: 1: one field written, one copy",
  rung2_chained:
    "rung 2 — let r2 = r with f0: 1 with f1: 2: a second chained `with` — rung 2 minus rung 3 isolates the second copy",
  rung3_multi:
    "rung 3 — let r2 = r with f0: 1, f1: 2: two fields in one RecordUpdate — rung 3 minus rung 1 isolates one field write",
};

const PLUS_RUNG_NAME = "rung1_append";
const PLUS_RUNG_LABEL = "rung 1 — let xs2 = xs plus i: one append at length L";

function buildList(n) {
  const parts = new Array(n);
  for (let i = 0; i < n; i++) parts[i] = i;
  return "[" + parts.join(", ") + "]";
}

function buildRecord(width) {
  const fields = [];
  for (let i = 0; i < width; i++) fields.push(`f${i}: ${i}`);
  return "{ " + fields.join(", ") + " }";
}

// rungName is null for the control (touches `r`, no update).
function buildWithSrc(rungName, width, iterL) {
  const record = buildRecord(width);
  const bodyExprs = {
    null: "r",
    rung1_single: "r with f0: 1",
    rung2_chained: "r with f0: 1 with f1: 2",
    rung3_multi: "r with f0: 1, f1: 2",
  };
  const body = `let ignored = ${bodyExprs[rungName === null ? "null" : rungName]}`;
  const loop = `for each i in base:\n  for each j in base:\n    ${body}\n`;
  return `let r = ${record}\nlet base = ${buildList(iterL)}\n${loop}`;
}

// rungName is null for the control (reads `xs`, appends nothing).
function buildPlusSrc(rungName, length, iterL) {
  const baseList = buildList(length);
  const body = `let ignored = ${rungName === null ? "xs" : "xs plus i"}`;
  const loop = `for each i in base:\n  for each j in base:\n    ${body}\n`;
  return `let xs = ${baseList}\nlet base = ${buildList(iterL)}\n${loop}`;
}

function buildCumulativeSrc() {
  const baseList = buildList(CUMULATIVE_BASE);
  return (
    `let base = ${baseList}\n` +
    "xs = []\n" +
    "for each i in base:\n" +
    "  for each j in base:\n" +
    "    xs = xs plus j\n" +
    'show "LEN=" + text of (count of xs)\n'
  );
}

const WORLD_T = 32; // matches benchmarks/world_shape.planes exactly
const WORLD_SUBJECT_COUNTS = [16, 64, 256];
const WORLD_FACET_W = 4;
const WORLD_SUBJECT_W = 7;
const WORLD_WORLD_W = 3;

// Everything in benchmarks/world_shape.planes except the `subject-count` /
// `subject-ids` lines, which this generates per S. Kept byte-for-byte
// identical to the shipped file's function definitions so the two cannot
// silently drift; test_update_cost.py checks buildWorldSrc(64) against the
// file on disk.
const WORLD_PRELUDE = `to make-subject of i:
  give {
    identity: { id: i, kind: "subject", canonical: true, version: 1 },
    situation: { place: "passage", x: i, y: 0, active: true },
    relation: { contains: [], connects-to: [], near: [], belongs-to: "world" },
    behavior: { pattern: "patrol", state: "idle", ticks-in-state: 0, deterministic: true },
    expression: { asset: "subject-mesh", layer: 1, animation: "idle", material: "default" },
    affordance: { actions: [], preconditions: [], authority: "system", fallback: "none" },
    lineage: { source: "world-shape-benchmark", author: "system", agreement: "none", immutable: false }
  }

to toggle-state of s:
  if s == "active":
    give "idle"
  else:
    give "active"

to advance-subject of subj, tick-num:
  let situation = subj.situation
  let new-situation = situation with x: situation.x + 1, y: situation.y + 1
  let behavior = subj.behavior
  let new-behavior = behavior with state: (toggle-state of behavior.state), ticks-in-state: behavior.ticks-in-state + 1
  give subj with situation: new-situation, behavior: new-behavior

to advance-world of world, tick-num:
  let new-subjects = for each subj in world.subjects: advance-subject of subj, tick-num
  let evt = { sequence: tick-num, kind: "tick-advance", subject-count: count of new-subjects }
  let new-events = world.events plus evt
  give world with subjects: new-subjects, events: new-events, tick: tick-num
`;

function buildWorldSrc(s) {
  return buildWorldSrcFor(s, WORLD_T);
}

// Phase 3 (build prompt §6) reuses this at t != WORLD_T to checkpoint the
// derivation graph at a chosen tick count -- otherwise identical to
// buildWorldSrc.
function buildWorldSrcFor(s, t) {
  const ids = buildList(s);
  const ticks = buildList(t);
  return (
    WORLD_PRELUDE +
    `let subject-count = ${s} because "S — the subject count this canonical instance measures; the sweep script generates the same shape at S in 16, 64, 256"\n` +
    `let subject-ids = ${ids}\n` +
    `let ticks = ${ticks}\n` +
    "\nlet initial-subjects = for each i in subject-ids: make-subject of i\n" +
    "let initial-world = { subjects: initial-subjects, events: [], tick: 0 }\n" +
    "\ncurrent-world = initial-world\n" +
    "for each t in ticks:\n" +
    "  current-world = advance-world of current-world, t\n" +
    '\nshow "FINAL-TICK=" + text of current-world.tick\n' +
    'show "SUBJECT-COUNT=" + text of subject-count\n' +
    'show "EVENTS-LENGTH=" + text of (count of current-world.events)\n' +
    'show "FACET-FIELD-COUNT=4"\n' +
    'show "SUBJECT-FIELD-COUNT=7"\n' +
    'show "WORLD-FIELD-COUNT=3"\n'
  );
}

function parseOnce(src) {
  const t0 = process.hrtime.bigint();
  parse(src);
  const t1 = process.hrtime.bigint();
  return Number(t1 - t0);
}

function calibrateRepeats(src, timerFn) {
  const sample = Math.max(1, timerFn(src));
  const k = Math.max(1, Math.ceil(TARGET_NS / sample));
  return Math.min(k, 5000);
}

function measureRepeated(src, timerFn, k) {
  const warmupK = Math.max(1, Math.ceil(k / 10));
  for (let i = 0; i < warmupK; i++) timerFn(src); // discarded
  const trialTotals = [];
  for (let t = 0; t < TRIALS; t++) {
    let total = 0;
    for (let i = 0; i < k; i++) total += timerFn(src);
    trialTotals.push(total);
  }
  return {
    k,
    trialTotalsNs: trialTotals,
    medianNsPerRun: median(trialTotals) / k,
    minNsPerRun: Math.min(...trialTotals) / k,
  };
}

function interpolate(x0, y0, x1, y1, x) {
  if (x1 === x0) return y0;
  return y0 + ((x - x0) / (x1 - x0)) * (y1 - y0);
}

// Phase 2 (build prompt §5): the same primitive, in the shape Horizon will
// actually produce. (a) parse+load and (c) the remainder are measured
// DIRECTLY, by timing benchmarks/world_shape.planes's own program
// (generated per S) through the ordinary `runProgram`/`parse` entry points.
// (b) with/plus copy cost is DERIVED from the with/plus arms already
// measured above -- never measured a second time inside this program's own
// timing, per §5(b) -- applied to the actual widths (facet=4, tested
// directly; subject=7, interpolated between the tested W=4/W=8 points;
// world=3, extrapolated below W=4 from the fitted line) and the actual
// events-list length trajectory this program produces (0..WORLD_T-1,
// averaged).
function runWorldPhase(withResults, withPerWidth, withDerived, plusDerived) {
  const facetUpdateNs = withResults["4"].rungs.rung3_multi.marginalMedianNsPerCall;
  const rung3At8 = withResults["8"].rungs.rung3_multi.marginalMedianNsPerCall;
  const subjectUpdateNs = interpolate(4, facetUpdateNs, 8, rung3At8, WORLD_SUBJECT_W);
  const costPerUpdateAt3 =
    withDerived.costPerUpdateNsIntercept + withDerived.costPerUpdateNsPerFieldSlope * WORLD_WORLD_W;
  const worldUpdateNs = costPerUpdateAt3 + 2 * withPerWidth[String(WORLD_FACET_W)].fieldWriteMarginalMedianNs;

  const avgEventsLength = (WORLD_T - 1) / 2;
  const plusCostNs = plusDerived.nsIntercept + plusDerived.nsPerElementSlope * avgEventsLength;

  const worldTimer = (s) => runOnce(s, "world-trial");

  const results = {};
  for (const s of WORLD_SUBJECT_COUNTS) {
    const src = buildWorldSrc(s);
    const k = calibrateRepeats(src, worldTimer);
    const total = measureRepeated(src, worldTimer, k);
    const parseTotal = measureRepeated(src, parseOnce, k);

    const totalNsPerRunMedian = total.medianNsPerRun;
    const parseNsPerRunMedian = parseTotal.medianNsPerRun;
    const execNsPerRunMedian = totalNsPerRunMedian - parseNsPerRunMedian;

    const aParsePerTick = parseNsPerRunMedian / WORLD_T;
    const execPerTick = execNsPerRunMedian / WORLD_T;
    const bCopyPerTick = s * (2 * facetUpdateNs + subjectUpdateNs) + worldUpdateNs + plusCostNs;
    const cRemainderPerTick = execPerTick - bCopyPerTick;

    results[String(s)] = {
      S: s,
      T: WORLD_T,
      k,
      totalNsPerRunMedian,
      totalNsPerRunMin: total.minNsPerRun,
      parseNsPerRunMedian,
      parseNsPerRunMin: parseTotal.minNsPerRun,
      aParseNsPerTick: aParsePerTick,
      bCopyNsPerTick: bCopyPerTick,
      cRemainderNsPerTick: cRemainderPerTick,
      totalNsPerTick: totalNsPerRunMedian / WORLD_T,
      facetUpdateNs,
      subjectUpdateNs,
      worldUpdateNs,
      plusCostNsAtAvgLength: plusCostNs,
      avgEventsLength,
    };
  }
  return results;
}

const RETENTION_S = 64;
const RETENTION_CHECKPOINTS = [1, 100, 300, 600];
const RETENTION_SOAK_SECONDS = 30 * 60;
const RETENTION_TICKS_PER_SECOND = 60;

// BFS over Deriv.inputs from `root` (a Deriv, not a Traced), counting
// UNIQUE reachable nodes by object identity. Reads only public fields
// (`.inputs`) -- never calls an interpreter method (build prompt §3's
// permitted exception for the retention arm).
function countReachableDerivs(root) {
  const seen = new Set();
  const stack = [root];
  while (stack.length) {
    const node = stack.pop();
    if (seen.has(node)) continue;
    seen.add(node);
    for (const inp of node.inputs) {
      if (!seen.has(inp)) stack.push(inp);
    }
  }
  return seen.size;
}

// Phase 3 (build prompt §6): reachable Deriv count and JS heap used at tick
// 1/100/300/600 for world_shape's shape at S=64. Four independent full runs
// (0..checkpoint-1 ticks each) through the ordinary Interpreter/`run` entry
// point -- deterministic and pure, so this gives the SAME final world value
// a single continuous 600-tick run would at each checkpoint. `global.gc()`
// (only available under `node --expose-gc`) forces a clean live-heap
// snapshot before each reading; without it, heapUsed is reported as-is.
function runRetentionPhase() {
  const results = {};
  for (const checkpoint of RETENTION_CHECKPOINTS) {
    const src = buildWorldSrcFor(RETENTION_S, checkpoint);
    const host = new BrowserHost({});
    const itp = new Interpreter({ host });
    itp.run(src);
    const tracedWorld = itp.env.get("current-world");
    const derivCount = countReachableDerivs(tracedWorld.node);
    if (typeof global.gc === "function") global.gc();
    const heapUsedBytes = process.memoryUsage().heapUsed;
    results[String(checkpoint)] = {
      checkpointTick: checkpoint,
      S: RETENTION_S,
      reachableDerivCount: derivCount,
      heapUsedBytes,
      gcForced: typeof global.gc === "function",
    };
  }

  // Mirrors measure_update_cost.py: growth relative to the tick=1 checkpoint,
  // not absolute bytes -- this phase runs last, after the with/plus/
  // cumulative/world phases have already allocated (and mostly, but perhaps
  // not entirely, freed) memory of their own. heapUsed after a forced GC is
  // much less contaminated than Python's high-water-mark ru_maxrss, but the
  // same baseline-subtraction is applied for a like-for-like methodology.
  const ticks = RETENTION_CHECKPOINTS.map((c) => results[String(c)].checkpointTick);
  const derivs = RETENTION_CHECKPOINTS.map((c) => results[String(c)].reachableDerivCount);
  const heap = RETENTION_CHECKPOINTS.map((c) => results[String(c)].heapUsedBytes);
  const heapBaseline = heap[0];
  const heapGrowth = heap.map((v) => v - heapBaseline);
  const derivFit = linearFit(ticks, derivs);
  const heapFit = linearFit(ticks, heapGrowth);

  const soakTicks = RETENTION_SOAK_SECONDS * RETENTION_TICKS_PER_SECOND;
  const extrapolatedHeapGrowthBytes = heapFit.intercept + heapFit.slope * soakTicks;
  const extrapolatedDerivs = derivFit.intercept + derivFit.slope * soakTicks;

  return {
    S: RETENTION_S,
    checkpoints: RETENTION_CHECKPOINTS,
    results,
    heapBaselineBytes: heapBaseline,
    heapGrowthBytes: heapGrowth,
    derivCountPerTickSlope: derivFit.slope,
    heapGrowthBytesPerTickSlope: heapFit.slope,
    soakSeconds: RETENTION_SOAK_SECONDS,
    soakTicksPerSecond: RETENTION_TICKS_PER_SECOND,
    soakTicks,
    extrapolatedHeapGrowthBytes,
    extrapolatedDerivCount: extrapolatedDerivs,
    note: "heapUsed is read after a forced GC (node --expose-gc) but still may "
      + "carry residue from earlier phases in this run; growth is measured "
      + "relative to the tick=1 checkpoint, not in absolute bytes. "
      + "Extrapolation is from a 4-point linear fit over ticks 1..600; not "
      + "measured directly.",
  };
}

function median(xs) {
  const s = [...xs].sort((a, b) => a - b);
  const n = s.length;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

function runOnce(src, label) {
  const t0 = process.hrtime.bigint();
  const r = runProgram(src, {});
  const t1 = process.hrtime.bigint();
  if (r.error) throw new Error(`${label}: ${r.error.tag}: ${r.error.message}`);
  return Number(t1 - t0);
}

function calibrate(buildSrcFn) {
  let L = 10;
  let elapsedNs = 0;
  for (let step = 0; step < MAX_CALIBRATION_STEPS; step++) {
    const src = buildSrcFn(L);
    elapsedNs = runOnce(src, "calibrate");
    if (elapsedNs >= TARGET_NS || L >= MAX_L) return { L, calibrationNs: elapsedNs };
    const scale = Math.sqrt(TARGET_NS / Math.max(elapsedNs, 1));
    L = Math.min(MAX_L, Math.max(L + 1, Math.ceil(L * scale * 1.15)));
  }
  return { L, calibrationNs: elapsedNs };
}

function measure(buildSrcFn, L) {
  const N = L * L;
  const warmupN = Math.max(1000, Math.ceil(0.1 * N));
  const warmupL = Math.max(1, Math.ceil(Math.sqrt(warmupN)));
  runOnce(buildSrcFn(warmupL), "warmup"); // discarded

  const src = buildSrcFn(L);
  const trialsNs = [];
  for (let t = 0; t < TRIALS; t++) trialsNs.push(runOnce(src, "trial"));
  return {
    L,
    N,
    trialsNs,
    medianNs: median(trialsNs),
    minNs: Math.min(...trialsNs),
  };
}

// Least-squares slope/intercept — used to state the fitted ns/field (with
// arm) and ns/element (plus arm) slope, per Criterion C (build prompt §1):
// with cost is expected to scale linearly in record field count, plus cost
// linearly in list length.
function linearFit(xs, ys) {
  const n = xs.length;
  const meanX = xs.reduce((a, b) => a + b, 0) / n;
  const meanY = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (xs[i] - meanX) * (ys[i] - meanY);
    den += (xs[i] - meanX) ** 2;
  }
  const slope = den ? num / den : 0;
  const intercept = meanY - slope * meanX;
  return { slope, intercept };
}

function runWithArm() {
  const results = {};
  for (const width of WITH_WIDTHS) {
    const controlFn = (l) => buildWithSrc(null, width, l);
    const rung3Fn = (l) => buildWithSrc("rung3_multi", width, l);
    const { L: iterLControl } = calibrate(controlFn);
    const { L: iterLRung } = calibrate(rung3Fn);
    const iterL = Math.min(iterLControl, iterLRung);

    const controlResult = measure(controlFn, iterL);
    const widthResult = {
      L: iterL,
      N: controlResult.N,
      controlMedianNs: controlResult.medianNs,
      controlMinNs: controlResult.minNs,
      controlTrialsNs: controlResult.trialsNs,
      rungs: {},
    };
    for (const rungName of WITH_RUNG_NAMES) {
      const rungFn = (l) => buildWithSrc(rungName, width, l);
      const rungResult = measure(rungFn, iterL);
      const marginalMedian = rungResult.medianNs - controlResult.medianNs;
      const marginalMin = rungResult.minNs - controlResult.minNs;
      widthResult.rungs[rungName] = {
        label: WITH_RUNG_LABELS[rungName],
        rungMedianNs: rungResult.medianNs,
        rungMinNs: rungResult.minNs,
        rungTrialsNs: rungResult.trialsNs,
        marginalMedianNsPerCall: marginalMedian / rungResult.N,
        marginalMinNsPerCall: marginalMin / rungResult.N,
      };
    }
    results[String(width)] = widthResult;
  }

  const med = (width, rung) => results[String(width)].rungs[rung].marginalMedianNsPerCall;
  const mn = (width, rung) => results[String(width)].rungs[rung].marginalMinNsPerCall;

  const perWidth = {};
  for (const width of WITH_WIDTHS) {
    perWidth[String(width)] = {
      fieldWriteMarginalMedianNs: med(width, "rung3_multi") - med(width, "rung1_single"),
      fieldWriteMarginalMinNs: mn(width, "rung3_multi") - mn(width, "rung1_single"),
      secondCopyMarginalMedianNs: med(width, "rung2_chained") - med(width, "rung3_multi"),
      secondCopyMarginalMinNs: mn(width, "rung2_chained") - mn(width, "rung3_multi"),
      costPerUpdateMedianNs: med(width, "rung1_single"),
      costPerUpdateMinNs: mn(width, "rung1_single"),
    };
  }

  const isolatedCopyYs = WITH_WIDTHS.map((w) => perWidth[String(w)].secondCopyMarginalMedianNs);
  const isolated = linearFit(WITH_WIDTHS, isolatedCopyYs);
  const updateYs = WITH_WIDTHS.map((w) => perWidth[String(w)].costPerUpdateMedianNs);
  const update = linearFit(WITH_WIDTHS, updateYs);

  const derived = {
    isolatedCopyNsPerFieldSlope: isolated.slope,
    isolatedCopyNsIntercept: isolated.intercept,
    costPerUpdateNsPerFieldSlope: update.slope,
    costPerUpdateNsIntercept: update.intercept,
  };
  return { results, perWidth, derived };
}

function runPlusArm() {
  const results = {};
  for (const length of PLUS_LENGTHS) {
    const controlFn = (l) => buildPlusSrc(null, length, l);
    const rungFn = (l) => buildPlusSrc(PLUS_RUNG_NAME, length, l);
    const { L: iterLControl } = calibrate(controlFn);
    const { L: iterLRung } = calibrate(rungFn);
    const iterL = Math.min(iterLControl, iterLRung);

    const controlResult = measure(controlFn, iterL);
    const rungResult = measure(rungFn, iterL);
    const marginalMedian = rungResult.medianNs - controlResult.medianNs;
    const marginalMin = rungResult.minNs - controlResult.minNs;
    results[String(length)] = {
      label: PLUS_RUNG_LABEL,
      L: iterL,
      N: rungResult.N,
      controlMedianNs: controlResult.medianNs,
      controlMinNs: controlResult.minNs,
      controlTrialsNs: controlResult.trialsNs,
      rungMedianNs: rungResult.medianNs,
      rungMinNs: rungResult.minNs,
      rungTrialsNs: rungResult.trialsNs,
      marginalMedianNsPerCall: marginalMedian / rungResult.N,
      marginalMinNsPerCall: marginalMin / rungResult.N,
    };
  }

  const ys = PLUS_LENGTHS.map((l) => results[String(l)].marginalMedianNsPerCall);
  const { slope, intercept } = linearFit(PLUS_LENGTHS, ys);
  return { results, derived: { nsPerElementSlope: slope, nsIntercept: intercept } };
}

function runCumulative() {
  const src = buildCumulativeSrc();
  runOnce(src, "cumulative-warmup"); // discarded
  const trialsNs = [];
  for (let t = 0; t < TRIALS; t++) trialsNs.push(runOnce(src, "cumulative-trial"));
  const totalMedian = median(trialsNs);
  const totalMin = Math.min(...trialsNs);
  // L*(L-1)/2 total element-copies across the whole grow-to-L run (the i-th
  // append copies i existing elements): O(L^2)/2, so k = total / (L*(L-1)/2)
  // is the implied per-copied-element constant.
  const pairs = (CUMULATIVE_L * (CUMULATIVE_L - 1)) / 2;
  const kMedian = totalMedian / pairs;
  const kMin = totalMin / pairs;
  const extrapolatedMedianNs = (kMedian * EXTRAPOLATE_TO * (EXTRAPOLATE_TO - 1)) / 2;
  const extrapolatedMinNs = (kMin * EXTRAPOLATE_TO * (EXTRAPOLATE_TO - 1)) / 2;
  return {
    L: CUMULATIVE_L,
    trialsNs,
    totalMedianNs: totalMedian,
    totalMinNs: totalMin,
    impliedNsPerCopiedElementMedian: kMedian,
    impliedNsPerCopiedElementMin: kMin,
    extrapolateToEvents: EXTRAPOLATE_TO,
    extrapolatedTotalMedianNs: extrapolatedMedianNs,
    extrapolatedTotalMinNs: extrapolatedMinNs,
    note: "extrapolation from the fitted O(L^2) constant; not measured directly",
  };
}

// Mirrors measure_update_cost.py's run_retention_subprocess: re-invokes this
// script's own --retention-only mode as a fresh `node --expose-gc` process,
// so the heap reading reflects only the retention phase's footprint, not
// whatever the with/plus/cumulative/world phases already allocated.
function runRetentionSubprocess() {
  const result = spawnSync(
    process.execPath,
    ["--expose-gc", fileURLToPath(import.meta.url), "--retention-only", "--json"],
    { encoding: "utf8" },
  );
  if (result.status !== 0) {
    throw new Error(`retention subprocess failed: ${result.stderr}`);
  }
  return JSON.parse(result.stdout).retention;
}

function main() {
  const jsonMode = process.argv.includes("--json");

  if (process.argv.includes("--retention-only")) {
    console.log(JSON.stringify({ retention: runRetentionPhase() }));
    return;
  }

  const machine = {
    implementation: "js",
    nodeVersion: process.version,
    platform: `${os.type()} ${os.release()} ${os.arch()}`,
    cpu: os.cpus()?.[0]?.model ?? "unknown",
  };

  const { results: withResults, perWidth: withPerWidth, derived: withDerived } = runWithArm();
  const { results: plusResults, derived: plusDerived } = runPlusArm();
  const cumulative = runCumulative();
  const worldResults = runWorldPhase(withResults, withPerWidth, withDerived, plusDerived);
  // See run_retention_subprocess in measure_update_cost.py for why this is
  // isolated: an in-process reading (even with a forced GC) still showed
  // residue from the with/plus/cumulative/world phases above.
  const retention = runRetentionSubprocess();

  const output = {
    machine,
    trials: TRIALS,
    targetMs: TARGET_NS / 1e6,
    with: {
      widths: WITH_WIDTHS,
      rungNames: WITH_RUNG_NAMES,
      results: withResults,
      perWidth: withPerWidth,
      derived: withDerived,
    },
    plus: {
      lengths: PLUS_LENGTHS,
      rungName: PLUS_RUNG_NAME,
      results: plusResults,
      derived: plusDerived,
    },
    cumulative,
    world: {
      subjectCounts: WORLD_SUBJECT_COUNTS,
      ticks: WORLD_T,
      facetW: WORLD_FACET_W,
      subjectW: WORLD_SUBJECT_W,
      worldW: WORLD_WORLD_W,
      results: worldResults,
    },
    retention,
  };

  if (jsonMode) {
    console.log(JSON.stringify(output));
    return;
  }

  console.log("# The update-cost ladder — JavaScript (Node)");
  console.log(`NODE_VERSION=${machine.nodeVersion}`);
  console.log(`PLATFORM=${machine.platform}`);
  console.log(`CPU=${machine.cpu}`);
  console.log(`TRIALS=${TRIALS}`);
  console.log(`TARGET_MS=${TARGET_NS / 1e6}`);
  console.log("--- with arm ---");
  for (const width of WITH_WIDTHS) {
    const w = withResults[String(width)];
    console.log(`W=${width} L=${w.L} N=${w.N} CONTROL_MEDIAN_NS=${w.controlMedianNs.toFixed(1)}`);
    for (const rungName of WITH_RUNG_NAMES) {
      const r = w.rungs[rungName];
      console.log(
        `  ${rungName}: MARGINAL_MEDIAN_NS_PER_CALL=${r.marginalMedianNsPerCall.toFixed(2)} MARGINAL_MIN_NS_PER_CALL=${r.marginalMinNsPerCall.toFixed(2)}`,
      );
    }
    const pw = withPerWidth[String(width)];
    console.log(
      `  fieldWriteMarginalMedianNs=${pw.fieldWriteMarginalMedianNs.toFixed(2)} secondCopyMarginalMedianNs=${pw.secondCopyMarginalMedianNs.toFixed(2)}`,
    );
  }
  console.log(`isolatedCopyNsPerFieldSlope=${withDerived.isolatedCopyNsPerFieldSlope.toFixed(3)}`);
  console.log(`costPerUpdateNsPerFieldSlope=${withDerived.costPerUpdateNsPerFieldSlope.toFixed(3)}`);
  console.log("--- plus arm ---");
  for (const length of PLUS_LENGTHS) {
    const p = plusResults[String(length)];
    console.log(
      `L=${length} iterL=${p.L} N=${p.N} MARGINAL_MEDIAN_NS_PER_CALL=${p.marginalMedianNsPerCall.toFixed(2)} MARGINAL_MIN_NS_PER_CALL=${p.marginalMinNsPerCall.toFixed(2)}`,
    );
  }
  console.log(`nsPerElementSlope=${plusDerived.nsPerElementSlope.toFixed(4)}`);
  console.log("--- cumulative ---");
  console.log(
    `L=${cumulative.L} TOTAL_MEDIAN_NS=${cumulative.totalMedianNs.toFixed(0)} TOTAL_MIN_NS=${cumulative.totalMinNs.toFixed(0)}`,
  );
  console.log(`impliedNsPerCopiedElementMedian=${cumulative.impliedNsPerCopiedElementMedian.toFixed(4)}`);
  console.log(
    `EXTRAPOLATED to ${EXTRAPOLATE_TO}: ${(cumulative.extrapolatedTotalMedianNs / 1e6).toFixed(1)}ms (median-derived, EXTRAPOLATION)`,
  );
  console.log("--- world (benchmarks/world_shape.planes shape) ---");
  for (const s of WORLD_SUBJECT_COUNTS) {
    const w = worldResults[String(s)];
    console.log(
      `S=${s} T=${w.T} k=${w.k} TOTAL_NS_PER_TICK=${w.totalNsPerTick.toFixed(0)} ` +
        `a_parse=${w.aParseNsPerTick.toFixed(0)} b_copy=${w.bCopyNsPerTick.toFixed(0)} ` +
        `c_remainder=${w.cRemainderNsPerTick.toFixed(0)}`,
    );
  }
  console.log("--- retention (S=64, derivation graph reachable from `current-world`) ---");
  for (const c of RETENTION_CHECKPOINTS) {
    const r = retention.results[String(c)];
    console.log(
      `TICK=${c} REACHABLE_DERIVS=${r.reachableDerivCount} HEAP_USED_BYTES=${r.heapUsedBytes} GC_FORCED=${r.gcForced}`,
    );
  }
  console.log(`derivCountSlopePerTick=${retention.derivCountPerTickSlope.toFixed(2)}`);
  console.log(`heapGrowthBytesSlopePerTick=${retention.heapGrowthBytesPerTickSlope.toFixed(1)}`);
  console.log(
    `EXTRAPOLATED ${(retention.soakSeconds / 60).toFixed(0)}min soak @ ${retention.soakTicksPerSecond}tick/s = ` +
      `${retention.soakTicks} ticks: ${(retention.extrapolatedHeapGrowthBytes / 1e6).toFixed(1)}MB heap growth, ` +
      `${retention.extrapolatedDerivCount.toFixed(0)} derivs (EXTRAPOLATION)`,
  );
}

main();
