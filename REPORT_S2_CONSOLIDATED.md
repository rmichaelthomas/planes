# REPORT_S2_CONSOLIDATED.md

S2 lands every remaining item from `REPORT_SELFHOST_SWEEP.md` §10 at once, so
`interp.planes` can be written against a complete language instead of
discovering gaps one build at a time. Everything §A ruled shipped. Six phases,
one commit each; the suite is **669** (was 637), counts **32 / 10 / 7 / 8**.

---

## 1. What shipped, against §A

| Ruling | Outcome |
|---|---|
| **A.1** reduce frames per Planes call | Done. if-based 7→4 (ceiling 140→245), when-based 7→5 (140→196). Short of "more than double" — reported with the reason (§2). |
| **A.2** `join of xs` builtin | Shipped. Arity 1, O(n), no coercion, empty→"". Builtins 8→9. |
| **A.3** `rest of xs` builtin | Shipped. Arity 1, `rest of []` raises, lists only, analyser sees through. Builtins 9→10. |
| **A.4** builtins 8→10, reserved words 32 | Held. 10 builtins, 32 keywords, no reserved word added. |
| **A.5** no fixpoint/iteration construct | Honoured. None added. |
| **A.6** status-record threading, 5 rules | `demo/status_threading.planes` + one test per rule (§6). |
| **A.7** field enumeration stays absent | Honoured. No enumeration construct; the `when`-exhaustiveness check stays a later `shapes` item. |
| **A.8** core includes all effect kinds | `CORE_SUBSET.md` corrected (§7). |

---

## 2. Phase 1 — frames per Planes call, measured

**Method:** `scripts/measure_frames_per_call.py` wraps `Interpreter.call` from
outside and diffs the Python stack depth between two consecutive Planes-level
calls (minus one for the wrapper frame); the ceiling is a binary search on
where `recursion-too-deep` first fires. Host: macOS arm64, CPython 3.14.6,
`sys.recursionlimit` 1000.

