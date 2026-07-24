# The Annotation Plane and the Canonical Renderer — Session Report

**Date:** July 23, 2026
**Session type:** Implementation. Tier 0: the third plane (`because` / `note:`), and the canonical renderer the corpus has referenced since planes v2.0 §33 but never built.
**Mandate:** Phase zero tooling (I-Q1, I-Q2), the annotation plane with structural inertness, the inertness test as the guarantee, and `render.py` with the generated rule marker (unbound v2.0 §31).
**Result:** Built. 362/362 tests passing (333 prior + 29 new: 17 in `test_annotation.py`, 12 in `test_render.py`). `annotated.planes` runs clean, round-trips, and shows the marker. Verification gate (`verify_annotation.py`) all-PASS. One real design correction made mid-build, reported in full below — not papered over.

---

## 1. Phase Zero — Tooling Baseline (I-Q1, I-Q2)

No packaging config existed. Added `pyproject.toml`, a local `.venv/` (Homebrew's
Python refuses unmanaged installs — PEP 668 — so `ruff`/`mypy`/`coverage` live in
a project-local virtualenv, gitignored).

**Ruff, before any fix:** 269 errors, 68 auto-fixable.
**Ruff, after `--fix` (import sorting/splitting, unused imports only):** 201 remaining,
all requiring judgment: `F405`/`F403` (the deliberate `from lexer import *` cycle-break
in `shapes.py`/`parser.py`/`interp.py`, which carries its own explanatory comment —
left alone), `E701`/`E702` (multi-statement lines), `E741` (ambiguous names), `E501`
(two long lines).

**Mypy, before any fix:** 6 errors in 4 files.
**Mypy, after fixing the two "obvious annotation" hints** (`known_funcs: set = set()`,
`RESULTS: list = []`): 4 remain, all the same pattern — `except X as e:` followed by
code that reads `e` outside the `except` block, in `shapes_cli.py` (×3) and `planes.py`
(×1). Left as reported: whether that pattern is a latent bug or intentional is a
judgment call this build didn't make.

**Branch coverage baseline:** committed to `coverage-baseline.md`. Confirms v3.0 §53a's
prediction with a caveat: the analyser (`shapes.py`, `rules.py`, `modules.py`) sits at
89–98%, the CLI entry points (`shapes_cli.py` 6%, `planes.py` 52%) and two standalone
scripts (`run_hn.py`, `shapes_python_probe.py`, both 0%) sit near zero — but part of
that gap is a measurement artifact: `test_rules.py`'s CLI-exit-code tests invoke
`shapes_cli.py` via `subprocess`, which a parent-process `coverage.py` run cannot see.
Noted in the doc, not fixed (no behavioral change permitted in this phase).

No behavioral change. Suite held at 333/333 through this phase.

---

## 2. The Annotation Plane

Two constructs, both read positionally — `because` in trailing position after an
`Assign` or `Rule`, `note` at statement start followed by `:` — the same way `may`
and `is` already are. No ambiguity found; `because`/`note` were **not** reserved.
The ceiling stays at 30, not 32.

Inertness is structural in two different ways for the two constructs, because they
are different kinds of thing:

- **`Because`** is a field, not a statement. `Assign.expr` and `Rule`'s own fields
  are all `eval()`/`check()` ever touch; `stmt.annotation` was never wired into
  either, so there was nothing to strip — the promise holds by omission, not by an
  added guard. `eval()` has no case for `Because` at all; if one somehow reached it,
  it falls through to the pre-existing `cannot-evaluate` error.
- **`Note`** is a statement, like `Rule`. Unlike `Rule` (which reaches `exec_stmt`
  and quietly returns `None`), `exec_stmt` **raises** `annotation-executed` if a
  `Note` reaches it — see §3 for why that single sentence in the build prompt needed
  a second read.

`why` may now show a `because` text beside its one-line derivation and beside a
`why_tree()`'s root — display only, both functions take an optional `because=`
argument, and neither the `Deriv` graph nor `origins()` ever sees it (tested
directly: `origins()` returns `[]`, and no `Deriv` node ever carries `kind=="because"`).

