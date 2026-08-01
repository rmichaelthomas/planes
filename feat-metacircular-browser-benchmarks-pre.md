# feat/metacircular-browser — the Node reference, before any code change

**Date:** 2026-08-01
**Commit:** `9ce72af` — one commit past the prompt's stated base `839a8dd`, which is
this session's own docs propagation (#65, two markdown files). No code moved between
them.
**Node:** v22.23.1
**Machine:** darwin 25.5.0, arm64
**Corpus program:** `ordinary.planes`
**Method:** wall clock around the whole `node` process, 20 runs per case.

**This is a reference, not a regression bar.** The browser numbers are read against
it. §336 governs the unit — milliseconds, not construct counts.

## Raw process timings

| case | mean | median | min | max |
|------|------|--------|-----|-----|
| `node -e 0` (cold-start floor) | 57.68 ms | 57.85 ms | 54.79 ms | 59.75 ms |
| `run ordinary.planes` (direct) | 79.52 ms | 79.05 ms | 76.39 ms | 90.98 ms |
| `tokens ordinary.planes` (direct lex) | 75.79 ms | 75.74 ms | 72.54 ms | 78.55 ms |
| `ast ordinary.planes` (direct parse) | 77.75 ms | 78.10 ms | 75.19 ms | 80.60 ms |
| `meta run` — stage load alone, 0 files | 179.92 ms | 179.40 ms | 174.75 ms | 189.75 ms |
| `meta run` — stage load + 1 file | 294.83 ms | 294.94 ms | 286.67 ms | 303.07 ms |
| `meta lex` — stage load alone, 0 files | 94.31 ms | 94.44 ms | 92.15 ms | 96.69 ms |
| `meta lex` — stage load + 1 file | 132.15 ms | 132.19 ms | 130.41 ms | 135.05 ms |
| `meta parse` — stage load alone, 0 files | 141.71 ms | 142.01 ms | 137.05 ms | 144.01 ms |
| `meta parse` — stage load + 1 file | 197.96 ms | 198.09 ms | 194.04 ms | 202.08 ms |

**Stage load alone is `meta <stage>` with zero corpus files** — the stage graph loads
and nothing is processed. The difference between that and the one-file run is the
per-program cost with load amortised out, which is the only per-program number that
means anything (§N+2 failure mode 6).

## Derived — and one derivation that is WRONG, kept because it is instructive

Every process figure above carries ~57.68 ms of node cold start. Subtracting it:

| stage | stage load | per program, metacircular | "per program, direct" | "ratio" |
|-------|-----------|---------------------------|-----------------------|---------|
| `run` | 122.24 ms | **114.91 ms** | ~~21.84 ms~~ | ~~5.26×~~ |
| `lex` | 36.63 ms | **37.84 ms** | ~~18.11 ms~~ | ~~2.09×~~ |
| `parse` | 84.03 ms | **56.25 ms** | ~~20.07 ms~~ | ~~2.80×~~ |

- *stage load* = (stage load alone) − (cold start) — **sound**
- *per program, metacircular* = (stage load + 1 file) − (stage load alone) — **sound**;
  the subtraction removes cold start and stage load, leaving evaluation
- *per program, direct* = (the direct subcommand) − (cold start) — **NOT SOUND**

> ### The correction
>
> **The right-hand columns are struck through because they are wrong, and the browser
> measurement is what caught them.** `node js/cli.mjs run ordinary.planes` minus node's
> cold start is not the cost of evaluating `ordinary.planes`. It is the cost of
> importing and compiling the whole `js/*.mjs` graph, reading three grammar JSON files
> off disk, parsing the program, and *then* evaluating it — and the evaluation is the
> smallest term by three orders of magnitude. Measured in-process, warm, it is
> **0.030 ms**, not 21.84 ms.
>
> So the "ratio" column compared a per-program delta on one side against whole-process
> overhead on the other. It flattered the metacircular path enormously: the real
> in-process figure for `run` is **~600–1250×**, not 5.26×.
>
> The left-hand columns survive, because both are deltas between two runs of the same
> process shape. The lesson is the one §336 keeps making — a number is only as good as
> what was subtracted from it — and the reason this section is corrected in place
> rather than deleted is that the wrong derivation is the more useful artifact. See
> `metacircular-browser-report.md` for the measurement that replaced it.

What survives, and matters:

- **Stage load is not the expensive part of `run`** — 122 ms once, against 115 ms
  *per program*. A session that runs one program pays roughly double; one that runs ten
  pays 1.1×. The split is why §4.4 requires the page to show it separately.
- **The metacircular per-program cost is real and large in absolute terms** — 115 ms to
  run one small program through the self-hosted interpreter, against a direct
  evaluation too small for this method to resolve at all. That much was visible here;
  only its *ratio* needed the browser to measure honestly.
