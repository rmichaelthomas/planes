// js/world_emit_node.mjs — Node-only bridge wiring Interpreter's optional
// `emitWorld` hook (interp.mjs) to js/world_ir.mjs + js/world_source_map.mjs.
//
// interp.mjs must stay browser-loadable (grammar_data.mjs's own comment:
// "No shared module statically imports node:fs, so every one of them loads
// in a browser tab") and world_ir.mjs / world_source_map.mjs both read the
// filesystem directly, so interp.mjs cannot import either of them itself.
// Its Show case instead calls `this.emitWorld` — an optional, synchronous,
// dependency-injected hook, null (and therefore a no-op) unless a Node-only
// caller supplies one. This file is that supply: pass the function this
// builds as an Interpreter constructor's `emitWorld` option and Build 2
// emission is live; omit it (as every existing browser page does,
// unchanged) and interp.mjs behaves exactly as it did before this build.

import { parseWorldEnvelope } from "./world_ir.mjs";
import { formatSourceMapPath } from "./world_source_map.mjs";

// (native, entryFile, line) -> { normalized, warnings }, or throws
// WorldIRError. `native` is interp.mjs's own toHost() conversion of the
// shown value — plain objects/arrays/numbers/strings/booleans, the same
// native form the affordance facet's `affordance.sourceMapTarget` gets
// overwritten on in place before validation (never merely filled in when
// absent), the same way interp.py's `_maybe_emit_world_envelope` does it.
export function emitWorld(native, entryFile, line) {
  if (native.affordance && typeof native.affordance === "object") {
    const target = formatSourceMapPath(entryFile, line);
    if (target !== null) native.affordance.sourceMapTarget = target;
  }
  return parseWorldEnvelope(native);
}
