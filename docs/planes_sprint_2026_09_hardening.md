# Planes — hardening, fixing and additive sprint (September 2026)

**Date:** September 13, 2026
**Base:** `main` at `c4400ad` (addendum v37.1)
**Inputs:** every Planes checkpoint and addendum from v37.1 back to the `unbound` inception (vault, plus `docs/`); the Horizon design docs; the DeepSeek brainstorm transcripts; `reports/`; PRs #100–#104; the playtest, persona and crosswalk documents; and every portfolio document that uses Planes (5xFive, Koncord in `~/browser-concordance/checkpoints/`, Omniglot, Cartouche, CueCue, Undertow, Cutter, Motif, MuseSky, TAOS).
**Companion:** [`ROADMAP.md`](../ROADMAP.md) holds everything past this sprint.

Every item below says where it came from. **Verified** means it was run or read at `c4400ad` in this session. **Reported** means a source document or a reading pass says so and it was not re-run here.

The sprint has two halves. **Sprint A** changes no language semantics: fixes, agreement, gates, docs, embedding. It can start now. **Sprint B** is the language work the portfolio surfaced: the eighth effect kind and the rule-plane changes. Track 0 held the decisions Sprint B needed. The architect answered all of them in a walkthrough on September 13, 2026, and they are recorded below.

---

## Track 0 — decided (walkthrough, September 13, 2026)

Each answer closes its question. None is carried forward.

