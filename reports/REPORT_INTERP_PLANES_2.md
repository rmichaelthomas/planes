# S3c — `interp.planes` Build 2: Statements and Control Flow

Route B stage three, build 2. `grammar/interp.planes` now **runs programs**:
statements that sequence and branch, function bodies that are blocks, lexical
scoping, failure that propagates and is caught — checked throughout by agreement
with `interp.py` through the canonical value form and the show output.

Base `main` at `236c9fc`. Branch `feat/interp-planes-statements`. Eight phases
plus gate, one commit each. **813 tests green** (749 baseline + 64 new), all
gates clean.

---

## What shipped, phase by phase, against §A

| Phase | What | §A |
|---|---|---|
| 1 | **Lexical scoping** — the callee sees its definition env, not the caller's | A.1 |
| 2 | **The status record** — `eval-node`/`exec-stmt`/`exec-block`, the five rules | A.3, A.2 |
| 3 | **Branching** — `if`/`else`, `when` with match-and-bind patterns | A.2, A.3 |
| 4 | **Bindings and output** — `let`, scope-walking reassignment, `show` | A.5 |
| 5 | **`for each`** — statement + comprehension, `where`, lists and strings | A.3, A.7 |
| 6 | **Failure** — `or fail as`, `fail as tag` (Rules 2 and 3) | A.3 |
| 7 | **Function bodies as blocks** — interpreted recursion becomes possible | A.7 |
| 8 | **Whole programs + measurement** — the corpus through three Planes stages | A.6, A.7 |

The architecture (the load-bearing decision): a **status-threaded core**
(`eval-node`, `exec-stmt`, `exec-block`, `apply-function-node`) threads
`{ status, value, env, error }` per A.3, and the build-1 `eval` is a
**value-returning adapter** over it, re-raising a fail status as the host error
its tag names so the 66 build-1 tests reach the evaluator unchanged. Host
exceptions are used only at the leaf (catching a value-op failure to convert it
to a fail status) and at that adapter boundary; all propagation — give, fail,
runtime errors, Rule-1 pass-through — is the status record's job. This resolves
a tension the prompt did not flag (see *What this build disproved*).

---

## Phase 1: the divergence test, and the environment

**The inference held.** A.1 inferred, from build 1's report, that build 1's
`params + call-env` was dynamic scoping and `interp.py`'s `Env(fn.env)` was
lexical. Verified against `interp.py` before changing anything: `call` does
`inner = Env(fn.env)` — a fresh scope over the function's *definition* env — and
build 1 prepended parameters to the *caller's* env. Dynamic vs lexical, confirmed.

**The fix.** `apply-function` builds the callee frame from `globals-of(call-env)`
— the function bindings only, dropping every caller local — plus the parameters.
Functions stay globally resolvable (mutual recursion holds) with no stored
closure and no cyclic record.

**The divergence test.** `to inner of x: give x + secret` / `to outer of secret:
give inner of 1`, called as `outer of 5`. Under dynamic scoping `inner` saw
`outer`'s `secret` and returned `6` where `interp.py` raised `unknown-name`
(demonstrated by reverting the one line and re-running). Under lexical scoping
both fail `unknown-name`. It is the only shape that distinguishes the two, and
build 1's tests could not: its bodies had no locals to leak.

**Environment size, before and after.**

| | env at a 60-deep call chain |
|---|---|
| build 1 (dynamic) | **121** — grows ~2 per level |
| after Phase 1 (lexical) | **62** — flat (params + the fixed function set) |
| under recursion (Phase 8) | **2** — flat (`k` + `cd`) |

Confirmed by measurement, not inspection. The O(depth) growth is gone; no pruning
implemented, none needed (A.1).

**One build-1 test changed result, named:** `test_non_expression_body_fails_naming_build_2`
asserted that a multi-statement body fails `build-2-statements`. Phase 7 lifts
that limitation, so the test now runs the body and agrees with `interp.py`
(renamed `test_multi_statement_body_now_runs_build_2`). It asserted a temporary
limitation, not a bug, and is the only build-1 test whose result moved. All 65
others pass unmodified.

