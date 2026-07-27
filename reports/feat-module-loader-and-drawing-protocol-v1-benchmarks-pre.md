## Pre-Build Benchmarks — feat/module-loader-and-drawing-protocol-v1
**Date:** 2026-07-27
**Commit:** e0c54f6

This build changes per-frame parsing (module resolution adds a graph walk
ahead of `parse`) and rendering (the painter is rewritten to a 26-verb,
OKLCH, path-and-transform-aware implementation). These figures are the
baseline the post-build numbers are diffed against. All cases run under plain
`node` (no `--stack-size` flag), matching the environment `paint.html` itself
runs in.

### Test 1: turtle.planes — one runProgram call, static
**Input:** paint/turtle.planes, single call (50 samples)
**Result:** parse mean 0.1556ms / worst 0.4078ms; run mean 2.9610ms / worst 6.0679ms; paint mean 0.4242ms / worst 2.1539ms
**Time:** total mean 3.5408ms

### Test 2: bloom.planes — 120 ticks
**Input:** paint/bloom.planes, 120 ticks
**Result:** per-tick parse mean 0.1308ms / worst 0.3352ms; step(run) mean 0.4928ms / worst 1.1747ms; paint mean 0.0214ms / worst 0.0735ms; total per-tick mean 0.6464ms / worst 1.3991ms
**Time:** 120 ticks in 77.57ms

### Test 3: snake.planes — 120 ticks, fixed synthetic key sequence
**Input:** paint/snake.planes, 120 ticks, deterministic Right/Down/Left/Up cycling every 5 ticks
**Result:** per-tick parse mean 0.2948ms / worst 1.0006ms; step(run) mean 0.4440ms / worst 0.9215ms; paint mean 0.0118ms / worst 0.1091ms; total per-tick mean 0.7518ms / worst 1.9528ms
**Time:** 120 ticks in 90.22ms

### Test 4: draw-command throughput through parseCommand
**Input:** 10000 commands cycling through all 10 A.5 verbs
**Result:** 2,264,344 commands/second
**Time:** 4.42ms for 10000 commands

### Method

`parse` timing is `js/parser.mjs`'s `parse(src)` called directly on the raw
program text. `run` timing for test 1 is `runProgram` from `js/browser_main.mjs`;
for tests 2–3 it is `step` from `js/paint/loop.mjs` (which composes the tick
prelude and runs the whole program — the per-tick unit the loop actually
pays for). `paint` timing is `paint(ctx, lines, dimensions)` from
`js/paint/painter.mjs` against a no-op fake 2D context (`beginPath`, `stroke`,
`fill`, `arc`, etc. all record-nothing stubs), matching `paint_painter.test.mjs`'s
own fake-context pattern. Test 4 cycles the ten A.5 verbs (`pen`, `width`,
`move`, `line`, `circle`, `dot`, `rect`, `box`, `text`, `clear`) through
`parseCommand` 10,000 times after a 1,000-call warm-up.
