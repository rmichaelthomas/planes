# REPORT_RECURSION_AND_AMBER_SITE5.md

**Build:** fix/recursion-leak-and-fifth-amber-site
**Base:** `main` at `5d455a1` (confirmed — HEAD matched exactly before branching)
**Result:** 611/611 tests passing (603 baseline + 8 new), ruff/mypy/
`audit_locked_vs_built.py`/`grammar_gen.py --check` all clean at every
commit, amber fire rate zero throughout (four sites, unchanged), reserved-
word/builtin/effect-kind ceiling unchanged at 32/8/7.

---

## What shipped

- **Ruling 2 (Phase 1):** `interp.py`'s `invoke()` catches `RecursionError`
  narrowly — only around the recursive re-entry through a function's own
  body (`exec_block(fn.body, inner)`), nowhere else in the call machinery
  — and re-raises as `PlanesError("recursion-too-deep", ...)`, naming the
  function and the iterative `for each` idiom that replaces per-item
  recursion. No `sys.setrecursionlimit`, no Planes-level depth counter.
  `test_recursion.py` (6 tests): self- and mutual recursion past the
  ceiling both raise the shaped error, not `RecursionError`; safe depth
  is unaffected; the error is catchable by `or fail as` (v9.0 §106).
- **Ruling 3 (Phase 2), measured and declined:** `scripts/
  find_amber_site5_candidates.py` tokenizes all 36 `.planes` files in the
  repo and flags the `f of x <op> y` shape. 8 candidates, in 3 files —
  `AMBER_SITE5_BLAST_RADIUS.md` judges each individually. All 8 are
  either `text of X + "literal"` (string concatenation) or `pred of c or
  other-pred` (boolean chains); in every case the existing parse is what
  the author meant, and the alternate reading does not even type-check
  under the language's guarded semantics. The parser is unchanged: no
  fifth `raise_amber_*`, no change to `grammar/vocabulary.json` or
  `grammar/messages/amber.json`. Amber stays at four sites.
- **Ruling 1 (Phase 3), a decision not to build, made canonical:**
  `demo/association.planes` — a table of `{name, value}` records, a
  `lookup` function doing a `for each … where` linear scan, a `show` of a
  hit and a miss. Enters the agreement corpus (29 → 30 files;
  `test_lexer_in_planes.py` and `test_bracket_misparse.py` both updated
  and re-verified at 100% agreement, self-tokenization still complete).
  `shapes.py`'s `const_call` had a real gap found while proving Ruling
  1's own justification: on its multi-statement-body fallback (any
  function that isn't a single `give` — this idiom's shape, generally),
  it discarded already-computed argument nodes, so `origins_of` on a
  value fetched through `lookup` stopped at the call and never reached
  the table. Fixed by threading `arg_nodes` into that fallback (and the
  arity-mismatch one, computed at the same point) — the folded value
  stays `UNKNOWN`, unchanged and still sound; only the derivation graph's
  completeness improved. `test_shapes.py` (2 new tests) pins the actual
  claim: the runtime/static oracle holds across the idiom, and
  `origins_of` traces `hit`/`miss` back to `prices`.

## No AST node added

This build adds no new AST node. `lexer.py`'s node classes are unchanged;
no exhaustive `isinstance` dispatch (`interp.py`'s `eval`/`exec_stmt`,
`shapes.py`'s `walk`/`const`/`assigned_in`/`calls_in`, `render.py`'s
renderer) needed a new case for one. The two source changes
(`interp.py`'s `invoke`, `shapes.py`'s `const_call`) both add a branch to
an *existing* case, not a new dispatch arm.

## Ruling 1 — the decision not to build, and its test

Both alternatives priced in `PROBE_PARSER.md` — a `lookup of table, key`
builtin, or dynamic `[...]`/`r[k]` syntax for records — are declined.
Records are structural; `shapes.py`'s dispatch and the static derivation
graph `origins_of` walks depend on every field access being a literal
name known when the source is written. Dynamic field access would make
that unknowable in general, degrading the effect-surface guarantee the
language exists to make — a sharper version of #11's declined ruling for
lists and strings, made on soundness grounds rather than convenience.

The list-of-records `for each … where` scan has no such problem: every
field access inside it is a literal name, so the analyser sees exactly
what is read. `test_shapes.py::test_origins_of_traces_an_association_
lookup_back_to_its_table` is the actual justification, pinned: the
matched *value* stays statically `UNKNOWN` (correctly — which record
matches depends on the runtime key), but the derivation chain still
proves `hit` and `miss` both derive from `prices`, the table `lookup`
scanned. That is "the analyser sees through it," precisely stated: sound
widening where the value is genuinely undecidable, full traceability
everywhere it is not.

`unbound` v3.0 §42 (placing optimization below the visible line, cited
in Ruling 1 and Phase 1 ruling 4) was not re-read this session — carried
from the chain, as the build prompt's own provenance section flagged.
Nothing in this build's reasoning depends on its exact wording beyond
"the O(n) scan is a semantic description, not an implementation
commitment," which is consistent with every other citation of it found
in this repo's history.

