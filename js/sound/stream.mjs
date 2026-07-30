// js/sound/stream.mjs — the walk over a sound stream, once, for every player
// (planes-sound-protocol-v1.md §§1-6, normative).
//
// A player is a SINK: an object with one method per verb. This module reads
// the stream in order, decides what each line means, and calls the sink. It
// owns everything that is protocol semantics rather than medium:
//
//   * the version declaration and its ordering rules (§1.1) — including that
//     an unimplemented version refuses the WHOLE stream and plays nothing;
//   * the refusal contract (§2) — which lines are errors and what they are
//     called, including the three domain refusals a well-formed line can
//     still earn (a zero denominator, a gain out of range, a note that starts
//     before the tick or lasts no time);
//   * the reset table (§5), handed to the sink as one value;
//   * the pitch computation (§4) — the ratio is resolved to a frequency HERE,
//     once, so two players cannot disagree about what 3/2 one octave up is,
//     and the integer triple is carried alongside it so nothing downstream has
//     to reconstruct the ratio from a float;
//   * the envelope (§6.3), as one function both media are given;
//   * the schedule itself, and what `silence` does to it.
//
// None of that is Web-Audio-specific or WAV-specific, and a second player that
// re-implemented it would agree on every case anyone thought to test and
// diverge on the first one nobody did. This is js/paint/stream.mjs's argument,
// applied to a second medium on purpose.

import { parseCommand } from "./protocol.mjs";

const SUPPORTED_VERSIONS = new Set([1]);

// The specification's §5 table, as one value. A sink resets to this at the
// start of every stream; nothing persists between streams except what a
// program restates.
export const DEFAULTS = Object.freeze({
  wave: "sine",
  gain: 0.2,
});

// §4: pinned here so two players cannot disagree about what a stream means.
export const BASE_HZ = 220;

// §4: base × 2^octave × numerator / denominator. Computed in the shared walk
// and handed to the sink already resolved — the ratio itself travels with it
// (numerator, denominator, octave) so a why card, a WAV header comment or a
// test can still read the fifth as a fifth rather than as 330.
export function frequencyOf(numerator, denominator, octave) {
  return BASE_HZ * Math.pow(2, octave) * (numerator / denominator);
}

// §6.3, pinned: a linear rise to full gain over the first 0.16 seconds (or
// over `lasts`, whichever is shorter), then an exponential fall to 0.0001 of
// full scale at exactly `lasts`. Returns a multiplier in 0..1 for a time `t`
// measured from the note's own start.
//
// audio.mjs does not call this — it schedules the SAME two ramps on a
// GainNode, which is the medium's own way of spelling this curve — and
// wav.mjs does, sample by sample. That is the one place the two players differ
// in mechanism; the curve is this one either way, and js/test/sound_agree.test.mjs
// checks the two against each other at sampled points.
export const ATTACK_SECONDS = 0.16;
export const DECAY_FLOOR = 0.0001;

export function envelopeAt(t, lasts) {
  if (t < 0 || t > lasts) return 0;
  const attack = Math.min(ATTACK_SECONDS, lasts);
  if (attack > 0 && t < attack) return t / attack;
  const remaining = lasts - attack;
  if (remaining <= 0) return 1;
  // exponentialRamp from 1 to DECAY_FLOOR across `remaining`.
  return Math.pow(DECAY_FLOOR, (t - attack) / remaining);
}

export function walk(lines, sink) {
  const errors = [];
  const text = [];
  let scheduled = 0;

  let versionSet = false;
  let declaredVersion = 1; // §1.1: absent is version 1
  let sawSoundingCommand = false;

  let waveWord = DEFAULTS.wave;
  let gainValue = DEFAULTS.gain;

  sink.reset(DEFAULTS);

  try {
    for (const line of lines) {
      const cmd = parseCommand(line);

      if (cmd.kind === "prose") {
        text.push(cmd.text);
        continue;
      }

      if (cmd.kind === "error") {
        errors.push({ tag: cmd.tag, message: cmd.message });
        continue;
      }

      if (cmd.verb === "protocol") {
        if (versionSet) {
          errors.push({
            tag: "protocol-repeated",
            message: 'a second "sound protocol" declaration is not allowed in one stream',
          });
          continue;
        }
        if (sawSoundingCommand) {
          errors.push({
            tag: "protocol-late",
            message: '"sound protocol" must appear before the first sounding command',
          });
          continue;
        }
        const [requested] = cmd.args;
        if (!SUPPORTED_VERSIONS.has(requested)) {
          // The whole stream is refused: nothing is played (§1.1) — a player
          // cannot refuse a phrase it has already begun.
          return {
            scheduled: 0,
            text: [],
            refused: true,
            errors: [
              {
                tag: "unsupported-version",
                message:
                  `this player implements sound protocol version 1; the stream declared ` +
                  `version ${requested} and is refused whole`,
              },
            ],
          };
        }
        versionSet = true;
        declaredVersion = requested;
        continue;
      }

      sawSoundingCommand = true;

      switch (cmd.verb) {
        case "wave":
          waveWord = cmd.args[0];
          sink.wave(waveWord);
          break;
        case "gain": {
          const g = cmd.args[0];
          if (!(g >= 0 && g <= 1)) {
            errors.push({
              tag: "gain-out-of-range",
              message: `"gain" takes a level from 0 to 1 in "${line}", got ${g}`,
            });
            break;
          }
          gainValue = g;
          sink.gain(g);
          break;
        }
        case "note": {
          const [numerator, denominator, octave, at, lasts] = cmd.args;
          if (denominator === 0 || numerator <= 0 || denominator < 0) {
            errors.push({
              tag: "bad-ratio",
              message:
                `"note" takes a pitch ratio with a positive numerator and denominator in "${line}", ` +
                `got ${numerator}/${denominator}`,
            });
            break;
          }
          if (at < 0 || lasts <= 0) {
            errors.push({
              tag: "bad-time",
              message:
                `"note" starts at or after the tick begins and lasts longer than no time at all in ` +
                `"${line}", got at ${at} lasting ${lasts}`,
            });
            break;
          }
          sink.note({
            numerator,
            denominator,
            octave,
            at,
            lasts,
            frequency: frequencyOf(numerator, denominator, octave),
            wave: waveWord,
            gain: gainValue,
          });
          scheduled += 1;
          break;
        }
        case "silence":
          sink.silence();
          scheduled = 0;
          break;
      }
    }
  } finally {
    sink.finish();
  }

  return { scheduled, text, errors, refused: false, version: declaredVersion };
}

// The schedule as data, with no medium at all: a sink that collects notes and
// nothing else. Both real players are built on top of one of these in spirit;
// it is also what a test, an export, and the why panel read, and what
// scripts/verify-garden.mjs compares two runs of.
export function collectSink() {
  const notes = [];
  return {
    notes,
    reset() {
      notes.length = 0;
    },
    wave() {},
    gain() {},
    note(n) {
      notes.push(n);
    },
    silence() {
      notes.length = 0;
    },
    finish() {},
  };
}

// The one-call form of the above: `schedule(lines)` gives the notes a stream
// asks for, in order, with everything already resolved.
export function schedule(lines) {
  const sink = collectSink();
  const { errors, text, refused } = walk(lines, sink);
  return { notes: refused ? [] : sink.notes.slice(), errors, text, refused };
}
