// js/modules.mjs — Planes module resolution, ported from modules.py.
//
// `use http` / `use file` name builtin capability modules; `use utils` names a
// file utils.planes resolved relative to the importing file. Pure: every
// host-bound operation (turning a module name into a location, reading the
// text at a location) is supplied by a loader — an ordinary object with
// locate/read/key/label, not a Host method (js/host.mjs's seven-method
// interface stays closed; see module_loader_node.mjs / module_loader_browser.mjs
// for the two implementations). This file imports nothing from the outside
// world, so it loads unchanged under Node and in a browser tab.

import { tokenize } from "./lexer.mjs";
import { parse, scan_names } from "./parser.mjs";

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

// The ModuleError a loader raises when `name` cannot be found — shared so
// every loader's "not found" message is byte-identical, whether the check
// happens synchronously (Node's existsSync, inside locate) or only after a
// failed fetch (a browser, inside read).
export function missingModuleError(name) {
  return new ModuleError(
    name,
    `no module named '${name}'`,
    `create ${name}.planes next to this file, or use one of: ` +
      `${[...BUILTIN_MODULES].sort().join(", ")}`,
  );
}

// Locate the file for `use name`. Returns null for builtins. `fromLocation` is
// the importing file's own location, or null when there is none (the loader
// resolves that case against its own base). Throws ModuleError (via the
// loader) if `name` cannot be found.
export function resolve(loader, name, fromLocation) {
  if (BUILTIN_MODULES.has(name)) return null;
  return loader.locate(name, fromLocation);
}

// Load a location and everything it uses, depth first, via `loader`. Returns
// [location, source] pairs in dependency order — imports before importers.
// Cycles raise. Async because a loader's `read` may be (a browser fetch).
export async function load_graph(loader, location, seen = null, stack = null) {
  seen = seen ?? new Map();
  stack = stack ?? [];
  const key = loader.key(location);
  if (seen.has(key)) return [];
  if (stack.some((s) => s.key === key)) {
    const cycle = [...stack, { location, key }]
      .map((s) => loader.label(s.location))
      .join(" -> ");
    throw new ModuleError(
      loader.label(location),
      `module cycle: ${cycle}`,
      "break the cycle by moving shared code to a third file",
    );
  }
  const src = await loader.read(location);
  stack.push({ location, key });
  const ordered = [];
  for (const mod of cachedUsesIn(src)) {
    const target = resolve(loader, mod, location);
    if (target !== null) ordered.push(...(await load_graph(loader, target, seen, stack)));
  }
  stack.pop();
  seen.set(key, true);
  ordered.push([location, src]);
  return ordered;
}

