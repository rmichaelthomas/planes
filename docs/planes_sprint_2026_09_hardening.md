# Planes — hardening, fixing and additive sprint (September 2026)

**Date:** September 13, 2026
**Base:** `main` at `c4400ad` (addendum v37.1)
**Inputs:** every Planes checkpoint and addendum from v37.1 back to the `unbound` inception (vault, plus `docs/`); the Horizon design docs; the DeepSeek brainstorm transcripts; `reports/`; PRs #100–#104; the playtest, persona and crosswalk documents; and every portfolio document that uses Planes (5xFive, Koncord in `~/browser-concordance/checkpoints/`, Omniglot, Cartouche, CueCue, Undertow, Cutter, Motif, MuseSky, TAOS).
**Companion:** [`ROADMAP.md`](../ROADMAP.md) holds everything past this sprint.

Every item below says where it came from. **Verified** means it was run or read at `c4400ad` in this session. **Reported** means a source document or a reading pass says so and it was not re-run here.

The sprint has two halves. **Sprint A** changes no language semantics: fixes, agreement, gates, docs, embedding. It can start now. **Sprint B** is the language work the portfolio surfaced — the eighth effect kind and the rule-plane changes — and it starts with decisions only the architect can make. Track 0 lists those decisions. Most of them block only Sprint B.

---

## Track 0 — decisions for the architect

Nothing in Sprint A waits on these, except D6's copy.

| # | Decision | Why now | Source |
|---|---|---|---|
| D1 | **P-Q25: the send effect.** Its name (`send` is already a function name in `demo/fdiff/`, the README and tests), a new host method or a body on `ask`, where `ask` ends and `send` begins, what happens to existing `doing ask` claims, `may not send` rules, and how the five seven-kind pins move. Also: Horizon Phase 0 says world programs use "no eighth effect". Say whether that holds for world programs or was a Phase-0-only constraint. | Filed today. Five downstream copies of the vocabulary would need to change with it. | v37.1 §531–§533; Horizon Phase 0 constraints |
| D2 | **P-Q17 (v37.0): rule-target matching.** Exact string, host, or path prefix, and the syntax for it (`under`? trailing slash?). | Koncord (PE-Q42) and 5xFive (`compliance-compiler.ts` writes a `{...}` hole into a rule target as a wildcard) both need a rule that covers `…/pixel.gif`. | v37.0 §522–§524; Koncord v1.12 §282 |
| D3 | **`until` and `contradicts`.** Locked at v5.0 §76, never built. Build them in Sprint B, or retire the lock in a checkpoint. | A locked construct with no code breaks the "locked means built" rule. Nothing flags it: `audit_locked_vs_built.py` doesn't look at rule-plane relations. *Verified absent:* no syntax in `.py`, `.mjs`, `.swift` or `grammar/*.json`. | v5.0 §76 (F-Q1, F-Q2) |
| D4 | **Supersession fingerprints: optional or mandatory.** "Absence is unverified supersession." Still optional in `parser.py:493–494`. | This is the original P-Q17 (v2.0 §36). It was parked with the rule plane and never came back. Deciding it now fits alongside D2 and D3. | v2.0 §36, v3.0 §53 |
| D5 | **Restore A-Q20 and A-Q21 to the register.** A-Q20: what the error catalogue is for, and where it lives. A-Q21: split a raise site reached by several intents, so each fix clause is always true. | *Verified:* both are carried open at v23.0, then disappear from every later register without being resolved. The true open count is **twenty**, not eighteen. Relevant now because PR #101 and the Swift port made messages a four-host agreement cost. | v22.1 §281, v22.2 §286, v23.0 register |
| D6 | **Tutor copy that says something false.** Approve replacement wording for three strings (see F4). | The teaching proposal relies on the page telling the truth. | Tutor reading pass, verified at `tutor.html` |

Also for the next checkpoint (bookkeeping, not decisions):
- **P-Q17 has been used three times**: v2.0 §36 fingerprints, v14.0 §159 host seam, v37.0 rule-target matching. v37.1 recorded two and gave the first as v3.0.
- **P-Q16 and P-Q23 have each been used twice.**
- The P-Q20–P-Q23 closures live only in `reports/REPORT_AUDIT.md`. The vault chain never records them.

---

## Sprint A — fix and harden (no semantics change)

Order within Sprint A is by risk: wrong answers first, then agreement, then consumers, then docs. Each item names its gate.

### Fixes: the language gave a wrong or unstable answer

**F1. The reference reports a repeated destination at a line chosen by the hash seed.** *Verified* in `test_swift_host_rules.py:177–206`. `shapes.py` keeps top-level effects in a Python `set` sorted by `(boundary, kind, target)`, so when two sites tie, `PYTHONHASHSEED` decides which line a violation names. JS and Swift report the first site. The test accepts either Python answer instead of pinning one.
- Fix: order ties by site in `shapes.py`, keeping the first, the way `EffectSet` already does in JS.
- Gate: the test asserts one answer across eight seeds, and `test_js_rules.py` and `test_swift_rules.py` agree.
- Source: PR #102 "Found and still open".

