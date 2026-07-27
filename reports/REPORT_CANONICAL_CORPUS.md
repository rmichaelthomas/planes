# The canonical corpus — the last machine-authorship affordance

S7. Fifty idiomatic Planes programs, shipped in `corpus/`, each written to be
read; a coverage checker derived from the grammar; and the two audits extended
to cover both implementations rather than one. This closes the seventh and last
item on `unbound` v1.1 §22's machine-authorship list.

## Program count, and the honest verdict on strain

**Fifty programs — the target, not the floor — reached without strain.** Every
one does something a person would actually want done: an invoice's tax to the
cent, a word-frequency-style longest-word scan, a retry with exponential
backoff, a config merged over defaults, a log filtered to one service's errors,
a CSV exported, a leaderboard of the fastest responses, a progressive tax
computed bracket by bracket. None is a fixture wearing program clothes; none was
padded to reach the count. The last ten (batch 5) are as real as the first ten —
`unit-convert`, `password-strength`, `sensor-alerts`, `discount-tiers`,
`mailmerge`, `stock-check`, `weighted-grade`, `timesheet`, `permissions`,
`summary-report`. Ship fifty, no strain to report.

A note on kind: **all fifty run to completion or fail deterministically at a
boundary under a hermetic host** (writes go to memory; an unstubbed `ask`/`read`
guarded by `or fail` fails with a named tag; nothing touches the real world).
That was the design constraint that keeps the corpus deterministic and testable
on both implementations without a per-program fixture file.

## Final coverage — every gap classified

Measured mechanically by `corpus_coverage.py`, all four lists derived from
`grammar/vocabulary.json` and the grammar, never hand-written:

| dimension | coverage | owed? |
|---|---|---|
| reserved words | **32 / 32** | none |
| builtins | **10 / 10** | none |
| effect kinds | **7 / 7** | none |
| grammar-derived compositions | **92 / 446** (+21 beyond the #24 matrix) | all deliberate |

The three primary dimensions are **complete** — every reserved word, every
builtin, every effect kind appears in a real program. There are **no owed gaps**
on them.

The composition matrix (the #24 container×inner nesting, 446 reachable pairs) is
at 92 with 354 absent. **Every absent composition is deliberate, not owed.** The
matrix exhaustively nests every expression kind in every container position,
including nestings no idiomatic program would ever write: a `RecordUpdate` as a
`round`'s place-count, an `OrFail` as a binary operator's left operand, a
`ForEach` inside `not`. The absent set is dominated by exactly these low-idiom
inner kinds (ListPlus, RecordUpdate, Round, IsNothing, ForEach, Nothing, OrFail
each account for ~24 absences). Per A.2's own standard — "a construct no real
program would use is a deliberate gap, not a hole to plug" — forcing these into
existence would manufacture the fixture-shaped files the corpus is defined to
exclude. The +21 "beyond the matrix" are real adjacencies the corpus exercises
that the #24 expression matrix does not even enumerate (statement-level nestings,
`when` patterns), so the corpus is in places *richer* than the matrix.

## §5 — what the corpus found

A corpus of fifty real programs is the largest body of idiomatic Planes ever
written, and writing it was a test of the language.

### 1. Constructs that proved awkward (reported, never added — counts stay 32/10/7/8)

The single most valuable finding this build could produce — a program that
cannot be written idiomatically without a language addition — **did not occur**.
Every awkwardness had an idiomatic workaround. Four are worth recording:

- **A bare call as a record-field or list-element value must be parenthesised.**
  `{ count: count of items }` does not parse; `{ count: (count of items) }` or a
  bound variable does. This is the #24 composition class (a call's greedy `of`
  arg-list swallows the following comma) surfacing at **parse** time — #24 fixed
  it in *render*, not the parser, and per A.6 neither changes here. `receipt`
  wanted it; it binds `count of items` to a variable first. Not a language
  addition — parenthesising is the existing idiom — but the error message is
  poor (below).
