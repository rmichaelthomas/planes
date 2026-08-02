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

import { runProgram, runProgramGraph } from "../browser_main.mjs";

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

// `seed` is a fifth prelude binding, alongside tick/keys/pointer/state: a
// fixed number for a tick to read, never state (it is never threaded back
// out through state.json — a program that wants it to vary ticks itself,
// the way `tick` already does). Defaults to 0 so this stays a neutral,
// program-agnostic default — a program that cares what value it starts at
// (paint/garden.planes, whose placement functions read it) is passed one
// explicitly by whatever page is driving it, the same way a program that
// cares about `tick` is driven by a loop or a scrubber rather than reading
// this module's own idea of a sensible tick.
export function composePrelude({ tick, keys, pointer, state, event = null, seed = 0 }) {
  return (
    [
      `let tick = ${planesLiteral(tick)}`,
      `let keys = ${planesLiteral(keys)}`,
      `let pointer = ${planesLiteral(pointer)}`,
      `let state = ${planesLiteral(state)}`,
      `let event = ${planesLiteral(event)}`,
      `let seed = ${planesLiteral(seed)}`,
    ].join("\n") + "\n"
  );
}

// How many lines this module prepends before a program's own first line.
// `composePrelude` ends with a newline and `step`/`stepGraph` add one more
// between it and the source, so a program's line 1 is this many lines down.
// Computed from the prelude itself, never counted by hand.
export const PRELUDE_LINES = composePrelude({
  tick: 0,
  keys: [],
  pointer: { x: 0, y: 0, down: false },
  state: null,
}).split("\n").length;

// The interpreter counts lines in what it was HANDED, which is the prelude
// plus the program. A caller who handed over a program wants line numbers in
// that program — otherwise every trace entry points six lines past where the
// reader is looking, and a why panel titles a mark with `use sound`. Rebased
// here, where the prelude is added, rather than in the interpreter, which
// correctly knows nothing about any of this.
function rebaseTrace(trace) {
  return trace.map(([node, line]) => [node, line - PRELUDE_LINES]);
}

// The shared tail of a tick, once a runProgram-shaped result is in hand:
// thread state.json back out as next tick's state, rebase the trace onto the
// program's own line numbers, and corroborate the static effect surface
// (A.3) — a tick's actual effects should never touch the network boundary.
function stepResult(context, { output, trace = [], annotations = {}, effects, files, error }) {
  trace = rebaseTrace(trace);
  if (error) {
    return { lines: output, trace, annotations, state: context.state, surfaceSafe: false, error };
  }

  let nextState = context.state;
  if (files && Object.prototype.hasOwnProperty.call(files, "state.json")) {
    try {
      nextState = JSON.parse(files["state.json"]);
    } catch {
      return {
        lines: output,
        state: context.state,
        trace,
        annotations,
        surfaceSafe: false,
        error: { tag: "bad-state-json", message: "state.json did not parse as JSON" },
      };
    }
  }

  const surfaceSafe = !effects.some(([kind]) => kind === "ask");
  // `trace` and `annotations` ride alongside `lines`: one trace entry per
  // line, in the same order, so a caller that knows which line it is looking
  // at knows where that line came from without a second run.
  return { lines: output, trace, annotations, state: nextState, surfaceSafe, error: null };
}

// Runs one tick: composes the prelude, runs the whole program, paints
// nothing itself (the caller does that with js/paint/painter.mjs) but reports
// the output lines and the next state. Never throws — a program error comes
// back as `error`, exactly as runProgram already reports it (rule 3: a
// recursion-too-deep error is reported as itself, not swallowed). Synchronous
// and unchanged since before the module loader: a program with no file-backed
// `use` never touches a loader at all.
export function step(src, context) {
  const prelude = composePrelude(context);
  const result = runProgram(prelude + "\n" + src, {});
  return stepResult(context, result);
}

// Like step, but resolves file-backed `use`d modules first via
// runProgramGraph — the module-loader-aware tick a page passes a `loader` to.
// The page awaits; the interpreter itself never does (checkpoint v21.0 §248):
// once a module's text is cached, resolving it again costs a Map lookup, not
// a fetch, so a ticking program pays the network cost once per module for the
// life of the run, not once per frame.
export async function stepGraph(src, context, { loader, base } = {}) {
  const prelude = composePrelude(context);
  const result = await runProgramGraph(prelude + "\n" + src, { base, loader });
  return stepResult(context, result);
}