| # | Question | Decision | Closes |
|---|---|---|---|
| 1 | What is the error-message catalogue for? | `grammar/errors.json` is a generated reference copy and stays as it is. Messages are written in each host's code, and the agreement suites keep every host saying the same words. | A-Q20 |
| 2 | When one error is raised for several reasons, does each get its own advice? | Yes. Every raise site gives a fix clause true for that exact case, which is already how the code works. The one leftover, `interp.py:97`'s `nothing` clause that still lists cases inside itself, is routine cleanup (F7). | A-Q21 |
| 3 | Must `supersedes` carry the fingerprint of the rule it overrides? | **Yes, required.** Without it the checker refuses the rule and prints the fingerprint to add. No portfolio rule file uses `supersedes` today (*verified* in `~/5xfive/worker` and `~/browser-concordance`). Only `demo/rules/exception.planes` and tests need it. | The original P-Q17 (v2.0 §36) |
| 4 | Should rules expire on a date (`until`)? | **No.** The v5.0 §76 lock on `until` is withdrawn. No program or portfolio project needs it, so a real need later starts as a new idea. | F-Q2 |
| 5 | Should Planes let an author declare that two rules must never both apply (`contradicts`)? | **Yes, build it** (B3). It records an incompatibility in meaning that structural conflict detection can't see. 5xFive runs Z3 separately for consistency across compliance sources, and this catches part of what Z3 is used for. | F-Q1 |
| 6 | Does a rule about an address cover only that exact address? | **No.** A rule's target covers that address and everything under it (B2). | P-Q17 (v37.0); Koncord PE-Q42 |
| 7 | Is `send` a language command or an effect label? | **An effect label for `foreign` functions**, the way `clock` works. No native send command, no new keyword, no new host method. The effect vocabulary grows from seven to eight. `send` stays usable as a function name. | P-Q25 (name, host method) |
| 8 | Where does `ask` end and `send` begin? | **The author of the foreign declaration chooses, by one rule:** a request that carries the program's data out (a message, form, upload or report) is `send`; one that only fetches is `ask`. Planes doesn't guess from HTTP methods. Data inside a URL is still traced by derivation (v37.0 §520). | P-Q25 (boundary) |
| 9 | What happens to existing sends labelled `doing ask`? | **Relabel them** in the build (`README.md:548`, `demo/fdiff/v1.planes`, `demo/fdiff/v2.planes`). `--diff` reports an `ask` → `send` change as a change, even when the code is otherwise unchanged. | P-Q25 (existing claims) |
| 10 | Does a rule about `ask` also govern `send`? | **Forbidding `ask` to an address also forbids `send` to it.** Forbidding `send` does not forbid `ask`. Allowing `ask` does not allow `send`. No rule written before `send` ever weakens. | P-Q25 (rules) |
| 11 | Does `send` conflict with Horizon's "no eighth effect"? | **No.** Horizon §9.2 limited how world data is carried (it crosses `show`) during the Phase 0 build. It is not a limit on the language. World data keeps using `show`. | P-Q25 (Horizon) |
| 12 | Four false lines in `tutor.html` | **Approved replacements** (F4). The architect also ruled the decorative seed a **bug**. Sharing a seed was meant to be the point (v24.0 §316, v27.0 §81), and no build or audit flagged it. Filed as [issue #106](https://github.com/rmichaelthomas/planes/issues/106), no rush. | — |

---

## The rest of the register — decided (walkthrough, September 13, 2026)

The architect answered the sixteen questions left after Track 0 in the same session. **The open register is empty.**

| # | Question | Decision | Closes |
|---|---|---|---|
| 13 | Where does the interactive surface live? | The GitHub Pages site, `rmichaelthomas.github.io/planes`. Prosecode.org is no longer the planned home. | A-Q5 |
| 14 | Rename the `shapes` tool? | No. `shapes` stays the command's name; the feature is always "the effect surface" in writing. | A-Q10 |
| 15 | Private functions? | No. Every function a module defines stays visible. A name clash is fixed by renaming at the point of use, which F8 makes correct. | A-Q6c |
| 16 | Versions in the language? | No. `use` names a file. Versions come from tagged releases, and `--diff` shows what changed between two. | A-Q6a |
| 17 | How is Planes distributed? | Tagged GitHub releases only: Swift through SwiftPM at a tag (E3), JS by copying `js/` at a tag (E2), Python by checkout at a tag. No PyPI or npm. | A-Q7 |
| 18 | What does a registry publish? | There is no registry. `--json` and `--diff` publish and compare a surface wherever the code lives. | A-Q8 |
| 19 | A public cross-host determinism claim? | Yes, after H6's four-way `sine` agreement test passes: the same numbers on every machine and in every implementation. | A-Q24 |
| 20 | D1's first artifact? | Neither a reference model nor a trig table. No determinism-market work. | A-Q25 |
| 21 | The benchmark set? | H7: four ordinary jobs in Planes, Python and JS, plus effect-surface time over the corpus with its foreign fraction, published in the README. | A-Q1 |
| 22 | What the measurement layer needs? | Nothing. It belonged to a model-narrated tutor that is not being built. | A-Q13 |
| 23 | The wedge: analyse other languages? | No. Planes analyses Planes programs only; other languages are Cutter's job. | A-Q11 |
| 24 | Foreign target portability? | The eight `sharedTargets()` names are the portable set, supported by every host that runs programs. Any other name works only where a host provides it. | A-Q17 |
| 25 | What is a lesson? | One entry in `tutor.html`'s lesson list. | T-Q4 |
| 26 | "Approximate": feature or caution? | Information, not a warning. | T-Q5 |
| 27 | Answer key, and the record plane? | The worked example is the answer, shown openly; not a record-plane artifact. | T-Q6 |
| 28 | Starter vocabulary; what the picker writes? | Garden words ship in the key. The learner writes their `because` reason and sky name. The picker writes `custom-sky of` and numbers, never the learner's words. | T-Q7 |

Found while verifying these: F8 below ([issue #108](https://github.com/rmichaelthomas/planes/issues/108)).

For the next checkpoint's register (bookkeeping only):
- P-Q17 has been used three times: v2.0 §36 fingerprints, v14.0 §159 host seam, v37.0 rule-target matching.
- P-Q16 and P-Q23 have each been used twice.
- The P-Q20–P-Q23 closures live only in `reports/REPORT_AUDIT.md`.
- The v23.0-to-v30.1 count carried two offsetting errors: v25.1 decremented A-Q2, which was never counted, and v30.1 re-resolved A-Q23, already closed at v24.0 §309. Separately, A-Q20 and A-Q21 were dropped from the list from v30.1 onward.

---

## Sprint A — fix and harden (no semantics change)

Order within Sprint A is by risk: wrong answers first, then agreement, then consumers, then docs. Each item names its gate.

### Fixes: the language gave a wrong or unstable answer

**F1. The reference reports a repeated destination at a line chosen by the hash seed.** *Verified* in `test_swift_host_rules.py:177–206`. `shapes.py` keeps top-level effects in a Python `set` sorted by `(boundary, kind, target)`, so when two sites tie, `PYTHONHASHSEED` decides which line a violation names. JS and Swift report the first site. The test accepts either Python answer instead of pinning one.
- Fix: order ties by site in `shapes.py`, keeping the first, the way `EffectSet` already does in JS.
- Gate: the test asserts one answer across eight seeds, and `test_js_rules.py` and `test_swift_rules.py` agree.
- Source: PR #102 "Found and still open".

**F2. `text of` on a list returns a placeholder.** *Verified:* `show text of [1, 2, 3]` prints `[3 items]`. Code that follows the error message's advice to use `text of` gets that placeholder, silently.
- Fix: make it the repr that shapes already uses for a known list (PR #103 made JS match Python here), or refuse it with a fix clause. Either one closes the wrong answer; either way the output must change identically in every host.
- Source: v22.2 §286.

**F3. A reserved-word error names a function that doesn't exist.** *Verified:* `to dawn and dusk:` reports "cannot appear in the function name 'dawn and'", then dumps all 32 reserved words.
- Fix: quote the whole name as written. Make the message byte-identical across Python, JS, `grammar/interp.planes` and Swift's parser.
- Teaching needs this too: the tutor passes these names straight to the engine (`tutor.html:860` blocks only `of`).
- Source: tutor reading pass (D).

**F4. Tutor claims that are false.** *Verified* at `c4400ad`:
- `tutor.html:504`: "the same seed always grows the exact same one". The seed ticket is "decorative… never fed back into the program" (`tutor.html:1023`).
- `tutor.html:797`: lesson 7 says "Your garden is already grown, from everything you built in the lessons before this one". Lesson 7's garden is fixed frame data (`tutor.html:800–808`). The learner's lesson 4 reason and lesson 6 sky name are not carried in.
- The capstone completion string "the garden you grew across the lessons" is flagged AUTHOR-DRAFTED in `tutor-refinements-verification.md`.

Fix, approved at Track 0 #12:
1. Share card: "Your garden is a tiny file. Give a friend the file, and the **exact same** garden grows on their computer."
2. Under the save button: "Trade garden files with anyone else growing a garden — the same file always grows the exact same one."
3. Lesson 7 introduction: "Here's a garden grown from everything you've learned — every line in it is one you now know how to write. This is your sandbox now…" (the rest unchanged)
4. Lesson 7 completion (`tutor.html:1202`): "Every line in this garden is one you learned to write — now it's yours to change."

The six-digit seed stays as a keepsake on the certificate, and no copy claims it does anything. Making the seed real is a bug, not this fix: [issue #106](https://github.com/rmichaelthomas/planes/issues/106).

Gate: `js/test/tutor_redesign.test.mjs` asserts the four old phrases never appear.

**F5. `trim()` in the three JS protocol parsers was never audited.** *Verified present:*
- `js/paint/protocol.mjs:194, 257`
- `js/sound/protocol.mjs:88`
- `js/scene/ir.mjs:42`

PR #101 replaced `trim()` with Python's whitespace set in the lexer, and listed these three as "not audited".
- Fix: decide whether each protocol follows Python's `isspace` rules, then either switch them or pin the difference with a test.
- Source: PR #101.

**F6. A JS `RecordEntry` can't cross a structured-clone boundary.** *Reported:* 5xFive v2.9 §243 had to sanitize it before a Cloudflare Workflow `step.do()`; until it did, every automation failed.
- Fix: give records a plain-data form (`toJSON` or a documented `toPlain`), with a round-trip test through `structuredClone`.
- Verify first: *not re-run here.*

**F8. Renaming a module's function on import makes that module call the other module's function.** *Verified* in Python and JS ([issue #108](https://github.com/rmichaelthomas/planes/issues/108)). With `use a` and `use b with helper as b-helper`, b's own calls to `helper` run a's, silently. In the reproduction that means a wrong value, and a network request b never made. `interp.py:1126–1150` hoists every module into one flat env, and `js/run_file.mjs` ports the same structure.
- Fix: a module's calls resolve to its own definitions first, in Python, JS and `grammar/interp.planes`.
- Gate: agreement tests over the issue's two reproductions, and a test that the effect surface and the run agree on them.
- Why now: Track 0's no-private-functions answer (#15) relies on renaming working.

**F7. The `nothing` comparison's fix clause still lists cases inside itself.** `interp.py:97` reads "test for absence with `is nothing` — if the nothing is inside a compared list or record rather than the whole value (the path names which)…". Track 0 #2 settled that each raise site's advice is true for its exact case. Split it so the whole-value and inner-value cases each raise with their own clause, byte-identical in every host.

### Hardening: agreement, gates and completeness

**H1. `--rules` results in `--json`.** *Verified:* `shapes_cli.py:21–23` says "--rules does not yet appear in --json's output — a --json consumer cannot see rule results at all today."
- A-Q8 names this as the registry's one missing field group. Every JSON consumer (5xFive, Undertow, Omniglot, Cartouche) wants it.
- Build in Python, JS and Swift. Bump the JSON format version only if an existing field changes.

**H2. The audit tool learns rule-plane relations.** `audit_locked_vs_built.py` checks constructs, not rule-plane relations. That is why `until` and `contradicts` went unflagged from v5.0 to Track 0.
- Extend it to `supersedes`, `permit`, `contradicts` and mandatory fingerprints.
- `contradicts` reports NOT BUILT until B3 lands. That is the point.
- `until` is withdrawn (Track 0 #4) and must not appear as a locked construct.

**H3. Commit the v37.0 MCP demo.** *Verified absent:* there is no `demo/mcp/` at `c4400ad`. v37.0 §518–§521 logged it as the first agent-tool artifact written in Planes, and its strongest adoption asset (the `derived from: pkg-name` trace).
- Rebuild `demo/mcp/v1.planes` and `demo/mcp/v2.planes` plus the JSON surface.
- Gate: a test that `--diff` v1→v2 exits 1 and `--rules` flags the telemetry host. After #104, the registry host must not be flagged.

**H4. Measure `HostRules` cost.** Koncord v1.10 §272.4 records the per-page rule-check cost as unmeasured.
- Add a Swift benchmark over a realistic rules file (`demo/rules/exception.planes` scaled up) and a page's worth of asks.
- Record p50/p95 the way `world_kernel_bench.py` does.

**H5. Stale statements in live files.**
- `identity/render_logo.py` still says "rough marker, not locked" and has no Typography section (v16.0 §176, reported).
- `README.md`'s foreign example spells a POST as `doing ask` (v37.1 §531). It is relabelled `doing send` in B1 (Track 0 #9), not here.
- Not included: `reports/CORE_SUBSET.md`'s stale "half the keywords" (v18.0 §206). It lives in `reports/`, which is archival.

**H6. Four-way `sine` agreement, then the determinism claim.** No suite was found that compares `sine` digit for digit across hosts. Each tests its own (e.g. `js/test/exactness.test.mjs`).
- The gap has bitten once. `test_world_kernel_conformance.py`'s docstring records Python and JS `sine` results disagreeing "in a low decimal digit" during the kernel spike. The fixture now rounds before comparing, so that suite no longer detects a `sine` difference.
- *Spot check, September 13:* `sine_degrees` in Python and `sineDegrees` in JS return identical exact fractions for 27 angles (integers, negatives, fractions, `360000030`). This is not a substitute for the suite.
- Add an agreement test sweeping many angles (including large, negative and quarter-turn ones) through Python, JS, `grammar/interp.planes` and Swift's `PlanesNumber`.
- Once it passes, add one README sentence: Planes computes the same numbers on every machine and in every implementation (#19).

**H7. The published benchmarks** (#21). Add a README Performance section, measured once on the architect's Mac with the machine named.
- **Set A:** word count, record updates, invoice arithmetic and a file transform, each written in Planes, Python and JS. Unflattering results are published.
- **Set B:** effect-surface time across the 51 corpus programs, stating the fraction that crosses a foreign boundary.

### Consumers: make Planes easy to embed and to pin

These came from the portfolio. 5xFive and Koncord both rebuilt pieces rather than depend on Planes cleanly, and Undertow and CueCue re-implemented the format.

**E1. Publish the surface format.** Write `docs/surface-format-v1.md`: the `shapes_cli --json` format 1, the effect-kind vocabulary, and the `{...}` hole convention.
- Add a JSON Schema under `grammar/protocols/` and a test that Python, JS and Swift output validates against it.
- Five projects copy this format by hand (Undertow, Cutter, Omniglot, Koncord `HostEffect`, 5xFive). Cutter has already drifted: it added `process` and `tool` kinds.
- Say plainly that a copy which adds kinds is no longer Planes' vocabulary.

**E2. A JS embedding entry point.** Add `js/embed.mjs`, which loads grammar data from a generated module (the way Swift embeds `GrammarData.swift`) so no caller hits `GrammarDataError: vocabulary not loaded`. Add hand-written `.d.ts` types for `parse`, `analyse`, `check` and `Interpreter`.
- 5xFive's `VENDOR.md` calls grammar loading "not optional" and says four review rounds missed it.
- *Verified:* no `.d.ts` or `.d.mts` in `js/`.

**E3. A root `Package.swift`.** SwiftPM resolves a remote package only from a manifest at the repository root (Koncord v1.12 build prompt §2). Today there is only `swift/Package.swift`.
- Add a root manifest pointing at `swift/Sources`. Keep `swift/` building.
- Consider `.iOS(.v17)` beside `.macOS(.v14)` if nothing in the port is macOS-only. Check before claiming.

**E4. A non-Python checker for manifest authors.** Document one command that parses and analyses a `.planes` file without Python (`node js/cli.mjs …` or `planes-swift …`).
- CueCue writes a "Planes declaration" that doesn't parse. *Reported, and confirmed by the reading pass:* `syntax error — line 1: expected from`. Nothing outside Python ever checked it.

**E5. Downstream pin refresh (outside this repo; listed so it isn't lost).**
- 5xFive vendors `1d8a833` (*verified*, `~/5xfive/worker/lib/planes/VENDOR.md`). It predates #100–#104, including the computed-target fix behind 5xFive v3.2 §267's false "can't rule it out" warning.
- Koncord's checkpoints verified Swift Planes at `9ec3cfa`, before #104's `patternExcludes`.
- Once E2 and E3 land, both should move to the Sprint A tag.

### Sprint A gate

`PATH=.venv/bin:$PATH scripts/ci.sh` green in full. Don't rely on a truncated run: `set -e` stops at the first failure.

Every agreement suite (JS and Swift) must cover each fixed branch. Tag the result so downstream projects can pin a named commit instead of a bare SHA.

---

## Sprint B — additive, decided at Track 0

**B1. The send effect (P-Q25).** Specified by Track 0 #7–#11:
- `send` is an **effect kind that `foreign` declarations use**: `foreign post of message from "slack.post" doing send "https://hooks.slack.com/…"`.
  - No keyword, no builtin, no host method.
  - The vocabulary is `ask clock env random read send show write`.
  - `send` is on the network boundary with `ask`. Its note: a request that carries the program's data out.
- **Documentation states the one rule:** data going out is `send`; fetch-only is `ask`. Nothing checks beyond the declared label, the same trust every `doing` claim has.
- **Relabel** `README.md:548`, `demo/fdiff/v1.planes` and `demo/fdiff/v2.planes` to `doing send`.
- **`--diff` reports a kind change** (`ask` → `send` on the same destination) as a change, exit 1.
- **Rules:**
  - `may not ask to X` forbids both `ask` and `send` to X.
  - `may not send to X` forbids only `send`.
  - `may ask to X` permits only `ask`.
  - `may send to X` permits `send`.
  - A test pins that every rule written before `send` flags at least what it flagged before.
- **Horizon:** world data keeps crossing `show`. Horizon §9.2 was a Phase 0 build limit.
- **Build across:**
  - `grammar/vocabulary.json`, `shapes.py`, `rules.py`, `interp.py`'s `doing` validation
  - `js/`, `grammar/*.planes`, Swift (including `HostRules`' `HostEffect`)
  - E1's schema
  - the five pins: `test_foreign.py` `test_effect_vocabulary_stays_closed`, `js/test/garden_gate.test.mjs` H, README counts, `core_check.py`, `corpus_coverage.py`
- **Gate:** v37.1 §530's three-part test is recorded in the PR, and the agreement suites cover each rule direction above.

**B2. Rule-target matching (P-Q17 v37.0).** Specified by Track 0 #6, built with B1 so `ask` and `send` match the same way.
- A rule target covers that address **and everything under it**:
  - the same scheme and host;
  - the path matches at `/` boundaries, so `/ingest` covers `/ingest/v2` but not `/ingestion`;
  - a query string or fragment on the effect's target is ignored.
- A different host is never covered (`tracker.example.evil.com` is not `tracker.example`). Subdomains are separate addresses.
- It applies to forbid and permit rules alike.
- #104's `_pattern_excludes` is re-proven against the new semantics: a computed target is excluded only when its known chunks cannot reach any address under the rule's target. The v37.0 §514 argument stands: never hide a real reach.
- Settles Koncord PE-Q42 and removes 5xFive's `{...}` wildcard workaround in `compliance-compiler.ts`.

**B3. `contradicts`, and mandatory fingerprints.**
- `contradicts` (Track 0 #5): an authored declaration that two rules must never both apply, reported when both are active. Distinct from structural conflict detection (v5.0 §76).
- Fingerprints (Track 0 #3): `supersedes [name]` without `@fingerprint` is refused, and the message prints the fingerprint to add. Update `demo/rules/exception.planes` and the tests.
- H2's audit flips `contradicts` and fingerprints to BUILT.
- `until` is not built (Track 0 #4).

**B4. Readable violations.** Keep a rule's `because` and the violation parts as structured fields in the JSON (after H1), so hosts can write their own wording without parsing the rendered text.
- 5xFive v3.2 §267 translates `v.render()` output, MuseSky MOD-2 wants amber without jargon, and Koncord keeps Planes backstage.
- Small, and it removes three downstream parsers.

---

## Not in this sprint, on purpose

These are real, and in [`ROADMAP.md`](../ROADMAP.md):
- the Swift interpreter
- a beneficiary field on rules (TAOS OL-Q1; four projects)
- Horizon Phase 2's art pass and school-hardware gates
- the tutor's phone and touch pass and adult variant
- collection builtins
- dynamic record lookup
- surface-to-receipt wiring

Reason: each one needs a design or an external input (hardware, learners, an architect ruling) that a hardening sprint shouldn't stand in for.
