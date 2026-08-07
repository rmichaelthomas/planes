# Horizon Phase 0 Build 3 — deltas, snapshots, and the host-owned committed-event log

**Date:** August 7, 2026
**Branch:** `feat/world-deltas-snapshots-event-log`
**Base:** `main` at `1074aed` (Build 2: world runtime — emission, source maps, and persistent invocation)
**Scope:** Monotonic deltas between two world-v1 envelopes; the host-owned, append-only, hash-chained committed-event log; durable snapshots; recovery by deterministic replay. No numeric-bridge fixed-point units (Build 4). No renderer/Pixi/asset work (Phase 1+). No Liminate/Seshat authority pipeline (§17-18) — a receipt is carried as an opaque host-supplied field only.

---

## 0. The governing decision: T-Q-Horizon

Locked in the session preceding this build, restated here as the rationale every choice in Phase 2 answers to:

> The committed-event log is a **host-owned, append-only, hash-chained store**, fed by the record plane — **not a Planes list**. Each event's semantic payload is a traced Planes value; its integrity envelope (sequence, previous-hash, receipt, witnessed `when`) is carried by the record/host layer. Recovery is deterministic replay under the standing replay-reconstructibility gate (v30.0 §474).

The value plane has no `hash` builtin and cannot chain events by content — that is the finding the decision routes around, not a limitation this build works around silently. Every hash in this build (delta semantic hashes, event-log chain hashes, snapshot integrity hashes) is computed in `world_delta.py`/`world_event_log.py`/`js/world_delta.mjs`/`js/world_event_log.mjs` — host/driver-layer Python and JavaScript, never inside `interp.py`/`js/interp.mjs`, never as a language builtin. §5 below is the grep proof.

## 1. Phases completed

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Monotonic deltas — `world_delta.py`/`js/world_delta.mjs` diff two normalized world-v1 envelopes into created/removed subjects, per-facet field patches, relation adds/removes, a revision counter, and a semantic hash | Done |
| 2 | The host-owned, append-only, hash-chained committed-event log — `world_event_log.py`/`js/world_event_log.mjs`, plus a new optional `Host.append_event`/`appendEvent` capability | Done |
| 3 | Durable snapshots and recovery-by-replay — `world_snapshot.py`/`.mjs`, `world_recovery.py`/`.mjs` | Done |

## 2. Files created

- `world_delta.py`, `js/world_delta.mjs` — the delta computation and its canonical text form
- `world_event_log.py`, `js/world_event_log.mjs` — the append-only, hash-chained event store
- `world_snapshot.py`, `js/world_snapshot.mjs` — durable capture/restore of a world value
- `world_recovery.py`, `js/world_recovery.mjs` — recovery by deterministic replay
- `test_world_delta.py` (14), `test_world_delta_conformance.py` (3), `test_world_event_log.py` (19), `test_world_snapshot.py` (8), `test_world_recovery.py` (6) — 50 new Python tests
- `js/test/world_delta.test.mjs` (14), `js/test/world_event_log.test.mjs` (18), `js/test/world_snapshot.test.mjs` (8), `js/test/world_recovery.test.mjs` (6) — 46 new JS tests
- `reports/REPORT_WORLD_EVENT_LOG.md` (this file)

## 3. Files modified

