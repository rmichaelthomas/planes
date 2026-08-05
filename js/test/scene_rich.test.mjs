// js/test/scene_rich.test.mjs — the rich paint/scene.planes's own
// verification gate (build prompt planes_build_prompt_tutor_redesign.md
// §11.2, points A/B/C). Supersedes js/test/tutor_scene.test.mjs (v26.0/#71):
// that suite pinned the THIN scene.planes's exact output shape (a flat
// `background`/`fill` per sky/ground, a bare circle for a flower's head) —
// assertions the v27.0 richness (gradients, shadows, curved paths, paired
// helpers) makes false by design, not by defect. Its coverage is carried
// forward here at the new shape: every phrase still refuses correctly and
// names the fix, every helper still emits an accepted stream, every mark is
// still hit-testable at its own centre, and the reserved-word ceiling still
// holds — plus the two things v27.0 actually adds: the vocabulary/scene.planes
// SEAM (§420-421) and the one-subject-per-rich-helper invariant (§415).
//
// WHY THIS IS A SUITE AND NOT A STANDALONE SCRIPT. Same rule
// js/test/garden_gate.test.mjs and js/test/tutor_gate.test.mjs state: a
// build's own verification belongs in `node --test`, which the gate already
// runs, not in a `scripts/verify-*.mjs` `test_gate.py`'s retirement rule
// forbids.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { runProgramGraph, analyseProgramGraph } from "../browser_main.mjs";
import { walk } from "../paint/stream.mjs";
import { markSink } from "../paint/marks.mjs";
import { hitTest, outlineOf } from "../paint/hit.mjs";
import { scan_names } from "../parser.mjs";
import {
  PLACEABLES,
  skyPhraseNames,
  groundPhraseNames,
  skyRefusalMessage,
  groundRefusalMessage,
} from "../scene_vocab.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const PAINT = path.join(REPO, "paint");
const SCENE_BASE = pathToFileURL(PAINT + path.sep).href;
const DIMENSIONS = { width: 480, height: 360 };

function installFsFetch() {
  const real = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const p = fileURLToPath(url);
    if (!fs.existsSync(p)) return { ok: false, text: async () => "" };
    return { ok: true, text: async () => fs.readFileSync(p, "utf-8") };
  };
  return () => {
    if (real) globalThis.fetch = real;
    else delete globalThis.fetch;
  };
}

const sceneSrc = () => fs.readFileSync(path.join(PAINT, "scene.planes"), "utf-8");

async function run(src) {
  return runProgramGraph(src, { base: SCENE_BASE });
}

const STARTER_PROGRAM = `use scene

start
sky of "middle of the afternoon"
ground of "wet grass"

sun of 240, 70
two-bees of 300, 150

let spot = 90 because "it's the tallest in the yard"
two-flowers of 120, spot
`;

// ---- A: vocabulary/seam --------------------------------------------------

test("A: every sky phrase js/scene_vocab.mjs lists is accepted by scene.planes with a distinct background", async () => {
  const restore = installFsFetch();
  try {
    const lines = new Set();
    for (const phrase of skyPhraseNames()) {
      const r = await run(`use scene\n\nstart\nsky of "${phrase}"\n`);
      assert.equal(r.error, null, `${phrase}: ${r.error && r.error.message}`);
      const bg = r.output.find((l) => l.startsWith("draw gradient ") || l.startsWith("draw background "));
      assert.ok(bg, `${phrase} produced no sky-painting line`);
      lines.add(bg);
    }
    assert.equal(lines.size, skyPhraseNames().length, "two sky phrases painted the same gradient");
  } finally {
    restore();
  }
});

test("A: every ground phrase js/scene_vocab.mjs lists is accepted by scene.planes with a distinct fill", async () => {
  const restore = installFsFetch();
  try {
    const lines = new Set();
    for (const phrase of groundPhraseNames()) {
      const r = await run(`use scene\n\nstart\nground of "${phrase}"\n`);
      assert.equal(r.error, null, `${phrase}: ${r.error && r.error.message}`);
      const bg = r.output.find((l) => l.startsWith("draw gradient ") || l.startsWith("draw fill "));
      assert.ok(bg, `${phrase} produced no ground-painting line`);
      lines.add(bg);
    }
    assert.equal(lines.size, groundPhraseNames().length, "two ground phrases painted the same gradient");
  } finally {
    restore();
  }
});

