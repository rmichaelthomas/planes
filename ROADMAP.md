# Planes roadmap

**Updated:** September 13, 2026, after the Track 0, register and parked-item walkthroughs, after Sprint A merged (PRs #111–#134), and after Sprint B merged (PRs #135–#138, September 14). Nothing on the chain is open (base `c4400ad`, addendum v37.1)
**Supersedes as the working roadmap:** `reports/planes_handoff_2026_08_01_language_and_performance_roadmap.md`. That file is archival and unedited. Its phase order still stands, and each phase's current status is below.
**Near-term work:** [`docs/planes_sprint_2026_09_hardening.md`](docs/planes_sprint_2026_09_hardening.md)

Planes is a general-purpose language whose effect surface and numeric exactness are computable without running a program, and whose every value can say where it came from. That property is the product. Everything below either protects it, extends where it reaches, or makes it cheaper to use. Nothing is admitted that weakens it (v17.0 §183).

It is also used by other projects now, so this roadmap tracks their needs as well as the chain's:

| Project | How it uses Planes | Pinned at |
|---|---|---|
| 5xFive | Automations compile to Planes and run on the JS interpreter in a Cloudflare Worker; compliance rules compile to Planes rules | `sprint-a-2026-09` (vendored, 5xfive #73) |
| Koncord | Swift `HostRules`: a page's requests checked against `rules.planes` (the `koncord-shared-agency` package, from its networking layer on) | `sprint-a-2026-09` through the root `Package.swift` (koncord-shared-agency #38) |
| Omniglot, Cartouche | A `.planes` manifest analysed, never run, with the Python CLI | — |
| Undertow, Cutter | Re-implement the surface JSON format and effect vocabulary in TypeScript | format 1, by hand |
| Motif | Ported the tutor's typing loop and why-card; a Planes voice is planned | `1d8a833` (copied JS) |
| MuseSky, TAOS | Design dependencies: amber as interaction grammar; derived reach in the obligation stack | — |

---

## Done — Sprint A: fix and harden

Built and merged September 13, 2026. `scripts/ci.sh` passed in full on the result. Item by item, with PRs and what the sprint found, in the sprint doc. In short:
- **Wrong answers fixed:** the hash-seed line, `text of` a list (and the surface now predicts it), the reserved-word message, false tutor copy, the JS protocol whitespace, records across `structuredClone`, and the module rename bug ([#108](https://github.com/rmichaelthomas/planes/issues/108)), which also under-reported reach in all three analysers.
- **Held in place:** `--rules` in `--json`; the audit covers rule-plane relations; the MCP demo committed with a test; `sine` and `root` agree across four hosts; every corpus program checked against its own surface.
- **Easier to embed:** the surface format published with a schema; `js/embed.mjs` with types; a root `Package.swift` for macOS and iOS; a documented Node/Swift checker.
- **Measured:** `HostRules` cost; a README Performance section.

E5 is done too: 5xFive and Koncord both pin the tag.

## Done — Sprint B: the effect vocabulary grows to eight, and the rule plane catches up

Built and merged September 14, 2026 (PRs #135–#138). `scripts/ci.sh` passed in full on the result. Details in the sprint doc.

1. **The send effect** (#137). `send` is an eighth effect kind `foreign` functions declare: data going out. `ask` is fetch-only. Existing sends are relabelled; `--diff` reports an `ask` → `send` change; forbidding `ask` also forbids `send`. The surface format is now version 2 (`docs/surface-format-v2.md`); version 1 stays as the Sprint A tag's record.
2. **Rule-target matching** (#135). A rule's address covers everything under it: same scheme and host (ASCII case-insensitive), path at `/` boundaries, query ignored, subdomains separate. A rule address with a query is refused. Non-URL targets still match exactly. Settles Koncord PE-Q42.
3. **`contradicts`, and mandatory supersession fingerprints** (#136). `supersedes` without the overridden rule's fingerprint is refused, printing the one to add. `contradicts [other]` reports a violation when both rules apply. The audit lists both as built; `until` stays withdrawn.
4. **Structured violations** (#138). Every fact a rendered violation states is a field, and `render()` is computed from those fields in Python, JS and Swift. `js/embed.d.mts` types them; the README and `swift/README.md` show a host writing its own wording.

Downstream, not yet done: 5xFive and Koncord still pin `sprint-a-2026-09` (format 1). Moving them to Sprint B means format 2, Koncord's `AdmissionRules.swift` compiling rule targets as prefixes (`^` + escaped address + `(/|$|[?#])`), and 5xFive dropping its `{...}` wildcard workaround.

---

## Later — by theme

Each item says where it came from and what it waits on. The Aug 1 handoff's phases are marked **P0–P4**.

### 1. Contracts and receipts (handoff P0)

| Item | Status | Waits on |
|---|---|---|
| Release versioning | **Decided: no header or manifest syntax in programs.** A tagged release pins language, grammar, host and protocols together. The drawing and sound protocols keep their own version lines. | — |
| Canonical AST serialization and a public conformance corpus | Partial. The canonical form exists in Python, JS and Swift, and agreement suites run it. Not yet published as fixtures a stranger can run. | Sprint A tag |
| Structured run receipt: sources, seed, host, surface, observed effects, rule decisions | Partial. The record plane (#7), fingerprints and the event log (#85) exist; nothing is signed. | Omniglot O-Q3 and 5xFive refusal receipts want surface→receipt wiring |
| `planes describe`, a manifest of manifests | Admitted at v18.0 §200, not built | — |
| Surface format versioning | Format 1 (Sprint A E1) and format 2 (Sprint B: `send`, address-covering rules, contradictions, full violation fields) published with schemas | — |

### 2. Authority, budgets and the rule plane (handoff P1)

| Item | Status | Waits on |
|---|---|---|
| Requested → granted → observed effects, host-enforced allowlists | Not built. `foreign … doing` is still a claim. | A design session. Enforcement lives at the host; linear capability types are withdrawn. |
| Resource budgets: steps, depth, rational size, output bytes, effect counts | Only `_WHY_SEARCH_BUDGET` exists | — |
| **A beneficiary on rules**: who a rule protects | Not built. Asked by TAOS (OL-Q1), Koncord v0.13 §96.3 and the Cloudflare contribution; Undertow built its own `for=`. | Architect: language or Liminate |
| Rules about data reaching a send (`customer emails may not derive into any send`) | Partial. `send` labels data leaving (Sprint B1); named subjects resolve through derivation (A-Q22); data in a URL is traced (v37.0 §520). A rule about which data derives into a `send` isn't built. | A design session |
| Rule-set consistency beyond conflict and vacuity | 5xFive runs Z3 on Liminate, not on Planes rules | — |
| Retroactive re-check of stored derivations against new rules | Brainstormed (DeepSeek) | — (expiring rules were declined at Track 0 #4) |
| Dynamic record lookup; precedence diagnostics | Not built. **Decided:** a missing looked-up field gives `nothing`, exactly as `person.age` does today. | — |

### 3. The language itself

These are gaps real programs hit, each with a witness. Per standing rule, work is admitted on a red gate, a wrong answer or a violated guarantee, not on wishlist alone.

| Gap | Witness |
|---|---|
| No collection operations: sort, sum, max, group | ChatGPT-written programs assumed `sort of … with`; sorting needs `foreign builtins.sorted` |
| No text split or word count | Three witnesses (v22.1 §283); `corpus/word-count.planes` takes pre-split input |
| No index into a list | Only `first n of` and `rest` |
| No native `clock`, `env` or date arithmetic; `random`/`env` aren't host methods | Dashboard, neglect-score and token programs (DeepSeek); `ADDENDUM_SPRINT` §6 |
| Numeric recursion hits `recursion-too-deep` and its advice fails | v22.2 §288 |
| No exponentiation, so equal temperament can't be written | v20.0 §233 |
| `plus` copies the list on every append, so building a list element by element is quadratic | Sprint A H7: 50 s against 5.6 s for the same word count |
| `foreign` names aren't checked for reserved words, in any host | Sprint A F3 |
| String escapes are only `\" \\ \n \t`; JSON's `\r \b \f \uXXXX` are refused | `grammar/json.planes:23`; the tutor's `because` can't hold a `"` |
| `why` is a statement, not a value a program can branch on | DeepSeek; wanted for click-to-explain and audits |
| A host `ask` must return synchronously | 5xFive v3.2 §264a works around it with a prefetched address |
| A dead `Builtin` node in `lexer.py` | `ADDENDUM_SPRINT` §6 (reported) |

Held on purpose, with their triggers:
- **One step at a time:** structured concurrency (v4.2 §70.1, Tier 5) is withdrawn. Planes programs run sequentially, which is what keeps `why` and replay exact. An app that needs parallel work does it around Planes, as 5xFive and Koncord do.
- **No type system, with no exceptions:** v9.1 §118. §119's linear-capability candidate (unbound v1.1 §25, v4.2 §70.2) is withdrawn. Authority, if ever enforced, is checked at the host (requested → granted → observed).
- **No `hash` builtin:** v32.0.
- **No private functions** (A-Q6c): every function a module defines stays visible; a clash is fixed by renaming at the point of use, which #108 makes correct.
- **No versions in the language** (A-Q6a): `use` names a file; versions come from tagged releases, and `--diff` shows what changed between two.

### 4. Errors and messages

- **Settled at Track 0:**
  - `grammar/errors.json` is a generated reference copy; messages are written in each host's code and held equal by the agreement suites (A-Q20, closed).
  - Every raise site gives advice true for its exact case (A-Q21, closed; the last leftover is sprint item F7).
- The 54 error messages never audited (v22.2 §291).
- Teaching-grade tags: the tutor softens only 4.
- Messages are a four-host byte-identical contract (Swift README rule 4), so every message change costs four edits.
- The Swift CLI refuses a file as `shapes: line N: …` with exit 2; Python and Node print `syntax error — line N: …` with exit 1 (Sprint A E4).

### 5. Performance (handoff P2–P3)

| Item | Status |
|---|---|
| Persistent program session, no re-parse per tick | **Done for the world runtime** (#84, #87). Not done for Garden/Paint-style reruns. |
| Explicit stack instead of host recursion | **Done for `explain`** (#79). The interpreter still recurses; metacircular ceiling 178–199 frames. |
| Retention tail and GC stalls | Python fixed (#88); JS windowed tail residue unconfirmed against a dense scene |
| `_cut` redesign | Phase-2-gated, to be decided against a real cell's per-tick shape (v33.0) |
| Published benchmarks (A-Q1, decided) | **Done (Sprint A H7).** README Performance section, measured on the M1 Pro at `6b0499e`: on the four ordinary jobs, `planes.py` is 10–167x plain Python and the JS interpreter 2–12x plain Node; effect surfaces take a median 57 ms per corpus file in Python; 3 of 51 corpus programs cross a foreign boundary. |
| `HostRules` cost | **Measured (Sprint A H4):** 1.1–3.0 ms p50 to check a 150-request page against 50–200 rules |
| Reference machine | **Decided: the architect's Mac**, named in every published number and gate. School-hardware recalibration happens only if Planes is deployed on school computers. Firefox never measured. |
| Bytecode, Wasm, JIT | **Decided: neither.** Measured unnecessary (v33.0: kernel p95 1.6 ms against a 5 ms gate), and a compiled form would build the same derivations. Planes runs on its interpreters. |
| Provenance retained per run | **Decided, as built:** ordinary runs keep full history. Long-running programs keep a window and seal older history (#77); `why` on sealed values replays on demand (#79), gated on byte-identical agreement. |

### 6. Ports and embedding

| Item | Status |
|---|---|
| Swift interpreter | Not ported. `planes-swift` can't run a program. Needed if a SwiftUI app runs Planes, not only checks rules. |
| iOS target | **Done (Sprint A E3):** the root `Package.swift` declares macOS 14 and iOS 17, and the library builds for iOS |
| Running a program against the real filesystem from the JS CLI | Missing: `run` and `run-file` use an in-memory host (Sprint A H7) |
| Self-hosted world emission | A named follow-on (`test_world_runtime_conformance.py`) |
| `grammar/interp.planes` dynamic `host.resolve` | The `foreign.planes` gap (v25.0 §360) |
| Workers-ready JS bundle, TypeScript types, structured-clone-safe records | **Done (Sprint A E2, F6):** `js/embed.mjs` needs no loading step or filesystem, `js/embed.d.mts` types it, and a record entry has `toPlain()` |
| Effect extraction from non-Planes code (JS, HTML, Python) | **Not Planes' job** (A-Q11, decided). Planes analyses Planes programs only; other languages are Cutter's, which already maps TS and Python reach in Planes' vocabulary. Asked by Koncord §98 and Omniglot O-Q4. |
| Foreign target names across hosts (A-Q17, decided) | The eight names in `sharedTargets()` (`js/host.mjs`) are the portable set, and every host that runs programs supports them, Swift included once it has an interpreter. Any other name works only where that host provides it, and fails elsewhere with "cannot find". |

### 7. Ecosystem and distribution (handoff P4)

Decided in the register walkthrough:
- **Distribution (A-Q7):** tagged GitHub releases only.
  - Swift through SwiftPM at a tag (after the root `Package.swift`).
  - JS by copying `js/` at a tag (with the embedding entry point).
  - Python by checking out the repository at a tag.
  - No PyPI or npm packages.
- **No registry (A-Q8).** `--json` and `--diff` publish and compare a surface wherever the code lives.
- **Public home (A-Q5):** the GitHub Pages site, `rmichaelthomas.github.io/planes`.
- **The tool keeps the name `shapes` (A-Q10).** The feature is always "the effect surface" in writing.
- **Determinism (A-Q24):** Planes publicly claims the same numbers on every machine and in every implementation. The four-host `sine` and `root` test passed (Sprint A H6), and the README says so.
- **No determinism-market artifact (A-Q25):** no reference model, no generated trig table.
- **Analysing other languages (A-Q11)** is not Planes' job (§6).

Still later:
- A task/workflow plane: cancellation, deadlines, retries.
- LSP support built on effect and provenance hovers.
- A syntax quick reference for agents. 5xFive v3.1 §260 found an agent inventing `;` comments and quoted keys.

### 8. Horizon

Held by inception v2.0: build → descend → inhabit, movement first, one small slice at a time.

| Phase | Status |
|---|---|
| 0 substrate | Done (#83–#86) |
| 1 engine kernel and renderer | Done (#87–#91). Rapier, audio buses and the asset compositor deferred until content needs them. |
| 2 playable cell | In progress: input seam (#93), crossing port (#95), walk slice (#97). Still owed: |
| | – visual acceptance against the look-dev frame |
| | – Breeze/Harbor gates on school hardware, only if Planes is deployed there |
| | – `pixi_performer.mjs`'s hard-coded hydrofoil and single environment image |
| | – a seed the page can re-roll (`world-init` takes no parameters) |
| | – the real Ala Eriri cell |
| 3 Living Lens | Not started |
| 4 co-builder and trust | Not started |
| 5 Living World Seed | Not started |
| 6 release gates and pilot | Not started |

Open alongside it: the R2 machine-export provenance bound (v29.0 §454) must be set before any AI agent reads derivations in a child-facing product.

### 9. Teaching

- **Decided in the register walkthrough:**
  - A lesson is one entry in `tutor.html`'s lesson list: title, instruction, worked example, and the ordered lines to type (T-Q4).
  - "Approximate" is presented as information, not a warning (T-Q5).
  - The worked example is the lesson's answer, shown openly. It is lesson content, not a record-plane artifact (T-Q6).
  - The garden words ship ready-made in the key. The learner writes their own `because` reason and their own sky name. The picker writes `custom-sky of` and the colour numbers, never the learner's words (T-Q7).
- **No measurement layer (A-Q13).** It belonged to a model-narrated tutor that is not being built.
- **Crosswalk gaps after v35.0's exact-match typing.** Lessons 2 and 5 can't be answered by changing a number, and lessons 3 and 6 have no prediction or explanation prompt. The ODE codes are unchecked against Draft v1.0.
- **Unverified surfaces.** No phone or touch pass (verified only to 800px, and the coordinate tip is hover-only). Refresh loses mid-lesson progress in lessons 1–6.
- **Audience.** The page speaks to children in adult wording ("approximating builtin"). There is no adult variant.
- **Proposal and page must agree.** The proposal says each lesson adds to one program and that Planes shows what a program touches before it runs. The tutor does neither today.
- **More first-timers.** None tested since #98/#99.
- **The seed is decorative, but sharing a seed was meant to be the point** (v24.0 §316, v27.0 §81). Bug, [issue #106](https://github.com/rmichaelthomas/planes/issues/106), no rush. Until it's fixed, the copy says the saved file is what's shared (sprint F4).

---

## The open register

**Empty.** Addendum v37.1 counted eighteen, but it had dropped A-Q20 and A-Q21, so the true count was twenty. The architect answered all twenty on September 13, 2026:
- **Track 0:** A-Q20, A-Q21, P-Q17 (v37.0), P-Q25. Also closed outside the register: the original P-Q17 fingerprints, F-Q1 `contradicts`, F-Q2 `until`, and Koncord PE-Q42.
- **The register walkthrough:** A-Q1, A-Q5, A-Q6a, A-Q6c, A-Q7, A-Q8, A-Q10, A-Q11, A-Q13, A-Q17, A-Q24, A-Q25, T-Q4, T-Q5, T-Q6, T-Q7.

Each answer is recorded where it lands above, and in the sprint doc's decision tables.

**The parked items are closed too** (parked-item walkthrough, same day):
- **I-Q5 and I-Q6:** one new test runs every corpus program, checks its runtime effects against its effect surface, and checks that renaming, commenting and reordering leave the surface unchanged (sprint H8).
- **I-Q7:** no mutation-testing tool. Each fix PR breaks its own change once and shows the tests catch it.
- **Tier 5 concurrency:** withdrawn.
- **R-Q1:** a record carries one time, the crossing time, as built.
- **Linearity for capabilities:** withdrawn.
- **Handoff questions 1–5:** no version header; provenance as built; missing looked-up field is `nothing`; the architect's Mac is the reference machine; no bytecode or Wasm.

Nothing on the Planes chain is open. New questions start fresh.

## Standing terms any item on this page inherits

- **Agreement.** Python is the reference. JS, `grammar/interp.planes` and Swift agree byte-for-byte, checked by running and diffing.
- **Soundness is not negotiable.** A change may remove impossible matches; it may never hide a real reach.
- **Closed vocabularies.** The effect vocabulary and the host surface are closed, and grow only by a checkpoint that passes v37.1 §530.
- **Exactness.** Exact numbers; rounding is a named operation; replay never re-executes effects.
- **Build discipline.**
  - Locked means built, and the audit says so.
  - Verification scripts graduate into suites.
  - Absence claims carry a verification marker.
  - Archival documents are not edited.
  - No working document is written to the vault except by the architect.
