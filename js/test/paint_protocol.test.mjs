// js/test/paint_protocol.test.mjs — the drawing protocol (planes-drawing-
// protocol-v1.md §§1-7), headless.
//
// A line beginning with `draw` is always a command — never reinterpreted as
// prose, even when it is malformed. Any other line is prose, unconditionally,
// including a line that happens to spell a zero-arity verb's own name. These
// tests cover every verb at correct and wrong arity, every error tag, `~`
// stripping, and label's free-text tail.

import { test } from "node:test";
import assert from "node:assert/strict";
import { parseCommand, VERBS } from "../paint/protocol.mjs";

test("VERBS is the frozen twenty-six-verb table, protocol excluded", () => {
  assert.equal(VERBS.length, 26);
  assert.equal(new Set(VERBS).size, 26, "no duplicates");
  assert.ok(!VERBS.includes("protocol"), "protocol is a stream directive, not a drawing verb");
  assert.ok(Object.isFrozen(VERBS));
  for (const retired of ["pen", "move", "dot", "box", "text", "join"]) {
    assert.ok(!VERBS.includes(retired), `${retired} was retired or renamed`);
  }
  assert.ok(VERBS.includes("label"), "text -> label");
  assert.ok(VERBS.includes("corner"), "join -> corner");
});

// ---- every verb at correct arity -------------------------------------------

const NUMERIC_CASES = [
  ["stroke", "draw stroke 0.6 0.15 210 1", [0.6, 0.15, 210, 1]],
  ["fill", "draw fill 0.6 0.15 210 1", [0.6, 0.15, 210, 1]],
  ["width", "draw width 3", [3]],
  ["line", "draw line 0 0 100 50", [0, 0, 100, 50]],
  ["rect", "draw rect 0 0 100 50", [0, 0, 100, 50]],
  ["circle", "draw circle 200 100 40", [200, 100, 40]],
  ["ellipse", "draw ellipse 200 100 40 20", [200, 100, 40, 20]],
  ["arc", "draw arc 200 100 40 0 90", [200, 100, 40, 0, 90]],
  ["triangle", "draw triangle 0 0 10 0 5 10", [0, 0, 10, 0, 5, 10]],
  ["vertex", "draw vertex 100 100", [100, 100]],
  ["curve", "draw curve 10 10 20 20 30 30", [10, 10, 20, 20, 30, 30]],
  ["translate", "draw translate 10 20", [10, 20]],
  ["rotate", "draw rotate 30", [30]],
  ["scale", "draw scale 2 -1", [2, -1]],
  ["size", "draw size 16", [16]],
  ["background", "draw background 0.9 0.05 90", [0.9, 0.05, 90]],
];

for (const [verb, line, args] of NUMERIC_CASES) {
  test(`${verb} at correct arity parses its numeric arguments`, () => {
    assert.deepEqual(parseCommand(line), { kind: "command", verb, args });
  });
}

const ZERO_ARITY = ["shape", "close", "end", "push", "pop", "clear"];
for (const verb of ZERO_ARITY) {
  test(`${verb} takes no arguments`, () => {
    assert.deepEqual(parseCommand(`draw ${verb}`), { kind: "command", verb, args: [] });
  });
}

test("protocol takes one positive integer", () => {
  assert.deepEqual(parseCommand("draw protocol 1"), { kind: "command", verb: "protocol", args: [1] });
});

test("label takes two numbers and the rest of the line as text", () => {
  assert.deepEqual(parseCommand("draw label 8 16 score: 42"), {
    kind: "command",
    verb: "label",
    args: [8, 16],
    text: "score: 42",
  });
});

test("label's text may contain spaces and a verb name", () => {
  assert.deepEqual(parseCommand("draw label 8 16 press draw circle to continue"), {
    kind: "command",
    verb: "label",
    args: [8, 16],
    text: "press draw circle to continue",
  });
});

// ---- word-argument verbs: one valid, one invalid word ----------------------

const WORD_CASES = [
  ["cap", ["butt", "round", "square"], "triangle"],
  ["corner", ["miter", "round", "bevel"], "square"],
  ["align", ["left", "center", "right"], "middle"],
];

for (const [verb, valid, invalid] of WORD_CASES) {
  for (const word of valid) {
    test(`${verb} accepts "${word}"`, () => {
      assert.deepEqual(parseCommand(`draw ${verb} ${word}`), { kind: "command", verb, args: [word] });
    });
  }
  test(`${verb} rejects a word outside its set`, () => {
    const r = parseCommand(`draw ${verb} ${invalid}`);
    assert.equal(r.kind, "error");
    assert.equal(r.tag, "bad-word");
    assert.match(r.message, new RegExp(invalid));
  });
}

// ---- every verb at wrong arity ----------------------------------------------