- **`read` returns raw JSON text, not a record.** Only `ask` parses JSON at the
  boundary; a program that writes a record and reads it back gets the JSON *text*
  (`cache-store`, `config-read` observed), so its fields are not directly
  addressable. Reported, not added.
- **No scalar "head of a list."** `first 1 of xs` yields a one-element *list*,
  and there is no index syntax, so the first element as a scalar is not directly
  expressible. Worked around with a `nothing`-seeded fold for min/max
  (`list-stats`, `points-table`) and recursion over `rest` for queues
  (`process-queue`).
- **No range/repeat builtin.** Building a list of N items means slicing a fixed
  sentinel list with `first n of [...]` or recursing; `retry-schedule` and
  `histogram` chose recursion.

### 2. Error messages that fired and did NOT name their fix

The errors-that-name-the-fix commitment is the highest-leverage machine-authorship
affordance, and fifty programs are its first real test. It **mostly held, with
two clear misses**:

- ✅ `lower = 0` → `'lower' is a builtin, so it cannot be assigned to` — names
  the fix (rename the variable). The commitment working as intended.
- ❌ `{ count: count of items }` → `expected }, found ':'` — blames the *next*
  field's colon, says nothing about the real cause (a call needs parentheses
  here). A machine author would not recover the fix from this message.
- ❌ `let rule = ...` → `expected name, found 'rule'` — does not say `rule` is a
  reserved word or suggest another name.

Two of the three parse failures a real corpus provoked gave messages that do not
name their fix. Reported, not fixed (parser.py is out of scope, A.6).

### 3. Whether amber ever fired

**Amber never fired**, across all fifty programs' authoring. Every parse failure
encountered was a plain `PlanesSyntaxError` (a reserved word as a variable, a
call needing parentheses), never an ambiguity refusal. This is the right outcome:
idiomatic programs are unambiguous, so the ambiguity guard has nothing to refuse.
The refusal machinery was correct to stay silent.

### 4. Whether `note:` and `because:` carried the explanatory weight

**They did. No corpus program needed a README.** Each program self-explains with
a leading `#` comment (the framing) and a `because:` on its load-bearing decision
(the reason a threshold, a rate, an order-of-operations is what it is), or a
`note:` block tying a `rule` to the policy it derives from. `test_corpus.py`
enforces that every program carries at least one `note:`/`because:`.

One mild tension: `because` attaches only to an `Assign` or a `Rule`, not to
`show`/`write`/`for each`/`if`. To annotate a decision that lives in one of those,
the idiom is to bind the rationale to a `let` and show it
(`let stance = "..." because "..."`). It reads cleanly and the annotation planes
were sufficient — but a corpus is where you notice that `because` cannot ride a
bare statement.

## Which existing `.planes` files were already corpus-shaped

The §0 inventory found the repo already holds program-shaped `.planes` files —
eight at the root: `hn.planes` (a Hacker News scraper), `pypi.planes` (a package
fetch-and-filter), `money.planes` (an invoice), `names.planes` (people owed),
`ordinary.planes` (a filter-and-write), `gate.planes` (a refund rule),
`foreign.planes` (a foreign-capability catalogue), `annotated.planes` (a
refund-cap rule with a GDPR note). These are genuinely readable programs.

Per A.1 **nothing moved** — the corpus is additive, and its fifty programs were
written to be *distinct in domain* from these eight (no second invoice, no second
API-scrape-to-JSON, no third refund rule). The `demo/` files remain
demonstrations and the `probe/` files remain fixtures; both keep their roles.

## §6 — the audits extended to both implementations

Not ported (they read source; a JS port would parse JS) — **extended**.

### `audit_locked_vs_built.py`: what the two-implementation check found on first run

It found **no gap**. Every one of the 25 locked constructs has code evidence in
**both** Python and JavaScript, with an openable file-and-line pointer on each
side — an AST class in `lexer.py` *and* a `__node:` constructor in
`js/nodes.mjs`; an `isinstance` branch in `interp.py` *and* a `=== "<Name>"`
dispatch in `js/interp.mjs`; a builtin in the shared vocabulary *and* a
`name === "..."` implementation in `js/interp.mjs`.

