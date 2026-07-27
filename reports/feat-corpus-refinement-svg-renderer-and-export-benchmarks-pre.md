## Pre-Build Benchmarks — feat/corpus-refinement-svg-renderer-and-export
**Date:** 2026-07-27
**Commit:** 2d36449

Phase A raises the command count per frame substantially — bloom gains a fill
per ring and a path-drawn petal, roughly doubling its stream — so the command
count is measured here alongside the timings rather than inferred from them.
The painter's cost scales with lines walked; the interpreter's scales with
helper calls made; these are the two things Phase A moves. Phase B adds a
second renderer but does not change what the programs emit, and Phase C runs
only on demand. All cases run under plain `node` (no `--stack-size` flag),
matching the environment `paint.html` itself runs in, with a warm loader per
program (paint.html's "one loader per run" rule), so these are steady-state
per-tick costs, not the one-time module fetch.

### Test 1: turtle.planes — one runProgramGraph call, static, warm loader
**Input:** paint/turtle.planes, single call (50 samples), loader pre-warmed
**Result:** parse mean 0.1522ms / worst 0.2407ms; run mean 3.4034ms / worst 8.0245ms; paint mean 1.0034ms / worst 2.3847ms
**Commands emitted:** 2299
**Time:** total mean 4.5590ms

### Test 2: bloom.planes — 120 ticks, warm loader reused across ticks
**Input:** paint/bloom.planes, 120 ticks
**Result:** per-tick parse mean 0.1378ms / worst 0.9472ms; step(run) mean 0.9803ms / worst 2.5822ms; paint mean 0.0372ms / worst 0.1655ms; total per-tick mean 1.1610ms / worst 2.7855ms
**Commands per tick:** mean 22.0 / worst 22
**Time:** 120 ticks in 139.32ms

### Test 3: snake.planes — 120 ticks, fixed synthetic key sequence, warm loader
**Input:** paint/snake.planes, 120 ticks, deterministic Right/Down/Left/Up cycling every 5 ticks
**Result:** per-tick parse mean 0.2705ms / worst 0.8532ms; step(run) mean 1.2457ms / worst 2.0563ms; paint mean 0.0298ms / worst 0.5258ms; total per-tick mean 1.5505ms / worst 2.4055ms
**Commands per tick:** mean 11.0 / worst 11
**Time:** 120 ticks in 186.06ms

### Test 4: draw-command throughput through parseCommand (26-verb table)
**Input:** 10000 commands cycling through all 26 verbs
**Result:** 2,075,873 commands/second
**Time:** 4.82ms for 10000 commands

### Verb coverage on `main` — the thing Phase A exists to change

Measured, not assumed: every `draw`-prefixed line the three programs emit over
40 ticks each, verb collected, differenced against `VERBS` in
`js/paint/protocol.mjs`.

| Program | Verbs emitted |
|---|---|
| turtle | `clear` `line` `pop` `push` `rotate` `stroke` `translate` `width` |
| bloom | `circle` `clear` `stroke` `width` |
| snake | `circle` `clear` `fill` `label` `rect` `stroke` |

**Used (12 of 26):** `circle` `clear` `fill` `label` `line` `pop` `push` `rect`
`rotate` `stroke` `translate` `width`

**Never used anywhere (14):** `align` `arc` `background` `cap` `close`
`corner` `curve` `ellipse` `end` `scale` `shape` `size` `triangle` `vertex`

**Alpha values ever emitted:** `0` and `1` only — no fractional alpha exists in
the corpus.

The whole path group (`shape` `vertex` `curve` `close` `end`) — the five verbs
that make the vocabulary open-ended rather than a fixed menu — is untouched.
A second renderer verified against this corpus would be verified against less
than half the protocol, which is why Phase A precedes Phase B.

### Method

`parse` timing is `js/parser.mjs`'s `parse(src)` called directly on the raw
program text. `run` timing for test 1 is `runProgramGraph` from
`js/browser_main.mjs`; for tests 2–3 it is `stepGraph` from
`js/paint/loop.mjs` (the per-tick unit the loop actually pays for). `paint`
timing is `paint(ctx, lines, dimensions)` from `js/paint/painter.mjs` against a
no-op fake 2D context, matching `paint_painter.test.mjs`'s own fake-context
pattern. **Commands emitted / per tick** counts lines matching `/^\s*draw\b/`
in the program's output — the lines a renderer walks, prose excluded. Test 4
cycles all twenty-six verbs through `parseCommand` 10,000 times after a
1,000-call warm-up.
