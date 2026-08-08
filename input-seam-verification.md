# Horizon Phase 2 Build 1 — the input-event seam — verification (§6.2)

`scripts/verify-input-seam.mjs` ran locally as this build's one-time evidence
run (all 7 assertions below passed) and was then deleted per this repo's own
`test_gate.py` rule (C6, Ruling 3 — see `test_world_kernel_verification.py`'s
own module docstring for the precedent this build followed): "a verification
script graduates into a suite or is deleted when its build merges." Every
durable assertion it made now lives in a permanent suite `scripts/ci.sh` runs
on every future build, listed below in place of the deleted script's own
pass/fail table.

| assertion | graduated into | result |
|---|---|---|
| A. empty-batch identity — JS current tree vs. HEAD baseline (60 ticks) | one-time evidence run, not re-run by CI (see note) | PASS |
| A. empty-batch identity — Python current tree vs. HEAD baseline (60 ticks) | one-time evidence run, not re-run by CI (see note) | PASS |
| A (durable form). `advance()`/`step()` with no events always equals an explicit empty list | `test_world_runtime.py::test_advance_with_no_events_matches_advance_with_an_explicit_empty_list`, `test_world_kernel.py::test_step_with_no_events_matches_step_with_an_explicit_empty_list`, `js/test/world_runtime.test.mjs` "advance() with no events matches advance([])...", `js/test/world_kernel.test.mjs` "step() with no events matches step([])..." | PASS |
| B. event applies deterministically, exactly one field changes | `test_world_kernel.py::test_a_nudge_event_changes_exactly_situation_x_deterministically`, `js/test/world_kernel.test.mjs` "a nudge event changes exactly situation.x, deterministically" | PASS |
| C. cross-implementation determinism with a non-empty event batch | `test_world_kernel_conformance.py::test_python_and_js_agree_on_a_kernel_soak_with_a_nudge_event` | PASS |
| D. worker plumbing — acknowledgedInputSequence matches, delta payload reflects the event | `js/test/world_renderer_worker.test.mjs` "SimulationWorkerHandle: an 'input' message WITH an event payload changes the next delta's payload deterministically" | PASS |
| Invariant 4 — wrong-arity `advance` refuses with a named error | `test_world_runtime.py::test_a_program_declaring_advance_with_the_wrong_arity_refuses_at_construction`, `js/test/world_runtime.test.mjs` "a program declaring advance with the wrong arity refuses at load" | PASS |
| Backward compatibility — a bare-sequence `"input"` message (no event payload) is still a true no-op on the semantic tick | `js/test/world_renderer_worker.test.mjs` "an 'input' message is acknowledged on the next delta's acknowledgedInputSequence, without altering the semantic tick" (pre-existing test, unmodified, still green) | PASS |

7/7 original checks passing. A and C are hard blockers per the build prompt — both pass.

**Note on A's HEAD-baseline form:** `scripts/verify-input-seam.mjs` compared
this branch's empty-batch output against a `git worktree` checkout of `main`
(the pre-seam commit) — a one-time, PR-specific proof that this build did not
silently perturb the self-driving path, not an ongoing property ("matches a
frozen historical commit" stops being meaningful once this branch merges and
becomes `main` itself). Its durable, forward-looking form — "the `events=[]`
default always agrees with an explicit empty list, for as long as this
default exists" — is what graduated into the permanent suites above, plus
the full pre-existing world-model suite (147 Python tests, 121 JS tests, all
of which call `advance`/`step` with no events and remain green unmodified).

## Full suite results

- Python (`test_world_runtime.py`, `test_world_kernel.py`,
  `test_world_runtime_conformance.py`, `test_world_kernel_conformance.py`,
  `test_world_kernel_verification.py`, `test_retention_tail_verification.py`,
  `test_world_delta*.py`, `test_world_ir*.py`, `test_world_numeric_bridge*.py`,
  `test_world_event_log.py`, `test_world_recovery.py`, `test_world_snapshot.py`,
  `test_world_source_map.py`, `test_world_emission.py`): **147/147 passing**.
- Python, full `-k world` sweep across the repo: **143/143 passing** (run
  before the graduation tests below were added; re-run above covers those).
- JavaScript (`js/test/world_runtime.test.mjs`, `js/test/world_kernel.test.mjs`,
  `js/test/world_delta.test.mjs`, `js/test/world_ir.test.mjs`,
  `js/test/world_snapshot.test.mjs`, `js/test/world_recovery.test.mjs`,
  `js/test/world_emission.test.mjs`, `js/test/world_event_log.test.mjs`,
  `js/test/world_numeric_bridge.test.mjs`, `js/test/world_renderer_worker.test.mjs`):
  **121/121 passing**.
- `test_gate.py`: 18/19 passing. The one failure
  (`test_no_verification_script_exists_for_the_gate_not_to_run`, flagging
  `scripts/verify-cut-cost.py`) is a **pre-existing failure on `main`**,
  unrelated to this build (that script shipped in PR #89, is untouched by
  this branch, and fails the identical assertion when checked out on `main`
  directly) — noted here, not fixed, since it is outside this build's file
  inventory.

## Invariants

1. Empty-batch identity — held (see A above).
2. Cross-implementation determinism — held, extended to cover input (C above).
3. No language keyword — held; `git diff --name-only main` shows no
   lexer/parser/grammar file.
4. Arity contract — held (see above).
5. Timed-span integrity — held; `test_b_the_timed_span_in_step_never_calls_a_sink_by_static_inspection`
   and `test_d_no_gc_call_between_the_two_perf_counter_reads_in_step` both
   updated for `step`'s new signature and still pass.
6. Single-subject projection preserved — held; the worker still projects
   exactly one semantic subject (`reso-tide-walker-1`) per tick.
