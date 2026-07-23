# Rule Plane, Effect-Only Slice — Session Report

**Date:** July 23, 2026
**Session type:** Implementation. Tests inception checkpoint §8's claim on the one half it can be tested against.
**Mandate:** Build the smallest slice of the rule plane that checks an effect-reaching rule (*payment data may not leave the billing module*, shaped down to *anything may not ask to X*) statically, against real machinery, and produces the violation message inception checkpoint §24 wrote by hand — or find out that §8 does not hold and report that instead.
**Result:** §8 held, without qualification, for the effect half. `rules.py` imports nothing — not even `shapes`. 240/240 tests passing (217 existing, unmodified in behavior, plus 23 new). §24's message is produced in full except the one line that names a derivation, which is correctly not fake-able and is omitted. A pre-existing, previously-invisible bug was found and fixed along the way (§3).

---

## 1. Whether §8's Claim Held

**Yes, cleanly, and more strongly than the checkpoint's own appendix predicted.**

`rules.py`'s complete import list:

```python
$ grep -n "^import\|^from" rules.py
(no output)
```

Not "imports only the public `Surface` queries" — imports *nothing*. `check(rules, surface)` receives `surface` as a parameter and calls exactly one thing on it, `surface.declared`, then reads `.kind`, `.target`, `.computed`, `.site` off the `Effect` objects that property yields. It never names `shapes`, `Analyser`, `Consts`, or `Effect` in an `import` statement. The dependency is structural (duck-typed on the object handed in), not even textual.

This is the strongest form the §8 claim could take: not merely "uses only the public surface," but "does not need to know the surface's module exists." Consistency invariant #2 (`rules.py` imports from `shapes.py`, never the reverse) is trivially true — there is no import in either direction from `rules.py`'s side.

`narrows`, `_resolve_active`, and `_check_conflicts` (§13, below) add no coupling: they compare `Rule` objects to each other, never touching `Surface` or `Effect` at all.

## 2. Which Part of §24's Message Is Produced

The target, from inception checkpoint §24:

```
[readings-stay-local] violated at line 9.
  readings derive from file "readings.csv" (line 5)
  ask https://metrics.internal/ingest
  rule declared at line 1
```

What this slice produces, running the actual demo file (`demo/rules/violation.planes`, `python3 shapes_cli.py demo/rules/violation.planes --rules`):

```
[readings-stay-local] violated at line 9.
  ask https://metrics.internal/ingest
  rule declared at line 1: anything may not ask to "https://metrics.internal/ingest"
```

Every line is real, produced by matching a parsed `Rule` against a computed `Surface` — nothing hand-typed to fit the target. The one line not produced is `readings derive from file "readings.csv" (line 5)`. That line asserts a *derivation* — that the value flowing into `ask` came from `readings.csv`. Nothing in this codebase computes that statically. `shapes.py` has no derivation graph; `Deriv`/`Traced` (`interp.py`) build one, but only at runtime, one execution at a time, and a rule must never execute anything (v2.0 §33; enforced in §7, tested in §8.12). Producing that line would mean either running the program to get a real derivation (violating §33) or inventing plausible-looking provenance from nothing — the second is explicitly the failure the two guarantees exist to prevent, and it was not done. The line is omitted, not faked.

**One addition beyond the literal §24 target, made after §11.4's human read.** The original message left "rule declared at line 1" bare — to know *what* the rule actually forbids, a reader had to open the file and look. `rules.py::condition()` now echoes the rule's own condition on that line (`rule declared at line 1: anything may not ask to "https://metrics.internal/ingest"`), so the message is legible without leaving the terminal. This isn't a deviation from a locked constraint — §5 of the build prompt only forbids the *derivation* line specifically; it says nothing against enriching the rest. The reasoning is the same one behind `read_claim`'s error messages and the locked commitment in unbound v1.1 §22 item 1: an error should name the fix, not send the reader hunting for it. This is exactly the kind of thing meant to fall out of building the slice and getting a human to actually read the output, rather than being specified up front.

## 3. A Finding: `Effect.site` Existed but Was Dead

The build prompt's own appendix cites `Effect(kind, boundary, target, computed, site, claimed)` as evidence that effect-reaching rules were already supported — `site` reads as "the field this rule plane needs already exists." It does exist. It was never populated. Every one of the six `Effect(...)` construction sites in `shapes.py` omitted `site`, so it silently held its dataclass default, `0`, for every effect in every program ever analysed. The first real test of a violation message —

```
[no-telemetry] violated at line 0.
```

— caught it immediately, because a rule plane is the first consumer that needs a *specific* line rather than just "somewhere in this program."

