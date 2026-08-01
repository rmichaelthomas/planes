# How many draw commands fit in a frame

Produced by `node scripts/measure-density.mjs`. **This is a measurement, not a
gate.** Nothing in `ci.sh` runs it and it never fails a build. Its one job is to
set `SCENE_BUDGET` — the command count `paint/garden.planes` is allowed to
spend — from a number rather than from a guess.

## What was timed

One tick, end to end, the way a page actually pays for it: compose the five
prelude bindings, parse the whole module graph (`draw.planes`, `math.planes`,
the program), run it, collect the output lines. Parsing is per-tick in both
hosts — `js/browser_main.mjs`'s `runProgramGraph` re-parses every source on
every call, and `interp.py`'s `run_file` does the same — so timing only the
evaluator would flatter the numbers by exactly the part a scrubber drag pays
for twice.

The probe program is shaped like the garden, not like a benchmark: a recursive
one-mark-per-index spine, two commands per mark (a `fill` then a rotated
`ellipse`), and the same per-mark arithmetic the scene uses — `mod`, `sine`,
`cosine`, multiplication and division. The marks are split into families of 25
rather than one long chain, because the garden is a dozen shallow recursions
(stars, clouds, plants, blades) and not one deep one, and the difference is not
cosmetic: see the refusal note below.

Frame budget: **60ms**. Not 16.7ms — a tick is not all a frame pays for — but
the point past which dragging the scrubber stops feeling like a drag.

## Measured

Median of 7 runs after 6 warmups (JavaScript) / 5 runs after 2 warmups
(Python), macOS 25.5, Apple silicon, Node 22.23, CPython 3.13.

| draw commands | `js/interp.mjs` | `interp.py` |
|---:|---:|---:|
| 51 | 13.7 ms | 36.6 ms |
| 201 | 14.3 ms | 123.1 ms |
| 501 | 35.6 ms | 320.2 ms |
| 1001 | 68.0 ms | 647.4 ms |

Under 60ms per tick:

- **JavaScript: 877 commands**
- Python: 91 commands

## SCENE_BUDGET = 877

The JavaScript number, not the smaller of the two. The garden is drawn by a
browser; `interp.py` has no canvas and never renders a frame of it. The Python
column is here because the same program has to stay *runnable* there — that is
a correctness fact, not a frame budget, and sizing the picture to it would
spend a real limit on a host that never draws.

At 877 the scene is drawn at full density: no count was reduced to fit. What
it actually spends, counted from the emitted stream across all three days:

| | commands | per tick |
|---|---:|---:|
| lightest frame sampled | 750 | 28.7 ms |
| densest frame sampled | 868 | 33.7 ms |

**And the command count turned out to be the wrong unit.** The probe spends
0.07ms a command; the garden spends 0.04, because a probe mark is two
commands of arithmetic and a garden mark is often one command carrying six.
The number that governs is the one measured directly: 28 to 34 milliseconds a
tick, half the frame budget, everywhere in the cycle. `SCENE_BUDGET` is
reported here as a command count because that is what a scene is written in,
but a build that changes the scene should re-measure the milliseconds rather
than trust the conversion.

Two things the scene did to get there, both found by measuring rather than by
guessing, and both worth more than any count reduction:

- **`spread` was written with `mod`, and `mod` is a doubling recursion.**
  Thirty-odd Planes frames per call, five hundred calls a frame: 110ms a tick
  on its own. Rewritten over `whole of`, which is one exact big-integer
  divmod, it costs nothing measurable. `paint/math.planes`'s `part` and
  `floor` were rewritten the same way and are now correct for negatives AND
  constant-time.
- **The hash was quadratic, and a quadratic modulo a power of two is not
  uniform.** `fbm` came out with a range of 0.47 where it should have had 1.0,
  and it never rained once in three days. The cubic — scattered first, because
  its own constant term dominates for small n — is uniform, and the weather
  works.

## Two findings worth keeping

**The fixed cost is most of a small frame.** 51 commands cost 13.7ms in
JavaScript and 201 cost 14.3ms: parsing `draw.planes` and `math.planes` again every
tick is roughly 13ms of every frame regardless of what the program draws.
Above about 200 commands the per-command cost (~0.07ms in JavaScript, ~0.6ms in
Python) starts to dominate. A page that wanted more headroom would cache the
parsed graph, not draw less.

**`interp.py` refuses a spine `js/interp.mjs` runs.** A single recursion 250
frames deep raises `recursion-too-deep` in Python while JavaScript completes it
— the same 32-vs-201 asymmetry S8 measured in the metacircular runs, met again
from the other side. It constrains how the scene is written, not how big it is:
every recursive family in `paint/garden.planes` stays well under a hundred
frames, so both implementations run it. The measurement script reports the
refusal as a result rather than crashing on it.

