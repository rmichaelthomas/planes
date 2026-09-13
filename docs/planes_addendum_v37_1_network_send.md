# planes_addendum_v37_1_network_send.md

# CANONICAL CHECKPOINT DOCUMENT
## Planes
### v37.1 — network_send: a network effect that sends is accepted for a later build, browser request kinds are not, and v37.0's rule-checker fix is applied

**Status:** LOCKED — EXTENDS planes_checkpoint_v37_0_rule_target_matching
**Date:** September 13, 2026
**Author:** Rob Thomas / R. Michael Thomas (architect) and Claude (analytical and implementation partner)
**Domain prefix:** planes
**Session type:** Thread closure addendum. One language question settled in principle and left for a build session. One locked fix from v37.0 applied. No language semantics changed.
**Relationship to prior checkpoints:** Direct continuation of planes_checkpoint_v37_0_rule_target_matching (August 24, 2026). All prior decisions from the earliest inception through v37.0 are in force. Nothing retracted. Part/§ numbering continues from Part CCI / §524.
**Relationship to v37.0:** Applies v37.0 §513's fix, which v37.0 recorded as a patch not yet in the repo. Adds one open question. Does not touch P-Q17 (rule-target matching).

**Where this document lives.** The architect asked for it in the Planes repository, committed to `main`. It is the first working document on this chain kept in the repo (`docs/`) rather than the vault.

Koncord's networking layer asked something of Planes that Planes could not say. Its content rule list needed each admitted request to carry a *type* — fetch, image, script — and a Planes rule's `ask` carries only a destination (Koncord Primitive Engine addendum v1.10 §271.1). Koncord worked around it. The architect then asked the question on Planes' own terms: set Koncord aside — would request kinds expand the language usefully and purposefully, and what would make an addition additive enough to consider? Untangled, the question held two different things. Browser request kinds turned out to be a browser's vocabulary, not a program's. But asking it exposed a real gap Planes has always had: a program can *get* from the network and cannot *send* to it, and the effect surface cannot tell the two apart when a host does it. The first is refused. The second is accepted in principle and left for a build.

---

## HOW TO READ THIS DOCUMENT

- **Part CCII (§525–§527)** — v37.0's rule-checker fix, found unapplied and applied in all three implementations.
- **Part CCIII (§528–§531)** — the request-kind question, untangled: where it came from, why browser kinds are refused, the test an addition must pass, and the gap it named.
- **Part CCIV (§532–§533)** — the decision, and what a build must settle.
- **No language semantics changed.** The vocabulary is still seven effect kinds. A program behaves as before, except that `--rules` no longer reports matches v37.0 §513 proved impossible.
- Absence claims are marked *verified*, with where, or *UNVERIFIED*.

---

## PART CCII — v37.0's FIX, APPLIED

