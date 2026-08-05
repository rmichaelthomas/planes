## Pre-Build Benchmarks — feat/update-cost-measurement
**Date:** 2026-08-05
**Commit:** 4dfbcf1

This build does not modify any interpreter, parser, lexer, analyser, host,
or renderer file — it adds a measurement instrument, per the build prompt's
scope (§1: "It does not touch any interpreter, parser, lexer, analyser,
numeric, host, or renderer file"). There is therefore no prior-code-path
timing to diff a post-build number against, unlike the `paint`/interpreter
builds this convention was written for (e.g.
`feat-module-loader-and-drawing-protocol-v1-benchmarks-pre.md`, which
diffs frame time before and after a rendering rewrite).

What "pre" means here instead: no instrument existed to produce a number at
all. Verified by listing at branch time (`4dfbcf1`), before any other step:

```
$ find . -iname '*measure_update_cost*' -not -path './.git/*'
(no output)
$ find . -iname '*world_shape*' -not -path './.git/*'
(no output)
$ find . -iname '*REPORT_UPDATE_COST*' -not -path './.git/*'
(no output)
```

No `scripts/measure_update_cost.py` or `.mjs`, no
`benchmarks/world_shape*.planes`, no report on functional-update cost. v5.0
§59 accepted an O(n) cost for `with`/`plus` and said "it should be measured
before it is optimised" — nothing in the repository had done so. That is
the pre-build state: the claim was asserted, never measured.

See `feat-update-cost-measurement-benchmarks-post.md` for the numbers this
build produces, and `reports/REPORT_UPDATE_COST.md` for the full method,
criteria, and verdicts.
