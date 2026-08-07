# Horizon Phase 0 Build 1 — World IR protocol (world-v1) and its three-implementation parser

**Date:** August 6, 2026
**Branch:** `feat/world-v1-protocol-and-parser`
**Base:** `main` at `c854438`
**Scope:** Language-and-protocol substrate only. No Pixi, no assets, no agent, no renderer. Parses and validates a world envelope; does not wire `show` to emit one (Build 2), does not implement deltas/snapshots/the event log (Build 3), does not touch the numeric-bridge unit convention (Build 3/4).

---

## 1. Phases completed

| Phase | Deliverable | Status |
|---|---|---|
| 1 | `grammar/protocols/world-v1.json` — the World IR host-protocol contract | Done |
| 2 | Three parser/validator implementations — `world_ir.py`, `js/world_ir.mjs`, `grammar/world_ir.planes` — plus their unit tests | Done |
| 3 | `test_world_ir_conformance.py` — the cross-implementation byte-identical agreement gate, with a demonstrated failability proof | Done |

## 2. Files created

- `grammar/protocols/world-v1.json`
- `world_ir.py`
- `js/world_ir.mjs`
- `grammar/world_ir.planes`
- `test_world_ir.py`
- `js/test/world_ir.test.mjs`
- `test_world_ir_conformance.py`
- `reports/REPORT_WORLD_V1.md` (this file)

No other file was created or modified. `docs/superpowers/specs/2026-08-01-horizon-living-passage-game-engine-design.md` carries Rob's own pre-existing uncommitted edit (the canonical visual acceptance artifact, §24.4) — untouched by this build, and not staged into any commit this build makes.

## 3. Envelope shape this build settles on

The build prompt frames a world envelope as "a record/dict of records" and cites `interp.py`'s `records_from_json` for the version-refusal shape specifically — a flat top-level field, not a nested record. This build settles the envelope as:

```
{ "version": 1, "identity": {...}, "situation": {...}, "relation": {...},
  "behavior": {...}, "expression": {...}, "affordance": {...}, "lineage": {...} }
```

One instance per §8 facet — the full World IR for a single subject. Multi-subject batching, deltas, and snapshots are §9.3 concerns explicitly deferred to Build 3; this build proves the per-subject contract the later ones will batch.

## 4. Facet fields and new types

Every field traces to a spec §8.1–§8.7 bullet; ambiguous bullets were translated conservatively (noted below) rather than expanded into invented authority.

| Facet | Critical | Fields |
|---|---|---|
| identity | yes | id, kind, subkind, displayName, status, schemaVersion |
| situation | yes | containingPlace, space, x, y, state, occupancy, anchorId, chunkActive, physicsRef, audioRef |
| relation | no | relationId, relationType, fromId, toId, provenance |
| behavior | no | eventPattern, transition, timerTicks, condition, stateMachine, emittedEvent, failurePath |
| expression | no | assetId, layer, depth, animationState, material, lightingResponse, particleIntent, colliderId, sensorId, audioAnchor, fidelityVariant, accessibleAlt |
| affordance | no | action, precondition, valueShape, preview, inverse, authorityRequired, explanation, sourceMapTarget, fallback |
| lineage | yes | corpusSource, culturalStatus, author, origin, because, agreementFingerprint, permittedTransformations, publishingRestriction, systemBoundary |

Identity, situation, and lineage are critical: a subject without an identity or a place to be isn't describing anything, and a subject without lineage/authority can't be safely governed under §18/§20. Relation, behavior, expression, and affordance are optional: a static or decorative subject can legitimately carry none of them.

**Relation's spec-named fields `from`/`to` were renamed `fromId`/`toId`.** `from` and `to` are both reserved words in the Planes grammar (`from` is a full keyword; `to` opens a function definition), so neither can be a bare `when`-pattern field binding in `grammar/world_ir.planes`. Renaming in the protocol keeps all three implementations naming the same field — the alternative (Python/JS keep `from`/`to`, Planes alone renames) would have been the exact drift this build's own invariants forbid.

**New field types**, none of which scene-v1.json needed:

