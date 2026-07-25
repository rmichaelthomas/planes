# REPORT_PARSER_FINISHED.md — S3a, the parser finished

**Branch:** `feat/parser-finished` · **Base:** `main` at `b2e5973`
**Result:** `grammar/parser.planes` reaches **31 / 31 full corpus agreement**
with `parser.py`, self-parses in full agreement, and the two S2 follow-ons
(render.py exhaustiveness, builtin-name reservation) are closed. Counts
unchanged 32 / 10 / 7 / 8; amber at four sites, fire rate zero; 685 tests;
all blocking gate sections pass.

## Agreement, separated by phase

The corpus is **31 files**, not the 30 the prompt expected — S2 added
`demo/status_threading.planes` after the parser-in-planes report measured
4/30. Progression:

| After | PASS / 31 | Isolates |
|---|---|---|
| Baseline (`b2e5973`) | 4 | — |
| **Phase 1** — cursor on `rest of xs` | **4** | the cursor's contribution alone |
| **Phase 2** — `known_funcs` + amber | **11** | the name table's contribution |
| **Phase 4** — remaining statement forms | **31** | everything past the ladder |

Phase 1 moved the PASS count by **zero**, and that is the finding (below):
the cursor was never the blocker for any file the corpus could still see.
Phase 2 (+7) is the name table. Phase 4 (+20) is the statement forms.

## The four ceiling-blocked files — the prompt's premise was stale

The prompt's §1 says "the four files that failed on the ~140 ceiling should
now pass — confirm that specifically, by name." Measured, the premise does
not hold, and Phase 1's real effect is different:

- The four named files — `foreign.planes` (147 tokens), `hn.planes` (167),
  `pypi.planes` (158), `gate.planes` (201) — were ceiling-blocked at the
  **140** ceiling the parser-in-planes report measured. **S2 already raised
  the recursion ceiling 140 → 245.** All four are under 245, so their
  `to-cons` already succeeded; they were failing on real constructs (a
  `foreign` declaration, a `first`-in-record-field, URL-string juxtaposition
  calls), not the cursor. Phase 1 changed nothing for them; they pass now
  because of **Phases 2 and 4**.
- The one file that actually hit the cursor-construction ceiling at 245 is
  **`status_threading.planes`** (577 tokens) — added by S2 *after* the
  report, so the report never saw it. Phase 1 moved it from
  `recursion-too-deep: 'unreverse' recursed past…` to a clean
  `parse-error: found 'when'`, proving the `rest of xs` cursor at whole-file
  scale.

So all four named files **do pass** in the final 31/31 — but naming them as
Phase 1's contribution would be false. Phase 1's contribution is: the
cons machinery (`to-cons` / `reverse-into` / `unreverse`) is gone
(grep-confirmed, only a doc comment remains), and cursor construction costs
zero recursion at any length.

## `known_funcs` — the table and its cost

Built as the association idiom (A.2): a **list of `{ name, arity }` records
scanned with `for each … where`**, no dynamic record lookup. `prescan-funcs`
reproduces `parser.py`'s `prescan_funcs` token-for-token (tested
byte-identical across the corpus); builtins come from `use vocabulary` (all
arity 1); `build-known` appends prescan over builtins so a user function
shadows a builtin, matching `merged.update(prescan)`.

**Measured across the corpus:** table size **min 10, max 17, mean 11.8,
median 11** entries. A worst-case lookup (a miss, full scan) on the largest
table (17 entries, `foreign.planes`) is **0.061 ms**. The idiom's
~1.3 ms/500-entry cost is **invisible at corpus scale** — the largest real
table is 30× below the ~50-entry point where the sweep found the cost
becomes visible. At this scale the linear scan is free.

## The four amber sites — synthetic fixtures

The corpus contains no ambiguous file (fire rate zero, re-confirmed on both
the corpus and the demo module graphs), so the sites can only be exercised
by deliberately-ambiguous fragments, one per site under `probe/amber/`
(outside every corpus glob, so no count assertion moves):

| Site | Fixture | What it proves |
|---|---|---|
| 1 multi-word | `to a:` + `to a b:`, call `a b` | both `a` and `a b` defined ⇒ refuse |
| 2 juxtaposition | `greet` (arity 1) + `home` (arity 0), `greet home` | head takes an arg and the next name is a 0-arity function ⇒ refuse |
| 3 paren-arglist | `scale` (arity 1), `scale(a) + b` | an operator after `)` with an arity-1 head ⇒ both readings fit ⇒ refuse |
| 4 rename | `to load:` + `to load record:`, `use cache with load record as fresh` | two prefixes of the `old` name both exported ⇒ refuse |

