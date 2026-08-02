# A Crossing director-build performance record

Measured 2026-08-01 from the `codex/a-crossing-nine-landings` isolated
worktree. These are local observations and regression anchors, not universal
Planes language limits.

## Environment and workload

- Apple Silicon, macOS
- Node.js 22.23.1
- Codex in-app Chromium 150
- Desktop viewport 1280×720 CSS pixels at device-pixel ratio 2
- Portrait viewport 390×844 CSS pixels
- Fixed seed 481027
- Semantic rate: 8 Planes steps per second (125 ms budget per step)
- Live profile: 543 semantic runs and the most recent 240 shader frames
- Complete desktop and portrait ready → planning → crossing → arrived runs

## Live browser timings

Milliseconds. The semantic sample includes the initial cold run; the isolated
maximum is therefore more useful as a startup observation than a steady-state
budget.

| Operation | n | average | p95 | max |
|---|---:|---:|---:|---:|
| Planes semantic step | 543 | 9.411 | 12.100 | 69.600 |
| Scene IR parse | 543 | 1.090 | 1.300 | 3.100 |
| Stage reconciliation | 543 | 0.120 | 0.200 | 3.500 |
| WebGL atmosphere draw | 240 | 0.013 | 0.100 | 0.200 |

The conservative sum of component p95 values is 13.6 ms, about 10.9% of the
125 ms semantic interval. Rendering is not coupled to that rate: CSS/SVG
interpolation and the WebGL atmosphere use browser frames between ordered
Planes steps.

The measured page held 201 DOM elements, one low-power WebGL2 context, three
filtered-noise audio beds after explicit unlock, and no audio warnings.

## Visual delivery assets

| Asset | Purpose | Bytes | Loaded by modern browser? |
|---|---|---:|---|
| `passage-environment.webp` | environment plate | 477,766 | yes |
| `hydrofoil.webp` | transparent vessel sprite | about 28 KB | yes |
| `passage-environment.jpg` | plate fallback | about 856 KB | fallback only |
| `passage-environment.png` | source master | 3,022,275 | no |
| `hydrofoil.png` | source master | 730,703 | no |
| `ala-eriri-symbols.svg` | canonical archive symbols | 4,463 | archive use |

The modern visual payload is roughly 506 KB before shared fonts, runtime
modules, and document markup. The sprite optimization reduced its delivery
cost by about 96% while preserving the full-resolution source master.

## Behavioral performance checks

- Action controls remain stable across eight-Hz ticks and no longer lose
  pointer activation during DOM replacement.
- Desktop uses the full horizon composition.
- Portrait uses one undistorted world layer and a compositor pan; it does not
  create a second simulation or stretch the vessel.
- Reduced-motion mode disables the atmosphere canvas and decorative sprite
  animation.
- Source and effect-surface panes are lazy and absent from the primary play
  workload until requested.
- Audio is locked/muted until user activation; cue serials prevent repeated
  scheduling.

## Current conclusion

A Crossing is not close to exhausting its 125 ms semantic interval on this
machine. The next likely constraints are asset count/decoding, independently
animated characters, provenance indexing over much larger output graphs, and
audio-node growth—not the present Scene IR parse or stage reconciliation.

Do not increase semantic tick rate merely to make motion smoother. Keep Planes
ordered and deterministic; interpolate performers between steps. Add sprite
atlases, scene chunking, object pooling, or worker execution only when measured
scenes cross explicit budgets.

## Suggested regression budgets

- warm semantic p95: alert above 25 ms;
- Scene IR parse p95: alert above 4 ms;
- stage apply p95: alert above 2 ms;
- shader draw p95: alert above 1 ms;
- modern initial visual assets: alert above 1.5 MB;
- no continuous oscillator and master gain no higher than 0.38;
- no more than one semantic state authority.

These thresholds intentionally leave headroom for richer landings while
making regressions visible before the 125 ms interval is threatened.

## Reproduce

Run the focused suites:

    node --test js/test/a_crossing_*.test.mjs
    python3 -m unittest test_a_crossing_in_planes.py

Serve the isolated worktree and exercise one complete crossing. The page
publishes semantic, parse, apply, shader, audio, viewport, and state samples in
`data-crossing-metrics` on the root element.
