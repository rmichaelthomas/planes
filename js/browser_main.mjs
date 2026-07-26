// js/browser_main.mjs — the browser entry point (the deliverable's engine).
//
// Loads the JavaScript implementation and runs a Planes program in a browser,
// with no build step: the grammar data is imported as JSON modules straight
// from the single source of truth (grammar/*.json — A.7 keeps them read-only,
// this only reads), and the interpreter runs against the in-memory BrowserHost.
// The same module runs under Node — runProgram() has no DOM dependency, so the
// browser code path is testable headless (js/test/browser.test.mjs); the DOM
// wiring at the bottom is guarded and only fires in a real page.

import vocab from "../grammar/vocabulary.json" with { type: "json" };
import amber from "../grammar/messages/amber.json" with { type: "json" };
import { setVocabulary, setAmberTemplates } from "./grammar_data.mjs";
import { Interpreter, PlanesError } from "./interp.mjs";
import { PlanesSyntaxError } from "./lexer.mjs";
import { BrowserHost } from "./host_browser.mjs";
import { analyse } from "./shapes.mjs";

// Inject the grammar once, from the imported JSON — the browser analogue of
// loader_node.mjs's fs reads.
setVocabulary(vocab);
setAmberTemplates(amber);

// Run a Planes program string and return { output, effects, error }. Pure of
// the DOM, so it runs under Node too. `files`/`responses` seed the in-memory
// VFS and the ask stubs.
export function runProgram(src, { files = {}, responses = {} } = {}) {
  const host = new BrowserHost({ files, responses });
  const itp = new Interpreter({ host });
  try {
    itp.run(src);
    return { output: itp.output, effects: itp.effects, files: host.files, error: null };
  } catch (e) {
    let error;
    if (e instanceof PlanesError) error = { tag: e.tag, message: e.message };
    else if (e instanceof PlanesSyntaxError) error = { tag: "syntax", message: e.message };
    else if (e instanceof RangeError) error = { tag: "recursion-too-deep", message: e.message };
    else throw e;
    return { output: itp.output, effects: itp.effects, files: host.files, error };
  }
}

// The static effect surface of a program string, WITHOUT running it (A.5). The
// browser analogue of shapes_cli.py — analyse(src) never executes anything, so
// this says what the program *would* touch, not what it did. Returns
// { surface, error }; a parse failure (PlanesSyntaxError, or PlanesAmbiguity,
// its subclass) is reported, not thrown.
export function analyseProgram(src) {
  try {
    return { surface: analyse(src), error: null };
  } catch (e) {
    if (e instanceof PlanesSyntaxError) {
      return { surface: null, error: { tag: "syntax", message: e.message } };
    }
    throw e;
  }
}

// The surface as human-readable text: the boundaries and destinations it
// touches, then — since shapes.js carries provenance for free — a `why` block
// naming where each target derives from. Nothing here runs the program.
export function surfaceReport(surface) {
  const lines = [surface.render()];
  const withOrigins = [];
  for (const e of surface.declared) {
    const names = [...new Set(surface.originsOf(e).map(([n]) => n))];
    if (names.length) {
      withOrigins.push(`  ${e}\n      why → derives from: ${names.join(", ")}`);
    }
  }
  if (withOrigins.length) {
    lines.push("");
    lines.push("why — where each target comes from (nothing was run):");
    lines.push(...withOrigins);
  }
  return lines.join("\n");
}

// ---- DOM wiring (only in a browser)
if (typeof document !== "undefined") {
  const $ = (id) => document.getElementById(id);
  const runBtn = $("run");
  const surfaceBtn = $("surface");
  const source = $("source");
  const outEl = $("output");

  function show(text, isError) {
    outEl.textContent = text;
    outEl.classList.toggle("error", Boolean(isError));
  }

  function run() {
    const { output, error } = runProgram(source.value);
    const lines = [...output];
    if (error) lines.push(`✗ ${error.tag}: ${error.message}`);
    show(lines.length ? lines.join("\n") : "(no output)", Boolean(error));
  }

  function surface() {
    const { surface: s, error } = analyseProgram(source.value);
    if (error) {
      show(`✗ ${error.tag}: ${error.message}`, true);
      return;
    }
    show(
      "EFFECT SURFACE — what this program would touch, without running it:\n\n" +
        surfaceReport(s),
      false,
    );
  }

  runBtn.addEventListener("click", run);
  surfaceBtn.addEventListener("click", surface);
  source.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run();
    if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === "Enter") surface();
  });
  run(); // run the sample on load
}
