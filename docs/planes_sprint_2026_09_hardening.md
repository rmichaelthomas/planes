# Planes — hardening, fixing and additive sprint (September 2026)

**Date:** September 13, 2026
**Status:** Sprint A built and merged the same day (PRs #111–#132), tagged `sprint-a-2026-09` at `01be2c0`, and both downstream pins moved to the tag (E5). Sprint B built and merged September 14, 2026 (PRs #135–#138).
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

---

## Parked items — decided (walkthrough, September 13, 2026)

The architect closed the long-parked, never-registered items in the same session. **Nothing on the chain is open.**

| # | Question | Decision | Closes |
|---|---|---|---|
| 29 | Check every corpus program's runtime effects against its effect surface? | Yes (H8). | I-Q5 (v3.0) |
| 30 | Check that harmless edits never change the surface? | Yes, in the same test (H8). | I-Q6 (v3.0) |
| 31 | A mutation-testing tool? | No. Each fix PR breaks its own change once and shows the tests catch it, as #102–#104 did. | I-Q7 (v3.0) |
| 32 | Programs doing several things at once? | No. Structured concurrency is withdrawn; programs run one step at a time. | v4.2 §70.1 (Tier 5) |
| 33 | Does a record carry write time as well as crossing time? | One time, the crossing time, as built (`Record.when`). | R-Q1 (v6.1 §86) |
| 34 | Linear types for capabilities? | Withdrawn. Authority, if ever enforced, is checked at the host. "No type system" has no exceptions. | unbound v1.1 §25; v9.1 §119 |
| 35 | Language-release header and manifest syntax? | None. Tagged releases pin versions. | Handoff Q1 |
| 36 | Minimum provenance every run retains? | As built: full history by default; window, seals and replay on demand for long runs (#77, #79). | Handoff Q2 |
| 37 | Missing key in dynamic record lookup? | `nothing`, as static field access gives today. | Handoff Q3 |
| 38 | Which platform defines performance budgets? | The architect's Mac, named in every number. School hardware only if deployed there. | Handoff Q4 |
| 39 | First portable execution target: bytecode, Wasm, or both? | Neither. Planes runs on its interpreters. | Handoff Q5 |

For the next checkpoint's register (bookkeeping only):
- P-Q17 has been used three times: v2.0 §36 fingerprints, v14.0 §159 host seam, v37.0 rule-target matching.
- P-Q16 and P-Q23 have each been used twice.
- The P-Q20–P-Q23 closures live only in `reports/REPORT_AUDIT.md`.
- The v23.0-to-v30.1 count carried two offsetting errors: v25.1 decremented A-Q2, which was never counted, and v30.1 re-resolved A-Q23, already closed at v24.0 §309. Separately, A-Q20 and A-Q21 were dropped from the list from v30.1 onward.

---

## Sprint A — fix and harden (no semantics change)

### Done (September 13, 2026)

Every in-repo item merged, and `scripts/ci.sh` passed in full on the result.

| Item | PR | What landed |
|---|---|---|
| F1 | #113 | A repeated destination names its first line on every hash seed; pinned across eight seeds against Swift |
| F2, F7 | #125 | `text of` a list or record gives its contents, and the effect surface predicts that exact text in Python, JS and Swift (or widens to `{...}`). The `nothing` comparison's fix clause splits into its whole-value and inner-value cases |
| F3 | #118 | A reserved word inside a function name quotes the whole name and suggests a hyphen. `grammar/parser.planes` gained the check it lacked |
| F4 | #111 | The four approved tutor lines, pinned by a test |
| F5, F6 | #123 | The three JS protocol parsers strip both whitespace sets (none has a Python counterpart). A record entry has `toPlain()`, which survives `structuredClone` and JSON |
| F8 | #124 | A module's own calls resolve to its own definitions first, by a table lookup, in Python and JS. The same flaw in all three analysers' rename tables, which under-reported reach, is fixed. Closes #108. `grammar/interp.planes` has no modules |
| H1 | #119 | `--json --rules` carries a `rules` object with structured violation fields in Python, JS and Swift. Format stays 1 |
| H2 | #115 | The audit checks `supersedes` and `permit` (built), `contradicts` and mandatory fingerprints (not built, scheduled B3), and lists `until` as withdrawn |
| H3 | #116 | `demo/mcp/v1.planes` and `v2.planes`, reconstructed from v37.0, with surfaces and a test: `--diff` exits 1, the telemetry host is flagged, the registry host isn't |
| H4, E3 | #120 | A root `Package.swift` (macOS 14 and iOS 17, both verified by building). `HostRules` costs 1.1 ms (50 rules) to 3.0 ms (200 rules) p50 per 150-request page on the M1 Pro (`swift/host-rules-bench-results.md`) |
| H5 | #112 | The identity sheet cites where each lock was made: v8.0 for type, palette and lockup; v7.0 §87 for the provisional plane colours |
| H6 | #117 | `sine` (1,724 values) and `root` (237) agree across all four hosts; no disagreement found. The README states the claim |
| H7 | #131 | README Performance section; harness and results in `benchmarks/published/` |
| H8 | #130 | All 51 corpus programs and #108's reproductions pass the runtime-vs-surface check in Python and JS. Renaming and comments leave every surface unchanged; reordering applies to the one program with two or more functions |
| E1 | #126 | `docs/surface-format-v1.md` and `grammar/protocols/surface-v1.json`; all three hosts' output validates |
| E2 | #121 | `js/embed.mjs` (grammar loaded on import, no `fs` or `fetch`) and `js/embed.d.mts`, type-checked under `tsc --strict` against a consumer |
| E4 | #128 | README: checking a file with Node or Swift. `node js/cli.mjs shapes` now refuses a syntax error in one line, as `shapes_cli.py` does |
| E5 | 5xfive #73; koncord-shared-agency #38 | **5xFive** vendors the tag's JS (15 modules; `python_unicode*.mjs` are new dependencies), with `.d.mts` updated for `toPlain` and `asJson`. Its checks pass: typecheck, lint, 1,207 tests. Two compliance tests had pinned the false computed-target match #104 removed, and were corrected. **Koncord** depends on `https://github.com/rmichaelthomas/planes.git` at `revision: "sprint-a-2026-09"` instead of `~/planes/swift`: 781 tests, 0 failures. The dependency arrived with Koncord's networking layer, and both merged to its `main` together. Follow-ups in 5xFive: `toPlain` could replace its `sanitizeRecords`; `js/embed.mjs` could replace `load-grammar.ts`; the `{...}` wildcard waits for B2 |

Four PRs fixed what parallel branches broke together: #114 and #122 made the repo walks skip hidden directories (agent worktrees), #127 regenerated `grammar/errors.json`, and #129 reconciled the corpus count, the README catalogue counts and a self-hosted test harness.

### Found while building Sprint A

- **`plus` copies the list on every append**, so building a list one element at a time is quadratic. A first word-count benchmark took 50 s where counting inline took 5.6 s (H7).
- **The JS CLI can't run a program against the real filesystem.** `run` and `run-file` use an in-memory host; `NodeHost` is wired only to the `host` probe (H7).
- **`foreign` names aren't checked for reserved words** in any of the four hosts (F3).
- **The Swift CLI words a refused file differently:** `shapes: line 1: …` and exit 2, where Python and Node print `syntax error — line 1: …` and exit 1 (E4).
- **Only one corpus program has two or more top-level functions**, so H8's reorder check has one real subject.
- **`demo/mcp/v2.planes`'s telemetry call is a POST labelled `doing ask`.** B1 relabels it with the others.

### The plan as written

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

**H8. Every corpus program, checked against its own surface.** `test_coverage.py` runs the oracle (every runtime effect appears in the static surface) over one case per node type, not over the corpus (#29, #30).
- Run each of the 51 corpus programs under the stubbed host `test_corpus.py` already uses, and assert its runtime effects are covered by its surface.
- For each program, rename a local name, add a comment, and reorder its function definitions, and assert the surface is unchanged.
- Run it in Python and JS. It is the net that should have caught F8.

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

### Done (September 14, 2026)

Built in parallel on three branches, then B4; `scripts/ci.sh` passed in full on the result.

| Item | PR | What landed |
|---|---|---|
| B1 | #137 | `send` in `grammar/vocabulary.json` and every host, Swift `HostEffect.send` included. README, `demo/fdiff/` and `demo/mcp/v2.planes` relabelled. `SurfaceDiff` treats a changed kind on the same destination as significant. Rules: forbidding `ask` covers `send`, a permit clears only its own kind; opposite rules conflict when their covered kinds overlap on the same scope. Surface format 2 (`docs/surface-format-v2.md`, `grammar/protocols/surface-v2.json`); the v1 files are as tagged plus a pointer. The seven-kind pins now say eight |
| B2 | #135 | One URL matcher in `rules.py`, `js/rules.mjs` and `Rules.swift` (and so `HostRules`): same scheme and host compared ASCII case-insensitively, port as written, path at `/` boundaries, effect query and fragment ignored. A rule target with `?` or `#` is refused. Narrowing is strict containment; equal scopes collide. `_pattern_excludes` re-proven for covering, conservatively |
| B3 | #136 | `supersedes [x]` without `@fingerprint` is refused with the fingerprint to add; every fixture carries a computed one. `contradicts [x]` is a clause after `supersedes`, with no fingerprint; unknown, self and doubly-declared pairs are refused. When both rules apply, a contradiction violation names both and one effect each. The audit reports both relations built |
| B4 | #138 | Two facts only the prose carried, a rule's subject and an effect's computed/declared flags, became fields. `render()` is `render_violation(as_json())` in Python, JS and Swift, pinned over every shape and fixture; `js/embed.d.mts` types `ViolationJson`; Swift has a `render-from-fields` oracle command |

### Found while building Sprint B

- **A `foreign` named after an effect kind was counted twice** by all three analysers (`foreign send of payload … doing send`). Fixed in B1.
- **`contradicts` missed a rule that applies only through `ask` covering `send`.** Fixed when B1 was reconciled with B3.
- **Full Unicode lowercasing disagrees across hosts** (a final Σ), so host comparison folds ASCII only. Fixed in B2.
- **Downstream work B2 and B1 create:** Koncord's `AdmissionRules.swift` compiles rule targets to exact-URL regexes and needs prefix matching; 5xFive's `{...}` wildcard can go (it can't; see Downstream below); both pin format 1 at `sprint-a-2026-09` until they move.

### Downstream (September 14, 2026)

| Project | PR | What happened |
|---|---|---|
| Planes | tags; #140 | `sprint-b-2026-09` tagged at cc7b08f. Koncord's rule-cost measurement on it found B2 had made Swift checks two orders of magnitude slower (0.139 → 14.9 ms release, 50 rules; HostRulesBench page 1.03 → 77 ms). URL targets were re-parsed into copies on every pairwise comparison. #140 parses each once into UTF-8 views, rejects pairs by folded origin, and restores 0.148 ms and 1.63 ms. Matching unchanged. Tagged `sprint-b-2026-09.1` |
| 5xFive | 5xfive #74, merged | Vendors `sprint-b-2026-09`: four modules and two grammar files changed, blobs verified. `rules.d.mts` types B3/B4. No wrapper code changed. **The `{...}` wildcard stays**: B2 covers only URL-shaped addresses, so a rule on `5x:acme:member:` matches no tagging write. A test holds that. Typecheck, lint, 1,208 tests, CI green |
| Koncord | koncord-shared-agency #40, merged | The compiled list and page watch cover addresses, as two WebKit triggers per address (its URL filter has no `|`). `send` rules are left out, because Koncord checks requests as `ask`. Pinned at `sprint-b-2026-09.1`. 783 tests pass. Parity: Etsy and Airbnb fail on pixels as already accepted. The New York Times fails on fonts (12 vs 20), on `main` as well. The architect accepted it |

Still open from this: `js/rules.mjs` has the same parsing pattern (0.049 → 1.38 ms on 50 rules), which matters once a JS host checks many rules.

### The plan as written

**B1. The send effect (P-Q25).** Specified by Track 0 #7–#11:
- `send` is an **effect kind that `foreign` declarations use**: `foreign post of message from "slack.post" doing send "https://hooks.slack.com/…"`.
  - No keyword, no builtin, no host method.
  - The vocabulary is `ask clock env random read send show write`.
  - `send` is on the network boundary with `ask`. Its note: a request that carries the program's data out.
- **Documentation states the one rule:** data going out is `send`; fetch-only is `ask`. Nothing checks beyond the declared label, the same trust every `doing` claim has.
- **Relabel** the README's `foreign` POST example (`README.md:548` at `c4400ad`), `demo/fdiff/v1.planes`, `demo/fdiff/v2.planes` and `demo/mcp/v2.planes`'s telemetry call to `doing send`.
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
