import assert from "node:assert/strict";
import test from "node:test";

import { createSceneModel, resolveCameraLayout, resolveSceneAsset } from "../scene/a_crossing_stage.mjs";

const firstIntent = {
  camera: { id: "horizon", x: 0.42, y: 0.54, zoom: 1 },
  environment: { id: "bright-passage", light: "afternoon", weather: "rolu-grandi-3" },
  subjects: [
    { id: "hydrofoil", asset: "hydrofoil-main", x: 0.16, y: 0.72, scale: 1, visibility: "visible", state: "planning" },
    { id: "radio-mast", asset: "radio-mast", x: 0.85, y: 0.3, scale: 1, visibility: "visible", state: "clear" },
  ],
  routes: [{ id: "reso-nkwo", fromX: 0.12, fromY: 0.73, toX: 0.84, toY: 0.57, state: "planning", progress: 0 }],
  signals: [], weather: [], cues: [],
  actions: [{ subject: "hydrofoil", kind: "route", choice: "depart", label: "Launch crossing", emphasis: "primary" }],
};

test("scene reconciliation keeps semantic subject identity stable", () => {
  const first = createSceneModel(firstIntent);
  const hydrofoil = first.subjects.get("hydrofoil");
  const next = createSceneModel({
    ...firstIntent,
    subjects: firstIntent.subjects.map((subject) => subject.id === "hydrofoil" ? { ...subject, x: 0.43, state: "crossing" } : subject),
  }, first);

  assert.strictEqual(next.subjects.get("hydrofoil"), hydrofoil);
  assert.equal(hydrofoil.x, 0.43);
  assert.equal(hydrofoil.state, "crossing");
});

test("scene actions are exactly the actions Planes emitted", () => {
  const model = createSceneModel(firstIntent);
  assert.deepEqual(model.actions, firstIntent.actions);
  assert.equal(model.actions.some(({ choice }) => choice === "hold-reserve"), false);
});

test("unknown visual assets resolve to a designed canonical fallback", () => {
  assert.equal(resolveSceneAsset("hydrofoil-main"), "hydrofoil-main");
  assert.equal(resolveSceneAsset("future-vessel"), "canonical-silhouette");
});

test("selection accepts only a semantic subject in the current model", () => {
  const model = createSceneModel(firstIntent);
  assert.equal(model.select("hydrofoil"), true);
  assert.equal(model.selected, "hydrofoil");
  assert.equal(model.select("invented-host-object"), false);
  assert.equal(model.selected, "hydrofoil");
});

test("paused models suppress visual advancement without changing semantic progress", () => {
  const model = createSceneModel(firstIntent);
  model.pause();
  assert.equal(model.paused, true);
  assert.equal(model.routes[0].progress, 0);
  model.resume();
  assert.equal(model.paused, false);
});

test("the compositor converts Planes camera intent into a portrait world pan", () => {
  const start = resolveCameraLayout({ width: 390, height: 844, camera: { x: .42, y: .54, zoom: 1 } });
  const arrival = resolveCameraLayout({ width: 390, height: 844, camera: { x: .61, y: .54, zoom: 1.12 } });

  assert.equal(start.portrait, true);
  assert.equal(start.zoom, 1);
  assert.ok(start.panX > arrival.panX);
  assert.equal(Math.round(start.worldWidth), 1500);
});

test("desktop camera intent remains direct", () => {
  const layout = resolveCameraLayout({ width: 1280, height: 720, camera: { x: .58, y: .54, zoom: 1.08 } });
  assert.equal(layout.portrait, false);
  assert.equal(layout.zoom, 1.08);
  assert.equal(layout.panX, 0);
});
