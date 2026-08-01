# feat/metacircular-browser — benchmarks, AFTER the build

**Date:** 2026-08-01
**Branch:** `feat/metacircular-browser`
**Reference:** `feat-metacircular-browser-benchmarks-pre.md`
**Node:** v22.23.1 · **Machine:** darwin 25.5.0, arm64 · 20 runs per case

## The Node path is unmoved

Nothing this build adds is on the Node CLI's path. `js/meta_browser.mjs` is imported by
`meta.html` and by its own suite, never by `js/cli.mjs`; the one change to
`js/browser_main.mjs` (injecting `grammar/core.json`, adding `loadGraphInto`) is in a
module the CLI does not import. The table confirms it rather than assuming it:

| case | pre | post | Δ |
|------|-----|------|---|
| `node -e 0` (cold-start floor) | 57.68 ms | 58.97 ms | +2.2% |
| `run ordinary.planes` (direct) | 79.52 ms | 80.85 ms | +1.7% |
| `meta run` — stage load alone | 179.92 ms | 186.03 ms | +3.4% |
| `meta run` — stage load + 1 file | 294.83 ms | 318.06 ms | +7.9% |
| `meta lex` — stage load alone | 94.31 ms | 94.39 ms | +0.1% |
| `meta lex` — stage load + 1 file | 132.15 ms | 134.26 ms | +1.6% |
| `meta parse` — stage load alone | 141.71 ms | 151.75 ms | +7.1% |
| `meta parse` — stage load + 1 file | 197.96 ms | 211.12 ms | +6.6% |

The cold-start floor itself moved +2.2% between the two sittings with no code involved,
which sets the noise scale: the three cases above 6% are within about 2× of that floor's
own drift, and every one of them is a `meta` case whose work this build did not touch.
**No code on any of these paths changed**; `git diff main -- js/cli.mjs js/interp.mjs
js/lexer.mjs js/parser.mjs js/loader_node.mjs` is empty.

One measured-and-discarded artifact, recorded because it nearly went in the table: a
first post-build run put `run ordinary.planes` at a 132.41 ms mean with a 433.75 ms
maximum. That was this build's own leftovers — a `python3 -m http.server` and two
headless browsers still resident from the engine measurement. Killed and re-measured;
the numbers above are the clean sitting. A benchmark taken beside the tooling that
produced the other benchmarks is not a benchmark.

## The numbers this build actually produced

The Node process timings above are the *reference*, not the result. The result is
in-process, warm, per-call, and lives in `metacircular-browser-report.md`:

| environment | `run` stage, median warm ratio | recursion ceiling, direct → metacircular |
|---|---|---|
| Node v22.23.1 (V8) | 701× | 1199 → 178 |
| Chromium 150 (V8) | 441× | 1407 → 199 |
| WebKit 26 (JSC) | 762× | 6383 → 631 |

**The pre-build file's derived "5.26×" is struck through there and corrected.** It
compared a per-program delta against whole-process overhead; the real in-process figure
is two to three orders of magnitude larger. The correction is in the pre file rather
than deleted from it, because the wrong derivation is the more useful artifact.