- `host.py` — one new optional method, `append_event(self, entry)`, alongside `record`/`snapshot`: a no-op default on `Host`; `TestHost` gets a real in-memory sink, `self.events`. **Reasoning for a new method rather than reusing `record`:** `record` is wired specifically to the interpreter's own per-effect-boundary bookkeeping — `maybe_record` calls it only when `Interpreter.record` is `True`, with entries shaped as `interp.py`'s own `Record` dataclass (kind/boundary/target/computed/anchor/when/derivation). `WorldRuntime` (Build 2) always constructs its interpreter with `record=False`, so `host.record` never fires for a world host in practice — but conflating a world-domain committed event with a language-level effect-boundary record in the same untyped sink would make the two indistinguishable once appended, and the build prompt's own §4 requirement 4 asks for a *dedicated* in-memory event sink, not reuse of `recorded`. `snapshot(fingerprint, entry)`, by contrast, genuinely is reused unchanged for Phase 3 (§7) — its `(fingerprint, opaque entry)` shape needed nothing new.
- `js/host.mjs` — the same `appendEvent(_entry) {}` no-op on `Host`, and a real `this.events = []` sink on `MemoryHost` (which `TestHost` inherits, mirroring `recorded`/`snapshots`).
- `js/test/drawing_invariants.test.mjs` — its own exhaustive `Host` surface enumeration (`"the Host interface is the same seven methods, plus record, snapshot, and targetHint"`) is the one place in the repo that lists every optional method by name, not just the required seven; it needed `appendEvent` added to that list, the same maintenance every build that adds an optional host method has to do here (this is the JS-side twin of `test_retention.py`/`test_replay.py`'s own copies of the "seven required" assertion — each build that touches the host re-affirms the count in its own words rather than editing a shared assertion).
- `js/host_node.mjs` — **not modified.** `NodeHost` extends `Host` directly and overrides neither `record` nor `snapshot`; it inherits the new `appendEvent` no-op automatically. The build prompt listed it as a file to modify defensively; nothing in it needed to change.

## 4. Phase 1 — deltas

`world_delta.compute_delta(prev_envelope, next_envelope, prev_revision)` takes two envelopes already normalized by `world_ir.parse_world_envelope` (exactly what `WorldRuntime.envelope` returns per tick) and returns a delta: `revision_from`/`revision_to` (always `prev_revision`/`prev_revision + 1`, regardless of content — advancing the counter is the driver's job, one delta per tick), `created_subjects`/`removed_subjects`, `facet_patches`, `relations_added`/`relations_removed`, and a `semantic_hash` (SHA-256 over `canonical_outcome_string`, full 64-char hex digest — not a truncated fingerprint, since this hash later feeds the event log's chain and the snapshot's corruption check, where collision resistance matters more than it does for `_seal`'s in-run comparison fingerprint).

**Single-subject scope, stated plainly.** `grammar/protocols/world-v1.json`'s records are flat — one `identity`, one `situation`, and so on — not keyed lists of many subjects. Build 1/2's actual world-v1 shape is one subject per envelope. "Created subject"/"removed subject" is therefore modeled as `identity.id` changing between tick N and N+1: the same id on both sides is one subject continuing (facet patches apply, walked in `FACET_ORDER`/`FIELD_ORDER`); a different id is that subject replaced wholesale, with no patches computed (there is no field-level correspondence between two different subjects). `relation` is walked separately from the generic per-facet-patch loop because the spec calls out "relation additions and removals" as their own bucket (§9.3): a relation appearing/disappearing produces a whole-record add/remove; a relation whose `relationId` changes is a remove-old-add-new pair; a relation whose `relationId` is stable but another field changed is a facet patch like any other facet's field change.

Determinism: every walk is in `FACET_ORDER`/`FIELD_ORDER` — world_ir.py's own fixed tuples — never raw dict iteration, so `canonical_delta_string` is byte-identical across construction orders (proven directly: `test_canonical_delta_string_is_deterministic_regardless_of_dict_construction_order` builds the same envelope with reversed dict insertion order and asserts identical output).

`test_world_delta_conformance.py` shells out to `node js/world_delta.mjs` (CLI mode, JSON on stdin, canonical text on stdout — the same convention `js/world_ir.mjs` established in Build 1) across six fixtures (patch, create-remove, relation-added, relation-removed, relation-replaced, no-op) and asserts byte-identical output, Python against JS. **3/3 passing.**

## 5. Phase 2 — the host-owned committed-event log

**The decision proof, first, since it is the one a diff cannot show by absence alone:**

```
$ grep -n "BUILTIN_NAMES\s*=" parser.py
(unchanged — 13 entries, confirmed below)
$ python3 -c "from parser import BUILTIN_NAMES; print(len(BUILTIN_NAMES))"
13
$ git diff main --stat -- shapes.py rules.py parser.py lexer.py 'grammar/*.planes' \
    js/shapes.mjs js/rules.mjs js/parser.mjs js/lexer.mjs
(no output — zero changes)
```

No `hash` builtin, no eighth effect kind, no value-model change. Every hash in this build is computed in `world_delta.py`/`world_event_log.py` (Python) and `js/world_delta.mjs`/`js/world_event_log.mjs` (JS), reusing `hashlib.sha256`/`sha256Hex` — the exact primitive `interp.py`'s `_seal` and `js/sha256.mjs` already use for the retention window's own fingerprint (R1, checkpoint v28.0 §441) — never anything new added to the language.

**Two layers, by design.** `append_event(events, payload, when, receipt=None)` and `verify_chain(events)` are pure functions over a plain list of entry dicts — not methods on a particular object — so a host's durably-persisted, later-reloaded log can be re-verified independent of whichever `WorldEventLog` instance originally produced it (this is what Phase 3's recovery leans on: a log read back from storage is exactly as verifiable as one built live). `WorldEventLog` is the stateful convenience wrapper: an in-memory ordered ledger, appending through the pure functions above and forwarding each new entry to the optional `host.append_event`/`appendEvent` for durability — off by default, a no-op on a host that keeps nothing, the same tier `record`/`snapshot` already occupy.

