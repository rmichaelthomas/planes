# Rule Plane — The Permit Form, Exception Resolution, and Fingerprinting

**Date:** July 23, 2026
**Session type:** Implementation. Closes the forbid-only gap the previous slice named as its own limitation.
**Mandate:** Add a `may` permit form; make it clear a specific prohibition, not defeat it globally; make equal-specificity opposite-assertion conflict — v2.0 §32's actual "opposite things" case — expressible and checked; add content-derived fingerprinting for `supersedes`, per the U-Q18/U-Q12 decisions locked ahead of this build.
**Result:** All three pieces shipped. `rules.py` still imports nothing but `hashlib` (stdlib, for the fingerprint). 264/264 tests passing — 240 before this session, two changed as this build's own §3/§4 required (argued below, not silently edited), 24 new.

---

## 1. `rules.py`'s Import List

```
$ grep -n "^import\|^from" rules.py
16:import hashlib
```

One import, `hashlib`, added for `fingerprint()` (§5 below). §6's consistency invariant said a stdlib import for hashing is fine and is not a `shapes` coupling — it isn't; `rules.py` still never names `shapes`, `parser`, `interp`, `Analyser`, `Consts`, or `Effect` in an import statement anywhere. §8's result from the previous slice — the checker consumes only what `Surface`/`Effect` publicly expose — is unchanged by this build. `narrows`, `_resolve_active`, `_check_permits_are_related`, and `_check_conflicts` all still compare `Rule` objects to each other and never touch `Surface` or `Effect`.

## 2. The Exception Resolution Rule, As Implemented

> An effect is a violation if a `forbid` rule matches it and no `permit` rule that supersedes or narrows that forbid rule *also matches the same effect*.

The italicized clause is the part easy to get wrong, and it is the one place this build found a real bug in its own first draft (§6 below). A permit is not a blanket override of the forbid it excepts — the forbid rule stays active and keeps applying to every effect the permit's own scope doesn't reach:

```
rule [no-external-sends] anything may not ask
rule [audit-allowed] anything may ask to "https://audit.internal"
x = ask "https://audit.internal"            -- cleared
y = ask "https://elsewhere.example.com"     -- still a violation
```

Both lines are covered by `test_broad_forbid_still_applies_where_the_permit_does_not_reach` and `test_permit_matching_a_different_target_does_not_clear`.

**A permit grants nothing on its own.** Every effect is permitted by default — Planes is a general-purpose language, not a sandbox — so a permit only has force *against* a matching, related forbid. `_check_permits_are_related` raises `RuleConflict` for a permit that excepts no forbid rule of its kind, whether because no forbid of that kind exists at all, or because the one that exists is unrelated (different target, no `supersedes`, no `narrows`). Tested by `test_unrelated_permit_raises_conflict` and `test_a_global_permit_grants_nothing_without_a_matching_forbid`.

**`narrows` alone clears a match; `supersedes` is required only at equal specificity.** Both are tested independently: `test_permit_that_narrows_a_forbid_clears_it_without_supersedes` (no `supersedes` clause at all) and `test_permit_that_supersedes_a_forbid_clears_it` (explicit clause, equal or unequal specificity either way).

**A computed permit target clears nothing.** This is the mirror image of the forbid side's existing conservatism, and it is not the same direction. For a *forbid*, an effect whose target the analyser could not pin down is treated as a possible match — widening a prohibition is sound, because missing a real violation is the failure that matters. For a *permit* granting an exception, the same uncertainty must NOT clear a match — widening an exception is not sound, because it could silently excuse an effect that isn't actually the one the permit names. `check()`'s clearing loop requires `p_matched and not p_uncertain`, not just `p_matched`. No test in the required list calls this out by name; it fell out of writing `check()` correctly and is worth flagging as a place the two guarantees' conservatism has a direction that flips depending on which side of "does this effect happen" a rule is arguing.

## 3. Same-Assertion vs. Opposite-Assertion `supersedes`: One Clause, Two Meanings

This is the one place the build prompt's semantics required a design decision it didn't spell out, and it is worth being explicit about, because getting it wrong would have silently broken the previous slice's already-shipped, already-tested behavior.

`supersedes` between two rules of the **same** assertion (forbid supersedes forbid, or permit supersedes permit) is unchanged from the previous build: version replacement. The superseded rule is dropped entirely from the active set before matching or conflict detection ever sees it — U-Q18's "an edit is an event, not a silent substitution," and nothing about adding permits should change what a same-assertion override already did correctly.

