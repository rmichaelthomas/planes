# Closing the Annotation Build's Reported Gaps — Session Report

**Date:** July 24, 2026
**Session type:** Hardening pass, not a feature build. Closes the five gaps `REPORT_ANNOTATION.md` named against itself.
**Mandate:** Widen the inertness sample, resolve the `why`/inertness tension structurally, fix the coverage measurement blind spot, triage the mypy/ruff findings left as judgment calls, and split the verification report so it can't overstate its own coverage.
**Result:** Built. 365/365 tests passing (362 prior + 3 new: sample-size, nesting-coverage, and the `why`-does-not-break-inertness proof). `ruff check .` and `mypy .` both exit clean. All eight verification-gate sections (A1/A2/B/C/D/E/F/G) PASS. One finding from the prior report turned out to be wrong on closer inspection — corrected below, not quietly dropped.

---

## 1. The Five Gaps, and What Closed Each

### Gap 1 — the inertness sample rested on one file

`annotation-verification.md` §A showed 35 PASS rows; only 8 were the real three-way
check, and only `annotated.planes` — a purpose-built demo — carried any annotation.
Added plausible `because`/`note` annotations to four more real programs already in
the repo, each chosen to exercise a nesting site `render.strip_annotations` recurses
through but nothing had tested: `money.planes` (inside a `FuncDef` — the tax rate and
the rounding step), `gate.planes` (inside an `If` branch — the 185.42 regression
guard; added since none of the three files this phase named had a suitable `if`, and
the prompt's own escape hatch covers that), `hn.planes` (inside a `ForEach` body —
the printed-vs-written distinction for each story), and `demo/rules/exception.planes`
(both rules in a permit/forbid pair, plus a `note` deriving from one). Sample: 5
files, `FuncDef`/`If`/`ForEach` all exercised, both proven by a dedicated test
(`test_inertness_sample_covers_more_than_one_file`,
`test_nesting_is_exercised_in_funcdef_if_and_foreach`) and independently re-checked
by the verification gate's new §F, not just asserted once.

### Gap 2 — `why`/inertness resolved by scope, not structurally

Ruling implemented: **inertness governs effects, not inspection.** `show`, `write`,
`ask`, `read` are what a program *does* — the closed vocabulary `EFFECT_KINDS`
covers, logged in `Interpreter.effects`. `why` is the derivation query, not a
boundary crossing; it never touches `effects` at all. `test_annotation.py`'s
`run_and_capture` now compares show-output (`effects` of kind `"show"`), the full
effect log, and the static surface — never the raw interleaved `i.output` that `why`
also writes to. `annotated.planes` now calls `why cap` on its annotated binding, the
exact case the prior build scoped out rather than resolved.
`docs/annotation-scope.md` writes the rule down, as a lock, per the prior report's
own §6 item 1.

### Gap 3 — the coverage blind spot

`test_rules.py`'s CLI-exit-code tests invoke `shapes_cli.py` via `subprocess.run`,
invisible to a parent-scoped `coverage run`. Fixed with the standard coverage.py
subprocess hook: `pyproject.toml`'s `[tool.coverage.run] parallel = true` +
`[tool.coverage.paths]`, and a committed `sitecustomize.py` at the repo root calling
`coverage.process_startup()` (a no-op unless `COVERAGE_PROCESS_START` is set, which
`subprocess.run` inherits from the parent by default). `shapes_cli.py`: 6% → 51%
(+45pp — the artifact was real and large). `planes.py`: 52% → 58%. Full delta and
the newly-honest remaining gap (which CLI flags genuinely have zero test coverage,
named explicitly) are in `coverage-baseline.md`, original numbers kept under a
"before" heading per the instruction not to erase the evidence.

### Gap 4 — four mypy errors left as a judgment call

Traced every `except ... as e:` block in `shapes_cli.py` and `planes.py`
exhaustively (§2 below — this is where the correction is). Renamed the four flagged
`for e in ...:` loop variables to `eff`, resolving the name collision. mypy: 4 → 0.

### Gap 5 — 201 unclassified ruff findings