**The entry shape.** Semantic payload — `tick`, `actor`, `delta` (a `world_delta` dict or `None`), `affected_subjects`, `rationale` — is ordinary data, walked through `canonical_delta_string` when present. Integrity envelope — `format`, `sequence` (0-based, monotonic), `previous_hash` (the prior entry's own hash, or `GENESIS_HASH` — 64 zero characters — for the first), `when` (supplied by the caller, not fetched internally, so this module never needs a working `host.clock()` of its own — deliberate, since `ReplayHost.clock()` refuses by design and this module must stay usable during recovery), and an opaque `receipt` (`None` unless the caller supplies one; producing a real one is the Liminate/Seshat authority pipeline, §17-18, explicitly out of scope) — is added here, never inside the language.

**Append-only, verified three ways:**
1. `WorldEventLog`'s public surface is exactly `{append, events, verify}` — asserted directly (`test_the_public_surface_has_no_mutate_or_delete_method`, and its JS mirror against `Object.getOwnPropertyNames(WorldEventLog.prototype)`), and every one of `update`/`delete`/`remove`/`mutate`/`set`/`clear`/`pop`/`truncate` is confirmed absent.
2. `events()` returns a defensive deep copy (`copy.deepcopy`/`structuredClone`) — mutating a returned entry, or the returned list itself, is proven not to reach the log's own state.
3. Undo/redo (§13.3) are out of this build's own scope to implement, but the shape that makes them possible without destructive deletion — append an inverse event, or snapshot-and-replay past an unwanted one — is exactly what the append-only, no-mutate surface guarantees; nothing here forecloses it.

**Tamper detection, three shapes:**
- A naive tamper (edit an entry's payload, leave its own `hash` stale) is caught immediately, at that entry's own index — its stored hash no longer matches its recomputed content.
- A sophisticated tamper (edit an entry's payload AND recompute that entry's own `hash` to match) is still caught, at the NEXT entry — whose `previous_hash` was fixed to the original hash and cannot agree with the edited one. This is the chain property specifically, not merely a per-entry checksum, and it is tested as its own case (`test_tampering_an_earlier_event_and_recomputing_its_own_hash_still_breaks_the_chain`).
- Reordering two entries is caught the same way (`test_reordering_two_events_is_detected`).

**Versioned.** `events_to_json`/`events_from_json` (Python) and `eventsToJson`/`eventsFromJson` (JS) carry `format` and refuse an unrecognized one — mirroring `interp.py`'s `records_from_json`/`RECORD_FORMAT_VERSION` contract exactly, including the refuse-don't-guess wording.

**Required host surface: still seven.** `test_host.py::test_a_host_is_five_capabilities_a_resolver_and_a_json_reader` (18/18 in that file), `test_retention.py::test_seven_required_host_methods_unchanged` and `test_replay.py::test_seven_required_host_methods_unchanged_and_no_restore_added` — none of which this build touched — all still pass unmodified, plus this build's own copy, `test_world_event_log.py::test_seven_required_host_methods_unchanged_and_append_event_optional`. Four independent assertions of the same count, the established pattern in this repo (§3's note on why `js/test/drawing_invariants.test.mjs` needed updating rather than a shared assertion).

**19/19 Python, 18/18 JS passing.**

## 6. The failability proof (§N+3.2)

`world_event_log.py::verify_chain` was temporarily replaced with `return True, None` unconditionally:

```python
def verify_chain(events):
    return True, None  # FAILABILITY-PROOF MUTATION -- revert before commit
    """[docstring and real body, now unreachable]"""
    ...
```

**Mutated run** (`python3 test_world_event_log.py`): 5 of 19 tests failed — `test_reordering_two_events_is_detected`, `test_tampering_an_earlier_event_and_recomputing_its_own_hash_still_breaks_the_chain`, `test_tampering_an_earlier_events_payload_is_caught_at_its_own_slot`, `test_tampering_the_last_events_own_hash_is_detected`, `test_the_gate_is_capable_of_failing` — exactly the five tamper-detection tests, and none of the other 14 (append/sequence/versioning/host-forwarding tests are correctly unaffected by a broken verifier). `14/19 passing`.

**Reverted run:** file restored byte-for-byte from a pre-mutation copy (`diff` confirmed identical); `19/19 passing` again.

## 7. Phase 3 — snapshots and recovery

**Snapshots.** `world_snapshot.capture_snapshot(envelope, revision, host=None)` bundles `{revision, envelope, semantic_hash}` and persists through the host's existing, optional `snapshot(fingerprint, entry)` — reused completely unchanged; the fingerprint passed is the envelope's own semantic hash, content-addressed, matching `_seal`'s own fingerprint-keyed calling convention. `restore_snapshot` is the refuse-don't-guess reverse: a malformed wrapper (missing `revision`/`envelope`/`semantic_hash`), an envelope failing world-v1 validation (including an unsupported protocol version — this build deliberately does not invent a second, parallel snapshot-format-version field; it re-validates the envelope through `world_ir.parse_world_envelope`, so "versioned by world-v1.json's version" is the SAME version check that already exists, not a duplicate of it), or a semantic hash that no longer matches a freshly recomputed one over the envelope, all refuse, naming which. **8/8 Python, 8/8 JS passing.**

**Recovery = replay, and why it does not call `replay()` directly.** `interp.replay(steps, subject, ...)` re-executes an ordered list of SOURCE SNIPPETS, one `Interpreter.run` per step. `WorldRuntime` (Build 2) does not tick that way — it loads the module graph exactly once and then ticks by calling the already-loaded `world-init`/`advance` FUNCTIONS directly against one persistent interpreter. `world_recovery.recover` therefore reuses replay's two load-bearing pieces — `ReplayHost` and `trace=True` — directly, through `WorldRuntime`'s own `host=` constructor parameter: a `WorldRuntime` given a `ReplayHost` ticks through `world-init`/`advance` exactly as it always does, with every effect answered by reading a log back rather than performing it. This is documented in full in `world_recovery.py`'s own module docstring, including why there is no cheaper "resume from a checkpoint" path — no `Traced` value's derivation is reconstructible except by re-executing every step that produced it, the same constraint `replay()` itself already has.

**The snapshot is an integrity checkpoint, not a resume point.** Recovery always replays from `world-init` through the target tick; the snapshot's revision tells it how far to walk before checking, and what to check against — a snapshot whose envelope does not match what deterministic replay actually produces at its own declared revision refuses (`WorldRecoveryError`, tag `snapshot-replay-divergence`), rather than being trusted silently. This is a strictly stronger check than the snapshot's own self-consistency (§7's hash check): `test_recovery_refuses_when_snapshot_does_not_match_what_replay_actually_produces` constructs a snapshot that IS internally hash-consistent (its stored hash matches its own forged envelope) but was never actually produced by the program, and confirms recovery still refuses it.

**The one real scope note, resolved rather than silently narrowed.** `world_runtime_demo.planes` has exactly one host effect: the top-level `show demo-world` Build 2's own Phase 1 emission gate exercises, which fires every time `run_file`/`runFile` LOADS the program — including the fresh load `recover` performs. `WorldRuntime` always constructs its interpreter with `record=False` (Build 2), so it never accumulates a tick-level effect log during real operation, and there is no way to retroactively obtain one for a run that already happened. `world_recovery.py`'s `_module_load_effect_log`/`js/world_recovery.mjs`'s `moduleLoadEffectLog` resolves the one effect that DOES need answering: a fresh, throwaway `Interpreter(record=True)` re-runs `run_file` ALONE (module-level statements only, before any `world-init`/`advance` call) against a hermetic `TestHost`, and the resulting effect log is folded in ahead of whatever the caller supplies. This is not a workaround — the module load is exactly as deterministic and tick-independent as anything else this module replays, so its effect trace is exactly as reconstructible on demand. What remains genuinely out of reach: an `advance` that ITSELF performs a host effect, since `WorldRuntime` has no way to have recorded one in the first place. Flagged here and in both modules' docstrings, not silently narrowed past.

**Byte-identity, both halves of the gate.** `test_recovery_reconstructs_byte_identical_canonical_form_and_derivation` advances a world 10 ticks, snapshots at tick 4, and recovers via `recover(DEMO, snapshot, 6)`; it asserts both `canonical_outcome_string(recovered) == canonical_outcome_string(original)` AND `{card: explain(...), prompt: why_tree(...), machine: why_machine(...)}` computed on the recovered `Traced` world value equals the same computed on the original eager run's tick-10 value — the same three-register comparison R3's own `test_eager_and_replayed_derivations_agree_byte_for_byte_in_python` uses, applied at world scale. Two more cases cover a snapshot at tick 0 and a snapshot with zero ticks after it. **6/6 Python, 6/6 JS passing.**

## 8. Verification gate — N+3.1

- Full existing test suite (`scripts/ci.sh`, no `--fast`): **all checks passed in 223.4s** — `81 files, 81 reporting, 1456 oks` (Python; 76 at Build 2, +5 new test files this build adds, auto-discovered by the existing `test_*.py` glob — 14+3+19+8+6 = 50 of those 1456's growth) and `node --test`: `903 tests, 903 pass, 0 fail` (JS; 857 at Build 2, +46 this build — 14+18+8+6).
- `ruff` and `mypy`: clean across every file this build created or modified (`world_delta.py`, `world_event_log.py`, `world_snapshot.py`, `world_recovery.py`, `host.py`, and all five new `test_*.py` files individually confirmed, then the full-repo gate run confirmed the same).
- `check_js_tests.py`: 55 of 55 test-shaped `.mjs` files under `js/` are inside what the gate runs (up from 53 — the four new `js/test/*.test.mjs` files this build adds).
- `git diff main --stat` on `shapes.py`, `rules.py`, `parser.py`, `lexer.py`, `grammar/*.planes`, and their JS equivalents: empty (§5).

Reproduce: `PATH="$PWD/.venv/bin:$PATH" scripts/ci.sh`.

## 9. Decision proofs (§N+3.2) — pass/fail table

| # | Proof | Method | Result |
|---|---|---|---|
| 1 | No value-plane integrity | `grep`/`BUILTIN_NAMES` count (13, unchanged) + `git diff main --stat` on the static surface (empty) — §5 | **PASS** |
| 2 | Tamper detection | `verify_chain` mutated to always report success; 5/19 tamper-specific tests went red; reverted, byte-identical, 19/19 green — §6 | **PASS** |
| 3 | Append-only | `WorldEventLog`'s public surface asserted to be exactly `{append, events, verify}`; `update`/`delete`/`remove`/`mutate`/`set`/`clear`/`pop`/`truncate` all confirmed absent, Python and JS — §5 | **PASS** |
| 4 | Recovery byte-identity | 10-tick advance, snapshot at tick 4, recover via replay to tick 10: canonical form AND `{card, prompt, machine}` derivation match the pre-crash eager run byte-for-byte, Python and JS — §7 | **PASS** |
| 5 | Host surface unchanged | `test_host.py` (18/18), `test_retention.py`, `test_replay.py` (each carrying its own "seven required" assertion, all untouched by this build) plus this build's own copy in `test_world_event_log.py` all green — §5 | **PASS** |

| Test file | Result |
|---|---|
| `test_world_delta.py` | 14/14 |
| `test_world_delta_conformance.py` | 3/3 |
| `test_world_event_log.py` | 19/19 |
| `test_world_snapshot.py` | 8/8 |
| `test_world_recovery.py` | 6/6 |
| `js/test/world_delta.test.mjs` | 14/14 |
| `js/test/world_event_log.test.mjs` | 18/18 |
| `js/test/world_snapshot.test.mjs` | 8/8 |
| `js/test/world_recovery.test.mjs` | 6/6 |
| Full suite (`scripts/ci.sh`) | all green, 223.4s |

## 10. Consistency check: no unauthorized diff

```
$ git diff main --stat -- shapes.py rules.py parser.py lexer.py 'grammar/*.planes' \
    js/shapes.mjs js/rules.mjs js/parser.mjs js/lexer.mjs
(no output — zero changes)
```

## 11. What this build did not do (by design)

- No numeric-bridge fixed-point unit convention (Build 4) — `world-v1.json`'s `coordinates.numericBridge` note still names this deferred.
- No renderer, Pixi, asset, or agent work (Phase 1+).
- No Liminate/Seshat authority pipeline (§17-18) — `receipt` is carried as an opaque, host-supplied field; producing a real one is out of scope, stated in §5.
- No new builtin, effect, or value-model change of any kind (§5/§10).
- No self-hosted (`grammar/interp.planes`) mirror of delta computation — driver-level infrastructure a world program's own source never calls, matching Build 2's own precedent for not mirroring emission in the self-hosted stack.
- No implementation of undo/redo itself — only the append-only, no-mutate shape (§5) that makes appended-inverse-events-plus-replay possible without destructive history deletion, per §13.3.

The T-Q-Horizon architectural constraint — the committed-event log is host-owned, append-only, and hash-chained, never a Planes list — is now **closed in code**, not only in decision. Phase 0 Build 4 (the numeric-bridge fixed-point unit convention) remains. The open-question count from prior sessions is unchanged at sixteen — this build implemented a locked decision; it resolved no register question.
