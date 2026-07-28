#!/usr/bin/env node
// scripts/measure_call_cost.mjs — the ladder, JavaScript implementation.
//
// Decomposes the cost of one interpreted Planes-level call by subtraction:
// each rung is a tiny program that adds ONE thing to an otherwise-identical
// call, run inside a loop, timed as a whole, with an empty-loop control
// subtracted to isolate what that one rung adds. It changes nothing it
// measures: every rung and the control run through the ordinary
// `runProgram` entry point (js/browser_main.mjs) exactly as any program
// does; nothing here reaches into the interpreter.
//
// WHY A NESTED for-each LOOP, NOT RECURSION. Planes recursion has a ceiling
// around ~140-200 levels deep (scripts/measure_frames_per_call.py measures
// it directly) — far short of the hundreds of thousands to millions of
// iterations a 200ms floor needs at sub-microsecond per-call costs. `for
// each` (interp.py's eval_foreach) iterates with a native host-language
// loop, not a Planes-level call, so it never touches that ceiling. A single
// flat list of that many elements would also mean a source-text literal of
// several megabytes — parsed every trial, which would swamp the very thing
// being measured. Nesting two `for each` loops over the SAME modest list
// (length L, N = L*L total iterations) keeps the source text small (a few
// KB) while N scales quadratically with L, and the nesting's own overhead
// (one extra Env per level, per interp.py's `inner = Env(env)`) is identical
// between a rung and its control, so it cancels in the subtraction exactly
// like the loop overhead does.
//
// Timer: process.hrtime.bigint() — NOT performance.now(), which is
// deliberately coarsened in Node and would sit at or above the 5us signal
// this ladder is trying to resolve.
//
// Per rung: calibrate L so ONE run takes >= 200ms, run one further untimed
// warm-up pass sized to max(10% of N, 1000) iterations (discarding JIT
// warm-up from the figure), then run 7 timed trials at the calibrated L.
// The empty-loop control is measured the SAME way, AT THE SAME L as the
// rung it will be subtracted from (not independently calibrated to its own
// 200ms floor) — see reports/REPORT_CALL_COST.md §1 for why that is the
// correct comparison. Median and minimum are reported across the 7 trials,
// not the mean (the honest and the clean signal, per the build's own
// convention — see scripts/measure_call_cost.py's docstring, which follows
// the same protocol).
//
// Usage: node scripts/measure_call_cost.mjs [--json] [--self-hosted]
// --self-hosted runs the same rungs through grammar/interp.planes,
// interpreted by interp.mjs, at a fixed (small) L — for the record only,
// clearly separated from the JS-native figures above it.

import os from "node:os";
import { runProgram } from "../js/browser_main.mjs";

const TRIALS = 7;
const TARGET_NS = 200_000_000; // 200ms floor, per §4.2
const MAX_L = 4000; // N = 16,000,000 at the cap; a safety bound, not expected to be hit
const MAX_CALIBRATION_STEPS = 25;