This is the same shape of bug as the FFI tuple-vs-string kind bug (REPORT_FOREIGN.md §5, REPORT_TARGETS.md §3): a field existed, nothing exercised the path that would make its absence visible, and it stayed silently wrong until a new consumer needed it. Fixed by threading line numbers from the tokens that already carry them (`Show`, `WriteTo`, `Call`, `Foreign` in `lexer.py` each gained a `line: int = 0` field; `parser.py` passes the already-available token line at every construction site — no new lexing work, the information was one token dereference away) through to `Effect(..., site=node.line)` in `shapes.py`'s `walk()` and `foreign_effects()`. This is source-position plumbing, not derivation machinery — it adds no new pass, no provenance graph, nothing §12 would have stopped for. `EFFECT_KINDS` was also moved from `shapes.py` to `lexer.py` in the same pass, because the parser needs the closed vocabulary to validate a rule's effect kind at parse time and cannot import `shapes.py` without a cycle; `shapes.py` re-exports it unchanged via its existing `from lexer import *`, so `from shapes import EFFECT_KINDS` still works everywhere it already did.

All 217 pre-existing tests pass unchanged after both fixes; neither touches behavior anything currently tests, only a field nothing previously read.

## 4. The Public Query Surface: One Real Gap, Otherwise Sufficient

`Surface.declared` (already public, already listed as an allowed query) was enough for everything `rules.py` needed to *match*. The one thing the query surface did not provide — because nothing had needed it before — was `Effect.site` actually being populated (§3). That was a data-completeness gap in `shapes.py`, not a missing query; no new method was added to `Surface`, and none was needed. Once `site` was real, `at`, `targets`, `touches`, `declared`, `kinds`, `boundaries` were never reached for beyond `declared`, and never fell short.

Nothing else was awkward. `Surface.declared`'s existing dedup-and-sort behavior made `check()`'s output order deterministic for free.

## 5. §13: Continued Past §8 Holding

Per §13, having confirmed §8 held, work continued without stopping into `narrows`, `supersedes`, and equal-specificity conflict.

**`narrows(b, a)`** — unambiguous from the build prompt's own text ("a rule naming a target narrows one that does not"): same kind, `a` has no target, `b` has one → `b`'s forbidden set is a strict subset of `a`'s. Implemented exactly that, comparable only within a shared kind.

**`supersedes`** — added as a trailing clause on the rule statement itself (`rule [new] ... supersedes [old]`), per "written as a clause of the asserting rule... external registry refused." `may` and `not` set the precedent for reading a word positionally without reserving it; `supersedes` follows the same pattern — the reserved-word count in `lexer.py` did not move a second time. A rule named in another's `supersedes` clause is dropped before matching. An unresolvable `supersedes` — an unknown name, or a rule superseding itself — is a compile error naming the fix, resolved in `rules.py::_resolve_active`, never silently ignored.

**Equal-specificity conflict as a compile error** — implemented with one explicit, documented narrowing of scope, called out here rather than silently assumed. v2.0 §32, as summarized in the build prompt, frames this as "two rules that demand opposite things," which reads as presuming a *permitting* assertion alongside the forbidding one — an ACL-style precedence graph where a narrower `may` carves an exception out of a broader `may not`. §2 of this build locked the grammar to `may not` only ("the minimum that expresses an effect-reaching rule"); no `may`-as-permit form exists in this slice. Two all-forbidding rules can never demand *opposite* things — at most they can be redundant (one narrows the other, handled) or ambiguous (equally specific, unrelated by narrows or supersedes). What is implemented is that second, well-defined case: two distinct rules, same kind, same target (including both unrestricted), with neither narrowing nor superseding the other, is a `RuleConflict`, raised before matching, naming both rules, both lines, and the shared kind/target. This is a real compile-time check with real tests (`test_equal_specificity_conflict_is_a_compile_error`, `test_supersedes_resolves_what_would_otherwise_conflict`), not a stub — but it is narrower than "opposite things" would be once this language has a permitting assertion, and that gap should not be mistaken for having been resolved. It is a scope decision made in the open, not a silent one.

Stopped before fingerprinting, per §13's own instruction: v2.0 §29's content-derived identity forces U-Q18 — where superseded rule versions live, and for how long — which has no answer anywhere in the chain available to this session. Building fingerprinting without an answer to U-Q18 would mean inventing a retention policy nobody has decided. Not built.

> **Correction, added in the permit-form build (`feat/rule-permit-and-fingerprints`, see REPORT_PERMIT.md).** The prediction above — "opposite-assertion conflict becomes expressible once a permitting assertion exists" — was correct, and it is now built. U-Q18 was answered (store nothing; the superseding rule carries a fingerprint of the version it overrides, recomputed and compared, not retained) and fingerprinting shipped in the same build. The claim that stood correctly at the time this section was written — "two all-forbidding rules can never demand opposite things" — is no longer the state of the language; it described a true boundary of the effect-only slice, not a permanent one. Left in place above because it was an accurate account of what existed when it was written, and the two-guarantees discipline this project runs on treats a correction as a visible addition, not a rewrite of the record.