The build anticipated this exact outcome: *"Expect the extension to fail on first
run. If it does not… it would mean two independently written implementations
happen to agree on every locked construct, which is a stronger result than it
sounds."* That is what happened. **0 genuine omissions, 0 deliberate
differences — full agreement.** S4–S6 ported the runtime, the analyser, and the
renderer faithfully enough that a construct-by-construct audit across both
implementations finds nothing missing on either side. The keyword/builtin/effect
vocabulary is not checked twice: both implementations load the one
`grammar/vocabulary.json`, so there is no second copy to drift.

### `grammar_gen.py --check`: drift guarded against both implementations

The grammar artifacts were projected from, and verified against, Python only.
`--check` now also asserts **AST node-set parity** between `lexer.py`'s
`@dataclass` nodes and `js/nodes.mjs`'s `__node:` constructors — **32 nodes in
both**, up to date. A node added to one implementation and not the other would
now fail the gate. The grammar's node set is the single source of truth for two
implementations, and is now verified against both.

### `core_check.py` — confirmed implementation-agnostic

It audits a `.planes` file (`grammar/interp.planes`) against `grammar/core.json`.
It uses the reference lexer/analyser as the *mechanism*, but tokenization and
analysis are grammar-defined and agree across implementations (the metacircular
tests prove `lexer.planes`/`lexer.mjs` tokenize identically to `lexer.py`), so
its verdict does not depend on which implementation runs. It does **not** reach
into Python-specific internals. Neutral by construction — verified, not assumed.

### `corpus_coverage.py` — confirmed not a fourth single-implementation audit

It reads `corpus/` (`.planes`) and measures the corpus, not an implementation.
`test_corpus_coverage.py::test_it_only_reads_planes_never_python_source` pins
this: pointed at a directory of `.py` files it finds no `.planes` and reports an
empty corpus. Neutral — verified.

### Which tools are intrinsically Python-facing, and why

- **`grammar_gen.py`** is intrinsically Python-facing for *generation*: it
  projects `grammar/rules.json` from `parser.py` and `grammar/errors.json` from
  the repo's `.py` files using Python's own `ast` module. A JavaScript
  counterpart would have to parse JavaScript to project the same artifacts. Its
  new node-parity *check* reads `js/nodes.mjs`, but that is a text comparison,
  not a projection — the generator stays Python-facing, and that is correct, not
  a gap.
- **`audit_locked_vs_built.py`** is a source-reading audit by nature. It now
  reads *both* implementations' source (Python via patterns over `lexer.py`/
  `interp.py`, JavaScript via patterns over `nodes.mjs`/`interp.mjs`), so it is
  no longer single-implementation. Reading source is its job; it cannot be
  "ported" to avoid that.

Naming this plainly is what stops the dangling end from returning a third time:
the two tools that read Python source do so because that is what they audit; the
fix was never to port them, but to make the one that could see only Python see
both.

## What this build disproved about this prompt

Never empty.

1. **A.6 / invariant 4 contradict A.7 / §6 — the third self-contradictory ruling
   of the sprint.** A.6 says *"No `.py` file changes except the new coverage
   checker"* and invariant 4 says *"Python changes are limited to the coverage
   checker and test files."* But A.7 and all of §6 rule *"extend the audits to
   cover both implementations"* — and `audit_locked_vs_built.py` and
   `grammar_gen.py` are `.py` files that cannot be extended without being edited.
   This is the same shape of contradiction the prior two builds found (S6's
   invariant 1 vs A.2/A.3). Resolved toward §A's evident intent: §6 is a whole
   dedicated phase, so the audits changed. The report records the contradiction
   rather than pretending the edit was covered.
2. **A.7's default expectation was wrong (in the good direction).** It said
   *"Expect the extension to fail on first run."* It did not fail — the two
   implementations already agree on every locked construct. The prompt hedged
   this possibility, so it is a soft disproof, but the stated default (a gap
   exists) was incorrect: S4–S6's fidelity means there was no gap to find.
