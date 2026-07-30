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
