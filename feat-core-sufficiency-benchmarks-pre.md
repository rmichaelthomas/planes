# feat/core-sufficiency — benchmarks, BEFORE any code change

**Date:** 2026-08-01
**Commit:** `90d5ae9c30a9c27bed2cd537bee4fd594f418521` — "The hand-edited files get the
gate the generated ones already had (#62)"
**Node:** v22.23.1
**Machine:** darwin 25.5.0, arm64
**Method:** wall clock around the whole `node` process, 20 runs per case, taken on
`main` before the branch had any edit on it.

§336 governs this build: the restriction check sits in an evaluation hot path, so
**milliseconds are the unit, not construct counts**. Invariant 8 sets the bar — no
case more than 5% slower with the flag *off*. With the flag *on*, whatever it costs
is a reported number and not a gate.

The corpus lists are the ones `test_js_metacircular.py` produces: `_all_files()` is
every `**/*.planes` outside `.venv` (118 files), `_standalone()` is the subset with
no `use` line (71 files).

## Case 1 — `node js/cli.mjs meta lex <all 118 corpus files>`

`grammar/lexer.planes` running on the JavaScript interpreter, tokenising the corpus.

| mean | median | min | max | runs |
|------|--------|-----|-----|------|
| 8500.47 ms | 8473.42 ms | 8102.05 ms | 8777.75 ms | 20 |

## Case 2 — `node js/cli.mjs meta parse <71 standalone files>`

`grammar/parser.planes` (which `use`s `lexer` and `vocabulary`) on the JavaScript
interpreter, parsing the standalone corpus to canonical form.

| mean | median | min | max | runs |
|------|--------|-----|-----|------|
| 3553.62 ms | 3537.38 ms | 3458.93 ms | 3657.20 ms | 20 |

## Case 3 — `node js/cli.mjs meta run <71 standalone files>`

`grammar/interp.planes` and its whole module graph on the JavaScript interpreter,
executing the standalone corpus. This is the case the sufficiency question is about.

| mean | median | min | max | runs |
|------|--------|-----|-----|------|
| 7221.80 ms | 7105.66 ms | 6798.90 ms | 7867.76 ms | 20 |

## Case 4 — `node js/cli.mjs run hn.planes`

A single ordinary program, direct on the JavaScript interpreter — no metacircular
layer. Dominated by node cold start (~65 ms of the number below), which is exactly
why it is here: it is the case where a per-node cost in `eval` would be *least*
visible, and a regression that shows up here is a large one.

| mean | median | min | max | runs |
|------|--------|-----|-----|------|
| 73.50 ms | 72.58 ms | 69.49 ms | 85.26 ms | 20 |

## Case 5 — `node js/cli.mjs run ordinary.planes`

| mean | median | min | max | runs |
|------|--------|-----|-----|------|
| 74.87 ms | 75.32 ms | 71.31 ms | 76.89 ms | 20 |

## The 5% bar, in milliseconds

| case | baseline mean | invariant-8 ceiling (+5%) |
|------|---------------|---------------------------|
| 1 — meta lex | 8500.47 ms | 8925.49 ms |
| 2 — meta parse | 3553.62 ms | 3731.30 ms |
| 3 — meta run | 7221.80 ms | 7582.89 ms |
| 4 — run hn.planes | 73.50 ms | 77.17 ms |
| 5 — run ordinary.planes | 74.87 ms | 78.61 ms |
