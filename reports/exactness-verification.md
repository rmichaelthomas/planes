# Exactness and `sine` Verification (§10.2)

Run on the branch, before merge. Base `ed7a15d`.

**There is no `scripts/verify-exactness.mjs`, and that is deliberate.** §10.2
asks for one; `scripts/ci.sh`'s retirement rule — applied one PR ago, at Rob's
instruction, and now enforced by `test_gate.py` across `.py`, `.mjs`, `.js`,
`.ts` and `.sh` in both spellings — says a build's verification script
graduates into a suite or is deleted. Writing one would fail the gate on the
commit that added it. So every assertion below lives in a suite `ci.sh` runs on
every commit, and this table is the record of the gate having run, not
something to re-run. The suites are the check.

- `test_exactness.py` — 36 tests
- `js/test/exactness.test.mjs` — 24 tests

**All 60 pass. `ci.sh` exits 0: 57 suites / 1160 oks, 362 JS tests, ruff, mypy
on 92 source files.**

## A. Property — BLOCKING

| Check | Where | Result |
|---|---|---|
| exact ⊕ exact stays exact, in every arithmetic operation | `test_exact_combined_with_exact_stays_exact`, JS `exact combined with exact stays exact` | PASS |
| approximate propagates through add, subtract, multiply, divide, negation, both operand orders | `test_anything_touching_an_approximate_value_is_approximate` + JS twin | PASS |
| the entry point survives 200 subsequent exact operations | `test_the_entry_point_survives_a_long_chain_of_exact_operations` + JS twin | PASS |
| the entry record is shared by reference, not copied per operation | `test_the_entry_point_is_shared_by_reference_not_copied` + JS twin | PASS |
| a value carried through a collection keeps the property | `test_an_approximate_value_carried_through_a_collection_is_still_approximate` + JS twin | PASS |
| `round … to N places` returns EXACT | `test_round_to_places_returns_an_exact_value` + JS twin | PASS |
| a money example stays exact end to end (19.99 × 3, 8.25% tax, rounded to the cent) | `test_rounding_money_keeps_it_exact` + JS twin | PASS |
| rounding an approximate value does not launder it back to exact | `test_rounding_an_approximate_value_does_not_launder_it_back_to_exact` + JS twin | PASS |
| `==` between approximate values has no epsilon and no tolerance | `test_equality_between_approximate_values_has_no_tolerance` + JS twin | PASS |
| no tolerance constant exists in either numeric tower (code, not comments) | `test_no_epsilon_or_tolerance_constant_exists_in_the_numeric_tower` + JS twin | PASS |
| every corpus program's values stay exact — 50 programs, 1000+ numbers walked | `test_no_corpus_program_produces_an_approximate_value` | PASS |
| the rendering `~` still means non-terminating, NOT approximate | `test_the_tilde_in_rendering_means_non_terminating_not_approximate` + JS twin | PASS |
| past `MAX_DENOMINATOR` is still a refusal, not a new kind of approximate | `test_the_bound_still_refuses_rather_than_approximating` + JS twin | PASS |

## B. `sine` — BLOCKING

| Check | Where | Result |
|---|---|---|
| 0, 90, 180, 270, 360 — three land exactly on the right rational | `test_sine_at_the_quarter_turns` + JS twin | PASS |
| every result is approximate, **including `sine of 0`** | `test_every_sine_result_is_approximate_including_the_exact_looking_ones` + JS twin | PASS |
| `sine of -d` = `-(sine of d)`; `sine of (180-d)` = `sine of d`, at 11 angles | `test_sine_symmetry` + JS twin | PASS |
| argument reduction is exact at any magnitude — `sine of 360000030` **is** `sine of 30`, bit for bit | `test_argument_reduction_is_exact_at_any_magnitude` + JS twin | PASS |
| accuracy against a 50-digit series (not a double) is under 1e-16 across [-180, 180] | `test_sine_matches_a_high_precision_reference_to_the_stated_accuracy` | PASS |
| the result's denominator is bounded to 10^30 | `test_a_sine_result_carries_a_bounded_denominator` + JS twin | PASS |
| the stated parameters are the ones the code uses; the constant is within 1.3e-42 of π/180 | JS `the stated parameters are the ones the code uses` | PASS |
| `sine` of a non-number refuses, naming degrees | `test_sine_refuses_a_non_number` | PASS |
| everything downstream of a sine is approximate, and still names the entry | JS `sine propagates` | PASS |

## C. Agreement — BLOCKING

| Check | Where | Result |
|---|---|---|
| **121 inputs, three implementations, the same rendered digits** — negatives, every quadrant boundary, 360000030, ±1000000, fractional degrees | `test_all_three_implementations_agree_bit_for_bit_on_sine` | PASS |
| a 17-expression battery agrees on BOTH the text and the property, in all three | `test_the_three_implementations_agree_on_text_and_exactness` | PASS |
| both analysers report the same approximation routes for the whole `paint/` corpus | `test_both_analysers_agree_on_the_approximation_routes` | PASS |

