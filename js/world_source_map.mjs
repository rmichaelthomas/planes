// js/world_source_map.mjs — world-record -> Planes-source-path mapping.
//
// Horizon Phase 0 Build 2, Phase 2. Mirrors world_source_map.py field for
// field, refusal tag for refusal tag. Extends interp.mjs's existing
// attribution discipline (Function.file / trace_line) from "which line
// printed this text" to "which line produced this world record" — the same
// repo-relative "<file>:<line>" path format, built and resolved by the same
// two functions on both sides.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export class SourceMapError extends Error {
  constructor(tag, detail, fix) {
    super(`${tag}: ${detail}`);
    this.tag = tag;
    this.detail = detail;
    this.fix = fix;
  }
}

// The `sourceMapTarget` string for a world record produced while running
// `entryFile` (an absolute path — Interpreter.entryFile) at `line`
// (Interpreter.trace_line's own return value). Repo-relative, so the path
// resolves the same way regardless of which machine ran the interpreter.
// Returns null when there is no real entry file to point at.
export function formatSourceMapPath(entryFile, line) {
  if (entryFile === null || entryFile === undefined) return null;
  const rel = path.relative(REPO_ROOT, path.resolve(entryFile));
  return `${rel}:${line}`;
}

// Round-trip a sourceMapTarget back to the exact Planes source line it names
// (§7.3's round-trip guarantee). Returns the line's text (no trailing
// newline). Throws SourceMapError — never returns nothing — when the path is
// malformed, names a file outside the repo, or names a line the file does
// not have.
export function resolveSourceMapPath(targetPath) {
  if (typeof targetPath !== "string" || !targetPath.includes(":")) {
    throw new SourceMapError(
      "malformed-source-map-path",
      `${JSON.stringify(targetPath)} is not a '<file>:<line>' source-map path`,
      "build the path with world_source_map.formatSourceMapPath, which always "
        + "produces '<repo-relative-file>:<line>'",
    );
  }
  const sep = targetPath.lastIndexOf(":");
  const rel = targetPath.slice(0, sep);
  const lineText = targetPath.slice(sep + 1);
  const lineNum = Number(lineText);
  if (!Number.isInteger(lineNum) || lineNum < 1) {
    throw new SourceMapError(
      "malformed-source-map-path",
      `${JSON.stringify(targetPath)} does not end in a numeric line number`,
      "build the path with world_source_map.formatSourceMapPath",
    );
  }
  const full = path.normalize(path.join(REPO_ROOT, rel));
  const relFromRoot = path.relative(REPO_ROOT, full);
  if (relFromRoot.startsWith("..") || path.isAbsolute(relFromRoot)) {
    throw new SourceMapError(
      "unresolvable-source-map-path",
      `${JSON.stringify(targetPath)} resolves outside the repo`,
      "a sourceMapTarget must name a file inside the repo the interpreter ran in",
    );
  }
  if (!fs.existsSync(full) || !fs.statSync(full).isFile()) {
    throw new SourceMapError(
      "unresolvable-source-map-path",
      `${JSON.stringify(targetPath)} names a file that does not exist in the repo: ${rel}`,
      "the sourceMapTarget must point at a Planes source file that is actually in the repo",
    );
  }
  const lines = fs.readFileSync(full, "utf-8").split("\n");
  // A trailing newline produces one empty trailing element split() would
  // otherwise count as an extra line; drop it so the line count agrees with
  // readlines()'s on the Python side for any file that ends in "\n".
  if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
  if (lineNum > lines.length) {
    throw new SourceMapError(
      "unresolvable-source-map-path",
      `${JSON.stringify(targetPath)} names line ${lineNum}, but ${rel} has ${lines.length} lines`,
      "the sourceMapTarget must point at a line that exists in the file",
    );
  }
  return lines[lineNum - 1];
}
