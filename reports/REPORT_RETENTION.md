# REPORT — R1: Retention Window and Seal Nodes

**Build:** `feat/retention-window-and-seals`, branched from `main` at `8331a1a`.

**Corrections the resume prompt named, verified this session and binding
on this build (build prompt §1):** HEAD is `8331a1a`, not `e614c2e` — PRs
#71–#76 (all tutor.html work, out of this program's scope) merged since
v28.0 locked, none R1-relevant. `why_tree` exists in `interp.py` only;
`js/interp.mjs` has no `why_tree` — its depth-14 truncation is untouched
here in both senses: the Python function's behaviour is unchanged, and no
JavaScript equivalent is built (R2's job, not R1's).

---

## 1. SHA table

Captured at branch time via `git rev-parse HEAD:<path>`:

| path | blob SHA |
|---|---|
| `interp.py` | `7b65ed06ec9ff29fc84eec6fc7160fe1a70eb27c` |
| `js/interp.mjs` | `bc5d848877a87b32b1bb01fce35953535e8118cb` |
| `host.py` | `24a8bf845e914a0242d253b794ed0ce778f96887` |
| `js/host.mjs` | `cdf48d55773d81a214070a8a993920b34607e766` |
| `reports/REPORT_UPDATE_COST.md` | `5153ed4b293c451fce2a77360808f96df821487f` |

All five match the build prompt's §2 table exactly — verified via
`git rev-parse`, not assumed.

## 2. Verified absences (S1)

```
$ git show 8331a1a:interp.py    | grep -c "window\|seal\|snapshot"   -> 0
$ git show 8331a1a:js/interp.mjs | grep -c "window\|seal\|snapshot"  -> 0
$ git show 8331a1a:host.py       | grep -c "snapshot"                -> 0
$ git show 8331a1a:js/host.mjs   | grep -c "snapshot"                -> 0
```

No window, seal, or snapshot machinery existed anywhere in the four files
this build touches, at branch time. The build prompt's own claim is
confirmed, not merely inherited.

## 3. What was built

