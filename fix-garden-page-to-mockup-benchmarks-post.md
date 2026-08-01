# Post-build measurement — `garden.html` at 1440×1080

**Measured against:** the rebuilt `garden.html` on `fix/garden-page-to-mockup`.
**Instrument, method, machine:** identical to `fix-garden-page-to-mockup-benchmarks-pre.md` — `scripts/measure-page-tick.mjs`, chromium 151.0.7922.34, median of 9 after 3 discarded warmups, seed 481027, ticks 30 / 130 / 260.

The page now ships `scale: 3` — a 1440×1080 backing store over an unchanged 480×360 program coordinate space.

---

## The shipped configuration, on hardware rasterisation

| tick | commands | run ms | walk ms | paint ms | **total ms** | pre (scale 1) | Δ |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 901 | 31.5 | 1.3 | 3.0 | **35.4** | 38.4 | **−3.0** |
| 130 | 863 | 27.9 | 1.2 | 2.4 | **32.0** | 32.8 | **−0.8** |
| 260 | 792 | 22.7 | 1.0 | 2.2 | **26.0** | 25.7 | +0.3 |

**No tick exceeds 60 ms. Nothing was accepted, because nothing regressed.** Every difference is inside run-to-run noise (`run`, the interpreter, is the whole cost and the resolution does not touch it). Nine times the pixels cost **zero measurable milliseconds**: `paint` is 3.0 ms at scale 3 against 3.0 ms at scale 1.

This is the first build in this page's history where the resolution went up and the frame did not get slower. It is not an optimisation — it is what a rasteriser with hardware behind it does with a fill-rate increase on a 1.5-megapixel surface.

## The software floor, for the record

| tick | run ms | walk ms | paint ms | **total ms** | pre (scale 1) |
|---:|---:|---:|---:|---:|---:|
| 30 | 32.9 | 1.4 | 268.8 | **303.5** | 62.3 |
| 130 | 27.8 | 1.1 | 215.5 | **245.1** | 49.8 |
| 260 | 22.2 | 1.0 | 211.4 | **234.2** | 45.2 |

Without hardware rasterisation the page costs ~4.9× what it did. **This is stated, not hidden, and it is not a new condition:** at scale 1 the software path was *already* over the 60 ms bar at tick 30 (62.3 ms). A machine falling back to SwiftShader has never run this scene inside budget; this build widens a gap that already existed rather than opening one.

The scale was **not** silently reduced. §4 Phase 7 forbids that, and the representative measurement does not ask for it.

## What the split proves

`paint` is the only stage the backing store touches, and it is the stage that stayed flat:

| | scale 1 | scale 3 | ratio |
|---|---:|---:|---:|
| paint, hardware | 3.0 ms | 3.0 ms | **1.0×** |
| paint, software | 27.6 ms | 268.8 ms | 9.7× |
| pixels | 172,800 | 1,555,200 | 9.0× |

Software tracks pixel count almost exactly. Hardware does not track it at all. Splitting the timer three ways is what makes that visible — a single end-to-end number would have shown 62 → 303 in software and been read as "the resolution is unaffordable", which is true only of a machine the page was already too heavy for.
