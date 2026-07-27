// js/test/paint_loop.test.mjs — the tick loop (§3), headless.
//
// composePrelude/step are pure and run under plain runProgram, so they are
// tested directly. createLoop wraps them in a scheduler; tests inject a fake
// one (no requestAnimationFrame under Node) to drive frames deterministically.

import { test } from "node:test";
import assert from "node:assert/strict";
import { parse } from "../parser.mjs";
import { composePrelude, planesLiteral, step, createLoop } from "../paint/loop.mjs";

test("composePrelude emits bindings only, and the output parses as valid Planes", () => {
  const src = composePrelude({
    tick: 12,
    keys: ["ArrowLeft"],
    pointer: { x: 240, y: 130, down: false },
    state: { x: 100, y: 50, score: 3 },
  });
  assert.doesNotThrow(() => parse(src, new Set()));
  assert.match(src, /let tick = 12/);
  assert.match(src, /let keys = \["ArrowLeft"\]/);
  assert.match(src, /let pointer = \{ x: 240, y: 130, down: false \}/);
  assert.match(src, /let state = \{ x: 100, y: 50, score: 3 \}/);
});

test("composePrelude renders a nothing state as the literal `nothing`, and it parses", () => {
  const src = composePrelude({ tick: 0, keys: [], pointer: { x: 0, y: 0, down: false }, state: null });
  assert.match(src, /let state = nothing/);
  assert.doesNotThrow(() => parse(src, new Set()));
});

test("planesLiteral renders every JSON-shaped value the harness needs to thread through", () => {
  assert.equal(planesLiteral(null), "nothing");
  assert.equal(planesLiteral(true), "true");
  assert.equal(planesLiteral(false), "false");
  assert.equal(planesLiteral(5), "5");
  assert.equal(planesLiteral(-2.5), "-2.5");
  assert.equal(planesLiteral("hi"), '"hi"');
  assert.equal(planesLiteral('a "quote"'), '"a \\"quote\\""');
  assert.equal(planesLiteral([1, 2]), "[1, 2]");
  assert.equal(planesLiteral({ a: 1, b: "x" }), '{ a: 1, b: "x" }');
});

test("a first tick with nothing state works: the program handles it and writes real state", () => {
  const src = `use file
if state is nothing:
  let next = { count: 0 }
else:
  let next = state with count: state.count + 1

write next to "state.json"
show "count: " + text of next.count
`;
  const r = step(src, { tick: 0, keys: [], pointer: { x: 0, y: 0, down: false }, state: null });
  assert.equal(r.error, null);
  assert.deepEqual(r.state, { count: 0 });
  assert.deepEqual(r.lines, ["count: 0"]);
});

test("a three-tick sequence threads state correctly", () => {
  const src = `use file
if state is nothing:
  let next = { count: 0 }
else:
  let next = state with count: state.count + 1

write next to "state.json"
show "count: " + text of next.count
`;
  let state = null;
  const seen = [];
  for (let tick = 0; tick < 3; tick++) {
    const r = step(src, { tick, keys: [], pointer: { x: 0, y: 0, down: false }, state });
    assert.equal(r.error, null);
    state = r.state;
    seen.push(r.lines[0]);
  }
  assert.deepEqual(seen, ["count: 0", "count: 1", "count: 2"]);
  assert.deepEqual(state, { count: 2 });
});

test("an erroring program returns the error rather than throwing", () => {
  const src = `z = 5 + "x"\n`;
  assert.doesNotThrow(() => {
    const r = step(src, { tick: 0, keys: [], pointer: { x: 0, y: 0, down: false }, state: null });
    assert.ok(r.error);
    assert.equal(r.error.tag, "cannot-combine");
  });
});

test("a recursion-too-deep error is reported as itself, not swallowed", () => {
  const src = `to recurse of n:
  if n <= 0:
    give 0
  else:
    give 1 + (recurse of (n - 1))

let result = recurse of 100000
show text of result
`;
  const r = step(src, { tick: 0, keys: [], pointer: { x: 0, y: 0, down: false }, state: null });
  assert.equal(r.error.tag, "recursion-too-deep");
});

// ---- createLoop: a fake, manually-driven scheduler stands in for rAF.

