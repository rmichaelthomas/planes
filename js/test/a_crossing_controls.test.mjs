import assert from "node:assert/strict";
import test from "node:test";

import { actionSurfaceSignature } from "../scene/a_crossing_controls.mjs";

test("an unchanged Planes action surface has a stable identity across semantic ticks", () => {
  const firstTick = [
    { subject: "passage", kind: "need", choice: "care", label: "Care", emphasis: "primary" },
    { subject: "passage", kind: "need", choice: "education", label: "Education", emphasis: "secondary" },
  ];
  const nextTick = firstTick.map((action) => ({ ...action }));

  assert.equal(actionSurfaceSignature(firstTick), actionSurfaceSignature(nextTick));
});

test("a semantic action change invalidates the control surface", () => {
  const choosing = [
    { subject: "passage", kind: "need", choice: "care", label: "Care", emphasis: "primary" },
  ];
  const planning = [
    { subject: "passage", kind: "route", choice: "depart", label: "Launch crossing", emphasis: "primary" },
  ];

  assert.notEqual(actionSurfaceSignature(choosing), actionSurfaceSignature(planning));
});
