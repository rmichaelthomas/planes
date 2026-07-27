## Post-Build Benchmarks — feat/module-loader-and-drawing-protocol-v1
**Date:** 2026-07-27
**Commit:** 00f7978 (Phase 6, branch head at benchmark time)

Same four cases as the pre-build report, run against the new pipeline:
`runProgramGraph`/`stepGraph` (module resolution ahead of parse) and the
rewritten 26-verb, OKLCH painter. A loader is warmed once per program before
measuring — matching paint.html's "one loader per run" rule — so these are
the steady-state per-tick cost once a run is underway, not the one-time
module-fetch cost (which happens once per run, not per tick, and is
separately asserted at exactly one fetch per module by
`js/test/paint_examples.test.mjs`).

### Test 1: turtle.planes — one runProgramGraph call, static, warm loader
**Input:** paint/turtle.planes, single call (50 samples), loader pre-warmed
**Result:** parse mean 0.1472ms / worst 0.2103ms; run mean 3.3676ms / worst 8.5122ms; paint mean 1.2073ms / worst 2.6127ms
**Time:** total mean 4.7221ms

### Test 2: bloom.planes — 120 ticks, warm loader reused across ticks
**Input:** paint/bloom.planes, 120 ticks
**Result:** per-tick parse mean 0.1224ms / worst 0.5230ms; step(run) mean 0.9349ms / worst 2.1497ms; paint mean 0.0351ms / worst 0.0907ms; total per-tick mean 1.0936ms / worst 2.3472ms
**Time:** 120 ticks in 131.24ms

### Test 3: snake.planes — 120 ticks, fixed synthetic key sequence, warm loader
**Input:** paint/snake.planes, 120 ticks, deterministic Right/Down/Left/Up cycling every 5 ticks
**Result:** per-tick parse mean 0.2714ms / worst 0.8249ms; step(run) mean 1.2149ms / worst 1.9936ms; paint mean 0.0268ms / worst 0.1485ms; total per-tick mean 1.5146ms / worst 2.3202ms
**Time:** 120 ticks in 181.75ms

### Test 4: draw-command throughput through parseCommand (26-verb table)
**Input:** 10000 commands cycling through all 26 verbs
**Result:** 2,126,830 commands/second
**Time:** 4.70ms for 10000 commands

## Diff against pre-build (e0c54f6)

| Case | Stage | Pre | Post | Δ |
|---|---|---:|---:|---:|
| 1 turtle (one-shot) | parse | 0.1556ms | 0.1472ms | −5% |
| 1 turtle | run | 2.9610ms | 3.3676ms | +14% |
| 1 turtle | paint | 0.4242ms | 1.2073ms | **+185%** |
| 2 bloom (per-tick) | parse | 0.1308ms | 0.1224ms | −6% |
| 2 bloom | **run** | 0.4928ms | 0.9349ms | **+90%** |
| 2 bloom | paint | 0.0214ms | 0.0351ms | +64% |
| 3 snake (per-tick) | parse | 0.2948ms | 0.2714ms | −8% |
| 3 snake | **run** | 0.4440ms | 1.2149ms | **+174%** |
| 3 snake | paint | 0.0118ms | 0.0268ms | +127% |
| 4 parseCommand | throughput | 2,264,344/s | 2,126,830/s | −6% |

**The per-tick `run` regressions on bloom and snake (and turtle's `paint`)
exceed 15% and are flagged as gate items per §12.1, with the reasoning below
for Rob's call.**

### Root cause

Two sources, both structural rather than accidental:

1. **Library calls replace inline string concatenation.** Phase 6 requires
   every program to call `circle of x, y, r` etc. instead of building
   `"draw circle " + text of x + ...` by hand — the entire point of
   `draw.planes`. A real function call (new `Env`, parameter binding, a
   recursive `exec_stmt`) costs more than one inline expression. turtle.planes
   additionally now emits ~4.5x more lines per run (2299 vs 513) because real
   `push`/`translate`/`rotate`/`pop` transform bookkeeping replaces what used
   to be pure coordinate arithmetic — more lines is more for `paint()` to
   walk, which is turtle's own +185%.
2. **The module graph is re-resolved and re-parsed every tick.** The entry
   source is deliberately live per frame (checkpoint v21.0 §249.4), so it
   cannot be cached — it may have changed. `draw.planes`/`math.planes` do not
   change within a run, and are now cached (see below), but the entry's own
   `parse`, the collision check, and hoisting still run fresh every tick.

### Mitigation already applied

Profiling found three real, fixable redundancies, all now fixed
(`js/modules.mjs`, `js/browser_main.mjs`):

- `hoistAndRun` computed `effective_names` twice per call (once via
  `names_in_graph`, once via `rename_map`) — each re-tokenizing every file in
  the graph. Now computed once.
- `runProgramGraph`/`analyseProgramGraph` called `uses_in(src)` twice on the
  same (large, per-tick-changing) entry text. Now called once.
- `renames_in`, `scan_names`, and `load_graph`'s own `uses_in` lookup are now
  cached by source text (pure functions of the string alone — a text change
  is a different cache key, never a stale hit), and `parse` results are
  cached per loader by `(source, known-set)` when a loader opts in via an
  `astCache` (`module_loader_browser.mjs`; `module_loader_node.mjs`'s
  one-shot CLI use does not need it and does not get it).

Together these cut bloom's per-tick `run` cost from an initial unoptimized
~3.5ms down to ~0.93ms — roughly an 80% reduction in the module-system
overhead — before hitting the floor of what the library-call architecture
itself costs.

### Why this is still within budget

The absolute numbers, not just the relative ones: bloom's worst per-tick
`run` sample is 2.15ms, snake's 1.99ms — against a 16.67ms budget at 60fps,
each ticking program uses well under 15% of one frame even at its worst
sample, with the rest of the pipeline (parse + paint) adding only a few more
tenths of a millisecond. This matches what the live browser check showed
(playwright-cli, §12.3-adjacent spot check during Phase 6): bloom animates
smoothly, snake responds to arrow keys with no perceptible lag.

### The verdict this leaves to Rob

The remaining regression cannot be closed further without either (a) touching
`interp.mjs`'s call mechanism — outside this build's stated scope — or
(b) abandoning the library-call architecture Phase 6 explicitly requires.
Flagged per §12.1's own clause: **blocking unless explicitly accepted.**
