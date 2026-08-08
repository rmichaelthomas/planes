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

RUNG 1 (Horizon Phase 1: the retention tail, build prompt §2). The
engine-kernel spike found the tail's cause directly: CPython's cyclic
collector pays a periodic full-collection pass over the live `Deriv`
graph, and that pass gets more expensive every tick the graph grows,
because a full collection traces every object in the oldest generation on
every run, whether or not a cycle is actually present.

The graph does not need that tracing at all. `interp.py`'s `Deriv.inputs`
is populated only from nodes `mk()` already built — the interpreter's own
monotonically increasing `_generation` counter stamps every node at
construction, before its `inputs` are attached, so an edge can only ever
point to a STRICTLY OLDER node. No node built later can be assigned into
an older node's `inputs` (the only place a back-edge could live), so a
cycle through `Deriv` alone is not merely absent by observation, it is
unreachable by construction. Reading `Env` (`parent`-only, never a list of
children), `Function` (its closure `env` is never itself stored back into
that env — Planes has no first-class function values, so `self.funcs`,
not `Env.vars`, is the only place a `Function` lives), and `Host`/
`WorldRuntime` (neither holds a reference back to the `Interpreter`) turns
up no other cycle either. So the cyclic collector's periodic scan of this
graph is pure waste: refcounting alone already reclaims every `Deriv` the
moment `_cut` drops the last reference to it (`gc.freeze()`/`gc.disable()`
change only which objects the CYCLE detector re-scans, never whether
plain reference counting deallocates something — an object's refcount
reaching zero frees it immediately regardless of its freeze/generation
state).

The fix below hands collection timing to the one safe point a fixed-step
kernel already has — between ticks, outside the timed span — instead of
CPython's own allocation-threshold heuristic, which has no way to know a
step is in progress and can just as easily land mid-`advance()`:

  1. `gc.disable()`, once, in `__init__` — stops the automatic scheduler
     from ever firing inside a step. This is a process-wide setting
     (`gc` is not object- or interpreter-scoped); a `WorldKernel` is the
     long-lived driver of a whole session, so it owning this for as long
     as it is stepping ticks is the same shape as it owning `t0`/`elapsed`
     below.
  2. `gc.collect()` at the tick boundary — reclaims anything actually
     unreachable (a real cycle, if one exists anywhere else in the
     process) while it is still discoverable, at a point we chose rather
     than one CPython chose.
  3. `gc.freeze()` right after — moves everything that survived into the
     permanent generation, so future collections (of either kind) never
     re-scan it. Safe unconditionally, not just for the nodes a window
     will never cut: freezing does not extend any object's lifetime or
     change when refcounting frees it (point above), so a node `_cut`
     later drops is reclaimed the instant that happens whether or not it
     was ever frozen.

`gc_interval` (ticks between maintenance calls, default every tick) is
exposed so a caller — `world_tail_bench.py` among them — can measure
whether a coarser cadence changes the trade, without a code change.
"""
import gc
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

    def __init__(self, path, host=None, window=None, trace=True, gc_interval=1):
        self.runtime = WorldRuntime(path, host=host, window=window, trace=trace)
        self.revision = 0
        self.prev_envelope = None
        self.gc_interval = gc_interval
        self._ticks_since_gc_maintain = 0
        # Rung 1 (module docstring): hand collection timing to the tick
        # boundary below, process-wide, for as long as this kernel steps.
        gc.disable()

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

    def step(self, events=None):
        """Advance one tick. Returns `(delta, elapsed_seconds)` — the
        caller is responsible for handing both to a sink AFTER this
        returns, so the timed span above never includes sink cost (§4,
        §8 invariant 1). Raises `WorldKernelError` if `start()` was never
        called, or if the tick's envelope carries a warning.

        `events` (default: none, i.e. the empty batch) is per-tick
        production work — the input-event seam's own marshalling — and so
        stays inside the timed span below exactly like the envelope
        conversion already does (build prompt §3.3 / invariant 5); it is
        passed straight through to `WorldRuntime.advance`, which is where
        the host-to-Planes conversion actually happens."""
        if self.prev_envelope is None:
            raise WorldKernelError("start() must be called before step()")

        t0 = time.perf_counter()
        self.runtime.advance(events)
        next_envelope, warnings = self.runtime.envelope
        delta = compute_delta(self.prev_envelope, next_envelope, self.revision)
        elapsed = time.perf_counter() - t0

        # Rung 1 (module docstring): collector maintenance at the tick
        # boundary, strictly after `elapsed` is captured — never inside
        # t0/elapsed (build prompt invariant 2 / §6.2.D).
        self._ticks_since_gc_maintain += 1
        if self._ticks_since_gc_maintain >= self.gc_interval:
            gc.collect()
            gc.freeze()
            self._ticks_since_gc_maintain = 0

        if warnings:
            raise WorldKernelError(
                f"tick {self.revision + 1} produced {len(warnings)} "
                f"warning(s): {warnings} — every tick must parse clean")

        self.prev_envelope = next_envelope
        self.revision = delta["revision_to"]
        return delta, elapsed
