# feat/core-sufficiency — benchmarks, AFTER the build

**Date:** 2026-08-01
**Branch:** `feat/core-sufficiency`
**Base measured against:** `90d5ae9` (see `feat-core-sufficiency-benchmarks-pre.md`)
**Node:** v22.23.1
**Machine:** darwin 25.5.0, arm64
**Method:** identical to the pre file — wall clock around the whole `node` process,
20 runs per case.

Invariant 8: **no case more than 5% slower with the flag off.** With the flag on,
whatever it costs is a reported number, not a gate.

---

## With the flag OFF — invariant 8

| case | pre (mean) | post (mean) | Δ | ceiling (+5%) | verdict |
|------|-----------|-------------|---|---------------|---------|
| 1 — `meta lex`, 118 files | 8500.47 ms | **7918.28 ms** | **−6.85%** | 8925.49 ms | pass |
| 2 — `meta parse`, 71 files | 3553.62 ms | **3342.87 ms** | **−5.93%** | 3731.30 ms | pass |
| 3 — `meta run`, 71 files | 7221.80 ms | **6921.73 ms** | **−4.15%** | 7582.89 ms | pass |
| 4 — `run hn.planes` | 73.50 ms | **72.34 ms** | **−1.57%** | 77.17 ms | pass |
| 5 — `run ordinary.planes` | 74.87 ms | **72.35 ms** | **−3.37%** | 78.61 ms | pass |

**Every case passes, and every case reads faster — which is not a speedup and should
not be recorded as one.** Nothing in this build makes the unrestricted interpreter do
less work; it adds two already-false boolean tests to `eval`/`exec_stmt`, one to
`parse_statement`, and one small JSON read to `loadGrammar`. The pre and post runs
were taken on the same machine some tens of minutes apart, and the spread within a
single case (case 1's own min-to-max is 7430–8176 ms post, 8102–8778 ms pre) is wider
than the gap between them. **The honest reading is that the flag-off cost is below
this method's noise floor**, and the ±5% bar is met with room that the measurement
cannot resolve further.

Case 4 and case 5 are the tightest instruments here — ~65 ms of each is node cold
start, so the interpreter's own share is small and a per-node cost would show up
proportionally larger. Neither moved.

Full detail:

| case | mean | median | min | max | runs |
|------|------|--------|-----|-----|------|
| 1 — `meta lex` | 7918.28 ms | 7994.73 ms | 7430.64 ms | 8175.58 ms | 20 |
| 2 — `meta parse` | 3342.87 ms | 3347.63 ms | 3261.48 ms | 3446.51 ms | 20 |
| 3 — `meta run` | 6921.73 ms | 6829.51 ms | 6699.06 ms | 7447.46 ms | 20 |
| 4 — `run hn.planes` | 72.34 ms | 71.93 ms | 70.49 ms | 75.60 ms | 20 |
| 5 — `run ordinary.planes` | 72.35 ms | 72.08 ms | 70.19 ms | 75.38 ms | 20 |

---

## With the flag ON — a reported number, in two forms

**Against the real `grammar/core.json`, the restricted run does not measure the check.**
It refuses at `grammar/lexer.planes:89` before the first corpus file is touched, so the
number below is how long a doomed run takes to find out it is doomed — useful, and not
what "the restriction costs" means:

| case | mean | vs. the same case with the flag off |
|------|------|-------------------------------------|
| 1 — `meta lex --core` | 101.53 ms | refuses; 1.3% of the full run |
| 2 — `meta parse --core` | 150.67 ms | refuses; 4.5% of the full run |
| 3 — `meta run --core` | 190.14 ms | refuses; 2.7% of the full run |

**The cost of the check is measured against a core widened by `when` alone** (28 → 29
keywords, via `--core-json`), because that is the core under which the identical
workload actually completes:

| case | flag off | `--core`, core + `when` | Δ — what the check costs |
|------|----------|-------------------------|--------------------------|
| 1 — `meta lex`, 118 files | 7918.28 ms | 8605.54 ms | **+8.68%** |
| 2 — `meta parse`, 71 files | 3342.87 ms | 3554.58 ms | **+6.33%** |
| 3 — `meta run`, 71 files | 6921.73 ms | 7553.38 ms | **+9.13%** |

Roughly **+6% to +9%** to run the whole metacircular stack with every evaluation
checked against the port surface. That is the price of the answer, paid only when the
answer is being asked for, and it is not a gate.

Where it goes, measured rather than guessed: the suspect set — the node kinds that
could possibly spend a non-core keyword, derived from `core.json` and not hand-listed —
is `Assign, Rule, When, Why` under the real core and `Assign, Rule, Why` under the
widened one, out of 32 node kinds in the map. So under the core these timings were
taken with, **almost no node reaches the slow path at all**: the +6–9% is very nearly
all the fast path itself — one property read and one `Set.has` on `node.__node`, per
`eval` and per `exec_stmt`, over a workload that evaluates on the order of millions of
nodes. That is also why the flag-off cost is invisible: with `coreOnly` false the same
two sites are a single already-false boolean test and the `Set.has` never happens.

Full detail:

| case | mean | median | min | max | runs |
|------|------|--------|-----|-----|------|
| `meta lex --core` (real core) | 101.53 ms | 101.55 ms | 99.77 ms | 103.30 ms | 20 |
| `meta parse --core` (real core) | 150.67 ms | 150.36 ms | 148.02 ms | 161.48 ms | 20 |
| `meta run --core` (real core) | 190.14 ms | 190.05 ms | 185.02 ms | 194.44 ms | 20 |
| `meta lex --core` (core + `when`) | 8605.54 ms | 8480.30 ms | 7562.19 ms | 9552.74 ms | 20 |
| `meta parse --core` (core + `when`) | 3554.58 ms | 3554.72 ms | 3442.54 ms | 3654.05 ms | 20 |
| `meta run --core` (core + `when`) | 7553.38 ms | 7680.55 ms | 7135.95 ms | 8053.93 ms | 20 |