## 6. The Anti-Drift Grep

It fired once, mid-build, correctly, on `lexer.py`, for `govern` — not from `interp.py`, `parser.py`, or genuine governance vocabulary, but from a doc-comment on the `Rule` dataclass copied near-verbatim from this build prompt's own §2 code sample: `# what it governs; "anything" is the wildcard`. This is worth recording precisely because it is the mechanism working as designed, catching real drift rather than failing to fire: the word was in the file, the grep does a lowercase substring check, and it does not know or care that the word came from the specification rather than from scope creep. The fix was to reword the comment (`# what the rule applies to`), not to touch the test. `test_no_governance_vocabulary_in_source` was never edited and passes unmodified — the same three files it has always scanned (`lexer.py`, `parser.py`, `interp.py`), the same five banned words. `test_ordinary_program_needs_no_governance` also passes unmodified.

**The grep passing clean is not, by itself, evidence that this session's work is correct.** ADDENDUM_SPRINT.md §5 already made this point once, about REPORT_FOREIGN.md's closing line, and it applies here with the same force: a clean grep means no governance vocabulary leaked into three specific files. It says nothing about whether `rules.py` matches correctly, whether the parser's error messages are honest, or whether the violation message says what it should. Those are the claims in §1, §2, §4, and §5 above, each checked separately and independently of the grep.

## 7. One Existing Test Was Edited — Not Accommodated, Argued

`test_reserved_list_is_only_structural_words` (`test_names.py`) hard-caps `len(KEYWORDS)` and its own docstring documents three prior, legitimate rises (25 → 26 → 29), each tied to a report making the case that the new word had no other spelling. `§2` of this build mandates exactly one new reserved word, `rule`, as load-bearing. Growing `KEYWORDS` to 30 is therefore not incidental — it is the first thing this build does — and it necessarily fails that test's hard-coded ceiling on the very same commit that adds the keyword. Per this file's own established convention (three prior precedents, same file, same shape of edit), the ceiling was bumped to 30 and a fourth bullet was added, in the same style as the other three, naming the report and the argument (`rule` has no other spelling; `may`/`not` were deliberately left unreserved). This is the one exception in this session to "no existing test is modified to accommodate this build" (§9.1) — made in the open, following a precedent already present in the file being edited, not to silence a failure but because the ceiling test's own design is to move exactly when a case like this one is made.

## 8. Test Summary

```
test_planes.py     50/50    language, including the anti-drift grep and the governance-free-program gate
test_shapes.py      63/63   analyser, modules, namespacing, renaming, oracle
test_numbers.py     31/31   exactness, rounding, boundaries, limits
test_names.py       15/15   every builtin/keyword name usable as a name; reserved-word ceiling (29 → 30, §7)
test_foreign.py     37/37   FFI, declarations, claims, the unknown default
test_host.py        14/14   the host seam
test_coverage.py     7/7    node-type oracle coverage, including the new Rule case
test_rules.py       23/23   parsing (5 required + 2 extra = 7), matching (6/6 required), narrows/supersedes/conflict (9, §13), inertness (1/1 required)
                   -------
                   240/240
```

217 before this session, unmodified in behavior (one edited to raise its own documented ceiling, §7). 23 new.

## 9. What Is Not Built

- **Named-subject rule matching.** `readings may not ask` parses; checking it raises `RuleNotSupported` naming why, every time, by design (§4's failure mode #1 — silent pass on an unsupported subject — was checked against directly in `test_named_subject_raises_rather_than_passing_silently`). Requires the static derivation graph this slice was explicitly told not to build.
- **The derivation line in a violation message.** §2 above.
- **Fingerprinting / content-derived rule identity (v2.0 §29).** Stopped per §13's own instruction, blocked on U-Q18.
- **A permitting (`may`) assertion.** Without it, "equal-specificity conflict" (§5 above) is necessarily narrower than v2.0 §32's own "opposite things" framing. The gap is named, not hidden.

## 10. Verification, Stated Separately From the Grep

Ran directly, not inferred: all eight suites (`test_planes.py` through `test_rules.py`) executed via `python3 <file>.py`, 240/240 passing, shown above. `demo/rules/violation.planes` with `--rules` produces the exact §5-target message and exits 1; `demo/rules/clean.planes` produces "1 rule checked, no violations" and exits 0 — both run and read in §11.2, not assumed from the code. `test_the_suite_does_not_touch_the_real_world` ran every `test_*.py` including the new `test_rules.py` and found no real-filesystem writes.

The anti-drift grep's result is §6, above, and is a separate claim from this one.