---

## The five rules of A.3, each pinned

Every rule is exercised by a test naming it, Rule 1 hardest.

| Rule | What | Test |
|---|---|---|
| **1** pass-through is early exit | a block does nothing after the first non-normal status | `test_rule1_passthrough_later_statements_do_not_run` — gives `1`, then a rebind to `999` that never runs; also `..._over_many_later_statements` |
| **2** give stops at the function boundary | a giving function returns a normal value to the caller | `test_rule2_give_resets_to_normal_at_function_boundary`, `test_give_stops_at_boundary_fail_does_not` |
| **3** fail crosses the boundary | a fail three call levels deep, caught by an `or fail` above all of them | `test_fail_propagates_across_call_levels_caught_above` |
| **4** the env rides in the record | bind `x`, read it back in a later statement | `test_rule4_env_rides_in_the_record` |
| **5** never read `value` on a non-normal status | after a failed assign, a later statement that would compute on it is pass-through — no crash | `test_rule5_no_value_read_after_fail` |

`demo/status_threading.planes` proved the idiom; build 2 is its first real
consumer, and the demo runs end to end through all three Planes stages (a
`RUNNABLE` corpus file).

---

## Whole programs through three Planes stages

`lexer.planes` → `parser.planes` → `interp.planes` (`execute-program`), the
interpreted program's `show` delegating to the host. `scripts/run_corpus_through_planes.py`
runs the corpus both ways and compares output.

**RUNNABLE: 24 / 28 build-1+2 programs. 0 divergences.** (54 corpus files, 26 N/A.)

Runnable programs include `gate.planes`, `probe/fold_tokens.planes` (a tokenizer
with `when`/`with`/nested `if`), `probe/selfhost/phase4_fixpoint.planes` (a
recursive reachability fixpoint), mutual recursion, `demo/association.planes`,
`demo/status_threading.planes`, and `probe/parser/nested_fail_propagation.planes`
(which *deliberately* ends in a `parse-error` fail — both sides agree on the tag).

**What blocks the other 4:**

| File | Blocked by |
|---|---|
| `foreign.planes`, `demo/fdiff/v1.planes`, `demo/fdiff/v2.planes` | a **foreign call** — the host boundary, build 3 |
| `probe/parser/cursor_scales.planes` | **recursion-too-deep** — interpreted recursion is shallower than the host's (the A.7 exposure, below) |

The 26 N/A are module-importing programs (module resolution is not build 2) and
negative parser fixtures (the amber ambiguity sites, the no-index-syntax file) —
programs that do not parse on either side, by design.

---

## §8 measurements, as numbers, with methods

