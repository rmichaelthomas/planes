// js/run_file.mjs — run a file plus everything it uses (Node-only).
//
// The port of interp.py's Interpreter.run_file. Kept out of interp.mjs so
// interp.mjs stays browser-loadable — the browser deliverable runs a single-file
// program with Interpreter.run(src), never a module graph. Node-only because it
// constructs the Node module loader directly (module_loader_node.mjs, over
// node:fs); modules.mjs itself is pure and the browser has its own entry point
// (browser_main.mjs's runProgramGraph, over module_loader_browser.mjs). Operates
// on an Interpreter instance via its public hoist / exec_stmt / env / output.

import { load_graph, check_collisions, hoistAndRun } from "./modules.mjs";
import { createNodeModuleLoader } from "./module_loader_node.mjs";

export async function runFile(interp, filePath) {
  const loader = createNodeModuleLoader();
  const graph = await load_graph(loader, filePath);
  check_collisions(graph, loader);
  const targetKey = loader.key(filePath);
  return hoistAndRun(interp, graph, targetKey, loader);
}
