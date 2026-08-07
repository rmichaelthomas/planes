# Horizon Phase 1: the retention tail — verification gate (§6.2)

| assertion | result |
|---|---|
| test_a_why_machine_is_byte_identical_changes_active_vs_bypassed | PASS |
| test_b_python_and_js_chain_hash_agree_for_both_retention_configurations | PASS |
| test_c_seal_surface_unchanged_fingerprint_refusal_released_count | PASS |
| test_d_no_gc_call_between_the_two_perf_counter_reads_in_step | PASS |
| test_f_interp_py_and_js_interp_mjs_changes_confined_to_seal | PASS |
| test_f_streamed_and_joined_hash_produce_the_same_digest | PASS |

6/6 passing.

A/B/C/D/F failure blocks the PR. All pass.

E (the tail-gate finding) is not run here — it is a property of the full multi-minute soak, recorded in horizon-retention-tail-results.md instead. See that file's own §4 pass condition 1 for its answer.