// Each rung adds ONE thing to the call the previous rung already has (§4 of
// the build prompt). `preamble` defines the target function (and, for the
// depth rungs, the outer-scope name it assigns); `callExpr` is what the loop
// body calls once per iteration. `null` callExpr is the empty-loop control.
const RUNGS = [
  {
    name: "control",
    label: "empty loop (no call)",
    preamble: "",
    callExpr: null,
  },
  {
    name: "rung1_noop",
    label: "rung 1 — noop, no args, empty body: isolates dispatch + environment allocation",
    preamble: "to noop:\n  give nothing\n",
    callExpr: "noop",
  },
  {
    name: "rung2_ident",
    label: "rung 2 — ident of x: give x: + parameter binding",
    preamble: "to ident of x:\n  give x\n",
    callExpr: "ident of 1",
  },
  {
    name: "rung3_add1",
    label: "rung 3 — add1 of x: give x + 1: + one rational op and its derivation record",
    preamble: "to add1 of x:\n  give x + 1\n",
    callExpr: "add1 of 1",
  },
  {
    name: "rung4_add3",
    label: "rung 4 — add3 of x: give x + 1 + 1 + 1: marginal cost of two more arithmetic ops, no extra call",
    preamble: "to add3 of x:\n  give x + 1 + 1 + 1\n",
    callExpr: "add3 of 1",
  },
  {
    name: "rung5_txt",
    label: "rung 5 — txt of x: give text of x: a derived value with no gcd",
    preamble: "to txt of x:\n  give text of x\n",
    callExpr: "txt of 1",
  },
  {
    name: "rung6_circle",
    label: "rung 6 — c of x, y, r: the draw.planes circle helper's body exactly",
    preamble:
      'to c of x, y, r:\n  show "draw circle " + text of x + " " + text of y + " " + text of r\n',
    callExpr: "c of 1, 2, 3",
  },
  {
    name: "rung7_depth1",
    label: "rung 7a — assignment to an outer-scope name, recursion depth 1",
    preamble: "outer = 0\nto recur of n:\n  if n <= 0:\n    outer = n\n    give 0\n  else:\n    give recur of (n - 1)\n",
    callExpr: "recur of 1",
  },
  {
    name: "rung7_depth8",
    label: "rung 7b — assignment to an outer-scope name, recursion depth 8",
    preamble: "outer = 0\nto recur of n:\n  if n <= 0:\n    outer = n\n    give 0\n  else:\n    give recur of (n - 1)\n",
    callExpr: "recur of 8",
  },
];

function buildList(n) {
  const parts = new Array(n);
  for (let i = 0; i < n; i++) parts[i] = i;
  return "[" + parts.join(", ") + "]";
}