Not "agree to twelve digits" — the same digits. The three implementations do
integer arithmetic scaled by 10^50 with one rounding rule, so bit-identity is
structural rather than hoped for.

## D. Invariants — BLOCKING

| # | Invariant | How | Result |
|---|---|---|---|
| 1 | exactly one builtin added, 10 → 11 | `test_sine_is_unary_…`; `grammar/vocabulary.json` diff is **one added line** | PASS |
| 1 | `grammar/vocabulary.json` is the only authored grammar file changed | `vocabulary.planes`, `errors.json`, `rules.json` are projections regenerated by `grammar_gen.py --check`; `core.json` and the message data untouched | PASS |
| 2 | `sine` is unary; every builtin is unary | `test_sine_is_unary_and_the_builtin_count_moved_by_exactly_one` | PASS |
| 3 | three implementations agree bit-for-bit, and on the property | category C | PASS |
| 4 | no implementation calls a host trigonometric function | `test_no_implementation_reaches_for_a_host_trigonometric_function` — every `.py`, `.mjs` and `.planes` under the repo, **comments stripped**, four renderer files allowlisted by name with the reason | PASS |
| 5 | `sharedTargets` unchanged; no host gained a trig target | `test_the_foreign_route_was_not_the_delivery_mechanism` | PASS |
| 6 | `round … to N places` returns exact; corpus money stays exact | category A | PASS |
| 7 | no corpus program's output changes except `bloom.planes` | `test_corpus.py` (50 programs, unchanged); bloom's change is Phase 4 and deliberate | PASS |
| 8 | Host method count stays 7; no drawing verb changed | `js/test/drawing_invariants.test.mjs` | PASS |
| 9 | `PI_OVER_180` and the series depth are byte-identical across implementations | the literals in `planes_num.py`, `js/planes_num.mjs`, `grammar/interp.planes`; category C proves the consequence | PASS |
| 12 | no square root crept in | the only `sqrt` in the diff is a comment explaining why it is the harder case; §253 stays a fast follow | PASS |

## E. Surface, and `why`

| Check | Where | Result |
|---|---|---|
| bloom's computed surface reports approximate values **without running it** | `test_the_surface_says_bloom_produces_approximate_values_without_running_it` + JS twin | PASS |
| turtle's and snake's do not | `test_the_surface_says_turtle_and_snake_do_not` + JS twin | PASS |
| the route names the path: `(top level) → wave → cosine → sine` | same tests | PASS |
| importing a module that *can* approximate is not producing one | `test_importing_a_module_that_can_approximate_is_not_producing_one` | PASS |
| a user function named `sine` shadows the builtin and the fact | `test_a_user_function_named_sine_shadows_the_builtin_and_the_fact` + JS twin | PASS |
| the route reported is the shortest one | `test_the_route_is_the_shortest_one_and_crosses_files` + JS twin | PASS |
| `why` on an approximate comparison names where each side stopped being exact | `test_why_on_an_approximate_comparison_names_the_entry_point` | PASS |
| the entry is named ONCE when both sides entered the same way — deduped by content, not object identity (S8's named trap) | `test_why_names_the_entry_once_when_both_sides_entered_the_same_way` | PASS |
| `why` says nothing about approximation when there is none | `test_why_says_nothing_about_approximation_when_there_is_none` | PASS |
| both implementations render the same `why` | `test_both_implementations_render_the_same_why` | PASS |

## Two things found by building, not by reading

1. **The specified algorithm does not work.** §5.4 bounds only the result and
   leaves the series on plain exact rationals. `sine of 60` then needs a
   denominator of 10^1224, past `MAX_DENOMINATOR`, and **refuses outright**;
   every input that did not refuse cost ~3ms in the JavaScript port. The
   working values are integers scaled by 10^50 instead — same digits, 190×
   faster, and `why` names four parameters rather than three.

2. **The self-hosted `round` and `whole` were dropping the property.**
   `round (sine of 30) to 4 places` came back EXACT in `grammar/interp.planes`
   and approximate in the other two. Found by the agreement battery, fixed in
   Phase 2.

## Stated corrections to the specification

- §5.2 says the first omitted term is under 2×10⁻¹⁹. At π/4 it is **4.62×10⁻¹⁷**,
  two orders of magnitude larger. Eight terms is the fixed decision and is
  kept; the arithmetic in its justification was wrong, and the code and `why`
  state the true bound.
- §5.4 says `why` reports three parameters. It reports **four** — the working
  precision is real and forced (above), and hiding it would be the silence
  this feature exists to remove.
- §10.2 asks for a verification script. See the note at the top.