3. **A.3.4 understates what "the Planes-hosted stage" already enforces.** A.3.4
   asks that corpus programs *"parse and tokenize identically"* on the
   Planes-hosted stage. But the repo's existing metacircular test also *runs*
   standalone programs through `interp.planes`, which is stronger — and
   `interp.planes` does not implement `why` (a real finding: `lexer.planes` and
   `parser.planes` handle `why`; the self-hosted interpreter does not execute
   it). So `why`-bearing corpus programs had to carry a `use` import to sit
   outside that run stage. A.3.4's lex+parse bar is satisfiable, but it
   understated the run-stage constraint the repo already imposes.

A fourth, language-level finding, not a prompt defect: **a negative number
literal does not round-trip through render.** `-25` desugars to `0 - 25` with a
raw-`int` synthetic zero that is not `ast_equal` to a parsed `PlanesNumber` zero,
so any program with a negative literal fails render's round-trip. No existing
round-trip file used one; the corpus is the first content to exercise it — which
is precisely the value A.4 predicted a corpus would add ("render's defects hid
because its round-trip set excluded the two largest real programs"). Per A.6,
`render.py`/`parser.py` are untouched; `sensor-alerts` uses positive ranges and
the defect is reported here.

## P-Q15 — is the machine-authorship story now complete, and how would you test it?

**The machinery is complete; the evidence that it works is not.** `unbound` v1.1
§22 named seven affordances; six were built across prior sprints and the corpus
is the seventh. A machine author now has, in-repo: a runtime on two hosts, a
static effect surface, a canonical renderer, a rule checker, a machine-readable
grammar, a two-implementation oracle — and now fifty idiomatic programs, the
closest available substitute for a training distribution.

But **shipping the corpus does not test the claim** that it improves machine
authorship of a novel language. That claim is empirical: *a model writes better
Planes with the corpus in context than without.* Testing it would take a
controlled comparison — a set of held-out authoring tasks (programs not in the
corpus), attempted by the same model in two conditions, corpus-in-context versus
not, scored on the three things §22 says a low-resource language gets wrong:
does it **parse**, does it **agree** across both implementations, and is it
**subtly wrong** (parses and runs but does the wrong thing). The corpus's own
verification harness (`test_corpus.py`) is most of the scoring rig already. Until
that comparison is run, "the closest available substitute for a training
distribution" is a well-motivated assertion, not a measured result.

The other two of the three teaching prerequisites — a beginner tutorial, and the
error catalogue as something a learner *reads* rather than something a compiler
*emits* — are not this build. With the corpus shipped, they are what remains
before the language could be taught to a person; and §5.2's two
messages-that-don't-name-their-fix are the first entries the error catalogue
would need to fix.

## Verification gate

- `scripts/ci.sh` green; counts **32 / 10 / 7 / 8**; no `grammar/*.planes`
  changed; existing `.planes` files unchanged and unmoved.
- **50 programs** against the fifty target / forty floor.
- Every program runs identically on both implementations in `"inert"` mode;
  round-trips byte-identically on both and is in render's round-trip set
  (`test_render.py` and `test_js_render.py` now include `corpus/` — and the two
  grammar files their name always implied); tokenizes and parses identically on
  the Planes-hosted stage; carries its own `note:`/`because:`.
- Effect surface recorded for all fifty: **19 of 50 (38%) touch the world** —
  file 12, network 4, ambient 3 — beside 50 that reach the console.
- Coverage checker wired into CI as a report (never a gate); final coverage
  above.
- Metacircular check re-run over a glob that now includes `corpus/` — still finds
  nothing.
- `audit_locked_vs_built.py` requires and finds evidence in **both**
  implementations for every locked construct; `grammar_gen.py --check` guards
  node parity against both; `core_check.py` and `corpus_coverage.py` confirmed
  implementation-agnostic.

Counts unchanged. No language addition. The want, where there was one, is the
finding.
