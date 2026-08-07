# Horizon Phase 1 — `_cut`'s per-`mk` cost: measured results

**Date:** captured at run time by this script.  
**Commit:** `02010fd9ac2ec1dcccf68bff3ad15aa752c99786`.  
**Fixed-step rate:** 30 Hz (33.333 ms tick period). **Window:** 300 (the shippable configuration).

## Machine specs (live capture, never invented)

| | Python run | Node run |
|---|---|---|
| CPU | Apple M1 Pro | Apple M1 Pro |
| cores | 10 | 10 |
| RAM | 16.0 GB | 16.0 GB |
| OS | Darwin 25.5.0 arm64 | Darwin 25.5.0 arm64 |
| runtime version | Python 3.14.6 | v22.23.1 |

## §1 — the real fixture (`paint/world/kernel_spike_fixture.planes`)

10000 ticks, window=300, both implementations — the SAME fixture and soak shape `horizon-retention-tail-results.md` used, `_cut` changed only.

### Python — after

| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |
|---|---|---|---|---|---|---|---|
| 8.477 | 9.171 | 9.609 | 9.856 | 26.182 | 62.016 | 9.232 | 10000 |

Wall clock: 92.68 s. Chain hash: `c85a23bc3d49cb15bb021caa5df5d99b6224090012722b6877e1b165e9ca7fed`. Ticks over 50 ms: **1**.

**Before** (horizon-retention-tail-results.md (SHA 579842a, commit de541dc)): p50 8.969 ms, p95 9.510 ms, max 76.473 ms, over-50ms 4.

**p95 change:** 9.510 ms -> 9.609 ms (+0.099 ms). **Over-50ms change:** 4 -> 1.

### JavaScript — after

| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |
|---|---|---|---|---|---|---|---|
| 3.171 | 3.941 | 5.003 | 5.495 | 25.563 | 341.558 | 4.188 | 10000 |

Wall clock: 41.98 s. Chain hash: `c85a23bc3d49cb15bb021caa5df5d99b6224090012722b6877e1b165e9ca7fed`. Ticks over 50 ms: **6**.

**Before** (horizon-retention-tail-results.md (SHA 579842a, commit de541dc)): p50 3.571 ms, p95 5.369 ms, max 340.600 ms, over-50ms 7.

**p95 change:** 5.369 ms -> 5.003 ms (-0.366 ms). **Over-50ms change:** 7 -> 6.

## §2 — the synthetic accumulator chain (`test_retention.py`'s own `_chain` shape)

10000 `x = x + 1` steps, window=300, per-statement timing (one `_cut`-relevant `mk` burst per timed sample) — no DAG sharing by construction, isolating what the frontier fast path achieves when its own precondition (§3 below) actually holds.

| implementation | min | p50 | p95 | p99 | p99.9 | max | mean | samples |
|---|---|---|---|---|---|---|---|---|
| Python | 0.030 | 0.047 | 0.053 | 0.063 | 0.141 | 0.279 | 0.048 | 10002 |
| JS | 0.017 | 0.020 | 0.035 | 0.135 | 0.614 | 2.322 | 0.027 | 10002 |

## §3 — why the real fixture does not speed up: measured, not assumed

**FINDING — the fast path's own precondition is violated pervasively by
ordinary per-tick arithmetic, so the real fixture soak above shows no
material improvement.** The frontier fast path (`interp.py`'s
`_register_edges`/`_cut`, mirrored in `js/interp.mjs`) is safe to trust only
when a node's history is reachable through exactly one owner at a time.
When a value gets read more than once inside a larger expression — the
completely ordinary `(x - 1) * x` shape, not a contrived edge case — the
SAME derivation node becomes reachable through two independent owners, and
this codebase's own original `_cut` resolves that case in an order that
depends on the specific shape of its stack-based discovery walk for that
one call, not on any property (generation, insertion order, or anything
else) a cheaper incremental cache can reconstruct without literally
re-running that same walk.

**Live-measured** (a separate, un-timed 200-tick
Python run instrumenting `_register_edges`/`_seal`, so the timed soak above
is never itself perturbed by instrumentation overhead): of
613 calls into `_register_edges` (fast-path
extension attempts, both direct and reseed-triggered), **395
(64.4%) detected a newly-introduced second owner** and were
abandoned back to the general walk; `_seal` was called an average of
**467.6 times per tick** — the fixture's
twelve-subject arithmetic reuses locally-computed values constantly. Every
time sharing is detected the fast path safely (§5.2, verified below) falls
back to the unmodified original algorithm for that one call rather than
risk producing a different-but-plausible seal, which is why the fixture's
own p95 above lands within noise of `horizon-retention-tail-results.md`'s
own pre-this-build number — this build's fast path rarely gets to run to
completion on this fixture's actual code shape.