**F2. `text of` on a list returns a placeholder.** *Verified:* `show text of [1, 2, 3]` prints `[3 items]`. Code that follows the error message's advice to use `text of` gets that placeholder, silently.
- Fix: make it the repr that shapes already uses for a known list (PR #103 made JS match Python here), or refuse it with a fix clause. Either one closes the wrong answer; changing the output needs D5-style care because the message is shared by every host.
- Source: v22.2 §286.

**F3. A reserved-word error names a function that doesn't exist.** *Verified:* `to dawn and dusk:` reports "cannot appear in the function name 'dawn and'", then dumps all 32 reserved words.
- Fix: quote the whole name as written. Make the message byte-identical across Python, JS, `grammar/interp.planes` and Swift's parser.
- Teaching needs this too: the tutor passes these names straight to the engine (`tutor.html:860` blocks only `of`).
- Source: tutor reading pass (D).

**F4. Tutor claims that are false.** *Verified* at `c4400ad`:
- `tutor.html:504`: "the same seed always grows the exact same one". The seed ticket is "decorative… never fed back into the program" (`tutor.html:1023`).
- `tutor.html:797`: lesson 7 says "Your garden is already grown, from everything you built in the lessons before this one". Lesson 7's garden is fixed frame data (`tutor.html:800–808`). The learner's lesson 4 reason and lesson 6 sky name are not carried in.
- The capstone completion string "the garden you grew across the lessons" is flagged AUTHOR-DRAFTED in `tutor-refinements-verification.md`.

Fix: new wording, which needs D6. Gate: `js/test/tutor_redesign.test.mjs` asserts none of those phrases appear.

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

### Hardening: agreement, gates and completeness

**H1. `--rules` results in `--json`.** *Verified:* `shapes_cli.py:21–23` says "--rules does not yet appear in --json's output — a --json consumer cannot see rule results at all today."
- A-Q8 names this as the registry's one missing field group. Every JSON consumer (5xFive, Undertow, Omniglot, Cartouche) wants it.
- Build in Python, JS and Swift. Bump the JSON format version only if an existing field changes.

**H2. The audit tool learns rule-plane relations.** `audit_locked_vs_built.py` checks constructs, not rule-plane relations. That is why D3's `until` and `contradicts` have gone unflagged since v5.0.
- Extend it to `supersedes`, `permit`, `contradicts`, `until` and fingerprints.
- It will report D3's pair as NOT BUILT until D3 is decided. That is the point.

**H3. Commit the v37.0 MCP demo.** *Verified absent:* there is no `demo/mcp/` at `c4400ad`. v37.0 §518–§521 logged it as the first agent-tool artifact written in Planes, and its strongest adoption asset (the `derived from: pkg-name` trace).
- Rebuild `demo/mcp/v1.planes` and `demo/mcp/v2.planes` plus the JSON surface.
- Gate: a test that `--diff` v1→v2 exits 1 and `--rules` flags the telemetry host. After #104, the registry host must not be flagged.

**H4. Measure `HostRules` cost.** Koncord v1.10 §272.4 records the per-page rule-check cost as unmeasured.
- Add a Swift benchmark over a realistic rules file (`demo/rules/exception.planes` scaled up) and a page's worth of asks.
- Record p50/p95 the way `world_kernel_bench.py` does.

**H5. Stale statements in live files.**
- `identity/render_logo.py` still says "rough marker, not locked" and has no Typography section (v16.0 §176, reported).
- `README.md`'s foreign example spells a POST as `doing ask` (v37.1 §531). Leave the example as it is until D1, but footnote it.
- Not included: `reports/CORE_SUBSET.md`'s stale "half the keywords" (v18.0 §206). It lives in `reports/`, which is archival.

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

## Sprint B — additive, after Track 0

**B1. The send effect (P-Q25), designed then built.** Design session first (D1). Then build it across:
- `grammar/vocabulary.json`, `interp.py`, `host.py`, `shapes.py`, `rules.py`
- `js/`, `grammar/interp.planes`, and Swift (including `HostRules`' `HostEffect`)
- the five pins: `test_foreign.py` `test_effect_vocabulary_stays_closed`, `js/test/garden_gate.test.mjs` H, README counts, `core_check.py`, `corpus_coverage.py`
- E1's schema

Gate: v37.1 §530's three-part test, written into the design doc before the build.

**B2. Rule-target matching (P-Q17 v37.0), as D2 decides it.** Build after B1 so `may not send to` and `may not ask to` get the same matching semantics in one pass. It composes with #104's `_pattern_excludes`, whose soundness argument (v37.0 §514) has to be re-proven for prefix semantics.

**B3. `until` and `contradicts` (if D3 keeps them), plus fingerprints (D4).** `until` takes an explicit `--as-of` and never reads the clock. An expired rule is a fifth Violation shape. H2's audit flips to BUILT.

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
- module versioning and private functions
- the registry
- surface-to-receipt wiring

Reason: each one needs a design or an external input (hardware, learners, an architect ruling) that a hardening sprint shouldn't stand in for.
