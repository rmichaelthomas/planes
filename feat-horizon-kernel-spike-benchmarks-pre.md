# feat/horizon-kernel-spike — benchmarks, BEFORE the persistent kernel

**Date:** 2026-08-07
**Commit:** `432900b84eb1e50548eadb33c8d17f9da807831d` — "Horizon Phase 0 Build 4:
the numeric bridge — fixed-point unit convention and boundary quantization (#86)"
**Machine:** Apple M1 Pro, 10 cores, Darwin 25.5.0 arm64, Python 3.14.6
**Method:** `scripts/measure_kernel_legacy_loop.py`, 1000 ticks, `time.perf_counter()`
around each tick as a whole.

Build prompt §7: before the persistent kernel exists, this captures the per-tick
cost of the loop design doc §12 rejects — "composes source prelude text, parses
and runs the graph, renders output to text, writes state through an in-memory
JSON file, and repeats." Every tick here gets a brand-new `Interpreter`; the
fixture's own source text (`paint/world/kernel_spike_fixture.planes` — the SAME
fixture the persistent kernel drives) is re-parsed from scratch; the previous
tick's world state is re-injected as a composed prelude literal (the
js/paint/loop.mjs / test_a_crossing_in_planes.py convention); the result is
written to and read back from an in-memory `state.json` — never held as an
in-memory `Traced` value across ticks, unlike `WorldRuntime.advance`.

## Case 1 — the non-persistent loop, one tick at a time

Compose prelude → fresh `Interpreter()` → parse + run the whole program (fixture
+ driver) → write `state.json` → read it back → `json.loads`. Timed as a whole,
per tick.

| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |
|-----|-----|-----|-----|-------|-----|------|-------|
| 3.136 ms | 4.173 ms | 4.439 ms | 4.677 ms | 6.787 ms | 7.025 ms | 4.189 ms | 1000 |

Wall clock for the full 1000-tick run: 4.19 s.

## What this is a baseline for

`horizon-kernel-spike-results.md` (post-build) reports the SAME fixture's
per-tick cost under the persistent kernel (`world_kernel.py` — one `WorldRuntime`
held for the whole soak, `advance()` called directly, no reparse, no JSON
round-trip between ticks) and states the speedup as a measured ratio, not an
assumed one. `feat-horizon-kernel-spike-benchmarks-post.md` restates the
persistent numbers in this file's own table shape for a direct side-by-side.

This is not the number design doc §16's `simulation step` gate is measured
against — that gate is about the persistent path's own cost, not this rejected
one. This file exists only to make the payoff of eliminating repeated
parse/module/serialization cost (§28's mitigation, §12's ordering) a measured
fact rather than an assumed one.
