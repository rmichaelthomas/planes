"""world_source_map.py — world-record -> Planes-source-path mapping.

Horizon Phase 0 Build 2, Phase 2. Extends `interp.py`'s existing attribution
discipline — `Function.file` names the file a definition lives in,
`Interpreter.trace_line` resolves an output line back to the entry-file
source line that produced it — from "which line printed this text" to
"which line produced this world record". It does not invent a parallel
mechanism: the line number a `sourceMapTarget` carries is the exact same
number `trace_line` already computes for `self.trace`.

Two functions, one path format (`<repo-relative-file>:<line>`), so the
builder and the resolver agree on it without a third piece of code holding
them together:

  format_source_map_path(entry_file, line)  — build one, at emission time
  resolve_source_map_path(path)             — round-trip it back to real
                                               source text (§7.3), or refuse

A path that resolves to nothing is a failure, not a warning: `world-v1`'s
own `unknownRecords` note draws that same line between "absent" (warn) and
"present but wrong" (refuse), and a dangling source map is the second kind.
"""
import os

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


class SourceMapError(Exception):
    """A refusal naming the rule it broke — the same three-part tag/detail/fix
    shape `world_ir.WorldIRError` carries, kept as its own class for the same
    reason: this module has no import dependency on the language
    implementation it maps paths for."""

    def __init__(self, tag, detail, fix):
        self.tag = tag
        self.detail = detail
        self.fix = fix
        super().__init__(f"{tag}: {detail}")


def format_source_map_path(entry_file, line):
    """The `sourceMapTarget` string for a world record produced while running
    `entry_file` (an absolute path — `Interpreter.entry_file`) at the given
    entry-file `line` (`Interpreter.trace_line`'s own return value).

    Repo-relative, not absolute: the path must resolve the same way
    regardless of which machine or working directory ran the interpreter,
    the same portability `trace_line`'s own reports already assume — a
    reader following a source map into the repo needs a path INTO the repo,
    not into whatever absolute prefix happened to hold the checkout.

    Returns None when there is no real entry file to point at (a program run
    through `Interpreter.run(src)` with no path) — the caller's job is to
    leave `sourceMapTarget` as whatever the program supplied rather than
    inventing a path with nothing real behind it.
    """
    if entry_file is None:
        return None
    rel = os.path.relpath(os.path.abspath(entry_file), REPO_ROOT)
    return f"{rel}:{line}"


def resolve_source_map_path(path):
    """Round-trip a `sourceMapTarget` back to the exact Planes source line it
    names (§7.3's round-trip guarantee). Returns the line's text (no
    trailing newline). Raises `SourceMapError` — never returns nothing —
    when the path is malformed, names a file outside the repo, or names a
    line the file does not have.
    """
    if not isinstance(path, str) or ":" not in path:
        raise SourceMapError(
            "malformed-source-map-path",
            f"{path!r} is not a '<file>:<line>' source-map path",
            "build the path with world_source_map.format_source_map_path, "
            "which always produces '<repo-relative-file>:<line>'")
    rel, _, line_text = path.rpartition(":")
    try:
        line_num = int(line_text)
    except ValueError:
        raise SourceMapError(
            "malformed-source-map-path",
            f"{path!r} does not end in a numeric line number",
            "build the path with world_source_map.format_source_map_path")
    if line_num < 1:
        raise SourceMapError(
            "malformed-source-map-path",
            f"{path!r} names line {line_num}, which is not a valid 1-indexed line",
            "build the path with world_source_map.format_source_map_path")
    full = os.path.normpath(os.path.join(REPO_ROOT, rel))
    if os.path.commonpath([REPO_ROOT, full]) != REPO_ROOT:
        raise SourceMapError(
            "unresolvable-source-map-path",
            f"{path!r} resolves outside the repo",
            "a sourceMapTarget must name a file inside the repo the interpreter ran in")
    if not os.path.isfile(full):
        raise SourceMapError(
            "unresolvable-source-map-path",
            f"{path!r} names a file that does not exist in the repo: {rel}",
            "the sourceMapTarget must point at a Planes source file that is actually in the repo")
    with open(full, encoding="utf-8") as f:
        lines = f.readlines()
    if line_num > len(lines):
        raise SourceMapError(
            "unresolvable-source-map-path",
            f"{path!r} names line {line_num}, but {rel} has {len(lines)} lines",
            "the sourceMapTarget must point at a line that exists in the file")
    return lines[line_num - 1].rstrip("\n")
