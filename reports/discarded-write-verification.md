# discarded-write verification

Build verification for "A discarded write says so, instead of writing zero." No throwaway `verify-*` script was written for this build — every check below was graduated directly into a permanent suite as it was written (`test_discarded_write.py`, `js/test/discarded_write.test.mjs`), so there is nothing for scripts/ci.sh's retirement rule to catch. This report captures the same evidence a one-time script would have, run directly against the committed suites and tools.

| # | Section | Check | Result | Detail |
|---|---|---|---|---|
| 1 | A | the A-Q9 program is refused, naming the variable and the fix | PASS | tag `discarded-write`, detail names `'total'`, fix names `let` and "bare assignment" |
| 2 | A | the corrected form (drop `let`) writes the correct sum | PASS | writes `7` |
| 3 | A | the check runs before any statement executes — no partial side effect | PASS | a `write` placed before the hazardous `let` never runs; `i.fs == {}` |
| 4 | B | condition 1 alone (let, not in a loop) does not fire | PASS | `[]` |
| 5 | B | condition 2 alone (in a loop, bare `=`) does not fire | PASS | `[]` |
| 6 | B | condition 3 alone (let in a loop, RHS does not self-read) does not fire | PASS | `[]` |
| 7 | B | condition 4 alone (let in a loop, self-reads, no enclosing binding) does not fire | PASS | `[]` |
| 8 | B | all four together is what fires | PASS | `["total"]` |
| 9 | soundness | a binding in one `if` branch does not leak into its sibling | PASS | found during this build's own self-review; `[]` after the fix (was `["amt"]` before) |
| 10 | soundness | a binding from a sibling statement in the same loop body still counts as an ancestor for a nested loop | PASS | `["total"]` |
| 11 | soundness | the hazard still fires through a nested `if` (no false negative from the branch-isolation fix) | PASS | `["total"]` |
| 12 | C | Python and JavaScript agree byte-for-byte on the hazard message | PASS | `js["message"] == str(py_error)` |
| 13 | C | Python and JavaScript agree the fixed form runs and writes the same sum | PASS | both `7` |
| 14 | C | the self-hosted interpreter (`grammar/interp.planes`, running on top of interp.py) raises the identical tag/detail/fix | PASS | all three fields equal |
| 15 | C | the self-hosted interpreter runs the fixed form clean | PASS | `status: "normal"` |
| 16 | C | all three implementations agree — the new shape | PASS | Python == JavaScript == self-hosted on (tag, detail, fix) |
| 17 | D | `let` still shadows locally when the hazard shape is absent (RHS does not self-read) | PASS | writes/shows `0`, unchanged from before this build |
| 18 | D | bare-assignment accumulation is completely unaffected | PASS | shows `15` |
| 19 | E | no `.planes` file under `corpus/`, `demo/`, `paint/`, or `grammar/` trips the check | PASS | 0 firings across 84 files, including `grammar/interp.planes` itself (the file this check's own self-hosted implementation now lives in) and the `demo/app` module graph |
| 20 | F | the reference work list stays at 0 | PASS | `errors_coverage.py`: 111 errors, 106 name a fix, 0 shortfall |
| 21 | F | the self-hosted work list stays at 0 | PASS | 113 raise sites (112 + this build's one new site), 73 name a fix, 0 shortfall |
| 22 | G | `grammar/errors.json` regenerated (never hand-edited) | PASS | `grammar_gen.py --check` clean; new entry `interp.discarded-write.check_discarded_writes` |
| 23 | G | `grammar/vocabulary.json`'s `binding_semantics.hazard` states the new, refused behaviour | PASS | mentions `discarded-write` and "refused"; `test_binding_semantics_section_matches_the_language` asserts both |
| 24 | invariant | exactly one new error tag; the Host interface, `grammar_gen.py`, and every renderer are untouched | PASS | `git diff --stat` — no changes to `host.py` / `js/host.mjs` / `grammar_gen.py` / `js/paint/*.mjs` |
| 25 | invariant | `core_check.py` — no new keyword or builtin outside the declared core | PASS | still 28/32 keywords (excluded `let`, `rule`, `when`, `why`), 10/11 builtins (excluded `sine`) |
| 26 | invariant | full gate green, counts risen only by this build's own new tests | PASS | 59 suites / 1191 Python oks (was 58/1172); 398 JS tests (was 385); `ruff`/`mypy` clean |

**26/26 checks passed.**

No blocking failures (sections A, B, C, D all pass).

## Where the check lives (§2.4)

**Detection is pure and lives in `parser.py` / `js/parser.mjs`** (`find_discarded_writes` / `findDiscardedWrites`), operating on the already-parsed AST with its own scope-tracking structure (`_WriteScope` / `WriteScope`) — new machinery, since `parser.py`'s existing `known_funcs`/`prescan_funcs` track function *names and arities* only, nothing about variable bindings. It is sound: proven by mirroring `interp.py`'s actual runtime scoping exactly rather than approximating it — a frame opens only at `for each` (matching `eval_foreach`'s fresh `Env(env)` per iteration) and at a function body (matching `invoke`'s fresh `Env`); `if`/`when`/an `or fail ... as tag:` handler get no frame in the *runtime* env either (`interp.py`'s own comment on the `If` case: "the no-child-scope choice if/else already makes"), but the *static* walk still opens a throwaway child frame per branch, discarded once that branch is walked — not to mirror a runtime frame that doesn't exist, but because the branches are mutually exclusive and a name only one of them binds must not read as bound to its sibling or to what follows (the same reasoning `shapes.py`'s own `consts.child()` per branch already states). This was found and fixed during this build's own self-review (§9 below).

**Raising is not pure, so it happens in `interp.py` / `js/interp.mjs`**, the one place on each side that already owns `PlanesError` — `find_discarded_writes` cannot raise it itself without `parser.py` importing `interp.py`, which would cycle (`interp.py` already imports `parser.py`; this is the identical reason `lexer.py`'s `GrammarDataError` exists rather than reusing `PlanesError`, stated in that class's own docstring). `Interpreter.run` / `Interpreter.run_file` (Python) and `Interpreter.run` / `checkDiscardedWrites` called from `modules.mjs`'s `hoistAndRun` (JavaScript) call the check immediately after parsing each file and before hoisting or executing a single statement — refused before the wrong answer can be produced, not caught after.

**The self-hosted port lives in `grammar/interp.planes`**, alongside every other `fail ... as <tag>` site, using a functionally-threaded scope chain (Planes has no mutable closure) rather than reflection (Planes has none) — an explicit per-node-kind dispatch over the expression node kinds `grammar/parser.planes` actually produces.

## Phase 5's sweep, in full

0 firings across 84 `.planes` files: every file in `corpus/` (50), `demo/` (including the `demo/app` module graph, checked through the same loader `run_file` uses), `paint/`, and `grammar/` (`interp.planes`, `parser.planes`, `lexer.planes`, `json.planes` — including this build's own ~250 new lines in `interp.planes`). No stop-and-report was needed.

## Corpus (§4, Phase 4)

No new corpus file was added. The corrected form — accumulation across a loop with bare `=` — is already well represented: `corpus/list-stats.planes`, `corpus/ledger.planes`, `corpus/histogram.planes`, and `corpus/moving-average.planes` all demonstrate it. Per the prompt's own instruction, the broken (`let`) form was not added anywhere.
