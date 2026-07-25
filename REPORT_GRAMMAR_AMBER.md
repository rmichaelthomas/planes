# Grammar as Loadable Data, and Amber at the Parser's Four Guess Sites — Session Report

**Date:** July 25, 2026
**Session type:** Feature build, Tier 4 (addendum v4.2 §69.1 grammar-as-data, §69.5 scoped amber).
**Branch:** `feat/grammar-as-data-and-scoped-amber`, off `main` at `08b051e`.
**Mandate:** Ship the language's vocabulary as one loadable file instead of five scattered locations (one hand-duplicated), and make the parser refuse — at parse time, by name-table arity — at the four sites it currently resolves silently by rule.
**Result:** Built. 523/523 tests passing (481 pre-build + 42 new). `ruff check .` and `mypy .` both clean. `audit_locked_vs_built.py` exits 0 at every commit in this branch. `grammar_gen.py --check` exits 0. The verification gate's blocking sections (A, C, D, E, H) all PASS.

---

## 1. Phases Completed

| Phase | What shipped | Commit |
|---|---|---|
| 0 | Baseline: `audit_locked_vs_built.py`, full suite (481), parse-time benchmarks, AST fixtures pinned | `ed60d93` (plus a standalone pre-existing hardening fix, `cadf8be`, committed to `main` first at Rob's direction — see §7) |
| A | `grammar/vocabulary.json` as source of truth; `lexer.py`/`parser.py` load it; `audit_locked_vs_built.py`'s `check_keyword`/`check_builtin` rewritten in the same commit; anti-drift grep guard | `be97721` |
| B | Arity in the name table (`prescan_funcs` returns `{name: arity}`); the `read_name_until` defect fixed and renamed `read_multiword_name` | `8b744c7` |
| C | Amber: `PlanesAmbiguity`, all four sites, messages as data in `grammar/messages/amber.json`; two real ambiguities found and fixed in existing fixtures (§4) | `f778347` |
| D | `grammar_gen.py`: generated `grammar/rules.json` and `grammar/errors.json`, `--check` mode, `scripts/ci.sh` | `0a03f64` |
| Gate | `verify_grammar_and_amber.py`, assertions A–I | `c9245ce` |
| E | This report | — |

### Files created

`grammar/vocabulary.json`, `grammar/rules.json`, `grammar/errors.json`, `grammar/messages/amber.json`, `grammar/README.md`, `grammar_gen.py`, `test_grammar_data.py`, `test_amber.py`, `verify_grammar_and_amber.py`, `scripts/ci.sh`, `ast_fixtures_baseline.json`, `grammar-as-data-benchmarks-pre.md`, `grammar-as-data-benchmarks-post.md`, `grammar-amber-verification.md`, this file.

### Files modified

`lexer.py` (loads `KEYWORDS`/`TOKEN_SPEC`/`EFFECT_KINDS` from the vocabulary file), `parser.py` (loads `BUILTIN_NAMES`/`FIELD_NAME_KINDS`; arity; amber; the `read_multiword_name` fix), `audit_locked_vs_built.py` (vocabulary checks rewritten; plus a standalone, pre-existing `with`/`plus` evidence-tightening fix — §7), `test_names.py` and `test_shapes.py` (two fixtures rewritten to disambiguate — §4), `demo/app/net.planes` (same).

### Files read, not modified

`interp.py`, `rules.py`, `shapes.py`, `modules.py`, `host.py`, `render.py`, `planes_num.py`, `shapes_cli.py` — none needed a change; `grammar_gen.py` reads all of them mechanically for `errors.json` (§5).

---

## 2. The Audit, Before and After Phase A

**Before Phase A** (on `main` at the `cadf8be` baseline, `check_keyword`/`check_builtin` still regexing `KEYWORDS`/`BUILTIN_NAMES` literals directly out of `lexer.py`/`parser.py`):

```
========================================================================
BUILT vs LOCKED — audit of corpus claims against actual code
repo root: <repo>
========================================================================
[... 22 constructs, all BUILT ...]
[BUILT    ] first                        (lock: v3.0 §48)
        lexer.py:52 (in KEYWORDS)
        interp.py:689 (eval_binop first branch)
[... ]
[BUILT    ] normalize builtin            (lock: §107)
        parser.py:~9 (in BUILTIN_NAMES)
========================================================================
All locked constructs have code evidence. No drift.
========================================================================
```
Exit 0, all 22 constructs BUILT.

**The failure mode #5 moment** — after A.2 (vocabulary loading wired into `lexer.py`/`parser.py`) but *before* A.3 (audit tool rewritten), run to confirm the prompt's own prediction rather than take it on faith:

```
[NOT BUILT] first                        (lock: v3.0 §48)
        MISSING: keyword(first)
        interp.py:689 (eval_binop first branch)
[...]
[NOT BUILT] normalize builtin            (lock: §107)
        MISSING: builtin(normalize)
========================================================================
LOCKED BUT NOT BUILT — 2:
   - first  (v3.0 §48)
   - normalize builtin  (§107)
```
Exit 5. Exactly the predicted failure: two real, working, tested features reported absent because the tool's regex had nothing left to match. This state was never committed — A.3 landed in the same commit as A.2.

**After Phase A** (A.2 and A.3 together, `be97721`):

```
[BUILT    ] first                        (lock: v3.0 §48)
        grammar/vocabulary.json:65 (in keywords)
        interp.py:689 (eval_binop first branch)
[...]
[BUILT    ] normalize builtin            (lock: §107)
        grammar/vocabulary.json:81 (in builtins)
========================================================================
All locked constructs have code evidence. No drift.
========================================================================
```
Exit 0, all 22 constructs BUILT, every pointer openable — now pointing into `grammar/vocabulary.json` for the two checks that moved.

`audit_locked_vs_built.py` exits 0 at every commit in this branch (verified directly, not assumed — `git log` shows five commits on this branch; the tool was re-run after each).

---

## 3. Generated Counts

From `grammar/vocabulary.json` (hand-edited, source of truth):

| Table | Count |
|---|---|
| Token classes | 7 |
| Keywords | 32 |
| Builtins | 8 (all arity 1) |
| Effect kinds | 7 (4 distinct boundaries) |
| Field-name token kinds | 14 |
| Positional words (descriptive only) | 6 |

From `grammar_gen.py`'s output (generated, checked by `--check`):

| File | Count |
|---|---|
| `grammar/rules.json` — form inventory | 26 `parse_*`/`paren_is_arglist` forms |
| `grammar/errors.json` — error/message entries | 82 (29 `parser.py`, 39 `interp.py`, 14 `rules.py`) |
| `grammar/errors.json` — distinct tags | 69 |
| `grammar/messages/amber.json` — templates | 6 (4 sites, 2 with an unknown-arity variant: sites 2 and 3) |

`shapes.py`, `modules.py`, `host.py`, `render.py`, `planes_num.py`, and `shapes_cli.py` contribute **zero** entries to `errors.json` — confirmed by direct read (§5), not by the generator's silence alone.

---

## 4. Amber's Fire Rate, and the Two Latent Ambiguities It Found

Fire rate over every `.planes` file in the repo, after fixes: **zero**, across all 29 files (8 named root-corpus files + 20 valid demo/ module-graph entry points; one demo file, `demo/cycle/*`, is a deliberately cyclic fixture and not a valid standalone entry point, so it is excluded from this count the same way `test_module_cycle_is_an_error_not_a_hang` treats it). Well under the "more than one site per file" ceiling that would have triggered a stop-and-report on aggressiveness (§10 failure mode 6) — the ceiling was never approached.

Getting to zero required resolving two real ambiguities amber correctly found while proving the corpus silent, both **checked with Rob before either fixture was edited** (per the build prompt's own hard line: a semantic-adjacent finding is a stop-and-report, not a licence to narrow the rule quietly):

**Site 3 — `demo/app/net.planes`, `ask (api base) + "/" + name + "/json"`.** `ask` has arity 1 (all builtins do), so `ask((api base) + "/" + name + "/json")` and `ask(api base)` (with `+ "/" + name + "/json"` binding outside the call) are both shaped like a valid single-argument call — nothing in the source said which was meant; the parser had always silently picked the first reading via `paren_is_arglist`'s lookahead. The identical pattern also lived in `test_names.py`'s `test_parenthesised_argument_continuing_an_expression`. Rob's decision: keep D4 exactly as ruled, fix the two fixtures. Both rewritten to `ask ((api base) + "/" + name + "/json")`, making the intended reading explicit rather than implicit.

**Site 1 — `test_shapes.py`'s inline rename fixture.** `use b with greet as greet b` renamed `b`'s `greet` to `greet b`, which shares the prefix `greet` with the name still in scope from `a`. `show greet b` then had two readings: one call to `greet b`, or the value `greet` followed by a separate statement `b`. Renamed the alias to `b greet` instead — same test intent (rename resolves the collision), no shared prefix.

A third, closely related finding surfaced and was fixed **without** escalation, because it was an outright bug rather than a design tension: an early version of the site-4 (rename clause) check applied the same ambiguity test to the *new* alias half of a rename, not just the *old* (looked-up) half. Since `modules.names_in_graph` already registers a rename's target as a known name for the rest of the file being parsed, checking the alias against `known_funcs` flagged every rename whose alias happened to still share a prefix with the name it replaced — which is the common case, not the rare one. Caught immediately by `test_rename_replaces_rather_than_aliases` (a real, working, previously-passing test) failing; fixed by checking only the `old` half, which is the actual lookup.

No other latent ambiguity was found. Site 2 (juxtaposition) correctly refuses on a purpose-built synthetic case (`ask main`, where both are arity-relevant known functions) but never fires anywhere in the real corpus.

---

## 5. Backlog: Untested Error Tags

From `grammar/errors.json`'s `tags` index, cross-referenced against every `test_*.py` file for a literal occurrence of the tag string (a coarse proxy — a test can exercise a tag's code path without ever asserting the tag literally, so this likely over-reports; it cannot under-report, since a tag that never appears as a string anywhere in the test suite is definitely never asserted on directly):

- `unknown-operator` (`interp.py:944`, `interp.py:969`) — an operator string apply_op/arith don't recognize; likely unreachable through the parser today (every operator apply_op sees was tokenized as a known OP), which would make it a defensive branch, not a live gap.
- `unknown-builtin` (`interp.py:765`) — similarly likely defensive: `BUILTIN_NAMES` is the only source of names reaching this path.
- `not-a-collection` (`interp.py:782`) — a `for each` over a non-list/non-record value; plausibly reachable (`for each x in 5:`) and worth a real test.

None of these are this build's scope to fix — they predate it and are unrelated to grammar-as-data or amber. Recorded here because `grammar/errors.json`'s `tags` index is what makes this kind of gap visible for the first time; noting it is the report's job per §8.

---

## 6. Anything the Build Disproved About This Prompt

- **§1.2's "22 PlanesSyntaxError raise sites in parser.py" was already off by one at `08b051e`, before this build touched anything** — `git show 08b051e:parser.py | grep -c "raise PlanesSyntaxError("` gives 23, not 22 (verified directly, not trusted from the prompt). A small, harmless miscount in the prior session's manual read, not something this build introduced. After Phase C: 29 (the same 23, unchanged, plus 6 new `PlanesAmbiguity` raise sites).
- **§1.2's "36 `PlanesError` constructions in interp.py" was also an undercount at `08b051e`: 39, not 36** — `interp.py` is byte-identical to `08b051e` throughout this build (`git diff 08b051e -- interp.py` is empty), so this is purely a prior-session miscount, not drift. `grammar_gen.py`'s AST walk gives 39 mechanically, matching `grep -c "PlanesError("` minus the one line that is the class definition itself.
- **"Roughly 14 message shapes in rules.py" holds exactly**, once `Violation.render`'s two branches and `Violation._render_vacuous`'s three are extracted mechanically (`grammar_gen.py`'s `_extract_branches`) rather than read by eye: 7 (`RuleConflict`) + 2 (`RuleNotSupported`) + 2 (`render`) + 3 (`_render_vacuous`) = 14.
- **`shapes.py`, `modules.py`, `host.py`, `render.py`, `planes_num.py`, `shapes_cli.py` construct zero of the five target exception classes.** The prompt's own provenance flagged these six files as "not read this session" and anticipated they'd add to the error-template count. They don't, for `errors.json`'s purposes — each raises its own distinct exception type (`ModuleError`, `HostError`, `ValueError`, `TypeError`, `ZeroDivisionError`, `Inexact`, `NotImplementedError`), none of which is `PlanesError`/`PlanesSyntaxError`/`PlanesAmbiguity`/`RuleConflict`/`RuleNotSupported`. This is a correction, not a gap in the generator: confirmed by direct read of all six files, not by the walker's silence alone.
- **Site 3's amber rule, applied literally, is not compatible with the existing corpus without fixture changes.** The prompt anticipated amber might be "too aggressive" in the abstract (failure mode 6) and named a one-site-per-file ceiling as the trigger for stopping; what actually happened was narrower and sharper — amber fired correctly, at exactly the rate the ceiling allows (well under one site per file, in fact zero once fixed), but on a real, working, intentionally-authored idiom (`unary-function (nested-call) + concatenation`) that appears independently in a demo fixture and a test. This wasn't a case of the rule being wrong; it was a case of the rule being right about something the corpus hadn't been written to expect. Recorded for the next checkpoint: D4's arity-only criterion is confirmed correct as ruled, but any future construct with unary-arity built-ins should expect this exact shape of ambiguity when parenthesized sub-calls precede a trailing operator.
- **A pre-existing, uncommitted local change to `audit_locked_vs_built.py` was found in the working tree at session start** (§7) — unrelated to this build's scope, but touching the exact file Phase A also needed to modify. Not something the prompt could have anticipated; resolved with Rob before Phase 0 began.

---

## 7. A Note on Session Start

The working tree had an uncommitted, unrelated change to `audit_locked_vs_built.py` at the start of this session: tightening `record_update_with` and `plus_operator`'s evidence requirements to match `when`'s two-part standard (an AST node **and** an interpreter branch, not either alone). Two cosmetic lint issues in that diff (two line-length wraps, one ambiguous loop-variable name) were fixed before committing. Rob's direction: commit it to `main` standalone before starting the grammar/amber build, since it's self-contained and touches the same file Phase A needed. Committed as `cadf8be`, confirmed green (suite, ruff, mypy, audit) before Phase 0 began.

---

## 8. What's Next

This branch is ready for the human clarity read (build prompt §11.3): four amber refusal messages, against real ambiguous programs, need one read from Rob — do they read as help, or as an obstacle? That is not machine-checkable and this report does not attempt to substitute for it. Per this repo's established pattern (PRs #6, #7, #8), the branch is pushed and a PR opened; merge waits on Rob's explicit reply.
