# Pre-build measurement — `garden.html` before the page rebuild

**Measured against:** `garden.html` blob `3f31fb6`, repo at `d15c09f` (unmodified `main`).
**Instrument:** `scripts/measure-page-tick.mjs` — chromium 151.0.7922.34 via Playwright 1.62.1, Darwin 25.5.0 arm64.
**Method:** median of 9 samples after 3 discarded warmups, seed 481027, ticks 30 (full density), 130 (mid-scene), 260 (a raining frame).

`scripts/measure-density.mjs` measures the interpreter. This measures the page — specifically the three calls `garden.html`'s own `runAt` makes per tick, in order:

1. `session.runAt(tick, seed)` — compose, parse the module graph, run, collect
2. `markSink()` + `walk(lines)` — the third sink, for hit-testing
3. `paint(ctx, lines, DIMENSIONS)` — the rasteriser, at `DIMENSIONS.scale`

The split matters because this build changes **only** the rasteriser's workload. A total that moved would otherwise be unattributable.

---

## The finding that decided the resolution

**The backing-store scale is essentially free on hardware rasterisation, and catastrophic without it.** `paint` moves 3.0 → 3.4 ms across scales 1 → 4 on a GPU, and 27.6 → 270.3 ms across the same range in software. §3.5's 3× is therefore affordable — but only because the rasteriser is hardware, and that had to be measured rather than assumed.

The first pass of this measurement used Playwright's default headless chromium, which rasterises in software via SwiftShader. It reported scale 3 at **303 ms/tick** and would have forced a Phase 7 stop-and-report. That number was an artefact of the instrument: this scene is dense with `filter: blur(...)` (the sun's glow, seven clouds, the wet-ground sheen, every firefly), which is pathological in software and ordinary on a GPU. The instrument was wrong, not the design.

## Hardware rasterisation (`--gpu`) — representative of the real page

| scale | backing | tick | commands | run ms | walk ms | paint ms | **total ms** |
|---:|---|---:|---:|---:|---:|---:|---:|
| **1** | 480×360 | 30 | 901 | 34.5 | 1.3 | 3.0 | **38.4** |
| | | 130 | 863 | 29.2 | 1.2 | 2.3 | **32.8** |
| | | 260 | 792 | 22.4 | 0.9 | 2.2 | **25.7** |
| **2** | 960×720 | 30 | 901 | 34.1 | 1.3 | 3.1 | **39.3** |
| | | 130 | 863 | 28.4 | 1.1 | 2.5 | **32.1** |
| | | 260 | 792 | 22.6 | 1.1 | 2.5 | **26.1** |
| **3** | 1440×1080 | 30 | 901 | 32.1 | 1.2 | 3.3 | **36.5** |
| | | 130 | 863 | 28.7 | 1.1 | 2.5 | **32.6** |
| | | 260 | 792 | 23.0 | 1.1 | 2.4 | **26.5** |
| **4** | 1920×1440 | 30 | 901 | 34.7 | 1.6 | 3.4 | **39.8** |
| | | 130 | 863 | 29.2 | 1.3 | 2.6 | **34.1** |
| | | 260 | 792 | 23.0 | 1.3 | 2.6 | **27.1** |

Every tick at every scale is under 40 ms — comfortably inside the 60 ms bar, and inside the 250 ms wall-clock budget a 4-ticks-per-second loop actually has. The cost is the **interpreter** (22–35 ms), which the resolution does not touch. `run` agrees with REPORT_GARDEN_ALIVE.md's measured 28–34 ms.

## Software rasterisation (SwiftShader) — the floor, for the record

| scale | tick | run ms | walk ms | paint ms | **total ms** |
|---:|---:|---:|---:|---:|---:|
| **1** | 30 | 31.0 | 1.3 | 27.6 | **62.3** |
| | 130 | 28.0 | 1.1 | 20.9 | **49.8** |
| | 260 | 22.7 | 1.1 | 21.2 | **45.2** |
| **2** | 30 | 31.6 | 1.3 | 135.5 | **168.5** |
| | 130 | 28.0 | 1.2 | 102.8 | **131.7** |
| | 260 | 22.0 | 1.0 | 104.2 | **127.3** |
| **3** | 30 | 32.1 | 1.2 | 270.3 | **303.1** |
| | 130 | 27.3 | 1.0 | 215.8 | **244.7** |
| | 260 | 21.9 | 0.9 | 212.3 | **234.9** |

**A pre-existing fact, not something this build introduces:** on software rasterisation the page was *already* over the 60 ms bar at tick 30 (62.3 ms) at the current 480×360. A machine with no GPU acceleration has never run this scene inside the budget. The build raises the software cost substantially; it does not create the condition.

Software `paint` tracks pixel count almost exactly — 27.6 → 135.5 (4.9× for 4× the pixels) → 270.3 (9.8× for 9×) — which is what a rasteriser with no hardware behind it should do, and is the clearest evidence the two modes differ in kind rather than degree.
