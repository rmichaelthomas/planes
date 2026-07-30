// js/test/sound_protocol.test.mjs — the Planes Sound Protocol's parser and
// shared walk (planes-sound-protocol-v1.md §§1-7), headless.

import { test } from "node:test";
import assert from "node:assert/strict";

import { parseCommand, VERBS } from "../sound/protocol.mjs";
import { walk, schedule, collectSink, frequencyOf, envelopeAt, BASE_HZ, DEFAULTS, ATTACK_SECONDS } from "../sound/stream.mjs";

// ---- the prefix --------------------------------------------------------------

test("a line not beginning with `sound` is prose and is never interpreted", () => {
  for (const line of ["draw circle 1 2 3", "note of 3, 2", "silence", "soundtrack", ""]) {
    assert.equal(parseCommand(line).kind, "prose", line);
  }
});

// A shared quirk, matched deliberately rather than diverged from. Both
// protocols test the prefix with `\b`, and `\b` sits between a letter and a
// hyphen — so `sound-ish` reaches the parser as a command with no verb, and
// `draw-ish` does exactly the same thing on the drawing side. The
// specifications both say "a command begins with the WORD", so this is a
// small divergence from both of them; it is reported rather than fixed here,
// because fixing it in one protocol and not the other would be worse than the
// quirk, and fixing it in both changes what an existing drawing stream means.
test("a hyphenated near-miss is a command with no verb, in this protocol and the drawing one alike", async () => {
  const { parseCommand: parseDraw } = await import("../paint/protocol.mjs");
  assert.equal(parseCommand("sound-ish").tag, "unknown-verb");
  assert.equal(parseDraw("draw-ish").tag, "unknown-verb");
});

test("a drawing line reaches a player as prose, untouched", () => {
  const { text, notes } = schedule(["draw protocol 2", "draw circle 1 2 3", "sound note 1 1 0 0 1"]);
  assert.deepEqual(text, ["draw protocol 2", "draw circle 1 2 3"]);
  assert.equal(notes.length, 1);
});

test("a sound line reaching the DRAWING walk is prose there too — both prefixes cross", async () => {
  const { walk: drawWalk } = await import("../paint/stream.mjs");
  const sink = new Proxy({}, { get: (_t, k) => (k === "at" ? undefined : () => {}) });
  const { text, errors } = drawWalk(["sound note 3 2 1 0 0.4", "draw circle 1 2 3"], sink);
  assert.deepEqual(errors, []);
  assert.deepEqual(text, ["sound note 3 2 1 0 0.4"]);
});

// ---- the verb table ----------------------------------------------------------

test("the table is exactly four verbs", () => {
  assert.deepEqual([...VERBS].sort(), ["gain", "note", "silence", "wave"]);
});

test("every verb parses at its own arity", () => {
  const good = [
    ["sound wave sine", "wave"],
    ["sound wave triangle", "wave"],
    ["sound wave square", "wave"],
    ["sound gain 0.5", "gain"],
    ["sound note 3 2 1 0.5 0.4", "note"],
    ["sound silence", "silence"],
  ];
  for (const [line, verb] of good) {
    const cmd = parseCommand(line);
    assert.equal(cmd.kind, "command", line);
    assert.equal(cmd.verb, verb);
  }
});

test("the wave set is closed at three", () => {
  const cmd = parseCommand("sound wave sawtooth");
  assert.equal(cmd.tag, "bad-word");
  assert.match(cmd.message, /sine, triangle, square/);
});

test("the wrong argument count is an error naming the count", () => {
  const cmd = parseCommand("sound note 3 2 1");
  assert.equal(cmd.tag, "wrong-arity");
  assert.match(cmd.message, /takes 5 arguments/);
});

test("an unrecognised verb is an error, never a caption", () => {
  const cmd = parseCommand("sound crescendo 3");
  assert.equal(cmd.tag, "unknown-verb");
  assert.match(cmd.message, /gain, note, silence, wave/);
});

test("a number that is not a number is an error", () => {
  const cmd = parseCommand("sound gain loud");
  assert.equal(cmd.tag, "bad-number");
});

test("a leading ~ is accepted and discarded — an inexact rational renders with one", () => {
  const cmd = parseCommand("sound note 1 1 0 ~0.333 0.4");
  assert.equal(cmd.kind, "command");
  assert.equal(cmd.args[3], 0.333);
});

test("exponent notation is not a number here", () => {
  assert.equal(parseCommand("sound gain 1e-2").tag, "bad-number");
});

// ---- the version declaration -------------------------------------------------

test("an unimplemented version refuses the WHOLE stream and plays nothing", () => {
  const r = schedule(["sound protocol 7", "sound note 1 1 0 0 1"]);
  assert.equal(r.refused, true);
  assert.deepEqual(r.notes, []);
  assert.equal(r.errors[0].tag, "unsupported-version");
});

test("a second declaration is an error", () => {
  const { errors } = schedule(["sound protocol 1", "sound protocol 1"]);
  assert.equal(errors[0].tag, "protocol-repeated");
});

