// js/test/tick_scrubber.test.mjs — js/paint/tick_scrubber.mjs, headless.
//
// A minimal fake range input (value/min/max as plain properties, a real
// listener registry) is enough to exercise the wiring without a DOM —
// garden.html's own real <input type="range"> behaves identically for
// everything this module touches.

import { test } from "node:test";
import assert from "node:assert/strict";
import { createTickScrubber } from "../paint/tick_scrubber.mjs";

function fakeInput() {
  const listeners = {};
  return {
    value: "0",
    min: "",
    max: "",
    addEventListener(name, fn) {
      listeners[name] = fn;
    },
    fire(name) {
      listeners[name]?.();
    },
  };
}
function fakeButton() {
  const listeners = {};
  return {
    addEventListener(name, fn) {
      listeners[name] = fn;
    },
    click() {
      listeners.click?.();
    },
  };
}
function fakeLabel() {
  return { textContent: "" };
}

test("initializes min/max/value and the label", () => {
  const rangeEl = fakeInput();
  const labelEl = fakeLabel();
  createTickScrubber({ rangeEl, max: 239, onChange: () => {}, labelEl, labelText: (t) => `day ${t}` });
  assert.equal(rangeEl.min, "0");
  assert.equal(rangeEl.max, "239");
  assert.equal(rangeEl.value, "0");
  assert.equal(labelEl.textContent, "day 0");
});

test("dragging the range (an input event) calls onChange with the new value", () => {
  const rangeEl = fakeInput();
  const seen = [];
  createTickScrubber({ rangeEl, max: 100, onChange: (t) => seen.push(t) });
  rangeEl.value = "42";
  rangeEl.fire("input");
  assert.deepEqual(seen, [42]);
});

test("the forward/back steppers move by exactly one and fire onChange", () => {
  const rangeEl = fakeInput();
  const backEl = fakeButton();
  const forwardEl = fakeButton();
  const seen = [];
  const scrubber = createTickScrubber({ rangeEl, backEl, forwardEl, max: 10, onChange: (t) => seen.push(t) });
  scrubber.setTick(5, { fire: false });
  forwardEl.click();
  assert.equal(rangeEl.value, "6");
  backEl.click();
  backEl.click();
  assert.equal(rangeEl.value, "4");
  assert.deepEqual(seen, [6, 5, 4]);
});

test("setTick clamps to [0, max] and never fires onChange out of range", () => {
  const rangeEl = fakeInput();
  const seen = [];
  const scrubber = createTickScrubber({ rangeEl, max: 5, onChange: (t) => seen.push(t) });
  scrubber.setTick(-3);
  assert.equal(rangeEl.value, "0");
  scrubber.setTick(999);
  assert.equal(rangeEl.value, "5");
  assert.deepEqual(seen, [0, 5]);
});

test("setTick with fire:false updates the display but does not call onChange", () => {
  const rangeEl = fakeInput();
  const seen = [];
  const scrubber = createTickScrubber({ rangeEl, max: 10, onChange: (t) => seen.push(t) });
  scrubber.setTick(7, { fire: false });
  assert.equal(rangeEl.value, "7");
  assert.deepEqual(seen, []);
  assert.equal(scrubber.getTick(), 7);
});

test("setMax re-bounds the range and re-clamps the current value without firing", () => {
  const rangeEl = fakeInput();
  const seen = [];
  const scrubber = createTickScrubber({ rangeEl, max: 100, onChange: (t) => seen.push(t) });
  scrubber.setTick(80, { fire: false });
  scrubber.setMax(50);
  assert.equal(rangeEl.max, "50");
  assert.equal(rangeEl.value, "50");
  assert.deepEqual(seen, [], "re-bounding is silent, not a simulated drag");
});

test("labelText defaults to the bare tick number when omitted", () => {
  const rangeEl = fakeInput();
  const labelEl = fakeLabel();
  const scrubber = createTickScrubber({ rangeEl, max: 20, onChange: () => {}, labelEl });
  scrubber.setTick(9, { fire: false });
  assert.equal(labelEl.textContent, "9");
});

test("scrubbing to day 30, away, and back to day 30 lands on the exact same tick — the purity precondition", () => {
  const rangeEl = fakeInput();
  const seen = [];
  const scrubber = createTickScrubber({ rangeEl, max: 239, onChange: (t) => seen.push(t) });
  scrubber.setTick(30);
  scrubber.setTick(5);
  scrubber.setTick(30);
  assert.deepEqual(seen, [30, 5, 30]);
});
