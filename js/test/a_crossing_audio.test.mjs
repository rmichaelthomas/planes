import assert from "node:assert/strict";
import test from "node:test";

import { createCrossingAudio, planAudioIntent } from "../scene/a_crossing_audio.mjs";

const audioIntent = {
  beds: [{ id: "channel-day", gain: 0.18, anchor: "center" }],
  cues: [{ id: "bell-double", gain: 0.15, anchor: "nkwo-eriri", serial: 4 }],
};

test("the structured mix never schedules a continuous bare oscillator", () => {
  const plan = planAudioIntent(audioIntent);
  assert.ok(plan.beds.length >= 2);
  assert.ok(plan.beds.every((bed) => bed.source === "noise" && bed.filter));
  assert.equal(plan.nodes.some((node) => node.source === "oscillator" && node.continuous), false);
  assert.ok(plan.cues.every((cue) => cue.duration > 0 && cue.duration <= 0.8));
  assert.ok(plan.masterGain <= 0.38);
});

test("audio remains locked and silent until an explicit unlock", async () => {
  let contexts = 0;
  const audio = createCrossingAudio({ contextFactory: () => { contexts += 1; return null; } });
  audio.apply(audioIntent);
  assert.equal(contexts, 0);
  assert.equal(audio.diagnostics().unlocked, false);
  await audio.unlock();
  assert.equal(contexts, 1);
});

test("cue serials are deduplicated across repeated semantic ticks", () => {
  const first = planAudioIntent(audioIntent);
  const second = planAudioIntent(audioIntent, new Set(first.cueKeys));
  assert.equal(first.cues.length, 1);
  assert.equal(second.cues.length, 0);
});

test("unknown audio identifiers produce diagnostics and silence", () => {
  const plan = planAudioIntent({ beds: [{ id: "unknown-bed", gain: 1, anchor: "center" }], cues: [{ id: "shriek", gain: 1, anchor: "center", serial: 1 }] });
  assert.deepEqual(plan.beds, []);
  assert.deepEqual(plan.cues, []);
  assert.deepEqual(plan.warnings, ["unknown audio bed: unknown-bed", "unknown audio cue: shriek"]);
});
