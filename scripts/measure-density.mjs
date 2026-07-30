// scripts/measure-density.mjs — how many draw commands fit in a frame.
//
// THIS IS A MEASUREMENT, NOT A GATE. It never exits non-zero on a slow
// machine and nothing in ci.sh calls it. Its one output is a number —
// SCENE_BUDGET, the command count paint/garden.planes is allowed to spend —
// and that number is a fact about this machine, recorded in
// benchmarks/density.md so a later reader can see what the scene was sized
// against rather than guessing.
//
// WHAT IS TIMED. One tick, end to end, the way a page actually pays for it:
// compose the prelude, parse the whole module graph, run it, collect the
// output lines. Not "the interpreter's inner loop" — parsing is per-tick in
// both hosts (js/browser_main.mjs's runProgramGraph re-parses every source
// each call; interp.py's run_file does the same), so a measurement that
// skipped it would flatter the numbers by exactly the part a scrubber drag
// pays twice.
//
// The generated program is shaped like the garden, not like a benchmark: the
// same recursive emit-one-mark-per-index spine, the same per-mark mix of
// `mod`, `sine`, `cosine`, division and multiplication, and the same two
// commands per index (a `fill` then an `ellipse`). A tight loop of bare
// `circle` calls would measure string concatenation and report a budget the
// real scene could never hit.
//
// Usage:
//   node scripts/measure-density.mjs                    # both hosts
//   node scripts/measure-density.mjs --js               # JavaScript only
//   node scripts/measure-density.mjs --densities 50,200 # a shorter sweep

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import { performance } from "node:perf_hooks";

import { Interpreter } from "../js/interp.mjs";
import { TestHost } from "../js/host.mjs";
import { runFile } from "../js/run_file.mjs";
import { setVocabulary, setAmberTemplates } from "../js/grammar_data.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..");

setVocabulary(JSON.parse(fs.readFileSync(path.join(REPO, "grammar/vocabulary.json"), "utf-8")));
setAmberTemplates(JSON.parse(fs.readFileSync(path.join(REPO, "grammar/messages/amber.json"), "utf-8")));

// The frame budget: 60 frames a second is 16.7ms, but a tick is not the only
// thing a frame pays for (the painter walks the stream, the canvas composites,
// the browser lays out). 60ms is the number this build sizes against — the
// point past which a scrubber drag stops feeling like a drag and starts
// feeling like a series of jumps.
const FRAME_BUDGET_MS = 60;

const DEFAULT_DENSITIES = [50, 200, 500, 1000];

// One mark = one `fill` line and one `ellipse` line, exactly as
// paint/garden.planes spends them.
const COMMANDS_PER_MARK = 2;

// Marks per recursive family. The garden is not one recursion a thousand
// deep — it is a dozen families (stars, clouds, plants, blades, bees) each a
// few dozen deep, and the difference is not cosmetic: interp.py refuses a
// single spine past roughly two hundred frames with `recursion-too-deep`
// while js/interp.mjs runs on (the 32-vs-201 gap S8 measured). A probe built
// as one long chain would measure that refusal instead of the tick cost.
const MARKS_PER_FAMILY = 25;

function programFor(markCount, tick = 60, seed = 481027) {
  const families = Math.max(1, Math.ceil(markCount / MARKS_PER_FAMILY));
  const perFamily = Math.ceil(markCount / families);
  return `${prelude(tick, seed)}
use draw
use math

show "draw protocol 2"

to spread of n:
  let big = mod of (n * 2654435761 + 12345), 10007
  give big / 10007

to mark of index, total, band:
  if index >= total:
    give nothing
  else:
    let n = band * ${perFamily} + index
    let a = mod of (tick * 2.4 + n * 83), 360
    let wobble = (spread of (n * 7)) * 0.8
    let x = 34 + (spread of n) * 412 + (cosine of a) * 26
    let y = 30 + wobble * 280 + (sine of (a * 2)) * 9
    let l = 0.28 + wobble * 0.5
    let hue = mod of (28 + n * 37), 360
    fill of l, 0.11, hue, 0.94
    ellipse of x, y, (2 + wobble * 4), (1.4 + wobble * 2), a
    mark of (index + 1), total, band

to family of index, total:
  if index >= total:
    give nothing
  else:
    mark of 0, ${perFamily}, index
    family of (index + 1), total

family of 0, ${families}
`;
}

// A prelude with the same five bindings js/paint/loop.mjs's composePrelude
// renders, so the timed program is the same program a page runs.
function prelude(tick, seed) {
  return `let tick = ${tick}\nlet keys = []\nlet pointer = { x: 0, y: 0, down: false }\nlet state = nothing\nlet seed = ${seed}\n`;
}