## Ruling 2 — the measured ceiling, the message, what it names

Measured directly in this build, independently of `PROBE_PARSER.md`'s
figure (binary search over `countdown of N`, Python 3.14.6, default
`sys.getrecursionlimit()` of 1000, unmodified): **the last depth that
succeeds is 140; 141 raises.** This matches `PROBE_PARSER.md` capability
1 exactly, on a different Python patch version — the ~7-frames-per-call
cost `interp.py`'s call chain (`exec_stmt → eval → eval_binop/eval →
call → invoke → exec_block → exec_stmt`) imposes has not moved.

**No test asserts 140 (or any number).** `test_recursion.py` runs
`countdown of 2000` and a mutually-recursive equivalent — far past any
plausible ceiling — and asserts the *shape* of what comes back:
`PlanesError`, not `RecursionError`; `tag == "recursion-too-deep"`; the
function's own name in `detail`; the iterative-idiom fix text in `fix`.
If a future change alters frames-per-call and the real ceiling moves,
these tests do not need to change.

The message: `'{name}' recursed past the depth this interpreter can
follow`, with a fix hint naming the specific replacement (`for each` over
the whole collection, a state record threaded forward, a cons-list stack
sized to nesting depth rather than item count) — not a generic "reduce
recursion" but the actual idiom `PROBE_PARSER.md` capability 4 verified.

## Ruling 3 — the blast-radius measurement and the 2b decision

Measured before any parser code was touched (`AMBER_SITE5_BLAST_RADIUS.md`,
committed on its own before Phase 3 began). 8 candidate sites, in 3
files, all in `demo/rules/{clean,violation}.planes`,
`grammar/lexer.planes` (×3), and `hn.planes`. Every single one judged
individually as "the existing parse is what the author meant" — 8 for 8,
zero exceptions, and zero instances anywhere in the real corpus of the
ruling's own paradigm case (arithmetic inside the argument, `n - 1`-
shaped).

**Declined.** This is the build prompt's own "many instances, or any
where the current parse is clearly what was meant" branch. The
significance is not just the count: amber's other four sites refuse by
*syntactic shape*, not by semantic judgment of intent — that is their
whole design. A fifth site built the same way would refuse on shape
alone, with no way to distinguish "this `+` is clearly concatenation"
from "this `-` is clearly a mistake." Landing it would have refused all
8 of these existing, correct, currently-passing files — the fire-rate-
nonzero outcome Phase 2b's own second branch exists to catch, caught
here at measurement time instead of after landing and reverting. The
corpus overturned the ruling as written; that is a result, not a
failure — Ruling 3's own text anticipated exactly this outcome as one of
two legitimate ones.

## Amber sites and fire rate

| | Before | After |
|---|---|---|
| Site count | 4 | 4 (unchanged — Ruling 3 declined) |
| Fire rate on corpus | 0 | 0 (unchanged; now also verified against `demo/association.planes`) |

No location asserting "four amber sites" needed updating, because the
count did not change. Checked: `grammar/messages/amber.json` (four
distinct `site` locations, unchanged), `test_amber.py` (no hardcoded
count), `verify_grammar_and_amber.py` (no hardcoded count).
`PROBE_PARSER.md`, `REPORT_FAIL_AND_PARSER_PROBE.md`,
`REPORT_GRAMMAR_AMBER.md`, `REPORT_STRING_ESCAPES.md` are historical
records of when four was the live count and stay as they are, per this
repo's established convention of not editing closed reports.

## Corpus count, agreement, self-tokenization

- `test_lexer_in_planes.py`: `CORPUS` (root + `demo/**/*.planes`) is now
  30 files (29 at `REPORT_GRAMMAR_AMBER.md` §4, +1 for
  `demo/association.planes`). Full byte-identical agreement between
  `lexer.py` and `grammar/lexer.planes` holds across all 30 — **30 PASS,
  0 PARTIAL.** Self-tokenization (`grammar/lexer.planes` tokenizing
  itself, and `grammar/vocabulary.planes`) still complete.
- `test_bracket_misparse.py`'s independent 29-file corpus assertion
  (8 root + 21 demo, excluding `demo/cycle/*`) updated to 30 the same
  way; every file (except the documented `demo/clash/main.planes`
  collision case) still analyses clean through `shapes.analyse_file`.
- This is also a contribution to P-Q15's corpus half, which now stands
  at 30 of the 50–100 `unbound` v1.1 §22 item 7 calls for.

## Counts

- Reserved words: **32** (`test_names.py`'s ceiling test green; no word
  added — `RecursionError` handling and the association idiom both spend
  zero new syntax).
- Builtins: **8** — `count, lower, upper, text, whole, ask, read,
  normalize`. No `lookup` builtin added (Ruling 1).
- Effect kinds: **7** (`ask, read, write, show, clock, random, env`,
  unchanged).
- Host methods: **8** — the `Host` base class's `raise NotImplementedError`
  methods (`ask, read, write, show, clock, resolve, parse_json, to_json`;
  `record` and `target_hint` both have real default implementations and
  are optional, per `REPORT_HOST.md`'s original framing). `host.py` has
  zero lines changed in this build's diff.
- `audit_locked_vs_built.py`: **no drift**, every locked construct has
  code evidence, at every commit.
- No dynamic record access exists anywhere in the diff: no `r[k]`, no
  `lookup` builtin, `parser.py` itself has zero lines changed in this
  entire build.

## Remaining gaps, and what closing them would cost

- **The `of`/`-` precedence trap itself is unchanged.** Ruling 3 declined
  to add a parser-level refusal, but the underlying grammar fact — `of`
  binds its argument to a single primary, tighter than every binary
  operator — is exactly as true after this build as before. It remains a
  real thing a new Planes programmer can get wrong once (as
  `PROBE_PARSER.md` capability 1's own first attempt did), mitigated
  only by `render.py`'s convention of always parenthesizing call
  arguments and by this build's own measurement that it has not, in
  practice, produced a wrong program anywhere in the current corpus.
  Closing it for real (if a future corpus ever shows real confusion)
  costs a fifth `raise_amber_*` site plus a `grammar/messages/amber.json`
  entry — small, and now fully scoped by this build's own measurement
  script, which can simply be re-run against a larger or different
  corpus later.
- **The O(n) cost of the association idiom is real, not just described.**
  Ruling 1 treats it as below the visible line per `unbound` v3.0 §42,
  but no benchmark in this build measured it against a `known_funcs`-
  sized table (tens to low hundreds of entries, per `PROBE_PARSER.md`).
  Cheap to close: a timing test against a synthetic table at that scale.

## What this build disproved about this prompt

**Ruling 3, as the build prompt states it, does not survive contact with
the real corpus** — not a small miss, an 8-for-8 result the opposite of
what landing the site would have required. The prompt's own Phase 2b
anticipated this outcome as one of two legitimate branches and did not
treat it as a failure mode, which held up: this is not a build that came
up short, it is a build whose own measurement step did exactly the job
it was written for.

Separately, the prompt's phrasing of "Zero or few instances, all clearly
intentional: land the fifth site" reads, on first pass, as if it could
also describe this build's own 8-instance, all-intentional result — it
does not, once "fire rate must stay zero on the corpus after landing" is
taken seriously: amber refuses by syntactic shape, not semantic intent,
so "the author clearly meant X" is not evidence *for* landing a
shape-based refusal; it is evidence the refusal would misfire on exactly
that code. A future version of this ruling's own wording could make that
non-overlap explicit rather than leaving it to be worked out from the
fire-rate constraint stated two sentences later.

## The parser arc, re-scoped

`REPORT_FAIL_AND_PARSER_PROBE.md` projected five builds after the parser
probe (which was itself Build 1), with Build 3 — the dynamic-lookup
capability — named as the one load-bearing unknown everything downstream
depended on.

This build **is** Build 2 and Build 3, both closed in the same session:

- **Build 2 (cross-cutting frictions) — done.** The recursion-ceiling
  leak is closed (Phase 1). The `of`/`-` precedence trap is measured,
  not patched (Phase 2) — see Remaining Gaps above; it is now a known,
  bounded, empirically-checked property of the language rather than an
  open question.
- **Build 3 (dynamic-lookup capability) — collapsed, not built.** Ruling
  1 answers the question `REPORT_FAIL_AND_PARSER_PROBE.md` explicitly
  declined to answer: no builtin, no new record syntax. The list-of-
  records idiom is canonical, demonstrated, and analyser-sound (Phase
  3). Nothing about Build 4 or 5 is now blocked on a decision that has
  not been made.

**What remains is Build 4 (a parser written in Planes, doing the
token-to-cons/for-each+stack handoff `PROBE_PARSER.md` capability 4
demands) and Build 5 (the four amber sites' site-specific assembly,
still possibly folding into Build 4, exactly as the prior report left
that question open).** The arc is now **two builds, not five** — three
of the five are done or resolved in this session and the prior one
combined. Build 4 is further de-risked than the prior report left it:
its eventual recursive descent (if any survives the for-each+stack
idiom) now fails cleanly instead of crashing raw if it ever exceeds
depth, and the association idiom it will need for its own `known_funcs`-
style lookups (`PROBE_PARSER.md` capability 7's own stated use case) now
has a canonical, precedent-setting, corpus-checked implementation to
follow instead of only a probe file.

Phase 2's measurement did not change the arc's shape — Build 3 collapsing
was Ruling 1's doing, decided before Phase 2 ran. What it changed is
confidence: the arc's Build 2 entry is now closed on *measured* grounds
(an 8-for-8 corpus result) rather than an open question carried forward
un-investigated.