All established at baseline / Phase 8 via `scripts/measure_interp_planes.py` and
`scripts/measure_frames_per_call.py`, never carried (A.7's opening note). Python
3.14.6, `recursionlimit` 1000.

| Measure | Value | Method |
|---|---|---|
| Host recursion ceiling, `if`-based | **245** (4 frames/call) | self-calling countdown, binary search on `recursion-too-deep` |
| Host recursion ceiling, `when`+`if` | **196** (5 frames/call) | same, `when`-dispatch shape |
| Interpreted **recursion depth** | **32** (35 host frames per interpreted call) | `to cd of k: if k <= 0: give 0; give cd of (k-1)` through `execute-program`, binary search |
| Interpreted **statement nesting** | **33** | N nested `if true:` blocks |
| Interpreted **expression nesting** | **139** | `1 + (1 + (…))` through the adapter `eval` |
| Full **pipeline** nesting | **23** | `nested_expr` through `evaluate-source` (all three stages) |
| Env at recursion depth | **2** | wrap `run-body`, read callee-env length |
| Env at a 60-deep call chain | **62** | same, mutual-recursion chain |

**The A.7 exposure, quantified.** Interpreted *recursion* (32) is far shallower
than interpreted *nesting* (139) or the host ceiling (245): each interpreted
call spends ~35 host frames — `eval-node` → `eval-call-node` →
`apply-function-node` → `run-body` → `exec-block` → `exec-stmt` → `run-stmt` →
`eval-node` … — on top of the host's own. A.7 predicted this ("interpreted
recursion is the exposure"); it is now a number. It was met, not raised:
`run-foreach` loops natively rather than recursing per item, so only the
interpreted program's own recursion consumes the ceiling, and `cursor_scales`
is the one corpus program that exhausts it.

---

## Does A.6's parse-bound finding still dominate?

**Yes, for nesting.** The full pipeline still tops out at 23 expression-nesting
levels, an order of magnitude below the evaluator's 139 — `parser.planes`'s
precedence cascade spends the frames, exactly as build 1 found. No build-2 phase
was blocked by parse depth: the language's statement constructs are shallow, and
`parser.planes` self-parses `interp.planes` (85 top-level nodes, agreeing with
`parser.py`) at three-quarters of a megabyte.

**But the binding constraint for real programs is interpreted recursion depth
(32), not parse depth.** `cursor_scales.planes` is blocked by the recursion
ceiling, not the parse ceiling. A.6's precedence-climbing rewrite would raise the
*nesting* limit; it would not help the *recursion* limit, which is the one a real
recursive program meets first. The parser build remains correctly deferred — but
the number to schedule it against is now recursion depth, and precedence climbing
is not the fix for that.

---

## Where `interp.py` was harder to reproduce than expected

- **`if`/`when` are statement-only at the surface.** `interp.py`'s `eval` has
  `If`/`When` cases, but the parser never produces them in expression position —
  `y = if c: 1 else: 2` does not parse. Those `eval` cases are reached only
  through `exec_stmt`'s fall-through (`return self.eval(stmt, env)`). So one
  status-threaded implementation of each serves both positions, reached from
  `run-stmt` through `eval-node`; the "expression" framing in the prompt is a
  property of `interp.py`'s internals, not of Planes source.
- **The `for each` child scope.** `interp.py` runs each item in `Env(env)`, so
  the loop variable and body-local lets are per-iteration while a reassignment of
  an outer variable walks to the parent and persists — the accumulator idiom.
  With an immutable threaded env this needed `rebind-outer`: reconstruct the outer
  env after each item from the body's env (reassignments applied, per-iteration
  additions dropped), keeping the env flat across the loop.
- **`when` equality is guarded, not lenient.** A match entry compares through the
  same guarded `equal()` that `==` uses, so a present field of the wrong type
  *fails* rather than silently not-matching. Reproduced with `values-equal`, not
  `raw-eq`.
- **`show` is `fmt`, not the canonical form.** A list shows `[N items]`, a record
  `{record}`, a string bare — `builtin-text` (already `fmt` from build 1) is the
  text, delegated to the host through `interp.planes`'s own `show`.
- **A Planes precedence gotcha.** `f of a, b + c` binds the call tighter than
  `+`, so an error message spliced as a call argument reads as `(f of a, b) + c`.
  Every `error-of` message is parenthesized.

---

## §A premises at baseline

- **A.1's inference survived** — verified against `interp.py`, dynamic vs lexical
  as stated. Its consequence (env stops growing with depth) is measured: 121 → 62.
- **A.7's `when`-ceiling stale-number trap, avoided.** The prompt correctly
  carried *no* figure; §0 measured the `when`+`if` ceiling at **196** and the
  `if` ceiling at **245**. The shape determines the ceiling — the exact trap A.7's
  opening note names. Every number this build reasons about is from §0 / Phase 8.
- **A.1's "the globals" was incomplete — found and closed.** A.1 said a
  function's definition env "is the globals: the function values." But
  `interp.py`'s global scope also holds top-level `let`s, and a function reads
  them (`g = 10; to f: give g; show f` prints `10`). `globals-of` (functions
  only) failed `unknown-name` there. `run-top-level` now threads the current
  top-level env as the globals a callee sees, closing the divergence while a
  caller's own locals stay invisible (the lexical guarantee holds). This is the
  one §A premise that needed correcting, and it was caught by baseline
  verification rather than by a corpus program.

---

## What this build disproved about this prompt

