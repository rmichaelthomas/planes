// js/run_file.mjs — run a file plus everything it uses (Node-only).
//
// The port of interp.py's Interpreter.run_file. Kept out of interp.mjs (and
// importing modules.mjs, which touches node:fs) so interp.mjs stays
// browser-loadable — the browser deliverable runs a single-file program with
// Interpreter.run(src), never a module graph. Operates on an Interpreter
// instance via its public hoist / exec_stmt / env / output.

import path from "node:path";
import { parse } from "./parser.mjs";
import {
  load_graph,
  check_collisions,
  names_in_graph,
  rename_map,
} from "./modules.mjs";

export function runFile(interp, filePath) {
  const graph = load_graph(filePath);
  check_collisions(graph);
  const known = names_in_graph(graph);
  const renames = rename_map(graph);
  const targetAbs = path.resolve(filePath);
  let entry = [];
  for (const [p, src] of graph) {
    const prog = parse(src, known);
    interp.hoist(prog, interp.env, renames.get(p) ?? {});
    if (path.resolve(p) === targetAbs) {
      entry = prog;
    } else {
      for (const stmt of prog) {
        if (stmt.__node === "Use") interp.exec_stmt(stmt, interp.env);
      }
    }
  }
  for (const stmt of entry) {
    if (stmt.__node === "Note") continue;
    interp.exec_stmt(stmt, interp.env);
  }
  return interp.output;
}
