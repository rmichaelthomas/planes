## Post-Build Benchmarks — feat/corpus-refinement-svg-renderer-and-export
**Date:** 2026-07-27
**Commit:** 7b4a98c (Phase C, branch head at benchmark time)

The same four cases as the pre-build report, run against the refined corpus,
the shared stream walk and the second renderer. Same method: plain `node`, a
warm loader per program, steady-state per-tick cost. A fifth case is added
below — the two renderers timed against each other on the same stream, which
did not exist to measure before.

### Test 1: turtle.planes — one runProgramGraph call, static, warm loader
**Input:** paint/turtle.planes, single call (50 samples), loader pre-warmed
**Result:** parse mean 0.3124ms / worst 0.6043ms; run mean 7.5044ms / worst 11.0618ms; paint mean 2.0005ms / worst 4.6751ms
**Commands emitted:** 3577
**Time:** total mean 9.8173ms

### Test 2: bloom.planes — 120 ticks, warm loader reused across ticks
**Input:** paint/bloom.planes, 120 ticks
**Result:** per-tick parse mean 0.2785ms / worst 1.2535ms; step(run) mean 1.6601ms / worst 3.7758ms; paint mean 0.1229ms / worst 0.5435ms; total per-tick mean 2.0792ms / worst 4.2697ms
**Commands per tick:** mean 140.0 / worst 140
**Time:** 120 ticks in 249.50ms

### Test 3: snake.planes — 120 ticks, fixed synthetic key sequence, warm loader
**Input:** paint/snake.planes, 120 ticks, deterministic Right/Down/Left/Up cycling every 5 ticks
**Result:** per-tick parse mean 0.3902ms / worst 1.6463ms; step(run) mean 1.7842ms / worst 2.9601ms; paint mean 0.0672ms / worst 0.5250ms; total per-tick mean 2.2520ms / worst 3.5125ms
**Commands per tick:** mean 55.0 / worst 55
**Time:** 120 ticks in 270.24ms

### Test 4: draw-command throughput through parseCommand (26-verb table)
**Input:** 10000 commands cycling through all 26 verbs
**Result:** 2,419,867 commands/second
**Time:** 4.13ms for 10000 commands

### Test 5 (new): the two renderers on the same stream
**Input:** each program's stream, 50 samples, canvas against a no-op fake 2D context

| Stream | lines | `paint` mean / worst | `toSvg` mean / worst | SVG size |
|---|---:|---:|---:|---:|
| turtle | 3577 | 1.8180ms / 2.2693ms | 2.2726ms / 2.8474ms | 138546 B |
| bloom | 140 | 0.0973ms / 0.1639ms | 0.1246ms / 0.4165ms | 5077 B |
| snake | 59 | 0.0471ms / 0.0937ms | 0.0853ms / 0.1172ms | 8227 B |

The SVG renderer costs 25–80% more than the canvas one on the same stream,
which is string building against a fake context that does nothing. It is only
ever run on demand — an export, never a frame — so it is on no hot path. That
the two are the same order of magnitude at all is the shared walk: neither
pays twice for reading the stream.

## Diff against pre-build (2d36449)

| Case | Stage | Pre | Post | Δ |
|---|---|---:|---:|---:|
| 1 turtle (one-shot) | commands | 2299 | 3577 | +56% |
| 1 turtle | parse | 0.1522ms | 0.3124ms | +105% |
| 1 turtle | run | 3.4034ms | 7.5044ms | **+121%** |
| 1 turtle | paint | 1.0034ms | 2.0005ms | **+99%** |
| 1 turtle | **total** | 4.5590ms | 9.8173ms | **+115%** |
| 2 bloom (per-tick) | commands | 22 | 140 | +536% |
| 2 bloom | parse | 0.1378ms | 0.2785ms | +102% |
| 2 bloom | run | 0.9803ms | 1.6601ms | **+69%** |
| 2 bloom | paint | 0.0372ms | 0.1229ms | +230% |
| 2 bloom | **total per tick** | 1.1610ms | 2.0792ms | **+79%** |
| 3 snake (per-tick) | commands | 11 | 55 | +400% |
| 3 snake | parse | 0.2705ms | 0.3902ms | +44% |
| 3 snake | run | 1.2457ms | 1.7842ms | **+43%** |
| 3 snake | paint | 0.0298ms | 0.0672ms | +126% |
| 3 snake | **total per tick** | 1.5505ms | 2.2520ms | **+45%** |
| 4 parseCommand | throughput | 2,075,873/s | 2,419,867/s | +17% |

**The per-tick regression exceeds the 25% threshold §9.1 sets. It was raised
at the §9.3 gate with the reasoning below and explicitly accepted.**

### Root cause: the command count, and nothing else

Every regression above tracks the command count and no other variable. §3
predicted bloom would "roughly double" its stream; reaching the five path
verbs, the arc, `scale`, `corner` and a fill-plus-stroke per ring took 6.4×,
and snake's grid took 5×. Marginal cost is about 5µs per emitted command —
one helper call in `draw.planes` (a new `Env`, parameter binding, six string
concatenations, a `show`) — measured before Phase A and unchanged after it.
`parse` roughly doubled on turtle and bloom for the same reason at one remove:
the source files are longer, and the entry source is deliberately live per
frame (checkpoint v21.0 §249.4), so it cannot be cached.

Phase B added a second renderer and changed nothing about what the programs
emit; the shared walk costs the canvas renderer nothing measurable. Phase C
runs only when a button is pressed.

### What was found and fixed rather than accepted

Two real inefficiencies turned up while measuring and are fixed in the
shipped code, not merely noted:

1. **turtle's coordinates were carrying thirty-four exact digits.** Eight
   compounded multiplications by `0.72` and `1.09` on exact rationals produce
   denominators of 5^16 × 10^8, and `text of` renders every digit —
   `draw ellipse 0 -8.979590765701411970396185788678144 …`. Rounding
   `child-length` and `other-length` to three places (the language's own
   `round … to N places`, no builtin added) cut turtle's `run` from 12.67ms
   back to 7.50ms, a 41% saving, and shortened every emitted line.
2. **bloom translated to its centre once per ring.** The whole bloom is now
   drawn at the origin inside one `push`/`translate`/`pop`, the way turtle's
   tree already was, which removed 7 commands per frame and made `rings`
   take three parameters instead of five.

### Why the remainder was accepted

The absolute numbers: bloom's worst per-tick total is 4.27ms and snake's
3.51ms, against 16.67ms at 60fps — each ticking program uses under a third of
one frame at its worst sample, including parse and paint. The live browser
check bears this out: bloom animates smoothly and snake responds to arrow
keys with no perceptible lag.

Closing the gap further needs one of two things, both outside this build:
abandoning the verb coverage Phase A exists to establish, or changing
`interp.mjs`'s call mechanism. **The second is worth a conversation of its
own.** At ~5µs a call, a program that draws is paying most of its frame
budget in function-call overhead rather than in arithmetic or in drawing, and
`draw.planes`'s helpers are the smallest possible functions — one `show` of a
concatenation. Nothing here measures where that 5µs goes; that measurement is
the next build's, not this one's finding.