`supersedes` between two rules of **opposite** assertions (permit supersedes forbid) cannot mean the same thing. If it triggered the same blanket drop, `rule [audit-allowed] ... supersedes [no-external-sends]` would delete `[no-external-sends]` entirely — removing the prohibition on every target, not just the one the permit names, which is exactly the "any `may` anywhere silently defeats any `may not` anywhere" failure §3 explicitly warned against. `_resolve_active` now drops a superseded rule only when `target_rule.assertion == r.assertion`; a cross-assertion `supersedes` leaves both rules active, and the forbid's fate is decided per-effect by `check()`'s clearing loop instead. `test_broad_forbid_still_applies_where_the_permit_does_not_reach` is the regression test for this specific distinction — it fails immediately if the blanket-drop behavior is applied to a cross-assertion pair.

The fingerprint check in `_resolve_active` applies uniformly to both cases, because a supersedes target having changed is exactly as much a problem whether the relation is a version bump or an exception.

## 4. `_check_conflicts`, Extended

Two more things had to change beyond "also compare assertion":

- **The equal-specificity check now also accepts an explicit `supersedes` as a resolution**, not just `narrows`. Under the previous, forbid-only build this was never needed: any `supersedes` relation caused a blanket drop before `_check_conflicts` ever ran, so the pair never coexisted long enough to need this. Now that cross-assertion `supersedes` leaves both rules active (§3 above), an equal-specificity, opposite-assertion pair resolved by an explicit `supersedes` clause reaches `_check_conflicts` still holding both rules, and without this addition it would have been misreported as an unresolved conflict.
- **`_check_permits_are_related` treats equal-specificity pairs as "related," even though `narrows` itself correctly says no.** This was a real bug caught by manual testing before it reached the test suite (§6 below): an equal-target, opposite-assertion pair with no `supersedes` was being caught by the coarser "permit excepts no forbid rule" check before it ever reached the precise "demand opposite things" diagnostic in `_check_conflicts`. Fixed by widening "related" in the permits-check specifically to include equal targets, deferring the actual judgment to `_check_conflicts`, which has the sharper message.

## 5. Fingerprinting, As Implemented

`hashlib.sha256` over `subject`, `assertion`, `kind`, `target` (unit-separator-joined, empty string for no target), truncated to six hex characters. Explicitly excludes `name` and `line`, per §5's requirement — a rename or a moved line changes neither a rule's meaning nor its fingerprint, confirmed by `test_fingerprint_ignores_name_and_line`. `test_fingerprint_is_stable_across_runs` confirms the same rule fingerprints identically on repeated calls (the property `hash()` would not have given, which is why `hashlib` was used as directed).

Grammar: `supersedes [old] @a3f9c2`, parsed only inside a `supersedes` clause. A malformed attempt (wrong length, non-hex characters) needed its own lexer token — `@` plus exactly six hex characters is now a dedicated `FINGERPRINT` token in `lexer.py`, ahead of `NUMBER` in `TOKEN_SPEC`, because most fingerprints start with a digit and `NUMBER`'s greedy digit-run would otherwise split `@3f9c2d` into a number and a name at the first letter. `@` was also added to `OP`'s character class as a fallback, purely so a malformed fingerprint tokenizes as something the parser can catch and name the fix for (`test_malformed...` cases were not in the required list but the failure mode was real enough to guard against — see the parser's `elif self.at("OP", "@")` branch) rather than silently vanishing, which is what happens to any character the lexer's regex doesn't match at all.

Mismatch detection lives in `_resolve_active`, checked for every `supersedes` clause that carries a fingerprint regardless of assertion (§3 above), and names both rules, both lines, both fingerprints, and the fix (`test_mismatched_fingerprint_raises_naming_both_rules`). Absence is unverified, not invalid, and behaves exactly as it did before this build added fingerprints at all (`test_absent_fingerprint_behaves_exactly_as_before`).

`--fingerprints` on `shapes_cli.py` prints `[name] @xxxxxx` for every rule in the file and exits 0 unconditionally (informational, not a gate) — the minimum needed to make a fingerprint pasteable, per U-Q12's decision that the full canonical renderer is a separate, forked build and not this one's job.

## 6. A Bug Found by Testing the Design, Not the Code

Before writing the required test list, this build hand-ran three scenarios to sanity-check the design against itself: a clean exception, an unrelated permit, and an opposite-assertion conflict at equal specificity. The third one came back wrong — it raised "excepts no forbid rule" instead of "demand opposite things," because `_check_permits_are_related`'s notion of "related" was `narrows(p, f) or p.supersedes == f.name`, and `narrows` is deliberately `False` for equal-specificity pairs (that's what makes it a conflict rather than a nesting case). The coarser check fired first and hid the more accurate one underneath it.

