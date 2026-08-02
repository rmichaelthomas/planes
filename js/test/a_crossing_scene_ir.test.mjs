import assert from "node:assert/strict";
import test from "node:test";

import { SceneIntentError, parseSceneIntent } from "../scene/ir.mjs";

const intentLines = [
  "scene protocol 1",
  "scene camera horizon 0.42 0.54 1",
  "scene environment bright-passage afternoon rolu-grandi-3",
  "scene subject hydrofoil hydrofoil-main 0.38 0.67 1 visible active",
  "scene route reso-nkwo 0.1 0.73 0.82 0.55 active 0.24",
  "scene signal clinic-beacon 0.91 0.43 warm available",
  "scene weather swell 3 southwest",
  "scene action hydrofoil route depart Launch-crossing primary",
  "scene cue crossing-commit 17",
  "audio bed channel-day 0.34 center",
  "audio cue bell-double 0.22 hydrofoil 17",
];

test("parses one complete Planes-directed scene without inventing fields", () => {
  const intent = parseSceneIntent(intentLines);

  assert.equal(intent.protocol, 1);
  assert.deepEqual(intent.camera, { id: "horizon", x: 0.42, y: 0.54, zoom: 1 });
  assert.deepEqual(intent.environment, {
    id: "bright-passage",
    light: "afternoon",
    weather: "rolu-grandi-3",
  });
  assert.deepEqual(intent.subjects[0], {
    id: "hydrofoil",
    asset: "hydrofoil-main",
    x: 0.38,
    y: 0.67,
    scale: 1,
    visibility: "visible",
    state: "active",
  });
  assert.equal(intent.routes[0].progress, 0.24);
  assert.deepEqual(intent.actions[0], { subject: "hydrofoil", kind: "route", choice: "depart", label: "Launch crossing", emphasis: "primary" });
  assert.equal(intent.cues[0].serial, 17);
  assert.equal(intent.audio.beds[0].gain, 0.34);
  assert.equal(intent.audio.cues[0].anchor, "hydrofoil");
  assert.deepEqual(intent.warnings, []);
});

test("rejects a malformed critical camera record", () => {
  assert.throws(
    () => parseSceneIntent(["scene protocol 1", "scene camera horizon left 0.5 1"]),
    (error) => error instanceof SceneIntentError && error.record === "camera",
  );
});

test("reports unknown optional scene records and continues", () => {
  const intent = parseSceneIntent([
    "scene protocol 1",
    "scene camera horizon 0.42 0.54 1",
    "scene environment bright-passage afternoon clear",
    "scene shimmer route-cord 0.8",
  ]);

  assert.deepEqual(intent.warnings, [{ line: 4, message: "unknown scene record: shimmer" }]);
  assert.equal(intent.environment.id, "bright-passage");
});

test("rejects normalized coordinates outside the renderer contract", () => {
  assert.throws(
    () => parseSceneIntent([
      "scene protocol 1",
      "scene camera horizon 1.2 0.5 1",
      "scene environment bright-passage afternoon clear",
    ]),
    (error) => error instanceof SceneIntentError && error.record === "camera",
  );
});
