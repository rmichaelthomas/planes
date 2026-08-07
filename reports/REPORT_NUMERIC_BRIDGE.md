# Horizon Phase 0 Build 4 — the numeric bridge: fixed-point unit convention and boundary quantization

**Date:** August 7, 2026
**Branch:** `feat/world-numeric-bridge`
**Base:** `main` at `cf55c36` (Build 3: deltas, snapshots, and the host-owned committed-event log)
**Scope:** The declared fixed-point unit convention over the existing `to_host`/`from_foreign` seam, outbound/inbound boundary quantization with `approx` marking, and the semantic-hash determinism rule (spec §9.4). No renderer, Pixi, Rapier integration, GPU code, asset, or agent work (Phase 1+). No change to the exact-rational core. **Last Phase 0 build.**

---

## 0. A discrepancy found and resolved before starting

The build prompt's file inventory names `interp.py` at SHA `d0c1537`. Current `main` carries `interp.py` at `7b988ee6`. Traced: `d0c1537` is `interp.py` as of commit `004778e` (R3, before Build 2); Build 2 (PR #84) added `world_envelopes`/`_maybe_emit_world_envelope` and two new imports to the file. `git diff 004778e -- interp.py` confirms the only changes are that addition — `to_host` and `from_foreign`, the two functions this build actually depends on, are byte-identical between both SHAs. The prompt's SHA reference is stale (written before Build 2 merged); the boundary seam this build needed was unaffected. Flagged to Rob at the time rather than silently worked around; proceeded on the verified-identical basis.

## 1. Phases completed

| Phase | Deliverable | Status |
|---|---|---|
| 1 | The fixed-point unit convention — `grammar/protocols/world-v1.json`'s `coordinates.numericBridge` defined, `situation.x`/`situation.y` carry `unit`/`places` | Done |
| 2 | Quantization at the boundary — `world_numeric_bridge.py`/`js/world_numeric_bridge.mjs`: outbound via `round_to`, inbound via `from_foreign` + pin, `approx` marking on lossy crossings only | Done |
| 3 | Determinism on semantic hashes — `is_deterministic`/`isDeterministic` reuse `world_delta.semantic_hash`; stated and tested | Done |

## 2. Files created

- `world_numeric_bridge.py`, `js/world_numeric_bridge.mjs` — the fixed-point unit convention, quantization boundary, and determinism rule
- `grammar/world_numeric_bridge.planes` — the self-hosted mirror of the REACHABLE half (quantization arithmetic + lossy/exact classification); see §5 for why the `approx`-marking half is not mirrored here
- `test_world_numeric_bridge.py` (17 tests), `js/test/world_numeric_bridge.test.mjs` (16 tests) — quantization correctness, `round_to` reuse, exact/lossy marking, inbound exactness, determinism
- `test_world_numeric_bridge_conformance.py` (4 tests) — Python/JS/.planes byte-identical quantization + Python/JS determinism-hash agreement
- `reports/REPORT_NUMERIC_BRIDGE.md` (this file)

## 3. Files modified

