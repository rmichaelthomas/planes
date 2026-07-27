#!/usr/bin/env node
// js/shapes_cli.mjs — the standalone effect-surface CLI, ported from
// shapes_cli.py's --index / --search / --diff (S6, A.5).
//
// A THIN shell over the already-ported engine: every line of analysis lives in
// shapes.mjs / shapes_node.mjs (analyseFile, the Surface queries, diff). This
// file only enumerates files, calls the engine, and formats the same text the
// Python CLI prints. If a command ever needed engine behaviour that did not
// exist, that would be a finding (A.5) — none did; --index, --search, and --diff
// each read only public Surface queries and diff, all present since S5.
//
// Node-only, per the module-split finding: file enumeration needs the
// filesystem, so this imports node APIs and shapes_node.mjs (which imports
// node:fs). It is a standalone entry point, never reached from the browser
// bundle (invariant 6).
//
// Usage:
//   node js/shapes_cli.mjs --index [dir-or-glob ...]
//   node js/shapes_cli.mjs --search <boundary> [dir-or-glob ...]
//   node js/shapes_cli.mjs --diff old.planes new.planes

import fs from "node:fs";
import path from "node:path";
import { loadGrammar } from "./loader_node.mjs";
import { diff } from "./shapes.mjs";
import { analyseFile } from "./shapes_node.mjs";
import { PlanesSyntaxError } from "./lexer.mjs";

// str.ljust(n) — Python's f"{s:<n}" / f"{s:n}" for strings: pad with spaces on
// the right, no truncation.
function ljust(s, n) {
  return s.length >= n ? s : s + " ".repeat(n - s.length);
}

// os.path.basename(p).replace(".planes", "") — but Python's str.replace removes
// every occurrence, so replaceAll.
function pkgName(p) {
  return path.basename(p).replaceAll(".planes", "");
}

// sorted(glob.glob(os.path.join(pat, "*.planes") if isdir(pat) else pat)) for
// one pattern. Handles a directory (→ its *.planes), a `*`-glob in the basename,
// or a plain path.
function globOne(pat) {
  let p = pat;
  if (fs.existsSync(p) && fs.statSync(p).isDirectory()) {
    p = path.join(p, "*.planes");
  }
  const dir = path.dirname(p);
  const base = path.basename(p);
  if (!base.includes("*")) return fs.existsSync(p) ? [p] : [];
  const re = new RegExp(
    "^" + base.split("*").map((s) => s.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*") + "$",
  );
  let entries;
  try {
    entries = fs.readdirSync(dir);
  } catch {
    return [];
  }
  return entries
    .filter((e) => re.test(e))
    .map((e) => (dir === "." ? e : path.join(dir, e)));
}

function globAll(patterns) {
  const out = [];
  for (const pat of patterns) out.push(...globOne(pat).sort());
  return out;
}

function surfaceKind(s) {
  return s.isLibrary() ? "library" : s.isPure() ? "pure" : "program";
}

async function main(args) {
  if (!args.length) {
    process.stderr.write("usage: shapes_cli --index|--search|--diff ...\n");
    return 2;
  }
  loadGrammar();
  const outLines = [];
  const emit = (s) => outLines.push(s);
  const flush = () => process.stdout.write(outLines.join("\n") + (outLines.length ? "\n" : ""));

  if (args[0] === "--index") {
    const paths = globAll(args.slice(1).length ? args.slice(1) : ["*.planes"]);
    if (!paths.length) {
      process.stderr.write("no .planes files found\n");
      return 1;
    }
    const rows = [];
    for (const p of paths) {
      try {
        rows.push([p, await analyseFile(p)]);
      } catch (e) {
        if (e instanceof PlanesSyntaxError) {
          process.stderr.write(`${p}: syntax error — ${e.message}\n`);
        } else throw e;
      }
    }
    emit(`${ljust("package", 16)} ${ljust("kind", 9)} boundaries`);
    emit("-".repeat(52));
    for (const [p, s] of rows) {
      const bnd = s.boundaries().join(", ") || "-";
      emit(`${ljust(pkgName(p), 16)} ${ljust(surfaceKind(s), 9)} ${bnd}`);
    }
    flush();
    return 0;
  }

  if (args[0] === "--search") {
    if (args.length < 2) {
      process.stderr.write("--search needs a boundary (network, file, console)\n");
      return 2;
    }
    const boundary = args[1];
    const paths = globAll(args.slice(2).length ? args.slice(2) : ["*.planes"]);
    let hits = 0;
    let skipped = 0;
    for (const p of paths) {
      let s;
      try {
        s = await analyseFile(p);
      } catch (e) {
        if (e instanceof PlanesSyntaxError) {
          process.stderr.write(`${p}: syntax error — ${e.message}\n`);
          skipped += 1;
          continue;
        }
        throw e;
      }
      if (s.touches(boundary)) {
        hits += 1;
        for (const eff of s.at(boundary)) emit(`${ljust(pkgName(p), 16)} ${eff}`);
      }
    }
    if (!hits) {
      const note = skipped
        ? ` (${skipped} file(s) could not be parsed and were not searched)`
        : "";
      emit(`nothing touches ${boundary} among the files searched${note}`);
    }
    flush();
    return 0;
  }

  if (args[0] === "--diff") {
    if (args.length < 3) {
      process.stderr.write("--diff needs two files\n");
      return 2;
    }
    const before = await analyseFile(args[1]);
    const after = await analyseFile(args[2]);
    const d = diff(before, after);
    emit(`${args[1]} -> ${args[2]}`);
    emit(d.render());
    flush();
    return d.isSignificant() ? 1 : 0;
  }

  process.stderr.write(`unknown command: ${args[0]}\n`);
  return 2;
}

process.exit(await main(process.argv.slice(2)));
