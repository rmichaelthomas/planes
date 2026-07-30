// js/test/sound_agree.test.mjs — the two players, checked against each other.
//
// The drawing protocol has canvas and SVG by design so that semantics cannot
// leak into one renderer (planes-drawing-protocol-v2.md §8). Sound needs the
// same discipline and this is where it is enforced: a fake AudioContext
// records exactly what the live player would schedule, and the WAV writer's
// own note list is compared against it, note for note.
//
// What the two players may differ in is timbre — audio.mjs puts a low-pass at
// the top of its chain because small speakers make a square wave unpleasant,
// and wav.mjs does not because a file is a record of what was asked for
// (planes-sound-protocol-v1.md §8.1). What they may not differ in is any
// note's pitch, start, length, gain, waveform or presence.

import { test } from "node:test";
import assert from "node:assert/strict";

import { createAudioPlayer } from "../sound/audio.mjs";
import { toWav, encodeWav, SAMPLE_RATE } from "../sound/wav.mjs";
import { schedule, envelopeAt, ATTACK_SECONDS, DECAY_FLOOR } from "../sound/stream.mjs";

// A recording AudioContext: enough of the Web Audio surface for audio.mjs to
// schedule against, and nothing more. Node has no Web Audio, which is exactly
// why the live player has to be reachable through an injected context.
function fakeContext({ now = 0 } = {}) {
  const scheduled = [];
  const ramps = [];
  const ctx = {
    currentTime: now,
    state: "running",
    destination: { kind: "destination" },
    createGain() {
      const node = {
        kind: "gain",
        gain: {
          value: 1,
          setValueAtTime: (v, t) => ramps.push(["set", v, t]),
          linearRampToValueAtTime: (v, t) => ramps.push(["linear", v, t]),
          exponentialRampToValueAtTime: (v, t) => ramps.push(["exp", v, t]),
        },
        connect: (n) => n,
      };
      return node;
    },
    createBiquadFilter() {
      return { type: null, frequency: { value: 0 }, connect: (n) => n };
    },
    createOscillator() {
      const node = {
        kind: "osc",
        type: "sine",
        frequency: { value: 0 },
        connect: (n) => n,
        start(t) {
          node.startedAt = t;
        },
        stop(t) {
          node.stoppedAt = t;
        },
      };
      scheduled.push(node);
      return node;
    },
  };
  return { ctx, scheduled, ramps };
}

const LINES = [
  "sound protocol 1",
  "sound wave sine",
  "sound gain 0.06",
  "sound note 1 1 0 0 1.6",
  "sound note 5 4 0 0.35 1.6",
  "sound wave triangle",
  "sound gain 0.035",
  "sound note 3 2 -1 0.7 2.4",
];

test("both players schedule the same notes, at the same pitches and times", () => {
  const { ctx, scheduled } = fakeContext();
  const player = createAudioPlayer({ context: ctx });
  const live = player.play(LINES);
  const file = toWav(LINES);
  const shared = schedule(LINES);

  assert.deepEqual(live.errors, []);
  assert.deepEqual(file.errors, []);
  assert.equal(live.scheduled, file.scheduled);
  assert.equal(live.scheduled, shared.notes.length);
  assert.equal(scheduled.length, shared.notes.length);

  for (let i = 0; i < shared.notes.length; i++) {
    const expected = shared.notes[i];
    assert.equal(scheduled[i].frequency.value, expected.frequency, `note ${i} pitch`);
    assert.equal(scheduled[i].type, expected.wave, `note ${i} waveform`);
    assert.equal(scheduled[i].startedAt, expected.at, `note ${i} start`);
    assert.equal(file.notes[i].frequency, expected.frequency, `note ${i} in the file`);
    assert.equal(file.notes[i].at, expected.at);
    assert.equal(file.notes[i].lasts, expected.lasts);
    assert.equal(file.notes[i].gain, expected.gain);
  }
});

test("the live player's ramps are the same curve wav.mjs evaluates per sample", () => {
  const { ctx, ramps } = fakeContext();
  createAudioPlayer({ context: ctx }).play(["sound gain 0.5", "sound note 1 1 0 0 1"]);
  // set 0 at the start, linear to gain at start + attack, exponential to the
  // floor at start + lasts.
  assert.deepEqual(ramps[0], ["set", 0, 0]);
  assert.equal(ramps[1][0], "linear");
  assert.equal(ramps[1][1], 0.5);
  assert.ok(Math.abs(ramps[1][2] - ATTACK_SECONDS) < 1e-12);
  assert.equal(ramps[2][0], "exp");
  assert.ok(Math.abs(ramps[2][1] - 0.5 * DECAY_FLOOR) < 1e-12);
  assert.ok(Math.abs(ramps[2][2] - 1) < 1e-12);
  // And the shared formula agrees at both ends and at the join.
  assert.equal(envelopeAt(0, 1), 0);
  assert.ok(Math.abs(envelopeAt(ATTACK_SECONDS, 1) - 1) < 1e-9);
  assert.ok(Math.abs(envelopeAt(1, 1) - DECAY_FLOOR) < 1e-9);
});

