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

// ---- DOM wiring (only in a browser)
if (typeof document !== "undefined") {
  const $ = (id) => document.getElementById(id);
  const runBtn = $("run");
  const source = $("source");
  const outEl = $("output");

  function render() {
    const { output, error } = runProgram(source.value);
    const lines = [...output];
    if (error) lines.push(`✗ ${error.tag}: ${error.message}`);
    outEl.textContent = lines.length ? lines.join("\n") : "(no output)";
    outEl.classList.toggle("error", Boolean(error));
  }

  runBtn.addEventListener("click", render);
  source.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") render();
  });
  render(); // run the sample on load
}