`shapes.py` needed **no code change**. `walk()`'s default `return set()` for every
unhandled node type already meant annotations contribute zero effects — verified
live rather than assumed, and covered by `test_coverage.py`'s per-node oracle.

---

## 3. What Surprised Me: the Raise That Couldn't Fire

The build prompt's §1.4 code, read literally, makes `exec_stmt` raise
`annotation-executed` the instant it sees a `Note` — full stop, no filtering
mentioned. Implemented exactly as given, `annotated.planes` immediately failed to
run: a top-level `note:` block is an ordinary statement in `prog`, and `run()`
unconditionally calls `exec_stmt` on every statement in order. **Any** program using
`note:` at all would crash on the first note it reached.

That directly breaks two things the same build prompt asks for in the same breath:
"`annotated.planes` ... must run clean," and Phase 2's inertness test, which needs
**both** the annotated and the stripped version to run to completion so their
output/effects/surface can be compared — a crash on one side and success on the
other aren't "byte-identical," they're trivially different.

The tell was the error's own fix text: `"this is a bug in Planes, not in your
program — please report it"`. That phrasing only makes sense as a **defensive
tripwire** — something that should never fire during correct, ordinary use of the
documented `note:` syntax. If it fired on every single use of the feature, telling
the user it's not their fault would be actively misleading.

Resolution: `Note` is now filtered out at the three places statement lists get
dispatched for execution — `run()`, `run_file()`'s entry loop, and `exec_block()` —
so a normal run never calls `exec_stmt` on one. `exec_stmt`'s raise stays exactly as
written, now serving its actual purpose: a structural guarantee that if some future
call site forgets to filter, the interpreter refuses loudly rather than silently
doing something with a `Note`'s contents. `test_coverage.py`'s `Note` entry, which I
first built with a special `ExpectedToRaise` case type to route around the "always
crashes" behavior, reverted to a completely ordinary oracle case once the fix landed
— `Note` is inert by filtering the same way `Because` is inert by omission, and
both now "run exactly as the program would without them," which is the actual
guarantee, restated honestly instead of routed around.

A second, smaller version of the same shape: `why`'s optional `because`-display
**does** change `i.output` when exercised — that's the feature working as specified
in §1.5. Combining it with an annotated variable inside `annotated.planes` would
make the inertness test fail *correctly*, flagging a real (if narrow and expected)
exception to "output is byte-identical." Resolved by scope: `annotated.planes`
doesn't call `why` on an annotated binding; the display feature has its own direct
tests (`test_why_displays_because_text`, `test_why_omits_because_when_none_given`,
`test_stale_because_does_not_survive_reassignment`) instead of being exercised
through the byte-identical check. Worth a note for whoever locks the checkpoint:
"why may display" and "inertness is byte-identical output" are in genuine tension
the moment both apply to the same statement, and the resolution here is "don't do
that in the demo," not a structural fix — a future build could tighten this (e.g.
scoping the byte-identical check to output produced by `show`, not `why`) if it
matters more than it did here.

---

## 4. The Canonical Renderer

`render(prog, rules=None, surface=None)`. Round-trip verified across every
standalone-parseable `.planes` file in the repo — the top-level 7, `annotated.planes`,
and every fixture under `demo/` except `demo/app/net.planes`, which needs the
cross-file `known` name table `modules.py`'s `run_file()` supplies and does not
parse alone even on `main`, unrelated to this build.

**Calls render as `name of (arg1), (arg2)`, never `name(args)`.** This wasn't a style
choice — `parse_primary`'s `(` branch decides "argument list" vs. "parenthesised
sub-expression that continues" by peeking at the token *after* the closing paren, so
`ask("url") + x` parses as `ask` receiving `("url") + x` as its **one** argument, not
as a call followed by an addition. Found this by tracing `hn.planes`'s
`ask "..." + text of story-id + ".json"` construction by hand before trusting any
output. `of` with every argument parenthesised has no such lookahead hazard and
works identically for single- and multi-word names — one rendering rule, no
call-shape special-casing.