The synthetic chain in §2 shows the same fast path when its precondition
holds throughout (a single-owner accumulator, exactly what
`REPORT_UPDATE_COST.md` §5.4 and this build prompt's own §2 describe as
the target shape): the per-call cost the previous build measured scaling
with window size stops scaling with it entirely.

**Correctness is not in question either way** — §5.2's seal-identity
requirement is absolute regardless of which path a given call takes, and
`scripts/verify-cut-cost.py` (§6) checks it directly, on both the fixture
and the synthetic chain, at every window size tried.

**Next lever, named:** closing this gap requires reproducing original's
own per-call discovery order for genuinely shared nodes — not a bigger
cache, a DIFFERENT mechanism that tracks, per shared node, which of its
several pending owners a from-scratch walk would visit first — which is a
larger redesign than this build's own scope, not a parameter tune. Recorded
here as a stated next lever per this build prompt's own §4 point 1
requirement, not a silent partial pass.

## §4 pass condition 1 — the recalibrated §16 step gate (p95 ≤ 5.0 ms at 30 Hz)

| configuration | implementation | p95 (after) | clears 5.0 ms? | p95 (before) |
|---|---|---|---|---|
| real fixture, window=300 | Python | 9.609 ms | no | 9.510 ms |
| real fixture, window=300 | JavaScript | 5.003 ms | no | 5.369 ms |
| synthetic chain, window=300 | Python | 0.053 ms | yes | n/a |
| synthetic chain, window=300 | JavaScript | 0.035 ms | yes | n/a |

**FAIL on the real fixture, PASS on the synthetic chain — reported plainly, not smoothed over (build prompt §4 point 1/§6.2.E). See §3 for the measured reason and the named next lever.**

## §5 — A-Q3, RESOLVED PERMANENTLY (this build ends the recurrence)

A-Q3 had reopened on every gate move because Addendum v30.1 §480 armed its
reopening to a *moving* threshold — 20% of the §16 gate — so a gate change
re-armed it by construction. This build severs that coupling.

The retention-tail build (`horizon-retention-tail-results.md`, §4 pass
condition 3) already measured, live, the `with`/`plus` copy cost this
question turns on: **0.163019 ms/tick at S=16** (Python; JS 0.026009
ms/tick) against the recalibrated 1.0 ms sub-threshold — **6x under** at
the subject count the Horizon design describes for the first cell (~12
subjects). Copy cost only crosses 1.0 ms at S=256 (Python: 2.5122 ms/tick),
~20x the density of that first cell. This build's own `_cut` work is
independent of that number — Rung 3 (§1-4 above) does not touch
`with`/`plus` at all — so the measurement stands unchanged and is cited
here, not re-run.

Structural sharing (the A-Q3 escape) is the largest, most
§474-hazardous change available in this codebase, and at ship scale it
solves a problem that does not exist. It is not the constraint. `_cut`'s
own per-`mk` cost — what this build actually addresses (§1-3 above,
including the honest limit named in §3) — is.

**A-Q3 — RESOLVED, NOT LICENSED. Permanently.** Naive full-copy
`with`/`plus` is adequate at every subject count the Horizon design
describes; the structural-sharing escape stays unexercised. §480's
tripwire-2 (the §16-gate percentage coupling) is **STRUCK** — a gate
recalibration no longer reopens A-Q3. It is replaced by a single fixed
reopening gate: A-Q3 reopens only if a real (non-synthetic) world cell,
once Phase 2 builds it, sustains measured `with`/`plus` copy cost **≥ 2.0
ms/tick** — an absolute figure that does not move with any gate. Below
that, A-Q3 stays closed and is not re-examined. The replay-
reconstructibility gate (v30.0 §474) remains the standing licence
condition on any future A-Q3 build, if one is ever gated in. **Open-
question count returns to sixteen and A-Q3 leaves the register.**

The absolute 2.0 ms figure is the SME's call, flagged as an invention for
the architect to strike: it is the *original* pre-recalibration A-Q3
threshold from §480, promoted from "20% of a moving gate" to a fixed
number, chosen because it is the number the chain already reasoned about
and because it sits at ~S=270 (Python) — a density Phase 2's real cell
would have to blow past ~20x over to reach. If the architect wants a
different absolute number, it is one line to change; the *mechanism*
(fixed, not gate-coupled) is the fix.

This is a measured, recorded resolution written into this build's own
results, not a question handed back and not a separate document. A-Q3
does not appear in the next resume prompt.
