// js/sound/audio.mjs — the Web Audio player: a SINK for js/sound/stream.mjs
// (planes-sound-protocol-v1.md §§4-7, normative).
//
// This file knows how to make an oscillator sound for four tenths of a second.
// It does not know what a stream is, what the version declaration means, what
// 3/2 one octave up comes to in hertz, or what any error is called — all of
// that is stream.mjs's, shared verbatim with wav.mjs. What is left here is
// exactly the part that is Web Audio.
//
// THE ONE PLACE THE TWO PLAYERS DIFFER IN MECHANISM. §6.3's envelope is a
// formula, and wav.mjs evaluates it per sample. Here it is scheduled as two
// ramps on a GainNode — `linearRampToValueAtTime` to the note's gain at
// `start + ATTACK_SECONDS`, then `exponentialRampToValueAtTime` to
// `DECAY_FLOOR × gain` at `start + lasts`. Those are the same curve, spelled
// the way the medium spells it, and js/test/sound_agree.test.mjs checks the
// two against each other at sampled points rather than trusting the claim.
//
// DROPPED NOTES (§3.1). A note whose `at` has already passed by the time the
// stream is walked is dropped, silently and on purpose — a player that has
// spent 40 milliseconds walking a stream does not race to catch up on a note
// scheduled for millisecond 10. `droppedCount()` reports how many, for a page
// that wants to say so.

import { walk, ATTACK_SECONDS, DECAY_FLOOR } from "./stream.mjs";

// The master level every note passes through, so a page has one knob rather
// than a rule about how loud a program is allowed to be.
const MASTER_GAIN = 0.5;

// A low-pass at the top of the chain: three of the four waveforms this
// protocol allows are harmonically rich enough to be unpleasant on small
// speakers, and this is the player's business, not the protocol's — it changes
// no note's pitch, start or length, so the two players still agree about the
// schedule. wav.mjs deliberately does not filter (a file is a record of what
// was asked for), and js/test/sound_agree.test.mjs compares schedules, not
// spectra.
const LOWPASS_HZ = 1800;

export function createAudioPlayer({ context } = {}) {
  let ctx = context || null;
  let master = null;
  let dropped = 0;

  function ensure() {
    if (ctx) return ctx;
    const Ctor = typeof AudioContext !== "undefined" ? AudioContext : globalThis.webkitAudioContext;
    if (!Ctor) throw new Error("js/sound/audio.mjs: this environment has no Web Audio");
    ctx = new Ctor();
    return ctx;
  }

  function ensureMaster() {
    const c = ensure();
    if (master) return master;
    master = c.createGain();
    master.gain.value = MASTER_GAIN;
    const lp = c.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = LOWPASS_HZ;
    master.connect(lp).connect(c.destination);
    return master;
  }

  // `origin` is the context time the tick began. Every note's `at` is relative
  // to it (§3), so a stream walked 12 milliseconds after the tick started
  // still lands its notes where the program put them.
  function sink(origin) {
    return {
      reset() {},
      wave() {},
      gain() {},
      silence() {
        // Nothing scheduled yet can be unscheduled: notes are only started
        // when the walk reaches them, and `silence` clears the schedule inside
        // the walk itself (stream.mjs), so by the time a note reaches this
        // sink it has already survived every `silence` before it. This method
        // exists because the sink interface has it, and does nothing because
        // there is nothing left for it to do.
      },
      note({ frequency, at, lasts, wave, gain }) {
        const c = ensure();
        const startAt = origin + at;
        if (startAt < c.currentTime) {
          dropped += 1;
          return;
        }
        const out = ensureMaster();
        const osc = c.createOscillator();
        const env = c.createGain();
        osc.type = wave;
        osc.frequency.value = frequency;
        const attack = Math.min(ATTACK_SECONDS, lasts);
        env.gain.setValueAtTime(0, startAt);
        env.gain.linearRampToValueAtTime(gain, startAt + attack);
        env.gain.exponentialRampToValueAtTime(Math.max(gain * DECAY_FLOOR, 1e-6), startAt + lasts);
        osc.connect(env).connect(out);
        osc.start(startAt);
        osc.stop(startAt + lasts + 0.05);
      },
      finish() {},
    };
  }

  return {
    // Walks `lines` and schedules whatever they ask for, starting from now.
    // Returns the same shape stream.mjs's walk does, so a caller can report
    // errors the same way the drawing side already does.
    play(lines) {
      const c = ensure();
      if (c.state === "suspended" && c.resume) c.resume();
      return walk(lines, sink(c.currentTime));
    },
    // Constructs the context without playing anything — a page calls this
    // from the click that turned sound on, because a browser will not start an
    // AudioContext outside a gesture.
    unlock() {
      const c = ensure();
      ensureMaster();
      if (c.state === "suspended" && c.resume) c.resume();
      return c;
    },
    droppedCount: () => dropped,
    context: () => ctx,
  };
}
