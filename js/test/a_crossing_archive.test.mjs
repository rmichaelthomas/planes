import assert from "node:assert/strict";
import test from "node:test";

import { createArchiveController } from "../scene/a_crossing_archive.mjs";

test("archive defaults to Revision and does not load technical layers at arrival", () => {
  let sourceLoads = 0;
  let surfaceLoads = 0;
  const archive = createArchiveController({
    loadSource: async () => { sourceLoads += 1; return "source"; },
    loadSurface: async () => { surfaceLoads += 1; return "surface"; },
  });
  assert.equal(archive.state.tab, "revision");
  assert.equal(sourceLoads, 0);
  assert.equal(surfaceLoads, 0);
});

test("source and surface load once and only when their tabs are requested", async () => {
  let sourceLoads = 0;
  let surfaceLoads = 0;
  const archive = createArchiveController({
    loadSource: async () => { sourceLoads += 1; return "Planes source"; },
    loadSurface: async () => { surfaceLoads += 1; return "effect surface"; },
  });
  await archive.open("atlas");
  assert.deepEqual([sourceLoads, surfaceLoads], [0, 0]);
  await archive.open("source");
  await archive.open("source");
  await archive.open("surface");
  assert.deepEqual([sourceLoads, surfaceLoads], [1, 1]);
  assert.equal(archive.state.source, "Planes source");
  assert.equal(archive.state.surface, "effect surface");
});

test("archive preserves all nine canonical landings from Planes observations", () => {
  const archive = createArchiveController();
  archive.update({
    result: { state: { revision: "crossing revised" }, lines: [
      "atlas eriri-ukwu 500 172 landing", "atlas anomabu 278 82 landing", "atlas sabel 690 72 landing",
      "atlas tado 220 210 landing", "atlas bonny 724 195 landing", "atlas vela 360 310 landing",
      "atlas marronde 506 326 landing", "atlas banta 742 306 landing", "atlas reso 142 324 landing",
      "atlas nkwo-eriri 500 172 capital", "atlas route-cord 468 329 passage",
    ] },
    events: [{ kind: "need", choice: "care" }], seed: 481027,
  });
  assert.equal(archive.state.landings.length, 9);
  assert.deepEqual(archive.state.landings.map(({ id }) => id), ["eriri-ukwu", "anomabu", "sabel", "tado", "bonny", "vela", "marronde", "banta", "reso"]);
  assert.equal(archive.state.revision, "crossing revised");
});
