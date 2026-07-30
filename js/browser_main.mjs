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
import { analyse, Analyser } from "./shapes.mjs";
import { parse } from "./parser.mjs";
import {
  load_graph,
  resolve,
  check_collisions,
  hoistAndRun,
  uses_in,
  names_in_graph,
  rename_map,
  BUILTIN_MODULES,
} from "./modules.mjs";
import { BrowserModuleLoader } from "./module_loader_browser.mjs";

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
    return { ...observed(itp, host), error: null };
  } catch (e) {
    let error;
    if (e instanceof PlanesError) error = { tag: e.tag, message: e.message };
    else if (e instanceof PlanesSyntaxError) error = { tag: "syntax", message: e.message };
    else if (e instanceof RangeError) error = { tag: "recursion-too-deep", message: e.message };
    else throw e;
    return { ...observed(itp, host), error };
  }
}

// Everything a caller can observe about a finished run, in one place so the
// single-file and module-graph entry points cannot drift apart about what they
// hand back.
//
// `trace` is interp.mjs's own show/why trace — one entry per output line, in
// the same order, carrying the derivation of the expression that produced it
// and its source line. `annotations` is the `because` text each name last
// carried. Both are OBSERVATION, not effect: nothing here runs anything, and
// `effects` is byte-identical with or without a caller reading them
// (js/test/trace.test.mjs pins that).
function observed(itp, host) {
  return {
    output: itp.output,
    trace: itp.trace,
    annotations: Object.fromEntries(itp.annotations),
    effects: itp.effects,
    files: host.files,
  };
}

// A sentinel location for the entry source itself — it is never fetched (the
// caller already has `src` in hand), so it only has to be distinct from every
// real fetched location, never equal to one.
const ENTRY = "__entry__";

