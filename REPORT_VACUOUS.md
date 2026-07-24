# Session Report — The Vacuous Rule: Reporting a Subject That Resolved and Matched Nothing

Opens and closes P-Q19 (the vacuous-rule gap, found by verification of the
derivation build `3d63305`…`6320aae`). Extends that build and Checkpoint
v2.0. All four judgment calls from `REPORT_DERIVATION.md` were carried
unchanged and not revisited.

---

## This was a reporting change, not a semantics change — verified, not asserted

Every existing test in `test_rules.py` (53 of them) passed **without
modification** once the implementation was in place. That is the strongest
available evidence that no rule which passed before now fails, and no rule
which failed before now passes: the entire pre-existing behavioral contract
of `check()`, expressed as tests, held exactly as written.

## The exit-code table (§4)

`--rules` run over every `.planes` file in the repository (26 files, every
one under the repo root and `demo/`, excluding the ephemeral `demo/_*`
scratch directories test files create and clean up), before this build's
changes (`git stash` back to the state at `6320aae`) and after:

| file | before | after |
|---|---|---|
| `demo/app/config.planes` | 0 | 0 |
| `demo/app/main.planes` | 0 | 0 |
| `demo/app/net.planes` | 1 | 1 |
| `demo/clash/cache.planes` | 0 | 0 |
| `demo/clash/loader.planes` | 0 | 0 |
| `demo/clash/main.planes` | 1 | 1 |
| `demo/fdiff/v1.planes` | 0 | 0 |
| `demo/fdiff/v2.planes` | 0 | 0 |
| `demo/pkgs/cachelib.planes` | 0 | 0 |
| `demo/pkgs/fetcher.planes` | 0 | 0 |
| `demo/pkgs/logger.planes` | 0 | 0 |
| `demo/pkgs/mathlib.planes` | 0 | 0 |
| `demo/pkgs/sneaky.planes` | 0 | 0 |
| `demo/rename/cache.planes` | 0 | 0 |
| `demo/rename/loader.planes` | 0 | 0 |
| `demo/rename/main.planes` | 0 | 0 |
| `demo/rules/clean.planes` | 0 | 0 |
| `demo/rules/exception.planes` | 0 | 0 |
| `demo/rules/violation.planes` | 1 | 1 |
| `demo/v1.planes` | 0 | 0 |
| `demo/v2.planes` | 0 | 0 |
| `foreign.planes` | 0 | 0 |
| `hn.planes` | 0 | 0 |
| `money.planes` | 0 | 0 |
| `names.planes` | 0 | 0 |
| `ordinary.planes` | 0 | 0 |
| `pypi.planes` | 0 | 0 |

**Zero differences.** `diff` between the before and after tables is empty.
The three pre-existing exit-1 cases are unrelated to rules or to this
build: `net.planes` fails to parse standalone (a pre-existing syntax error
when analysed outside `main.planes`'s import graph), `clash/main.planes`
hits the pre-existing module-name-collision demo, and
`rules/violation.planes` is a genuine, unaffected rule violation
(`anything`-subject, target-matched, exit 1 both before and after). No file
already in the repository happens to contain a named-subject rule that
resolves and matches nothing — the new exit-2 path is real and tested
(§5), but this corpus does not exercise it. That is itself informative: the
gap this build closes was reachable in principle (proven by the synthetic
test cases) but had not yet occurred in any file this repository ships.

## Existing tests: none changed

Checked directly, not just reviewed: `git stash` back to the pre-build
`rules.py`/`shapes_cli.py`/`test_rules.py`, ran `test_rules.py`, restored,
ran again. No existing test's assertions needed to change — ten new tests
were added, zero were edited. This is the signal the build prompt asked to
watch for ("if one does, that is a signal this build crossed into
semantics — stop and report before editing it"); it did not fire.

## The exit-code-2 choice

Accepted as specified. `2` already means "usage error" elsewhere in
`main()`, and the prompt's framing — both mean "this invocation did not do
what you think it did" — holds up under scrutiny: a usage error means the
tool wasn't asked to do anything meaningful; a vacuous rule means the tool
was asked to check something and found nothing to check it against. Both
are "this gate did not actually gate." No argument for a different code.

## `--json` gap

Confirmed and left alone, as instructed. `as_json` in `shapes_cli.py` does
not include rule results — vacuous, violated, or clean — in any form. An
agent consuming `--json` cannot see rule outcomes today. This is a real
hole, separate from this build, and the CLI docstring now says so
explicitly (`--rules does not yet appear in --json's output`).

## `rules.py`'s import block

Confirmed by `ast.parse` (the same direct assertion as the prior build,
`test_rules_module_imports_only_hashlib`, still passing unmodified):

```
['hashlib']
```

No new import was needed. Vacuous detection is built entirely from
`_target_matches` and `_subject_matches`, both already present, plus
`Violation`'s existing constructor pattern.

## Decisions this build made that the prompt did not specify

Two, named explicitly per the standing instruction:

1. **`vacuous_situation` (1/2/3) is set as a plain attribute after
   construction, not threaded through `Violation.__init__`.** The prompt's
   given constructor signature adds exactly one new parameter (`vacuous`)
   and shows no situation/detail parameter alongside it. Rather than add an
   undocumented kwarg to a signature the prompt wrote out explicitly,
   `check()` constructs the `Violation` with `vacuous=True` and then sets
   `v.vacuous_situation = 1 | 2 | 3` directly — `Violation` is a plain
   mutable class, not frozen, so this is unremarkable in this codebase and
   keeps the constructor's shape exactly as specified. **Recommend: lock.**
   It is a narrow, mechanical choice with no behavioral consequence.

2. **The counter loop computes `_subject_matches` for every kind-matching
   effect unconditionally, rather than short-circuiting on `_target_matches`
   first as the pre-existing code did.** Distinguishing situations 1/2/3
   needs to know, for every effect that shares the rule's kind, whether the
   subject reaches it *regardless* of whether the target also matches — so
   both predicates are computed before either `continue`s. This is a
   real (if small) added cost per named-subject rule: `_subject_matches`
   now runs even for effects whose target already excluded them, where
   before it never would have. The actual violation-detection condition
   (`not matched or not subject_ok: continue`) is unchanged, so no rule's
   pass/fail outcome differs — only when the (pure, side-effect-free)
   `_subject_matches` call happens. **Recommend: lock**, and treat the
   existing §6-style cost note in `check()`'s docstring as already covering
   it — no further comment needed unless a future profiling pass finds it
   material.

## Test counts

| | before this build | after |
|---|---|---|
| `test_rules.py` | 53/53 | 63/63 |
| `test_shapes.py`, `test_planes.py` (incl. session gate), `test_coverage/foreign/host/names/numbers.py` | unchanged | unchanged, all green |

Ten new tests, all in `test_rules.py`, covering §5 items 1–8 directly (one
test each for situations 1/2/3, the `anything`-is-never-vacuous regression,
an unaffected matching named subject, a vacuous-plus-real-violation mix,
`is_violation` is False for vacuous, and permits are out of scope) plus two
CLI-level tests exercising the actual `shapes_cli.py` subprocess exit codes
(2 for a vacuous rule, 0 for a clean `anything` rule with no match) for
end-to-end confidence beyond the in-process `check()` assertions. Item 9
(the standing session gate) is `test_planes.py`'s
`test_ordinary_program_needs_no_governance` /
`test_ordinary_program_is_traceable`, unmodified, still passing (verified
above in the exit-code and test-count check).

## Commits

```
3538ab7 rules: report a named subject that resolved but matched nothing (P-Q19)
```
