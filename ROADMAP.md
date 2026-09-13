# Planes roadmap

**Updated:** September 13, 2026, after the Track 0 decision walkthrough (base `c4400ad`, addendum v37.1)
**Supersedes as the working roadmap:** `reports/planes_handoff_2026_08_01_language_and_performance_roadmap.md`. That file is archival and unedited. Its phase order still stands, and each phase's current status is below.
**Near-term work:** [`docs/planes_sprint_2026_09_hardening.md`](docs/planes_sprint_2026_09_hardening.md)

Planes is a general-purpose language whose effect surface and numeric exactness are computable without running a program, and whose every value can say where it came from. That property is the product. Everything below either protects it, extends where it reaches, or makes it cheaper to use. Nothing is admitted that weakens it (v17.0 §183).

It is also used by other projects now, so this roadmap tracks their needs as well as the chain's:

| Project | How it uses Planes | Pinned at |
|---|---|---|
| 5xFive | Automations compile to Planes and run on the JS interpreter in a Cloudflare Worker; compliance rules compile to Planes rules | `1d8a833` (vendored) |
| Koncord | Swift `HostRules`: a page's requests checked against `rules.planes` | `9ec3cfa` (checkpoint-verified) |
| Omniglot, Cartouche | A `.planes` manifest analysed, never run, with the Python CLI | — |
| Undertow, Cutter | Re-implement the surface JSON format and effect vocabulary in TypeScript | format 1, by hand |
| Motif | Ported the tutor's typing loop and why-card; a Planes voice is planned | `1d8a833` (copied JS) |
| MuseSky, TAOS | Design dependencies: amber as interaction grammar; derived reach in the obligation stack | — |

---

## Now — Sprint A: fix and harden

No semantics change. See the sprint doc. In short:
- the hash-seed-dependent line in the reference
- `text of` on a list
- the reserved-word message
- false tutor copy
- the unaudited JS `trim()`s
- `--rules` in `--json`
- the audit tool covering rule-plane relations
- the MCP demo committed
- `HostRules` cost measured
- the surface format published with a schema
- a JS embedding entry point with types
- a root `Package.swift`
- a tagged release downstream projects can pin

## Next — Sprint B: the effect vocabulary grows to eight, and the rule plane catches up

All decided at Track 0 (September 13, 2026). The full specification is in the sprint doc, B1–B4.

1. **The send effect.** The network gets its `write`.
   - `send` is an effect kind `foreign` functions declare. No keyword, no host method.
   - The vocabulary goes from seven to eight.
   - Data going out is `send`; fetch-only is `ask`.
   - Existing mislabelled sends are relabelled, and `--diff` reports the change.
   - Forbidding `ask` also forbids `send`, so no older rule weakens.
2. **Rule-target matching.** A rule's address covers everything under it: same host, path at `/` boundaries, query ignored. Subdomains are separate. Built with `send`, so both network kinds match the same way. Settles Koncord PE-Q42.
3. **`contradicts`, and mandatory supersession fingerprints.** `until` is withdrawn.
4. **Structured violations.** Hosts write their own wording from fields, not by parsing rendered text.

---

## Later — by theme

Each item says where it came from and what it waits on. The Aug 1 handoff's phases are marked **P0–P4**.

### 1. Contracts and receipts (handoff P0)

