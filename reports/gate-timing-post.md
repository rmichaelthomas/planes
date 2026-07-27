# Gate timing — after C4 / Phase A

Same machine, same conditions as `gate-timing-pre.md`: **Darwin 25.5.0,
arm64, 10 cores**, Python 3.14.6, node v22, ruff 0.16.0, mypy 2.3.0.

## Whole gate

| | before | after | |
|---|---:|---:|---|
| **`scripts/ci.sh` wall** | **≈ 491 s** | **47.5 s** | **10.3× faster** |
| test suites | 488.7 s | 44.4 s | |
| non-test steps | 2.15 s | 2.13 s | unchanged |
| suite files on disk | 54 | 54 | |
| suite files reporting | 52 | **54** | +2 |
| oks | 996 | **1064** | +68 |
| `node` spawns | 3602 | **1274** | −65% |
| `scripts/ci.sh --fast` | — | **10.0 s** | new |

Run twice for stability: 47.5 s and 48.3 s, both green, both 1064/54.

## Where the time went

Three changes, in order of what each returned.

**1. The suite stopped running itself twice — 294.8 s.**
`test_coverage.py::test_the_suite_does_not_touch_the_real_world` re-ran every
other suite as a subprocess to watch for filesystem leaks. That observation is
one `scripts/run_suites.py` already makes, because it is already running every
suite, so the runner makes it and hands the record over through an environment
variable it sets on the children it spawns. Run standalone, with no record,
the test re-runs the suites exactly as before. **The assertion is unchanged**;
it now watches the gate's real run rather than a second synthetic one, which
is the stronger of the two observations. `test_coverage.py`: **248.9 s → 0.5 s**.

**2. The cross-implementation cases batched — 44.9 s.**
`js/cli.mjs` gained `run-batch`, which calls the same `runOne` the per-case
`run` calls. `test_builtin_guards.py` sends its 481 distinct programs in one
process instead of 528. **47.5 s → 2.6 s.**
`scripts/verify_batch_equivalence.py` runs every case through both paths:
**481/481 identical**.

**3. The suites run in parallel — 149.5 s.**
Serial after (1) and (2) is 193.9 s; at 10 jobs it is 44.4 s. Three suites are
declared exclusive and run alone first, because they mutate state other suites
read (see the hermeticity audit in `REPORT_FAST_FOLLOW.md`).

## Per-suite wall time, serial (`PLANES_JOBS=1`, 193.9 s)

This is the honest per-suite cost; the parallel numbers are inflated by
contention and are not the basis for anything.

| seconds | cumulative | suite | in `--fast` skip |
|---:|---:|---|---|
| 32.67 | 16.9% | `test_js_render.py` | yes |
| 23.13 | 28.8% | `test_interp_effects_in_planes.py` | yes |
| 20.29 | 39.3% | `test_js_shapes.py` | yes |
| 15.95 | 47.5% | `test_js_metacircular.py` | yes |
| 11.26 | 53.3% | `test_why_in_planes.py` | yes |
| 10.59 | 58.8% | `test_js_interp.py` | yes |
| 10.30 | 64.1% | `test_corpus.py` | yes |
| 10.26 | 69.4% | `test_js_parser.py` | yes |
| 8.61 | 73.8% | `test_js_lexer.py` | yes |
| 7.63 | 77.7% | `test_js_json.py` | yes |
| 4.82 | 80.2% | `test_interp_statements_in_planes.py` | yes |
| 3.57 | 82.1% | `test_lexer_in_planes.py` | no |

The eleven suites above the 80% line are exactly the `--fast` tier, named in
`scripts/ci.sh` with each one's measured cost beside it.

## Non-test steps (unchanged)

| seconds | step |
|---:|---|
| 0.67 | `grammar_gen.py --check` |
| 0.65 | `core_check.py` |
| 0.30 | `mypy .` (93 source files) |
| 0.20 | `corpus_coverage.py` |
| 0.12 | `core_check.py grammar/json.planes` |
| 0.07 | `ruff check .` |
| 0.07 | `audit_locked_vs_built.py` |
| 0.06 | `errors_coverage.py` |
| **2.13** | **total** |

## What did not change

* No test's assertions. Two files *gained* a `__main__` runner, which is why
  the ok count rose by 68 — those tests already passed and were not counted.
* `js/cli.mjs`'s `run` subcommand. Every other suite still uses it.
* `PLANES_JOBS=1` reproduces the serial order and the same totals: 54 files,
  54 reporting, 1064 oks, 193.9 s.
