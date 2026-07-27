#!/usr/bin/env python3
"""Run every corpus program through the SELF-HOSTED stack and check it against
the reference (C1, §6).

`scripts/run_corpus_through_planes.py` measures a different thing: it drives
whole programs through interp.planes in "real" mode and marks anything with a
`use` line N/A, because module resolution is out of scope there. Twelve corpus
programs use `file` and four use `http`, so that harness never sees the half of
the corpus that touches the world — which is the half the host boundary is
about.

This one runs the corpus in "inert" mode, where an effect is data: the
configuration supplies the files, responses, clock, randoms, envs, and foreign
results, and nothing reaches a filesystem, a network, or a clock. The oracle is
interp.py under a `TestHost`, which is the same arrangement on the reference
side — a host with the outside world replaced. Both sides are compared on their
whole output (show lines in order) and on the terminal error tag, so a program
that deliberately fails counts as agreeing when it fails the same way.

INERT_CONFIG is the per-program configuration. It exists for one reason: a pure
foreign has no result in inert mode unless the run supplies one, and since C1 a
missing one FAILS naming the stub rather than returning `nothing`. The supplied
result is computed through the host's own function, not written out by hand, so
the stub cannot drift from what the reference actually returns.

Run:  .venv/bin/python3 scripts/run_corpus_selfhosted.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from host import PythonHost, TestHost  # noqa: E402
from interp import Deriv, Interpreter, PlanesError, Traced  # noqa: E402
from lexer import PlanesSyntaxError  # noqa: E402
from planes_num import Number  # noqa: E402

INTERP_PLANES = "grammar/interp.planes"

_shared = None


def _planes():
    global _shared
    if _shared is None:
        _shared = Interpreter()
        _shared.run_file(INTERP_PLANES)
    return _shared


def _t(v):
    return Traced(v, Deriv("literal", "<host value>", v))


def _num(n):
    return {"kind": "number", "value": Number.of(n), "approx": None, "deriv": None}


def _lst(items):
    return {"kind": "list", "items": items, "deriv": None}


# corpus/fastest-responses.planes declares `foreign ranked ... from
# "builtins.sorted" doing nothing` and calls it on its own `times-ms`. The stub
# is that call, made through the host: the reference resolves the same target
# and runs the same function, so the supplied result is the host's answer rather
# than a constant that could drift from it.
_TIMES_MS = [214, 87, 402, 63, 155, 91, 300]
_RANKED = PythonHost().resolve("builtins.sorted")(_TIMES_MS)

INERT_CONFIG = {
    "corpus/fastest-responses.planes": {
        "foreigns": [{"name": "ranked",
                      "value": _lst([_num(n) for n in _RANKED])}],
    },
}


def inert_io(**cfg):
    d = {"mode": "inert", "log": [], "output": [], "annotations": [],
         "modules": [], "clock": 0, "randoms": [], "files": [],
         "responses": [], "envs": [], "foreigns": []}
    d.update(cfg)
    return d


def _io_of(state):
    for b in state["env"]:
        if b["name"] == "__io__":
            return b["value"]
    raise AssertionError("no __io__ binding in program env")


def planes_run(src, cfg):
    """(output, tag) from an inert interp.planes run. `tag` is None on a clean
    completion, the terminal fail tag otherwise."""
    i = _planes()
    try:
        state = i.call("execute-program-with",
                       [_t(src), _t(inert_io(**cfg))], i.env).value
    except PlanesError as e:
        return [], e.tag
    except RecursionError:
        return [], "recursion-too-deep"
    io = _io_of(state)
    tag = None
    if state["status"] == "fail":
        err = state["error"] or {}
        tag = err.get("tag")
    return list(io["output"]), tag


def reference_run(src):
    """The same, from interp.py under a TestHost — a host with the outside world
    replaced, which is the reference's own inert mode."""
    host = TestHost()
    itp = Interpreter(host=host)
    try:
        itp.run(src)
    except PlanesError as e:
        return list(itp.output), e.tag
    except RecursionError:
        return list(itp.output), "recursion-too-deep"
    except PlanesSyntaxError:
        return [], "PARSE"
    return list(itp.output), None


def classify(path):
    src = open(path, encoding="utf-8").read()
    cfg = INERT_CONFIG.get(path.replace(os.sep, "/"), {})
    ref_out, ref_tag = reference_run(src)
    pl_out, pl_tag = planes_run(src, cfg)
    if (pl_out, pl_tag) == (ref_out, ref_tag):
        return "RUNNABLE", ("" if pl_tag is None else f"both fail: {pl_tag}")
    if pl_tag is not None and ref_tag is None:
        return "BLOCKED", f"interp.planes fails {pl_tag}; the reference runs"
    i = next((k for k in range(min(len(pl_out), len(ref_out)))
              if pl_out[k] != ref_out[k]), None)
    where = (f"; first diff at line {i}: planes={pl_out[i]!r} "
             f"reference={ref_out[i]!r}" if i is not None else "")
    return "DIVERGENCE", (f"planes=({len(pl_out)} lines, {pl_tag}) "
                          f"reference=({len(ref_out)} lines, {ref_tag}){where}")


def main():
    files = sorted(glob.glob("corpus/**/*.planes", recursive=True))
    buckets = {}
    for f in files:
        try:
            status, detail = classify(f)
        except Exception as e:                             # noqa: BLE001
            status, detail = "ERROR", f"{type(e).__name__}: {e}"
        buckets.setdefault(status, []).append((f, detail))
    for status in ("RUNNABLE", "BLOCKED", "DIVERGENCE", "ERROR"):
        rows = buckets.get(status, [])
        if not rows:
            continue
        print(f"\n=== {status} ({len(rows)}) ===")
        for f, detail in rows:
            print(f"  {f}" + (f"   [{detail}]" if detail else ""))
    runnable = len(buckets.get("RUNNABLE", []))
    print(f"\nSELF-HOSTED RUNNABLE {runnable} / {len(files)} corpus programs")
    return 0 if runnable == len(files) else 1


if __name__ == "__main__":
    sys.exit(main())
