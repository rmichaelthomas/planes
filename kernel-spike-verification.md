# Horizon Phase 1 engine-kernel spike — verification gate (§10.2)

| assertion | result |
|---|---|
| test_a_python_and_js_delta_sequences_are_byte_identical_over_a_soak | PASS |
| test_a_semantic_hash_chain_is_unbroken_on_both_implementations | PASS |
| test_b_sink_cost_is_excluded_from_the_recorded_figure_by_measurement | PASS |
| test_b_the_timed_span_in_step_never_calls_a_sink_by_static_inspection | PASS |
| test_c_the_results_file_is_complete | PASS |
| test_d_the_read_only_core_files_are_untouched | PASS |

6/6 passing.

A/B/D failure blocks the PR. A/B/D all pass.
C failure blocks unless the architect accepts a documented gap. C passes.
