# REPORT_PARSER_IN_PLANES.md

**Build:** feat/parser-in-planes -- Route B stage two
**Base:** `main` at `9b61615`
**Result:** 637/637 tests passing (611 baseline + 26 new), ruff/mypy/
`audit_locked_vs_built.py`/`grammar_gen.py --check` all clean at every
commit. Counts unchanged: 32 reserved words / 8 builtins / 7 effect
kinds / 8 host methods. Amber unchanged: four sites, fire rate zero.
Lexer agreement unchanged: 30 PASS, self-tokenization complete. No new
AST node; `parser.py`, `lexer.py`, `interp.py`, and `shapes.py` all have
zero lines changed in this entire branch.

---

## The ladder rung reached: 7 of 7 named rungs, plus three extras

Section 3's ladder named seven rungs. **All seven landed:**

1. Assignment (`name = expr`)
2. `show`
3. `if` / `else`, and the `BEGIN...END` / single-inline blocks they open
4. `to` function definitions (multi-word names, optional `of params`)
5. `give`
6. `for each ... [where ...]: ...` (the statement form)
7. `use [with old as new ...]`

Three items outside the named ladder landed too, because they were cheap
once the machinery for the named rungs existed: **list literals**
(`[...]`), **record literals** (`{...}`), and **`let`** (reuses the
`Assign` node `is_let: false` already had to produce). List/record
literals were not in Phase 2's stated scope (literals, variables, field
access, calls, parens, operators, `first`/`round`/builtins) — added
because several corpus files fail on nothing else, and the field-list
canonical-form machinery `Call.args`/`If.then`/`FuncDef.body` already
needed made both a small addition.