test("a declaration after the first sounding command is an error", () => {
  const { errors } = schedule(["sound note 1 1 0 0 1", "sound protocol 1"]);
  assert.equal(errors[0].tag, "protocol-late");
});

// ---- the three domain refusals -----------------------------------------------

test("a zero denominator is refused rather than divided by", () => {
  const { errors, notes } = schedule(["sound note 3 0 0 0 1"]);
  assert.equal(errors[0].tag, "bad-ratio");
  assert.deepEqual(notes, []);
});

test("a non-positive numerator is refused", () => {
  assert.equal(schedule(["sound note 0 2 0 0 1"]).errors[0].tag, "bad-ratio");
  assert.equal(schedule(["sound note -3 2 0 0 1"]).errors[0].tag, "bad-ratio");
});

test("a gain outside 0 to 1 is refused", () => {
  assert.equal(schedule(["sound gain 1.5"]).errors[0].tag, "gain-out-of-range");
  assert.equal(schedule(["sound gain -0.1"]).errors[0].tag, "gain-out-of-range");
  assert.deepEqual(schedule(["sound gain 0"]).errors, []);
  assert.deepEqual(schedule(["sound gain 1"]).errors, []);
});

test("a note before the tick, or lasting no time, is refused", () => {
  assert.equal(schedule(["sound note 1 1 0 -1 1"]).errors[0].tag, "bad-time");
  assert.equal(schedule(["sound note 1 1 0 0 0"]).errors[0].tag, "bad-time");
});

// ---- pitch is a ratio --------------------------------------------------------

test("the base is pinned at 220 Hz and octave is an exponent, not a multiplier", () => {
  assert.equal(BASE_HZ, 220);
  assert.equal(frequencyOf(1, 1, 0), 220);
  assert.equal(frequencyOf(1, 1, 1), 440);
  assert.equal(frequencyOf(1, 1, -1), 110);
});

test("a fifth is 3/2 and stays 3/2", () => {
  assert.equal(frequencyOf(3, 2, 0), 330);
  assert.equal(frequencyOf(3, 2, 1), 660);
});

test("a scheduled note carries its ratio alongside its frequency — nothing flattens it", () => {
  const { notes } = schedule(["sound note 5 4 1 0.25 0.5"]);
  assert.equal(notes[0].numerator, 5);
  assert.equal(notes[0].denominator, 4);
  assert.equal(notes[0].octave, 1);
  assert.equal(notes[0].frequency, 220 * 2 * 1.25);
});

// ---- state -------------------------------------------------------------------

test("the reset table is sine at gain 0.2 with an empty schedule", () => {
  assert.equal(DEFAULTS.wave, "sine");
  assert.equal(DEFAULTS.gain, 0.2);
  const { notes } = schedule(["sound note 1 1 0 0 1"]);
  assert.equal(notes[0].wave, "sine");
  assert.equal(notes[0].gain, 0.2);
});

test("wave and gain are state — a note carries what was set when IT was emitted", () => {
  const { notes } = schedule([
    "sound wave square",
    "sound gain 0.4",
    "sound note 1 1 0 0 1",
    "sound wave triangle",
    "sound note 1 1 0 1 1",
  ]);
  assert.equal(notes[0].wave, "square");
  assert.equal(notes[0].gain, 0.4);
  assert.equal(notes[1].wave, "triangle");
  assert.equal(notes[1].gain, 0.4);
});

test("`silence` discards every note scheduled so far and nothing after it", () => {
  const { notes } = schedule([
    "sound note 1 1 0 0 1",
    "sound note 3 2 0 0 1",
    "sound silence",
    "sound note 5 4 0 0 1",
  ]);
  assert.equal(notes.length, 1);
  assert.equal(notes[0].numerator, 5);
});

// ---- the envelope, pinned ----------------------------------------------------

test("the envelope rises linearly for 0.16s then falls exponentially to the floor", () => {
  assert.equal(envelopeAt(0, 1), 0);
  assert.ok(Math.abs(envelopeAt(ATTACK_SECONDS / 2, 1) - 0.5) < 1e-9);
  assert.ok(Math.abs(envelopeAt(ATTACK_SECONDS, 1) - 1) < 1e-9);
  assert.ok(envelopeAt(0.5, 1) < 1);
  assert.ok(Math.abs(envelopeAt(1, 1) - 0.0001) < 1e-9);
  assert.equal(envelopeAt(1.1, 1), 0);
  assert.equal(envelopeAt(-0.1, 1), 0);
});

test("a note shorter than the attack still rises over its own whole length", () => {
  assert.ok(Math.abs(envelopeAt(0.05, 0.1) - 0.5) < 1e-9);
});

// ---- the collecting sink -----------------------------------------------------

test("collectSink is a player that plays nothing and reports everything", () => {
  const sink = collectSink();
  const r = walk(["sound protocol 1", "sound note 1 1 0 0 1"], sink);
  assert.equal(r.scheduled, 1);
  assert.equal(r.version, 1);
  assert.equal(sink.notes.length, 1);
});