function fakeScheduler() {
  let queued = null;
  return {
    schedule: (fn) => {
      queued = fn;
      return { id: 1 };
    },
    cancel: () => {
      queued = null;
    },
    fireOnce() {
      const fn = queued;
      queued = null;
      if (fn) fn();
    },
    hasQueued() {
      return queued !== null;
    },
  };
}

test("createLoop runs one step per scheduled frame and threads state forward", () => {
  const sched = fakeScheduler();
  const src = `use file
if state is nothing:
  let next = { count: 0 }
else:
  let next = state with count: state.count + 1

write next to "state.json"
show "count: " + text of next.count
`;
  const frames = [];
  const loop = createLoop({
    getSource: () => src,
    getKeys: () => [],
    getPointer: () => ({ x: 0, y: 0, down: false }),
    initialState: null,
    onFrame: (r) => frames.push(r),
    schedule: sched.schedule,
    cancel: sched.cancel,
  });

  loop.start();
  assert.equal(loop.isRunning(), true);
  sched.fireOnce();
  sched.fireOnce();
  sched.fireOnce();

  assert.deepEqual(
    frames.map((f) => f.lines[0]),
    ["count: 0", "count: 1", "count: 2"],
  );
  assert.equal(loop.isRunning(), true);
  assert.ok(sched.hasQueued(), "a fourth frame is queued");
});

test("stop() halts scheduling — no further frames run", () => {
  const sched = fakeScheduler();
  const loop = createLoop({
    getSource: () => 'show "hi"\n',
    getKeys: () => [],
    getPointer: () => ({ x: 0, y: 0, down: false }),
    initialState: null,
    onFrame: () => {},
    schedule: sched.schedule,
    cancel: sched.cancel,
  });
  loop.start();
  sched.fireOnce();
  loop.stop();
  assert.equal(loop.isRunning(), false);
  assert.equal(sched.hasQueued(), false);
});

test("a tick that errors stops the loop rather than skipping the frame silently", () => {
  const sched = fakeScheduler();
  const frames = [];
  const loop = createLoop({
    getSource: () => 'z = 5 + "x"\n',
    getKeys: () => [],
    getPointer: () => ({ x: 0, y: 0, down: false }),
    initialState: null,
    onFrame: (r) => frames.push(r),
    schedule: sched.schedule,
    cancel: sched.cancel,
  });
  loop.start();
  sched.fireOnce();
  assert.equal(loop.isRunning(), false);
  assert.equal(frames.length, 1);
  assert.equal(frames[0].error.tag, "cannot-combine");
  assert.equal(sched.hasQueued(), false, "no next frame is queued after an error");
});

test("stepEveryNFrames throttles ticks below the scheduler's own rate", () => {
  const sched = fakeScheduler();
  const src = `use file
if state is nothing:
  let next = { count: 0 }
else:
  let next = state with count: state.count + 1

write next to "state.json"
show "count: " + text of next.count
`;
  const frames = [];
  const loop = createLoop({
    getSource: () => src,
    getKeys: () => [],
    getPointer: () => ({ x: 0, y: 0, down: false }),
    initialState: null,
    onFrame: (r) => frames.push(r),
    schedule: sched.schedule,
    cancel: sched.cancel,
    stepEveryNFrames: 3,
  });
  loop.start();
  // Six scheduler callbacks at a 1-in-3 throttle should yield exactly two ticks.
  for (let i = 0; i < 6; i++) sched.fireOnce();
  assert.deepEqual(
    frames.map((f) => f.lines[0]),
    ["count: 0", "count: 1"],
  );
});

test("reset() returns the loop to tick zero and the initial state", () => {
  const sched = fakeScheduler();
  const src = `use file
if state is nothing:
  let next = { count: 0 }
else:
  let next = state with count: state.count + 1

write next to "state.json"
show "count: " + text of next.count
`;
  const frames = [];
  const loop = createLoop({
    getSource: () => src,
    getKeys: () => [],
    getPointer: () => ({ x: 0, y: 0, down: false }),
    initialState: null,
    onFrame: (r) => frames.push(r),
    schedule: sched.schedule,
    cancel: sched.cancel,
  });
  loop.start();
  sched.fireOnce();
  sched.fireOnce();
  loop.reset();
  assert.equal(loop.isRunning(), false);
  loop.start();
  sched.fireOnce();
  assert.deepEqual(
    frames.map((f) => f.lines[0]),
    ["count: 0", "count: 1", "count: 0"],
  );
});
