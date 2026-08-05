// js/test/tutor_gate.test.mjs — the tutor.html build's own verification
// gate (build prompt §10.2, points B and C). Point A is
// js/test/tutor_scene.test.mjs's tests 1/2/3/6; point D is
// test_multiword_names.py, run by scripts/run_suites.py.
//
// WHY THIS FILE AND NOT scripts/verify-tutor-page.mjs. The build prompt
// asked for a standalone script, committed to the branch. This repository's
// own test_gate.py (`test_no_verification_script_exists_for_the_gate_not_to_
// run`) forbids exactly that and gates on its absence — found by running the
// gate against this branch before opening the PR, the same kind of
// pre-build-verification finding §1's own scope correction (runProgramGraph
// vs program_session.mjs) already models. The remedy test_gate.py itself
// names is this one: graduate the durable assertions into a suite the gate
// runs. So these are real `node --test` cases, not a report nothing runs.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

import { runProgramGraph } from "../browser_main.mjs";
import { walk } from "../paint/stream.mjs";
import { markSink } from "../paint/marks.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const PAINT = path.join(REPO, "paint");
const SCENE_BASE = pathToFileURL(PAINT + path.sep).href;

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

const STARTER_PROGRAM = `use scene

start
sky of "just before dark"
ground of "wet grass"
moon of 240, 90
star of 100, 60
flower of 120, 90
firefly of 300, 200
`;

// ---- B: the starter program runs clean under both implementations,
//         identically ------------------------------------------------------

test("B: the starter program produces byte-identical output under interp.py and js/interp.mjs", async () => {
  const restore = installFsFetch();
  const probe = path.join(PAINT, "__tutor_gate_starter_probe.planes");
  try {
    fs.writeFileSync(probe, STARTER_PROGRAM);
    const py = execFileSync(
      "python3",
      ["-c", "import json,sys\nfrom interp import Interpreter\nout = Interpreter().run_file(sys.argv[1])\nprint(json.dumps(out))\n", probe],
      { cwd: REPO, encoding: "utf-8" },
    );
    const pyOutput = JSON.parse(py.trim().split("\n").pop());

    const jsResult = await runProgramGraph(STARTER_PROGRAM, { base: SCENE_BASE });
    assert.equal(jsResult.error, null, jsResult.error && jsResult.error.message);

    assert.deepEqual(jsResult.output, pyOutput, "interp.py and js/interp.mjs disagree on the starter program");
    assert.ok(jsResult.output.length > 0, "the starter program produced no output");
  } finally {
    if (fs.existsSync(probe)) fs.unlinkSync(probe);
    restore();
  }
});

test("B: the starter program's marks are all hit-testable at their own centre (re-confirmed here, against the exact §3.5 text)", async () => {
  const restore = installFsFetch();
  try {
    const r = await runProgramGraph(STARTER_PROGRAM, { base: SCENE_BASE });
    assert.equal(r.error, null);
    const sink = markSink();
    const { errors } = walk(r.output, sink);
    assert.deepEqual(errors, []);
    assert.ok(sink.marks.length >= 6, `expected at least 6 marks (moon/star/flower stem/flower head/firefly + ground), found ${sink.marks.length}`);
  } finally {
    restore();
  }
});

// ---- C: provenance — a because-annotated binding reaches the mark's trace -

test("C: a because-annotated binding survives into result.annotations and into the mark's own derivation chain", async () => {
  const restore = installFsFetch();
  try {
    const src =
      'use scene\n\nstart\nsky of "just before dark"\nground of "wet grass"\n' +
      'let reach = 90 because "the corner gets the sun after noon"\n' +
      "flower of 120, reach\n";
    const r = await runProgramGraph(src, { base: SCENE_BASE });
    assert.equal(r.error, null, r.error && r.error.message);

    // The sentence survives into the run's own reported annotations.
    assert.equal(r.annotations.reach, "the corner gets the sun after noon");

    // And the node reached from result.trace[mark.line] — the same lookup
    // tutor.html's card does — names the annotated binding somewhere in its
    // derivation chain, not just in the flat annotations map.
    const sink = markSink();
    const { errors } = walk(r.output, sink);
    assert.deepEqual(errors, []);
    const headMark = sink.marks.find((m) => m.kind === "circle" && m.geometry.r === 9);
    assert.ok(headMark, "the flower's head circle was not found among the marks");
    const entry = r.trace[headMark.line];
    assert.ok(entry, "the flower head's stream line has no trace entry");
    const [node] = entry;

    function reachesName(n, label, seen = new Set()) {
      if (!n || seen.has(n)) return false;
      seen.add(n);
      if (n.kind === "name" && n.label === label) return true;
      return (Array.isArray(n.inputs) ? n.inputs : []).some((i) => reachesName(i, label, seen));
    }
    assert.ok(reachesName(node, "reach"), "the flower head's derivation never reaches the annotated name 'reach'");
  } finally {
    restore();
  }
});
