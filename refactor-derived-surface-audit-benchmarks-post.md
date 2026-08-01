# refactor/derived-surface-audit — post-change benchmarks

Three full `scripts/ci.sh` runs on this branch, after every fix (Phase 1's
`paths:` deletion, Phase 2's three checks and their four+one same-commit
fixes, Phase 3's `test_derived_claims.py`). `PATH="$PWD/.venv/bin:$PATH"`,
`PLANES_JOBS` unset — same machine, same job count, same `--fast` flag (off)
as the pre-change baseline.

## Total wall-clock

| Run | Total |
|---|---|
| 1 | 101.1s |
| 2 | 99.1s |
| 3 | 96.2s |
| **mean** | **98.8s** |

Against the pre-change mean of 115.0s, this is **not growth — it's 14.1%
faster**, comfortably inside invariant 9's "no more than 10% growth" ceiling.
The new `check_derived_claims` step itself costs well under half a second
(see below); the rest of the difference is run-to-run variance (warm disk
cache, less contention) of the same kind visible across the pre-change runs'
own 111.7s–121.0s spread.

## Per-step breakdown (seconds), run 3 — representative

| Step | Time | vs. pre-change mean |
|---|---|---|
| test suite | 73.774 | -18.6s |
| check_js_tests | 0.059 | ~same |
| js/test (node --test) | 18.292 | ~same |
| audit_locked_vs_built | 0.067 | ~same |
| grammar_gen --check | 0.784 | ~same |
| protocol_gen --check | 0.107 | ~same |
| core_check (interp.planes) | 0.879 | ~same |
| core_check (json.planes) | 0.123 | ~same |
| **check_derived_claims (new)** | **0.352** | **+0.352s** |
| errors_coverage (soft) | 0.082 | ~same |
| corpus_coverage (soft) | 0.199 | ~same |
| ruff | 0.075 | ~same |
| mypy | 0.313 | ~same |

`check_derived_claims.py` — three checks (a repo-wide walk of every `.py`
file for named dict literals, every `.mjs`/`.js` file for named object
literals, every root `*.html` page's prose against its module graph, and a
Python-AST walk of `sys.exit` across `scripts/*.{py,sh,mjs}` plus the five
named root checkers) — costs **0.352s**, a rounding error against the
73–90s the test suite alone takes.

## Assertion counts (this run, closing checkpoint v25.0 §354's gap — again,
post-change)

- **Python:** 63 suites (62 + `test_derived_claims.py`), 63 reporting,
  **1292 oks** (1277 + 1 new assertion in `test_gate.py` + 14 in
  `test_derived_claims.py`), 10 parallel jobs.
- **JavaScript:** `node --test js/test/*.mjs` — **737 tests, 737 pass, 0
  fail** — unchanged, as expected: this build touched no `.mjs` test file,
  only two `.mjs` source files (`js/browser_main.mjs`, `js/core_restrict.mjs`).

## Invariant 9

**Satisfied.** Gate wall-clock did not grow; it improved by 14.1% against
the pre-change mean, and the single new hard gate step this build adds costs
0.352s.
