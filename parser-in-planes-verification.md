# parser-in-planes-verification.md

**Build:** feat/parser-in-planes, Phase 4
**Method:** `scripts/parser_corpus_agreement.py` -- for every corpus file,
`parser.py`'s real `parse()` and `grammar/parser.planes`'s
`canonical-of-program-source` are each run, and their canonical AST text
forms (test_parser_in_planes.py's harness, proven agreeing on a
hand-built fixture in Phase 1) are compared. **PASS** means the two
canonical forms are byte-identical. **FAIL** means one side raised before
producing a canonical form at all -- there is no partial AST to diff,
only a firm stop, so nothing in this run falls into **PARTIAL**
(byte-identical up to a divergence point). Nothing is changed by running
this script; it only measures.

## Result: 4 PASS, 0 PARTIAL, 26 FAIL, out of 30

| # | File | Status | First disagreement / reason |
|---|---|---|---|
| 1 | `annotated.planes` | FAIL | `rule` statement -- past the section 3 ladder |
| 2 | `foreign.planes` | FAIL | cons-list cursor construction ceiling (147 tokens > ~140) |
| 3 | `gate.planes` | FAIL | cons-list cursor construction ceiling (201 tokens > ~140) |
| 4 | `hn.planes` | FAIL | cons-list cursor construction ceiling (167 tokens > ~140) |
| 5 | `money.planes` | FAIL | juxtaposition call (`total ...`) -- needs `known_funcs` |
| 6 | `names.planes` | FAIL | juxtaposition/paren-arglist ambiguity site -- needs `known_funcs` |
| 7 | `ordinary.planes` | FAIL | `for each` used as an expression (comprehension) -- out of scope |
| 8 | `pypi.planes` | FAIL | cons-list cursor construction ceiling (158 tokens > ~140) |
| 9 | `demo/app/config.planes` | **PASS** | -- |
| 10 | `demo/app/main.planes` | FAIL | juxtaposition call (`package ...`) -- needs `known_funcs` |
| 11 | `demo/app/net.planes` | FAIL | *(not a disagreement -- see below)* |
| 12 | `demo/association.planes` | **PASS** | -- |
| 13 | `demo/clash/cache.planes` | FAIL | juxtaposition call with a string argument |
| 14 | `demo/clash/loader.planes` | FAIL | juxtaposition call with a string argument |
| 15 | `demo/clash/main.planes` | FAIL | multiword function name (`record ...`) |
| 16 | `demo/fdiff/v1.planes` | FAIL | `foreign` declaration -- past the section 3 ladder |
| 17 | `demo/fdiff/v2.planes` | FAIL | `foreign` declaration -- past the section 3 ladder |
| 18 | `demo/pkgs/cachelib.planes` | FAIL | `write ... to ...` -- past the section 3 ladder |
| 19 | `demo/pkgs/fetcher.planes` | FAIL | juxtaposition call (`url ...`) |
| 20 | `demo/pkgs/logger.planes` | **PASS** | -- |
| 21 | `demo/pkgs/mathlib.planes` | **PASS** | -- |
| 22 | `demo/pkgs/sneaky.planes` | FAIL | juxtaposition call with a string argument |
| 23 | `demo/rename/cache.planes` | FAIL | juxtaposition call with a string argument |
| 24 | `demo/rename/loader.planes` | FAIL | juxtaposition call with a string argument |
| 25 | `demo/rename/main.planes` | FAIL | multiword function name (`record ...`) |
| 26 | `demo/rules/clean.planes` | FAIL | `rule` statement -- past the section 3 ladder |
| 27 | `demo/rules/exception.planes` | FAIL | `rule` statement -- past the section 3 ladder |
| 28 | `demo/rules/violation.planes` | FAIL | `rule` statement -- past the section 3 ladder |
| 29 | `demo/v1.planes` | FAIL | multiword function name / juxtaposition (`config ...`) |
| 30 | `demo/v2.planes` | FAIL | juxtaposition call with a string argument |

## Classification (build prompt section 4: every disagreement classified before it is fixed)

Every failure falls into one of the categories the build prompt names,
and none is a bug in `grammar/parser.planes` or a genuine difference in
what the two implementations consider the same AST:

### Language gap -- amber/`known_funcs`-dependent calls (14 files)

