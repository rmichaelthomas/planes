"""world_recovery.py — recovery = replay (Horizon Phase 0 Build 3, Phase 3
— spec §22, the standing replay-reconstructibility gate, v30.0 §474).

Worker failure (§22): "Restart from the newest valid snapshot and replay
acknowledged events." This module is that restart, built on R3's own
replay discipline (interp.py's `ReplayHost` plus a tracing-on interpreter)
rather than a second, independent reconstruction mechanism — recovery is
deterministic re-execution, never state guessing.

WHY THIS DOES NOT CALL `replay()` DIRECTLY. `interp.replay(steps, subject,
...)` re-executes an ordered list of SOURCE SNIPPETS, one `Interpreter.run`
call per step — the shape a program built up statement-by-statement across
several `why` queries takes. `WorldRuntime` (Build 2) does not tick that
way: it loads the module graph exactly once (`run_file`) and then ticks by
calling the already-loaded `world-init`/`advance` FUNCTIONS directly against
one persistent interpreter (`itp.call`), never by handing it new source
per tick. These are two different calling conventions over the same
underlying discipline — tracing-on re-execution against a `ReplayHost` that
answers effects by reading them back, never by performing them — so
world-scale recovery reuses the discipline's two load-bearing pieces
(`ReplayHost`, `trace=True`) directly, through `WorldRuntime`'s own `host=`
constructor parameter (a `WorldRuntime` given a `ReplayHost` ticks through
`world-init`/`advance` exactly as it always does; nothing about `advance`'s
call shape changes), rather than force-fitting `replay()`'s step-list shape
onto a driver that was built, in Build 2, specifically to not need one.

SNAPSHOT AS INTEGRITY CHECKPOINT, NOT AS A RESUME POINT. There is no way to
seed an interpreter mid-chain with an already-built derivation graph — any
`Traced` value's provenance is only reconstructible by re-executing every
step that produced it, the same constraint `replay()` itself has (it always
replays every step from the first, never from a checkpoint). Recovery
therefore always replays from `world-init` through the target tick. The
snapshot's job is not to shorten that walk; it is to be verified along the
way — reached and hash-checked at its own declared revision — so a snapshot
that does not match what deterministic replay actually produces at that
revision is caught (`snapshot-replay-divergence`) rather than silently
trusted.

SCOPE: `advance` must be effect-free; module-level statements may not be.
`world_runtime_demo.planes` has one host effect — the top-level `show
demo-world` Build 2's own Phase 1 emission gate exercises — that `run_file`
performs every time a `WorldRuntime` LOADS the program, including the fresh
one `recover` below constructs. That load is deterministic and
tick-independent (it runs before `world-init` is ever called), so its
effect trace is exactly as reconstructible on demand as anything else this
module replays: `_module_load_effect_log` below re-runs `run_file` ALONE,
once, with `record=True`, against a hermetic `TestHost` (host.py — the
harmless host this repo already treats as safe to run for exactly this kind
of throwaway, deterministic pass), and folds the resulting effect log in
ahead of whatever `effect_log` the caller supplies for tick-level effects.
`WorldRuntime` itself always constructs its own interpreter with
`record=False` (Build 2), so it never accumulates a tick-level effect log
during real operation; an `advance` that performs an ask/read/write/show/
clock effect is out of this build's reach for that reason — the
`effect_log` parameter below is the seam a caller with such a log (from a
host that records its own ticks some other way) can still use, flagged
rather than silently ignored (see REPORT_WORLD_EVENT_LOG.md).
"""
from host import TestHost
from interp import Interpreter, ReplayHost
from world_ir import canonical_outcome_string
from world_runtime import WorldRuntime
from world_snapshot import restore_snapshot


def _module_load_effect_log(path):
    """The deterministic effect log `run_file(path)` ALONE produces —
    module-level statements only, before any `world-init`/`advance` call.
    Recomputed fresh each call, not cached: it is exactly as reproducible
    as any other replay this module performs, by the same determinism
    argument R3 already rests on."""
    loader = Interpreter(host=TestHost(), record=True, trace=False)
    loader.run_file(path)
    return loader.effect_log


class WorldRecoveryError(Exception):
    """A refusal naming the recovery rule it broke — the same tag/detail/
    fix shape this build's other error classes carry."""

    def __init__(self, tag, detail, fix):
        self.tag = tag
        self.detail = detail
        self.fix = fix
        super().__init__(f"{tag}: {detail}")


def recover(path, snapshot, ticks_after_snapshot, window=None, effect_log=None):
    """Reconstruct the world value at
    `snapshot['revision'] + ticks_after_snapshot` by deterministic replay
    of `path`'s `world-init`/`advance` — the newest valid snapshot plus the
    events (ticks) after it (spec §13.3/§22).

    Refuses (raising `world_snapshot.WorldSnapshotError`, propagated
    unchanged) if `snapshot` itself does not verify — an unsupported
    world-v1 protocol version or a semantic hash that no longer matches its
    own envelope. Refuses (raising `WorldRecoveryError`) if replay, having
    reached the snapshot's own declared revision, produces a DIFFERENT
    canonical form than the snapshot claims — a snapshot that is internally
    self-consistent yet was never actually produced by this program, a
    deeper corruption than a broken hash.

    Returns the `WorldRuntime` at the reconstructed tick; a caller reads
    `.envelope` for the canonical-form comparison and `.world` (a `Traced`)
    for the derivation comparison — `explain`/`why_tree`/`why_machine`
    against the pre-crash eager run's own tick-N value, exactly as R3's own
    eager-vs-replayed gate compares (v30.0 §474).
    """
    normalized_snapshot_envelope, snapshot_revision = restore_snapshot(snapshot)

    full_effect_log = _module_load_effect_log(path) + list(effect_log or [])
    host = ReplayHost(full_effect_log)
    rt = WorldRuntime(path, host=host, window=window, trace=True)
    rt.init()
    for _ in range(snapshot_revision):
        rt.advance()

    replayed_envelope, _warnings = rt.envelope
    expected = canonical_outcome_string(normalized_snapshot_envelope)
    actual = canonical_outcome_string(replayed_envelope)
    if actual != expected:
        raise WorldRecoveryError(
            "snapshot-replay-divergence",
            "the snapshot's envelope does not match what deterministic replay "
            f"of '{path}' actually produces at revision {snapshot_revision}",
            "recover from an earlier snapshot that replay can actually reach, or "
            "regenerate this snapshot from a real run of the program")

    for _ in range(ticks_after_snapshot):
        rt.advance()

    return rt
