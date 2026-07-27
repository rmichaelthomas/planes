// js/shapes_node.mjs — analyseFile: a surface for a file plus everything it uses.
//
// The Node-only half of the analyser (A.7's expected split): following imports
// across files needs the module graph in modules.mjs, resolved here via the
// Node module loader. Keeping it here lets js/shapes.mjs — which the browser
// loads for the single-file effect-surface view — stay free of any node:
// import. The port of shapes.py's analyse_file.

import fs from "node:fs";
import { parse } from "./parser.mjs";
import { Analyser, analyse } from "./shapes.mjs";
import { load_graph, check_collisions, names_in_graph, rename_map } from "./modules.mjs";
import { createNodeModuleLoader } from "./module_loader_node.mjs";

export async function analyseFile(p, follow = true) {
  if (!follow) {
    // The single-file surface: `file` is the path as given (not resolved),
    // matching shapes.py's analyse(open(path).read(), file=path).
    return analyse(fs.readFileSync(p, "utf-8"), p);
  }
  const loader = createNodeModuleLoader();
  const graph = await load_graph(loader, p);
  check_collisions(graph, loader);
  const known = names_in_graph(graph, loader);
  const renames = rename_map(graph, loader);
  const combined = new Analyser();
  const targetKey = loader.key(p);
  combined.entryFile = targetKey;
  let entryProg = null;
  for (const [location, src] of graph) {
    const prog = parse(src, known);
    const key = loader.key(location);
    combined.collectDeclarations(prog, renames.get(location) ?? {}, key);
    if (key === targetKey) entryProg = prog;
  }
  return combined.analyseProg(entryProg);
}