This is recorded here rather than folded silently into §4 above because it is evidence for a specific claim: manually exercising a design's edge cases *before* encoding it into a test suite catches problems a test suite written from the same mental model would not have caught, since a test suite derived from an already-wrong model tends to confirm the model rather than challenge it. The fix (§4) is now covered by `test_opposite_assertion_equal_specificity_is_a_conflict` and `test_opposite_assertion_conflict_message_differs_from_same_assertion`, but the bug was found by hand, before either test existed.

## 7. Which Tests Changed, and the Argument for Each

**`test_nested_rules_do_not_conflict`** (§4's required change). It asserted `len(v) == 2` for a broad forbid and a narrower forbid both matching one effect, treating the two as independent. With permits in play, two same-shaped entries are now ambiguous to a reader — they could be two unrelated failures, or one could be the specific case of the other, or a permit could have cleared one of them. The original assertion (`len(v) == 2`, same rule names) is kept verbatim and extended, not replaced, with `broad.narrowed_by == [no-telemetry]` and a check that the rendered message names the relationship. This is real behavior change (`Violation` now carries `narrowed_by`), not a cosmetic tightening, so it could not be left alone.

**`REPORT_RULES.md` §5** (§3's required correction). Updated in place per the standing correction practice: the original prediction ("two all-forbidding rules can never demand opposite things... narrower than v2.0 §32's own framing") is left untouched above the correction block, because it was accurate when written — the effect-only slice genuinely had no permitting assertion. A blockquote beneath it states plainly that the boundary described was of that slice, not of the language, and points to this report.

No other existing test was modified. `test_rule_parses_with_all_fields` gained two additional assertions (`assertion == "forbid"`, `supersedes_fingerprint is None`) — additive, not a behavior change, and not counted as one of the two.

## 8. Test Summary

```
test_planes.py     50/50
test_shapes.py     63/63
test_numbers.py    31/31
test_names.py      15/15
test_foreign.py    37/37
test_host.py       14/14
test_coverage.py    7/7
test_rules.py      47/47   (23 from the previous slice + 24 new)
                  -------
                  264/264
```

240 before this session (two changed as argued in §7, not silently). 24 new.

## 9. The Anti-Drift Grep, Stated Separately From Verification

Ran clean this build, with no new hits: `policy`, `precedence`, `govern`, `allow `, `deny` do not appear in `lexer.py`, `parser.py`, or `interp.py`. Checked directly, not assumed — the same three-file, five-word scan `test_no_governance_vocabulary_in_source` has always run, unedited.

**That is a separate claim from verification, and it is stated separately on purpose** — ADDENDUM_SPRINT.md §5 and REPORT_RULES.md's own closing both made this point once already, about a report that closed with "anti-drift greps clean" as if it settled anything about correctness. It settles exactly one thing: no governance vocabulary leaked into three specific files. The claims that matter here — the exception resolution rule (§2), the same/opposite-assertion `supersedes` split (§3), fingerprint stability and mismatch detection (§5), the bug found by hand before it was a test (§6) — were each checked by running real code against real assertions, not by a grep.

## 10. What Forced a Choice This Prompt Didn't Fully Specify

- **The same/opposite-assertion split for `supersedes`'s meaning** (§3). The prompt gives the grammar and the exception-resolution rule but does not say what a cross-assertion `supersedes` should do to the superseded rule's *other* matches. The choice made — leave it active, resolve per-effect — is the only one consistent with §3's own resolution rule and with not silently reintroducing the "any `may` defeats any `may not`" failure the prompt explicitly warns against. Recorded here so it can be checked rather than assumed correct.
- **Whether equal-null-target pairs (`may not ask` vs. `may ask`, no targets at all) count as "opposite things."** They do, under the implementation here — same kind, same (absent) target, opposite assertion, no narrows/supersedes relation, so `_check_conflicts` raises. This reading was not spelled out in the prompt's worked example (which used a specific target on both sides) but follows the same rule uniformly rather than special-casing the unrestricted case.

## 11. What Is Still Not Built

- **Named-subject rule matching**, unchanged from the previous slice: `RuleNotSupported` still fires, every time, by design. §11 of this build prompt confirmed the derivation graph it needs is still not being built, and this session did not attempt it.
- **The canonical renderer.** U-Q12 locked that it forks from Liminate's and is its own build; `--fingerprints` here is the minimum that makes a fingerprint usable today, not that renderer.
- **A derivation line in a violation message**, unchanged from REPORT_RULES.md §2 — still requires the same static derivation graph, still not built.
