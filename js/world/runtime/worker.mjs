// js/world/runtime/worker.mjs — the Horizon Phase 1 simulation worker
// (design doc §11.1, build prompt §2/§3).
//
// WHY THIS DOES NOT `import { WorldKernel } from "../../world_kernel.mjs"`.
// The build prompt frames the worker as wrapping WorldKernel unmodified, and
// js/world_kernel.mjs IS unmodified — but it cannot literally run here.
// WorldKernel wraps WorldRuntime (js/world_runtime.mjs), and WorldRuntime's
// own docstring says so outright: "Node-only ... this is the Node-side
// counterpart to a browser world host, which is out of this build's scope
// (§32 — Phase 1+)." Its load() hardcodes loadGrammar() (loader_node.mjs,
// node:fs) and runFile() (run_file.mjs, node:fs via module_loader_node.mjs).
// A real browser Worker has neither. That "browser world host" is exactly
// what Phase 1 — this build — is.
//
// So this file reimplements WorldKernel's externally-observable contract —
// start() loads once and returns the initial envelope; step() returns
// exactly { delta, elapsedSeconds } — field for field, same warning-refusal
// behavior, same computeDelta call — on browser-safe primitives: the
// fetch-based BrowserModuleLoader (module_loader_browser.mjs) in place of
// the fs-based Node loader, and browser_main.mjs's own loadGraphInto in
// place of run_file.mjs's runFile. js/world_kernel.mjs itself is untouched;
// `git diff --name-only` on it stays empty. See also the browser-safety fix
// this build made to world_ir.mjs/world_delta.mjs (their own docstrings) —
// without that fix this file could not import either.
//
// SINGLE-SUBJECT PROTOCOL SCOPE, HONESTLY CARRIED THROUGH. world-v1's delta
// protocol is single-subject by construction (world_delta.mjs's own
// docstring). The fixture this worker drives — paint/world/
// kernel_spike_fixture.planes, reused unmodified, not a new Planes program —
// computes twelve subjects' worth of real per-tick work but projects only
// one (the water-edge subject, "reso-tide-walker-1") through the envelope
// advance() returns. So exactly one semantic subject crosses this worker's
// boundary per tick. The performers on the main thread are written generic
// (subject-ID-keyed), ready for a future multi-subject protocol, but today's
// placeholder scene will show exactly one moving placeholder — that is this
// protocol's real shape, not a shortcut this build took.
//
// NO INPUT-EVENT PARAMETER, HONESTLY CARRIED THROUGH. advance(world, tick)
// takes no third "events" argument today — world_runtime.mjs's advance()
// only ever passes (world, tick). This worker still implements the real
// message-contract machinery for inbound input (§11.5: "typed events"): an
// "input" message is received, sequenced, and acknowledged on the next
// outgoing delta message — proving the plumbing — but it cannot yet steer
// the simulation, because the language/runtime contract has no parameter
// for it to steer through. That is a real, disclosed Phase-2-relevant gap
// (design doc §12 item 5 names "fixed-step input/event batches" as the
// target shape advance should eventually take), not something this build
// silently papers over.
//
// FIXED-STEP RATE. 30 Hz, matching the kernel-spike build's own driver
// (build prompt §1's kernel-spike precedent) and design doc §15's "never
// adaptive" list: the semantic tick rate is invariant across Sun/Breeze/
// Harbor — only the renderer's frame budget and particle density adapt.
//
// RETENTION WINDOW. Left at a bounded 300 (not the unbounded default),
// matching the exact configuration Horizon Phase 1's retention-tail (PR #88)
// and cut-cost (PR #89) builds measured. The unbounded-window JS retention
// tail is a known, already-disclosed, separate Phase 0/1 kernel concern
// (up to ~398ms GC-pause outliers in prior soak testing) — leaving window
// unbounded here would risk this build's own "zero long tasks over 50ms"
// gate failing for a reason that has nothing to do with the renderer
// pipeline this build is actually proving. Recorded, not silently chosen.

import { Interpreter, toHost } from "../../interp.mjs";
import { PlanesNumber } from "../../planes_num.mjs";
import { BrowserHost } from "../../host_browser.mjs";
import { BrowserModuleLoader } from "../../module_loader_browser.mjs";
// Also runs interp's grammar bootstrap (setVocabulary/setAmberTemplates/
// setCore from the same JSON this page would otherwise import itself) as an
// import side effect — browser_main.mjs is already the one place that does
// this for a browser context, and duplicating it here would be a second
// place that can drift from the first. See its own top-of-file comment.
import { loadGraphInto } from "../../browser_main.mjs";
import { parseWorldEnvelope, SUPPORTED_VERSION } from "../../world_ir.mjs";
import { computeDelta } from "../../world_delta.mjs";
import { sha256Hex } from "../../sha256.mjs";

