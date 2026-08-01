# What the second interpretive layer costs — the measured answer

**Build:** `feat/metacircular-browser`
**Base:** `main` at `9ce72af` (one docs commit past the prompt's `839a8dd`)
**Date:** 2026-08-01
**Page:** `meta.html` · **Engine:** `js/meta_browser.mjs` · **Suite:** `js/test/meta_browser.test.mjs`

---

## The verdict, in one sentence

**Running a program through `grammar/interp.planes` instead of directly on
`js/interp.mjs` costs between 354× and 1013× — a median of 441× in Chromium 150 (V8)
and 762× in WebKit 26 (JSC) — and the ceiling on recursion falls from 1407 frames to
199 in Chromium and from 6383 to 631 in WebKit, so the second layer costs roughly 7×
to 10× the stack as well as two to three orders of magnitude of time.**

Every corpus program that runs directly still runs through the stack. The cost is
severe and it is not disqualifying.

---

## v11.0 §136, and whether the measurement supports it

§136 ruled that **the metacircular route gives the worst performance of any
implementation option.** It has stood since on reasoning alone, with no figure.

**The measurement supports the ruling, and by a much wider margin than the ruling
implied.** "Worst performance" reads, in ordinary use, as a factor of a few. It is a
factor of several hundred. Three independent environments agree on the order of
magnitude, so this is not one engine's artifact:

| environment | `run` stage, median warm ratio | range across five programs |
|---|---|---|
| Node v22.23.1 (V8 12.4.254.21) | **701×** | 611× – 1253× |
| Chromium 150.0.0.0 (V8) | **441×** | 354× – 517× |
| WebKit 26 / Safari Technology Preview build (JSC) | **762×** | 455× – 1013× |

**Where the ruling reads differently after measurement:** §136 also concluded the
metacircular route saves only about an eighth of the port surface. That trade — an
eighth of the surface for two to three orders of magnitude of speed — is now a
concrete exchange rate rather than a qualitative judgement. Nothing here reopens the
ruling; §1 of the prompt puts that out of scope. It supplies the number the ruling
never had.

---

## §5.1 — the table, per engine

Five corpus programs, three stages, three environments. **Warm** figures are batch
timed: run until at least 60 ms has elapsed, then divide by the iteration count.
That is necessary rather than fastidious — `performance.now()` is deliberately
coarsened in every browser as a Spectre mitigation, and a direct run of a small
program measures **0.0 ms**, so any ratio built on single-shot timing is a ratio
against zero.

### Node v22.23.1 (V8 12.4.254.21-node.56)

| stage | stage load | direct, median | metacircular, median | ratio (min–max) | identical |
|---|---|---|---|---|---|
| `lex` | 15.5 ms | 0.0257 ms | 24.98 ms | 642× – 2104× | 5/5 |
| `parse` | 32.1 ms | 0.0444 ms | 17.21 ms | 272× – 734× | 5/5 |
| `run` | 38.2 ms | 0.0584 ms | 39.54 ms | 611× – 1253× | 5/5 |

### Chromium 150.0.0.0 (V8), headless

| stage | stage load | direct, median | metacircular, median | ratio (min–max) | identical |
|---|---|---|---|---|---|
| `lex` | 15.9 ms | 0.0264 ms | 6.08 ms | 165× – 562× | 5/5 |
| `parse` | 29.9 ms | 0.0408 ms | 6.79 ms | 133× – 178× | 5/5 |
| `run` | 38.1 ms | 0.0566 ms | 20.27 ms | 354× – 517× | 5/5 |

### WebKit 26 (JSC), headless

| stage | stage load | direct, median | metacircular, median | ratio (min–max) | identical |
|---|---|---|---|---|---|
| `lex` | 20.0 ms | 0.0364 ms | 13.80 ms | 186× – 411× | 5/5 |
| `parse` | 41.0 ms | 0.0506 ms | 17.50 ms | 269× – 346× | 5/5 |
| `run` | 55.0 ms | 0.0615 ms | 47.50 ms | 455× – 1013× | 5/5 |

The five programs are `ordinary.planes`, `corpus/factorial.planes`,
`corpus/word-count.planes`, `corpus/slugify.planes`, `corpus/discount-tiers.planes`.

**Firefox was not measured.** The SpiderMonkey binary is not installed on this machine
and `playwright install firefox` would have added a dependency this build is not
entitled to add. Stated rather than omitted: the third engine is missing, and its row
is absent, not zero.

### What the engine comparison says

§225 found JSC roughly 4× JIT-cold Chrome. On this workload, warm, **JSC is slower
than V8 on the metacircular path by about 1.7×** (762× vs 441× median on `run`) and
almost identical on the direct path. The engine is a real variable — the spread across
engines is about 2×, against a spread across programs within one engine of about 3× —
but it does not change the conclusion's order of magnitude, which is exactly why §5.1
required more than one.

---

## §5.2 — the recursion ceiling

Binary search on a self-recursive Planes function, direct and through the stage, in
each environment. §225 measured 639 under Node; the figure below is a different search
on a different program shape, so it is not directly comparable to that one.

| environment | direct | through `interp.planes` | frames the layer costs |
|---|---|---|---|
| Node v22.23.1 (V8) | 1199 | **178** | 6.7× |
| Chromium 150 (V8) | 1407 | **199** | 7.1× |
| WebKit 26 (JSC) | 6383 | **631** | 10.1× |

**JSC gives 4.5× the stack of V8** — 6383 against 1407 direct — which is the most
practically useful engine difference this build found and is not a speed result at all.

**Is the metacircular ceiling low enough that ordinary corpus programs cannot run?**
No. This was the headline finding the prompt reserved a verdict sentence for, and it
did not materialise. The whole standalone corpus was run through the browser stack in
both engines:

| environment | programs agreeing | non-agreements |
|---|---|---|
| Chromium 150 | **64 / 71** | 7, all previously documented |
| WebKit 26 | **64 / 71** | the same 7 |

All seven are classes `test_js_metacircular.py` already names and already excuses:

| program(s) | class |
|---|---|
| `probe/amber/site1_multiword`, `site2_juxtaposition`, `site3_paren_arglist` | ambiguity — a parse refusal both sides make |
| `probe/index_string` | parse-error — likewise |
| `demo/fdiff/v1`, `demo/fdiff/v2` | both sides refuse; the tags differ within `FOREIGN_REFUSALS` |
| `foreign.planes` | the single documented gap — `interp.planes` has no dynamic `host.resolve` |

**Zero new divergences.** The browser stack reproduces the Node stack's behaviour
exactly, including its one known gap. That claim is now a gate assertion
(`js/test/meta_browser.test.mjs`), not a paragraph in this file.

---

## §5.3 — the core, in a second environment

Non-blocking, and it cost two lines: `js/browser_main.mjs` now injects
`grammar/core.json` alongside the vocabulary, so `js/core_restrict.mjs` is available in
a page for the first time.

**The 29-keyword core carries the metacircular stack in a browser.** A core-restricted
interpreter loads `grammar/interp.planes` and its whole graph and runs a corpus program
through it, with output identical to the unrestricted path, in every environment
measured:

| environment | restricted stage load | result |
|---|---|---|
| Node v22.23.1 | 19.0 ms | identical |
| Chromium 150 | 20.9 ms | identical |
| WebKit 26 | 125.0 ms | identical |

The sufficiency finding of the previous two builds now holds in two environments rather
than one.

---

## A number this build got wrong before it got it right

`feat-metacircular-browser-benchmarks-pre.md` derived a Node ratio of **5.26×** for the
`run` stage. That figure is wrong by more than two orders of magnitude, and the
correction is recorded in that file rather than quietly dropped.

The error: `node js/cli.mjs run <file>` minus node's cold start is not the cost of
evaluating the program. It is the cost of importing and compiling the whole `js/*.mjs`
graph, reading three grammar JSON files, parsing, and *then* evaluating — and the
evaluation is the smallest term by three orders of magnitude. Measured in-process and
warm it is **0.030 ms**, not 21.84 ms. The metacircular side of the same comparison
*was* a clean delta, so the ratio compared a real per-program cost against process
overhead and flattered the metacircular path by a factor of about 130.

Both halves of the pre-benchmark's left-hand columns survive, because both are deltas
between two runs of the same process shape. It was the cross-shape comparison that was
invalid. §336's rule — a number is only as good as what was subtracted from it — earned
its keep here.

---

## Every figure's provenance

| figure | produced by |
|---|---|
| Node rows, ceilings, core-restricted | `js/meta_browser.mjs` under Node v22.23.1, `fetch` stubbed to read the repo from disk (the idiom `js/test/module_loader.test.mjs` established) |
| Chromium rows | Playwright-driven headless Chromium 150.0.0.0, page served over `python3 -m http.server` |
| WebKit rows | Playwright-driven headless WebKit 26, same server |
| corpus agreement | the same page, same two engines, all 71 standalone programs |
| pre-build Node process timings | `feat-metacircular-browser-benchmarks-pre.md`, 20 runs per case |

No figure in this report or on the page appears without the engine that produced it
(invariant 8). The page reads its own engine and version from `navigator.userAgent` and
prints it beside every timing it shows.