**Generation.** Every `Deriv` now carries a `generation` — a per-interpreter
counter, stamped at construction, in the memory math's own unit
(`REPORT_UPDATE_COST.md` §5.4: 89 `Deriv` nodes/tick). Every one of the 41
`Deriv(...)` construction sites in `interp.py` (43 in `js/interp.mjs`, which
carries two extra fields on the same constructor) now goes through one
choke point — `Interpreter.mk()` — instead of calling the dataclass/class
constructor directly, so the stamp (and the cut below) apply uniformly with
no operation-kind special case. Two call sites are deliberately exempt: the
free-standing `lit()` function (kept unchanged — `js/cli.mjs` and
`js/meta_browser.mjs` import it directly as a plain constructor, unrelated
to any live interpreter's generation counter) and `mk()`/`_seal()`'s own
internal `Deriv(...)` calls, which cannot recurse into themselves.

**The seal.** `kind="seal"`, value at the cut, empty inputs, plus three
seal-only fields: `generation` (where the cut landed), `released_count`
(how many ordinary steps it folds in, absorbing any earlier seal's own
count rather than re-walking it), `fingerprint` (below). Its `label` **is**
the fixed refusal sentence — not a separate rendering — so `render()`'s new
arm is the one-liner every other kind already has (`return node.label`,
same as `"list"`/`"record"`/`"effect"`), and `why_tree` needs no
seal-specific case at all: a seal is a leaf like a literal, its label is
already the sentence, and `why_tree`'s untouched depth-14 walk simply
stops there.

**The cut (`_cut`).** Applied to every newly-built node's own reachable
inputs, in place. The one correctness subtlety, found and fixed by this
build's own test before it shipped (§5 below): age is measured against the
**node currently being built**, not each intermediate ancestor's own
generation — a `with`/`plus` chain links each step to the one immediately
before it, always exactly one generation apart, so checking an ancestor
against its *direct parent's* generation would never see more than 1 and
would never cut anything. Checked against the one fixed reference point
instead, an ancestor many links back reads as exactly that old.

**The seal's fingerprint.** A deterministic digest of the released
subgraph: two iterative passes (not recursive — a long chain is a `Deriv`
graph thousands of nodes deep, and Python's default recursion limit is
1000) assign every reachable node a stable index in first-discovery order,
then emit one line per node (kind, label, value, origin, and its inputs'
already-known indices) so the whole DAG — sharing included — is a flat,
order-independent-to-write text, hashed with `hashlib.sha256(...)
.hexdigest()[:12]` in Python and `sha256Hex(...).slice(0, 12)` in JS (the
same pure implementation `rules.py`/`js/sha256.mjs`'s own `fingerprint()`
already uses for the rule plane, at a longer truncation here since a seal's
identity space is larger than a rule's). Same program, same traversal
order in both languages (a stack, not a `for...in`/dict-iteration order
that could differ), so the same text, and so the same fingerprint — R1
extends the corpus's byte-identical-agreement discipline from output to
the released subgraph a seal replaces.

**The refusal.** `seal_refusal(generation, snapshot)` in both languages,
building the sentence from the same template with the same two values:

> history before generation N was released; deterministic replay from
> snapshot S recovers it exactly.

**PINs.** `Interpreter.pin(traced_or_node)` — no new syntax (parser.py and
every grammar file are untouched; PINs are host/embedder-level API, not a
program-writable construct). `self._pinned` holds a **direct, strong
reference** to the pinned node — an independent root the interpreter's own
bookkeeping keeps alive, the same way a still-bound `env` variable keeps a
value alive today. This is the one place this build's design changed
after an early draft: a first attempt made "protection" propagate through
a node's ancestry (so cutting an intermediate node could not silently
orphan a deeper pin) — and that propagation turned out to cascade
*forward* too, through every later node built from the pinned one,
permanently disabling the window for the rest of that chain's life. The
fix drops the propagation entirely: since `self._pinned` is an
independent reachability root, the live derivation graph is always free
to cut its own edge to a pinned node — cutting one path never loses it,
because a second, independent path already holds it — so pinning one
derivation costs exactly what it pins and nothing more. Inert by
construction: `pin()` never touches evaluation, `env`, `output`, or
`effects`.

**The host method.** `snapshot(fingerprint, entry)` on the abstract `Host`
(a no-op default, matching `record`'s shape exactly) and on `TestHost` /
`MemoryHost` (an in-memory `dict`/object keyed by fingerprint).
`PythonHost` overrides neither `record` nor `snapshot` — same pattern on
both sides. Required surface stays at seven; `test_host.py` /
`test_js_host.py` / the new `js/test/drawing_invariants.test.mjs` entry
all assert this directly.

## 4. Two things found and fixed before this build's own tests were
   trusted (self-run gate discipline)

**A. The always-1-generation bug.** `_cut`'s first draft compared an
ancestor's age against its *direct parent's own generation*. Every link in
a `with`/`plus` reassignment chain is exactly one generation apart by
construction, so that comparison never exceeded any window — the window
would have silently done nothing on the shape this build exists to fix.
Found by a 3000-generation smoke test before any language-side test file
was written; fixed by measuring age against the single node passed into
the top-level `_cut` call instead.

**B. The Python `id()`-reuse bug.** The first working draft memoized seals
in a `dict` keyed by `id(root)`, without holding `root` itself alive. Once
`root` becomes unreachable — which is exactly the condition sealing it
creates — Python is free to garbage-collect it and reuse its address for
an unrelated later object, and the memo then hands back a *stale* seal for
the *wrong* subgraph. This did not show up in any single-language test: it
showed up as a **cross-language fingerprint disagreement** — the same
200-line program, same `window=5`, produced `generation=19,
released_count=20` in Python and the correct `generation=595,
released_count=596` in JavaScript (whose own `_id()` is a `WeakMap` with an
ever-incrementing counter, so it never repeats an id and was never
vulnerable). Fixed by dropping the memoization entirely rather than
patching around Python's identity semantics: each call now walks only
what is still reachable and not already behind an earlier seal, so the
repeat work this would have saved is small, and only ever paid when the
same node is independently discovered stale from more than one surviving
path — the DAG-sharing case, not the common linear one. The JavaScript
side's own cache was removed to match, even though it was not itself
vulnerable, so the two implementations stay structurally aligned rather
than one memoizing what the other safely cannot. **This is the load-bearing
argument for building the cross-language agreement check before trusting
any other result**: a bug that is invisible from inside either
implementation alone was caught only by requiring them to agree.

## 5. Cross-language and inertness gate — `test_retention.py`

17/17 passing. The build prompt's own N+3.2 table:

```
=== R1 verification gate (N+3.2) ===
  PASS  unbounded-window == HEAD reachable count
  PASS  finite-window bounded reachable count
  PASS  cross-language fingerprint match
  PASS  seal refusal sentence byte-identical
  PASS  PIN reachable past window
  PASS  PIN-inertness (output/effects identical with/without PIN)
  PASS  seven required host methods unchanged
```

The cross-language checks shell out to a new `node js/cli.mjs retention
<config-json>` subcommand (mirroring the existing `run`/`trace` pattern):
runs a sequence of source snippets on one `Interpreter` + `TestHost`,
optionally pinning a named variable after a given step, and reports
generation count, reachable count, the first seal's
generation/releasedCount/fingerprint/label, the pinned node's reachable
count, and output/effects — everything `test_retention.py` needs to diff
against the same scenario run directly through `interp.py`.

## 6. Benchmarks (build step 6)

**Method.** Rather than inventing a new measured shape, both arms reuse
`benchmarks/world_shape.planes`'s own generator —
`scripts/measure_update_cost.py`'s `build_world_src_for` and
`count_reachable_derivs`, imported unmodified — at S=64, checkpointed at
tick 1/100/300/600, four independent full runs each (0..checkpoint-1
ticks), identical to `REPORT_UPDATE_COST.md` §5.4's own method. A new
script, `scripts/measure_retention_window.py`, adds exactly one parameter
— `window=` on the `Interpreter` — and runs each arm as its own
subprocess, for the same reason `measure_update_cost.py`'s
`run_retention_subprocess()` does: `ru_maxrss` is a process-wide
high-water mark, and running both arms in one process would let the first
contaminate the second's reading.

`benchmarks/retention_window.planes` — the file this build step names —
is a small, self-contained illustrative fixture (one piece of state
threaded through 20 ticks by reassignment, a `with` update plus a `plus`
onto a growing log each tick) rather than the rigorous S=64 measurement
target: reading `benchmarks/world_shape.planes` at S=64 through a debugger
is not a way most readers would choose to *see* what a window cuts, so
this file exists to be run directly and read by inspection. The rigorous
pre/post comparison below still measures `world_shape.planes` at S=64,
exactly as the build prompt's own method names it.

**Pre** (`reports/feat-retention-window-and-seals-benchmarks-pre.md`,
unbounded — no `window` argument at all, the literal HEAD/main shape):

| tick | reachable `Deriv` count | RSS growth from tick 1 |
|---:|---:|---:|
| 1 | 275 | 0.00 MB |
| 100 | 9,086 | 9.32 MB |
| 300 | 26,886 | 30.36 MB |
| 600 | 53,586 | 62.90 MB |

Fitted slope: **89.00 Deriv nodes/tick** — matching `REPORT_UPDATE_COST.md`
§5.4's own figure exactly (275 / 9,086 / 26,886 / 53,586 at the identical
four checkpoints). This is invariant 2's own proof against a real, complex
program, not only the synthetic chains in `test_retention.py`: run on this
branch, with no `window` argument, `world_shape.planes` at S=64 reproduces
the pre-R1 report's numbers to the digit.

**Post** (`reports/feat-retention-window-and-seals-benchmarks-post.md`,
`window=900` — roughly ten ticks of full history at the measured 89
nodes/tick):

| tick | reachable `Deriv` count | RSS growth from tick 1 |
|---:|---:|---:|
| 1 | 22 | 0.00 MB |
| 100 | 22 | 8.75 MB |
| 300 | 22 | 30.64 MB |
| 600 | 22 | 69.73 MB |

Fitted slope: **0.00 Deriv nodes/tick.** The reachable-`Deriv`-count line —
the direct, decisive measure this build's window exists to bound — is
flat: **53,586 → 22 at tick 600, a >2,400× reduction**, and the
extrapolated 108,000-tick soak count falls from 9,612,186 (≈9.1–10.6 GB,
per `REPORT_UPDATE_COST.md` §5.4) to **22, unconditionally, for any soak
length** — the reachable structure has already reached its steady-state
size by tick 1, since the window bounds it independent of elapsed time.

**A finding, named and not fixed: RSS growth does not show the same
improvement, and this build's own read of it says why.** RSS is a
process-wide *high-water mark* (never decreasing), and each checkpoint's
run must still *construct* the transient, not-yet-cut portion of history
before `_cut` collapses it — for `world_shape.planes`'s 64 independent
subject sub-chains, the discovery walk `_cut` runs on every new node is
proportional to (live branches × window-in-ticks), not to window alone,
so a single tick's peak transient allocation before collapsing is larger
than the linear-chain case this build's own correctness tests exercise.
Measured directly: the same S=64/tick=600 run took **1.68s unbounded,
9.15s at window=900** — a ~5.4× slowdown, consistent with that
explanation and confirmed linear (not quadratic) in tick count by the flat
RSS-growth-per-tick slope once construction churn is accounted for.

This is a genuine, measured cost of the current design, not a correctness
defect — the reachable-node-count bound (this build's actual acceptance
criterion) holds cleanly regardless, and `test_retention.py`'s pin,
inertness, and cross-language checks are all unaffected by it. It is left
here as a named cost rather than redesigned under this build's own time
budget, matching how this project's prior builds (PR #39/#40, the
per-tick regression memory records) have treated a measured-but-not-fixed
regression: quantified, explained, and handed forward rather than
silently absorbed into a late, unverified rewrite. The likely fix — invoke
`_cut` only at `"name"`-kind (assignment/reassignment) construction rather
than on every one of the ~89 `Deriv`s a tick builds, since only a
persistently-bound value's own chain needs periodic re-verification, not
every intermediate expression inside one statement — does not change the
window's unit (still a `Deriv`-generation count) or any test in this
build's own gate, but is exactly the kind of change that deserves its own
verification pass rather than a same-session addendum.