**Every `BinOp`/`Not`/`IsNothing` child is parenthesised** wherever it isn't already
the outermost expression of its statement. Traded minimal-parens prettiness for a
renderer with no precedence table to get wrong — correctness falls out of always
grouping, not from correctly ranking `+` against `and` against `in`.

**Round-trip equality ignores `line`.** `render(parse(src))` reparsed is compared
against the original AST with a purpose-built `ast_equal()`, not Python's dataclass
`==` — canonical reformatting legitimately moves where a token lands, and the
codebase's own precedent (`Effect`'s frozen dataclass excludes `derivation` from
`==` explicitly) is to name an excluded field rather than pretend position is
meaning.

**The marker** (`~ [rule-name] applies here`) is computed by calling `rules.check()`
— read-only, per invariant 5 — and mapping every `Violation` with a real `effect`
(both genuine violations and permit-cleared matches; only the vacuous shape has no
site) back to `effect.site`. Output only: nothing in `render.py` or the parser reads
a `~` line back in, verified by feeding a rendered-with-markers program back through
`render()` with no rules and confirming the marker text is gone, not reconstructed
from the prior text.

`shapes_cli.py --render` prints canonical form, with markers when the file declares
rules — its own single-file, unfollowed parse+analyse so `declaring_file=None`
matches `render()`'s internal `check()` call, per `rules.py`'s own documented
default-matching rule.

---

## 5. What Is Not Built

- **Any of the explicitly out-of-scope items** — mutation, `with`/`plus`, text-as-sequence,
  functions-as-values, `when` dispatch, user-defined errors, the record plane, amber,
  `until`/`contradicts`. None of the four phases needed to touch any of them; no
  finding about tier ordering to report.
- **A tighter branch-coverage measurement** for `shapes_cli.py`/`planes.py` that
  accounts for `subprocess`-invoked CLI tests (`coverage run --parallel-mode` +
  `COVERAGE_PROCESS_START`). Noted in `coverage-baseline.md`, not fixed — out of
  scope for a phase with "no behavioral change."
- **A resolution to the `why`/inertness tension** beyond scoping it out of the demo
  (§3, last paragraph) — flagged for whoever locks the next checkpoint, not silently
  left for someone to trip over.
- **The checkpoint recording V-Q1 and V-Q5 as locked**, carried forward from the
  immediately prior session (`48d1c359`) — still owed, still not this build's job.

---

## 6. Recommendation for the Next Session

Two things worth deciding on purpose rather than by inertia:

1. **The `why`/inertness tension (§3).** Either accept "don't combine `why` with an
   annotated variable in a program you're also inertness-testing" as a permanent,
   documented rule, or scope the byte-identical check to `show`-produced output only
   and let `why` diverge on purpose. Both are defensible; leaving it implicit is not.
2. **A checkpoint pass** covering both this build (annotation plane locked, renderer
   locked, the `Note`-filtering correction) and the still-owed V-Q1/V-Q5 checkpoint
   from the prior session — they're adjacent enough in time that combining them
   into one session may be cheaper than two separate passes.

Everything else in this build closed clean: no open questions, no deferred fixes,
no scope creep flagged and left unresolved.

---

## 7. Test Summary

| Suite | Tests |
|---|---|
| `test_planes.py` | 50 |
| `test_numbers.py` | 31 |
| `test_shapes.py` | 72 |
| `test_names.py` | 15 |
| `test_rules.py` | 63 |
| `test_foreign.py` | 37 |
| `test_host.py` | 14 |
| `test_coverage.py` | 7 |
| `test_assertions.py` | 20 |
| `test_values.py` | 24 |
| `test_annotation.py` | 17 (new) |
| `test_render.py` | 12 (new) |
| **Total** | **362/362** |

`verify_annotation.py`: sections A (inertness), B (round-trip), C (marker), D
(non-execution), E (regression + anti-drift) all PASS. Blocking set (A, B, E): PASS.
Full report in `annotation-verification.md`.