| Item | Status | Waits on |
|---|---|---|
| Versioned release contract: language, grammar, host interface, protocol versions, dependency hashes | Not built. The World IR (`world-v1.json`, #83) proved the pattern for a protocol. | Handoff open question 1: manifest syntax |
| Canonical AST serialization and a public conformance corpus | Partial. The canonical form exists in Python, JS and Swift, and agreement suites run it. Not yet published as fixtures a stranger can run. | Sprint A tag |
| Structured run receipt: sources, seed, host, surface, observed effects, rule decisions | Partial. The record plane (#7), fingerprints and the event log (#85) exist; nothing is signed. | A-Q13; Omniglot O-Q3 and 5xFive refusal receipts want surface→receipt wiring |
| `planes describe`, a manifest of manifests | Admitted at v18.0 §200, not built | — |
| Surface format versioning beyond format 1 | Starts with Sprint A E1 | Sprint B's eighth kind |

### 2. Authority, budgets and the rule plane (handoff P1)

| Item | Status | Waits on |
|---|---|---|
| Requested → granted → observed effects, host-enforced allowlists | Not built. `foreign … doing` is still a claim. | A design session; linear capabilities (unbound v1.1 §25) trigger with the first multi-principal program |
| Resource budgets: steps, depth, rational size, output bytes, effect counts | Only `_WHY_SEARCH_BUDGET` exists | — |
| **A beneficiary on rules**: who a rule protects | Not built. Asked by TAOS (OL-Q1), Koncord v0.13 §96.3 and the Cloudflare contribution; Undertow built its own `for=`. | Architect: language or Liminate |
| Rules about data reaching a send (`customer emails may not derive into any send`) | Partial. Named subjects resolve through derivation (A-Q22); data in a URL is traced (v37.0 §520). A request body can't be expressed until P-Q25. | Sprint B |
| Rule-set consistency beyond conflict and vacuity | 5xFive runs Z3 on Liminate, not on Planes rules | — |
| Retroactive re-check of stored derivations against new rules | Brainstormed (DeepSeek) | — (expiring rules were declined at Track 0 #4) |
| Dynamic record lookup with a missing-key contract; precedence diagnostics | Not built | Handoff open question 3 |

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
| String escapes are only `\" \\ \n \t`; JSON's `\r \b \f \uXXXX` are refused | `grammar/json.planes:23`; the tutor's `because` can't hold a `"` |
| `why` is a statement, not a value a program can branch on | DeepSeek; wanted for click-to-explain and audits |
| A host `ask` must return synchronously | 5xFive v3.2 §264a works around it with a prefetched address |
| Private functions (A-Q6c); module versioning (A-Q6a) | v18.0 §204, verified absent |
| A dead `Builtin` node in `lexer.py` | `ADDENDUM_SPRINT` §6 (reported) |

Held on purpose, with their triggers:
- **Structured concurrency:** Tier 5; trigger is the first parallel-I/O program.
- **No type system:** v9.1 §118, always cited with §119's linear-capability exception.
- **No `hash` builtin:** v32.0.

### 4. Errors and messages

- **Settled at Track 0:**
  - `grammar/errors.json` is a generated reference copy; messages are written in each host's code and held equal by the agreement suites (A-Q20, closed).
  - Every raise site gives advice true for its exact case (A-Q21, closed; the last leftover is sprint item F7).
- The 54 error messages never audited (v22.2 §291).
- Teaching-grade tags: the tutor softens only 4.
- Messages are a four-host byte-identical contract (Swift README rule 4), so every message change costs four edits.

### 5. Performance (handoff P2–P3)

| Item | Status |
|---|---|
| Persistent program session, no re-parse per tick | **Done for the world runtime** (#84, #87). Not done for Garden/Paint-style reruns. |
| Explicit stack instead of host recursion | **Done for `explain`** (#79). The interpreter still recurses; metacircular ceiling 178–199 frames. |
| Retention tail and GC stalls | Python fixed (#88); JS windowed tail residue unconfirmed against a dense scene |
| `_cut` redesign | Phase-2-gated, to be decided against a real cell's per-tick shape (v33.0) |
| Benchmark contract with named platforms | Open (handoff question 4; A-Q1). Every gate is still provisional, set on the dev machine. No Planes-vs-other-language figure exists; Firefox never measured. |
| Bytecode, Wasm, JIT | Rejected as measured-unnecessary for the kernel (v33.0). Reconsider only after profiling a real workload. |

### 6. Ports and embedding

| Item | Status |
|---|---|
| Swift interpreter | Not ported. `planes-swift` can't run a program. Needed if a SwiftUI app runs Planes, not only checks rules. |
| iOS target | `Package.swift` is macOS 14 only |
| Self-hosted world emission | A named follow-on (`test_world_runtime_conformance.py`) |
| `grammar/interp.planes` dynamic `host.resolve` | The `foreign.planes` gap (v25.0 §360) |
| Workers-ready JS bundle, TypeScript types, structured-clone-safe records | Sprint A E2 and F6 start it |
| Effect extraction from non-Planes code (JS, HTML, Python) | Asked by Koncord §98, Cutter, Omniglot O-Q4. Planes has said it analyses only Planes (Koncord v1.5 §240.3). **Needs a scope ruling**; A-Q11's option A is the same question. |

### 7. Ecosystem and distribution (handoff P4)

- **A-Q7:** distribution and installation. `pyproject.toml` is `0.1.0` with no publish path.
- **A-Q8:** what a registry publishes. After H1 it has every field group it named.
- **A-Q6a:** module versioning, which must come first.
- **A-Q10:** the `shapes` tool name.
- **A-Q11:** the wedge. Effect surfaces for Python/npm packages, starting from `shapes_python_probe.py`.
- **A-Q5:** the interactive surface's home. GitHub Pages ships; Prosecode.org was the stated home.
- A task/workflow plane: cancellation, deadlines, retries.
- LSP support built on effect and provenance hovers.
- **A-Q24:** a public cross-host determinism claim, now with four agreeing implementations.
- **A-Q25:** D1's first artifact, the generated fixed-point trig table.
- A syntax quick reference for agents. 5xFive v3.1 §260 found an agent inventing `;` comments and quoted keys.

### 8. Horizon

Held by inception v2.0: build → descend → inhabit, movement first, one small slice at a time.

| Phase | Status |
|---|---|
| 0 substrate | Done (#83–#86) |
| 1 engine kernel and renderer | Done (#87–#91). Rapier, audio buses and the asset compositor deferred until content needs them. |
| 2 playable cell | In progress: input seam (#93), crossing port (#95), walk slice (#97). Still owed: |
| | – visual acceptance against the look-dev frame |
| | – Breeze/Harbor gates on named school hardware |
| | – `pixi_performer.mjs`'s hard-coded hydrofoil and single environment image |
| | – a seed the page can re-roll (`world-init` takes no parameters) |
| | – the real Ala Eriri cell |
| 3 Living Lens | Not started |
| 4 co-builder and trust | Not started |
| 5 Living World Seed | Not started |
| 6 release gates and pilot | Not started |

Open alongside it: the R2 machine-export provenance bound (v29.0 §454) must be set before any AI agent reads derivations in a child-facing product.

### 9. Teaching

- **T-Q4:** a lesson as an artifact.
- **T-Q5:** exact vs approximate, as feature or caution.
- **T-Q6:** answer key and the record plane.
- **T-Q7:** starter vocabulary. The picker writes `custom-sky` too, against BP invariant 5.
- **Crosswalk gaps after v35.0's exact-match typing.** Lessons 2 and 5 can't be answered by changing a number, and lessons 3 and 6 have no prediction or explanation prompt. The ODE codes are unchecked against Draft v1.0.
- **Unverified surfaces.** No phone or touch pass (verified only to 800px, and the coordinate tip is hover-only). Refresh loses mid-lesson progress in lessons 1–6.
- **Audience.** The page speaks to children in adult wording ("approximating builtin"). There is no adult variant.
- **Proposal and page must agree.** The proposal says each lesson adds to one program and that Planes shows what a program touches before it runs. The tutor does neither today.
- **More first-timers.** None tested since #98/#99.
- **The seed is decorative, but sharing a seed was meant to be the point** (v24.0 §316, v27.0 §81). Bug, [issue #106](https://github.com/rmichaelthomas/planes/issues/106), no rush. Until it's fixed, the copy says the saved file is what's shared (sprint F4).

---

## The open register

**Sixteen questions.** Addendum v37.1 counted eighteen but had dropped A-Q20 and A-Q21, so the true count was twenty. Track 0 answered four: A-Q20, A-Q21, P-Q17 (v37.0) and P-Q25.

| # | Question | Where it lands |
|---|---|---|
| A-Q1 | The benchmark set | §5 |
| A-Q5 | The interactive surface's form and home | §7 |
| A-Q6a | Module versioning | §3, §7 |
| A-Q6c | Private functions | §3 |
| A-Q7 | Distribution and installation | §7 |
| A-Q8 | What a registry publishes | §7 |
| A-Q10 | The `shapes` tool name | §7 |
| A-Q11 | The wedge: option A dead or unexercised | §6, §7 |
| A-Q13 | What the measurement layer needs | §1 |
| A-Q17 | Foreign target portability (now three host tables, Swift included) | §6 |
| A-Q24 | Cross-host determinism claim | §7 |
| A-Q25 | D1's first artifact | §7 |
| T-Q4 – T-Q7 | Teaching | §9 |

Closed at Track 0, outside the register:
- the original P-Q17, supersession fingerprints: mandatory
- F-Q1, `contradicts`: build
- F-Q2, `until`: withdrawn

Parked or untracked, not closed:
- I-Q5, I-Q6, I-Q7: whole-corpus effect-log oracle, metamorphic tests, mutation tests. The Swift port did mutation testing informally.
- R-Q1
- linearity for capabilities
- Tier 5 concurrency
- handoff open questions 1–5

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
