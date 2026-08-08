// js/world_runtime.mjs — the JavaScript persistent-invocation driver
// (Build 2, §5). Mirrors world_runtime.py's contract exactly; see that
// file's module docstring for the full §12-items-1-6 mapping.
//
// Node-only (constructs a Node module loader through runFile, exactly as
// js/run_file.mjs itself is Node-only) — this is the Node-side counterpart
// to a browser world host, which is out of this build's scope (§32 —
// Phase 1+).

import { Interpreter, fromForeign, toHost } from "./interp.mjs";
import { PlanesNumber } from "./planes_num.mjs";
import { runFile } from "./run_file.mjs";
import { parseWorldEnvelope } from "./world_ir.mjs";
import { emitWorld } from "./world_emit_node.mjs";
import { loadGrammar } from "./loader_node.mjs";

export const WORLD_INIT = "world-init";
export const ADVANCE = "advance";

export class WorldRuntimeError extends Error {}

export class WorldRuntime {
  constructor(path, { host = null, window = null, trace = true } = {}) {
    this.itp = new Interpreter({ host, window, trace, record: false, emitWorld });
    this.path = path;
    this.world = null;
    this.tick = 0;
    this._loaded = false;
  }

  // The one and only load (§12 items 1-2): async because runFile's module
  // loader reads files over node:fs/promises. Must be awaited before
  // init()/advance() — a separate method, not folded into the constructor,
  // because a constructor cannot be async.
  async load() {
    loadGrammar();
    await runFile(this.itp, this.path);
    if (!this.itp.funcs.has(WORLD_INIT)) {
      throw new WorldRuntimeError(
        `'${this.path}' defines no '${WORLD_INIT}' function — a world program `
          + `must declare \`to ${WORLD_INIT}:\``,
      );
    }
    if (!this.itp.funcs.has(ADVANCE)) {
      throw new WorldRuntimeError(
        `'${this.path}' defines no '${ADVANCE}' function — a world program `
          + `must declare \`to ${ADVANCE} of world, tick, events:\``,
      );
    }
    const advanceParams = this.itp.funcs.get(ADVANCE).params;
    if (advanceParams.length !== 3) {
      throw new WorldRuntimeError(
        `'${this.path}' declares '${ADVANCE}' with ${advanceParams.length} `
          + `parameter(s), not 3 — a world program must declare `
          + `\`to ${ADVANCE} of world, tick, events:\``,
      );
    }
    this._loaded = true;
    return this;
  }

  init() {
    this._requireLoaded();
    this.world = this.itp.call(WORLD_INIT, [], this.itp.env, 0);
    this.tick = 0;
    return this.world;
  }

  // `events` (default: []) is a plain host list of typed event records,
  // converted through fromForeign — the same host-to-Planes boundary
  // conversion call_foreign already uses for a foreign call's return value
  // — and handed to mkLit, exactly as tick is on the line below. Passing
  // nothing reproduces the prior two-param self-driving behavior
  // byte-for-byte (build prompt invariant 1).
  advance(events = []) {
    this._requireLoaded();
    if (this.world === null) {
      throw new WorldRuntimeError(
        `advance() called before init() — call init() once to run '${WORLD_INIT}' `
          + "before any 'advance' batch",
      );
    }
    const tickTraced = this.itp.mkLit(PlanesNumber.of(this.tick));
    const eventsTraced = this.itp.mkLit(fromForeign(events), "events");
    this.world = this.itp.call(
      ADVANCE, [this.world, tickTraced, eventsTraced], this.itp.env, 0);
    this.tick += 1;
    return this.world;
  }

  // The current world value's world-v1 envelope (build prompt §5 acceptance
  // (a)): the same toHost/parseWorldEnvelope pair Phase 1 emission calls
  // from Show, reused here rather than duplicated, since advance's return
  // value is data the driver reads directly.
  envelope() {
    if (this.world === null) {
      throw new WorldRuntimeError("no current world value — call init() first");
    }
    const native = toHost(this.world.value);
    return parseWorldEnvelope(native);
  }

  _requireLoaded() {
    if (!this._loaded) {
      throw new WorldRuntimeError("load() must be awaited before init()/advance()");
    }
  }
}
