// js/paint/loop.mjs — the tick loop (A.2, A.3).
//
// A Planes program is called with its input: composePrelude renders the
// tick's inputs — `tick`, `keys`, `pointer`, `state` — as ordinary Planes
// literal bindings, prepended to the program source. No event handler, no
// callback and no loop of any kind exists inside a Planes program; the loop
// itself is requestAnimationFrame, driven from here.
//
// State crosses the tick boundary through the VFS, one direction only (A.3):
// outbound, the program does `write state to "state.json"`; inbound, this
// module reads `files["state.json"]` out of the returned host, JSON.parses
// it, and renders it back as next tick's `state` literal. `read` is never
// used for state and no JSON parsing happens inside Planes.

import { runProgram } from "../browser_main.mjs";

function stringLiteral(s) {
  let out = '"';
  for (const ch of s) {
    if (ch === '"') out += '\\"';
    else if (ch === "\\") out += "\\\\";
    else if (ch === "\n") out += "\\n";
    else if (ch === "\t") out += "\\t";
    else out += ch;
  }
  return out + '"';
}

// Numbers thread through as plain decimal text — tick counters, grid
// coordinates and scores in this build are always small integers or simple
// decimals, never large enough to need JS's exponential notation.
function numberLiteral(n) {
  if (!Number.isFinite(n)) {
    throw new Error(`cannot render ${n} as a Planes number literal`);
  }
  return String(n);
}

// Renders any JSON-shaped JS value (what JSON.parse hands back from
// state.json, or a plain literal composed for the prelude) as Planes source
// text. This is the one direction JSON crosses back into the language, and it
// crosses as source text, not as a parsed-JSON builtin (A.3).
export function planesLiteral(value) {
  if (value === null || value === undefined) return "nothing";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return numberLiteral(value);
  if (typeof value === "string") return stringLiteral(value);
  if (Array.isArray(value)) return "[" + value.map(planesLiteral).join(", ") + "]";
  if (typeof value === "object") {
    const fields = Object.entries(value).map(([k, v]) => `${k}: ${planesLiteral(v)}`);
    return "{ " + fields.join(", ") + " }";
  }
  throw new Error(`cannot render ${String(value)} as a Planes literal`);
}

export function composePrelude({ tick, keys, pointer, state }) {
  return (
    [
      `let tick = ${planesLiteral(tick)}`,
      `let keys = ${planesLiteral(keys)}`,
      `let pointer = ${planesLiteral(pointer)}`,
      `let state = ${planesLiteral(state)}`,
    ].join("\n") + "\n"
  );
}

// Runs one tick: composes the prelude, runs the whole program, paints
// nothing itself (the caller does that with js/paint/painter.mjs) but reports
// the output lines and the next state. Never throws — a program error comes
// back as `error`, exactly as runProgram already reports it (rule 3: a
// recursion-too-deep error is reported as itself, not swallowed).
export function step(src, context) {
  const prelude = composePrelude(context);
  const { output, effects, files, error } = runProgram(prelude + "\n" + src, {});
  if (error) {
    return { lines: output, state: context.state, surfaceSafe: false, error };
  }

  let nextState = context.state;
  if (files && Object.prototype.hasOwnProperty.call(files, "state.json")) {
    try {
      nextState = JSON.parse(files["state.json"]);
    } catch {
      return {
        lines: output,
        state: context.state,
        surfaceSafe: false,
        error: { tag: "bad-state-json", message: "state.json did not parse as JSON" },
      };
    }
  }

  // A runtime corroboration of the static effect surface this build promises
  // (A.3): a tick's actual effects should never touch the network boundary.
  const surfaceSafe = !effects.some(([kind]) => kind === "ask");

  return { lines: output, state: nextState, surfaceSafe, error: null };
}

// Drives `step` from a scheduler — requestAnimationFrame in a real page, or
// an injected fake under test (Node has no rAF). Three rules, from §3:
//   1. an erroring tick stops the loop and shows the error, rather than
//      silently skipping a frame;
//   2. never more than one runProgram call per animation frame, and a frame
//      is skipped rather than queued if the previous call has not returned;
//   3. a recursion-too-deep error is reported as itself (step already does
//      this — createLoop just doesn't hide it).
export function createLoop({
  getSource,
  getKeys,
  getPointer,
  initialState = null,
  onFrame,
  schedule,
  cancel,
  stepEveryNFrames = 1,
}) {
  const sched =
    schedule ||
    (typeof requestAnimationFrame !== "undefined"
      ? requestAnimationFrame
      : (fn) => setTimeout(fn, 16));
  const cancelFn =
    cancel || (typeof cancelAnimationFrame !== "undefined" ? cancelAnimationFrame : clearTimeout);

  let running = false;
  let pending = false;
  let tick = 0;
  let state = initialState;
  let handle = null;
  let framesSinceStep = 0;

  function frame() {
    if (!running) return;
    // requestAnimationFrame runs at the display's rate (commonly 60Hz), which
    // is far too fast for a human to react to in a grid-stepped game like
    // snake — the loop itself stays rAF (A.2), but a Planes tick need not
    // land on every one of its callbacks. stepEveryNFrames > 1 skips callbacks
    // between ticks; it never causes more than one runProgram call per
    // animation frame, only fewer.
    framesSinceStep += 1;
    if (framesSinceStep < stepEveryNFrames) {
      handle = sched(frame);
      return;
    }
    framesSinceStep = 0;
    if (pending) {
      // The previous call has not returned — skip this frame rather than
      // queue another on top of it (rule 2). step() is synchronous today, so
      // this never actually triggers; it is here so the invariant holds if
      // that ever changes.
      handle = sched(frame);
      return;
    }
    pending = true;
    const context = { tick, keys: getKeys(), pointer: getPointer(), state };
    const result = step(getSource(), context);
    pending = false;
    tick += 1;

    if (result.error) {
      running = false;
      onFrame(result);
      return; // rule 1: stop, don't skip
    }

    state = result.state;
    onFrame(result);
    handle = sched(frame);
  }

  return {
    start() {
      if (running) return;
      running = true;
      handle = sched(frame);
    },
    stop() {
      running = false;
      if (handle !== null) cancelFn(handle);
      handle = null;
    },
    reset() {
      running = false;
      if (handle !== null) cancelFn(handle);
      handle = null;
      tick = 0;
      state = initialState;
    },
    isRunning() {
      return running;
    },
  };
}
