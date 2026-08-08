# feat/reso-walk-movement — benchmarks, AFTER the build

**Date:** captured at run time by this session.
**Machine:** Apple M1 Pro, 10 cores, Darwin 25.5.0 arm64, node v22.23.1 (unchanged from the pre-benchmark's machine).
**Method:** identical to `feat-reso-walk-movement-benchmarks-pre.md` — `scripts/world_renderer_bench.mjs`'s static server, driven live via `playwright-cli` (headless Chrome) against `reso-walk.html`. Simulation-step samples are `client.metrics.stepMsSamples`; input-to-visible samples are `client.sendInput({kind:"move", dir:"west"}).then(r => r.ms)` — the real `move` event this build's own input seam carries, not a synthetic poke, so this measures the actual wire path a held key drives.

## Simulation step (worker), ms — `reso-walk.html`, 644 ticks

| count | min | p50 | p95 | p99 | max | mean |
|---|---|---|---|---|---|---|
| 644 | 9.5 | 10.6 | 11.4 | 13.5 | 22.7 | 10.64 |

## Input → visible response, ms — `sendInput({kind:"move", dir:"west"})`, 20 samples

| count | min | p50 | p95 | max | mean |
|---|---|---|---|---|---|
| 20 | 42.2 | 50.6 | 58.7 | 58.7 | 50.68 |

## Diff against feat-reso-walk-movement-benchmarks-pre.md (`horizon-crossing.html`)

| metric | crossing (pre) | reso walk (post) | delta |
|---|---|---|---|
| step p50 | 25.1 ms | 10.6 ms | **−58%** |
| step p95 | 28.2 ms | 11.4 ms | **−60%** |
| step mean | 25.47 ms | 10.64 ms | **−58%** |
| input→visible p50 | 50.8 ms | 50.6 ms | −0.4% (noise) |
| input→visible p95 | 59.0 ms | 58.7 ms | −0.5% (noise) |
| input→visible mean | 51.05 ms | 50.68 ms | −0.7% (noise) |

## Gate

**No regression.** Simulation step is markedly lighter than the crossing's, exactly as build prompt §6 predicted (`advance` here is a fixed-step clamp/integration and one range check — no need/route/power/radio branch chain). Input-to-visible latency is statistically indistinguishable from the crossing's own baseline, as expected: both reuse the identical `sendInput`/message-contract wire path (main thread → worker → acknowledged on the next delta → two-rAF-confirmed paint) with no new input-plumbing cost added. Zero worker errors across either capture.
