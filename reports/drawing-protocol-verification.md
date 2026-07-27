# Drawing Protocol Verification (§12.2)

Run at commit `(uncommitted)`.

| Category | Check | Result | Detail |
|---|---|---|---|
| Protocol | every verb (26) plus protocol parses at correct arity | PASS |  |
| Protocol | every verb errors at wrong arity | PASS |  |
| Protocol | all five error tags fire | PASS |  |
| Protocol | every zero-arity verb name is prose when unprefixed | PASS |  |
| Protocol | a leading ~ is accepted and stripped from a number | PASS |  |
| Protocol | label preserves internal spaces and an embedded verb name | PASS |  |
| Painter | the reset table is applied at the start of every call | PASS |  |
| Painter | OKLCH matches fixed expected RGB triples, including a clamped case | PASS |  |
| Painter | arc converts degrees to radians with no flip, and wraps end past start | PASS |  |
| Painter | all four path-lifecycle errors fire | PASS |  |
| Painter | both transform-balance errors fire | PASS |  |
| Painter | an unsupported protocol version refuses the whole stream: nothing is drawn | PASS |  |
| Modules | Node and browser loaders produce identical graphs for the same tree | PASS |  |
| Modules | the three ModuleError messages are byte-identical across loaders | PASS |  |
| Modules | a cycle is caught (already exercised above; re-asserted standalone) | PASS |  |
| Modules | a collision is caught (already exercised above; re-asserted standalone) | PASS |  |
| Modules | the browser loader issues exactly one fetch per module per run | PASS |  |
| Invariants | the host surface is unchanged at 7 methods | PASS |  |
| Invariants | grammar/vocabulary.json is unchanged from b7adc34 | PASS |  |
| Invariants | builtin count is unchanged at 10 | PASS |  |
| Invariants | js/modules.mjs imports nothing from node: | PASS |  |
| Invariants | draw.planes's function set equals the protocol verb table minus protocol | PASS |  |
| Invariants | no show "draw outside draw.planes | PASS |  |
| Programs | all three programs parse | PASS |  |
| Programs | all three programs run and emit zero protocol/painter errors | PASS |  |
| Programs | effect surfaces match main (console for turtle/bloom; console+file for snake) | PASS |  |

**26/26 checks passed.**

All checks passed, including the three blocking categories (A, C, D).

Note: the per-tick benchmark regression (§12.1) is tracked separately in `reports/feat-module-loader-and-drawing-protocol-v1-benchmarks-post.md` — it is also a blocking item per §12.1, independent of the checks in this file.
