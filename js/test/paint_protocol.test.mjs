// js/test/paint_protocol.test.mjs — the draw-command protocol (A.5), headless.
//
// A line that is not a recognised verb is text, never an error: parseCommand
// returns null and the caller routes it to the text pane. These tests cover
// every verb, wrong arity, an unknown verb, a `~`-prefixed number, and a
// `text` verb whose string contains spaces and a number.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { parseCommand, VERBS } from "../paint/protocol.mjs";

test("VERBS is the frozen A.5 whitelist", () => {
  assert.deepEqual(
    [...VERBS].sort(),
    ["box", "circle", "clear", "dot", "line", "move", "pen", "rect", "text", "width"].sort(),
  );
  assert.ok(Object.isFrozen(VERBS));
});

test("pen takes three numbers", () => {
  assert.deepEqual(parseCommand("pen 0.2 0.4 0.9"), { verb: "pen", args: [0.2, 0.4, 0.9] });
});

test("width takes one number", () => {
  assert.deepEqual(parseCommand("width 3"), { verb: "width", args: [3] });
});

test("move takes two numbers", () => {
  assert.deepEqual(parseCommand("move 10 20"), { verb: "move", args: [10, 20] });
});

test("line takes two numbers", () => {
  assert.deepEqual(parseCommand("line 30 40"), { verb: "line", args: [30, 40] });
});

test("circle takes three numbers", () => {
  assert.deepEqual(parseCommand("circle 100 100 25"), { verb: "circle", args: [100, 100, 25] });
});

test("dot takes three numbers", () => {
  assert.deepEqual(parseCommand("dot 50 60 5"), { verb: "dot", args: [50, 60, 5] });
});

test("rect takes four numbers", () => {
  assert.deepEqual(parseCommand("rect 0 0 100 50"), { verb: "rect", args: [0, 0, 100, 50] });
});

test("box takes four numbers", () => {
  assert.deepEqual(parseCommand("box 10 10 20 20"), { verb: "box", args: [10, 10, 20, 20] });
});

test("clear takes no arguments", () => {
  assert.deepEqual(parseCommand("clear"), { verb: "clear", args: [] });
});

test("text takes x, y, and the rest of the line as a string", () => {
  assert.deepEqual(parseCommand("text 5 10 hello world"), {
    verb: "text",
    args: [5, 10],
    text: "hello world",
  });
});

test("text's string may contain spaces and a number", () => {
  assert.deepEqual(parseCommand("text 5 10 score: 42 points"), {
    verb: "text",
    args: [5, 10],
    text: "score: 42 points",
  });
});

test("a `~`-prefixed exact-rational number is accepted, and the ~ is dropped", () => {
  assert.deepEqual(parseCommand("move ~10 ~20.5"), { verb: "move", args: [10, 20.5] });
});

test("wrong arity returns null", () => {
  assert.equal(parseCommand("pen 0.2 0.4"), null);
  assert.equal(parseCommand("move 1 2 3"), null);
  assert.equal(parseCommand("width"), null);
  assert.equal(parseCommand("clear 1"), null);
});

test("an unknown verb returns null", () => {
  assert.equal(parseCommand("triangle 1 2 3"), null);
});

test("a non-numeric argument to a numeric verb returns null", () => {
  assert.equal(parseCommand("move x y"), null);
});

test("text with fewer than one word of content returns null", () => {
  assert.equal(parseCommand("text 5 10"), null);
});

test("an empty line returns null", () => {
  assert.equal(parseCommand(""), null);
  assert.equal(parseCommand("   "), null);
});

test("a plain prose line returns null", () => {
  assert.equal(parseCommand("this is just text for the text pane"), null);
});
