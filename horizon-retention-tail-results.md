# Horizon Phase 1 — the retention tail: measured results

**Date:** captured at run time by this script.  
**Commit:** `de541dc1840ec3f71b84f054c585cba983b3b32e`  
**Fixed-step rate:** 30 Hz (33.333 ms tick period).  
**Soak length:** 10000 ticks per configuration, per implementation. **Python gc_interval:** 1 tick(s) between `gc.collect()`+`gc.freeze()` calls. **JS gc interval:** never (measured to make things worse; see js/world_kernel.mjs).

## Machine specs (live capture, never invented)

| | Python run | Node run |
|---|---|---|
| CPU | Apple M1 Pro | Apple M1 Pro |
| cores | 10 | 10 |
| RAM | 16.0 GB | 16.0 GB |
| OS | Darwin 25.5.0 arm64 | Darwin 25.5.0 arm64 |
| runtime version | Python 3.14.6 | Node v22.23.1 |
| --expose-gc active | n/a | True |

## §1/§2 — what changed since the spike (`horizon-kernel-spike-results.md`)

**Rung 1 (collector behaviour).** `Deriv.inputs` is acyclic by construction (every edge points to a strictly older `_generation` stamp; confirmed by reading `interp.py`, `Env`, `Function`, `Host`, `WorldRuntime` — no back-edge exists anywhere this graph is reachable from). `world_kernel.py` now calls `gc.disable()` once, then `gc.collect()` + `gc.freeze()` at the tick boundary, strictly after `elapsed` is captured — refcounting (not the cycle detector) is what actually reclaims a `Deriv` the moment `_cut` drops its last reference, freeze or no freeze, so this changes only when/how often the cyclic collector re-scans the live graph, never what gets collected. `js/world_kernel.mjs` CAN call `global.gc()` at the same point, but does not by default: V8 has no `gc.freeze()` counterpart, so unlike Python's fix, forcing `global.gc()` does not shrink what the NEXT call re-scans — every call pays a cost proportional to the CURRENT heap again. Measured (not assumed): forcing it, on every interval tried, cost MORE than V8's own automatic scheduling (see js/world_kernel.mjs's module docstring for the numbers). Rung 1's JS default is therefore "do nothing" — a measured finding recorded per build prompt §2's own allowance for "an explicit recorded reason", not a silent gap; the capability stays in the code, opt-in, for a future build with a different lever.

**Rung 2 (`_cut`'s own garbage, REPORT_RETENTION.md §6, folded in) — Python only, JS measured and reverted.** `interp.py`'s `_seal` now hashes each released-subgraph line into a `hashlib.sha256()` incrementally, never building a `parts` list + one large joined string first — `hashlib`'s `.update()` is a C-extension call, so this is a clean allocation win. The same technique was tried on the JS side (a hand-rolled incremental `Sha256Stream`) and MEASURED against `_seal`'s real ~300-line shape: 0.195 ms/call against the original `sha256Hex(parts.join("\n"))`'s 0.074 ms/call — 2.6x SLOWER, not faster, because `sha256Hex` and any JS replacement for it are both pure JavaScript (no C-extension asymmetry to exploit), and the per-call overhead of many small `update()` calls outweighs the allocation saved. Confirmed at the soak level (a first soak run with it active showed the windowed configuration's JS p50/p95 regress, not improve). `js/interp.mjs`'s `_seal` therefore keeps its original form — measured, not assumed, per the same discipline as Rung 1's JS finding above. Python's fingerprint, `released_count`, and seal refusal sentence are unchanged by its own Rung 2 — `test_retention.py`'s cross-language fingerprint-agreement gate (17/17, including the byte-identical check) is the direct proof.

## Configuration: window=None (unbounded retention, WorldRuntime's default)

### Python (world_kernel.py) — after

| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |
|---|---|---|---|---|---|---|---|
| 1.183 | 1.287 | 1.385 | 1.475 | 1.597 | 5.424 | 1.291 | 10000 |

Wall clock: 13.42 s. Chain hash: `c85a23bc3d49cb15bb021caa5df5d99b6224090012722b6877e1b165e9ca7fed`. Ticks over 50 ms: **0**.

Soak-stability (first half vs second half of the 10000-tick run): p50 1.287 ms -> 1.286 ms, p95 1.381 ms -> 1.391 ms, max 1.756 ms -> 5.424 ms.

**Before (horizon-kernel-spike-results.md (commit 432900b84eb1e50548eadb33c8d17f9da807831d)):** p50 1.344 ms, p95 1.597 ms, max 1574.678 ms (first-half max 668.696 ms, second-half max 1574.678 ms).

**Max pause change:** 1574.678 ms -> 5.424 ms (improved by 1569.254 ms).

### JavaScript (js/world_kernel.mjs) — after

| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |
|---|---|---|---|---|---|---|---|
| 0.111 | 0.133 | 0.209 | 2.347 | 3.131 | 169.614 | 0.219 | 10000 |

Wall clock: 2.27 s. Chain hash: `c85a23bc3d49cb15bb021caa5df5d99b6224090012722b6877e1b165e9ca7fed`. Ticks over 50 ms: **1**.

Soak-stability (first half vs second half of the 10000-tick run): p50 0.134 ms -> 0.133 ms, p95 0.355 ms -> 0.154 ms, max 4.307 ms -> 169.614 ms.

**Before (horizon-kernel-spike-results.md (commit 432900b84eb1e50548eadb33c8d17f9da807831d)):** p50 0.132 ms, p95 0.220 ms, max 133.893 ms (first-half max 4.384 ms, second-half max 133.893 ms).

**Max pause change:** 133.893 ms -> 169.614 ms (regressed by 35.721 ms).

## Configuration: window=300 (bounded retention)

### Python (world_kernel.py) — after

| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |
|---|---|---|---|---|---|---|---|
| 8.086 | 8.969 | 9.510 | 9.972 | 21.930 | 76.473 | 9.053 | 10000 |

Wall clock: 90.91 s. Chain hash: `c85a23bc3d49cb15bb021caa5df5d99b6224090012722b6877e1b165e9ca7fed`. Ticks over 50 ms: **4**.

Soak-stability (first half vs second half of the 10000-tick run): p50 8.893 ms -> 9.053 ms, p95 9.391 ms -> 9.597 ms, max 50.621 ms -> 76.473 ms.

**Before (horizon-kernel-spike-results.md (commit 432900b84eb1e50548eadb33c8d17f9da807831d)):** p50 8.862 ms, p95 9.319 ms, max 305.687 ms (first-half max 50.521 ms, second-half max 305.687 ms).

**Max pause change:** 305.687 ms -> 76.473 ms (improved by 229.214 ms).

### JavaScript (js/world_kernel.mjs) — after

| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |
|---|---|---|---|---|---|---|---|
| 3.059 | 3.571 | 5.369 | 5.800 | 18.439 | 340.600 | 4.071 | 10000 |

Wall clock: 40.81 s. Chain hash: `c85a23bc3d49cb15bb021caa5df5d99b6224090012722b6877e1b165e9ca7fed`. Ticks over 50 ms: **7**.

Soak-stability (first half vs second half of the 10000-tick run): p50 3.609 ms -> 3.533 ms, p95 5.387 ms -> 5.341 ms, max 340.600 ms -> 151.665 ms.

**Before (horizon-kernel-spike-results.md (commit 432900b84eb1e50548eadb33c8d17f9da807831d)):** p50 3.433 ms, p95 5.216 ms, max 188.000 ms (first-half max 188.000 ms, second-half max 153.806 ms).

**Max pause change:** 188.000 ms -> 340.600 ms (regressed by 152.600 ms).

## §4 pass condition 1 — the §16 tail gate (zero ticks over 50 ms)

| configuration | implementation | over-gate ticks (after) | over-gate ticks (before) | max, after | max, before |
|---|---|---|---|---|---|
| window=None (unbounded retention, WorldRuntime's default) | Python | **0** | n/a (see max) | 5.424 ms | 1574.678 ms |
| window=None (unbounded retention, WorldRuntime's default) | JavaScript | **1** | n/a (see max) | 169.614 ms | 133.893 ms |
| window=300 (bounded retention) | Python | **4** | n/a (see max) | 76.473 ms | 305.687 ms |
| window=300 (bounded retention) | JavaScript | **7** | n/a (see max) | 340.600 ms | 188.000 ms |

**ESCALATION STATEMENT (§6.2.E) — not a silent pass.** window=None (unbounded retention, WorldRuntime's default) / JavaScript: 1 tick(s); window=300 (bounded retention) / Python: 4 tick(s); window=300 (bounded retention) / JavaScript: 7 tick(s). The windowed (shippable) configuration still shows at least one over-gate tick after Rungs 1-2. Per build prompt §4 point 1 this is a recorded, non-empty result: either Rung 3 (structural sharing, a separate, already-scoped build per §2) or a re-scoped production window is the next step — Rungs 1-2 reduced the tail (see the before/after max-pause figures above) but did not fully close it on this fixture.

## §4 pass condition 2 — the recalibrated §16 step gate (p95 ≤ 5.0 ms at 30 Hz)

| configuration | implementation | p95 (after) | clears 5.0 ms? | p95 (before) | pre-existing? |
|---|---|---|---|---|---|
| window=None (unbounded retention, WorldRuntime's default) | Python | 1.385 ms | yes | 1.597 ms | n/a |
| window=None (unbounded retention, WorldRuntime's default) | JavaScript | 0.209 ms | yes | 0.220 ms | n/a |
| window=300 (bounded retention) | Python | 9.510 ms | no | 9.319 ms | yes |
| window=300 (bounded retention) | JavaScript | 5.369 ms | no | 5.216 ms | yes |

**FAIL, but not newly introduced by this build.** At least one configuration/implementation pair's p95 exceeds the recalibrated 5.0 ms gate — reported plainly rather than smoothed over (build prompt §4 point 2). The 'before' column shows this is the windowed configuration's own pre-existing per-tick floor (REPORT_RETENTION.md §6's own named-but-not-fixed finding: `_cut`'s per-call discovery walk, run on every `mk()` call under a bounded window, dominates at every window size tried) surfacing against the NEWLY TIGHTENED gate (10 ms -> 5 ms), not something Rungs 1-2 introduced: window=300 (bounded retention) / Python; window=300 (bounded retention) / JavaScript were already over 5.0 ms before this build.

## §4 pass condition 3 / §8 — the A-Q3 sub-threshold (1.0 ms/tick)

`scripts/measure_update_cost.py`/`.mjs` (unmodified by this build — Rungs 1-2 do not touch `with`/`plus` at all, so this remeasures the SAME copy path REPORT_UPDATE_COST.md's Criterion B already measured, at the new threshold) — the world-phase `(b) copy cost, parse excluded` row, per subject count S, against the recalibrated 1.0 ms/tick threshold (20% of the recalibrated 5.0 ms §16 gate, the same 20% relationship REPORT_UPDATE_COST.md's Criterion B used at the old 10 ms gate/2.0 ms threshold):

| S | Python b_copy (ns/tick) | Python (ms/tick) | over 1.0ms? | JS b_copy (ns/tick) | JS (ms/tick) | over 1.0ms? |
|---|---|---|---|---|---|---|
| 16 | 163019.5 | 0.1630 | no | 26009.4 | 0.0260 | no |
| 64 | 632850.7 | 0.6329 | no | 102914.8 | 0.1029 | no |
| 256 | 2512175.3 | 2.5122 | **yes** | 410536.6 | 0.4105 | no |

Source: Python pre-captured at /tmp/update_cost_py_2.json; JS pre-captured at /tmp/update_cost_js.json.

**At least one measured point exceeds the recalibrated 1.0 ms/tick sub-threshold.** This is unaffected by Rungs 1-2 (they do not touch `with`/`plus`), so it would have been true before this build too — the recalibration itself, not this build's own change, is what surfaces it. See the A-Q3 disposition below.

## §8 — the A-Q3 disposition

**ESCALATED — A-Q3 stays open.** At least one measured with/plus copy-cost point (Python max 2.5122 ms/tick, JS max 0.4105 ms/tick, across S=16/64/256) exceeds the recalibrated 1.0 ms/tick sub-threshold — Python's S=256 point is the one that crosses it. This is a property of the with/plus copy path itself (unchanged by Rungs 1-2, and would have been true under this threshold regardless of what this build did) at a large subject count, not of the retention/GC work this build actually performed. Structural sharing (Rung 3) is the licensed next build per this criterion, at this shape — as build prompt §2 states, that is a SEPARATE build with its own prompt, re-proving §474 replay-reconstructibility for a data-structure change; it is not built here. The open-question count stays at seventeen.

Note on variance: a first run of this same script (see the raw JSON in `retention-tail-raw.json`) measured the Python S=256 point at k=1 repeat-per-trial (the lowest repeat count the calibration reached, hence the noisiest single number in this table); a second run reproduced a result in the same regime — both exceed the threshold, though the exact ms/tick figure moves between runs. The disposition above is not sensitive to that noise: the recalibrated threshold is 1.0 ms and both runs' S=256 point measures more than double that.

## Phase 2, named explicitly (unchanged from the spike)

- Breeze/Harbor recalibration against named school hardware.
- Remeasure against the real Ala Eriri cell, replacing this synthetic fixture.
- If Rung 3 is licensed by the disposition above, it is a separate build with its own §474 replay-reconstructibility proof.