// Like runProgram, but resolves `use`d file-backed modules first (checkpoint
// v21.0 §248-249): a module path resolves relative to the importing source's
// own location, or `base` for the entry source itself, which has none. When
// `src` uses no file-backed module (the common case — every builtin-only
// program, and every program with no `use` at all), this delegates straight
// to runProgram: no fetch, no await cost. `loader` lets a caller reuse one
// loader (and its per-run cache) across many calls — paint.html constructs
// one per Run/Play press, not per frame, so a ticking program issues exactly
// one fetch per module for the life of that run.
export async function runProgramGraph(src, { base, files = {}, responses = {}, loader = null } = {}) {
  const used = uses_in(src);
  const fileBacked = used.filter((name) => !BUILTIN_MODULES.has(name));
  if (fileBacked.length === 0) {
    return runProgram(src, { files, responses });
  }

  const ldr = loader ?? new BrowserModuleLoader({ base });
  const host = new BrowserHost({ files, responses });
  const itp = new Interpreter({ host });
  try {
    const seen = new Map();
    const deps = [];
    for (const mod of used) {
      const target = resolve(ldr, mod, null);
      if (target !== null) deps.push(...(await load_graph(ldr, target, seen, [])));
    }
    const graph = [...deps, [ENTRY, src]];
    check_collisions(graph, ldr);
    const targetKey = ldr.key(ENTRY);
    hoistAndRun(itp, graph, targetKey, ldr);
    return { ...observed(itp, host), error: null };
  } catch (e) {
    let error;
    if (e instanceof PlanesError) error = { tag: e.tag, message: e.message };
    else if (e instanceof PlanesSyntaxError) error = { tag: "syntax", message: e.message };
    else if (e instanceof RangeError) error = { tag: "recursion-too-deep", message: e.message };
    else if (e && e.name === "ModuleError") error = { tag: "module-error", message: e.message };
    else throw e;
    return { ...observed(itp, host), error };
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

// Like analyseProgram, but follows `use`d file-backed modules first — the
// analyser analogue of runProgramGraph, and the browser counterpart of
// js/shapes_node.mjs's analyseFile(follow=true). Without this, a program that
// calls a draw.planes/math.planes helper would show those calls as
// `unresolved calls: …` instead of the console boundary they actually
// derive — accurate but useless to paint.html's surface pane once the three
// example programs adopt the drawing library in Phase 6.
export async function analyseProgramGraph(src, { base, loader = null } = {}) {
  const used = uses_in(src);
  const fileBacked = used.filter((name) => !BUILTIN_MODULES.has(name));
  if (fileBacked.length === 0) {
    return analyseProgram(src);
  }

  const ldr = loader ?? new BrowserModuleLoader({ base });
  try {
    const seen = new Map();
    const deps = [];
    for (const mod of used) {
      const target = resolve(ldr, mod, null);
      if (target !== null) deps.push(...(await load_graph(ldr, target, seen, [])));
    }
    const graph = [...deps, [ENTRY, src]];
    check_collisions(graph, ldr);
    const known = names_in_graph(graph, ldr);
    const renames = rename_map(graph, ldr);
    const targetKey = ldr.key(ENTRY);
    const combined = new Analyser();
    combined.entryFile = targetKey;
    let entryProg = null;
    for (const [location, fileSrc] of graph) {
      const prog = parse(fileSrc, known);
      const key = ldr.key(location);
      combined.collectDeclarations(prog, renames.get(location) ?? {}, key);
      if (key === targetKey) entryProg = prog;
    }
    return { surface: combined.analyseProg(entryProg), error: null };
  } catch (e) {
    if (e instanceof PlanesSyntaxError) {
      return { surface: null, error: { tag: "syntax", message: e.message } };
    }
    if (e && e.name === "ModuleError") {
      return { surface: null, error: { tag: "module-error", message: e.message } };
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


// ---- a stale module cache says so, instead of lying ---------------------------
//
// THE FAILURE THIS EXISTS FOR. These pages load about twenty-five same-origin
// ES modules with no versioning, because versioning them would need a build
// step and this repo does not have one — you open the file. A browser is then
// free to serve some of them from cache and fetch others, and Safari in
// particular keeps an instantiated module graph across a plain reload. After a
// change to the repo, a returning reader can get a MIXED SET: `sine` was added
// to grammar/vocabulary.json and to interp.mjs in one commit, and a browser
// that took the fresh JSON and the cached interpreter answered
//
//   ✗ unknown-builtin: no builtin is named 'sine'
//     try: the ten builtins are fixed and the lexer recognises only those, so
//     reaching this is a defect in the interpreter rather than in the program
//
// — which blames the interpreter, tells the reader to report a bug, and says
// "ten" while the vocabulary beside it says eleven. Every word of that is
// wrong and none of it points at the cache.
//
// WHAT CAN AND CANNOT BE FIXED. The `.planes` sources and modules this page
// fetches ITSELF are bustable, and are busted (js/module_loader_browser.mjs,
// paint.html) — a query string on a leaf fetch works. The `.mjs` graph is not:
// a query on an entry import does not propagate to that module's own relative
// imports, so busting the whole graph needs either rewritten import URLs (a
// build step) or `Cache-Control` (a server we control), and this page refuses
// both by design.
//
// So the graph is not prevented from going stale. It is made to SAY SO. This
// runs the interpreter that actually loaded against the vocabulary that
// actually loaded, and reports the disagreement in the one sentence that
// resolves it.

// A literal each builtin accepts far enough to reach its own dispatch. The
// argument is evaluated before the name is looked up, so any value that parses
// is enough; these are chosen to be the least surprising thing to read.
const PROBE_ARGUMENT = {
  count: "[1]", lower: '"A"', upper: '"a"', text: "1", whole: "1.5",
  ask: '"https://example.invalid"', read: '"x"', normalize: '"a"',
  join: '["a"]', rest: "[1, 2]", sine: "0",
};

// Every builtin the loaded vocabulary declares that the loaded interpreter
// does not implement. Effectful builtins refuse for their own reasons
// (`read` wants `use file`, `ask` wants a response) and those refusals are not
// this — only the tag that means "this interpreter has never heard of it".
export function unimplementedBuiltins() {
  const missing = [];
  for (const b of vocab.builtins) {
    const arg = PROBE_ARGUMENT[b.name] ?? "1";
    try {
      new Interpreter(new BrowserHost({})).run(`probe = ${b.name} of ${arg}\n`);
    } catch (e) {
      const tag = e instanceof PlanesError ? e.tag : null;
      if (tag === "unknown-builtin" || tag === "unknown-function") missing.push(b.name);
    }
  }
  return missing;
}

// null when the modules agree; otherwise the sentence to put in front of the
// reader. Deliberately names the remedy first and the diagnosis second — a
// reader who hits this wants to know what to press.
export function staleModuleWarning() {
  const missing = unimplementedBuiltins();
  if (!missing.length) return null;
  return (
    "This page is running a mix of old and new code — empty your browser's " +
    "cache and reload.\n\n" +
    `The vocabulary this page loaded declares ${vocab.builtins.length} builtins, ` +
    `and the interpreter it loaded does not implement ${missing.length} of them ` +
    `(${missing.join(", ")}). That cannot happen in one version of this repo, ` +
    "so the two came from different ones: your browser served some modules from " +
    "cache and fetched others.\n\n" +
    "In Safari: Develop → Empty Caches, then reload — a plain reload keeps ES " +
    "modules. In Chrome or Firefox: hold Shift and click reload."
  );
}

// ---- DOM wiring (only in a browser, and only on a page that has these
// exact four elements — paint.html imports runProgram/analyseProgram/
// surfaceReport from this module too, under its own element ids, and must
// not trip this page's wiring).
if (
  typeof document !== "undefined" &&
  document.getElementById("run") &&
  document.getElementById("surface") &&
  document.getElementById("source") &&
  document.getElementById("output")
) {
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

  const stale = staleModuleWarning();
  if (stale) show(stale, true);

  runBtn.addEventListener("click", run);
  surfaceBtn.addEventListener("click", surface);
  source.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run();
    if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === "Enter") surface();
  });
  if (!stale) run(); // run the sample on load, unless there is worse news
}