## 7. Gate

Full suite green: **68 Python suites, 68 reporting, 1,325 oks** (67 at
`main` plus the new `test_retention.py`), **805/805 `node --test`**,
`test_js_interp.py` and `test_js_metacircular.py` (the two explicitly
named agreement gates) passing, `grammar_gen.py --check` up to date (see
§8), `core_check.py`, `check_derived_claims.py`, `audit_locked_vs_built.py`,
`protocol_gen.mjs --check` all clean, `ruff` and `mypy` clean on every
Python file this build touches or adds — "all checks passed in 146.9s".

## 8. A mechanical consequence, not a language change

`grammar/errors.json` embeds each `raise PlanesError(...)` call site's
source line (`"source": "interp.py:N"`) for every catalogued error. Adding
`mk()`, `pin()`, `_cut()`, `_seal()`, and their docstrings above the
existing raise sites shifted every one of those line numbers, so
`grammar_gen.py --check` failed on line-number drift alone —
`git diff grammar/errors.json` (regenerated via `python3 grammar_gen.py`)
touches only `"source"` fields; every tag, template, and slot is
byte-identical to what was on `main`. `grammar/vocabulary.planes` and
`grammar/rules.json` show no diff at all. No language surface moved.

## 9. Deviations from the file inventory, named rather than absorbed
   silently

