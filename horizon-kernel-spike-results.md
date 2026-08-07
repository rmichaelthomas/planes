# Horizon Phase 1 — engine-kernel spike: measured results

**Date:** captured at run time by this script.  
**Commit (base):** `432900b84eb1e50548eadb33c8d17f9da807831d`  
**Fixed-step rate:** 30 Hz (33.333 ms tick period).  
**Soak length:** 10000 ticks per configuration, per implementation.

## Machine specs (live capture, never invented)

| | Python run | Node run |
|---|---|---|
| CPU | Apple M1 Pro | Apple M1 Pro |
| cores | 10 | 10 |
| RAM | 16.0 GB | 16.0 GB |
| OS | Darwin 25.5.0 arm64 | Darwin 25.5.0 arm64 |
| runtime version | Python 3.14.6 | Node v22.23.1 |

This machine is recorded as the **provisional Sun-tier reference device** (build prompt §1) — the run machine, not a named school device. Breeze/Harbor recalibration against named school hardware is a Phase 2 gate.

## Fixture profile (recorded for a Phase 2 diff)

```json
{
  "containingPlace": "reso-landing-cell (single place)",
  "containedSubjects": 12,
  "namedSubjects": {
    "water-edge": "continuous position (x drift + sine-driven y), rounded to the protocol's declared 3 places -- the envelope's own tracked subject",
    "weather/tide": "24-tick cycle, countdown timer + rising/falling phase",
    "structure": "static identity, 5-tick cycling occupancy",
    "living": "18-tick cycle, 3-phase state machine (resting/foraging/alert)",
    "activity": "15-tick cycle, a 2-tick active window emitting a semantic event"
  },
  "wanderers": 7,
  "wanderersDescription": "bulk per-tick load, no named role -- triangle-wave motion + a per-wanderer active predicate folded into situation.occupancy",
  "fixedStepHz": 30,
  "fixedStepPeriodMs": 33.333
}
```

## Configuration: window=None (unbounded retention, WorldRuntime's default)

### Python (world_kernel.py)

| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |
|---|---|---|---|---|---|---|---|
| 1.186 | 1.344 | 1.597 | 2.908 | 170.457 | 1574.678 | 2.161 | 10000 |

Wall clock: 21.68 s. Chain hash: `c85a23bc3d49cb15bb021caa5df5d99b6224090012722b6877e1b165e9ca7fed`.

Soak-stability (first half vs second half of the 10000-tick run): p50 1.345 ms -> 1.342 ms, p95 1.610 ms -> 1.578 ms, max 668.696 ms -> 1574.678 ms.

### JavaScript (js/world_kernel.mjs)

| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |
|---|---|---|---|---|---|---|---|
| 0.110 | 0.132 | 0.220 | 2.310 | 3.056 | 133.893 | 0.214 | 10000 |

Wall clock: 2.22 s. Chain hash: `c85a23bc3d49cb15bb021caa5df5d99b6224090012722b6877e1b165e9ca7fed`.

Soak-stability (first half vs second half of the 10000-tick run): p50 0.132 ms -> 0.131 ms, p95 0.366 ms -> 0.174 ms, max 4.384 ms -> 133.893 ms.

## Configuration: window=300 (bounded retention)

### Python (world_kernel.py)

| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |
|---|---|---|---|---|---|---|---|
| 7.949 | 8.862 | 9.319 | 9.537 | 24.595 | 305.687 | 8.989 | 10000 |

Wall clock: 89.97 s. Chain hash: `c85a23bc3d49cb15bb021caa5df5d99b6224090012722b6877e1b165e9ca7fed`.

Soak-stability (first half vs second half of the 10000-tick run): p50 8.852 ms -> 8.871 ms, p95 9.316 ms -> 9.320 ms, max 50.521 ms -> 305.687 ms.

### JavaScript (js/world_kernel.mjs)

| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |
|---|---|---|---|---|---|---|---|
| 3.028 | 3.433 | 5.216 | 5.575 | 15.867 | 188.000 | 3.911 | 10000 |

Wall clock: 39.20 s. Chain hash: `c85a23bc3d49cb15bb021caa5df5d99b6224090012722b6877e1b165e9ca7fed`.

Soak-stability (first half vs second half of the 10000-tick run): p50 3.467 ms -> 3.396 ms, p95 5.344 ms -> 5.033 ms, max 188.000 ms -> 153.806 ms.

## Tail latency and long-session growth (found while running this spike, not assumed)

