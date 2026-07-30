// js/sound/wav.mjs — the WAV player: a second SINK for js/sound/stream.mjs
// (planes-sound-protocol-v1.md §§4-7, normative).
//
// `toWav(lines, options)` returns the same three-part result the live player
// does — `{ wav, scheduled, text, errors }` — because it walks the same stream
// with the same module. Everything that is protocol rather than medium (the
// version declaration and its ordering, the schedule, the pitch computation,
// the envelope, every error tag) lives in stream.mjs and is shared verbatim
// with audio.mjs. What is here is what it means to sound a note *as samples*.
//
// The reason this exists is the reason js/paint/svg.mjs exists: with one
// player, semantics leak into it and the shared walk stops being normative,
// and nobody finds out until the second player is written. Writing this one
// found two — that `silence` has to clear the schedule inside the walk rather
// than inside a player, and that a note's wave and gain are the state at the
// moment it was emitted, not at the end of the stream.
//
// STATED LIMIT: NO FILTER. audio.mjs puts a low-pass at the top of its chain
// because small speakers make a square wave unpleasant; this does not, because
// a file is a record of what the program asked for. The two players therefore
// agree about every note's pitch, start, length and envelope and differ in
// timbre — which is a player's business (§7) and is stated here rather than
// discovered.
//
// Node-safe and browser-safe: no imports outside this repo, and nothing from
// `node:` at all.

import { walk, envelopeAt } from "./stream.mjs";

export const SAMPLE_RATE = 44100;

// One period of each waveform, as a function of phase in 0..1. Exactly the
// three §8 says the set stays closed at, and exactly reproducible from a
// formula — which is the whole reason the set is closed there.
function sampleOf(wave, phase) {
  if (wave === "square") return phase < 0.5 ? 1 : -1;
  if (wave === "triangle") return phase < 0.5 ? 4 * phase - 1 : 3 - 4 * phase;
  return Math.sin(phase * 2 * Math.PI);
}

// A note's contribution to the buffer, added in — notes overlap, and §6.1 says
// two notes at gain 0.5 overlapping are two notes at half amplitude, not one.
function mixNote(samples, note, sampleRate) {
  const start = Math.round(note.at * sampleRate);
  const count = Math.round(note.lasts * sampleRate);
  const step = note.frequency / sampleRate;
  for (let i = 0; i < count; i++) {
    const index = start + i;
    if (index < 0 || index >= samples.length) continue;
    const t = i / sampleRate;
    const phase = (i * step) % 1;
    samples[index] += sampleOf(note.wave, phase) * note.gain * envelopeAt(t, note.lasts);
  }
}

function wavSink(sampleRate) {
  let notes = [];
  return {
    notes: () => notes,
    reset() {
      notes = [];
    },
    wave() {},
    gain() {},
    note(n) {
      notes.push(n);
    },
    silence() {
      notes = [];
    },
    finish() {},
  };
}

// A 16-bit mono PCM RIFF file, built with DataView rather than a Node Buffer
// so this runs unchanged in a browser (which is where garden.html would reach
// for it) — the same discipline js/sha256.mjs follows.
export function encodeWav(samples, sampleRate = SAMPLE_RATE) {
  const bytesPerSample = 2;
  const dataBytes = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);

  const ascii = (offset, s) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };

  ascii(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true); // PCM header size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true); // byte rate
  view.setUint16(32, bytesPerSample, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  ascii(36, "data");
  view.setUint32(40, dataBytes, true);

  for (let i = 0; i < samples.length; i++) {
    // Clipped, not normalised: normalising would make a quiet phrase and a
    // loud one come out the same, which is a change to what the program said.
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * bytesPerSample, Math.round(clamped * 32767), true);
  }
  return new Uint8Array(buffer);
}

// `tailSeconds` pads the end so a note's own decay is not cut off by the file
// ending exactly where the last note does.
export function toWav(lines, { sampleRate = SAMPLE_RATE, tailSeconds = 0.25 } = {}) {
  const sink = wavSink(sampleRate);
  const { scheduled, text, errors, refused } = walk(lines, sink);
  // A refused stream plays nothing, in either player, and a WAV file with no
  // samples is not a silent phrase — it is no phrase at all (§1.1).
  if (refused) return { wav: null, notes: [], scheduled: 0, text, errors };

  const notes = sink.notes();
  let end = 0;
  for (const n of notes) end = Math.max(end, n.at + n.lasts);
  const length = Math.max(1, Math.ceil((end + tailSeconds) * sampleRate));
  const samples = new Float64Array(length);
  for (const n of notes) mixNote(samples, n, sampleRate);

  return { wav: encodeWav(samples, sampleRate), notes, scheduled, text, errors };
}
