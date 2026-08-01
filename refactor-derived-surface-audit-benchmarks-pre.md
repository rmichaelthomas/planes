# refactor/derived-surface-audit — pre-change benchmarks

Three full `scripts/ci.sh` runs on `main` at `976c3ab`, before any change in
this build. `PATH="$PWD/.venv/bin:$PATH"` (ruff + mypy from `./.venv`),
`PLANES_JOBS` unset (default parallel suite run).

## Total wall-clock

| Run | Total |
|---|---|
| 1 | 121.0s |
| 2 | 111.7s |
| 3 | 112.2s |
| **mean** | **115.0s** |

## Per-step breakdown (seconds)

| Step | Run 1 | Run 2 | Run 3 | Mean |
|---|---|---|---|---|
| test suite | 96.570 | 89.517 | 91.036 | 92.37 |
| check_js_tests | 0.066 | 0.062 | 0.059 | 0.062 |
| js/test (node --test) | 20.440 | 18.375 | 17.470 | 18.76 |
| audit_locked_vs_built | 0.076 | 0.075 | 0.071 | 0.074 |
| grammar_gen --check | 0.801 | 0.806 | 0.769 | 0.792 |
| protocol_gen --check | 0.112 | 0.111 | 0.105 | 0.109 |
| core_check (interp.planes) | 0.936 | 0.917 | 0.894 | 0.916 |
| core_check (json.planes) | 0.143 | 0.137 | 0.131 | 0.137 |
| errors_coverage (soft) | 0.085 | 0.082 | 0.079 | 0.082 |
| corpus_coverage (soft) | 0.211 | 0.210 | 0.208 | 0.210 |
| ruff | 0.098 | 0.079 | 0.050 | 0.076 |
| mypy | 0.335 | 0.271 | 0.264 | 0.290 |

`test suite` (parallel, 10 jobs) and `js/test` together account for the vast
majority of gate wall-clock; every checker this build adds or touches
(`core_check`, `grammar_gen --check`, `protocol_gen --check`) costs under a
second.

## Assertion counts (this run, closing checkpoint v25.0 §354's gap)

- **Python:** 62 suites, 62 reporting, **1277 oks**, 10 parallel jobs, 96.5s
  wall for the suite step alone.
- **JavaScript:** `node --test js/test/*.mjs` — **737 tests, 0 suites
  (flat), 737 pass, 0 fail**.

## Invariant 9 target for this build

Gate wall-clock must not grow more than 10% against the 115.0s mean above —
i.e. must stay under ~126.5s for the same machine, same job count, same
`--fast` flag (off).