`money.planes`, `names.planes`, `demo/app/main.planes`,
`demo/clash/cache.planes`, `demo/clash/loader.planes`,
`demo/clash/main.planes`, `demo/pkgs/fetcher.planes`,
`demo/pkgs/sneaky.planes`, `demo/rename/cache.planes`,
`demo/rename/loader.planes`, `demo/rename/main.planes`,
`demo/v1.planes`, `demo/v2.planes` -- **13 files**, plus `names.planes`
counted above (14 total). Every one uses juxtaposition (`ask url`,
`total "..."`) or a multiword function name (`fetch stories`,
`record ...`). `parser.py` resolves these against `Parser.known_funcs`, a
name-to-arity table built by `prescan_funcs` and threaded through
amber's own disambiguation (`check_juxtaposition_ambiguity`,
`raise_amber_multiword`). Amber is explicitly out of scope for this
build (section 7 invariant 3, Build 5) -- and `known_funcs` is the
shared prerequisite amber's four sites and this shape both depend on
(`PROBE_PARSER.md` capability 7). Building the name table without
building amber to consume it would leave every one of these calls
resolved *silently* (never refusing an ambiguous reading), which is not
a smaller version of the real capability -- it is a different, unsound
one. Declined for the same reason amber itself is declined here: it is
Build 5's job, not this one's.

### Language gap -- statement forms past the section 3 ladder (7 files)

`annotated.planes`, `demo/rules/clean.planes`,
`demo/rules/exception.planes`, `demo/rules/violation.planes` (`rule`);
`demo/fdiff/v1.planes`, `demo/fdiff/v2.planes` (`foreign`);
`demo/pkgs/cachelib.planes` (`write ... to ...`). The ladder (section 3)
named assignment, show, if/else, `to` definitions, give, for each, and
use as the rungs to build, with "everything else" as its own, later
rung. `rule`, `foreign`, and `write` are real, well-specified statement
forms `parser.py` handles (`parse_rule`, `parse_foreign`,
`trailing_or_fail`'s `WriteTo` path) -- not attempted this build, and
each would be a clean, bounded addition on top of the same
`parse-statement` dispatch every other rung already extends.

### Language gap -- `for each` as an expression (1 file)

`ordinary.planes` uses the comprehension form (`for each x in xs where
...: expr`, evaluating to a list) from expression context. Phase 3
explicitly scoped this build to the *statement* form of `for each`
(`as_expr=False`); the wrapped-header expression form is the one thing
capability 4's own writeup flagged as unbuilt here, consistent with list
and record literals also starting outside Phase 2's named scope (those
two were cheap enough to add anyway; the wrapped comprehension header is
a materially bigger addition -- a distinct block-vs-inline body shape
matrixed against the wrap detection itself).

### Language gap -- the cons-list cursor's construction ceiling (4 files)

`foreign.planes` (147 tokens), `pypi.planes` (158), `hn.planes` (167),
`gate.planes` (201) -- every corpus file over ~140 tokens. `to-cons`
(capability 4, `PROBE_PARSER.md`) builds the cursor via `reverse-into`
(safe, a single `for each` fold) then `unreverse` (recursive, one call
per token) to restore forward order -- the same recursion-per-item shape
capability 4 itself found hits the ceiling on a 200-item plain list.
**Caught cleanly, not a crash**: `#14`'s recursion-too-deep fix converts
the raw `RecursionError` this would have been into a named, catchable
`PlanesError`, exactly the synergy that build's own report projected
("Build 4 is further de-risked... its eventual recursive descent... now
fails cleanly instead of crashing raw"). Not fixed here -- see
`REPORT_PARSER_IN_PLANES.md`'s remaining-gaps section for what closing
it would cost.

### Not a disagreement -- test methodology, not a language gap (1 file)

`demo/app/net.planes` fails on **both** sides for the same reason:
`parser.py`'s own bare `parse(src)` (no `known` map) cannot resolve
`api base`, a multiword function defined in `config.planes`, another
file in the same module graph. `test_bracket_misparse.py`'s own corpus
test documents this exact case and works around it with
`shapes.analyse_file(path, follow=True)`, which loads the whole graph
first. This script does not do that (deliberately -- it is testing
`parse()` in isolation, matching Phase 2/3's own fragment-testing
style), so this is the harness's own known limitation, not evidence
either parser disagrees with the other.

## What zero PARTIAL means

Every one of `grammar/parser.planes`'s failures is a **refusal**, not a
silent wrong answer: an unbuilt statement form raises a named
`parse-error` naming the unhandled construct, and the cursor-construction
ceiling raises the same `recursion-too-deep` `#14` built. Nothing in this
run produced a canonical form that *looked* complete but disagreed with
`parser.py`'s -- the ladder rungs that are built (assignment, show,
if/else, `to` definitions, give, for each-as-statement, use, list/record
literals, let) hold exactly, on every file and fragment that reaches
them, with no near-miss found anywhere in this corpus.
