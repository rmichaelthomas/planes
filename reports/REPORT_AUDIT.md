# Session Report — The Unearned Assertion Audit

Opens and closes P-Q20, P-Q21 (the class), P-Q22 (`--effects` claims a
static property from a runtime log), P-Q23 (the output layer was
untested). `BUILD_READBACK.md` did not exist in this checkout; its
superseding fix (item 2 below) was built from this prompt directly.

All four judgment calls from `REPORT_DERIVATION.md` and both from
`REPORT_VACUOUS.md` were carried unchanged and not revisited.

---

## §1 restated: why this happened

Every test in `test_rules.py` and `test_shapes.py` before this build calls
`check()`/`analyse()` and asserts on the returned objects directly —
white-box. Before this build, exactly **two** tests in the whole repository
invoked a CLI script as a subprocess and checked its actual output (both in
`test_rules.py`, both added by the P-Q19 build). The analysis core
(`shapes.py`'s widening, `rules.py`'s matching) is exercised thousands of
times over; the string that gets printed at the end of that work was
exercised almost never. §4.3 closes that gap directly; §4.1/§4.2 are the
guard that keeps it closed.

## The full sweep table

Every site examined, in the order `planes.py → shapes_cli.py → shapes.py →
modules.py → interp.py`. "Earned" means the claim reads exactly the data
it asserts, in the same call, from the same computation.