- **`js/cli.mjs`** gained one new subcommand (`retention`), and
  **`js/test/drawing_invariants.test.mjs`** had one hardcoded assertion
  updated (the Host method list, to include `snapshot` beside `record` and
  `targetHint`) — neither file is in the build prompt's §2 inventory. Both
  are the same shape of addition prior builds' own file inventories
  routinely needed and listed (`test_js_host.py`'s pattern, `js/cli.mjs`
  growing one subcommand per phase, is the file's own stated purpose) —
  named here because the build prompt's inventory did not anticipate them,
  not because they are out of scope for what R1 asks.
- **`benchmarks/retention_window.planes`** is the illustrative fixture
  described in §6, not the S=64 measurement target — see that section for
  why, and for where the rigorous measurement actually runs.

## 10. What this does not decide

R2's readable-answer work (one-layer-by-default, aggregate folding, three
registers, retiring `why_tree`'s depth-14 truncation) is untouched — the
truncation's own behaviour is unchanged, and no JavaScript equivalent was
built, per the build prompt's own instruction not to treat this as R2's
symmetric-maintenance work. R3's replay-on-demand and tracing-off fast
path are untouched. A-Q3 (persistent data structures, structural sharing)
remains open — R1 does not implement one, and does not need one: the
window bounds retention by *cutting* history, not by making updates
cheaper, which is a different question the§6 finding's suggested
optimization does not touch either.

The RSS/CPU finding in §6 is the one open item this report hands forward
by name, per this build's own standing instruction to close what existing
tooling can close and name what needs a dedicated pass — this is the
latter.