- `text` — any text value, may be empty. Distinguishes free-form strings (display names, rationale) from `identifier`'s non-empty-symbol constraint.
- `semantic-id` — a stable identity cross-reference. Validated identically to `identifier` (non-empty text) in this build; a real uniqueness/registry check needs the identity registry a later build defines, so this type exists to name the intent now without overclaiming enforcement it can't yet deliver.
- `source-map-path` — non-empty text, forward-declared for Build 2's source maps. Validated identically to `identifier` today.
- `boolean` — `true`/`false` only. `chunkActive` needed a real tri-state-free flag that no existing scene-v1 type carried.

`identifier`, `integer`, `number`, and `normalized-number` are reused from scene-v1.json's own vocabulary; `positive-number` was not needed by any facet field and is not used here.

**Conservative simplification, disclosed per the build prompt's Failure Mode #2 discipline:** a record missing more than one required field is reported as "the record is missing one or more required fields," without naming which field. `when r is { f1, f2, ... }:` matches (or refuses) all named fields at once — there is no way to test one field's presence at a time when the field name would otherwise be a runtime value, and ordinary Planes has no way around that (no `typeof`, no dynamic field enumeration). Rather than let the self-hosted implementation diverge from Python/JS on this one case, `_validate_record` (Python) and `validateRecord` (JS) were written to the same all-at-once rule. Once presence holds, a wrong-typed field is named precisely, in declared order, in all three.

## 5. The type-probe idiom (self-hosted implementation)

`grammar/world_ir.planes` has no `typeof`/`kind of` builtin to call, and `when subject is {...}:` raises `not-a-record` immediately if `subject` isn't record-shaped — it cannot be used defensively to test "is this a record" the way a language with a safe `isinstance` could. Every type check in the file is instead a **probe**: attempt an operation that only succeeds for the wanted shape, and catch its failure with `or fail as`:

- text — `upper of v`
- number — `whole of v`
- boolean — `v == true`
- record — `when v is {}:`

`+`, `count of`, and `==` never coerce between kinds in this language (the value model's own rule), which is what makes a probe a genuine type test rather than a guess.

## 6. The four invariants

1. **Value model, effects, seven effect kinds, static surface, and thirteen builtins unchanged.** `git diff main --stat` shows no changes to `interp.py`, `js/interp.mjs`, `grammar/interp.planes`, `shapes.py`, `rules.py`, or the builtin table (confirmed empty diff on each, §7 below). This build adds a protocol and three validators over the existing value model; it introduces no builtin, effect, or value kind.
2. **`world-v1.json` is the single source of the contract.** `world_ir.py` and `js/world_ir.mjs` both read `grammar/protocols/world-v1.json` directly at import time — there is exactly one place the field/type/criticality table is declared for those two. `grammar/world_ir.planes` cannot read JSON at runtime (no host JSON import from a `.planes` module), so it carries the same table as hand-written Planes, matching `world-v1.json` field for field; `test_world_ir_conformance.py` is what holds it honest, not a second copy anyone edits independently — the same seam `js/scene_vocab.mjs`/`paint/scene.planes` already use.
3. **Refusal parity is byte-identical.** All six required fixtures (§8 below) produce byte-identical `tag`/`detail`/`fix` text across Python, JS, and self-hosted Planes. This did not hold on the first pass — see §9, two real divergences the gate caught and this build fixed before merge.
4. **No coercion at the type boundary.** `_type_ok` (Python) and `typeOk` (JS) check `bool` before the numeric types specifically because Python's/JS's runtime otherwise treats a boolean as interchangeable with `0`/`1` at points; the self-hosted probes achieve the same by construction (a boolean fails the `whole of` numeric probe, and a number fails the `== true` boolean probe, since `==` itself refuses cross-type comparison). A version field of `true` is refused as `unsupported-world-protocol-version`, not silently accepted as version `1`, in all three implementations — this exact case is covered in `test_world_ir.py`/`js/test/world_ir.test.mjs` conceptually via the `bool`-before-numeric ordering, and directly guarded in `world_ir.py`'s version check (`isinstance(version, bool) or version != SUPPORTED_VERSION`).

## 7. Consistency check: no unauthorized diff

```
$ git diff main --stat -- interp.py js/interp.mjs grammar/interp.planes shapes.py rules.py
(no output — zero changes)
```

## 8. Fixture pass/fail table

Six required fixtures per the build prompt's acceptance table, plus the failability row. `python==js==planes` is the byte-identical comparison of the canonical outcome string (see `test_world_ir_conformance.py`'s docstring for its format); `shape ok` additionally checks the agreed-upon result matches the fixture's *expected* accept/refuse decision and tag, so three implementations wrongly agreeing would still fail this table.