for (const [verb, line] of NUMERIC_CASES) {
  test(`${verb} with one argument too few is wrong-arity`, () => {
    const short = line.split(" ").slice(0, -1).join(" ");
    const r = parseCommand(short);
    assert.equal(r.kind, "error");
    assert.equal(r.tag, "wrong-arity");
  });
  test(`${verb} with one argument too many is wrong-arity`, () => {
    const r = parseCommand(`${line} 1`);
    assert.equal(r.kind, "error");
    assert.equal(r.tag, "wrong-arity");
  });
}

for (const verb of ZERO_ARITY) {
  test(`${verb} with an argument is wrong-arity`, () => {
    const r = parseCommand(`draw ${verb} 1`);
    assert.equal(r.kind, "error");
    assert.equal(r.tag, "wrong-arity");
  });
}

test("protocol with no argument is wrong-arity", () => {
  const r = parseCommand("draw protocol");
  assert.equal(r.kind, "error");
  assert.equal(r.tag, "wrong-arity");
});

test("protocol with two arguments is wrong-arity", () => {
  const r = parseCommand("draw protocol 1 2");
  assert.equal(r.kind, "error");
  assert.equal(r.tag, "wrong-arity");
});

test("label with fewer than two numbers is wrong-arity", () => {
  assert.equal(parseCommand("draw label").tag, "wrong-arity");
  assert.equal(parseCommand("draw label 8").tag, "wrong-arity");
});

test("label with numbers but no text is wrong-arity", () => {
  const r = parseCommand("draw label 8 16");
  assert.equal(r.kind, "error");
  assert.equal(r.tag, "wrong-arity");
});

test("label with numbers and only trailing whitespace is wrong-arity", () => {
  const r = parseCommand("draw label 8 16   ");
  assert.equal(r.kind, "error");
  assert.equal(r.tag, "wrong-arity");
});

// ---- error tags --------------------------------------------------------------

test("an unrecognised verb is unknown-verb", () => {
  const r = parseCommand("draw hexagon 1 2 3");
  assert.equal(r.kind, "error");
  assert.equal(r.tag, "unknown-verb");
});

test("draw with no verb at all is unknown-verb", () => {
  const r = parseCommand("draw");
  assert.equal(r.kind, "error");
  assert.equal(r.tag, "unknown-verb");
});

test("a retired verb (pen) is unknown-verb, not a silent alias", () => {
  const r = parseCommand("draw pen 1 0 0");
  assert.equal(r.kind, "error");
  assert.equal(r.tag, "unknown-verb");
});

test("a non-numeric argument in a numeric position is bad-number", () => {
  const r = parseCommand("draw circle x 100 40");
  assert.equal(r.kind, "error");
  assert.equal(r.tag, "bad-number");
});

test("exponent notation is not a valid number", () => {
  const r = parseCommand("draw width 1e3");
  assert.equal(r.kind, "error");
  assert.equal(r.tag, "bad-number");
});

test("a bare decimal point with no leading digit is not a valid number", () => {
  const r = parseCommand("draw width .5");
  assert.equal(r.kind, "error");
  assert.equal(r.tag, "bad-number");
});

test("protocol with a non-integer version is bad-protocol-version", () => {
  const r = parseCommand("draw protocol 1.5");
  assert.equal(r.kind, "error");
  assert.equal(r.tag, "bad-protocol-version");
});

test("protocol with a zero or negative version is bad-protocol-version", () => {
  assert.equal(parseCommand("draw protocol 0").tag, "bad-protocol-version");
  assert.equal(parseCommand("draw protocol -1").tag, "bad-protocol-version");
});

// ---- ~-prefixed numbers ------------------------------------------------------

test("a `~`-prefixed exact-rational rendering is accepted, and the ~ is dropped", () => {
  assert.deepEqual(parseCommand("draw circle ~66.666 100 40"), {
    kind: "command",
    verb: "circle",
    args: [66.666, 100, 40],
  });
});

test("a `~`-prefixed negative number is accepted", () => {
  assert.deepEqual(parseCommand("draw rotate ~-30"), { kind: "command", verb: "rotate", args: [-30] });
});

// ---- prose: never interpreted, even a zero-arity verb's own name -----------

test("a line not beginning with draw is prose, unconditionally", () => {
  assert.deepEqual(parseCommand("this is just text for the text pane"), {
    kind: "prose",
    text: "this is just text for the text pane",
  });
});

for (const verb of ZERO_ARITY) {
  test(`the bare word "${verb}" with no draw prefix is prose, not a command`, () => {
    assert.deepEqual(parseCommand(verb), { kind: "prose", text: verb });
  });
}

test('"close the file" is prose', () => {
  assert.deepEqual(parseCommand("close the file"), { kind: "prose", text: "close the file" });
});

test('a line quoting a draw command as text is prose', () => {
  const line = 'the next line will draw circle 200 100 40';
  assert.deepEqual(parseCommand(line), { kind: "prose", text: line });
});

test("an empty line is prose", () => {
  assert.deepEqual(parseCommand(""), { kind: "prose", text: "" });
});