§525. **The fix was not in the repo.** v37.0 locked §513 and listed `rules-computed-target-exclusion.patch` as "in outputs, not yet applied to repo." Verified absent at `621decc`: `_target_matches` at `rules.py:256` still returned `(True, True)` for every computed target, and no `_pattern_excludes`, `patternExcludes` or equivalent existed in `rules.py`, `js/rules.mjs` or `swift/Sources/Planes/Rules.swift`. The Swift port (PR #102), written after v37.0, had faithfully copied the unfixed checker. The patch file itself was not available to this session.

§526. **Applied as specified, with one guard §513 did not state.** PR #104, merged as `971961c`:
- `rules.py`: `_pattern_excludes(rule_target, effect_target)`, with anchored, ordered chunk matching over the `{...}` pattern. A hole may stand for any text, including none. When the chunks cannot reach the rule's target, `_target_matches` returns `(False, False)`. Otherwise it returns the prior `(True, True)`.
- **The guard.** A computed target that is not a pattern excludes nothing. A foreign function that declares an effect with no destination reports `<host function> (destination not stated)`, with `computed=True` and no hole. That text names where the claim came from, not where the request goes, so its differing from a rule's target proves nothing. Without the guard the predicate would have hidden a real reach, which §514 forbids.
- `js/rules.mjs` and `Rules.swift` carry the same predicate. Swift compares scalar by scalar, never by `String`'s canonical equivalence.

§527. **Verification.**
- `test_rules.py` gained end-to-end and unit cases: another host excluded, a still-possible target kept uncertain, both-end anchoring with ordered middle chunks, the no-destination guard, and a real violation still firing beside an excluded one.
- `test_js_rules.py` and `test_swift_rules.py` gained agreement scenarios for every branch, including a decomposed `é` against a composed one and an astral chunk.
- Disabling the exclusion in Python fails two tests. Disabling it in JavaScript or Swift fails that host's agreement suite.
- `grammar/errors.json` was regenerated; only five `rules.py` source lines moved.
- The full gate `PATH=.venv/bin:$PATH scripts/ci.sh` passed in 245.8s. Unlike v37.0, the gate ran here in full.

**Decision: v37.0 §513 is applied in all three implementations, with the guard that a computed target containing no hole, or reporting no stated destination, excludes nothing. LOCKED.**

---

## PART CCIII — THE REQUEST-KIND QUESTION, UNTANGLED

§528. **Where it came from.** Koncord's content rule list types each exception with a request type. A Planes `ask` has none: `grammar/vocabulary.json` lists it as `{"kind": "ask", "boundary": "network", "note": "request-with-response"}`, and Swift's `HostEffect` holds only kind, target and site (Koncord v1.10 §271.1). The Koncord session reports that its runtime default is being changed to allow-by-default in its v1.12, which would remove its need for a type from Planes. UNVERIFIED here: v1.12 was not written when this was.

§529. **Browser request kinds are refused as effect kinds.** Fetch, image, script, stylesheet, font and media describe what a *browser* does with a response. Planes is a general-purpose language, and its effect surface answers what a program can do to the outside world, for any program on any host. Adding one host's taxonomy to the closed vocabulary would make the vocabulary about that host. A host that needs such a type supplies it itself, as Koncord did.

§530. **The test an addition must pass, from Planes' own history.** The effect vocabulary has grown once, from four kinds (`ask`, `read`, `write`, `show`) to seven (adding `clock`, `random`, `env`), in the FFI session of July 23, 2026. Those three were added because a host function reading the time, entropy or the environment would otherwise have been an invisible hole. The principle recorded then was: *"An effect surface with an invisible hole is worth less than one that reports the hole."* The source is that session's report, as captured in the vault's `Deepseek Chat about the Planes README.md`. And the vocabulary is closed on purpose (`vocabulary.json`): *"an open vocabulary cannot be searched or diffed across packages."* `test_foreign.py:369` `test_effect_vocabulary_stays_closed` pins the set. So an addition must:
1. separate two things a reader of the surface needs to tell apart;
2. not already be answered by the surface or by derivation;
3. hold for any program, not one host.

Browser kinds fail 1 and 3.

§531. **The gap it named: the network has no `write`.** The file boundary has both `read` and `write`. The network boundary has only `ask`.
- **A native `ask` cannot send.** `host.py` `Host.ask(self, url)`: *"A request expecting a response. Returns the body as text."* `interp.py` passes only the url to `self.host.ask(url)`. There is no request body in the language.
- **A host that sends declares it as `ask`.** `README.md`'s own foreign example is `foreign send of x from "m.post" doing ask "https://api.example.com"`: a POST, labelled as a get.
- **The rules example forbids a send spelled as an ask.** `README.md`: `rule [readings-stay-local] anything may not ask to "https://metrics.internal/ingest"`.
- **What is already visible.** Data carried in a URL is traced by derivation (v37.0 §520, `derived from: pkg-name`).
- **What is not.** Data carried in a request body. It cannot be written natively, and through a foreign function it reads as an ask.

The question "does this program send my data anywhere" is probably the most important one an effect surface answers. It passes all three tests in §530, though it passes test 2 only in part (§531's URL case).

---

## PART CCIV — THE DECISION, AND WHAT A BUILD MUST SETTLE

§532. **The architect's decision.** Told the above, the architect: *"that sounds like worth adding later."*

**Decision: a network effect that sends data is accepted in principle as a future addition to Planes' closed effect vocabulary, to be designed and built at a Planes build session. Browser request kinds (fetch, image, script, stylesheet, font, media) are not effect kinds. Until that build, the vocabulary stays at seven. LOCKED.**

§533. **What the build must settle (P-Q25).**
- **Its name.** `send` is the obvious word, and `send` is already a name programs use: `foreign send of x` in `demo/fdiff/` and the README, and `to send of payload` across the rules and shapes tests. A program may define a function named like a builtin (`to ask of x:` parses), so whether an effect kind named `send` shadows, is shadowed by, or refuses those definitions is part of the design.
- **What it carries, and the host method.** Whether it is a new host method alongside `ask`, or `ask` gaining a body. The README's host table is seven methods, and every method must have a live caller.
- **Where ask ends and send begins.** A GET can leak data through its query string, and a POST can be a plain lookup, like search or GraphQL. The kind describes how a request carries data, so derivation still matters beside it.
- **Existing claims.** Foreign declarations that send while declaring `doing ask`, and whether a surface diff should report them when they are corrected.
- **Rules.** `may not send to "..."` beside `may not ask`, and how it composes with P-Q17's target matching.
- **What pins seven today** (verified by `git grep` at `971961c`):
  - `test_foreign.py` `test_effect_vocabulary_stays_closed`;
  - `js/test/garden_gate.test.mjs` "H: the counts are where they were — 32 keywords, 13 builtins, 7 effect kinds";
  - `README.md` (contents table and "7 effect kinds");
  - `core_check.py` ("all seven effect kinds are used");
  - `corpus_coverage.py`.
- **Every implementation.** `grammar/vocabulary.json`, Python, JavaScript, the self-hosted `grammar/interp.planes`, and Swift, including `HostRules.swift`'s `HostEffect`.

**Recorded.**

---

## WHAT IS LOCKED

- **v37.0 §513 applied** (§526), in `rules.py`, `js/rules.mjs` and `Rules.swift`, with the guard that a computed target containing no hole, or reporting no stated destination, excludes nothing. Merged as PR #104, `971961c`.
- **A network send effect is accepted in principle** for a later build (§532).
- **Browser request kinds are not effect kinds** (§529, §532).
- **The vocabulary stays at seven** until that build (§532).

## WHAT IS NOT LOCKED

- **Everything about the send effect's design** (§533, P-Q25).
- **P-Q17**, rule-target matching semantics, is unchanged from v37.0.

## WHAT IS LOGGED

- **v37.0's register reused a number.** It named rule-target matching P-Q17, but P-Q17 was already *"Fingerprints optional or mandatory"* (planes_checkpoint_v3_0, parked, rule plane). This document refers to the v37.0 question as "P-Q17 (v37.0, rule-target matching)" and does not renumber it, because archival documents are not edited. The new question takes **P-Q25**, the next unused number. Verified by `grep` of every `planes_*.md` in the vault's Planes folder and `git grep` of the repo: the highest in use is P-Q24.
- **v37.0's MCP demonstration is not in the repo.** Verified: no `demo/mcp/` at `971961c`. The artifact was in v37.0's outputs and was not available to this session.
- **v37.0's flag about `cut-cost-verification.md` did not reproduce.** Three full gate runs this session left the file unmodified (`git status` clean apart from intended changes).
- **The Planes repo moved since v37.0 without a record on this chain.** PR #100 lifted CPython's int-string digit limit. PR #101 made the JavaScript host read non-ASCII text as Python does. PR #102 added the Swift port, recorded on the Koncord axis at v1.10 §272. PR #103, merged today at `621decc`, brought the JavaScript host into agreement with Python where the Swift port found it did not: Unicode case and NFC at Python's version, text-mode file reads, and the effect-surface CLI's globbing. Listed here so the next session does not look for them in an earlier checkpoint.

---

## UPDATED OPEN QUESTIONS (v37.1 status)

Prior count: **seventeen** (v37.0).

| # | Question | Status |
|---|---|---|
| 1–16 | Carried from v36.0: game, engine and teaching register | Open — unchanged |
| P-Q17 (v37.0) | Should rule-target matching move from exact-string to host/path-prefix semantics? | Open — unchanged |
| **P-Q25** | How is a network effect that sends data designed: its name, what it carries and the host method, where ask ends and send begins, existing `doing ask` claims, rule syntax, and the seven-kind pins? | **New** — §533, for a Planes build session |

New count: **eighteen.** No question resolved.

---

## DOCUMENTS PRODUCED THIS SESSION

| Document | Type | Status |
|---|---|---|
| `docs/planes_addendum_v37_1_network_send.md` (this document) | Thread closure addendum | Complete, LOCKED |
| PR #103, `621decc` | JavaScript host agreement with Python | Merged |
| PR #104, `971961c` | v37.0 §513 rule-checker fix, three implementations | Merged |

---

## RESUME PROMPT (v37.1)

*We are resuming in the Planes domain from addendum v37.1 — network_send (September 13, 2026), kept in the repo at `docs/planes_addendum_v37_1_network_send.md`, extending checkpoint v37.0 — rule_target_matching (August 24, 2026, vault). All prior decisions in force; nothing retracted. Part/§ continues from Part CCIV / §533. HEAD is the commit that added this document, on top of `971961c`.*

*WHAT v37.1 LOCKED. (1) v37.0 §513 is applied, merged as PR #104 `971961c`. `_pattern_excludes` in `rules.py`, `patternExcludes` in `js/rules.mjs`, and `patternExcludes` in `swift/Sources/Planes/Rules.swift` make a computed target whose known `{...}`-pattern chunks cannot reach a rule's target a certain non-match. The guard: a computed target with no hole, or a foreign's `<host function> (destination not stated)`, excludes nothing. The agreement suites and the unit tests cover every branch, and the full gate passed. (2) A network effect that sends data is accepted in principle for a later build. Files have read and write; the network has only `ask`, whose host method takes a url and returns a body, so a program cannot send natively, and a host function that POSTs declares `doing ask`. (3) Browser request kinds (fetch, image, script, stylesheet, font, media) are not effect kinds: they are a host's taxonomy, and Koncord supplies its own. (4) The vocabulary stays at seven until the send effect is built.*

*THE TEST AN ADDITION PASSES (v37.1 §530, from the July 23, 2026 FFI session that grew the vocabulary from four to seven): it separates two things a reader of the surface needs to tell apart; it is not already answered by the surface or by derivation; and it holds for any program, not one host.*

*OPEN FOR A BUILD SESSION: P-Q25, the send effect's design. Its name (`send` is already a name in `demo/fdiff/`, the README and the tests), whether it is a new host method or a body on `ask`, where ask ends and send begins (GET query leaks, POST lookups), existing `doing ask` claims, `may not send` rules and their composition with P-Q17, and the seven-kind pins (`test_foreign.py` `test_effect_vocabulary_stays_closed`, `js/test/garden_gate.test.mjs` count test H, README counts, `core_check.py`, `corpus_coverage.py`) across `grammar/vocabulary.json`, Python, JavaScript, `grammar/interp.planes` and Swift including `HostRules`' `HostEffect`. P-Q17 (v37.0, rule-target matching) is also open and unchanged. v37.0 reused the number P-Q17, which was v3.0's fingerprints question; v37.1 did not renumber it and numbered its own question P-Q25, the next unused. Open-question count is eighteen.*

*LOGGED: v37.0's `demo/mcp/` artifact is not in the repo (verified at `971961c`). v37.0's `cut-cost-verification.md` flag did not reproduce. PRs #100–#103 (digit limit, JS non-ASCII, the Swift port, JS–Python agreement) landed after v37.0 and are listed at v37.1 LOGGED. Standing terms in force: three implementations must agree; soundness (never hide a real reach) is non-negotiable; absence claims carry verification markers; check the code and the chain for an existing answer before asking the architect.*

---

*A browser needed a word Planes did not have. The word it asked for belonged to the browser. The word Planes was missing was a different one — the network's `write` — and it had been missing since the vocabulary closed.*
