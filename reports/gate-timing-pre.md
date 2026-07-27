# Gate timing — baseline, `b173190`

Measured before any change in this build (C4 / Phase A.0). Nothing here is
taken from the build prompt; every figure is from a run on this machine.

**Machine:** Darwin 25.5.0, arm64, **10 cores** (`sysctl -n hw.ncpu`).
Python 3.14.6, node v22 (`/opt/homebrew/opt/node@22/bin/node`), ruff 0.16.0,
mypy 2.3.0. Suites run serially, one `python3` process each, as
`scripts/ci.sh` did at `b173190`.

**Instrument cost.** The `node`-spawn count comes from a shim on `PATH` that
appends a line to a counter file and `exec`s the real binary. Comparing a
shimmed and unshimmed post-change run puts the shim at ~1.8 ms per spawn, so
it inflates the 488.7 s baseline by roughly 6.5 s. The unshimmed baseline is
therefore about **482 s**. The shim is not committed to the default path.

## Whole gate

| | |
|---|---|
| test suites, serial | **488.7 s** |
| everything else | 2.2 s |
| **total** | **≈ 491 s** (~8.2 min) |
| suite files on disk | 54 |
| suite files reporting a result | **52** |
| oks | **996** |
| `node` process spawns, whole suite | **3602** |

The gate is the test suite. The eight non-test steps together are 0.45% of it.

## Per-suite wall time — the top of the distribution

54 suites, 488.7 s total.

| seconds | cumulative | suite |
|---:|---:|---|
| 248.86 | 50.9% | `test_coverage.py` |
| 47.49 | 60.6% | `test_builtin_guards.py` |
| 34.67 | 67.7% | `test_js_render.py` |
| 23.29 | 72.5% | `test_interp_effects_in_planes.py` |
| 21.47 | 76.9% | `test_js_shapes.py` |
| 16.56 | 80.3% | `test_js_metacircular.py` |
| 11.44 | 82.6% | `test_why_in_planes.py` |
| 11.29 | 84.9% | `test_js_interp.py` |
| 11.20 | 87.2% | `test_corpus.py` |
| 10.96 | 89.5% | `test_js_parser.py` |
| 9.23 | 91.4% | `test_js_lexer.py` |

The remaining 43 suites share 42.3 s between them.

## `node` spawns per suite

| spawns | suite |
|---:|---|
| 1801 | `test_coverage.py` |
| 528 | `test_builtin_guards.py` |
| 390 | `test_js_render.py` |
| 220 | `test_js_shapes.py` |
| 130 | `test_js_parser.py` |
| 126 | `test_js_interp.py` |
| 114 | `test_js_lexer.py` |
| 102 | `test_corpus.py` |
| 46 | `test_js_host.py` |
| 43 | `test_js_rules.py` |
| 40 | `test_js_shapes_derivation.py` |
| 13 | `test_js_shapes_cli.py` |
| 11 | `test_js_num.py` |
| 11 | `test_error_messages.py` |
| 8 | `test_js_hash.py` |
| — | 39 suites spawn none |
| **3602** | **total** |

## Non-test steps

| seconds | step |
|---:|---|
| 0.68 | `grammar_gen.py --check` |
| 0.67 | `core_check.py` |
| 0.27 | `mypy .` (91 source files) |
| 0.21 | `corpus_coverage.py` |
| 0.12 | `core_check.py grammar/json.planes` |
| 0.07 | `audit_locked_vs_built.py` |
| 0.07 | `ruff check .` |
| 0.06 | `errors_coverage.py` |
| **2.15** | **total** |

## The two hypotheses the prompt named

**Hypothesis 1 — the JavaScript comparisons spawn a process per case:
CONFIRMED, and a large undercount.** `test_builtin_guards.py` spawns exactly
528, as predicted from reading that one file. The prompt called that number a
lower bound for the repo, and it is: the repo-wide figure is **3602**, 6.8×
larger.

**Hypothesis 2 — the suite loop is serial: CONFIRMED**, and worth more than
predicted, because 10 cores sat idle for 8 minutes.

**Neither hypothesis names the actual hotspot.**
`test_coverage.py::test_the_suite_does_not_touch_the_real_world` runs
`subprocess.run([sys.executable, suite])` over **every other suite** to check
for filesystem leaks. The gate therefore executed the whole test suite twice.
That single test is **248.9 s of 488.7 s (50.9%)** and **1801 of 3602 spawns
(50.0%)** — its spawns are the nested suites' own, attributed to it because
the counter keys on the suite the runner launched. It is larger than every
JavaScript agreement suite combined, and no prior report in this repo names
it.

## A second finding from the same measurement

54 `test_*.py` files exist; **52** print a result line. `test_core_check.py`
(6 tests) and `test_interp_statements_in_planes.py` (62 tests) have **no
`__main__` runner**, so `python3 <file>` imports the module, runs nothing, and
exits 0. **68 tests sat inside a green gate without running.** Both pass when
executed — verified before changing anything — so this is 68 uncounted passes,
not 68 hidden failures. It is `REPORT_HOST_BOUNDARY.md` §5's failure mode,
found a second and third time, and it is why the 996 figure is not the number
this gate should report.