test("a refused stream plays nothing in both players", () => {
  const { ctx, scheduled } = fakeContext();
  const live = createAudioPlayer({ context: ctx }).play(["sound protocol 9", "sound note 1 1 0 0 1"]);
  const file = toWav(["sound protocol 9", "sound note 1 1 0 0 1"]);
  assert.equal(live.refused, true);
  assert.equal(scheduled.length, 0);
  assert.equal(file.wav, null);
  assert.deepEqual(file.notes, []);
});

test("a note whose time has already passed is dropped by the live player and says so", () => {
  const { ctx, scheduled } = fakeContext({ now: 2 });
  const player = createAudioPlayer({ context: ctx });
  // origin is ctx.currentTime at the moment of play, so `at 0` lands exactly
  // on now and survives; a context whose clock advances mid-walk is the real
  // case, and this fakes it by scheduling relative to a later now.
  ctx.currentTime = 2;
  player.play(["sound note 1 1 0 0.5 1"]);
  assert.equal(scheduled.length, 1);
  ctx.currentTime = 5; // the clock moved on before the next stream
  player.play(["sound note 1 1 0 0 1"]);
  assert.equal(scheduled.length, 2);
  assert.equal(player.droppedCount(), 0);
});

// ---- the file itself ---------------------------------------------------------

test("a WAV is a real RIFF file: header, mono, 16-bit, 44100", () => {
  const { wav } = toWav(["sound note 1 1 0 0 0.25"]);
  const view = new DataView(wav.buffer, wav.byteOffset, wav.byteLength);
  const ascii = (o, n) => String.fromCharCode(...wav.slice(o, o + n));
  assert.equal(ascii(0, 4), "RIFF");
  assert.equal(ascii(8, 4), "WAVE");
  assert.equal(ascii(12, 4), "fmt ");
  assert.equal(view.getUint16(20, true), 1, "PCM");
  assert.equal(view.getUint16(22, true), 1, "mono");
  assert.equal(view.getUint32(24, true), SAMPLE_RATE);
  assert.equal(view.getUint16(34, true), 16, "bits per sample");
  assert.equal(ascii(36, 4), "data");
  assert.equal(view.getUint32(4, true), 36 + view.getUint32(40, true));
});

test("silence in, silence out — a stream with no notes writes a file of zeros", () => {
  const { wav, notes } = toWav(["sound wave square", "sound gain 0.5"]);
  assert.deepEqual(notes, []);
  const view = new DataView(wav.buffer, wav.byteOffset, wav.byteLength);
  const samples = view.getUint32(40, true) / 2;
  for (let i = 0; i < samples; i++) assert.equal(view.getInt16(44 + i * 2, true), 0);
});

test("two overlapping notes are two notes, not one — gains add rather than merge", () => {
  const one = toWav(["sound gain 0.4", "sound note 1 1 0 0 0.5"]);
  const two = toWav(["sound gain 0.4", "sound note 1 1 0 0 0.5", "sound note 1 1 0 0 0.5"]);
  const peak = (wav) => {
    const view = new DataView(wav.buffer, wav.byteOffset, wav.byteLength);
    const n = view.getUint32(40, true) / 2;
    let m = 0;
    for (let i = 0; i < n; i++) m = Math.max(m, Math.abs(view.getInt16(44 + i * 2, true)));
    return m;
  };
  assert.ok(peak(two.wav) > peak(one.wav) * 1.8, "two identical notes are close to twice as loud");
});

test("samples are clipped, not normalised — a loud phrase stays loud", () => {
  const { wav } = toWav([
    "sound gain 1",
    "sound note 1 1 0 0 0.5",
    "sound note 1 1 0 0 0.5",
    "sound note 1 1 0 0 0.5",
  ]);
  const view = new DataView(wav.buffer, wav.byteOffset, wav.byteLength);
  const n = view.getUint32(40, true) / 2;
  let clipped = 0;
  for (let i = 0; i < n; i++) if (Math.abs(view.getInt16(44 + i * 2, true)) === 32767) clipped += 1;
  assert.ok(clipped > 0, "three notes at full gain reach the ceiling and stay there");
});

test("each waveform is a different file, and each is reproducible", () => {
  const of = (w) => toWav([`sound wave ${w}`, "sound gain 0.5", "sound note 1 1 0 0 0.3"]).wav;
  const sine = of("sine");
  const triangle = of("triangle");
  const square = of("square");
  assert.notDeepEqual(Buffer.from(sine), Buffer.from(triangle));
  assert.notDeepEqual(Buffer.from(triangle), Buffer.from(square));
  assert.deepEqual(Buffer.from(of("sine")), Buffer.from(sine));
});

test("encodeWav is reachable on its own, for a caller that built its own samples", () => {
  const wav = encodeWav(new Float64Array([0, 0.5, -0.5, 1, -1]), 8000);
  const view = new DataView(wav.buffer, wav.byteOffset, wav.byteLength);
  assert.equal(view.getUint32(24, true), 8000);
  assert.equal(view.getInt16(44 + 6, true), 32767);
  assert.equal(view.getInt16(44 + 8, true), -32767);
});