// load_graph's own recursive lookup of a file's `use` names — same
// text-keyed caching as renames_in/scan_names above, and the same reasoning:
// pure in src alone, so a cache hit is never stale.
const usesInCache = new Map();
function cachedUsesIn(src) {
  let r = usesInCache.get(src);
  if (r === undefined) {
    r = uses_in(src);
    usesInCache.set(src, r);
  }
  return r;
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

// renames_in/scan_names are pure functions of a file's own source text —
// nothing about them depends on which graph or which run asked. Caching them
// by source text is always correct (a text change is a different cache key,
// not a stale hit) and matters for a ticking program: without it, an
// unchanging library file gets re-tokenized twice per file on every single
// frame, forever, for text that never changes within a run.
const renamesInCache = new Map();
const scanNamesCache = new Map();

function cachedRenamesIn(src) {
  let r = renamesInCache.get(src);
  if (r === undefined) {
    r = renames_in(src);
    renamesInCache.set(src, r);
  }
  return r;
}

function cachedScanNames(src) {
  let r = scanNamesCache.get(src);
  if (r === undefined) {
    r = scan_names(src);
    scanNamesCache.set(src, r);
  }
  return r;
}

// The name each file contributes, after the importer's renames. Returns
// [location, original, effective] triples. `loader` supplies `label` for
// deriving a location's own module name (its basename minus ".planes").
export function effective_names(graph, loader) {
  const applied = {};
  for (const [, src] of graph) {
    for (const [mod, pairs] of Object.entries(cachedRenamesIn(src))) {
      applied[mod] = { ...(applied[mod] ?? {}), ...pairs };
    }
  }
  const out = [];
  for (const [location, src] of graph) {
    const mod = loader.label(location).replace(/\.planes$/, "");
    const pairs = applied[mod] ?? {};
    for (const name of cachedScanNames(src).keys()) {
      out.push([location, name, name in pairs ? pairs[name] : name]);
    }
  }
  return out;
}

// Every callable name in a loaded graph, after renames (both original and
// renamed forms).
export function names_in_graph(graph, loader) {
  const names = new Set();
  for (const [, original, effective] of effective_names(graph, loader)) {
    names.add(original);
    names.add(effective);
  }
  return names;
}

// location -> {original name: name it is known by elsewhere}.
export function rename_map(graph, loader) {
  const out = new Map();
  for (const [location, original, effective] of effective_names(graph, loader)) {
    if (original !== effective) {
      if (!out.has(location)) out.set(location, {});
      out.get(location)[original] = effective;
    }
  }
  return out;
}

// Two files defining the same function name is an error.
export function check_collisions(graph, loader) {
  const owners = new Map();
  for (const [location, , name] of effective_names(graph, loader)) {
    if (!owners.has(name)) owners.set(name, []);
    owners.get(name).push(location);
  }
  const clashes = [];
  for (const [name, locs] of owners) {
    if (new Set(locs).size > 1) clashes.push([name, locs]);
  }
  if (!clashes.length) return;
  clashes.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  const lines = [];
  for (const [name, locs] of clashes) {
    const where = [...new Set(locs.map((l) => loader.label(l)))].sort().join(", ");
    lines.push(`'${name}' is defined in ${where}`);
  }
  const first = clashes[0][0];
  const other = [...new Set(clashes[0][1].map((l) => loader.label(l)))].sort()[0];
  const otherMod = other.replace(/\.planes$/, "");
  throw new ModuleError(
    first,
    "two modules define the same name:\n  " + lines.join("\n  "),
    `rename one at the point of use, e.g. \`use ${otherMod} with ${first} as my ${first}\``,
  );
}

// parse(src, known)'s result depends on `known` too, so it can't be cached by
// source text alone the way renames_in/scan_names can — but for a fixed
// program, `known` (every name in the graph) is the same set on every tick,
// so a loader that opts in (an `astCache` Map — module_loader_browser.mjs's
// per-run cache, not module_loader_node.mjs's one-shot CLI use) gets the same
// win without ever risking a stale parse: a change to `src` or to which names
// are in scope is a different cache key, not a hit.
function parseCached(src, known, loader) {
  if (!loader.astCache) return parse(src, known);
  const key = src + " " + [...known].sort().join(",");
  let prog = loader.astCache.get(key);
  if (prog === undefined) {
    prog = parse(src, known);
    loader.astCache.set(key, prog);
  }
  return prog;
}

// Parse and hoist a resolved graph against `interp`, then execute the entry
// location's own top-level statements. The synchronous half of running a
// module graph — every location's source is already in hand by the time this
// runs, so nothing here awaits anything. Shared by the Node (run_file.mjs) and
// browser (browser_main.mjs) entry points, which differ only in how they
// resolved `graph` and `targetKey` in the first place.
export function hoistAndRun(interp, graph, targetKey, loader) {
  // `known` and `renames` both derive from effective_names, and computing it
  // twice (once per derivation) means re-tokenizing every file in the graph
  // twice, on every call — the difference between a one-off run and a
  // per-frame one. One pass instead.
  const entries = effective_names(graph, loader);
  const known = new Set();
  const renames = new Map();
  for (const [location, original, effective] of entries) {
    known.add(original);
    known.add(effective);
    if (original !== effective) {
      if (!renames.has(location)) renames.set(location, {});
      renames.get(location)[original] = effective;
    }
  }
  let entry = [];
  for (const [location, src] of graph) {
    const prog = parseCached(src, known, loader);
    interp.hoist(prog, interp.env, renames.get(location) ?? {});
    if (loader.key(location) === targetKey) {
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
