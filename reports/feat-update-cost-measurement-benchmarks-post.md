## Post-Build Benchmarks — feat/update-cost-measurement
**Date:** 2026-08-05
**Commit:** 4dfbcf1 (base; this build touches no measured file)

Not a diff against `feat-update-cost-measurement-benchmarks-pre.md` — there
is no prior number to diff against (see that file). These are the first
numbers this instrument has ever produced, condensed from
`reports/REPORT_UPDATE_COST.md` §5, which carries the full tables, fitted
models, R², and per-implementation detail. Machine: Apple M1 Pro, Darwin
25.5.0 arm64, Python 3.14.6, Node v22.23.1.

### Test 1: the `with` arm — cost per single-field update, by record width
**Input:** `scripts/measure_update_cost.py` / `.mjs`, W ∈ {4, 8, 16, 32, 64, 128}, 7 trials, 200ms floor
**Result (median ns/call):** Python 1614 → 3421 (W=4→128); JS 398 → 7090 (W=4→128)
**Fitted slope (isolated copy cost):** Python 11.6 ns/field (R²=0.967); JS 48.2 ns/field (R²=0.9999)

### Test 2: the `plus` arm — cost per append, by list length
**Input:** `scripts/measure_update_cost.py` / `.mjs`, L ∈ {64, 256, 1024, 4096, 16384}, 7 trials, 200ms floor
**Result (median ns/call):** Python 1666 → 94017 (L=64→16384); JS 628 → 126542 (L=64→16384)
**Fitted slope:** Python 5.6 ns/element (R²=0.9991); JS 7.7 ns/element (R²=0.9987)

### Test 3: cumulative growth to L=16,384 — one program run, sequential `plus`
**Input:** `scripts/measure_update_cost.py` / `.mjs`, 128×128 nested loop, 7 trials
**Result:** Python 1187.7ms total (8.85 ns/copied-element implied); JS 2031.8ms total (15.14 ns/copied-element implied)
**Extrapolated (EXTRAPOLATION) to 100,000 events:** Python 44.25s; JS 75.69s

### Test 4: the world-shaped program — per-tick decomposition
**Input:** `benchmarks/world_shape.planes` shape, S ∈ {16, 64, 256} subjects, T=32 ticks
**Result, S=256 (largest measured):** Python 9,614,100 ns/tick — 0.9% parse, 19.7% copy, 79.3% remainder; JS 2,509,370 ns/tick — 0.4% parse, 16.6% copy, 83.0% remainder
**Time:** full method and all three S points in REPORT_UPDATE_COST.md §5.3

### Test 5: derivation retention — reachable `Deriv` count and memory growth
**Input:** `benchmarks/world_shape.planes` shape, S=64, checkpoints at tick 1/100/300/600, isolated subprocess
**Result:** reachable `Deriv` count exact-agrees Python=JS at every checkpoint (275 / 9,086 / 26,886 / 53,586); slope 89.00 nodes/tick in both
**Extrapolated (EXTRAPOLATION) to a 30-minute soak at 60 ticks/s (108,000 ticks):** ~9.61M `Deriv` nodes; ~10.6 GB (Python RSS growth) / ~9.1 GB (JS heap growth)

### Method

Calibration protocol, timer choice, and the with/plus arm's nested-loop
technique are identical to `scripts/measure_call_cost.py`/`.mjs` (see
`reports/REPORT_CALL_COST.md` §1 and `reports/REPORT_UPDATE_COST.md` §3).
The world-shaped program times the whole per-tick program (a fresh parse
each time, matching today's actual per-tick architecture) rather than
holding parse outside the loop. The retention phase runs as an isolated
subprocess per language so its memory reading is not contaminated by the
with/plus/cumulative/world phases that measure earlier in the same process.
