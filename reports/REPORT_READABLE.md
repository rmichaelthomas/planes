# REPORT — R2: The Readable Answer

**Build:** `feat/readable-answer-and-js-whytree`, branched from `main` at `699acc1`.

**Preconditions the build prompt named, verified this session and binding
on this build (build prompt §1, §449):** HEAD is `699acc1`. `why_tree`
exists in `interp.py` only (line 1977 at branch time); `js/interp.mjs` has
`explain`, `render`, `origins`, `approximationsIn` and no deep-walk function
at all — confirmed by direct search, not assumed. This build is therefore
two unlike tasks, as the build prompt states: a Python *edit* (`why_tree`'s
existing depth-14 truncation, replaced) and a JavaScript *first build*
(`whyTree`, built from nothing).

---

## 1. SHA table

Captured via `git rev-parse HEAD:<path>` at branch time:

| path | blob SHA |
|---|---|
| `interp.py` | `65a64230ad7a7abaf783159f3eb08a94e4d069f0` |
| `js/interp.mjs` | `7cd827b2f766d2ab46c925abcd90781c2ce76923` |
| `js/cli.mjs` | `385a24f03ac44eb40e0cc5a64aa27673ac1c657d` |

`interp.py` and `js/interp.mjs` match the build prompt's own §2 table
exactly (`65a6423`, `7cd827b`) — verified via `git rev-parse`, not assumed.
`js/cli.mjs`'s SHA was not pinned by the build prompt (it says "read before
editing"); recorded here for completeness.

## 2. Verified absence (S1)

```
$ grep -n "why_tree" interp.py     -> line 1977 (why_tree), plus one docstring mention
$ grep -n "whyTree\|why_tree" js/interp.mjs js/cli.mjs   -> no matches
```

Confirmed at HEAD, this session, before any edit: the deep walk exists in
exactly one language. Treating the JavaScript side as a first build, not an
edit, is the load-bearing consequence (§1, §449) — and it shaped the whole
build: every helper below was written once, in Python, tested, then ported
line-for-line to `js/interp.mjs`, never the reverse.

## 3. What was built

**One-layer default (§3).** Unchanged, and confirmed rather than rebuilt:
`explain()` was already the `why` statement's only output, and it was
already one layer. The deep walk (`why_tree` / `why_machine`) is a
*separate* function, reached only by an explicit second call — that
separation *is* "the deep walk is reached explicitly," so no code change
was needed here, only a test proving the property holds
(`test_explain_stays_a_single_line_no_matter_how_deep_the_chain`,
`test_the_deep_walk_is_a_separate_explicit_call`).

**Labeled aggregate folding (§4, §451).** `_why_find_run` (Python) /
`whyFindRun` (JS) detects the maximal run of consecutive, identical-in-shape
hops starting at a `name` node: two hops are "identical in shape" when
their kind/label structure matches at every position with values erased
(`_why_hop_shape` / `whyHopShape`), stopping the comparison — without
descending into it — at the next same-label `name` node or a seal
(`_why_next_stop` / `whyNextStop`). A run shorter than `_WHY_MIN_FOLD` (8)
renders unfolded — high enough that `test_values.py`'s existing 3-step
accumulation test (`test_why_on_the_accumulated_total_shows_each_addition`,
asserting `tree.count("+ =") == 3`) keeps passing unedited, since folding
earns its keep only once a chain runs well past what a single screen
already shows plainly. At or past the threshold, the run folds into one
`{"type": "aggregate", "count": N, ...}` node — structurally distinct from
`{"type": "step", ...}` in the machine register, and rendered as `"<label>
advanced N more times (... identical in shape to the one above)"` in the
prompt register: a format with no `=` in it, so it can never be mistaken
for a single derivation line (F1).

**The seal-boundary rule (§5, §452 — R1 composition).** `_why_next_stop`
stops at `kind == "seal"` exactly as it stops at a same-label `name` node,
so a fold never crosses a seal: the aggregate's `count` is exactly the
number of within-window hops confirmed, and the seal that follows renders
as `{"type": "seal", "label": <the fixed refusal sentence>, ...}` — a true
leaf in the machine register (no `children` key), and, in the prompt
register, the identical text `why_tree` already rendered for a seal before
this build (`render()`'s `"seal"` arm — `return node.label` — is untouched;
R1's own design already made a seal a leaf `why_tree` needed no special
case for). Confirmed, not rebuilt, per the build prompt's own precondition.

