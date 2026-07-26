// js/shapes_node.mjs — analyseFile: a surface for a file plus everything it uses.
//
// The Node-only half of the analyser (A.7's expected split): following imports
// across files needs the filesystem and the module graph in modules.mjs, which
// imports node:fs. Keeping it here lets js/shapes.mjs — which the browser loads
// for the single-file effect-surface view — stay free of any node: import. The
// port of shapes.py's analyse_file.

import fs from "node:fs";
import path from "node:path";
import { parse } from "./parser.mjs";
import { Analyser, analyse } from "./shapes.mjs";
import {
  load_graph,
  check_collisions,
  names_in_graph,
  rename_map,
} from "./modules.mjs";

export function analyseFile(p, follow = true) {
  if (!follow) {
    // The single-file surface: `file` is the path as given (not resolved),
    // matching shapes.py's analyse(open(path).read(), file=path).
    return analyse(fs.readFileSync(p, "utf-8"), p);
  }
  const graph = load_graph(p);
  check_collisions(graph);
  const known = names_in_graph(graph);
  const renames = rename_map(graph);
  const combined = new Analyser();
  combined.entryFile = path.resolve(p);
  const targetAbs = path.resolve(p);
  let entryProg = null;
  for (const [pp, src] of graph) {
    const prog = parse(src, known);
    combined.collectDeclarations(prog, renames.get(pp) ?? {}, path.resolve(pp));
    if (path.resolve(pp) === targetAbs) entryProg = prog;
  }
  return combined.analyseProg(entryProg);
}