| Fixture | python==js==planes | shape ok | Result |
|---|---|---|---|
| valid | True | yes | PASS |
| bad-version | True | yes | PASS |
| missing-critical | True | yes | PASS |
| malformed-critical-field | True | yes | PASS |
| malformed-optional-field | True | yes | PASS |
| unknown-optional | True | yes | PASS |
| failability (mutate → red → revert → green) | — | — | PASS (see §9) |

Reproduce: `python3 test_world_ir_conformance.py`.

## 9. The failability proof

Per §N+3.2, `world_ir.py`'s version check was temporarily mutated to accept every version:

```python
# before (real code):
if isinstance(version, bool) or version != SUPPORTED_VERSION:
    raise WorldIRError("unsupported-world-protocol-version", ...)

# injected mutation:
if False:  # INJECTED MUTATION for the failability proof — accepts any version
    raise WorldIRError("unsupported-world-protocol-version", ...)
```

**Mutated run** (`python3 test_world_ir_conformance.py`): the `bad-version` fixture's `python==js==planes` cell flipped to `False` — Python wrongly accepted a version-2 envelope while JS and Planes correctly refused it — and both tests in the file failed.

```
bad-version                  False                no         FAIL
  FAIL  test_all_fixtures_agree_byte_for_byte_across_all_three_implementations: ...
  FAIL  test_the_gate_is_capable_of_failing: the comparison must be able to observe this divergence
0/2 passing
exit code: 1
```

**Reverted run** (mutation removed, file restored byte-for-byte): all fixtures passed again.

```
2/2 passing
exit code: 0
```

The gate is capable of failing, and was observed to fail on exactly the class of defect it exists to catch (one implementation silently drifting from the other two).

## 10. Real divergences the gate caught during this build

The conformance gate is not a formality here — it found two genuine byte-level mismatches between the self-hosted implementation and Python/JS before this build reached green, both fixed in the same session:

1. **Fix-clause text drift.** `grammar/world_ir.planes`'s malformed-record fix clause said `"...so every field world-v1 declares..."`; Python and JS both say `"...so every field world-v1.json declares..."`. One missing `.json` — exactly the kind of divergence that reads fine in isolation and fails byte-identical comparison.
2. **Missing type name in the malformed-field detail.** The self-hosted `check-field` helper originally returned only the failing field's *name*; Python/JS's detail text also names the field's *declared type* (`"...fails its declared type 'integer'"`). Fixed by having `check-field` build the full reason string, matching word for word.

Both are recorded here per the standing "a bug found while checking your own work is still a bug found" discipline — fixed in this build, not deferred.

## 11. Verification gate — N+3.1

- Full existing test suite (`scripts/ci.sh`, no `--fast`): **all checks passed in 199.6s** — `72 files, 72 reporting, 1374 oks`. This includes `test_world_ir.py`, `test_world_ir_conformance.py`, and `js/test/world_ir.test.mjs`, auto-discovered by the existing `test_*.py` / `js/test/*.mjs` globs with no registration step needed.
- `ruff` and `mypy` on the three new Python files: clean.
- `git diff main --stat` on the five protected files: empty (§7).

## 12. What this build did not do (by design)

- No `show` emission wiring — envelopes are validated, not produced from a running program (Build 2).
- No source maps (Build 2).
- No `world-init`/`advance` persistent-invocation convention (Build 2/3).
- No deltas, revision checks, snapshots, or the host-owned hash-chained event log (Build 3, per this session's locked decision).
- No numeric-bridge fixed-point unit convention — `coordinates.numericBridge` in `world-v1.json` names this explicitly as deferred rather than silently omitting it (Build 3/4).
- No builtin, effect, or value-model change of any kind (§6.1, §7).

Phase 0 Builds 2–4 remain: structured-`show` emission with source maps and persistent invocation; deltas/snapshots/the event log; the numeric-bridge unit convention. The open-question count from prior sessions is unchanged at sixteen — this build resolved no register question; it is scheduled substrate work.
