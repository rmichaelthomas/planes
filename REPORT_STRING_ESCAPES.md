# REPORT_STRING_ESCAPES.md

**Build:** fix/string-escapes-and-bootstrap
**Base:** `main` at `fdad13b`
**Result:** 573/573 tests passing (556 baseline + 17 new), ruff/mypy/
`audit_locked_vs_built.py`/`grammar_gen.py --check` all clean at every
commit, amber fire rate zero throughout, reserved-word ceiling
unchanged at 32/8/7/8.

---

## What shipped

- Four string escapes — `\"`, `\\`, `\n`, `\t` — in `grammar/vocabulary.json`'s
  STRING pattern and `lexer.py`'s tokenizer. An unrecognized escape and a
  trailing backslash before the closing quote are both syntax errors that
  name the fix, not silent corruption or a swallowed token.
- `PlanesSyntaxError` moved from `parser.py` into `lexer.py`, since
  `tokenize()` now needs to raise it and `lexer.py` cannot import
  `parser.py`.
- `grammar/lexer.planes`'s STRING section — the one token class the prior
  build (PR #11) left undone, because the language could not yet write a
  string literal containing the quote character the detection needed.
- **The renderer, the runtime `why` path, and the static analyser's
  derivation labels all re-escape now** — a defect this build's own
  grammar change activated, found and closed within the same session (see
  "What this build disproved," below).
- Full agreement across the 29-file corpus (29 PASS, 0 PARTIAL) and
  complete self-tokenization of `grammar/lexer.planes` and
  `grammar/vocabulary.planes` against `lexer.py` — the first closed
  bootstrap assertion in this domain's history.

## What did not ship

- `rules.py`'s four violation/conflict-message sites that quote
  `rule.target` are **not** fixed — see "Remaining gaps" below.
- No numeric or Unicode escape (`\x41`, `A`). Declined by the ruling
  this build executes, not a gap.
- No way for a `to` function to raise a custom-message error from
  ordinary Planes code. Pre-existing; documented in place in
  `grammar/lexer.planes`'s STRING section rather than routed around.

---

## The defect, stated against its lock

v9.0 §105 locks *text is a sequence of Unicode code points*. The
`STRING` production (`grammar/vocabulary.json`, pre-build) had no escape
sequences: its own character class, `"[^"]*"`, structurally excluded its
own delimiter. There existed sequences of code points — any containing a
double quote, and by the same splitting-on-newline argument, any
containing a newline — that no Planes string literal could denote. That
is a defect in the grammar, in the same class as `for each` refusing to
iterate a string (closed by the prior build), and this build closes it
where it lives: the grammar, not a workaround around the grammar.

## Why `chr of n` was declined

`REPORT_TEXT_ITERATION_AND_LEXER.md` §4 proposed `chr of n` as a way to
construct a quote character (`chr of 34`) without changing STRING's
grammar. Declined on the three grounds the build prompt states and this
build re-confirms empirically, not by assertion:

1. **It spends a builtin to route around a grammar defect.** The count
   would go from 8 to 9, permanently, for a capability that four new
   regex/lexer branches provide without touching the builtin surface at
   all (confirmed: builtins are still 8, all arity 1).
2. **`quote = chr of 34` is a magic number** in a language whose stated
   disposition (grammar/vocabulary.json's own framing throughout this
   repo's history) is that nothing is hidden. `\"` says what it means at
   the point it's written; `chr of 34` requires knowing that 34 is
   U+0022.
3. **It would not have closed the defect anyway.** `chr of n` gives one
   more way to *construct* a quote value at runtime, but the *literal
   syntax* would still be unable to denote a string containing one — the
   exact defect stays open, just less visible. This build's escapes make
   the literal syntax itself capable of every code-point sequence
   `for each` can already walk.

## The Phase 1 audit result

**The set is empty.** Every `.planes` file in the repository (40 files:
root, `demo/`, `grammar/`, `probe/`) was searched for a literal backslash
with a fixed-string grep (`grep -qF '\'`), avoiding any risk of a regex
metacharacter producing a false negative. The only hits — five lines, all
in `grammar/lexer.planes` — are inside `#` prose comments documenting the
very gap this build closes; none is inside a `"..."` token. See
`ESCAPE_AUDIT.md` for the full method and per-line table. No fixture
needed migrating; no corpus string's runtime value is at risk under the
new grammar.

What the audit's scope did **not** cover, and what surfaced anyway: two
property-based tests in `test_properties.py` (`test_count_of_matches_
code_point_length`, `test_first_n_of_string_is_a_code_point_prefix`)
generate random Unicode text at runtime and embed it directly into
Planes source via an f-string — their own docstrings said so:
"Planes strings have no escape syntax, so a generated string must embed
directly into source." That claim was true before Phase 2 and false
after: the random pool already contains a bare backslash, previously
safe to embed unescaped, now requiring escaping like any other quoted
format. Fixed at the embedding site (`planes_string_literal()`), not by
changing the tests' intent — they still verify `count of` and `first n
of` against arbitrary random text; they just build the source correctly
now.

## Whether `interp.py`, `render.py`, or `shapes.py` needed changes

**All three did.** This corrects the build prompt's own provenance note,
which — reasonably, given `interp.py` was unread at HEAD — anticipated
`interp.py` might need no change. It needed three.

Ruling 1 ("Escape processing happens in the lexer... `interp.py` needs
no change") holds for *escape resolution*: `interp.py` never sees an
escape sequence, and required no change to evaluate a `Str` node.
Ruling 3 ("the renderer must round-trip... check render.py and why_tree
output") is where the finding lives, and it is larger than the two named
files:

**The bug, reproduced before any fix (lines read: `render.py:89-93`,
its own module docstring at `render.py:7-8` — `render(parse(src))` must
parse to an equal AST for every program):**

```
>>> from parser import parse; from render import render
>>> src = 'x = "a\"b"\n'
>>> render(parse(src))
'x = "a"b"\n'          # does not even reparse: PlanesSyntaxError,
                       # unterminated string literal
```

`render_expr`'s `Str` case printed the resolved value straight between
bare quotes with no re-escaping — the exact inverse defect Phase 2
closed on the lexer side, now open on the renderer side, because nothing
before this build could produce a string whose rendering would need to
re-escape anything.

The same `.value[1:-1]` pattern that resolves `Str.value` (parser.py:
1028) also feeds five other AST fields, read directly to confirm:
`Because.text` (parser.py:512), `Rule.target` (parser.py:253, 362),
`Foreign.target` and a Foreign effect's literal target (parser.py:279,
366), and a `Note` entry's `from` text (parser.py:543). Every `render.py`
site printing one of these back inside bare quotes had the identical
bug — six sites total (`render.py:93,160,172,184,201,211`), all fixed
with one new function, `lexer.escape_string_literal` (the inverse of the
resolution already written for Phase 2), reused rather than
re-implemented per site.

A repo-wide sweep for the same `f'"{...}"'` shape (not scoped to
`render.py` and `why_tree` alone, since the first two findings implied
the pattern could recur anywhere a string-typed field is displayed)
found three more, all live:

- **`interp.py:547`**, `eval()`'s `Str` case — the *runtime* `Deriv`
  label for a literal, displayed by `why`'s one-line output (`explain()`,
  `interp.py:1044`) for any string that enters a derivation.
- **`interp.py:1046`** (now escaped), `explain()`'s own `because` line —
  a *different* function from `why_tree`, reached by every `why x`
  after a `because "..."` annotation (`interp.py:487`, `Why` statement
  execution: `self.annotations.get(stmt.expr.name)`, the same resolved
  text). This one is live and everyday, not `why_tree`'s unreached
  `because` parameter (see below).
- **`shapes.py:648,868`**, `const()`'s `Str` case and `claim_target()`'s
  literal-target case — the *static* analyser's own `StaticDeriv` labels,
  which `shapes.py:261-264` states explicitly mirror `interp.Deriv`'s
  shape "so the runtime and static graphs can eventually be compared."

`why_tree`'s own `because=` parameter (`interp.py:1081`) has the same
shape and is fixed too, even though nothing in the current codebase
calls it with a non-`None` `because` — a latent bug in a documented
public interface is still a bug, and the fix is free once
`escape_string_literal` exists.

**`text of` needed no change**, confirmed by reading it
(`interp.py:759-761`): it calls `fmt(arg.value)`, which for a string
returns the value verbatim with no quoting — the same function `why`'s
per-node value display uses, and by design never re-quotes as source, so
it was never exposed to this defect.

New tests pinning all of this, each verified to fail against the
pre-fix code before being written: `test_render.py` (5, covering all
four escapes through `render_expr`'s `Str` case, a `because` annotation,
a rule target, and a value-survives-the-round-trip check), `test_text.py`
(1, `why_tree`'s `because` line), `test_annotation.py` (2, `why`'s live
`because` line and literal-value output), `test_shapes.py` (1, the
static derivation label).

## Amber fire rate: before and after

**Zero, both times.** `test_amber.py`'s two corpus-wide fire-rate
assertions (`test_amber_never_fires_on_the_demo_module_graphs`,
`test_amber_never_fires_on_the_planes_corpus`) were part of the 556-test
green baseline at Phase 0 and remain green in the final 573-test suite.
`verify_grammar_and_amber.py`'s dedicated section F/H was re-run after
every substantive change in this build (four times total) and reported
`PASS` on every amber site and every fire-rate check each time; the only
number that moved was section I's benchmark overhead (parse-time cost of
the STRING regex change and the escape-resolution pass), which stayed
under the 25%-of-baseline blocking threshold throughout: +16.8%, +21.3%,
+16.3%, +14.0% worst-case across the four measurements, non-monotonic
(machine noise, not regression — no code path touched between the +21.3%
and +16.3% readings). No new guess site was added and no existing site's
behavior changed; the four guess sites §9 (grammar-as-data-and-scoped-
amber) scoped remain exactly four.

## The agreement table: PASS/PARTIAL

**29 PASS, 0 PARTIAL, 0 SKIPPED** — full corpus, full token-stream
equality, not partial-up-to-first-STRING. Before this build (PR #11's
state): 2 PASS, 27 PARTIAL, every PARTIAL diverging at exactly its first
`STRING` literal. Full per-file table with token counts:
`lexer-in-planes-verification.md`.

## Whether complete self-tokenization holds

**It holds, stated in those words.** `grammar/lexer.planes` tokenizes
its own 3835-token source — including every `STRING` literal in its own
documentation comments and pending-state records — to the exact token
stream `lexer.py` produces. It does the same for the generated
`grammar/vocabulary.planes`, 159 tokens. Zero divergence anywhere in
either file. This is the first closed bootstrap assertion in this
domain's history: a lexer for Planes, written in Planes, correctly
tokenizes itself, completely. Both checks are permanent tests
(`test_lexer_planes_tokenizes_itself_exactly`,
`test_lexer_planes_tokenizes_vocabulary_planes_exactly`), not probes.

## Every remaining language/architecture gap, and what closing it would cost

1. **A `to` function cannot raise a custom-message error.**
   `grammar/lexer.planes`'s STRING section documents this precisely at
   the point it matters: an unrecognized escape or a trailing backslash
   are errors `lexer.py` raises with a message naming the fix, and
   `lexer.planes` has no way to replicate that — `... or fail as tag`
   renames or catches a failure an expression already produced, it does
   not manufacture a new one from ordinary code. Untested by the corpus
   (`ESCAPE_AUDIT.md`: no string contains a backslash, valid or not) and
   by this file's own source (every escape it writes is one of the four
   valid ones). **Cost to close:** a new failure-construction primitive
   — plausibly a `fail with "message" as tag` expression form — which is
   a new keyword or a repurposing of `fail`'s existing grammar slot,
   either way a decision beyond this build's four-escapes scope and
   outside its stop-condition-1 boundary (no new keyword/builtin/effect
   kind/host method).
2. **`rules.py` cannot reuse `lexer.escape_string_literal`.** Four sites
   (`rules.py:89,158,190,452`) quote `rule.target` in violation/conflict
   messages with the identical unescaped-re-quote bug fixed everywhere
   else. Not fixed here: `rules.py`'s own docstring states `hashlib` is
   "the one import this file has ever needed — stdlib, not a `shapes`
   coupling," a deliberate architectural boundary. Importing from
   `lexer.py` would break that stated invariant; duplicating the
   four-entry escape table locally would create exactly the
   single-authored-copy drift risk `grammar_gen.py`'s D2 ruling exists
   to prevent for the vocabulary itself. Untested by the corpus either
   way (no rule target contains a backslash). **Cost to close:** a
   decision from whoever owns `rules.py`'s import boundary — relax it
   for one small, pure utility function, or accept a four-line local
   duplicate and the drift risk that comes with it. Not this build's
   call to make unilaterally.
3. **No numeric or Unicode escape.** Deliberately declined by this
   build's ruling (`\x41`, `A` reintroduce the opacity `chr of n`
   was declined for, and interact badly with §105's rule that
   normalization is explicit). Not a gap; a closed door, on purpose.

## What this build disproved about this prompt

**That closing the STRING gap in the grammar would be self-contained.**
The build prompt's own provenance note anticipated `interp.py` might
need a change and specified checking `render.py` and `why_tree` for
exactly this reason — but the actual shape of the defect was larger than
"the renderer's `Str` case" and "`why_tree`'s `because` line": it was
*every* place in the codebase that takes a string-typed AST field
resolved via `.value[1:-1]` and prints it back inside bare quotes as if
it were still-unescaped source, which turned out to be six sites in
`render.py`, two in `interp.py`'s live runtime path (not the one the
prompt named), two more in `shapes.py`'s static analyser, and four in
`rules.py` that could not be closed within this build's own stated
architectural constraints. The defect this build set out to fix (a
grammar that could not denote all text) and the defect it found while
fixing it (a family of call sites that assumed text, once denoted, would
never need denoting *again*) are the same defect, read from the two ends
of a round trip — Phase 2 closed the lexer end; Ruling 3 forced closing
the render end, and the full sweep it triggered was not optional once
the first instance (`render.py`) proved the shape was real and load-
bearing (its own module docstring makes the round-trip an explicit
invariant, not a nicety).

## Is the parser next, and is it a weekend?

**No — not at the pace this build and its two predecessors set for the
lexer, and the size difference says why.** `lexer.py` is ~150 lines of
actual tokenizing logic behind a single regex table; `parser.py` is
1200+ lines implementing full expression precedence, statement grammar,
and — the part with no lexer analogue at all — four scoped amber
disambiguation sites (`grammar-as-data-and-scoped-amber`, addendum v4.2
§69.1) where the grammar is genuinely ambiguous and the parser has to
choose a reading and justify it. The lexer took three builds to close
completely (`PROBE_LEXER.md`'s capability probe → `fix/text-iteration-
and-the-lexer`'s `for each`-over-a-string and bracket-misparse fixes →
this build's STRING escapes) even though its state machine is a single,
mostly-mechanical fold over one line's characters at a time. A parser
written in Planes would need, at minimum: the same probe-first discipline
applied to a much larger grammar (recursive-descent call structure,
operator-precedence climbing, the four amber sites' disambiguation logic
specifically — each of which is itself a small research question, not a
line of code), and — the lesson this build just relearned the hard way —
a check, up front, for whether *printing a parsed-and-then-rendered
Planes-in-Planes program back out* has the same round-trip assumptions
this build found broken in `render.py`. Scoped as a single weekend: no.
Scoped as this lexer's three-build arc, once more, with a probe phase
that explicitly budgets time for the amber sites: plausible, and the
honest next question to ask before scheduling it.