**Never empty.** Build 1's entry found the load-bearing unknown was the wrong
*component* (the parser, not the evaluator). Build 2's:

**A.3 and invariant 7 are in tension, and the prompt did not flag it.** A.3 says
"Every evaluation and execution step takes a status record and returns one." The
gate says "Every build-1 test passes unmodified." But the build-1 tests call
`eval(node, env)` and consume a *value* — so `eval` cannot become status-threaded
without changing them. Taken literally together, the two are unsatisfiable. The
resolution — a value-returning `eval` adapter over a status-threaded `eval-node`
core — honors A.3's substance (evaluation steps thread status; give, fail, and
Rule-1 pass-through are all the record's job) while keeping the public entry
point build-1 tests depend on. The prompt presented status-threading as cleanly
universal; in practice it is universal *beneath* a compatibility adapter, and the
adapter's `reraise` (enumerating the finite built-in tag set, since a program's
own custom `fail` tags never reach it) is a real, small piece of machinery the
prompt's framing did not anticipate.

Corollary disproved: the prompt's expectation that the parser's parse-bound
depth (A.6) is the constraint to watch. For real recursive programs the first
wall is **interpreted recursion depth (32)**, not parse depth — a different
number, in a different component, that precedence climbing would not move.

---

## Build 3 scoped: effects and the host boundary

Build 2 leaves exactly the surface A.5 predicted. The effect kinds that remain:

- **`write`** — a `WriteTo` node, fails `build-3-effect` today.
- **`ask`, `read`** — builtins, fail `build-3-effect` today.
- **`clock`, `random`, `env`** — foreign-only; reachable only through a `foreign`
  declaration, which is itself the host boundary. A foreign *call* fails today
  (`unknown-function`), and the three foreign corpus programs are `BLOCKED` on it.

So the predicted **all seven kinds** are the build-3 surface: the four
directly-invokable ones already fail naming build 3, and `clock`/`random`/`env`
arrive with the foreign/host-boundary work. Build 3 is:

1. **The host boundary** — a `Host` protocol the interpreter delegates to
   (`show` already does; `write`/`ask`/`read`/`clock`/`random`/`env` join it),
   and **foreign function calls** (`call_foreign`, value conversion in and out).
   This is the bulk of the work: `interp.planes` currently has no host object of
   its own — it borrows the outer interpreter's host for `show`. Build 3 gives it
   one, or an explicit effect-log the test harness inspects.
2. **The derivation slot** — `deriv` is `nothing` throughout (A.4); `or fail`'s
   error record carries `tag` and `detail` but not `path`. Provenance (`why`, the
   `Deriv` graph) is its own later build; the slot exists so it is a fill.
3. **The core-conformance checker** — `CORE_SUBSET.md`'s subset, checked by
   agreement the way each stage has been. With the evaluator complete, this
   becomes tractable: run the core corpus through all three Planes stages and
   assert the output matches `interp.py` across the whole subset, not a sample.

**Does the effect surface come out as all seven kinds as predicted?** Yes —
`show` implemented, `write`/`ask`/`read` failing build-3 directly, and
`clock`/`random`/`env` behind the foreign boundary. Seven kinds, one host object
away.

---

## Consistency invariants (§9) — all held

- Counts **32 / 10 / 7 / 8** (keywords / builtins / effect kinds / host methods).
- No dynamic record lookup; the association idiom, statically named fields only.
- No nested `when`/`else` ladder — `interp.planes` has **zero** `when` statements;
  dispatch is flat `if … give` throughout (A.1, A.2).
- `Traced`/`Deriv` in `interp.py` untouched; `host.py` untouched.
- The environment does not grow with call depth — asserted by measurement (62/2).
- Parser agreement **31/31**, lexer **100%**, all three self-hosting assertions
  holding, including `parser.planes` parsing the (heavily changed) `interp.planes`
  — 85 top-level nodes, agreeing with `parser.py`.
- Every build-1 test passes unmodified except the one named above.
- `audit_locked_vs_built.py`, `grammar_gen.py --check`, `ruff`, `mypy` clean at
  every commit.
- No generated artifact hand-edited.