test("A: an unrecognised sky phrase refuses, naming the fix and exactly js/scene_vocab.mjs's phrase list", async () => {
  const restore = installFsFetch();
  try {
    const r = await run('use scene\n\nstart\nsky of "a stormy tuesday"\n');
    assert.ok(r.error, "an unrecognised sky phrase must refuse, not paint a default");
    assert.equal(r.error.tag, "unknown-sky-feeling");
    assert.equal(r.error.message, `unknown-sky-feeling: ${skyRefusalMessage("a stormy tuesday")}`);
  } finally {
    restore();
  }
});

test("A: and an unrecognised ground phrase does too", async () => {
  const restore = installFsFetch();
  try {
    const r = await run('use scene\n\nstart\nground of "a muddy puddle"\n');
    assert.ok(r.error, "an unrecognised ground phrase must refuse, not paint a default");
    assert.equal(r.error.tag, "unknown-ground-feeling");
    assert.equal(r.error.message, `unknown-ground-feeling: ${groundRefusalMessage("a muddy puddle")}`);
  } finally {
    restore();
  }
});

test("A: no name defined in scene.planes collides with vocabulary.json's 45-word reserved surface", () => {
  const vocab = JSON.parse(fs.readFileSync(path.join(REPO, "grammar", "vocabulary.json"), "utf-8"));
  const reserved = new Set([...vocab.keywords.map((k) => k.word), ...vocab.builtins.map((b) => b.name)]);
  assert.equal(reserved.size, 45, `expected 45 reserved words, computed ${reserved.size}`);
  const defined = scan_names(sceneSrc());
  const collisions = [...defined.keys()].filter((name) => reserved.has(name));
  assert.deepEqual(collisions, [], `scene.planes defines a reserved word: ${collisions.join(", ")}`);
});

test("A: every placeable js/scene_vocab.mjs lists is a real, callable scene.planes helper", () => {
  const defined = scan_names(sceneSrc());
  for (const p of PLACEABLES) {
    assert.ok(defined.has(p.name), `the key lists "${p.name}" but scene.planes defines no such name`);
  }
});

// ---- B: rich render --------------------------------------------------------

const HELPER_PROGRAMS = {
  start: 'use scene\n\nstart\n',
  sky: 'use scene\n\nstart\nsky of "early morning"\n',
  ground: 'use scene\n\nstart\nground of "wet grass"\n',
  sun: 'use scene\n\nstart\nsun of 100, 50\n',
  moon: 'use scene\n\nstart\nmoon of 100, 50\n',
  star: 'use scene\n\nstart\nstar of 100, 50\n',
  flower: 'use scene\n\nstart\nflower of 100, 50\n',
  bee: 'use scene\n\nstart\nbee of 100, 50\n',
  firefly: 'use scene\n\nstart\nfirefly of 100, 50\n',
  "two-flowers": 'use scene\n\nstart\ntwo-flowers of 120, 90\n',
  "two-bees": 'use scene\n\nstart\ntwo-bees of 300, 150\n',
  "two-fireflies": 'use scene\n\nstart\ntwo-fireflies of 300, 150\n',
  "custom-sky": 'use scene\n\nstart\ncustom-sky of 0.7, 0.1, 40\n',
};

test("B: every scene.planes helper emits a stream walk accepts with zero errors", async () => {
  const restore = installFsFetch();
  try {
    for (const [name, src] of Object.entries(HELPER_PROGRAMS)) {
      const r = await run(src);
      assert.equal(r.error, null, `${name}: ${r.error && r.error.message}`);
      const { errors } = walk(r.output, markSink());
      assert.deepEqual(errors, [], `${name} emitted a protocol error`);
    }
  } finally {
    restore();
  }
});

test("B: every scene.planes helper's marks are all hit-testable at their own centre", async () => {
  const restore = installFsFetch();
  try {
    for (const [name, src] of Object.entries(HELPER_PROGRAMS)) {
      const r = await run(src);
      assert.equal(r.error, null, name);
      const sink = markSink();
      const { errors } = walk(r.output, sink);
      assert.deepEqual(errors, []);
      for (const mark of sink.marks) {
        if (!mark.visible) continue;
        const pts = outlineOf(mark);
        const cx = pts.reduce((s, [px]) => s + px, 0) / pts.length;
        const cy = pts.reduce((s, [, py]) => s + py, 0) / pts.length;
        const found = hitTest(sink.marks, cx, cy, { area: DIMENSIONS });
        assert.ok(found >= 0, `${name}: mark kind=${mark.kind} on line ${mark.line} is not hit-testable at its own centre`);
      }
    }
  } finally {
    restore();
  }
});

