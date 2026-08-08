# Handoff Packet — Planes language and performance roadmap

**Created for:** the next implementation or architecture agent  
**Created by:** Codex  
**Project:** Planes  
**Date:** August 1, 2026  
**Status:** approved strategic direction; no roadmap item has been implemented by this packet.

## 1. Current Goal

Build Planes into a general-purpose, agent-native programming language without losing its defining property: it shows what a program can do, what it did, and why. The user explicitly concurs with the language and performance directions in this packet and wants future work performed in the stated order.

## 2. Current State

Planes already has a working Python reference implementation, an independent JavaScript implementation, self-hosted grammar-language components, static effect analysis (Shapes), runtime provenance (`why`), governance rules, versioned drawing and sound protocols, and public Garden/Paint demonstrations.

The immediate architectural task is to turn these capabilities into stable contracts before growing syntax or pursuing native-speed execution. The immediate performance task is to remove repeated parse/module-graph work from interactive reruns before building a compiler or changing numerical semantics.

## 3. Active Intent

Primary intent: **plan**  
Target: an ordered language and performance roadmap  
Status: direction approved by the user; implementation planning is next  
Basis: explicit user instruction and approval in this conversation.

## 4. Verified Sources

| Source | Type | State | What was verified |
|---|---|---|---|
| `README.md` | language specification-by-implementation | verified | Separate computation, effect, provenance, governance, annotation, host, module, and grammar surfaces; Python and JavaScript implementations. |
| `grammar/` | JSON grammar plus self-hosted components | verified | Loadable vocabulary/errors/core/rules data; self-hosted lexer, parser, interpreter, and JSON path; current grammar metadata consistency. |
| `reports/REPORT_FOREIGN.md` | architecture report | verified | Foreign effect declarations are claims; unknown is preferred to falsely pure; external behavior is not statically proven. |
| `reports/REPORT_WHY_SELF_HOSTED.md` | architecture report | verified | Self-hosted runtime still has declared host/FFI/JSON capability gaps that must not be hidden behind a blanket self-hosted claim. |
| `reports/REPORT_FAIL_AND_PARSER_PROBE.md` | gap report | verified | Dynamic record lookup and recursion/precedence ergonomics are material language gaps. |
| `REPORT_GARDEN_ALIVE.md` and `benchmarks/density.md` | measurement reports | verified | Garden was measured end-to-end; repeated parse/module work is a large fixed cost; prior algorithmic rewrites delivered major gains. |
| `node scripts/measure-density.mjs` | current local benchmark | verified | This machine measured 604 JavaScript commands and 82 Python commands under the script's 60 ms threshold. This is machine-specific, not a release-wide performance claim. |
| Published Garden and Paint Pages | deployed demonstrations | inspected | Garden runs real Planes source with effect/provenance presentation; Paint demonstrates the language emitting a separate drawing protocol. |
| [CPython 3.11 specialization documentation](https://docs.python.org/3.11/whatsnew/3.11.html) | primary external research | verified | Adaptive specialization, inline caches, and superinstructions apply to hot, stable execution paths—not all code. |
| [WebAssembly goals](https://webassembly.org/docs/high-level-goals/) and [portability model](https://webassembly.org/docs/portability/) | primary external research | verified | Wasm separates portable core computation from host imports and is a possible later execution target. |

## 5. Inferred Claims

- **Inferred:** Planes' durable differentiation is not any single feature but its separable, inspectable planes: computation, effect surface, provenance, policy, annotations, and output protocols.
  - Basis: verified implementation/documentation structure and demonstrations.
- **Inferred:** A mature agent-facing language benefits more from auditable execution contracts than from accumulating familiar syntax quickly.
  - Basis: the user's goals and the verified foreign/host limitations.
- **Inferred:** Caching parsed program state will be the highest-return next interactive performance improvement.
  - Basis: measured fixed parse cost; must be validated after implementation.

## 6. Locked Decisions

- Preserve the separability of Planes' planes. Do not make effects, provenance, policies, rendering, or host access ambient language magic.
- Treat the Python interpreter as a semantic reference oracle while independent implementations and future execution engines are validated against it.
- Prioritize contracts, conformance, authority, receipts, and resource accounting before broad language growth.
- Prioritize caching and measurement before bytecode, JIT, or Wasm work.
- Preserve exact-number semantics and explanation quality; speed work may not silently approximate values or make `why` less truthful.
- Treat `foreign … doing …` as an unverified claim until a host authority and observation mechanism can enforce and record it.

## 7. Open Questions

| # | Question | Why it matters | Recommended resolution point |
|---|---|---|---|
| 1 | What is the exact language-release header and manifest syntax? | Determines reproducibility, modules, grammar compatibility, and cache keys. | Before package/version work. |
| 2 | What minimum provenance must every run retain? | Determines memory/performance trade-off without weakening `why`. | Before trace-tier optimization. |
| 3 | What is the missing-key behavior for dynamic record lookup? | Affects JSON/tooling/symbol-table ergonomics and error semantics. | Before adding the primitive. |
| 4 | What benchmark platform(s) define the public Garden interaction budget? | Prevents one developer machine becoming the language's performance truth. | Before enforcing performance regression policy. |
| 5 | Is the first portable execution target a Planes bytecode VM, Wasm, or both in sequence? | Determines implementation scope and conformance strategy. | Only after cache/profiler work. |

## 8. Active User Corrections

- Work as a rigorous subject-matter expert and thought partner, not as a generic language commentator.
- Ground conclusions in the repository, the language's evolution records, and the published demonstrations.
- Keep Planes' creative and purposeful uniqueness central to recommendations.
- Build in proper order; do not treat high-level agreement as authorization to skip design, conformance, or measurement work.

## 9. Context to Preserve

Planes is best understood as an **explainable execution substrate**. Its purpose is not merely to compute. It should let a person or agent inspect a program's possible effects before execution, its observed effects after execution, and the derivation behind a result.

The Garden is important evidence: it is not decorative output. It demonstrates real source, deterministic seeds, explicit effect surface, provenance attached to visible results, and performance measured against interaction targets.

The drawing and sound streams are versioned external protocols. This is a useful model for a missing language-level execution contract.

## 10. Work Completed

- Audited the grammar twice; the second audit confirmed that builtin metadata drift was fixed and the agent-readable grammar projections were strengthened.
- Audited language architecture, repository reports, implementations, tests, protocols, and published demonstrations.
- Verified focused grammar/core/Shapes suites: 16/16, 37/37, and 76/76 passing.
- Assessed current performance evidence and ran the density benchmark locally.
- Identified the ordered strategic direction in this packet.

## 11. Work Not Yet Completed

No roadmap feature below has been designed in implementation detail or built.

### Phase 0 — establish the contracts

1. Define a versioned language-release contract: language version, grammar version, standard library/modules, host interface, protocol versions, and dependency hashes.
2. Define a canonical AST/IR serialization and publish a conformance corpus covering parse, evaluation, effects, Shapes, provenance, rules, modules, and errors.
3. Define a structured run receipt: source/module hashes, inputs/seed, runtime/host versions, static surface, grants, observed effects, policy decisions, and provenance-query references.

**Acceptance criterion:** a third implementation/host can state exactly which Planes contract it supports and pass the same public fixtures.

### Phase 1 — make authority and cost enforceable

1. Introduce the authority distinction: **requested → granted → observed** effects. Enforce filesystem/destination allowlists and time/byte/rate budgets at the host boundary.
2. Add runtime resource budgets: execution steps, recursion depth, rational size, output bytes, and effect counts. Fail with ordinary Planes errors and relevant trace information.
3. Add explicit dynamic record lookup/iteration with a chosen missing-key contract; add precedence diagnostics and normalized recursion errors.
4. Add optional boundary contracts for functions, records, JSON, foreign calls, and protocols—without committing to a pervasive type-system rewrite.

**Acceptance criterion:** an agent can inspect a requested capability and resource budget before execution, while the host independently enforces both.

### Phase 2 — make interactive work fast without semantic compromise

1. Create a benchmark contract with cold/warm parse-load, Shapes, execution, provenance, render, memory, and p50/p95/worst-case measurements.
2. Cache source text, tokens, ASTs, resolved module graph, and static analysis for a program session, keyed by content hash plus language/grammar version.
3. Run every tick with a fresh runtime environment and effect record. Cache immutable program artifacts only.
4. Add cached-vs-uncached equivalence tests for output, effects, errors, Shapes, and provenance.
5. Introduce explicit evidence modes: normal receipt, full trace/`why`, and profiler counters. Never silently degrade the evidence collected.

**Acceptance criterion:** Garden-style repeated runs avoid reparsing unchanged modules and remain observationally identical to uncached runs.

### Phase 3 — improve the execution engine only where measurement supports it

1. Replace host-language recursive execution with an explicit Planes stack, trampoline, or bytecode VM to control depth and instruction accounting.
2. Profile actual hot paths: environment lookup, rational arithmetic, function calls, derivation allocation, output construction, and rendering.
3. Add semantics-preserving fast paths only for demonstrated hot paths.
4. Consider adaptive specialization only for stable, repeatedly executed paths; it must safely de-specialize and be invisible to program meaning.

**Acceptance criterion:** the new engine passes the canonical conformance corpus and emits equivalent receipts/traces for supported programs.

### Phase 4 — broaden portability and ecosystem deliberately

1. Add packages, private exports, dependency versions/locks, and effect-aware package descriptors.
2. Add an explicit task/workflow plane for cancellation, deadlines, retries, compensation, and resumable receipts. Do not introduce ambient callbacks as a substitute.
3. Only then evaluate compiling the pure Planes core to Wasm. Keep effects as host imports and preserve the interpreter as oracle.
4. Build LSP/editor/profiler support around the language's unique data: effect and provenance hovers, policy diffs, replay, and source mapping.

## 12. Do Not Claim Beyond This

- Do not claim full CI passed in this session. Focused suites passed; the full CI wrapper did not reach a confirmed final summary in this environment.
- Do not claim foreign effect declarations are verified, sandboxed, or enforced today. They are intentionally honest claims, not proof of outside behavior.
- Do not claim self-hosting is feature-complete across every host/FFI/JSON behavior; existing reports identify limitations.
- Do not claim the 604-command benchmark result is universally representative or a regression from the historical 877 number. It was one current-machine measurement.
- Do not begin a compiler, JIT, Wasm backend, global type system, or package manager before the preceding phase's contract and acceptance criteria hold.

## 13. Recommended Next Action

Start a dedicated **Phase 2 performance design session**. Its output should be a small, approved design for session-scoped parse/module/Shapes caching and a benchmark contract. It must state cache keys, invalidation, mutable-state boundaries, observability equivalence, benchmark workloads, and test gates.

This is the recommended next action because it has the clearest measured benefit, changes no user-visible language semantics, and establishes the discipline needed for all later optimization.

## 14. Handoff Notes for the Receiving Agent

- Read this packet before proposing code changes, then inspect the cited source files directly. Treat the packet as an ordered decision record, not a source of truth that replaces the repo.
- Keep static capabilities, host authority, observed effects, provenance, and render protocols as separate representations.
- For performance work, measure the real end-to-end user path. Do not use draw command count as a universal proxy for latency.
- Cache immutable parsed artifacts, never mutable environments or effect logs.
- Any optimization must have an equivalence test against the current reference behavior; correct output alone is insufficient—effects, errors, and `why` matter too.
- Existing dirty working-tree files are user-owned and unrelated to this packet: `js/grammar_data.mjs`, `js/interp.mjs`, `js/loader_node.mjs`, `js/parser.mjs`, `feat-core-sufficiency-benchmarks-pre.md`, and `js/core_restrict.mjs`. Preserve them unless the user explicitly scopes work to them.

## 15. Session Artifacts

| Artifact | Type | Path | Status |
|---|---|---|---|
| This packet | cross-agent actionable report | `reports/planes_handoff_2026_08_01_language_and_performance_roadmap.md` | delivered |
