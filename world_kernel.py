"""world_kernel.py — the fixed-step kernel loop (Horizon Phase 1: the
engine-kernel spike, build prompt §4).

Wraps one `WorldRuntime` (Horizon Phase 0 Build 2, read-only for this build):
`start()` calls `init()` once; each `step()` calls `advance()` once, converts
the result to a world-v1 envelope (`WorldRuntime.envelope`, itself
`to_host` + `world_ir.parse_world_envelope` — the exact pair Phase 1
emission already uses, not a second conversion path), and diffs it against
the previous tick's envelope via `world_delta.compute_delta`.

THE TIMED SPAN, STATED ONCE AND HELD TO (build prompt invariant 1). `step()`
times exactly: `WorldRuntime.advance()`, the envelope conversion that
necessarily sits between a raw Traced world value and anything
`compute_delta` can read, and `compute_delta()` itself. Nothing else is
inside `t0`/`elapsed` below — no sink call, no fixture construction, no
machine-spec capture. `scripts` reading this file for invariant B
("timing integrity") can check that by inspection: `sink.consume` (or any
sink call) never appears between the two `time.perf_counter()` reads.

Why the envelope conversion is IN the timed span and not treated as
overhead: design doc §11.1 puts "world delta production" inside the
simulation worker's own responsibilities, and a delta cannot exist without
first turning `advance`'s raw Traced return value into the envelope shape
`compute_delta` diffs. That conversion is real per-tick production work,
not a benchmarking artifact — excluding it would make the measured number
optimistic in a way invariant 1 exists to prevent (failure mode #1, build
prompt §9).
"""
import time

from world_delta import compute_delta
from world_runtime import WorldRuntime


class WorldKernelError(Exception):
    """The kernel's own contract, distinct from `WorldRuntimeError` (the
    persistent runtime's calling-convention contract) and from
    `world_ir.WorldIRError` (a returned value failing world-v1 validation) —
    raised only when `step()`/`start()` are called out of order, or when a
    tick's envelope carries a warning (§3's "warnings empty" acceptance bar
    applies every tick this kernel drives, not only at the fixture's own
    5-tick smoke test)."""


class WorldKernel:
    """Drives one `WorldRuntime` on a fixed-step schedule.

    `window`/`trace`/`host` pass straight through to the `WorldRuntime` this
    holds, at its own defaults (`window=None`, `trace=True`) unless a caller
    overrides them — this build does not invent a third configuration
    on top of what Build 2 already exposes. `trace=True` is not optional
    window-dressing: design doc §12 item 7 requires the runtime to
    "preserve derivations and `because` annotations across revisions", and
    that only holds with tracing on (R3, interp.py's own module docstring).
    """

    def __init__(self, path, host=None, window=None, trace=True):
        self.runtime = WorldRuntime(path, host=host, window=window, trace=trace)
        self.revision = 0
        self.prev_envelope = None

    def start(self):
        """Run `world-init` once. Not part of the per-tick measurement —
        it runs exactly once per kernel lifetime, not once per tick, so it
        has no place in a per-step distribution."""
        self.runtime.init()
        envelope, warnings = self.runtime.envelope
        if warnings:
            raise WorldKernelError(
                f"world-init produced {len(warnings)} warning(s): {warnings} — "
                "a kernel fixture must parse clean (build prompt §3's "
                "'warnings empty' bar), or the step cost it produces is not "
                "measuring a valid world-v1 envelope")
        self.prev_envelope = envelope
        self.revision = 0

    def step(self):
        """Advance one tick. Returns `(delta, elapsed_seconds)` — the
        caller is responsible for handing both to a sink AFTER this
        returns, so the timed span above never includes sink cost (§4,
        §8 invariant 1). Raises `WorldKernelError` if `start()` was never
        called, or if the tick's envelope carries a warning."""
        if self.prev_envelope is None:
            raise WorldKernelError("start() must be called before step()")

        t0 = time.perf_counter()
        self.runtime.advance()
        next_envelope, warnings = self.runtime.envelope
        delta = compute_delta(self.prev_envelope, next_envelope, self.revision)
        elapsed = time.perf_counter() - t0

        if warnings:
            raise WorldKernelError(
                f"tick {self.revision + 1} produced {len(warnings)} "
                f"warning(s): {warnings} — every tick must parse clean")

        self.prev_envelope = next_envelope
        self.revision = delta["revision_to"]
        return delta, elapsed
