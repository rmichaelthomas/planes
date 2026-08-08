# feat/reso-walk-movement — benchmarks, BEFORE the build

**Date:** captured at run time by this session.
**Commit (base):** `a366a6dfb40ce767605e5cf0d165fda4d3e27f60` (PR #96, `main`)
**Machine:** Apple M1 Pro, 10 cores, Darwin 25.5.0 arm64, node v22.23.1
**Method:** `scripts/world_renderer_bench.mjs`'s static server, driven live via `playwright-cli` (headless Chrome) against `horizon-crossing.html`. Simulation-step samples are the worker's own real per-tick `stepMs` (`client.metrics.stepMsSamples`, §16 gate's own metric — timed span is `advance()` + `takeOutput()` + `parseSceneIntent()` only, per `BrowserSceneKernel.step`'s existing discipline). Input-to-visible samples are `client.pokeSubject()`'s own round trip (main thread → worker → acknowledged on the next delta → two-rAF-confirmed paint) — the same synthetic direct-manipulation measurement build prompt §4/§16 already defines; Reso Walk's `move`/`touch` events reuse this exact same wire path (`sendInput`), so this is the correct baseline to diff against, not a new metric invented for this build.

## Simulation step (worker), ms — `horizon-crossing.html`, 1138 ticks

| count | min | p50 | p95 | p99 | max | mean |
|---|---|---|---|---|---|---|
| 1138 | 22.5 | 25.1 | 28.2 | 32.5 | 44.2 | 25.47 |

## Input → visible response, ms — `pokeSubject()`, 20 samples

| count | min | p50 | p95 | max | mean |
|---|---|---|---|---|---|
| 20 | 38.4 | 50.8 | 59.0 | 60.5 | 51.05 |

## Gate

Build prompt §6: Reso Walk's `advance` is lighter than the crossing's phase machine (no need/route/power/radio branch chain, a fixed-step clamp/integration and one range check instead) and must stay well under these figures; a step-cost or input-latency regression versus these numbers is a gate-blocker unless the architect accepts it. Reso Walk reuses the identical `sendInput`/message-contract wire path — no new input-plumbing cost is expected either.