| shape | frames before | frames after | ceiling before | ceiling after |
|---|---|---|---|---|
| `if`-based countdown (the sweep's benchmark) | 7 | **4** | 140 | **245** |
| `when`-based (the shape `interp.planes`'s `eval` takes) | 7 | **5** | 140 | **196** |

The sweep's "~7 frames per call" is confirmed exactly (the sweep's own 8 was a
measurement that included its instrumentation frame). **What collapsed:**
`invoke` folded into `call` (its only caller — the `call → invoke` frame is
gone); `exec_block` inlined at the four recursion-spine sites (the folded
call's body loop, `exec_stmt`'s `If`, `exec_when`'s block, `eval`'s `If`); and
`exec_when` folded into `exec_stmt`'s `When` case — the biggest lever for
self-hosting, because a real `eval` is a nested `when/else` ladder and every
level used to pay both an `exec_stmt(When)` and an `exec_when` frame.

**Target missed, honestly.** "More than double" needs 3 frames (ceiling >280);
the achievable safe floor is 4 (if) / 5 (when). The remaining frames are the
irreducible dispatch spine — `call`, the statement dispatches for the nested
`if`/`give`, and one expression `eval` for the recursive call. Removing more
means merging `exec_stmt` and `eval` or special-casing node kinds, which trades
the clean dispatch architecture and risks the semantics-unchanged invariant
(§8 mode 9: a real 7→4 with a reason beats a claimed 7→3 that does not survive
measurement). **Every pre-existing test passed unmodified** (invariant 6);
`Traced`/`Deriv` untouched (invariant 9); the `recursion-too-deep` error keeps
its shape and fix text, threshold only moved.

## 3. `join` and `rest` — integration and the O(n) measurement

Both match the `count`/`text`/`normalize` footprint end to end:
`grammar/vocabulary.json` (the entry; `BUILTIN_NAMES` derives from it, so the
parser picks them up for free), `interp.py`'s `builtin` dispatch, `shapes.py`'s
pure-builtin fold, `audit_locked_vs_built.py`, and `verify_grammar_and_amber.py`.

**`join` is O(n), measured against the sweep's 400 KB `+` case:** 400 KB joins
in **0.53 ms**, versus **~1.25 s** for the sweep's repeated `+` at the same size
— **~2360×**, and flat µs/byte (0.0013), the signature of O(n) against the `+`
build's O(n²).

## 4. Phase 3 — the `origins_of` test result (ruling pinned)

`rest`'s analyser guarantee is **pinned and holds** (`test_text.py`): the
analyser stays total on a program using `rest`, folds a known list statically,
and **both** `interp.origins()` (runtime) and `shapes.origins_of()` (static)
trace a `rest`-of value back to the source list — `origins_of(ask)` over
`ask (join of (rest of xs))` returns `['tail', 'xs']`, and the runtime origin
of a `rest` applied to an `ask`-fetched list is `network:…`. The ruling was
pinnable and correct, not wrong.

## 5. Phase 4 — the multi-line-literal defect

**Real cause, and it is what the sweep described.** The tokenizer is oblivious
to bracket nesting, so a literal's continuation line raises the indent and
emits a `BEGIN` inside the brackets whose matching `END` lands one dedent later,
outside the literal. `skip_bracket_ws` consumed the `BEGIN`; the `END` leaked to
the block level, where `parse_block` — unlike `parse_program`, which already
tolerates a stray `END` — mistook it for the block's close and dropped every
statement after the literal. **Fixed parser-side** (count the unbalanced
`BEGIN`s in `pending_ends`, absorb the owed `END` in `skip_blank`), which keeps
lexer agreement and self-tokenization trivially intact — a fix in either lexer
would have forced a matching `grammar/lexer.planes` change. Reproduced as five
failing tests first, confirmed red, then fixed. The parse-speed regression the
benchmark first flagged (>25%) was reclaimed by keeping `skip_blank`'s original
hot path (the owed-`END` case runs only when one is owed).

## 6. Phase 5 — the five rules, each pinned

`demo/status_threading.planes` (a toy evaluator over a statement list) plus
`test_status_threading.py`, one test per rule naming it:

| Rule | Pinned by |
|---|---|
| 1 — pass-through, not early exit | `give 1` then `give 999`; the result is **1**, so the second give never ran though the block walked to its end (tested hardest) |
| 2 — give stops at the function boundary | status resets to `"normal"`, value is the given value |
| 3 — fail propagates past the boundary | uncaught `apply-function` keeps status `"fail"`; `or-fail` resets to `"normal"`, value is the `{tag, detail}` |
| 4 — env rides in the record | bind then `lookup-env` returns 42 |
| 5 — no read of value without checking status | a `"fail"` state (value nothing) handed to `exec-stmt` returns untouched |

**The analyser sees through the idiom:** `analyse_file` computes a complete,
total surface across the whole recursive evaluator (11 `show` effects, no
UNKNOWN-crash), and `origins_of` traces a value threaded through a status-record
shape back to its threading name.

## 7. Phase 6 — what `CORE_SUBSET.md` got wrong

Beyond the effect kinds (A.8's correction — now core, with the reasoning inline
as §2a), the correction pass found **no further errors** in the derivation. The
construct inventory (§1.1), the not-core table minus the effect row (§2), and
§127's confirmed prediction all stood. The three edits were: effect kinds into
the core, `with` marked prediction-justified (the sole member with no program
behind it), and the builtin recount against 10 (`text`/`count`/`join`/`rest`,
`upper` borderline). The headline moved from "half the keywords, none of the
effects" to **half the keywords and all of the effects** — the one number a
second-host scoping most needs.

## 8. Amber, corpus, counts

- **Amber: four sites, fire rate zero.** `verify_grammar_and_amber.py` section
  F all PASS; Phases 2–3 touched the grammar and added no guess site.
- **Lexer agreement 100%, corpus 30→31** (`demo/status_threading.planes`), both
  count assertions moved (`test_lexer_in_planes.py`, `test_bracket_misparse.py`).
  Complete self-tokenization still holds.
- **Counts: 32 reserved words / 10 builtins / 7 effect kinds / 8 host methods.**
  `ruff`, `mypy`, `audit_locked_vs_built.py`, `grammar_gen.py --check` clean at
  every commit; `host.py` and `Traced`/`Deriv` untouched.

---

## 9. What this build disproved about this prompt (never empty)

1. **A.3 is internally contradictory.** Ruling 1 says `rest of []` errors, but
   its "match `first n of`" clause points at a builtin that *clamps and never
   errors* (`first 5 of [1,2]` → `[1,2]`). The §10 gate requires `rest of []`
   to raise, matching ruling 1's explicit intent, so it raises — and the "match
   `first n of`" clause is the defective half.
2. **`rest` collided with a program the prompt didn't know about.**
   `grammar/parser.planes` used `rest` as a local variable; making it a builtin
   broke that file (a builtin name cannot be a bare variable — same as
   `count = 5`). Renamed to `remaining` in three scopes; ASTs unchanged,
   agreement held.
3. **"More than double" was not achievable safely** (§2). The prompt's own
   hedge covered this, but the target itself assumed a 7→3 reduction the clean
   dispatch architecture does not permit without semantic risk.
4. **`render.py` had latent gaps the prompt's Phase 5 didn't anticipate.** It
   could not render `when` or `plus` at all (no `When`/`ListPlus` renderer),
   never caught because no root/demo corpus file used them and `grammar/*.planes`
   are outside the render corpus. The demo is the first; both were added and are
   now round-trip-tested. `render.py`'s `with` (RecordUpdate) renderer is still
   absent — a remaining gap (§10).

## 10. Every remaining gap, and what closing it costs

| Gap | Cost |
|---|---|
| The recursion ceiling is 196–245, not doubled | A further reduction needs merging `exec_stmt`/`eval` or a trampoline — larger than §42's "below the visible line". Revisit only on a real program that exceeds the post-A.1 ceiling (A.5's condition). |
| `render.py` cannot render `with` (RecordUpdate), and likely `If`/`WriteTo` as expressions | One `render_expr` case each, plus a round-trip test to exercise it. Needed before `render.planes` — the renderer must be exhaustive (#13). |
| The `when`-exhaustiveness check (A.7) | A `shapes`-level tooling item, scheduled after `interp.planes`. Not a language change. |
| A builtin name cannot be a bare local variable | A language wart, not ruled here: `count`, `rest`, `join` etc. shadow only via a function definition, not an assignment. Surfaced by gap 2; fixing it is a parser change out of this build's scope. |

## 11. `interp.planes`, scoped

With the language complete — frames halved-ish, `join`/`rest` present, the
multi-line defect fixed, the status idiom proven — writing `interp.planes` is
now a bounded effort, not an open-ended one. The lexer took three builds; the
parser is unfinished at one. `interp.planes` is **larger than either**, because
`interp.py` is 1154 lines of hand-dispatched evaluation and the status-record
idiom roughly doubles the statement count of every function that threads it.
Estimate **three builds**:

1. **The expression evaluator** — `eval` over the literal/var/op/call/field/
   record/list nodes, on the status record, with the environment as the Phase 1
   association idiom. Closes: the core of interpretation. Load-bearing unknown:
   whether the association-idiom environment stays under the §42 line at
   interpreter scale (Phase 1 said adequate to ~50 scoped entries — an
   `interp.planes` interpreting a real program is the first test of that).
2. **Statements and control flow** — `exec-stmt`/`exec-block` with the five
   status rules, `give`/`or fail`, `for each`, `when` dispatch over the AST.
   Closes: running whole programs. Load-bearing unknown: the recursion ceiling —
   `interp.planes` on `interp.py` spends Planes frames per interpreted level, so
   the usable interpreted-program depth is a fraction of 196, and this is where
   that bites for the first time.
3. **Effects and the host boundary** — `show`/`write`/`ask`/`read` threaded
   through the status record to a host, and the core-conformance checker
   (`CORE_SUBSET.md` §5) built to confirm `interp.planes` stays inside the core.
   Closes: self-hosting's first end-to-end run.

**The load-bearing unknown across all three is the recursion ceiling** (gap 1):
it is the one constraint that scales *against* a recursive interpreter rather
than with any single program's size, and A.1 moved it from 140 to 196–245
rather than removing it. If that proves too low for a real `interp.planes`
interpreting a real program, the language answer A.1 declined — a trampoline, a
CPS rewrite, or a raised limit — comes back onto the table, and it is the first
thing the interpreter build should measure.
