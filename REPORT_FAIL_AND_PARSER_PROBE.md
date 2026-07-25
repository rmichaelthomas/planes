# REPORT_FAIL_AND_PARSER_PROBE.md

**Build:** feat/fail-primitive-and-parser-probe
**Base:** `main` at `d7687f7`
**Result:** 603/603 tests passing (573 baseline + 30 new), ruff/mypy/
`audit_locked_vs_built.py`/`grammar_gen.py --check` all clean at every
commit, amber fire rate zero throughout, reserved-word ceiling unchanged
at 32/8/7/8.

---

## What shipped

- **Ruling 1**: `escape_string_literal` and STRING escape resolution
  relocated from `lexer.py` to a new leaf module, `planes_text.py` — pure,
  zero project imports, on `planes_num.py`'s pattern. `rules.py`'s four
  quote-in-message sites (`condition()`, the uncertain-target message,
  `_render_vacuous`'s situation-3 message, the equal-specificity conflict
  message) are fixed, closing `REPORT_STRING_ESCAPES.md`'s gap 2.
- **Ruling 2**: `fail <message> as <tag>`, a new statement, spelled with
  `fail`/`as` — both already reserved, so the count stays 32. Same
  `{tag, detail}` record shape `or fail as` produces; same propagation
  channel (verified, not assumed — see below); no new effect kind, but
  the message expression is walked for effects so an `ask`/`read` inside
  it still reaches the static surface.
- `grammar/lexer.planes` uses `fail` to raise its own unrecognized-escape
  and unterminated-string errors — closing `REPORT_STRING_ESCAPES.md`'s
  gap 1, at the exact site that reported it. The two implementations'
  messages agree exactly (tested directly, not assumed from shared code).