---

# What `blur` costs, and what a cast shadow costs

Measured on branch `feat/protocol-v3-softness`, base `721bffb`, before any of
protocol v3 was specified. §337 is a standing term in both directions: a
decision that ADDS a costly capability states its number as surely as one that
removes a capability. Two capabilities were measured here and the numbers sent
them opposite ways.

## What was timed, and where

`scripts/measure-page-tick.mjs`'s method, verbatim in what it times — the three
calls `garden.html`'s own `runAt` makes, in their order:

1. `session.runAt(tick, seed)` — compose the prelude, parse the graph, run,
   collect
2. `markSink()` + `walk(lines)` — the third sink, for hit-testing
3. `paint(ctx, lines, DIMENSIONS)` — the rasteriser

At **scale 3**, the 1440x1080 backing store the page actually uses, in a real
chromium — under BOTH hardware (ANGLE/Metal) and software (SwiftShader)
rasterisation, because neither alone is honest. Median of 9 after 3 discarded
warmups, seed 481027.

Three variants of the program:

- **A** — `paint/garden.planes` as it stands: six `shadow 0 0 r` glows.
- **B** — the five glow sites emitting `blur` and a normally-filled mark
  instead of `shadow 0 0 r` plus the surrounding `alpha` set and reset.
- **C** — B, plus cast shadows on the tree, the plant stems and the flower
  heads.

## The ticks were wrong, and are named correctly here

The build asked for ticks 30 (day), 130 (dusk) and 260 (raining). Measured
against the program at the page's own seed, all three labels are wrong:

| tick | phase | `light` | `wet` | what it actually is |
|---:|---:|---:|---:|---|
| 30 | 0.30 | ~0.68 | 0.685 | morning, **the hardest rain in the run** (40 drops, the cap) |
| 130 | 0.30 | ~0.68 | 0.051 | morning, essentially dry |
| 260 | 0.60 | 1.0 | 0.000 | afternoon, dry, full light |

None of the three is dusk and none is night, so four more were added: **45**
(day, raining, `wet` 0.558), **250** (noon, dry), **275** (dusk, phase 0.75),
**290** (night, `light` 0). Rain falls at ticks 0–65 and 135–180 and nowhere
else in the first three days.

## Measured — one tick, end to end

Hardware (ANGLE/Metal) rasterisation. The software column tracked it within a
millisecond everywhere and is not repeated.

| variant | tick | commands | run | walk | paint | **total** |
|---|---:|---:|---:|---:|---:|---:|
| A — current | 30 | 898 | 31.1 | 1.2 | 3.1 | **35.3** |
| A | 45 | 832 | 24.6 | 1.3 | 2.9 | **28.7** |
| A | 130 | 860 | 28.6 | 1.3 | 2.7 | **32.9** |
| A | 250 | 790 | 22.7 | 1.1 | 2.2 | **26.0** |
| A | 260 | 788 | 22.5 | 1.0 | 2.3 | **26.1** |
| A | 275 | 824 | 24.0 | 1.2 | 2.4 | **27.6** |
| A | 290 | 822 | 24.0 | 1.3 | 2.4 | **27.8** |
| **B — blur** | 30 | 895 | 28.0 | 1.2 | **1.3** | **30.3** |
| B | 45 | 829 | 22.8 | 1.1 | 1.1 | **25.0** |
| B | 130 | 857 | 27.0 | 0.9 | 1.2 | **29.2** |
| B | 250 | 785 | 21.4 | 0.8 | 1.1 | **23.4** |
| B | 260 | 783 | 21.4 | 0.9 | 1.0 | **23.3** |
| B | 275 | 819 | 23.4 | 1.0 | 1.1 | **25.5** |
| B | 290 | 817 | 22.8 | 0.8 | 1.0 | **24.7** |
| C — blur + cast shadows | 30 | 1022 | 30.3 | 1.3 | 3.3 | **34.9** |
| C | 45 | 956 | 25.2 | 1.3 | 3.2 | **29.8** |
| C | 130 | 984 | 29.5 | 1.3 | 3.1 | **34.0** |
| C | 250 | 912 | 23.2 | 1.2 | 2.6 | **27.2** |
| C | 260 | 910 | 23.9 | 1.0 | 17.7 | **43.8** |
| C | 275 | 946 | 24.6 | 1.0 | 3.1 | **29.4** |
| C | 290 | 817 | 23.4 | 0.8 | 1.2 | **25.4** |

