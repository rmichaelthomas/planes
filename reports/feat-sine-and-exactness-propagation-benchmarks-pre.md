## Pre-Build Benchmarks — feat/sine-and-exactness-propagation
**Date:** 2026-07-27
**Commit:** ed7a15d

This build changes the numeric tower in all three implementations. Exactness
tracking adds a field to every value and a check to every operation, so
**case 1 is the one that matters — a regression in raw arithmetic throughput
is a regression in every program that runs**. The other four cases bound the
blast radius: two ticking programs, the self-hosted interpreter (whose values
are records carrying host numbers, so it pays the field cost twice over), and
the agreement suite that has to keep passing.

### Case 1: arithmetic throughput, all three implementations
**Input:** add, multiply, subtract, divide on exact rationals — 20000 iterations in the reference and the port, 25 through the self-hosted interpreter
**Result:** Python 1,639,523 ops/s; JavaScript 9,544,072 ops/s; self-hosted 663 ops/s
**Time:** Python 48.79ms / 80000 ops; JavaScript 8.38ms / 80000 ops; self-hosted 150.72ms / 100 ops

The self-hosted arm is measured through `for each` rather than recursion: the
interpreted call stack is that interpreter's scarcest resource (a 200-deep
interpreted recursion is `recursion-too-deep` on the reference), and this case
is about arithmetic, not frames. Its number is three orders of magnitude below
the reference's because every operation is an interpreted expression walk over
a record-shaped value, not a method call — that ratio is the baseline, and
what matters after Phase 1 is whether it moves.

### Case 2: bloom.planes — 120 ticks
**Input:** paint/bloom.planes, 120 ticks
**Result:** total per-tick mean 2.1411ms / worst 3.9388ms; commands per tick 140

### Case 3: snake.planes — 120 ticks
**Input:** paint/snake.planes, 120 ticks, deterministic Right/Down/Left/Up cycling every 5 ticks
**Result:** total per-tick mean 1.8257ms / worst 2.8701ms; commands per tick 55

### Case 4: the self-hosted interpreter on a fixed program
**Input:** grammar/interp.planes (loaded once) running a program with recursion, a list walk, exact division and its inverse, and a named rounding
**Result:** load 274.7ms; run mean 143.0ms over 5 samples; output `['8', '1', '0.3333']`

The output is the case's own assertion: `1/3 * 3` is exactly `1`, and
`round (1/3) to 4 places` is exactly `0.3333`. Both must stay true and stay
**exact** after Phase 1 — §4.4's rounding rule is what keeps every invoice in
the corpus from coming out flagged.

### Case 5: the three-way agreement suite
**Input:** test_js_lexer.py, test_js_parser.py, test_js_interp.py, test_js_num.py, test_js_json.py, test_js_shapes.py, test_js_render.py, test_js_metacircular.py
**Result:** 8 files, 8 reporting, 51 oks
**Time:** 34.6s wall-clock, exit 0

### Method

Case 1's Python arm calls `planes_num.Number`'s operators directly; its
JavaScript arm calls `PlanesNumber`'s methods in a separate `node` process; its
self-hosted arm runs a Planes program through `grammar/interp.planes` using
`scripts/run_corpus_selfhosted.py`'s own harness, so the measurement and the
corpus agreement runner load the interpreter the same way. Cases 2 and 3 use
`stepGraph` from `js/paint/loop.mjs` with a warm loader, timing the whole tick
including `paint` against a no-op fake 2D context. Case 4 loads
`grammar/interp.planes` once and reports the mean of five runs of one fixed
program. Case 5 shells out to `scripts/run_suites.py --only` for the eight
`test_js_*.py` suites, which are the three-way agreement.

### The thresholds this build is held to

- **Arithmetic throughput regression over 10% is a blocker** (§10.1).
- **Per-tick regression over 15% is a blocker** (§10.1).

Both are tighter than the corpus-refinement build's, and deliberately: that
build's cost came from programs choosing to draw more, which is a choice. This
one's would come from the numeric tower itself, which nothing can opt out of.
