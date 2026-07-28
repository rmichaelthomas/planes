# number-of-verification.md

Automated verification for A-Q19 — `number of` and the corrected `cannot-combine` fix clause.

The table below is a one-time snapshot from `scripts/verify-number-of.py`,
run during this build (§8.2). The script itself is not committed: the
retirement rule (`test_gate.py::test_no_verification_script_exists_for_the_gate_not_to_run`)
requires a verification script to graduate its durable assertions into a
suite the gate runs, or be deleted, before the build merges. Sections A, B,
and C live on in `test_numbers.py`; the three-way agreement sweep (D) lives
on as `test_number_of_agrees_across_three_implementations_on_every_case` in
`test_builtin_guards.py`; the invariants (E) and corpus check (G) were
already covered by existing suites this build's changes also satisfy.

| section | check | result | detail |
|---|---|---|---|
| A | write 145 -> read -> number of -> +1 == 146 | PASS |  |
| A | read "145.48" -> number of -> +1 == 146.48 | PASS |  |
| B | number of "5" == 5 | PASS |  |
| B | number of "145.48" == 145.48 | PASS |  |
| B | number of "-3" == -3 | PASS |  |
| B | number of "-0.5" == -0.5 | PASS |  |
| B | number of "0" == 0 | PASS |  |
| B | number of "  5  " == 5 | PASS |  |
| B | number of "\t12.5\n" == 12.5 | PASS |  |
| C | number of "" refused as not-a-number | PASS |  |
| C | number of "abc" refused as not-a-number | PASS |  |
| C | number of "1e5" refused as not-a-number | PASS |  |
| C | number of "1/3" refused as not-a-number | PASS |  |
| C | number of "~0.333333333333" refused as not-a-number | PASS |  |
| C | number of 5 refused as not-text | PASS |  |
| C | number of true refused as not-text | PASS |  |
| C | number of nothing refused as not-text | PASS |  |
| C | number of [1, 2] refused as not-text | PASS |  |
| C | number of { a: 1 } refused as not-text | PASS |  |
| C | ~-prefix names its own reason | PASS |  |
| D | number of "5" | PASS |  |
| D | number of "145.48" | PASS |  |
| D | number of "-3" | PASS |  |
| D | number of "-0.5" | PASS |  |
| D | number of "0" | PASS |  |
| D | number of "  5  " | PASS |  |
| D | number of "\t12.5\n" | PASS |  |
| D | number of "" | PASS |  |
| D | number of "abc" | PASS |  |
| D | number of "1e5" | PASS |  |
| D | number of "1/3" | PASS |  |
| D | number of "~0.333333333333" | PASS |  |
| D | number of 5 | PASS |  |
| D | number of true | PASS |  |
| D | number of nothing | PASS |  |
| D | number of [1, 2] | PASS |  |
| D | number of { a: 1 } | PASS |  |
| D | number of "abc" | PASS |  |
| D | 18 cases, 0 divergences | PASS |  |
| E | builtin count is 12 | PASS |  |
| E | number of is arity 1 | PASS |  |
| E | BUILTIN_NAMES agrees | PASS |  |
| E | write path unchanged (whole numbers stay numbers) | PASS |  |
| E | host stays at 7 methods | PASS |  |
| E | grammar_gen.py --check passes | PASS |  |
| E | README states 12 builtins | PASS |  |
| E | README builtin list matches vocabulary.json | PASS |  |
| F | cannot-combine names both directions | PASS |  |
| F | cannot-combine identical in JS | PASS |  |
| F | cannot-combine identical in self-hosted | PASS |  |
| F | reference work list is 0 | PASS |  |
| F | self-hosted work list is 0 | PASS |  |
| G | corpus/running-balance.planes exists | PASS |  |
| G | runs cleanly | PASS |  |
| G | effect surface is file-and-console | PASS |  |
| G | JavaScript agrees | PASS |  |

**56/56 checks pass.** 0 blocking failure(s) (sections A, C, D, E).