Classified, not mass-fixed. `F403`/`F405` (155, the deliberate `from lexer import *`
cycle-break) and the `E701` compact-table patterns in `lexer.py`'s AST dataclasses
and `interp.py`'s operator-dispatch functions (26) are now `pyproject.toml`
per-file-ignores with the reason inline. Everything else — two long lines, six
ambiguous names, nineteen genuinely-compressed multi-statement lines — is fixed.
`ruff check .` now exits 0: every remaining finding is a stated, configured
exception, not silence.

---

## 2. A Correction, Not Just a Close-Out

`REPORT_ANNOTATION.md` §1 said the four mypy `except ... as e:` findings were
"a real latent `NameError`" and left determining reachability as owed work. That
claim was never actually checked against the code — it was a plausible-sounding
guess about what the mypy error code usually means, stated as a finding.

Tracing all four sites this session (§6.1 of the build prompt asked for exactly
this): every `except ... as e:` block in both files uses `e` only inside its own
block, in an f-string, immediately, then returns or continues. None of the four
flagged sites — `shapes_cli.py:182,317,330` and `planes.py:80` — are anywhere near a
stale read. Each is a `for e in <effects>:` loop that happens to reuse the letter
`e` from an unrelated, already-exited `except` block earlier in the same function.
mypy's complaint is a real, worth-fixing name-collision warning — a reader
skimming the function could momentarily wonder if the loop's `e` is the earlier
exception — but it was never a reachable bug under any code path.

This matters beyond the four lines it's about: it's the same failure shape
`REPORT_AUDIT.md` exists to catch, and it happened inside a report whose whole job
was auditing something else. Recorded here rather than silently fixed and moved
past, because a wrong claim that goes uncorrected is worse than an unfixed bug —
the bug was never there to begin with.

---

## 3. What This Cost

Five phases, all mechanical or structural — no new language surface. The two real
design decisions (the `why` boundary, and what "reachable" actually meant for the
mypy findings) both required tracing actual code paths by hand before writing
anything down; neither was resolvable by pattern-matching the prompt's own framing
against the code without checking it against the code.

---

## 4. What Is Not Built

- **A coverage-driven pass over `shapes_cli.py`'s genuinely-untested CLI surfaces**
  (`--index`, `--search`, `--diff`, `--render`, `--fingerprints`, `--json`,
  `--functions`, `--check`, and the top-level error branches) — named explicitly in
  `coverage-baseline.md`, not fixed, per this build's own §5.3: no test written to
  chase a coverage number. Its own build, its own review.
- **Any of the explicitly out-of-scope items** from the original Tier 0 build —
  unchanged, untouched.
- **The still-owed V-Q1/V-Q5 checkpoint** from the value-model-semantics session —
  carried forward again, now alongside a checkpoint for the annotation plane and
  this hardening pass.

---

## 5. Recommendation for the Next Session

One item, concrete: **the checkpoint pass** covering V-Q1/V-Q5 (owed two sessions
back), the annotation plane and renderer locks (owed one session back), and this
session's two locks (the `why`/effects boundary, now written down in
`docs/annotation-scope.md`; and the corrected understanding of what the four mypy
findings actually were). Three sessions' worth of "still owed" is a real backlog,
not a rounding error — worth doing as one checkpoint pass rather than deferring a
fourth time.

---

## 6. Numbers

**Ruff:** 201 → 0 (every remaining pattern classified as a stated, configured
exception in `pyproject.toml`, not silently ignored).
**Mypy:** 4 → 0.
**Coverage:** `shapes_cli.py` 6% → 51%, `planes.py` 52% → 58%, total 82% → 87%,
after fixing subprocess attribution. Full breakdown in `coverage-baseline.md`.

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
| `test_annotation.py` | 20 (+3 this session) |
| `test_render.py` | 12 |
| **Total** | **365/365** |

`verify_annotation.py`: sections A1 (5 files, real annotations), A2 (23 files,
structural/trivial-run no-op net), B (round-trip), C (marker), D (non-execution), E
(regression + anti-drift), F (widened sample), G (`why` boundary) — all PASS.
Blocking set (A1, B, E, F, G): PASS. Full report in `annotation-verification.md`.
