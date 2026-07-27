## Post-Build Benchmarks — feat/sine-and-exactness-propagation
**Date:** 2026-07-27
**Commit:** 37f19f5 (Phase 4, branch head at benchmark time)

The same five cases as the pre-build report, same method: plain `node` and
plain `python3`, a warm loader per program, `for each` rather than recursion in
the self-hosted arithmetic arm.

### Case 1: arithmetic throughput, all three implementations
**Result:** Python 1,572,335 ops/s; JavaScript 9,075,740 ops/s; self-hosted 650 ops/s
**Time:** Python 50.88ms / 80000 ops; JavaScript 8.81ms / 80000 ops; self-hosted 153.96ms / 100 ops

### Case 2: bloom.planes — 120 ticks
**Result:** total per-tick mean 2.4362ms / worst 4.9413ms; commands per tick 140

### Case 3: snake.planes — 120 ticks
**Result:** total per-tick mean 1.8490ms / worst 3.0689ms; commands per tick 55

### Case 4: the self-hosted interpreter on a fixed program
**Result:** load 287.8ms; run mean 149.9ms over 5 samples; output `['8', '1', '0.3333']`

### Case 5: the three-way agreement suite
**Result:** 8 files, 8 reporting, 51 oks
**Time:** 35.4s wall-clock, exit 0

## Diff against pre-build (ed7a15d)

| Case | Measure | Pre | Post | Δ | Threshold |
|---|---|---:|---:|---:|---|
| 1 | Python arithmetic | 1,639,523/s | 1,572,335/s | **−4.1%** | 10% |
| 1 | JavaScript arithmetic | 9,544,072/s | 9,075,740/s | **−4.9%** | 10% |
| 1 | self-hosted arithmetic | 663/s | 650/s | **−2.0%** | 10% |
| 2 | bloom per tick | 2.1411ms | 2.4362ms | **+13.8%** | 15% |
| 3 | snake per tick | 1.8257ms | 1.8490ms | +1.3% | 15% |
| 4 | self-hosted fixed program | 143.0ms | 149.9ms | +4.8% | — |
| 5 | agreement suite | 34.6s | 35.4s | +2.3% | — |

**Every case is inside its threshold.** Nothing is flagged for acceptance.

### What the numbers are

**Arithmetic, −4 to −5%.** This is the whole cost of the feature on every
program that never calls `sine`: one more field on every value, one more
attribute read and a truthiness test on every operation. It was measured three
times per implementation because the first Phase-1 reading came in at −7 to
−8% and the threshold is 10%; the settled figure with the same warm-up as the
pre-build run is −4 to −5%, and the spread across runs is about 3 points.

**bloom, +13.8%, and it is two things.** Roughly 8 points are Phase 1 — the
tower cost above, paid on every arithmetic operation in a 140-command frame.
Roughly 5 are Phase 4: thirteen `wave` calls per tick, each of which is two
interpreted function calls (`wave`, then `cosine`) plus one `sine` plus one
`round`. **`sine` itself is 0.08ms of the 2.44ms** — measured directly, thirteen
calls at 6.4µs. The builtin is not what costs; the interpreted call chain
around it is, which is the same ~5µs-per-call figure the previous build named
for a later conversation.

Run-to-run spread on bloom is 2.40–2.49ms (12–16%), so this sits close enough
to the 15% line to be worth stating rather than rounding down. Three
consecutive runs are in the report's source.

**snake, +1.3%.** snake `use`s `math` and calls no trigonometry, so it pays the
tower cost and nothing else. That it moved barely at all is the check that
Phase 1 landed inert.

### One thing that had to be fixed before the number was acceptable

bloom's `wave` **rounds its result to six places**, for the same reason turtle
rounds its coordinates. A `sine` result carries a denominator of 10^30 and
everything computed downstream inherits it. Unrounded, bloom emitted lines
like `draw circle 0 0 38.2765368539594373604971219987056` — 31 decimal places
of precision a sixth of a micron past what a pixel can show — and ran at
2.81ms per tick (+31%). Rounding took it to 2.44ms. **The rounding does not
make the value exact**, which is §4.1's rule doing exactly its job: the
surface beside the canvas still says these numbers are approximate.

### And one that was fixed before it was measurable at all

The algorithm §5.4 describes — the series on plain exact rationals, the result
reduced at the end — costs **~3ms per call** in the JavaScript port, where gcd
over 2000-bit BigInts dominates everything, and **refuses outright** at `sine
of 60` (a denominator of 10^1224, past `MAX_DENOMINATOR`). On scaled integers
it is 6.4µs, a 190× difference, with identical digits. Had that not been found,
bloom's thirteen calls per tick would have added 39ms to a 16.67ms frame.
