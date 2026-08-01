# Is the declared core enough? — the measured answer

> **RESOLVED, 2026-08-01, in the build immediately after this one.** `when` has
> joined `grammar/core.json`'s `keywords`; the port surface is 29 keywords, not 28;
> `core_check.py`'s graph block now **gates** rather than reports; and the whole
> module graph runs under restriction. The measurement below stands exactly as it
> was taken — **nothing in the body of this report has been edited** — but its
> verdict sentence describes the repo as it was at `17d2881`, not as it is now.
>
> The choice this report declined to make ("the measurement does not choose") was
> made on the evidence that `reports/CORE_SUBSET.md` §1.1 had listed `when` as core
> from the beginning, with `grammar/parser.planes`'s node dispatch — 28 `when`
> tokens at `135ecb4`, 0 by the time the exclusion was written — as its justifying
> program. The exclusion was a correct observation about two files, generalised to a
> graph of five. See `reports/CORE_SUBSET.md` §4a.
>
> The evidence here is not lost by the fix: `test_js_core_restricted.py`'s
> `test_the_gap_that_was_found_stays_found_if_when_ever_leaves_again` reproduces
> every number in this report against a crafted core, on every gate run.

**Build:** `feat/core-sufficiency`
**Base:** `main` at `90d5ae9` — "The hand-edited files get the gate the generated ones
already had (#62)"
**Date:** 2026-08-01

---

## The verdict, in one sentence

**No — and it is short by exactly one keyword: `when`, needed by
`grammar/lexer.planes`, which `grammar/interp.planes` reaches through
`use parser`.**

Add `when` to `grammar/core.json`'s `keywords` and nothing else, and all three
metacircular stages run to completion under restriction over the entire corpus,
producing output byte-identical to the unrestricted run. That is the whole of the
gap, measured rather than estimated.

---

## What was actually claimed, and what was actually checked

`grammar/core.json` declares the **port surface**: the keywords and builtins a second
host must implement in order to run `grammar/interp.planes`. `core_check.py` has
always enforced one direction of that — that `interp.planes` never *mentions* a
construct outside the declared core. It has never enforced the converse, which is the
claim the file actually makes: **that the declared core is enough.**

Every downstream claim inherits from that one — the port surface, the "a second host
is seven methods, not a rewrite" claim, and the v11.0 §136 ruling that the
metacircular route saves only an eighth of the surface. None of them had a checker
behind it, because no host had ever been built that implements only the core and
refuses everything else.

This build built one, and ran `interp.planes` on it.

---

## The finding

`grammar/interp.planes` conforms. It has always conformed, and `core_check.py` was
right about it.

But `interp.planes` is not what a second host runs. Its first line is `use parser`,
and `grammar/parser.planes`'s first lines are `use lexer` and `use vocabulary`. The
artifact is `interp.planes` **plus its module graph**, and one member of that graph —
`grammar/lexer.planes` — dispatches on record shape with `when`, sixteen times.

`when` is a keyword `core.json` explicitly **excludes**, with this reason:

> `"when": "dispatch is flat `if k == ...` on the node kind (A.1/A.6), never
> `when subject is {...}` -- so `when` is NOT needed, refuting CORE_SUBSET.md's claim
> that it is the only substitute for the absent isinstance"`

That sentence is **true of `interp.planes` and false of the graph `interp.planes`
needs**. CORE_SUBSET.md's original claim — that `when` is the substitute for the
absent `isinstance` — was not refuted. It was refuted for one file and then declared
refuted for the port surface, and the lexer is where it holds.

### Where, exactly

`to step of state, c:` at `grammar/lexer.planes:88` is the lexer's **innermost
character loop** — every character of every program passes through the `when` on the
next line. It is not a corner case. All sixteen sites:

| file | line | construct |
|------|------|-----------|
| `grammar/lexer.planes` | 89 | `when` (in `step`, the per-character dispatch) |
| `grammar/lexer.planes` | 92 | `when` |
| `grammar/lexer.planes` | 95 | `when` |
| `grammar/lexer.planes` | 98 | `when` |
| `grammar/lexer.planes` | 101 | `when` |
| `grammar/lexer.planes` | 104 | `when` |
| `grammar/lexer.planes` | 107 | `when` |
| `grammar/lexer.planes` | 110 | `when` |
| `grammar/lexer.planes` | 113 | `when` |
| `grammar/lexer.planes` | 261 | `when` (in `flush-pending`) |
| `grammar/lexer.planes` | 265 | `when` |
| `grammar/lexer.planes` | 271 | `when` |
| `grammar/lexer.planes` | 275 | `when` |
| `grammar/lexer.planes` | 281 | `when` |
| `grammar/lexer.planes` | 287 | `when` |
| `grammar/lexer.planes` | 290 | `when` |

**All sixteen are reached at evaluation time**, on a single ordinary corpus file. Not
one is dead code, so no reading survives in which the gap is theoretical.

No non-core **builtin** is reached anywhere in the graph. `sine` and `root` are
reimplemented by `interp.planes` from exact parts rather than called, exactly as
`excluded_builtins` says, and the restricted run confirms it: the two names are never
dispatched.

---

## §4.2 — the module graph, per file

Computed, not asserted: one restricted census run per stage over the whole corpus,
attributing every reached construct to the file it fired in.

| file | non-core keywords reached | non-core builtins reached | ran to completion |
|------|---------------------------|---------------------------|-------------------|
| `grammar/interp.planes` | — | — | yes |
| `grammar/parser.planes` | — | — | yes |
| `grammar/lexer.planes` | **`when`** (16 sites) | — | **no** |
| `grammar/json.planes` | — | — | yes |
| `grammar/vocabulary.planes` | — | — | yes |

`use file` and `use http` name **builtin capability modules**, not files
(`js/modules.mjs`'s `BUILTIN_MODULES`), so they contribute no row: there is no
`.planes` source behind them to restrict.

Four of the five files in the graph conform. The one that does not is the one nobody
had ever checked, because `core_check.py`'s `violations()` tokenizes a single file and
the derivation was made from that file alone.

---

## The decisive control — the core is short by exactly one keyword

A refusal says the core is insufficient. It does not say by how much. So the same
restricted run was repeated against a core document widened by `when` **and nothing
else** (28 → 29 keywords), via the `--core-json` affordance:

| stage | corpus | restricted run, core + `when` | output vs the unrestricted run |
|-------|--------|-------------------------------|-------------------------------|
| `meta run` | 71 standalone files | **completed** | byte-identical |
| `meta lex` | 118 files | **completed** | byte-identical |
| `meta parse` | 71 standalone files | **completed** | byte-identical |

One keyword. Nothing else in the language is missing from the declared port surface,
and the restriction changes no answer once it is added.

---

## The delta between the two checks, stated plainly

`core_check.py` and this build's restricted mode answer different questions, and both
answers are needed.

| | `core_check.py` (before this build) | the restricted run (this build) |
|---|---|---|
| **subject** | one file — `grammar/interp.planes` | that file **and its whole module graph** |
| **when** | statically, over the token stream | at evaluation, at the moment the construct is reached |
| **finds** | every construct MENTIONED, reached or not | every construct REACHED, mentioned or not |
| **misses** | anything in a module the entry file `use`s | anything in code the run never enters |
| **answers** | "does interp.planes stay inside the core?" | "**is the core enough to run it?**" |

Neither subsumes the other:

- **Static sees unreached code; runtime does not.** A `let` inside a function nobody
  calls is a violation to `core_check.py` and invisible to the restricted run — the
  gate asserts exactly this, so the distinction is recorded and not merely true. A
  restricted run that completes therefore means "every construct this run reached was
  core", not "every construct in the file is core".
- **Runtime sees the graph; the static check did not.** That is the whole finding.

They are complementary, and here they **agree exactly**: sixteen static mentions,
sixteen runtime reaches, at the same sixteen lines. The static check was not wrong
about what it looked at. It was looking at one fifth of the artifact.

`core_check.py` now follows `use` too (§5.2), the way `analyse_file(target,
follow=True)` already did for effect kinds — the mechanism was in the file, applied to
one half of its job and not the other.

**The graph block reports and does not gate.** There are exactly two ways to make it
green: rewrite `grammar/lexer.planes`, or widen `grammar/core.json`. This build forbids
both by invariant, precisely so the finding cannot erase itself — and choosing between
them is a decision about what the port surface *is*, which is not a checker's to make.
It is reported in the shape `scripts/ci.sh` already has for a measurement that is not a
gate (`errors_coverage`, `corpus_coverage`, both `timed_soft`).

---

## Why this had to be a runtime check

A static pre-pass over the token stream would have restated `core_check.py` in a second
language and tested nothing new — `core_check.py` already proves `interp.planes` does
not *mention* a non-core construct. Sufficiency is the converse: **a host implementing
only the core can actually run it.** That is only testable by refusing at the moment of
evaluation, which is where the three guards are (`exec_stmt`, `eval`, `builtin`).

The gate asserts the distinction directly: a `let` in a function the program never
calls does **not** refuse under `--core`. A static implementation would have refused
it, and would have been a different tool.

---

## What it cost

See `feat-core-sufficiency-benchmarks-post.md` for the full table. In summary:

- **Flag off:** every case within the ±5% bar invariant 8 sets. The guards are one
  already-false boolean test per `exec_stmt` and per `eval`; the parser's line stamp is
  one already-false boolean test per statement parsed and stores nothing.
- **Flag on:** measured against the widened core, because a run against the real core
  stops at the first character of the first file and measures how quickly a doomed run
  finds out, not what the check costs.

---

## The gate found one thing about itself

`scripts/verify-core-sufficiency.mjs` was written, run (27 of 28 assertions passing,
the 28th being the finding itself, reported and non-blocking), and committed — and
`test_gate.py` then failed the branch, correctly, under the retirement rule: *a
verification script graduates into a suite or is deleted when its build merges, in
either language.* It did both in this PR. The durable assertions — including the whole
crafted-core anti-vacuity group, which is what proves the mode reads `core.json` rather
than a hardcoded list of four words — are now in `test_js_core_restricted.py` and run
on every gate. The script is gone. `core-sufficiency-verification.md` is the record of
its last run.

The one assertion not graduated is the byte-identity comparison against a `main`
worktree: it pins a commit that will have moved by next month, and its durable form
already exists, because `test_js_metacircular.py` compares this stack against the
Python implementation on every gate run and would fail if the flag-off behaviour had
changed.

---

## Two things found on the way

**§5.1 was already done.** The prompt directed an unconditional correction of
`core.json`'s `size.builtins` string from "11 of 12" to "11 of 13", naming both `sine`
and `root`. That correction is already on `main`: PR #62 (`90d5ae9`) made it, along
with adding both entries to `excluded_builtins` with their reasons. The prompt's base
was `721bffb`; `main` had moved two commits. **No change was needed and none was made**
— `git diff main -- grammar/core.json` is empty.

**The one keyword the AST cannot distinguish.** `round x to 2 places` and `round x to 2`
produce the identical `Round` node — `places` is optional in the source and the parser
records nothing, so the restricted mode reads a `Round` as spending `places` either
way. `places` is in the core, so this over-reports nothing today. It is declared in
`js/core_restrict.mjs`'s `APPROXIMATE_KEYWORDS` and pinned by a test, so the day
`places` leaves the core, the answer is known to be an over-approximation rather than
an exact one. Giving `Round` a field for it would change the AST's **shape**, which
`grammar/parser.planes` pins.

---

## What a future build has to decide

The gap is one keyword, and closing it is a choice, not a repair:

1. **Widen the core to 29 keywords.** `when` joins the port surface. Honest — it says
   what a second host actually needs — and it costs one construct of implementation.
   `core.json`'s `excluded_keywords.when` entry, and CORE_SUBSET.md's derivation, both
   need rewriting: the refutation they record is a refutation for one file.
2. **Rewrite `grammar/lexer.planes` to flat `if`.** Keeps the core at 28 and keeps the
   claim that `when` is never needed. Costs a rewrite of the lexer's hottest loop —
   nine nested `when`s in `step` and seven in `flush-pending` — and the result is
   almost certainly less readable than what it replaces.

The measurement does not choose. It says the price of each in exact terms: one keyword
of port surface, or sixteen dispatch sites of rewrite.