p95 is stable across every configuration and both halves of the soak (see the soak-stability lines above) — the headline number below is trustworthy. The tail is not, in a specific and confirmed sense: `gc.disable()` on the Python side made every double-digit-millisecond outlier in this table disappear outright (confirmed directly, not inferred). With `window=None` the R1 derivation graph is never cut, stays live, and grows every tick, so cyclic-GC full-collection passes get more expensive as the soak goes on; `window=300` bounds the LIVE graph but not the RATE of garbage `_cut` itself produces (a fresh seal per cut edge), so it pays its own GC cost too. The table below reports first-half-vs-second-half max PLAINLY, including where it does not show the pattern growing monotonically (V8's GC scheduling is its own heuristic, not a fixed schedule — a run's single biggest pause can land in either half). The root cause (unbounded or high-volume garbage from the derivation graph) is the same either way; which half happens to contain the worst single pause is not.

| configuration | implementation | max, first half | max, second half | second-half is worse? |
|---|---|---|---|---|
| window=None (unbounded retention, WorldRuntime's default) | Python | 668.696 ms | 1574.678 ms | yes |
| window=None (unbounded retention, WorldRuntime's default) | JavaScript | 4.384 ms | 133.893 ms | yes |
| window=300 (bounded retention) | Python | 50.521 ms | 305.687 ms | yes |
| window=300 (bounded retention) | JavaScript | 188.000 ms | 153.806 ms | no |

3 of 4 configuration/implementation pairs show a worse max in the second half than the first.

**Design doc §16's 'zero tasks over 50 ms attributable to engine work' gate row is violated by at least one tick in this soak, in BOTH configurations, on the JavaScript implementation — the one that actually matters for a browser Worker (design §11.1): window=None (unbounded retention, WorldRuntime's default) / Python: 1574.7 ms; window=None (unbounded retention, WorldRuntime's default) / JavaScript: 133.9 ms; window=300 (bounded retention) / Python: 305.7 ms; window=300 (bounded retention) / JavaScript: 188.0 ms. This is a real §16-relevant finding this spike surfaced, not a synthetic-fixture artifact — the JS run uses the same V8 cyclic collector a shipped Worker would. It does not block this spike's own recalibration (p95 is what's being recalibrated), but it is not safe to file away either.**

## Recalibration statement (Sun-provisional)

- **Headline measured p95** (unbounded-retention configuration, the worse of the two implementations): **1.597 ms**, against design doc §16's current placeholder gate of **10.0 ms** and the 30 Hz fixed-step period of **33.333 ms**.
- **Clears the 10.0 ms placeholder:** yes.
- **Fits inside the 30 Hz period:** yes — restated per build prompt §4's instruction not to conflate 'fits the budget' with 'wall-clock throttled to 30 Hz': this run drove steps back-to-back, never throttled, and the number above is a plain comparison against the period, not a scheduling test.
- **Recommended §16 gate value (Sun-provisional):** given the headline p95 sits at roughly 16% of the current 10 ms placeholder with wide headroom against the 33.3 ms period, this spike recommends tightening the placeholder rather than loosening it — a provisional **p95 ≤ 5 ms at 30 Hz, Sun-provisional**, leaving real margin for Phase 2's real Ala Eriri cell (bigger, denser, than this synthetic fixture) before the 33.3 ms period itself becomes the binding constraint. **This is a recommendation, not a locked gate — the architect strikes or accepts it.**
- **A-Q3's 2.0 ms copy-cost sub-threshold:** this repo has no file reference for 'A-Q3' (it is not a checkpoint or file this build's inventory names), so this script cannot move it directly. Flagged here for the architect: if the §16 gate above moves, A-Q3 should move in step, per the build prompt's own §1 instruction.
- **The bytecode/WASM question (design §12/§28):** at 1.597 ms p95 against a 33.3 ms period, the persistent AST interpreter clears the STEADY-STATE budget with wide headroom, in both retention configurations (p50/p95 do not move across the soak — see the soak-stability lines above). Measured, not assumed: this is not grounds to reach for bytecode/WASM. But it is also not the whole answer — the tail-latency section above found a real cost this fixture pays that raw interpretation speed does not explain and bytecode/WASM would not fix: a compiled or bytecode-executed step still builds the same derivation graph R1 exists to retain, so the same GC-pause growth would recur under either. If Phase 2's real cell still shows this pattern, the fix this measurement points at is retention/GC engineering (window tuning, incremental collection, or a cheaper seal representation), not a faster evaluator.

## Phase 2, named explicitly

- Breeze/Harbor recalibration against named school hardware.
- Remeasure against the real Ala Eriri cell (design doc §24.1), replacing this synthetic fixture; diff its profile against the recorded one above.
- Tune the R1 retention window (`window=`) against the real cell's own derivation shape — this spike's bounded-window figures show a real, unglamorous trade for a branching per-tick shape, not a recommended production value.