- `grammar/protocols/world-v1.json` — `coordinates.numericBridge` changed from a deferral string to a structured convention object (`status`, `convention`, `quantizeOutbound`, `quantizeInbound`, `determinism`, `units`); `situation.x`/`situation.y` gained `"unit": "world-position", "places": 3`. No other facet's fields changed — the build prompt names only `situation`'s continuous quantities, and `expression.depth` (a `normalized-number`, already bounded to `[0,1]`) was left alone as out of the named scope.
- `js/interp.mjs` — one line: `function fromForeign(x)` → `export function fromForeign(x)`. Purely a visibility change (Python's `from_foreign` was already importable, having no `__all__`); the function's body is untouched. This is the one JS-side accommodation the build prompt's §2 anticipated ("if the cleanest seam is a new module the boundary calls rather than an edit to `to_host`, prefer that") — `world_numeric_bridge.py`/`.mjs` are new modules that import `to_host`/`from_foreign` rather than modifying them.

## 4. Phase 1 — the fixed-point unit convention

A continuous quantity crossing to a physics/GPU host declares a `unit` name and a `places` integer — decimal places of fixed-point precision, i.e. `10^places` host subdivisions per one Planes unit. This is deliberately the simplest fixed-point shape that maps directly onto the language's own existing `round ... to N places`: a "declared scale" IS a decimal-places count, not a second, foreign notion of fixed-point the bridge would have to translate to and from. A field carries `unit`/`places` only when it is such a quantity; a field with neither key crosses via the existing `to_host` exactly as Builds 1-3 already do, unquantized — the convention is additive, not a mode switch.

`situation.x`/`situation.y` — the only continuous quantities the build prompt names — now declare `unit: "world-position"`, `places: 3` (0.001 Planes-unit precision). Integer semantic ticks (`schemaVersion`, `occupancy`, `timerTicks`, and every other `integer`-typed field across all seven facets) were verified to carry no unit and were left untouched — they are boundary-exact already, and `expression.depth` (the one other numeric-shaped field, a `normalized-number`) was likewise left alone since the build prompt names only `situation`'s quantities.

This is boundary metadata, not a value-model change: `world_ir.py`'s `_type_ok`/`_validate_record` read only `field["name"]`/`field["type"]` from each field spec and were never touched; a field's extra `unit`/`places` keys are inert to validation. Confirmed directly — `test_world_v1_json_declared_units_validate_through_build_1s_parser` builds a valid envelope against the CURRENT protocol file and asserts it normalizes cleanly with `unit`/`places` never leaking into the normalized record's own field values, and the full existing `test_world_ir.py`/`test_world_ir_conformance.py`/`test_world_runtime.py`/`test_world_delta*.py` suites (43 tests) were run standalone against the edited JSON before any bridge code was written, to isolate the JSON change's own blast radius — all green.

## 5. Phase 2 — quantization at the boundary

One function carries the whole discipline, in both languages: `quantize_outcome(value, places)` rounds via the existing `Number.round_to`/`roundTo` and reports whether the rounding changed the value (`rounded.q != value.q`). This is the entire REACHABLE arithmetic — four operators, `round ... to N places`, `==` — and it is what `grammar/world_numeric_bridge.planes` mirrors exactly, conformance-tested three ways by `test_world_numeric_bridge_conformance.py`.

`quantize(value, unit, places)` builds on it: a crossing whose rounding left the value unchanged, or a value that was already approximate before this call, crosses through unchanged; a crossing that genuinely lost exactness gets a new `Approximation("quantize", ...)` — the same shape `SINE_APPROXIMATION`/`ROOT_APPROXIMATION` already use, naming the unit and places as provenance. An already-approximate value (e.g. the result of `sine`) is deliberately NOT relabelled — its existing marker already discloses the non-exactness (`test_already_approximate_value_keeps_its_own_marker` / its JS twin confirm the SAME `Approximation` object survives quantization untouched).

**Why `.planes` cannot mirror the marking half.** An `Approximation` is an interpreter-internal record that `planes_num.py`/`planes_num.mjs` attach at a fixed handful of host-implemented builtin call sites (`sine`, `root`, and now the bridge's `quantize`). There is no Planes-level operation that constructs one from source — the same way there is no Planes-level operation that fabricates a sine-flavoured approximation without calling `sine`. `grammar/world_numeric_bridge.planes`'s own module docstring states this explicitly (failure mode S2: named, not silently uncovered) and the file covers the arithmetic half only — `quantize-outcome`/`canonical quantize outcome string`, returning `{rounded, lossy}` without an Approximation object.

`to_host_quantized(value, unit, places)` / `toHostQuantized` (outbound) and `from_host_quantized(raw, unit, places)` / `fromHostQuantized` (inbound) wrap `quantize` around the existing `to_host`/`from_foreign` for each crossing direction. Inbound exactness is the one place a genuinely new discipline appears versus Builds 1-3: `from_foreign`'s shortest-round-trip decimal already prevents float-bit noise from entering as a claimed-exact value, but a host float that does not sit exactly on the declared scale (`1.4999999999999998`, a plausible physics-engine output) still needs pinning — `test_from_host_quantized_pins_a_noisy_host_float_to_the_declared_scale` confirms it lands on `1.5`, exact-marked-approximate, naming the quantization; `test_from_host_quantized_exact_at_scale_stays_exact` and `...integer_stays_exact` confirm a clean value crosses unmarked.

`test_no_unmarked_lossy_crossing_across_many_values` sweeps `n/d` for `n` in `[-50, 50]` and `d` in `{1, 3, 7, 1000}` (204 values) and asserts the marking rule holds in both directions for every one — not just the hand-picked fixtures.

## 6. Phase 3 — determinism on semantic hashes

`is_deterministic(envelope_a, envelope_b)` / `isDeterministic` is `world_delta.semantic_hash(a) == world_delta.semantic_hash(b)` — the SHA-256-over-`canonical_outcome_string` Build 3's delta/event log already uses. This build adds no new comparison primitive, only the rule that this is the one determinism is judged on, stated in `world-v1.json`'s `coordinates.numericBridge.determinism` and tested directly: `test_identical_semantic_hashes_are_deterministic_even_if_a_hypothetical_host_float_differs` attaches a simulated "host-rendered" artifact (an object living OUTSIDE the world-v1 envelope entirely, e.g. `{hostRenderedX: 10.000000001}` vs `{hostRenderedX: 10.000000002}`) to two semantically-identical envelopes and confirms the verdict is unaffected by that difference; `test_a_genuine_semantic_divergence_is_caught_by_the_hash` confirms an actual field change is caught.

`test_world_numeric_bridge_conformance.py` extends this to cross-implementation agreement: `test_determinism_hash_agrees_across_python_and_js_for_identical_envelopes` and `...catches_a_genuine_semantic_divergence_in_both_implementations` compute `semantic_hash` in Python directly and in JS by shelling out to `js/world_delta.mjs`'s existing CLI (`{prev, next, revision}` → `canonical_delta_string`, parsing its `semantic-hash:` line) — reusing Build 3's own CLI entry point rather than adding a second one.

## 7. Verification gate — N+3.1

- Full existing suite (Python, `scripts/ci.sh`, no `--fast`): **all checks passed in 243.7s** — `83 files, 83 reporting, 1477 oks` (Build 3 stood at 81 files / 1456 oks; this build's own two test files add 17 + 4 = 21 of that growth exactly).
- `node --test js/test/*.mjs`: **919 tests, 919 pass, 0 fail** (Build 3 stood at 903; this build's `world_numeric_bridge.test.mjs` adds the 16 difference exactly).
- `check_js_tests.py`: 56 of 56 test-shaped `.mjs` files under `js/` are inside what the gate runs (up from 55 — the one new `js/test/world_numeric_bridge.test.mjs`).
- `ruff check .` / `mypy .`: clean, full repo (132 source files under mypy), including every file this build created or modified.
- `audit_locked_vs_built.py`: every locked construct still has code evidence in both implementations — this build introduced no new keyword, builtin, effect, or AST node, so nothing new to audit.
- `git diff main --stat` on `planes_num.py`, `js/planes_num.mjs`, `shapes.py`, `js/shapes.mjs`, `parser.py`, `lexer.py`, `grammar/*.planes` (excluding the new `world_numeric_bridge.planes`): empty.

Reproduce: `PATH="$PWD/.venv/bin:$PATH" scripts/ci.sh`.

## 8. The failability proof (§N+3.2)

`test_the_gate_is_capable_of_failing` in both `test_world_ir_conformance.py`'s established pattern and this build's own `test_world_numeric_bridge_conformance.py`: `python_quantize_string("1.4995", 3)`'s real output has `lossy=true`; a string with that substring replaced to `lossy=false` is confirmed `!=` the real output — the byte-for-byte comparison this gate runs is capable of observing a real divergence, not vacuously agreeing on mismatched strings.

## 9. Decision proofs (§N+3.2) — pass/fail table

| # | Proof | Method | Result |
|---|---|---|---|
| 1 | Boundary-only — no new numeric type inside the value model | `git diff main --stat` on `planes_num.py`/`js/planes_num.mjs`: empty (§7). `quantize`'s only planes_num.py imports are `Approximation` (unmodified) — no new class, no edit to `Number`, `round_to`, or `MAX_DENOMINATOR`. | **PASS** |
| 2 | Marked lossy crossing | `test_lossy_crossing_is_marked_with_a_named_approximation` / JS twin: `.approx.op == "quantize"`, detail names unit+places. `test_exact_crossing_stays_exact`: unmarked. Swept 204-way in `test_no_unmarked_lossy_crossing_across_many_values` — §5. | **PASS** |
| 3 | `round_to` reuse | `test_quantize_outcome_reuses_round_to_exactly`: `quantize_outcome(v, p).q == v.round_to(p).q` for a spread of values, Python; JS twin does the same via `roundTo`. `quantize_outcome`/`quantizeOutcome`'s body calls `round_to`/`roundTo` directly and nothing else. | **PASS** |
| 4 | Semantic determinism | `test_identical_semantic_hashes_are_deterministic_even_if_a_hypothetical_host_float_differs`, `test_a_genuine_semantic_divergence_is_caught_by_the_hash`, and their cross-implementation twins in the conformance suite — §6. | **PASS** |
| 5 | Parser green | `test_world_v1_json_declared_units_validate_through_build_1s_parser` — §4. Full `test_world_ir*`/`test_world_runtime*`/`test_world_delta*` suites unregressed (§7). | **PASS** |

| Test file | Result |
|---|---|
| `test_world_numeric_bridge.py` | 17/17 |
| `test_world_numeric_bridge_conformance.py` | 4/4 |
| `js/test/world_numeric_bridge.test.mjs` | 16/16 |
| Full suite (`scripts/ci.sh`) | all green, 243.7s |

## 10. Consistency check: no unauthorized diff

```
$ git diff main --stat -- planes_num.py js/planes_num.mjs shapes.py js/shapes.mjs \
    parser.py lexer.py js/parser.mjs js/lexer.mjs 'grammar/*.planes' | grep -v world_numeric_bridge
(no output — zero changes)
```

## 11. What this build did not do (by design)

- No renderer, Pixi, Rapier integration, GPU code, asset, or agent work — Phase 1+, out of scope per the build prompt.
- No change to `MAX_DENOMINATOR`, `Number`, `Approximation`, `round_to`, the thirteen builtins, the effect vocabulary, or the seven effect kinds.
- No `sine`/`root` behavior change — their `approx` provenance is exactly the marker this build's own `quantize` reuses the shape of, not modifies.
- No unit/scale declaration on `expression.depth` or any facet beyond `situation.x`/`situation.y` — the build prompt names only those two, and adding more would be scope beyond "the minimum the convention needs."
- No wiring of quantization into `WorldRuntime.envelope`'s per-tick conversion — there is no physics/GPU host yet to receive a quantized value on a live tick; this build defines the convention and boundary discipline a Phase 1+ host will call, and proves it directly against fixtures rather than against a host that does not exist.

Horizon Phase 0 is now complete: all four builds (world-v1 protocol, world runtime, deltas/snapshots/event log, the numeric bridge) are merged and verified in place. The open-question count from prior sessions is unchanged — this build implemented a locked decision (§9.4) and resolved no register question.