- **A bug found and fixed while running this build's own §7.2 gate
  self-check, not deferred to review.** `lexer.py`'s unterminated-string
  message (unchanged since PR #12) said *"a backslash right before the
  closing quote escapes that quote"* even for a plain forgotten closing
  quote with no backslash anywhere on the line — inventing an
  explanation that never occurred. Fixed at the root (`lexer.py`
  distinguishes the two cases by whether the unmatched remainder ends in
  a quote — an odd backslash count precedes one only if a backslash is
  actually there) and mirrored in `grammar/lexer.planes` (a new
  `ends-in-escaped-quote` flag, true only immediately after resolving
  `\"` — the one path a literal quote can enter accumulated text by,
  since a raw `"` closes the token immediately rather than joining it).
  Both cases verified to agree between the two implementations, not just
  the one this build originally wrote. This is exactly the standing
  instruction this project's build prompts carry throughout — a closable
  finding gets fixed, not just recorded — applied to a self-check gate
  result rather than to a phase's own primary work.
- **Phase 3**: `PROBE_PARSER.md` — seven capability probes, all either
  WORKS or WORKS WITH FRICTION, no outright MISSING. Three findings
  beyond what the seven questions asked for directly (see below).

## What did not ship

- No parser. Phase 3 is explicitly an inventory, not an implementation.
- No fix to the `of`-binds-tighter-than-`-` surprise capability 1 found —
  it is documented, not changed; changing operator precedence is a
  language change with its own blast radius, out of this build's scope.
- No change to Python's recursion limit or any recursion-depth guard in
  `interp.py` — the ~140-deep ceiling and the raw `RecursionError` it
  leaks are reported as findings (capability 1), not patched. Raising
  `sys.setrecursionlimit()` trades a clean crash now for a segfault-range
  crash later; catching `RecursionError` and re-raising as `PlanesError`
  is a real, scoped fix this report recommends but does not make (out of
  a "probe, don't build" phase's scope).

---

## Ruling 1, executed

`escape_string_literal` and `resolve_string_escapes` (the latter renamed
from lexer.py's private `_resolve_string_escapes`, split into a pure core
in `planes_text.py` plus a thin `PlanesSyntaxError`-raising wrapper that
stays in `lexer.py`) now live in `planes_text.py`. Confirmed pure: it has
zero `import`/`from` statements at all (`test_planes_text.py`, both by
parsing its own AST and by checking no project-module name appears in its
loaded namespace).

**`rules.py`'s stated invariant is intact, read against its own words, not
against the report's paraphrase of them.** The docstring says: *"this
module only consumes [Surface] through the public `Surface` queries...
If this file ever needs to reach inside `Analyser`, `Consts`, or `Effect`
construction, that is a finding about §8"* — a claim about **architectural
coupling to `shapes.py`'s internals**, not a claim that the file may
import nothing at all. `planes_text.py` is a leaf utility with no project
dependencies of its own; importing it does not reach into `Analyser`,
`Consts`, or `Effect` construction, and `rules.py` still doesn't. The
pre-existing test that asserted the narrower reading
(`test_rules_module_imports_only_hashlib`) is updated to
`test_rules_module_imports_only_hashlib_and_planes_text`, asserting
`imports == {"hashlib", "planes_text"}` — the actual invariant, not a
stricter one nobody stated.

## Ruling 2, executed

`fail <message> as <tag>` is a new statement (`Fail` in `lexer.py`,
parsed in `parser.py`'s `parse_statement`, executed in `interp.py`'s
`exec_stmt`). **`fail`/`as` were already reserved** (by `or fail as`'s
own grammar) — the reserved-word count is unchanged at 32, confirmed
directly (`"fail" in KEYWORDS`, `"as" in KEYWORDS`, both `True` before
this build touched anything).

**User-raised failures share the existing propagation channel — verified
by reading `interp.py`'s `OrFail` handling before writing any code, per
this build's own provenance note that this was unverified and
load-bearing.** `PlanesError` (`interp.py:142`) is a plain Python
`Exception`; `or fail as`'s handling (`interp.py:650-663`) is an ordinary
`try`/`except PlanesError`. `raise PlanesError(stmt.tag, v.value)` (the
`Fail` case) therefore enters exactly the same channel every other
failure already uses — confirmed with a real test, not just by reading
the code: a `fail` inside a called function, wrapped by an outer `or fail
as`, has its tag renamed exactly the way any other propagated
`PlanesError` would (`test_fail.py`,
`test_a_fail_inside_a_called_function_propagates_through_or_fail_as`).
No second channel; stop condition 2 does not apply, satisfied by
construction rather than by the report's fallback language.

## Whether `shapes.py` needed a change for `fail`

**Yes — one case, and a second file (`render.py`) neither this build's
own Ruling 2 nor the base report anticipated needed one, found by reading
the relevant dispatch before adding the node, not by assuming a fallback
would be safe.**

`shapes.py`'s `walk()` (`shapes.py:430-607`) dispatches by `isinstance`
across every AST node type it cares about, with a `return set()` fallback
at the very end (`shapes.py:607`) for anything unmatched. Read directly:
that fallback would have made a bare `fail` correctly contribute no
effect *by accident* — but it would also have silently dropped any real
effect inside `message` (`fail (ask url) as tag` would vanish from the
static surface entirely, an unsoundness the oracle exists to catch). The
`Fail` case added (`shapes.py`, alongside `Give`/`Why`) walks
`node.message` for effects while adding none of its own — confirmed with
a test that puts a real `ask` inside a `fail` message and checks it
survives into `analyse()`'s effect set
(`test_an_effect_inside_the_message_is_still_in_the_static_surface`).

`render.py`'s `render_stmt` (`render.py:243-271`) has a **different**
fallback: an unmatched statement type is rendered as a bare *expression*
(`render_expr(node)`), which would have hit `render_expr`'s own fallback
— `raise ValueError(f"render_expr: unhandled node type ...")` — meaning
any program containing a `fail` statement would have **crashed the
renderer** without an explicit `Fail` case. Added
(`render.py:264-266`), confirmed by round-trip tests including one with
an escaped quote in the message.

## Amber: sites and fire rate, before and after

**Before this build (baseline, `d7687f7`):** four guess sites, fire rate
zero (part of the 573-test green baseline).

**After Phase 2** (the only phase that touches grammar — a new statement
form): **still four guess sites, fire rate still zero**, re-measured
directly with `verify_grammar_and_amber.py` after every substantive
change across this build (six full runs total). `fail`/`as` at the start
of a statement is unambiguous with `or fail as`'s mid-expression form —
both tokens were already reserved before this build, so no new
interpretation became possible, and no new guess site could be
manufactured by construction. Benchmark overhead (section I, non-
blocking under 25%) ranged 14.0%–21.6% across all six runs, consistent
with pre-existing machine-noise variance already observed in the prior
build — no monotonic trend, no regression traced to any specific commit.

## The seven parser capability verdicts

Full transcripts, verbatim amber refusal text, and per-site written
statements: `PROBE_PARSER.md`. Summary:

| # | Capability | Verdict |
|---|---|---|
| 1 | Recursion to fixed depth | WORKS WITH FRICTION |
| 2 | Mutual recursion | WORKS |
| 3 | Record with payload + position | WORKS |
| 4 | Cursor over a token list | WORKS WITH FRICTION |
| 5 | Nested tree | WORKS |
| 6 | Raising a parse error, nested | WORKS |
| 7 | Amber's four sites | shared prerequisite MISSING, workaround WORKS WITH FRICTION |

**Capability 7's four written statements** (condensed here; full text in
`PROBE_PARSER.md`, each checked against real, verified-firing fragments
from `test_amber.py` and the actual amber refusal text, not paraphrased):

- **Site 1** (multiword name): unbounded `NAME`-token lookahead
  (capability 4's cursor), building and looking up every prefix length —
  needs the dynamic-lookup workaround, nothing else new.
- **Site 2** (juxtaposition): two arity lookups and a three-way branch —
  the simplest of the four, needs only the dynamic-lookup workaround.
- **Site 3** (paren-arglist): needs the dynamic-lookup workaround *plus*
  two pieces no prior probe established — bracket matching over the
  cursor (bounded by paren-nesting depth, not token count) and rendering
  a token span back to text — both reduce to already-proven capabilities,
  just more assembly.
- **Site 4** (rename clause): the Python implementation's `name.split(" ")`
  has no Planes equivalent (checked against the 8-builtin closed set:
  none), but a Planes-native rewrite sidesteps it — keep the multi-word
  name's parts as a list from the point of tokenization, never join and
  re-split.

## Every remaining gap, and what closing it would cost

1. **`of` binds tighter than `-`** (capability 1). `countdown of n - 1`
   silently means `(countdown of n) - 1`. Not new — this is how the
   grammar has always worked, and `render.py`'s parenthesise-every-
   argument convention already exists because of it — but this build is
   the first to show it actively breaking hand-written recursive code,
   not just being a renderer style choice. **Cost to close:** a
   precedence change (make `of`'s argument extend across `+`/`-` at
   comparison-or-lower precedence, matching juxtaposition's existing
   `parse_additive` behavior) or better diagnostics (a targeted warning
   when a call immediately precedes a binary operator inside a function
   that recurses into itself) — either is a real, scoped language change,
   out of this build's mandate.
2. **The ~140 recursion ceiling, and the raw `RecursionError` it leaks**
   (capability 1). **Cost to close:** catch `RecursionError` in `call`/
   `invoke` (`interp.py`) and re-raise as a `PlanesError` naming the
   depth and the fix (rewrite as iteration, or reduce nesting) — a small,
   scoped, low-risk change; the depth ceiling itself is harder to raise
   safely (Python's own C-stack limit sits behind
   `sys.setrecursionlimit()`, and setting it too high trades a clean
   Python exception for a process crash).
3. **No dynamic, string-keyed record lookup** (capability 7's shared
   prerequisite) — the largest finding of this phase, affecting every
   one of the four amber sites and, plausibly, any future Planes-in-
   Planes tool that needs a symbol table. **Cost to close:** a genuinely
   new capability — either a builtin (`lookup of table, key`, spending
   one of the 8) or new syntax (dynamic `[...]` field access, which #11
   already declined for lists/strings on grounds that would need
   revisiting for records specifically). Not attempted here; the linear-
   scan workaround is verified sufficient for table sizes a real
   `known_funcs`-equivalent would hold.
4. **No string-split builtin** (capability 7, site 4). Sidestepped by a
   restructuring that avoids needing it (see above) — not a live gap for
   Route B specifically, but worth naming for any future need to split
   text on a delimiter.

## What this build disproved about this prompt

**That Ruling 1 and Ruling 2 were independent, cleanly-scoped moves.**
Ruling 1 read as "relocate a utility function" — and turned out to
require re-deriving, empirically, exactly how `rules.py`'s stated
architectural boundary should be read (narrower than the base report's
paraphrase), not just moving code. Ruling 2 read as "add a statement
that raises an error" — and required finding, by reading `render.py`'s
fallback dispatch before trusting it, that the *renderer* — not the
interpreter, not the analyser, the part of the codebase furthest from
"does `fail` work at runtime" — would have crashed on any program using
the new construct, a defect this build's own Ruling 3 (from the prior
session) should have made obvious to check for on sight and did not,
until this build's own read of `render_stmt` surfaced it independently.
Two rulings the prompt treated as separable turned out to share the same
shape of risk: **a new AST node is never really "added" until every
exhaustive `isinstance` dispatch across the codebase — not just the ones
a prompt names — is confirmed to have a case for it, not a fallback that
happens to be safe by luck.**

## A scoped estimate for the parser

**Not "weekend or month" — a build-by-build breakdown, on the lexer's own
demonstrated arc.**

The lexer took three builds to close completely: a capability probe that
found the blocking gaps (`PROBE_LEXER.md`), a build that closed those
gaps directly in the language (`for each` over strings, the bracket
misparse), and a build that closed the STRING gap in the grammar itself.
The parser is larger by every measure that matters here — `parser.py` is
1200+ lines against `lexer.py`'s ~150 lines of actual tokenizing logic,
and it has no lexer analogue at all for the four amber sites, each of
which (per this phase's own findings) needs real assembly, not just a
capability that already exists.

**Build 1 — the parser probe, done.** This build. Its output: no outright
MISSING capability, but a precise map of what has friction and why.

**Build 2 — close the two cross-cutting frictions.** The `of`/`-`
precedence trap and the recursion-ceiling leak (gap 1 and 2 above) are
both small, well-scoped, and load-bearing for *anything* recursive
written in Planes from here forward, not just a parser — closing them
first de-risks every later build the same way `for each`-over-strings
de-risked the lexer's later phases.

**Build 3 — the dynamic-lookup capability.** Gap 3 above (capability 7's
shared prerequisite) blocks all four amber sites identically. Whether
this becomes a real language change (a builtin, spending one of the 8;
or new syntax, reopening #11's ruling for records specifically) or stays
a documented workaround (the linear-scan idiom, already verified
sufficient) is itself a decision worth its own session, given `chr of n`
and `rest n of x` were both declined on similar grounds in this
project's history — a `lookup of table, key` builtin would need the same
scrutiny before landing.

**Build 4 — the lexer itself, in Planes, doing the token-to-cons/for-
each+stack conversion this phase's capability 4 finding demands** — the
actual tokenizer-to-parser handoff, built on the scaling idiom this
phase verified (`for each` over the flat token stream, a shallow cons-
list stack for nesting), not the naive recursive-descent-with-materialized-
cursor shape that looks obvious and hits the ceiling at 200 tokens.

**Build 5 (or folded into 4, depending how build 3 lands) — the four
amber sites**, each requiring the site-specific assembly `PROBE_PARSER.md`
already wrote down (site 3's bracket matching and token-span rendering
being the largest single piece of new plumbing among the four).

**The load-bearing unknown is Build 3.** Everything downstream of it
(builds 4 and 5) is scoped and de-risked by this phase's own probes —
real assembly work, not open questions. Build 3's outcome — whether
Route B gets a new builtin — is the one decision this report cannot make
for whoever reviews it, and it is the one thing worth resolving before
committing to a total build count.