// A loop for a program whose tick IS a position in a cycle rather than a
// counter — the garden's day, which the page can also scrub to directly.
// createLoop below owns its own tick and counts up forever; this one owns a
// FLOAT position, advances it by wall-clock time, and hands the integer part
// to whoever asked. That is the difference between "a frame happened" and
// "this much of the day passed", and it is what lets play and the scrubber
// share one value: playing writes it, dragging writes it, and both make the
// same picture at the same number.
//
// WALL-CLOCK, NOT PER-FRAME. `day += 1` per animation frame would run the day
// at whatever rate the machine happens to render, and a slow frame would
// slow time down rather than skip it. Advancing by elapsed seconds means a
// tick the machine had no time to draw is SKIPPED, not queued: at 16x the day
// still passes in the same few seconds, with fewer frames shown. Which is the
// honest behaviour for a scene that is a pure function of its own clock.
//
// It runs `run(tick)` and awaits it, and never starts a second run before the
// first returns (createLoop's rule 2, met the same way). An erroring run stops
// the loop (rule 1).
export function createSceneLoop({
  run,
  getTick,
  setTick,
  span,
  ticksPerSecond = 4,
  getSpeed = () => 1,
  schedule,
  cancel,
  now = () => (typeof performance !== "undefined" ? performance.now() : Date.now()),
  onError = null,
}) {
  const sched =
    schedule ||
    (typeof requestAnimationFrame !== "undefined" ? requestAnimationFrame : (fn) => setTimeout(fn, 16));
  const cancelFn =
    cancel || (typeof cancelAnimationFrame !== "undefined" ? cancelAnimationFrame : clearTimeout);

  let running = false;
  let pending = false;
  let handle = null;
  let last = 0;
  let position = 0;

  async function frame() {
    if (!running) return;
    const t = now();
    const elapsed = Math.min(0.25, (t - last) / 1000);
    last = t;
    if (!pending) {
      position += elapsed * ticksPerSecond * getSpeed();
      position = ((position % span) + span) % span;
      const tick = Math.floor(position);
      if (tick !== getTick()) {
        setTick(tick);
        pending = true;
        try {
          await run(tick);
        } catch (e) {
          pending = false;
          running = false;
          if (onError) onError(e);
          return;
        }
        pending = false;
        if (!running) return;
      }
    }
    handle = sched(frame);
  }

  return {
    start() {
      if (running) return;
      running = true;
      last = now();
      position = getTick();
      handle = sched(frame);
    },
    stop() {
      running = false;
      if (handle !== null) cancelFn(handle);
      handle = null;
    },
    // A drag writes the position too, so releasing the scrubber and pressing
    // play resumes from where the reader left it rather than from where the
    // loop had got to.
    syncTo(tick) {
      position = tick;
    },
    isRunning: () => running,
  };
}

// Drives `step` from a scheduler — requestAnimationFrame in a real page, or
// an injected fake under test (Node has no rAF). Three rules, from §3:
//   1. an erroring tick stops the loop and shows the error, rather than
//      silently skipping a frame;
//   2. never more than one runProgram call per animation frame, and a frame
//      is skipped rather than queued if the previous call has not returned;
//   3. a recursion-too-deep error is reported as itself (step already does
//      this — createLoop just doesn't hide it).
// `loader`/`base`, when given, switch every tick to stepGraph instead of
// step — the page awaits a module read, the interpreter still never does
// (checkpoint v21.0 §248's "the page waits; the program does not," extended
// per frame: once a `loader`'s cache is warm, awaiting an already-resolved
// value costs a microtask, not a fetch). Omit both and this is unchanged from
// before the module loader — synchronous, calling step() directly.
export function createLoop({
  getSource,
  getKeys,
  getPointer,
  initialState = null,
  onFrame,
  schedule,
  cancel,
  stepEveryNFrames = 1,
  loader = null,
  base = null,
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

  // requestAnimationFrame runs at the display's rate (commonly 60Hz), which is
  // far too fast for a human to react to in a grid-stepped game like snake —
  // the loop itself stays rAF (A.2), but a Planes tick need not land on every
  // one of its callbacks. stepEveryNFrames > 1 skips callbacks between ticks;
  // it never causes more than one step call per animation frame, only fewer.
  // Returns true when this callback should actually step.
  function dueToStep() {
    framesSinceStep += 1;
    if (framesSinceStep < stepEveryNFrames) return false;
    framesSinceStep = 0;
    return true;
  }

  function frameSync() {
    if (!running) return;
    if (!dueToStep()) {
      handle = sched(frameSync);
      return;
    }
    if (pending) {
      // The previous call has not returned — skip this frame rather than
      // queue another on top of it (rule 2). step() is synchronous, so this
      // never actually triggers here; it is the same guard frameAsync needs
      // for real.
      handle = sched(frameSync);
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
    handle = sched(frameSync);
  }

  async function frameAsync() {
    if (!running) return;
    if (!dueToStep()) {
      handle = sched(frameAsync);
      return;
    }
    if (pending) {
      // rule 2, and here it genuinely can trigger: stepGraph awaits a loader
      // read, so a second scheduler callback can land before the first
      // returns.
      handle = sched(frameAsync);
      return;
    }
    pending = true;
    const context = { tick, keys: getKeys(), pointer: getPointer(), state };
    const result = await stepGraph(getSource(), context, { loader, base });
    pending = false;
    tick += 1;
    if (!running) return; // stop()/reset() landed while this tick awaited

    if (result.error) {
      running = false;
      onFrame(result);
      return; // rule 1: stop, don't skip
    }

    state = result.state;
    onFrame(result);
    handle = sched(frameAsync);
  }

  const frame = loader ? frameAsync : frameSync;

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