**Three registers, one traversal (§6, §453).** `_why_build` (Python) /
`whyBuild` (JS) is the one walk every register renders from — it returns
`{"root": <node>, "because": because}`, where a node is one of `step`,
`aggregate`, `seal`, `repeat` (R1-era DAG dedup, kept), or `frontier` (§7,
below). `why_tree`/`whyTree` formats that tree as indented text (the prompt
register, unchanged return shape from HEAD); `why_machine`/`whyMachine`
returns the tree itself (the machine register); the card register is
`explain()`, unchanged, which starts from the identical `traced.node` the
walk's root does. `test_card_prompt_and_machine_describe_the_same_root_node`
checks this against ground truth directly (`traced.node.label`/`fmt(value)`),
not just registers against each other, so three registers that all drifted
the same wrong way together would still fail it.

**Truncation retired (§7, §455).** The `if depth > max_depth:
lines.append("...")` branch is gone. Two honest replacements: within a
fold, the aggregate (above); past the requested depth with no fold
detected, a `"frontier"` node — the node's own line, rendered normally,
followed by `"(more derivation below this depth — call again with a larger
depth to expand)"` when it still has unexplored inputs. Nothing here
depends on `max_depth`'s *default* changing (it hasn't — still 14, matching
HEAD, so `test_retention.py`'s own seal-reaching call sites are unaffected)
— what changed is only what happens *at* the boundary.

**The JavaScript side (§8, §449).** `whyTree`/`whyMachine`/the four
`why*` helpers in `js/interp.mjs` are a first build, written to interp.py's
exact algorithm — same budget constant, same digest scheme, same iterative
traversal shape — and held to byte-identical output via a new `js/cli.mjs`
`whytree`/`whytree-corpus` pair (mirroring the `retention`/`trace`
subcommands' own patterns) that `test_why_readable.py` shells out to.

## 4. Two things found and fixed before this build's own tests were
   trusted (self-run gate discipline)

Both were invisible on synthetic chain fixtures and found only by running
the new code against `benchmarks/world_shape.planes` (R1's own S=64
fixture) and `probe/parser/cursor_scales.planes` — real, structurally wider
and deeper programs already in the corpus — per this project's standing
discipline of not trusting a result the gate has not actually exercised.
Full detail, including the exact numbers, is in
`reports/feat-readable-answer-benchmarks-post.md`.

**A. Shape comparison, not just shape construction, needs a cost bound.**
The first working draft returned each hop's shape as a nested structure and
compared two shapes structurally. Building one shape was bounded by a
search budget; comparing two was not — a language's own structural
equality recurses into every shared level, and `_why_find_run`'s loop
performs that comparison once per hop. `world_shape.planes`'s
record-heavy, wide hops made this run for minutes. Fixed by hashing each
shape to a fixed-length SHA-256 digest — the same technique R1's own seal
fingerprint (`_seal`) already established — so comparison is a fixed-length
string check regardless of subtree size.

**B. A search needs to be bounded by memory, not by a helper's own
recursion depth.** `cursor_scales.planes` (200 calls threading a record
through `for each`, each field access one more indirection) put the path
to a matching name several hundred native stack frames deep — independent
of the node-count budget, which was never exceeded. Fixed by converting
`_why_next_stop` and `_why_hop_shape` to iterative, explicit-stack
traversal with `("enter"/"exit")` sentinel frames — the identical pattern
R1's own `_cut`/`_seal` already use, for the identical reason, applied here
rather than reinvented.

Both fixes are exercised by `test_why_readable.py`'s own scenarios (a
`fact of 20` recursive-argument-sharing case for A-adjacent DAG sharing,
and the `world_shape.planes`/`cursor_scales.planes` corpus-wide
cross-language check for both), so a regression on either axis fails the
gate, not just a benchmark's own numbers.

## 5. Verification gate — `test_why_readable.py`

13/13 passing. The build prompt's own N+3.2 table:

```
=== R2 verification gate (N+3.2) ===
  PASS  one-layer default (§3)
  PASS  aggregate labeled and distinguishable from a step (§4/F1)
  PASS  aggregate count == within-window steps (§5a/F2)
  PASS  seal is a named leaf, nothing past it present (§5b)
  PASS  three registers describe one source (§6/F3)
  PASS  zero bare "..." across the corpus (§7/F6)
  PASS  cross-language deep-walk byte-identity (§8/invariant 1)
```