## `blur` is CHEAPER than the shadow it replaces

Not near-neutral, which is what was expected — better. **Paint time halves**,
2.2–3.1ms to 1.0–1.3ms, and the whole tick drops 10 to 20 percent. The reason
is structural rather than lucky: `shadow 0 0 r` makes canvas rasterise the mark
TWICE — once blurred as the shadow, once crisp on top — where `blur` rasterises
it once, blurred. The glow sites never wanted the second copy; they were paying
for it to get the first.

Two smaller savings ride along: the surrounding `alpha` set and reset
disappear (three commands), and so does every `no-shadow` in the program,
because after this substitution nothing sets a shadow at all.

**B ships.**

## A cast shadow costs the entire frame budget

Variant C's medians look survivable and they are hiding something. Every
sample, `paint` only, 25 runs:

| variant | tick | median | p90 | max |
|---|---:|---:|---:|---:|
| A | 275 | 2.1 | 2.9 | 5.5 |
| B | 275 | 1.0 | 2.0 | 228.4 † |
| C — as specified | 130 | 3.4 | 92.0 | 92.7 |
| C | 260 | 2.3 | 4.8 | 215.7 |
| C | 275 | 5.1 | 188.4 | **1835.5** |
| C2 — shadow clamped on-canvas | 130 | 56.0 | 199.0 | 210.8 |
| C2 | 260 | 55.9 | 70.1 | 96.6 |
| C2 | 275 | 56.6 | 79.6 | 80.0 |
| C3 — C2, softness capped too | 260 | 68.4 | 73.6 | 100.8 |
| C3 | 275 | 68.5 | 99.4 | 99.9 |

† one isolated sample in an otherwise flat run of 25; B sets no shadow and
casts no filter at that tick, so it is the machine, not the picture.

C's distribution is bimodal: most frames cost 2–3ms and some cost 92, 216,
1163 or 1836. The first hypothesis — that cast shadows push marks onto
`painter.mjs`'s offscreen single-cast composite — is **wrong**, and the
measurement says so directly: A and C both reach that path exactly 63 times a
frame. The count does not move.

What moves is where the shadow lands. §6.5's `k = 0.6 + (1 − max(0, sunEl)) ×
1.9` reaches 2.5 at sunrise and sunset, which throws a shadow up to 2.4 canvas
widths from its caster — off the canvas entirely, culled by the renderer, and
free. The cheap frames were cheap because **nothing was drawn**.

Clamping the shadow so it stays on the canvas (C2) is the fix that proves the
point by inverting the result: the median goes from 2.3ms to **56ms**, and
capping the softness as well (C3) makes it **68ms**. Adding the ~23ms the
interpreter already spends puts the tick at 80–100ms against a 60ms budget.

**A cast shadow that is actually visible costs 56 to 68 milliseconds of paint
on its own — the whole frame budget, for shadows alone.** That is the number,
and it is the reason cast shadows are not in this build. The scene keeps its
play loop instead; §337 exists so that trade is made against a measurement
rather than a preference.

The same fact explains variant A's 2.2–3.1ms: the six existing glows are
affordable only because their radii are small and their offsets are zero.
`shadow` is an expensive verb wherever it is really used.

## Commands by layer, and rain's share

Variant A, tick 260, 788 commands. Attributed by the run's own trace — every
emitted line carries the source line that emitted it, so this is counted, not
apportioned.

| layer | commands | share |
|---|---:|---:|
| plants | 312 | 39.6% |
| tree | 189 | 24.0% |
| state resets (`no-shadow` / `no-stroke`) | 80 | 10.2% |
| grass | 80 | 10.2% |
| clouds | 42 | 5.3% |
| hills | 38 | 4.8% |
| bees | 24 | 3.0% |
| the picture (top level) | 14 | 1.8% |
| sun / moon | 7 | 0.9% |
| ground | 2 | 0.3% |
| **rain** | **0** | **0%** |

**Rain draws nothing at tick 260** — the frame is dry. At tick 30, its
densest, rain is capped at 40 drops and one `line` each: **40 commands, 4.5% of
an 898-command frame.** Grass is a fixed 80 (20 blades, three commands each),
10.2%.

So the subpath question closes on a number rather than an argument. The mockup
batches ~350 rain strokes into one path with many subpaths; this scene draws at
most 40 separate `line` commands, 4.5% of its densest frame, and grass 10.2%.
There is no fixed-arity form that would not reintroduce variadics under a new
name, and at 4.5% there is nothing to buy. The matter is closed.