// THE RICHNESS-VS-CARD INVARIANT (§415), checked mechanically rather than by
// eye: a rich helper's marks must all trace back to the ONE line the child
// wrote, so tutor.html's card heading (definitionAt/callAt off that single
// line) has exactly one subject to name. This needs no client-side subject
// map — interp.py/interp.mjs's own trace_line already reports the innermost
// call site actually WRITTEN IN THE ENTRY FILE for every show inside a
// used module, which collapses a helper's whole internal call tree (petal
// calls inside flower, both flowers inside two-flowers) onto that one line.
test("B: every rich helper's marks resolve to exactly one subject (one traced source line)", async () => {
  const restore = installFsFetch();
  try {
    for (const [name, src] of Object.entries(HELPER_PROGRAMS)) {
      if (name === "start") continue; // draws nothing
      const r = await run(src);
      assert.equal(r.error, null, name);
      const sink = markSink();
      walk(r.output, sink);
      assert.ok(sink.marks.length > 0, `${name} drew no marks`);
      const lines = new Set();
      for (const mark of sink.marks) {
        const entry = r.trace[mark.line];
        if (entry) lines.add(entry[1]);
      }
      assert.equal(lines.size, 1, `${name}: marks span ${lines.size} distinct source lines, expected exactly 1`);
    }
  } finally {
    restore();
  }
});

test("B: a paired helper's two placements are still two separately-clickable marks, both attributed to the one call line", async () => {
  const restore = installFsFetch();
  try {
    const r = await run(HELPER_PROGRAMS["two-flowers"]);
    assert.equal(r.error, null);
    const sink = markSink();
    walk(r.output, sink);
    // two flowers, each stem+leaf+6 petals+centre = 9 marks apiece
    assert.equal(sink.marks.length, 18, `expected 18 marks for a pair of flowers, found ${sink.marks.length}`);
    const centres = sink.marks.filter((m) => m.kind === "circle" && m.geometry.r === 5);
    assert.equal(centres.length, 2, "expected two flower-centre marks");
    assert.notEqual(centres[0].geometry.x, centres[1].geometry.x, "the pair's two flowers must sit at different x positions");
  } finally {
    restore();
  }
});

test("B: the starter program produces byte-identical output under interp.py and js/interp.mjs", async () => {
  const restore = installFsFetch();
  const probe = path.join(PAINT, "__scene_rich_starter_probe.planes");
  try {
    fs.writeFileSync(probe, STARTER_PROGRAM);
    const { execFileSync } = await import("node:child_process");
    const py = execFileSync(
      "python3",
      ["-c", "import json,sys\nfrom interp import Interpreter\nout = Interpreter().run_file(sys.argv[1])\nprint(json.dumps(out))\n", probe],
      { cwd: REPO, encoding: "utf-8" },
    );
    const pyOutput = JSON.parse(py.trim().split("\n").pop());

    const jsResult = await runProgramGraph(STARTER_PROGRAM, { base: SCENE_BASE });
    assert.equal(jsResult.error, null, jsResult.error && jsResult.error.message);
    assert.deepEqual(jsResult.output, pyOutput, "interp.py and js/interp.mjs disagree on the starter program");
  } finally {
    if (fs.existsSync(probe)) fs.unlinkSync(probe);
    restore();
  }
});

// ---- C: the boundary — exact throughout, approximate only under a planted
//         control that reaches `sine` ---------------------------------------

test("C: the starter program's static surface reports console and exact, without running it", async () => {
  const restore = installFsFetch();
  try {
    const { surface, error } = await analyseProgramGraph(STARTER_PROGRAM, { base: SCENE_BASE });
    assert.equal(error, null);
    assert.ok(!surface.isPure(), "a program that draws is not pure");
    assert.deepEqual(surface.boundaries(), ["console"]);
    assert.ok(!surface.producesApproximate(), "the starter program never reaches sine or an irrational root");
  } finally {
    restore();
  }
});

test("C: every scene.planes helper's own surface reports exact (no helper reaches sine or root)", async () => {
  const restore = installFsFetch();
  try {
    for (const [name, src] of Object.entries(HELPER_PROGRAMS)) {
      const { surface, error } = await analyseProgramGraph(src, { base: SCENE_BASE });
      assert.equal(error, null, name);
      assert.ok(!surface.producesApproximate(), `${name}'s surface reports approximate — it reaches sine or root`);
    }
  } finally {
    restore();
  }
});

test("C (control): a program that DOES reach sine reports approximate — proving the exactness check itself is live", async () => {
  const restore = installFsFetch();
  try {
    const { surface, error } = await analyseProgramGraph("wobble = sine of 45\n", { base: SCENE_BASE });
    assert.equal(error, null);
    assert.ok(surface.producesApproximate(), "a program calling `sine` must report approximate");
  } finally {
    restore();
  }
});
