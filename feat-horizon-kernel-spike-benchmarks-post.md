# feat/horizon-kernel-spike — benchmarks, AFTER the persistent kernel

**Date:** captured at run time by this script.  
**Commit (base):** `432900b84eb1e50548eadb33c8d17f9da807831d`  
**Machine:** Apple M1 Pro, 10 cores, Darwin 25.5.0 arm64, Python 3.14.6  
**Method:** `world_kernel_bench.py`, 10000 ticks, `time.perf_counter()` around `advance()` + envelope conversion + `compute_delta()` only (build prompt invariant 1).

## Case 1 — the persistent kernel, one tick at a time (window=None, WorldRuntime's default)

| min | p50 | p95 | p99 | p99.9 | max | mean | ticks |
|---|---|---|---|---|---|---|---|
| 1.186 | 1.344 | 1.597 | 2.908 | 170.457 | 1574.678 | 2.161 | 10000 |

Wall clock for the full 10000-tick run: 21.68 s.

## The payoff, against feat-horizon-kernel-spike-benchmarks-pre.md

The pre-benchmark's non-persistent loop (compose prelude, fresh `Interpreter` per tick, re-parse the whole fixture, write/read `state.json`) measured p50 ≈ 4.17 ms per tick over 1000 ticks. The persistent kernel above measures p50 ≈ 1.344 ms per tick over 10000 ticks — eliminating repeated parse/module-load/JSON-serialization cost is a real, measured speedup here, not an assumed one (design doc §12's ordering, §28's mitigation).