function median(xs) {
  const s = [...xs].sort((a, b) => a - b);
  const mid = s.length >> 1;
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

// The probe lives inside paint/ so `use draw` and `use math` resolve the same
// way garden.planes's own do — a module path resolves relative to the
// importing file's directory (js/module_loader_node.mjs). Removed in a
// `finally`, always.
const PROBE = path.join(REPO, "paint", "_density_probe.planes");

// More warmups than the Python side gets, and deliberately: V8 needs several
// passes before the interpreter's hot paths are compiled, and a two-run
// warmup left the 50-command row measuring slower than the 200-command one.
async function timeJs(markCount, { warmups = 6, runs = 7 } = {}) {
  const samples = [];
  let drawLines = 0;
  for (let i = 0; i < warmups + runs; i++) {
    const started = performance.now();
    const itp = new Interpreter({ host: new TestHost({}) });
    await runFile(itp, PROBE);
    const elapsed = performance.now() - started;
    drawLines = itp.output.filter((l) => l.startsWith("draw ")).length;
    if (i >= warmups) samples.push(elapsed);
  }
  return { ms: median(samples), drawLines };
}

const PY_DRIVER = `
import sys, time, statistics
sys.path.insert(0, ${JSON.stringify(REPO)})
from interp import Interpreter
from host import TestHost

probe = ${JSON.stringify(PROBE)}
warmups, runs = 2, 5
samples = []
draw_lines = 0
try:
    for i in range(warmups + runs):
        started = time.perf_counter()
        itp = Interpreter(host=TestHost())
        itp.run_file(probe)
        elapsed = (time.perf_counter() - started) * 1000
        draw_lines = sum(1 for l in itp.output if l.startswith("draw "))
        if i >= warmups:
            samples.append(elapsed)
except RecursionError:
    print("refused recursion-too-deep")
    raise SystemExit(0)
except Exception as e:
    print("refused %s" % (getattr(e, "tag", type(e).__name__),))
    raise SystemExit(0)
print("%.3f %d" % (statistics.median(samples), draw_lines))
`;

// A refusal is a result, not a crash: interp.py can decline a density
// outright (`recursion-too-deep`) where js/interp.mjs runs it, and that
// asymmetry is exactly the kind of thing a measurement exists to surface.
function timePython() {
  const out = execFileSync("python3", ["-c", PY_DRIVER], { cwd: REPO, encoding: "utf-8" });
  const parts = out.trim().split(/\s+/);
  if (parts[0] === "refused") return { ms: Infinity, refused: parts.slice(1).join(" ") };
  return { ms: Number(parts[0]), drawLines: Number(parts[1]), refused: null };
}

// The largest density whose measured tick stays under the frame budget,
// interpolated between the two densities that straddle it — reported as a
// command count, which is what SCENE_BUDGET is denominated in. Returns 0 when
// even the smallest density measured is already over.
function budgetFrom(rows, key) {
  let under = null;
  let over = null;
  for (const row of rows) {
    if (row[key] <= FRAME_BUDGET_MS) under = row;
    else if (over === null) over = row;
  }
  if (under === null) return 0;
  if (over === null) return under.commands; // everything measured fits
  const span = over.commands - under.commands;
  const rise = over[key] - under[key];
  if (rise <= 0) return under.commands;
  const extra = ((FRAME_BUDGET_MS - under[key]) / rise) * span;
  return Math.floor(under.commands + extra);
}

async function main() {
  const argv = process.argv.slice(2);
  const jsOnly = argv.includes("--js");
  const dIndex = argv.indexOf("--densities");
  const densities =
    dIndex !== -1 && argv[dIndex + 1]
      ? argv[dIndex + 1].split(",").map((s) => Number(s.trim()))
      : DEFAULT_DENSITIES;

  const rows = [];
  try {
    for (const commands of densities) {
      const marks = Math.round(commands / COMMANDS_PER_MARK);
      fs.writeFileSync(PROBE, programFor(marks), "utf-8");
      const js = await timeJs(marks, {});
      const py = jsOnly ? { ms: NaN, refused: null } : timePython();
      rows.push({ commands: js.drawLines, js: js.ms, py: py.ms, pyRefused: py.refused });
      const pyText = py.refused
        ? `refused (${py.refused})`
        : Number.isNaN(py.ms)
          ? "—"
          : `${py.ms.toFixed(1)}ms`;
      process.stdout.write(
        `${String(js.drawLines).padStart(5)} commands   js ${js.ms.toFixed(1).padStart(7)}ms   py ${pyText.padStart(9)}\n`,
      );
    }
  } finally {
    if (fs.existsSync(PROBE)) fs.unlinkSync(PROBE);
  }

  const jsBudget = budgetFrom(rows, "js");
  const pyBudget = jsOnly ? null : budgetFrom(rows, "py");
  process.stdout.write(`\nunder ${FRAME_BUDGET_MS}ms per tick:\n`);
  process.stdout.write(`  javascript  ${jsBudget} commands\n`);
  if (pyBudget !== null) process.stdout.write(`  python      ${pyBudget} commands\n`);
  // SCENE_BUDGET is the JAVASCRIPT number, not the smaller of the two. The
  // garden is drawn by a browser; interp.py has no canvas and never renders
  // a frame of it. The Python column is reported because the same program
  // has to remain runnable there — it is a correctness fact, not a frame
  // budget, and sizing the picture to it would spend a real limit on a host
  // that never draws.
  process.stdout.write(`\nSCENE_BUDGET (the host that draws the scene): ${jsBudget}\n`);
}

main();