The cross-language checks shell out to two new `js/cli.mjs` subcommands
(mirroring the existing `retention`/`trace` pattern): `whytree
<config-json>` for synthetic fold/seal scenarios, and `whytree-corpus
<file>` for every traced value in a whole corpus program — diffed against
`interp.py`'s `why_tree`/`why_machine`/`explain` run on the identical
scenario or file. `explain()` (the card register) is unchanged by this
build and carries a pre-existing, out-of-scope limitation: its
`approximations_in` walk is plain Python recursion and can hit Python's own
default recursion limit on an unwindowed chain past roughly 450 steps —
present on HEAD, reproduced there directly, nothing this build touches.
`_py_whytree_corpus` marks a card that hits it with a sentinel and excludes
only that one field from that one entry's cross-language comparison;
`prompt`/`machine` (this build's own surfaces, now iterative) are compared
unconditionally and never need this exemption.

## 6. Regression check

`test_retention.py`: still 17/17, all seven N+3.2 rows PASS — R1's own
surfaces (window, seal, generation, PIN, snapshot) are untouched; this
build reads the graph R1 produces and does not alter cutting or sealing.
Every existing test that calls `why_tree` directly
(`test_numbers.py`, `test_with_plus.py`, `test_text.py`, `test_values.py`,
`test_planes.py`, `test_foreign.py`, `planes.py`) passes unedited — none of
their scenarios are deep or repetitive enough to intersect a fold or the
frontier marker, so their asserted substrings are byte-for-byte what they
were on HEAD.

## 7. Gate

Full suite green: **69 Python suites, 69 reporting, 1,338 oks** (68 suites /
1,325 oks at `main`, plus the new `test_why_readable.py`'s 13),
**805/805 `node --test`** (unchanged from `main` — no JS regressions),
`grammar_gen.py --check` up to date (raise-site line numbers unshifted —
every addition in this build lands after the last raise site in the file),
`protocol_gen.mjs --check`, `core_check.py`, `audit_locked_vs_built.py`,
`check_derived_claims.py` all clean, `ruff` and `mypy` clean on every file
this build touches or adds — "all checks passed in 200.9s".

## 8. Benchmarks (§N+3.4, conditional — applied)

The deep walk is a rendering path, and folding changes its cost profile
materially (O(1) → O(N) unwindowed; flat under R1's own window
recommendation), so a before/after was captured rather than skipped:
`reports/feat-readable-answer-benchmarks-pre.md` /
`-post.md`. Summary: HEAD's depth-14 truncation costs ~0.01 ms regardless
of chain length; this build's folding costs ~44 ms at a synthetic 10,000-step
unwindowed chain (a length no interactive `why` is likely to reach) and
~1.3 ms at any length once R1's own recommended retention window is set,
since a seal bounds the walk the same way it already bounds reachable
`Deriv` count. A named, not-fixed limit: `_WHY_SEARCH_BUDGET` (4,000
operations, shared per fold-detection call) can cap an unwindowed fold
before its true end on chains whose *individual* hops are unusually large,
producing a correct-but-partial fold rather than one line covering the
whole chain — always exact in what it confirms (F2 holds), never wrong,
matching this project's own convention (REPORT_RETENTION.md §6) of naming a
measured, not-redesigned cost rather than absorbing it silently.

## 9. Deviations from the file inventory, named rather than absorbed
   silently

- **`test_why_readable.py`** and **`reports/REPORT_READABLE.md`** are the
  build prompt's own invented names, used as given.
- **`js/cli.mjs`** gained two subcommands (`whytree`, `whytree-corpus`),
  matching the build prompt's own instruction ("mirroring the existing
  retention pattern") and R1's own precedent (`REPORT_RETENTION.md` §9:
  `js/cli.mjs` grows one subcommand per phase, by the file's own stated
  purpose).

## 10. What this does not decide

The machine-export register's provenance bound is unset, per the build
prompt's own explicit instruction (§1, out of scope, v29.0 §454): this
build renders the derivation the product already exposes and invents no
restriction policy over it — **flagged here for the architect to schedule**
(F5's own prevention). R3's replay-on-demand and tracing-off fast path are
untouched. A-Q3 (persistent data structures, structural sharing) remains
open. The `_cut` RSS/CPU optimization R1 §6 named is untouched — a
different track, not this one. `explain()`/`approximations_in`'s
pre-existing recursion-depth ceiling (§5 above) is named, not fixed — it
predates this build, is not part of what R2 was asked to change, and this
build's own new surfaces (`why_tree`/`why_machine`) do not share it (both
are now iterative).