For every fixture the Planes refusal is **byte-identical** to `parser.py`'s
`render_amber` output (modulo the `ambiguity:` fail-tag prefix the runtime
adds) — one refusal style, not two (A.3). `assemble-amber` reproduces the
templates as inline string literals, since `parser.planes` cannot read
`grammar/messages/amber.json` without an effect; that JSON-as-data ruling
(D5) scoped `parser.py`, and this file already reproduces `parser.py`'s
inline ordinary-error text the same way.

## Every Phase 4 disagreement, classified

No disagreement turned out to be a genuine difference in what the two
implementations consider the same AST. Each was a construct `parser.planes`
did not yet parse (a language-surface gap closable with already-reserved
keywords — no new keyword/builtin/effect/host), classified in
`parser-in-planes-verification.md`'s table. The constructs, by resolution:
`write`/`WriteTo`; for-each-as-expression; the `because` trailer;
keyword-as-field-name; the **bare-expression-statement fallthrough**
`parser.planes` lacked (`parser.py`'s `parse_statement` ends with `return
self.parse_expr()`); `foreign` + effect claims; `rule` (may/may-not, `to`,
`supersedes`, `@fp`); `note`; `when` with match/bind pattern entries; and
the `with` (RecordUpdate) / `or fail` (OrFail) trailers. Two `parse_expr`-
vs-`parse_or` fidelity fixes surfaced: `give`/`if`-condition and a
parenthesised expression must use `parse_expr`, or a trailing `or fail` /
`with` fails to attach.

The one file that cannot be parsed standalone, **`demo/app/net.planes`**, is
**not a disagreement**: it calls `api base`, a multi-word function defined
in its sibling `config.planes`, and without that name in the table *both*
parsers stop at the identical point (`expected )` / `expected ')'`, both at
`base`, line 5). The harness resolves each file's `use`d siblings for their
names and passes that cross-file `known` mapping — the table the module
system supplies — identically to both parsers (`cross_file_known`;
`parse(src, known)` and the new `canonical-of-program-source-with-known`).
Given the module context, the two agree on the full AST. This is the
cross-file `known` `parser.py` has always taken, now supplied to both sides.

## Self-parsing verdict — it holds

A Planes parser parsing Planes source, checked against `parser.py`:

- `grammar/vocabulary.planes` — **AGREES** (guarded in the suite, ~0.3 s).
- `grammar/lexer.planes` — **AGREES**, a 156 046-character canonical form.
- `grammar/parser.planes` **itself** — **AGREES**, a 748 255-character
  canonical form. The second closed bootstrap assertion in this domain,
  after lexer self-tokenization.

Reaching `parser.planes` self-parse required ruling A.6 in earnest: parsing
this file's own deepest dispatch chains (`canonical-of-node` at 22 nested
levels, `parse-statement` at 16, `parse-primary` at 13, `digit-value` at 11)
exceeded the recursion ceiling — a design bug in the code, not a ceiling to
raise. Rewriting them from nested `when`/`else` ladders into flat
`if … give` sequences (each falling through when unmatched) dropped the
nesting to ~2 levels and, as a bonus, removed the per-dispatch frames the
nested form spent at run time. One further bug surfaced only here: a
parenthesised expression used `parse-or`, not `parse-expr`, so `(x with …)`
inside parentheses did not parse. Corpus agreement stayed 31/31 throughout.

## `render.py` — the full missing-node list

Enumerated all **32** AST node kinds from `lexer.py` mechanically and
checked each against `render.py`'s dispatch. Predicted by A.5: `with`
(RecordUpdate) absent; `If`/`WriteTo` in expression position suspected.
Measured:

- **`RecordUpdate` — genuinely missing.** Referenced nowhere in `render.py`;
  it fell through to `render_expr`'s final raise. **Added** — `base with
  name: expr, …`, base as an operand, chains left to right.
- `If` / `WriteTo` in expression position — **not gaps.** Both are
  statements only (`parse_statement`); neither ever appears as a
  sub-expression, so `render_expr` needing a case for them was a false
  suspicion. `WriteTo` inside an `OrFail` is already handled by
  `render_orfail`.
- `Builtin` — dead node (parser never builds it), raises a named error.
- `Because` — appears only as an annotation field, rendered inline by
  `render_because_suffix`; never a standalone node.
- Everything else — already handled.

The one structural gap besides RecordUpdate was `render_stmt`'s final
`return indent + render_expr(node)` **catch-all** (failure mode 6): now an
explicit `_EXPR_STMT` dispatch that raises, naming the kind, on a node that
is neither a known statement nor a renderable expression. Added a per-node-
kind round-trip test (parse → render → reparse → `ast_equal`) that also
asserts every kind `lexer.py` declares is covered, so a node added later
without a render case fails the test.

## Phase 6 — binding positions found, corpus clean

The effective reserved surface is **42** (32 keywords + 10 builtins,
disjoint). `parser.py` now rejects a builtin name at every **variable**
binding position, naming the collision: **assignment**, **`let`**, a **`to`
parameter**, a **`foreign` parameter**, a **`for each` loop variable**, an
**`or fail` tag** (which binds the error record), and a **`when { name }`
field binding**. A **function** definition is untouched — `to count of x:`
still shadows the builtin (the names mandate); a `fail … as tag` label and a
rename alias name a label / a function, not a variable, and are left alone.

**Corpus clean, confirmed by construction, not assumption:** every `.planes`
file (corpus, `grammar/*.planes`, `vocabulary.planes`) was parsed and every
binding position walked — **no file binds a builtin name.** So
`parser.planes` still loads under the new rule (it is parsed by `parser.py`),
and corpus agreement stays 31/31. `test_names.py`'s ceiling test is reframed
as the 42-name surface with the rationale that the keyword-vs-builtin budget
distinction had no difference to anyone writing Planes.

## What this build disproved about the prompt

1. **The four-ceiling-blocked-files premise (§1) is stale.** They were
   ceiling-blocked at 140; S2's 245 ceiling already cleared them, so Phase 1
   does not move them — the only file that hits the 245 cursor ceiling is
   `status_threading.planes`, which the report predating S2 never saw. Naming
   the four as Phase 1's contribution would be false; they pass in Phases 2
   and 4.
2. **A.5's `If`/`WriteTo`-in-expression-position suspicion is a false
   positive.** Both are statements only; `render_expr` needs no case for
   them. RecordUpdate was the only real render gap.
3. **The prompt frames "the three blockers" (cursor, `known_funcs`, amber)
   as what stood between 4 and full agreement.** Measured, they take the
   corpus from 4 to 11. The remaining 20 files needed the statement forms
   past the ladder — `write`, `foreign`, `rule`, `note`, `when`, the
   trailers, for-each-as-expression, and the bare-expression fallthrough —
   which the prompt's phase structure does not name but "target 100% PASS"
   requires. Finishing the parser meant porting all of them.

## `interp.planes` build 1 — scoped

Per S2 §11, build 1 is the expression evaluator on the status-record + an
association-idiom environment. What it takes:

- **The environment is the association idiom again** — a list of
  `{ name, value }` records scanned with `for each … where`, exactly the
  shape `known_funcs` used here. This build is direct evidence it is the
  right answer at that scale: the parser threaded a `{ name, arity }` table
  through the whole recursive descent and the lookups never showed on the
  benchmark (max 17 entries, 0.061 ms). An interpreter's scoped environment
  is the same shape at the same scale (S2 measured §42 adequate to N ≈ 50–200
  with a scoped env), so the idiom holds — **until** a program's environment
  grows past ~50 live bindings in one scope, where the 1.3 ms/500-entry cost
  starts to bite. Build 1 should measure real environment sizes the way this
  build measured table sizes, and only then decide whether a scoped env keeps
  it under the visible line.
- **The recursion ceiling is the load-bearing unknown, and this build
  sharpened it.** A recursive expression evaluator recurses per expression-
  nesting level, which is shallow — but S3a showed that a *dispatcher*
  written as a deep `when`/`else` ladder is itself deep enough to blow the
  ceiling when walked, and the fix (flat `if … give`) is now proven. Build 1
  should write its `eval` dispatch flat from the start, and measure the
  ceiling first (S2's standing instruction), because an interpreter compounds
  recursion the way `parser.planes` self-parse did.
- **The flat-dispatch + status-record + association-env combination is now
  demonstrated end to end** at 748 K characters of self-parsed Planes, which
  is the strongest evidence yet that `interp.planes` is expressible with the
  current 32/10/7/8 language and no new construct.
