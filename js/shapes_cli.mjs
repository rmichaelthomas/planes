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
import { codePointLength } from "./planes_text.mjs";

// f"{s:<n}": pad with spaces on the right to n code points, no truncation —
// Python counts code points where `s.length` counts UTF-16 units.
function ljust(s, n) {
  const count = codePointLength(s);
  return count >= n ? s : s + " ".repeat(n - count);
}

// os.path.basename(p).replace(".planes", "") — but Python's str.replace removes
// every occurrence, so replaceAll.
function pkgName(p) {
  return path.basename(p).replaceAll(".planes", "");
}

// Python's `<` on str: code-point order, where JavaScript's sort compares
// UTF-16 units and puts U+FF41 after U+1F600.
function pyStrCmp(a, b) {
  if (a === b) return 0;
  const ca = [...a];
  const cb = [...b];
  const n = Math.min(ca.length, cb.length);
  for (let i = 0; i < n; i++) {
    const x = ca[i].codePointAt(0);
    const y = cb[i].codePointAt(0);
    if (x !== y) return x < y ? -1 : 1;
  }
  return ca.length - cb.length;
}

// fnmatch's translation for a POSIX file name: `*`, `?`, `[...]` / `[!...]`,
// case-sensitive, matched code point by code point.
function fnmatch(name, pat) {
  const match = (n, p) => {
    if (p === pat.length) return n === name.length;
    const c = pat[p];
    if (c === "*") {
      for (let k = n; ; k++) {
        if (match(k, p + 1)) return true;
        if (k === name.length) return false;
      }
    }
    if (c === "?") return n < name.length && match(n + 1, p + 1);
    if (c === "[") {
      let j = p + 1;
      if (j < pat.length && pat[j] === "!") j++;
      if (j < pat.length && pat[j] === "]") j++;
      while (j < pat.length && pat[j] !== "]") j++;
      if (j >= pat.length) return n < name.length && name[n] === "[" && match(n + 1, p + 1);
      if (n >= name.length) return false;
      let k = p + 1;
      const negate = pat[k] === "!";
      if (negate) k++;
      const content = pat.slice(k, j);
      const v = name[n].codePointAt(0);
      let hit = false;
      for (let i = 0; i < content.length; ) {
        if (i + 2 < content.length && content[i + 1] === "-") {
          if (content[i].codePointAt(0) <= v && v <= content[i + 2].codePointAt(0)) hit = true;
          i += 3;
        } else {
          if (content[i] === name[n]) hit = true;
          i += 1;
        }
      }
      return hit !== negate && match(n + 1, j + 1);
    }
    return n < name.length && name[n] === c && match(n + 1, p + 1);
  };
  return match(0, 0);
}

// glob.glob(pattern) for a pattern whose wildcards are in its last segment: a
// directory stands for its *.planes, a name starting with "." matches only a
// pattern that does, and the directory part is kept as written.
function globOne(pattern) {
  let p = pattern;
  if (fs.existsSync(p) && fs.statSync(p).isDirectory()) {
    p = p.endsWith("/") ? p + "*.planes" : p + "/*.planes";
  }
  const slash = p.lastIndexOf("/");
  const dir = slash < 0 ? "" : p.slice(0, slash);
  const base = [...p.slice(slash + 1)];
  if (!base.some((c) => c === "*" || c === "?" || c === "[")) {
    return fs.existsSync(p) ? [p] : [];
  }
  let entries;
  try {
    entries = fs.readdirSync(slash < 0 ? "." : dir || "/");
  } catch {
    return [];
  }
  return entries
    .filter((e) => (e[0] !== "." || base[0] === ".") && fnmatch([...e], base))
    .map((e) => (slash < 0 ? e : p.slice(0, slash + 1) + e));
}

function globAll(patterns) {
  const out = [];
  for (const pat of patterns) out.push(...globOne(pat).sort(pyStrCmp));
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
