// js/world_kernel.mjs — the JavaScript fixed-step kernel loop (Horizon
// Phase 1: the engine-kernel spike). Mirrors world_kernel.py's contract
// exactly; see that file's module docstring for the full timed-span
// rationale (build prompt §4, invariant 1).
//
// Node-only, for the same reason js/world_runtime.mjs is Node-only: it
// constructs a Node module loader through `load()`/`runFile`.

import { computeDelta } from "./world_delta.mjs";
import { WorldRuntime } from "./world_runtime.mjs";

// WorldRuntime.envelope() (js/world_runtime.mjs) is a direct pass-through
// of world_ir.mjs's parseWorldEnvelope, which returns { normalized,
// warnings } — asserted once here rather than assumed at each call site.

export class WorldKernelError extends Error {}

export class WorldKernel {
  constructor(path, { host = null, window = null, trace = true } = {}) {
    this.runtime = new WorldRuntime(path, { host, window, trace });
    this.revision = 0;
    this.prevEnvelope = null;
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