**Not landed, named explicitly as out of scope or as the next rung:**
`rule`, `foreign`, `write ... to ...`, `note`, `because` (all "everything
else," rung 8's own catch-all); `with`/`plus`(`ListPlus` is parsed as an
operator, but the *statement*-trailing forms are not)/`or fail as`
(`parse_expr`'s wrapping, deliberately scoped out in Phase 2); `for each`
as an expression (the wrapped comprehension-header form); and every
juxtaposition or multi-word function call, which needs `known_funcs` —
declined for the same reason amber is declined (see below).

## The canonical-AST-form harness: shape and adequacy

One node per line, indentation for depth, node kind then fields in
`parser.py`'s own dataclass declaration order, leaf values quoted and
escaped so a string containing a quote or newline survives the text form
exactly the way it would survive re-parsing real source. The Python side
is fully generic (introspects `lexer.py`'s dataclasses via
`__dataclass_fields__`); the Planes side is hand-dispatched per node
kind, because Planes has no way to enumerate a record's own fields.

**It proved adequate for everything this build threw at it** — every
disagreement it ever reported during development was real (a genuine
`of`-precedence bug, a reserved-word collision, a missing import in the
harness itself), never a false positive from the comparison mechanism.
Two real gaps in the harness were found and fixed along the way, both
in the **generic Python-side serializer**, not the node-specific Planes
side: `AST_NODE_TYPES` (the tuple `_is_node` checks against) was missing
`ForEach`, `Use`, and `RecordLit` at various points — each one caught
immediately by the first fragment test exercising it, producing a raw
Python `repr()` instead of a recursive render, never a silent false
pass. And `_render_value`'s handling of tuple-typed fields (`Use.
renames`, shaped like `Foreign.effects` too) assumed a tuple was always
a single `(key, value)` pair; a *sequence* of pairs crashed trying to
unpack. Both are now fixed generically, not just for the fields that
first exposed them.

One shape never came up in this build's scope: a field whose value can
be `nothing` *or* a node (`ForEach.where`) needed a per-field `is
nothing` check on the Planes side, since Planes has no way to write a
polymorphic "recurse if this is a node, else render as nothing" function
generically the way the Python side's `_is_node` check can.

## Corpus agreement, and the self-parsing verdict

**4 PASS, 0 PARTIAL, 26 FAIL, out of 30** (`parser-in-planes-
verification.md` carries the full table and classification).
`demo/app/config.planes`, `demo/association.planes`, `demo/pkgs/
logger.planes`, `demo/pkgs/mathlib.planes` pass outright.

**Every disagreement classified, per the build prompt's own
requirement, before anything was fixed:**

- **14 files — `known_funcs`-dependent calls.** Juxtaposition (`ask
  url`) or multi-word function names (`fetch stories`). `parser.py`
  resolves these against `Parser.known_funcs`, built by `prescan_funcs`
  and consumed by amber's own disambiguation. Amber is out of scope
  (section 7 invariant 3, Build 5) — and `known_funcs` is the *shared
  prerequisite* amber's four sites and this shape both depend on
  (`PROBE_PARSER.md` capability 7). Building the table without amber to
  consume it would resolve every one of these silently, never refusing
  a genuinely ambiguous reading — not a smaller version of the real
  capability, a different and unsound one. Declined for the same reason
  amber itself is declined here.
- **7 files — statement forms past the ladder.** `rule` (4 files),
  `foreign` (2), `write ... to ...` (1). Rung 8's own named catch-all.
- **1 file — `for each` as an expression.** `ordinary.planes` uses the
  wrapped comprehension-header form; this build's stated scope was the
  statement form only.
- **4 files — the cons-list cursor's construction ceiling.** Every file
  over ~140 tokens (`foreign.planes` 147, `pypi.planes` 158,
  `hn.planes` 167, `gate.planes` 201). See "What this build disproved,"
  below — this is the load-bearing finding of the whole build.
- **1 file — not a disagreement at all.** `demo/app/net.planes` fails
  identically on *both* sides: `parser.py`'s own bare `parse(src)` (no
  cross-file `known` map) cannot resolve `api base`, defined in a
  sibling module-graph file. `test_bracket_misparse.py`'s corpus test
  documents this exact case and works around it with
  `shapes.analyse_file(path, follow=True)`; this build's harness tests
  `parse()` in isolation (matching Phase 2/3's own fragment style) and
  does not.

**Self-parsing (Phase 5): skipped.** Phase 4 did not reach full
agreement, and the build prompt names this explicitly as the condition
for skipping Phase 5 rather than attempting it. Not attempted, and
correctly not attempted — `grammar/parser.planes` itself is 1000+ lines
(comfortably past the 140-token construction ceiling many times over),
so a self-parse attempt would fail at cursor construction before
reaching any question Phase 5 actually wants answered.

## What this build disproved about this prompt

**The architecture ruling's "iteration where depth scales with input
length" could not be fully realized — cursor construction has no known
iterative solution given Planes's current primitives, and this build did
not find one.** `to-cons` (capability 4, `PROBE_PARSER.md`) builds the
cons-list cursor via `reverse-into` (one safe `for each` fold) then
`unreverse` (recursive, one call per token, to restore forward order).
This is the *exact* shape capability 4's own writeup names as the trap:
"cannot be built or fully drained by per-item recursion at real
token-stream sizes." This build inherited that trap rather than closing
it. Every alternative considered during design failed for a structural
reason, not a missed trick:

- Building the cons-list forward directly (prepend-while-folding)
  produces the last token as `head`, not the first — the *opposite* of
  what a left-to-right cursor needs, for the same reason `reverse-into`
  itself produces a reversed list.
- Walking a cons-list with `for each` is not possible at all — `for
  each` only walks a Planes-native list or string, and a cons-list is
  neither.
- Planes has no `while`, so there is no bounded-cost way to do
  "consume the reversed cons-list one cell at a time, rebuilding
  forward" without either recursion (back to the ceiling) or `for each`
  over something that is not a cons-list.
- An association-idiom-style indexed lookup (`for each entry in
  indexed-tokens where entry.i == target`) *would* avoid recursion
  entirely — every lookup is a host loop, zero Planes-recursion cost
  regardless of file size — but at real cost: O(*n*) per lookup, and a
  parser makes roughly O(*n*) lookups, so O(*n*²) total. Phase 6's own
  measurement (~1.3ms per lookup at 500 entries) makes this concrete:
  for `gate.planes`'s 201 tokens, an all-lookups-via-scan cursor would
  cost on the rough order of 201² ≈ 40,000 scan-steps just for
  sequential advancement, before any actual parsing work — plausibly
  workable for files this size, but the wrong tool for anything larger,
  and a genuinely different architecture from the one built here, not a
  drop-in fix.

**This is not this build's failure to find the "iterative" answer the
prompt assumed exists — it is evidence the answer may not exist yet at
this layer, with today's primitives.** The report's own honest
conclusion: either a language-level capability closes this cleanly (a
`rest`/`drop` operation for lists, declined twice already at #11 for
strings and lists, and this finding is a third, structurally different
argument for revisiting that — not for calls, this time, but for
exactly the "queue held by a single-pass builder" shape this build
needed), or Route B's eventual full parser accepts the O(*n*²)
indexed-scan architecture and its real cost, or a fundamentally
different technique (a two-pass tokenizer that emits an already-cons-
shaped stream directly from `lexer.planes`, sidestepping the
list-to-cons conversion entirely) closes it. None of the three was
attempted here; naming them precisely is this section's job.

**A secondary, smaller finding:** amber's `known_funcs` table turned out
to be a harder dependency to work around than the architecture section
anticipated. The prompt frames amber as cleanly separable ("Amber is out
of scope... a parser that omits the checks entirely still produces
identical ASTs on every corpus file"). That is true for the four amber
*checks* themselves — but `known_funcs`, the table those checks read, is
also what ordinary (non-ambiguous) juxtaposition and multi-word calls
need to resolve *at all*. 14 of this build's 26 failures trace to that
one dependency, not to amber's refusal logic. The separation holds for
amber's own logic; it does not fully hold for the data amber's logic
reads, which turns out to be load-bearing for correctness even absent
any ambiguity.

## No AST node added

Confirmed directly: `git diff main --stat -- parser.py lexer.py
interp.py shapes.py` is empty. This build writes Planes; it extends
nothing. No exhaustive `isinstance` dispatch anywhere in the codebase
needed a new case, because there is no new case to add.

## Remaining gaps, and what closing them would cost

- **The cons-list construction ceiling** (above) — the load-bearing gap.
  Cost to close depends entirely on which of the three named directions
  is chosen; none is a small patch.
- **`known_funcs`.** Building the table (`prescan_funcs`'s Planes
  equivalent — a single `for each` pass over tokens, safe, no recursion
  issue) is cheap. Consuming it *correctly* — juxtaposition and
  multi-word resolution without amber's disambiguation — is exactly the
  "resolve silently" trap named above, so this is really the same
  decision as Build 5's amber work, not a separable smaller task.
- **Rung 8's remaining statement forms** (`rule`, `foreign`, `write`,
  `note`, `because`, `when`). Each is a bounded, well-specified addition
  to the existing `parse-statement` dispatch — no new architecture
  needed, just more cases, following the same pattern rungs 1-7 all
  used.
- **`for each` as an expression**, **`with`** (`RecordUpdate`), and
  **`or fail as`** (`OrFail`) at the `parse_expr` level — each is a
  contained addition to `parse-primary`/the outer expression wrapper,
  not a new architectural piece.
- **Field names that are reserved words** (`r.to`, `{ from: "x" }`) —
  this build always requires a plain `NAME` for field access and record
  literal keys, a stated simplification from `parser.py`'s
  `FIELD_NAME_KINDS` allowance. Cheap to close: thread the same 14-kind
  set (already loaded via `grammar/vocabulary.json`'s
  `field_name_token_kinds`, reachable via the module graph this file
  already `use`s) through the two check sites.

## Build 5, rescoped

`REPORT_RECURSION_AND_AMBER_SITE5.md` left Build 5 (the four amber
sites, in Planes) as "still possibly folding into Build 4, exactly as
the prior report left that question open." **This build answers that
question directly: Build 5 does not fold into Build 4 as a small
addendum — it *gates* a meaningful fraction of Build 4's own remaining
work.** 14 of this build's 26 corpus failures, over half, trace to
`known_funcs`, which only a built amber can safely consume. Build 5 is
not "the four disambiguation sites, built after the parser is done" —
building `known_funcs`-dependent call resolution *is* amber's own
prerequisite work, done once, whether framed as "finishing the parser"
or "starting amber." The honest scoping is: **Build 4 and Build 5 share
one piece of remaining work (the name table and what depends on it) that
neither can cleanly finish without the other** — closer to the *same*
build than two sequential ones, a stronger claim than the prior report's
open "possibly folds in."

The cost of Build 5's *own* logic, once `known_funcs` exists, still
looks as `PROBE_PARSER.md` capability 7 described it per site: site 3
(paren-arglist bracket matching and span rendering) is the largest
single piece; the other three are smaller, similarly-shaped additions
to the same dispatch this build's calls already run through
(`parse-name-primary`/`parse-name-paren-call`).
