// js/modules.mjs — Planes module resolution, ported from modules.py.
//
// `use http` / `use file` name builtin capability modules; `use utils` names a
// file utils.planes resolved relative to the importing file. Node-only: it
// reads .planes files from disk. interp.mjs never imports it (it is pulled in
// only by js/run_file.mjs, the Node entry that loads a module graph), so
// interp.mjs stays browser-loadable.

import fs from "node:fs";
import path from "node:path";
import { tokenize } from "./lexer.mjs";
import { scan_names } from "./parser.mjs";

export const BUILTIN_MODULES = new Set(["http", "file"]);

export class ModuleError extends Error {
  constructor(name, detail, fix = "") {
    let msg = `${detail}`;
    if (fix) msg += `\n  try: ${fix}`;
    super(msg);
    this.name = "ModuleError";
    this.moduleName = name;
    this.detail = detail;
    this.fix = fix;
  }
}

// Locate the file for `use name`. Returns null for builtins.
export function resolve(name, fromPath) {
  if (BUILTIN_MODULES.has(name)) return null;
  const base = fromPath ? path.dirname(path.resolve(fromPath)) : process.cwd();
  const candidate = path.join(base, `${name}.planes`);
  if (fs.existsSync(candidate)) return candidate;
  throw new ModuleError(
    name,
    `no module named '${name}'`,
    `create ${name}.planes next to this file, or use one of: ` +
      `${[...BUILTIN_MODULES].sort().join(", ")}`,
  );
}

// Load a file and everything it uses, depth first. Returns [path, source] pairs
// in dependency order — imports before importers. Cycles raise.
export function load_graph(p, seen = null, stack = null) {
  seen = seen ?? new Map();
  stack = stack ?? [];
  const key = path.resolve(p);
  if (seen.has(key)) return [];
  if (stack.includes(key)) {
    const cycle = [...stack, key].map((x) => path.basename(x)).join(" -> ");
    throw new ModuleError(
      path.basename(p),
      `module cycle: ${cycle}`,
      "break the cycle by moving shared code to a third file",
    );
  }
  const src = fs.readFileSync(p, "utf-8");
  stack.push(key);
  const ordered = [];
  for (const mod of uses_in(src)) {
    const target = resolve(mod, p);
    if (target !== null) ordered.push(...load_graph(target, seen, stack));
  }
  stack.pop();
  seen.set(key, true);
  ordered.push([p, src]);
  return ordered;
}

// Module names this source uses, read from tokens (not a full parse — a file may
// call multi-word functions from a not-yet-loaded module).
export function uses_in(src) {
  const toks = tokenize(src);
  const out = [];
  for (let i = 0; i < toks.length; i++) {
    if (toks[i].kind === "USE" && i + 1 < toks.length && toks[i + 1].kind === "NAME") {
      out.push(toks[i + 1].value);
    }
  }
  return out;
}

// Renames declared by this file, as {module: {old: new}}.
export function renames_in(src) {
  const toks = tokenize(src);
  const out = {};
  let i = 0;
  while (i < toks.length) {
    if (toks[i].kind === "USE" && toks[i + 1].kind === "NAME") {
      const mod = toks[i + 1].value;
      let j = i + 2;
      const pairs = {};
      while (toks[j].kind === "WITH") {
        j += 1;
        const old = [];
        while (toks[j].kind === "NAME") {
          old.push(toks[j].value);
          j += 1;
        }
        if (toks[j].kind !== "AS") break;
        j += 1;
        const nw = [];
        while (toks[j].kind === "NAME") {
          nw.push(toks[j].value);
          j += 1;
        }
        if (old.length && nw.length) pairs[old.join(" ")] = nw.join(" ");
      }
      if (Object.keys(pairs).length) {
        out[mod] = { ...(out[mod] ?? {}), ...pairs };
      }
      i = j;
      continue;
    }
    i += 1;
  }
  return out;
}

// The name each file contributes, after the importer's renames. Returns
// [path, original, effective] triples.
export function effective_names(graph) {
  const applied = {};
  for (const [, src] of graph) {
    for (const [mod, pairs] of Object.entries(renames_in(src))) {
      applied[mod] = { ...(applied[mod] ?? {}), ...pairs };
    }
  }
  const out = [];
  for (const [p, src] of graph) {
    const mod = path.basename(p).replace(".planes", "");
    const pairs = applied[mod] ?? {};
    for (const name of scan_names(src).keys()) {
      out.push([p, name, name in pairs ? pairs[name] : name]);
    }
  }
  return out;
}

// Every callable name in a loaded graph, after renames (both original and
// renamed forms).
export function names_in_graph(graph) {
  const names = new Set();
  for (const [, original, effective] of effective_names(graph)) {
    names.add(original);
    names.add(effective);
  }
  return names;
}

// path -> {original name: name it is known by elsewhere}.
export function rename_map(graph) {
  const out = new Map();
  for (const [p, original, effective] of effective_names(graph)) {
    if (original !== effective) {
      if (!out.has(p)) out.set(p, {});
      out.get(p)[original] = effective;
    }
  }
  return out;
}

// Two files defining the same function name is an error.
export function check_collisions(graph) {
  const owners = new Map();
  for (const [p, , name] of effective_names(graph)) {
    if (!owners.has(name)) owners.set(name, []);
    owners.get(name).push(p);
  }
  const clashes = [];
  for (const [name, ps] of owners) {
    if (new Set(ps).size > 1) clashes.push([name, ps]);
  }
  if (!clashes.length) return;
  clashes.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  const lines = [];
  for (const [name, ps] of clashes) {
    const where = [...new Set(ps.map((p) => path.basename(p)))].sort().join(", ");
    lines.push(`'${name}' is defined in ${where}`);
  }
  const first = clashes[0][0];
  const other = [...new Set(clashes[0][1].map((p) => path.basename(p)))].sort()[0];
  const otherMod = other.replace(".planes", "");
  throw new ModuleError(
    first,
    "two modules define the same name:\n  " + lines.join("\n  "),
    `rename one at the point of use, e.g. \`use ${otherMod} with ${first} as my ${first}\``,
  );
}
