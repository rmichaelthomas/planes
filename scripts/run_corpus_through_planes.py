#!/usr/bin/env python3
"""Run whole corpus programs through the three Planes stages and check the
output against interp.py (S3c build 2, Phase 8).

The pipeline is entirely self-hosted: grammar/lexer.planes tokenizes,
grammar/parser.planes parses, and grammar/interp.planes runs the top-level
statements (execute-program), with the interpreted program's `show` delegating
to the host so its output lands where interp.py's own output does. For each
single-file corpus program, this runs it both ways and compares the show output.

A program is RUNNABLE when both sides succeed and their output matches. Anything
else is reported with the construct that blocks it: an effect or foreign call
(build 3), a module import (not resolved for a single file), the recursion
ceiling, or a genuine divergence. Programs interp.py itself cannot run as a bare
source (a module import, an effect with no host) are marked N/A -- they are not
pure build-1+2 programs to begin with.

Run:  .venv/bin/python3 scripts/run_corpus_through_planes.py
"""
import glob
import sys

sys.path.insert(0, ".")
from interp import Deriv, Interpreter, PlanesError, Traced  # noqa: E402
from lexer import PlanesSyntaxError  # noqa: E402

_shared = None


def _planes():
    global _shared
    if _shared is None:
        _shared = Interpreter()
        _shared.run_file("grammar/interp.planes")
    return _shared


def _t(v):
    return Traced(v, Deriv("literal", "<host value>", v, []))


def uses_import(src):
    return any(line.strip().startswith("use ") for line in src.splitlines())


def planes_run(src):
    """(output_lines, error_tag_or_None). error_tag names a status fail or a
    raised host error (e.g. recursion-too-deep)."""
    i = _planes()
    before = len(i.output)
    try:
        state = i.call("execute-program", [_t(src)], i.env).value
    except PlanesError as e:
        return list(i.output[before:]), e.tag
    except RecursionError:
        return list(i.output[before:]), "recursion-too-deep"
    tag = None
    if state["status"] == "fail":
        tag = state["error"]["tag"]
    return list(i.output[before:]), tag


def interp_run(src):
    """(output, tag). tag is None on success, a runtime PlanesError tag on a
    program failure, or the sentinel 'PARSE' when the source does not parse
    (a negative parser fixture, not a runnable program)."""
    itp = Interpreter()
    try:
        out = itp.run(src)
        return list(out), None
    except PlanesError as e:
        return list(itp.output), e.tag
    except RecursionError:
        return list(itp.output), "recursion-too-deep"
    except PlanesSyntaxError:
        return [], "PARSE"


# A foreign call whose target the host cannot load: interp.py raises
# foreign-not-found, interp.planes raises foreign-needs-host (it has no dynamic
# host.resolve at all). Both are the same outcome -- a refusal to run a foreign
# the host cannot provide -- so a program that hits this on both sides agrees.
FOREIGN_REFUSALS = {"foreign-not-found", "foreign-needs-host"}


def classify(path):
    src = open(path).read()
    if uses_import(src):
        return "N/A", "module import (use) -- needs module resolution"
    py_out, py_tag = interp_run(src)
    if py_tag == "PARSE":
        # interp.py does not parse it -- a negative parser fixture (ambiguity,
        # no index syntax), not a build-1+2 program to run.
        return "N/A", "negative parser fixture (does not parse)"
    pl_out, pl_tag = planes_run(src)
    # A program that deliberately fails is runnable when both sides fail the
    # same way with the same output up to the failure.
    if pl_out == py_out and pl_tag == py_tag:
        return "RUNNABLE", ("" if pl_tag is None else f"both fail: {pl_tag}")
    # Both sides refuse a foreign whose target the host cannot load, with the
    # same output up to the refusal -- agreement (build 3 closed the boundary:
    # arity, declared effects, and refusal on an unresolvable target).
    if (pl_tag in FOREIGN_REFUSALS and py_tag in FOREIGN_REFUSALS
            and pl_out == py_out):
        return "RUNNABLE", "both refuse the unloadable foreign target"
    # interp.py runs a foreign for real (its host resolves the target); the
    # Planes side cannot, because interp.planes has no dynamic host.resolve.
    # This is the one remaining build-3 boundary, and it is the second host's
    # single non-effect method (host.resolve / importlib), named precisely.
    if pl_tag == "foreign-needs-host" and py_tag is None:
        return "BLOCKED", ("arbitrary host-function resolution "
                           "(dynamic host.resolve -- the second host)")
    if pl_tag == "recursion-too-deep" and py_tag != "recursion-too-deep":
        return "BLOCKED", "recursion-too-deep (interpreted recursion is shallower)"
    return "DIVERGENCE", (
        f"planes=({len(pl_out)} lines, {pl_tag}) "
        f"python=({len(py_out)} lines, {py_tag})")


def main():
    files = sorted(
        f for f in glob.glob("**/*.planes", recursive=True)
        if not f.startswith("grammar/")
        and ".venv" not in f
    )
    buckets = {}
    for f in files:
        try:
            status, detail = classify(f)
        except Exception as e:  # noqa: BLE001
            status, detail = "ERROR", f"{type(e).__name__}: {e}"
        buckets.setdefault(status, []).append((f, detail))

    order = ["RUNNABLE", "BLOCKED", "DIVERGENCE", "ERROR", "N/A"]
    for status in order:
        rows = buckets.get(status, [])
        if not rows:
            continue
        print(f"\n=== {status} ({len(rows)}) ===")
        for f, detail in rows:
            print(f"  {f}" + (f"   [{detail}]" if detail else ""))
    runnable = len(buckets.get("RUNNABLE", []))
    considered = runnable + len(buckets.get("BLOCKED", [])) \
        + len(buckets.get("DIVERGENCE", [])) + len(buckets.get("ERROR", []))
    print(f"\nRUNNABLE {runnable} / {considered} build-1+2 programs "
          f"({len(files)} corpus files, {len(buckets.get('N/A', []))} N/A)")


if __name__ == "__main__":
    main()