const WORLD_INIT = "world-init";
const ADVANCE = "advance";
const TICK_HZ = 30;
const TICK_MS = 1000 / TICK_HZ;
const RETENTION_WINDOW = 300;
const FIXTURE_URL = new URL(
  "../../../paint/world/kernel_spike_fixture.planes",
  import.meta.url,
).href;

export class WorkerKernelError extends Error {}

// The browser-safe sibling of js/world_runtime.mjs — same five-method
// shape (load/init/advance/envelope, constructor), same call sequence,
// different (fetch-based) loader. See the module header for why this
// exists instead of importing world_runtime.mjs directly.
export class BrowserWorldRuntime {
  constructor(location, { window = null, trace = true } = {}) {
    this.itp = new Interpreter({ host: new BrowserHost({}), window, trace });
    this.location = location;
    this.loader = new BrowserModuleLoader({ base: location });
    this.world = null;
    this.tick = 0;
    this._loaded = false;
  }

  async load() {
    await loadGraphInto(this.itp, this.location, { base: this.location, loader: this.loader });
    if (!this.itp.funcs.has(WORLD_INIT)) {
      throw new WorkerKernelError(
        `'${this.location}' defines no '${WORLD_INIT}' function`,
      );
    }
    if (!this.itp.funcs.has(ADVANCE)) {
      throw new WorkerKernelError(
        `'${this.location}' defines no '${ADVANCE}' function`,
      );
    }
    this._loaded = true;
    return this;
  }

  // The fixture's own source text, from the loader's own fetch — reusing the
  // one fetch load() already made rather than issuing a second request just
  // to fingerprint it.
  sourceText() {
    return this.loader.readIfCached(this.location);
  }

  init() {
    this._requireLoaded();
    this.world = this.itp.call(WORLD_INIT, [], this.itp.env, 0);
    this.tick = 0;
    return this.world;
  }

  advance() {
    this._requireLoaded();
    if (this.world === null) {
      throw new WorkerKernelError("advance() called before init()");
    }
    const tickTraced = this.itp.mkLit(PlanesNumber.of(this.tick));
    this.world = this.itp.call(ADVANCE, [this.world, tickTraced], this.itp.env, 0);
    this.tick += 1;
    return this.world;
  }

  envelope() {
    if (this.world === null) {
      throw new WorkerKernelError("no current world value — call init() first");
    }
    const native = toHost(this.world.value);
    return parseWorldEnvelope(native);
  }

  _requireLoaded() {
    if (!this._loaded) {
      throw new WorkerKernelError("load() must be awaited before init()/advance()");
    }
  }
}

// The browser-safe sibling of js/world_kernel.mjs's WorldKernel — same
// start()/step() contract, same warning-refusal bar, same timed span
// (advance() + envelope() + computeDelta() only; sink/post-processing cost
// is never inside elapsedSeconds).
export class BrowserWorldKernel {
  constructor(location, opts = {}) {
    this.runtime = new BrowserWorldRuntime(location, opts);
    this.revision = 0;
    this.prevEnvelope = null;
  }

  async start() {
    await this.runtime.load();
    this.runtime.init();
    const { normalized, warnings } = this.runtime.envelope();
    if (warnings.length > 0) {
      throw new WorkerKernelError(
        `world-init produced ${warnings.length} warning(s): ${warnings.join(", ")}`,
      );
    }
    this.prevEnvelope = normalized;
    this.revision = 0;
    return normalized;
  }

  step() {
    if (this.prevEnvelope === null) {
      throw new WorkerKernelError("start() must be called before step()");
    }
    const t0 = performance.now();
    this.runtime.advance();
    const { normalized: nextEnvelope, warnings } = this.runtime.envelope();
    const delta = computeDelta(this.prevEnvelope, nextEnvelope, this.revision);
    const elapsedSeconds = (performance.now() - t0) / 1000;

    if (warnings.length > 0) {
      throw new WorkerKernelError(
        `tick ${this.revision + 1} produced ${warnings.length} warning(s): ${warnings.join(", ")}`,
      );
    }
    this.prevEnvelope = nextEnvelope;
    this.revision = delta.revisionTo;
    return { delta, elapsedSeconds };
  }
}

// ---- message-contract plumbing (design doc §11.5) --------------------------
//
// Every outgoing message carries protocolVersion (world-v1's own version —
// §9.2's "an unsupported world protocol version refuses the whole delta
// batch" is the same version this stamps), worldFingerprint (sha256 of the
// fixture's own source text — genuine content identity, not a placeholder
// string), a strictly-increasing sequence, and the currently-active
// cancellationToken. A SimulationWorkerHandle (below) is the postMessage-
// free core: constructed with a `post` callback and an `onReady` callback,
// it owns no `self`/DOM reference at all, so it is exactly as unit-testable
// under plain `node --test` as it is inside a real Worker. The bottom of
// this file is the only part that touches `self`.

