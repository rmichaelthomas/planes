// js/world_kernel.mjs — the JavaScript fixed-step kernel loop (Horizon
// Phase 1: the engine-kernel spike). Mirrors world_kernel.py's contract
// exactly; see that file's module docstring for the full timed-span
// rationale (build prompt §4, invariant 1).
//
// Node-only, for the same reason js/world_runtime.mjs is Node-only: it
// constructs a Node module loader through `load()`/`runFile`.
//
// RUNG 1 (Horizon Phase 1: the retention tail, build prompt §2) — MEASURED,
// NOT SHIPPED. V8 has no counterpart to CPython's `gc.freeze()` — no way
// from JS to move a set of objects permanently out of the collector's
// scan — so the Python fix ("shrink what the collector re-scans") has no
// JS equivalent. What V8 DOES expose, with `--expose-gc`, is
// `global.gc()`/`global.gc({type:'minor'})`: a synchronous, caller-
// triggered collection. This file CAN call it at the tick boundary
// (`gcInterval`, below) — but by default it does not, because measuring
// it (not assuming it) found it makes things worse, not better:
//
//   window=null, 1000 ticks: no forced gc ~200ms wall; global.gc() every
//   tick ~20,000ms wall (100x). window=300, 300 ticks: no forced gc
//   ~5.3ms/tick avg; global.gc() every tick ~11.5ms/tick avg (2.2x); even
//   every 10 ticks, ~6.25ms/tick avg (1.2x) — still worse than doing
//   nothing, at every interval tried, in both configurations.
//
// The reason tracks directly from the freeze gap above: `global.gc()`
// (major or minor) always does work proportional to the CURRENT heap/
// garbage volume, and every call pays that cost again — there is no way
// to make the SECOND call cheaper than the first the way Python's
// `gc.freeze()` does. V8's own automatic/incremental scheduler already
// spreads that same work out more cheaply than any schedule this file can
// force through the one lever `--expose-gc` exposes. So Rung 1's second
// technique ("control collection timing") has a real JS counterpart
// mechanically, but not a beneficial one — the measured, honest
// conclusion (build prompt §2: "an explicit recorded reason it cannot"),
// not a silent omission. `gcInterval` defaults to `Infinity` (never) for
// exactly this reason; it stays available, not deleted, so a future
// build with a different lever (e.g. `--max-semi-space-size` tuning,
// unexplored here) has a documented starting point and a baseline to beat.

import { computeDelta } from "./world_delta.mjs";
import { WorldRuntime } from "./world_runtime.mjs";

// WorldRuntime.envelope() (js/world_runtime.mjs) is a direct pass-through
// of world_ir.mjs's parseWorldEnvelope, which returns { normalized,
// warnings } — asserted once here rather than assumed at each call site.

export class WorldKernelError extends Error {}

export class WorldKernel {
  constructor(path, { host = null, window = null, trace = true, gcInterval = Infinity } = {}) {
    this.runtime = new WorldRuntime(path, { host, window, trace });
    this.revision = 0;
    this.prevEnvelope = null;
    this.gcInterval = gcInterval;
    this._ticksSinceGcMaintain = 0;
  }

  // The one and only load + world-init call. Async because WorldRuntime's
  // own load() is (its module loader reads files over node:fs/promises) —
  // must be awaited before step().
  async start() {
    await this.runtime.load();
    this.runtime.init();
    const { normalized, warnings } = this.runtime.envelope();
    if (warnings.length > 0) {
      throw new WorldKernelError(
        `world-init produced ${warnings.length} warning(s): ${warnings.join(", ")} — `
          + "a kernel fixture must parse clean (build prompt §3's 'warnings empty' bar), "
          + "or the step cost it produces is not measuring a valid world-v1 envelope",
      );
    }
    this.prevEnvelope = normalized;
    this.revision = 0;
  }

  // Advance one tick. Returns { delta, elapsedSeconds } — the caller hands
  // both to a sink AFTER this returns, so sink cost is never inside the
  // timed span below (build prompt §4, §8 invariant 1).
  step() {
    if (this.prevEnvelope === null) {
      throw new WorldKernelError("start() must be called before step()");
    }

    const t0 = performance.now();
    this.runtime.advance();
    const { normalized: nextEnvelope, warnings } = this.runtime.envelope();
    const delta = computeDelta(this.prevEnvelope, nextEnvelope, this.revision);
    const elapsedSeconds = (performance.now() - t0) / 1000;

    // Rung 1 (module docstring): OFF by default (gcInterval=Infinity) —
    // measured, not assumed, to make things worse on this fixture. Kept
    // as an opt-in for experimentation; when enabled, strictly after
    // elapsedSeconds is captured — never inside t0/performance.now()
    // above (build prompt invariant 2 / §6.2.D). Also a no-op unless the
    // process was started with --expose-gc.
    this._ticksSinceGcMaintain += 1;
    if (this._ticksSinceGcMaintain >= this.gcInterval) {
      if (typeof global !== "undefined" && typeof global.gc === "function") {
        global.gc();
      }
      this._ticksSinceGcMaintain = 0;
    }

    if (warnings.length > 0) {
      throw new WorldKernelError(
        `tick ${this.revision + 1} produced ${warnings.length} warning(s): `
          + `${warnings.join(", ")} — every tick must parse clean`,
      );
    }

    this.prevEnvelope = nextEnvelope;
    this.revision = delta.revisionTo;
    return { delta, elapsedSeconds };
  }
}