| # | Site | Verdict | What earns it / what didn't |
|---|---|---|---|
| 1 | `planes.py`: `"no such file: {path}"` | Earned | `os.path.exists(path)` just checked False, same branch |
| 2 | `planes.py`: `--effects` empty message | **Was unearned — fixed (item 1, P-Q22)** | Said "(none — this program touches nothing outside itself)" from `i.effects`, the one-run log; a program with `ask` in an untaken branch printed this while it was false |
| 3 | `planes.py`: `syntax error —` / `module error —` / `error —` | Earned | Each wraps an exception just caught in the same `except` |
| 4 | `planes.py`: `--why` output (`why_tree`, `origins`, `explain`) | Earned | `origins()` walks the whole reachable graph unconditionally — "every boundary crossing" is literally true; `why_tree` truncates at `max_depth` but signals it honestly with `"..."` in the printed output — the docstring says "Full transitive derivation," which overclaims, but a docstring is not user-facing output under §1's own definition (property 1: "the output makes a claim a reader acts on") |
| 5 | `shapes_cli.py`: `"no such file: {path}"` | Earned | Same pattern as #1 |
| 6 | `shapes_cli.py`: `"no .planes files found"` (`--index`) | Earned | `paths` is the glob result computed immediately above |
| 7 | `shapes_cli.py`: per-file `"{p}: syntax error —"` (`--index`) | Earned | Wraps the exception just caught |
| 8 | `shapes_cli.py`: `"--search needs a boundary..."` | Earned | `len(args) < 2` just checked |
| 9 | `shapes_cli.py`: `"nothing touches {boundary}"` (`--search`) | **Was unearned — fixed (sweep finding)** | Files that failed to parse were `continue`d out of `hits` with no signal at all (unlike `--index`, which reports the same failure to stderr); "nothing touches X" could be printed while a skipped file's real answer was never checked |
| 10 | `shapes_cli.py`: `"--diff needs two files"` | Earned | `len(args) < 3` just checked |
| 11 | `SurfaceDiff.render()`: `"no change to the effect surface"` | **Was unearned — fixed (sweep finding)** | `is_empty()` read `added`/`removed`, computed from `.effects` (top-level only); `new_boundaries` was already computed from `.declared`. A library whose new network call lives in an uncalled function showed `is_empty()==True` (renders "no change") while `new_boundaries==['network']` and `is_significant()==True` — the printed text and the exit code disagreed. See the dedicated section below. |
| 12 | `SurfaceDiff.render()`: `"NEW BOUNDARIES CROSSED"` / `"NEW DESTINATIONS"` / `"no longer touches"` | Earned (after #11's fix) | Now drawn from the same `.declared`-based comparison as `is_empty()` |
| 13 | `shapes_cli.py`: `derivation_stats` all-zero rendering | Examined, clean | Every `Effect(...)` construction site in `shapes.py` passes a real `StaticDeriv`, never `None` (checked all 6 sites) — the all-zero case is reachable only when `surface.declared` is genuinely empty, so "effects with a derivation: 0" is an honest report of an empty surface, not a silently-failed measurement |
| 14 | `shapes_cli.py`: `"no rules found in {file}"` | **Was unearned — fixed (item 3)** | `found` came from a second, independent parse of the same file, separate from the one that produced `surface`; reworded from "no rules in" to scope the claim to what this parse found |
| 15 | `shapes_cli.py`: `"{N} rule(s) checked"` | Earned | `found` is the exact object passed into `check_rules()` |
| 16 | `shapes_cli.py`: `"({N} named subjects resolved)"` | **Was unearned — fixed (item 2, P-Q20)** | Re-derived `named` from `found` and relied on `_resolve_subject` having raised earlier, in another module, if the count were wrong; now read back from `RuleResults.resolved_subjects` |
| 17 | `shapes_cli.py`: `"{summary}, no violations"` | Earned (given #16's fix) | Fires only when `results` is empty; every named-subject rule that matched nothing is guaranteed (by `check()`'s own vacuous-detection invariant, P-Q19) to add an entry to `results`, so empty `results` really does mean nothing to report |
| 18 | `rules.py`: `Violation.render()` (all four shapes) | Earned | Audited in the P-Q19 build; `origins` is read from `surface.origins_of(effect)` at construction time, same call |
| 19 | `shapes_cli.py`: exit codes 0/1/2 for `--rules` | Earned | `is_violation`/`vacuous` read directly off the `Violation` objects just returned |
| 20 | `shapes_cli.py`: `as_json()` fields (`pure`, `complete`, `kinds`, `boundaries`, ...) | Earned | Every field reads `surface` directly, same call |
| 21 | `shapes_cli.py`: bare surface print (`surface.render()`) | Earned | See #22–25 |
| 22 | `Surface.render()`: `"pure — this program touches nothing outside itself"` | **Earned — the contrast case** | See dedicated section below |
| 23 | `Surface.render()`: library note | Earned | `is_library()` reads `effects`/`functions`/`foreign` directly |
| 24 | `Surface.render()`: `"this surface is incomplete: a foreign function states no effects"` | Earned | `has_unknowns()` reads `self.declared` directly |
| 25 | `Surface.render()`: `"unresolved calls: ..."` | Earned | `self.unresolved`, populated in the same analysis pass |
| 26 | `shapes_cli.py --check`: `"module declarations match the effect surface"` | Earned | Fires only when `declared_but_unused()`/`used_but_undeclared()`, both computed from the same `surface`, are both empty |
| 27 | `shapes_cli.py --check`: per-item lines | Earned | Each printed item comes directly from the same two query results |
| 28 | `modules.py`: `ModuleError` (cycle, missing module, collision) | Earned | Each raised immediately from a condition just computed in the same function |
| 29 | `interp.py`: all `PlanesError` raise sites (~25, spot-checked in depth) | Earned | Every raise is adjacent to the exact condition just checked, in the same scope; `call_foreign`'s own comment already draws the earned/claimed distinction explicitly ("a declaration is a claim... the log records that the claim was acted on, not that it was verified") |
| 30 | `interp.py`: `explain()` / `render()` | Earned | Pure formatting of a derivation node already computed; no aggregate claim |

`host.py`, `lexer.py`, `parser.py` were not separately swept: `host.py` is named in §1 as already read and clean during the prompt's own scoping; `lexer.py`/`parser.py` are not in §3's enumerated file list and were treated as out of this build's boundary, consistent with how the prompt scoped the sweep.

## The `Surface.render()` contrast case

Both `planes.py`'s (former) `--effects` message and `Surface.render()`'s
`"pure"` message assert the identical fact in the identical words —
*"this program touches nothing outside itself"* — and one was unearned
while the other has always been earned:

- `Surface.render()`'s version fires from `self.is_pure()`, which is
  `not self.declared` — `self.declared` **is** the static effect surface,
  computed by walking every function and branch regardless of what ran.
  The words and the data are asking the same question.
- `planes.py`'s version fired from `not i.effects` — the interpreter's log
  of what one run actually did. The words claim a property of the program;
  the data is a property of the run. Different questions, same sentence.

This is the whole class in miniature: the defect was never the sentence.
It was which computation stood behind it.

## The `SurfaceDiff` finding, in full

Found during the sweep, not named in the prompt. Reproduced before fixing:

```python
before = analyse('to helper of n:\n  give n + 1\n')
after  = analyse('use http\nto helper of n:\n  give ask "https://tracker.example.com/collect"\n')
d = diff(before, after)
# is_empty():       True   (added/removed came from .effects — both empty, nothing ran)
# is_significant(): True   (new_boundaries came from .declared — a real new capability)
# render():         "no change to the effect surface"
```

`shapes_cli.py --diff` would have exited 1 (correct — `is_significant()`
drove the exit code) while printing "no change to the effect surface"
first — exactly the "library reported pure because nothing runs at load"
lie this project's own docstrings describe as the reason it exists,
reproduced inside its own diff tool, currently shipping, never caught
because no existing test diffs a library gaining a capability in a
function nothing calls. Fixed by computing `added`/`removed` from
`.declared` (matching `new_boundaries`/`dropped_boundaries`, which already
used it) instead of `.effects`. Verified against every existing `--diff`
test and both repository demo pairs (`demo/fdiff/v1→v2`,
`demo/v1→v2`) — byte-identical output and exit code before and after,
because both pairs happen to run everything at top level, where `.effects`
and `.declared` already agreed.

## The three prescribed fixes — before/after

**Item 1 — `planes.py --effects`:**
```
- "  (none — this program touches nothing outside itself)"
+ "  (nothing — this run performed no effects; run `shapes_cli.py <file>`
+   for what the program can do on any run)"
```

**Item 2 — `shapes_cli.py --rules` summary:**
```python
# before
named = [r for r in found if r.subject != "anything"]
if named:
    summary += f" ({len(named)} named {subj_word} resolved)"

# after
resolved = results.resolved_subjects   # read back from check()
if resolved:
    summary += f" ({len(resolved)} named {subj_word} resolved)"
```
`check()` now returns `RuleResults` (a `list` subclass — every existing
caller's `if not results` / iteration / `any(...)` / `len()` is
unaffected) carrying `resolved_subjects`, appended only after
`_resolve_subject` returns without raising.

**Item 3 — `shapes_cli.py --rules` / `--fingerprints`:**
```
- f"no rules in {os.path.basename(path)}"
+ f"no rules found in {os.path.basename(path)}"
```
Low-cost, as instructed — reworded rather than restructured the two-parse
architecture.

## The registry: iteration and false-positive count

Three scanner designs were tried, in order, because the first two each
failed one of the two things this registry has to do simultaneously —
catch every known site, and not drown in noise:

1. **Print-argument literals only** (`ast.walk` for `print(...)` calls,
   resolving only direct `Constant`/`JoinedStr` arguments). Missed item 2
   entirely: its claim text is built across two statements into a
   `summary` variable before `print(f"{summary}, no violations")` — a
   real false negative, caught by testing this design against the fix
   before trusting it.
2. **Whole-file literal scan** (every string/f-string literal in the file,
   regardless of whether it reaches `print`). Caught item 2 by accident
   (its fragments appear as bare literals) but surfaced roughly five
   categories of false positive that are not claims at all: the `pure`
   and `complete` JSON schema field tokens in `as_json()`, the
   `unresolved_calls` field name (a pure substring collision — "resolved"
   is a substring of "unresolved"), and both module docstrings (narrative
   help text, not a data-derived claim about a specific run).
3. **Final design** (shipped, in `test_assertions.py`): resolves the
   literal argument to every `print()` call, following simple
   same-function variable assignment (`x = f"..."`, `x += f"..."`) so a
   claim built across statements is still visible at its print site,
   without pulling in anything that never reaches `print` at all.

**False-positive count with the final design: 0.** All 9 distinct strings
it flags across `planes.py`/`shapes_cli.py` are registered in
`CLAIM_SITES`, and every one of them is a genuine claim-bearing print site
— none are schema keys, docstrings, or AST-walk artifacts.
`test_every_claim_verb_string_is_registered` asserts the found set equals
`set(CLAIM_SITES)` exactly (not just a subset), so a registry entry that
stops being reachable would also fail loudly.

## CLI test count

**Before: 2** (`test_cli_exit_code_2_for_a_vacuous_rule`,
`test_cli_exit_code_0_for_anything_with_no_match`, both in `test_rules.py`,
both from the P-Q19 build). **After: 17** — those 2 unchanged, plus 15
subprocess-level invocations in the new `test_assertions.py` (14 dedicated
CLI-coverage tests in §4.3, plus one more inside a §4.2 behavioral test
that also runs the CLI as a subprocess).

## Exit-code table: confirmed identical

Re-ran `REPORT_VACUOUS.md`'s exact procedure — `--rules` over all 26
`.planes` files in the repository, before (via `git stash` to
`7110903`) and after this build's changes. `diff` between the two tables:
empty. Separately, `--diff` was checked over both repository demo pairs
(`demo/fdiff/v1→v2`, `demo/v1→v2`, the only two existing `--diff`
fixtures) before/after the `SurfaceDiff` fix: identical exit codes,
byte-identical output.

## Existing tests changed

**None.** Every pre-existing test in `test_shapes.py`, `test_rules.py`,
`test_planes.py`, `test_coverage.py`, `test_foreign.py`, `test_host.py`,
`test_names.py`, `test_numbers.py` passes unmodified. `test_assertions.py`
is the only new file, per the build prompt's instruction.

## Decisions this build made that the prompt did not specify

1. **The sweep's own findings (the `SurfaceDiff` inconsistency, item 11;
   the `--search` silent-skip, item 9) were fixed in this same build,
   not merely reported.** The prompt's three named items were explicit
   fixes; the sweep's job (§3) was originally read as "report every site
   examined." The newly-added standing term — "a gap named in a report is
   fixed in the build that names it, or it is not named" — resolves this
   in favor of fixing both. **Recommend: lock**, and read it as retroactively
   governing every future sweep this project runs, not just this one.
2. **The registry's variable-resolution scanner is a bounded heuristic,
   not a real data-flow analysis**, deliberately: composite statements
   (`if`/`for`/`while`/`try`/`with`) recurse with a **copy** of the
   tracked bindings, so a mutation inside a branch never leaks to a
   statement after the branch, even when that leak would have been
   "more correct" for a specific case (it would have been, for fully
   resolving item 2's "resolved" fragment — see below). Chosen because
   the safe failure mode for a registry is under-resolving to `"{}"`
   (still forces registration, since the surrounding literal text still
   carries a claim-verb) rather than mis-resolving a value that never
   actually holds at that point. **Recommend: lock.**
3. **Docstrings are excluded from the claim registry even though the
   module-level ones are genuinely printed** (`print(__doc__.strip())`
   on bare invocation). A whole-file scan would catch them but also
   catches JSON schema keys as an unavoidable side effect of the same
   over-broad net; the final scanner's print-argument resolution
   naturally excludes docstrings too, since `__doc__.strip()` is a method
   call, not a literal, and isn't resolved by the same-function tracker.
   This is examined and accepted rather than fixed: a module docstring is
   narrative usage text, not a claim about a specific run's data, and
   `shapes_cli.py`'s docstring already states its own exit-code contract
   in prose — verified by inspection here (§3.3 of `shapes_cli.py`'s
   docstring vs. the actual `--rules` exit logic), not by an automated
   check. **Flagging, not locking**: if the exit-code contract changes
   again, the docstring's prose claim about it needs the same manual
   verification this session gave it once.
4. **`planes.py`'s `"effect surface:"` header text was left unchanged**,
   scoped tightly to the one line the prompt quoted. It is arguably the
   same category of looseness (a runtime log labeled with the project's
   static-analysis noun), but changing it would touch a string the
   prompt didn't cite and wasn't required to make item 1's fix honest —
   the fixed line underneath it no longer claims anything about the
   program, which is what mattered. **Flagging for the next session's
   judgment, not fixing here.**

## Test counts

| | before this build (`7110903`) | after |
|---|---|---|
| `test_shapes.py` | 72/72 | 72/72 (unchanged) |
| `test_rules.py` | 63/63 | 63/63 (unchanged) |
| `test_planes.py` (incl. session gate) | 50/50 | 50/50 (unchanged) |
| `test_coverage.py` | 7/7 | 7/7 (unchanged) |
| `test_foreign.py` | 37/37 | 37/37 (unchanged) |
| `test_host.py` | 14/14 | 14/14 (unchanged) |
| `test_names.py` | 15/15 | 15/15 (unchanged) |
| `test_numbers.py` | 31/31 | 31/31 (unchanged) |
| `test_assertions.py` (new) | — | 20/20 |
| **total** | **289** | **309** |

`rules.py`'s import block, reconfirmed by direct `ast` assertion after
adding `RuleResults`: `{'hashlib'}`. Unchanged.
