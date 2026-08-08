# Horizon Phase 1 — renderer pipeline results

Captured: 2026-08-08T00:24:00Z
Browser: HeadlessChrome (playwright-cli, chrome channel) 151.0.0.0 (headless)
Run machine: Darwin 25.5.0 (arm64), Apple M1 Pro x10, 16 GB RAM, node v22.23.1

**All frame-time gates below are Sun-provisional against this run machine.** No named school-hardware reference device exists to measure Breeze/Harbor against yet (design doc §16: gates "must be recalibrated against named reference devices"); recalibration is a Phase 2 gate. A gate that fails here against the placeholder scene is a recorded finding about pipeline overhead on this machine, not a shippable-quality verdict.

## Frame-time and simulation-step distributions, per tier

### sun — gate p95 ≤ 16.7 ms — PASS

- frame time (main thread, ms): count=480 min=7.30 p50=8.30 p95=8.90 p99=9.30 max=9.40 mean=8.33
- simulation step (worker, ms): count=120 min=3.90 p50=4.30 p95=5.40 p99=5.90 max=6.50 mean=4.41
- long tasks observed: 0, over 50ms: 0
- sprite count: 1, DOM mirror node count: 1
- JS heap used (MB): 7.3
- worker: snapshots=1 deltas=371 discarded=0 errors=0

### breeze — gate p95 ≤ 22 ms — PASS

- frame time (main thread, ms): count=481 min=7.30 p50=8.30 p95=8.90 p99=9.30 max=9.40 mean=8.33
- simulation step (worker, ms): count=120 min=4.00 p50=4.40 p95=4.70 p99=4.80 max=5.00 mean=4.37
- long tasks observed: 0, over 50ms: 0
- sprite count: 1, DOM mirror node count: 1
- JS heap used (MB): 6.6
- worker: snapshots=1 deltas=491 discarded=0 errors=0

### harbor — gate p95 ≤ 33.3 ms — PASS

- frame time (main thread, ms): count=481 min=7.30 p50=8.30 p95=9.10 p99=9.30 max=9.40 mean=8.33
- simulation step (worker, ms): count=120 min=4.00 p50=4.40 p95=4.90 p99=8.20 max=9.00 mean=4.48
- long tasks observed: 0, over 50ms: 0
- sprite count: 1, DOM mirror node count: 1
- JS heap used (MB): 7.1
- worker: snapshots=1 deltas=611 discarded=0 errors=0

## Input → visible response

Gate: p95 ≤ 70 ms, for a synthetic direct-manipulation poke — the Living Lens is Phase 3, and advance(world, tick) has no input-event parameter yet (worker.mjs's own header explains why), so this measures the message-contract round trip (main thread → worker → acknowledged on the next delta → painted), not a semantic effect of the poke.

- count=15 min=22.80 p50=44.10 p95=51.90 p99=51.90 max=51.90 mean=43.18
- gate: PASS

## Determinism and quality-tier invariance

- semantic determinism (identical snapshot hashes, same package/seed/events): PASS — automated: scripts/verify-renderer-pipeline.mjs check B1 — two independent fresh 12-tick runs of the real fixture over a real local server produced byte-identical delta.semanticHash sequences; see renderer-pipeline-verification.md.
- quality-tier invariance (identical semantic event log + save hash across tiers): PASS — automated: scripts/verify-renderer-pipeline.mjs check B2 — a 12-tick run with Sun/Breeze/Harbor switched mid-run (via FidelityController) produced the identical semantic hash sequence as a tier-switch-free run; see renderer-pipeline-verification.md. Also confirmed live in-browser: real WebGL context loss + recovery (via WEBGL_lose_context) left the worker ticking throughout (deltasApplied grew monotonically across the loss), and a forced loss past the 4s bounded interval triggered the real Safe Harbor performer swap with the subject re-hydrated — see the two capture screenshots.

## Diagnostic capture

Screenshots (placeholder scene, diagnostic evidence the pipeline runs — NOT a visual-acceptance capture):

- `horizon-renderer-pipeline-capture-pixi.png (Pixi, Sun tier)`
- `horizon-renderer-pipeline-capture-safe-harbor.png (Safe Harbor, forced context-loss-past-timeout fallback)`

## What this build did not do — owed to Phase 2

- visual acceptance against the §24.4 Reso Landing frame (asset compositor, segmented depth planes, rigs, real cell);
- Breeze/Harbor frame-gate recalibration against named school hardware;
- Rapier, audio, and the Living Lens interaction layer;
- the real Ala Eriri cell replacing the placeholder scene.