function buildSrc(rung, L) {
  const listLit = buildList(L);
  const body = rung.callExpr ? `let ignored = ${rung.callExpr}` : "let ignored = j";
  return `${rung.preamble}let base = ${listLit}\nfor each i in base:\n  for each j in base:\n    ${body}\n`;
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

// Adaptive calibration: N = L*L, so cost scales roughly quadratically in L.
// Converges in a small number of steps from the observed elapsed time,
// rather than blind doubling.
function calibrate(rung) {
  let L = 10;
  let elapsedNs = 0;
  for (let step = 0; step < MAX_CALIBRATION_STEPS; step++) {
    const src = buildSrc(rung, L);
    elapsedNs = runOnce(src, rung.name);
    if (elapsedNs >= TARGET_NS || L >= MAX_L) return { L, calibrationNs: elapsedNs };
    const scale = Math.sqrt(TARGET_NS / Math.max(elapsedNs, 1));
    L = Math.min(MAX_L, Math.max(L + 1, Math.ceil(L * scale * 1.15)));
  }
  return { L, calibrationNs: elapsedNs };
}

function measure(rung, L) {
  const N = L * L;
  const warmupN = Math.max(1000, Math.ceil(0.1 * N));
  const warmupL = Math.max(1, Math.ceil(Math.sqrt(warmupN)));
  const warmupSrc = buildSrc(rung, warmupL);
  runOnce(warmupSrc, rung.name); // discarded — JIT warm-up only

  const src = buildSrc(rung, L);
  const trialsNs = [];
  for (let t = 0; t < TRIALS; t++) {
    trialsNs.push(runOnce(src, rung.name));
  }
  return {
    L,
    N,
    warmupL,
    warmupNActual: warmupL * warmupL,
    trialsNs,
    medianNs: median(trialsNs),
    minNs: Math.min(...trialsNs),
  };
}

function main() {
  const jsonMode = process.argv.includes("--json");
  const results = {};

  // The control is measured once per rung, AT THAT RUNG'S calibrated L —
  // not independently calibrated to its own 200ms floor. See the header
  // comment and REPORT_CALL_COST.md §1 for why this is the correct
  // comparison: N must be held constant across the subtraction.
  const controlRung = RUNGS[0];
  const targetRungs = RUNGS.slice(1);

  for (const rung of targetRungs) {
    const { L } = calibrate(rung);
    const rungResult = measure(rung, L);
    const controlResult = measure(controlRung, L);
    const marginalMedianNs = rungResult.medianNs - controlResult.medianNs;
    const marginalMinNs = rungResult.minNs - controlResult.minNs;
    results[rung.name] = {
      label: rung.label,
      L,
      N: rungResult.N,
      warmupNActual: rungResult.warmupNActual,
      rungTrialsNs: rungResult.trialsNs,
      controlTrialsNs: controlResult.trialsNs,
      rungMedianNs: rungResult.medianNs,
      rungMinNs: rungResult.minNs,
      controlMedianNs: controlResult.medianNs,
      controlMinNs: controlResult.minNs,
      marginalMedianNsPerCall: marginalMedianNs / rungResult.N,
      marginalMinNsPerCall: marginalMinNs / rungResult.N,
    };
  }

  // Derived, pairwise deltas (§4's "each delta names one cost") — computed
  // from the per-rung marginal-over-control figures already in hand.
  const derived = {
    // rung 4 minus rung 3: two more arithmetic ops, no extra call.
    arithmeticMarginalMedianNsPerOp:
      (results.rung4_add3.marginalMedianNsPerCall - results.rung3_add1.marginalMedianNsPerCall) / 2,
    arithmeticMarginalMinNsPerOp:
      (results.rung4_add3.marginalMinNsPerCall - results.rung3_add1.marginalMinNsPerCall) / 2,
    // rung 5 minus rung 3: a derived value with no gcd vs one rational op —
    // narrows (does not fully isolate) derivation-record allocation.
    derivedValueVsRationalOpMedianNs:
      results.rung5_txt.marginalMedianNsPerCall - results.rung3_add1.marginalMedianNsPerCall,
    derivedValueVsRationalOpMinNs:
      results.rung5_txt.marginalMinNsPerCall - results.rung3_add1.marginalMinNsPerCall,
    // depth 8 minus depth 1: the Env.set parent-chain walk, if any.
    depth8VsDepth1MedianNs:
      results.rung7_depth8.marginalMedianNsPerCall - results.rung7_depth1.marginalMedianNsPerCall,
    depth8VsDepth1MinNs: results.rung7_depth8.marginalMinNsPerCall - results.rung7_depth1.marginalMinNsPerCall,
  };

  const machine = {
    implementation: "js",
    nodeVersion: process.version,
    platform: `${os.type()} ${os.release()} ${os.arch()}`,
    cpu: os.cpus()?.[0]?.model ?? "unknown",
  };

  const output = { machine, trials: TRIALS, targetMs: TARGET_NS / 1e6, results, derived };

  if (jsonMode) {
    console.log(JSON.stringify(output));
    return;
  }

  console.log("# The ladder — JavaScript (Node)");
  console.log(`NODE_VERSION=${machine.nodeVersion}`);
  console.log(`PLATFORM=${machine.platform}`);
  console.log(`CPU=${machine.cpu}`);
  console.log(`TRIALS=${TRIALS}`);
  console.log(`TARGET_MS=${TARGET_NS / 1e6}`);
  for (const rung of targetRungs) {
    const r = results[rung.name];
    console.log(`--- ${rung.name} ---`);
    console.log(`LABEL=${r.label}`);
    console.log(`L=${r.L} N=${r.N} WARMUP_N=${r.warmupNActual}`);
    console.log(`RUNG_TRIALS_NS=${r.rungTrialsNs.join(",")}`);
    console.log(`CONTROL_TRIALS_NS=${r.controlTrialsNs.join(",")}`);
    console.log(`MARGINAL_MEDIAN_NS_PER_CALL=${r.marginalMedianNsPerCall.toFixed(2)}`);
    console.log(`MARGINAL_MIN_NS_PER_CALL=${r.marginalMinNsPerCall.toFixed(2)}`);
  }
  console.log("--- derived ---");
  for (const [k, v] of Object.entries(derived)) {
    console.log(`${k}=${v.toFixed(2)}`);
  }
}

main();