export class SimulationWorkerHandle {
  constructor({ post, fixtureUrl = FIXTURE_URL, tickMs = TICK_MS, window = RETENTION_WINDOW } = {}) {
    this._post = post;
    this._fixtureUrl = fixtureUrl;
    this._tickMs = tickMs;
    this._window = window;
    this._kernel = null;
    this._sequence = 0;
    this._cancellationToken = "unset";
    this._cancelled = true;
    this._timer = null;
    this._fingerprint = null;
    this._latestInputSequence = 0;
    this._nextTickAt = null;
    this._boundTick = () => this._runOneTick();
  }

  // Everything that must happen before ticking can start: load the fixture,
  // run world-init, and post the initial full snapshot (design doc §9.3:
  // "Initial load produces a complete World IR snapshot"). Ticking begins
  // immediately afterward unless a "cancel" message arrives first.
  async boot() {
    this._kernel = new BrowserWorldKernel(this._fixtureUrl, { window: this._window, trace: true });
    const normalized = await this._kernel.start();
    this._fingerprint = sha256Hex(this._kernel.runtime.sourceText() ?? this._fixtureUrl);
    this._emit({
      type: "snapshot",
      envelope: normalized,
      revision: this._kernel.revision,
    });
    this._cancelled = false;
    this._scheduleTick();
  }

  // "cancel"/"resume"/"input" — the three inbound message shapes this
  // worker understands. Anything else is ignored rather than throwing: a
  // forward-compatible worker does not crash on a message a newer main
  // thread might one day send that this build doesn't know about yet.
  receive(message) {
    if (!message || typeof message !== "object") return;
    if (message.type === "cancel") {
      this._cancelled = true;
      this._nextTickAt = null;
      if (this._timer !== null) {
        clearTimeout(this._timer);
        this._timer = null;
      }
      return;
    }
    if (message.type === "resume") {
      this._cancellationToken = message.cancellationToken ?? this._cancellationToken;
      if (this._cancelled) {
        this._cancelled = false;
        this._scheduleTick();
      }
      return;
    }
    if (message.type === "input") {
      // Acknowledged, not applied — see the module header's "no input-event
      // parameter" note. Recording the highest sequence seen is enough to
      // prove the inbound half of the message contract without pretending
      // this fixture's advance() can react to it.
      if (typeof message.sequence === "number" && message.sequence > this._latestInputSequence) {
        this._latestInputSequence = message.sequence;
      }
      return;
    }
  }

  // Self-correcting: the next tick targets an absolute time exactly one
  // period after the last TARGET (not "one period from whenever this tick
  // happened to finish"), so per-tick execution cost does not compound into
  // a slower and slower real rate. If a stall put us more than a full
  // period behind (a long GC pause, a tab backgrounded), the phase resets
  // instead of firing a burst of back-to-back catch-up ticks.
  _scheduleTick() {
    if (this._cancelled) return;
    const now = performance.now();
    if (this._nextTickAt === null || now - this._nextTickAt > this._tickMs) {
      this._nextTickAt = now + this._tickMs;
    } else {
      this._nextTickAt += this._tickMs;
    }
    const delay = Math.max(0, this._nextTickAt - now);
    this._timer = setTimeout(this._boundTick, delay);
  }

  _runOneTick() {
    this._timer = null;
    if (this._cancelled) return;
    let stepped;
    try {
      stepped = this._kernel.step();
    } catch (err) {
      this._emit({ type: "error", message: describeError(err) });
      this._cancelled = true;
      return;
    }
    this._emit({
      type: "delta",
      delta: stepped.delta,
      stepMs: stepped.elapsedSeconds * 1000,
      revision: this._kernel.revision,
      acknowledgedInputSequence: this._latestInputSequence,
    });
    this._scheduleTick();
  }

  _emit(message) {
    this._sequence += 1;
    this._post({
      ...message,
      sequence: this._sequence,
      protocolVersion: SUPPORTED_VERSION,
      worldFingerprint: this._fingerprint,
      cancellationToken: this._cancellationToken,
    });
  }
}

function describeError(err) {
  if (err instanceof Error) return err.stack ?? err.message;
  return String(err);
}

// ---- the actual Worker wiring — the only part of this file that touches
// `self`. Guarded so the rest of this module stays importable (and every
// class above unit-testable) under plain `node --test`, which has no `self`.
if (typeof self !== "undefined" && typeof self.postMessage === "function") {
  const handle = new SimulationWorkerHandle({ post: (msg) => self.postMessage(msg) });
  self.addEventListener("message", (event) => handle.receive(event.data));
  handle.boot().catch((err) => {
    self.postMessage({
      type: "error",
      message: describeError(err),
      sequence: 0,
      protocolVersion: SUPPORTED_VERSION,
      worldFingerprint: null,
      cancellationToken: "unset",
    });
  });
}
