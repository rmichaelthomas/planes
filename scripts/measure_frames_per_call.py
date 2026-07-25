#!/usr/bin/env python3
"""Measure Python frames per Planes-level call, and the recursion ceiling.

S2 Phase 1 reduces frames-per-call in interp.py (unbound v3.0 §42 — an
optimization below the visible line; the ~140 ceiling is an implementation
cost, not a language limit). This script measures the two numbers that change
— frames per Planes call and the ceiling — so the reduction is reported, not
claimed. It changes nothing; it wraps Interpreter.invoke from outside to
observe the live stack.

Method: run a self-calling countdown. `invoke` is entered once per Planes-level
call, so the difference in Python stack depth between two consecutive `invoke`
entries is exactly the frames spent per Planes call. The ceiling is found by
binary search on the depth at which `recursion-too-deep` first fires.
"""
import sys

sys.path.insert(0, ".")
from interp import Interpreter, PlanesError  # noqa: E402

# Two recursion shapes. The `if` countdown is the benchmark the sweep used
# (comparable before/after). The `when` countdown is the shape a self-hosted
# `eval` actually takes — a nested when/else dispatch ladder — and is the
# number that matters for interp.planes.
COUNTDOWN = """
to countdown of n:
  if n <= 0:
    give 0
  else:
    give countdown of (n - 1)

answer = countdown of DEPTH
"""

WHEN_COUNTDOWN = """
to countdown of node:
  result = 0
  when node is { n }:
    if n <= 0:
      result = 0
    else:
      result = countdown of { n: n - 1 }
  give result

answer = countdown of { n: DEPTH }
"""


def stack_depth():
    """Number of Python frames currently on the stack."""
    d = 0
    f = sys._getframe()
    while f is not None:
        d += 1
        f = f.f_back
    return d


def measure_frames_per_call(src):
    # `call` is entered once per Planes-level call (invoke was folded into it
    # in S2 Phase 1). The wrapper itself adds exactly one frame per call, so
    # the true frames-per-call is the consecutive diff minus one.
    depths = []
    orig = Interpreter.call

    def traced_call(self, name, args, env):
        depths.append(stack_depth())
        return orig(self, name, args, env)

    Interpreter.call = traced_call
    try:
        Interpreter().run(src.replace("DEPTH", "20"))
    finally:
        Interpreter.call = orig

    # consecutive differences settle to the steady-state frames-per-call;
    # subtract 1 for the traced_call wrapper frame present at every level.
    diffs = [b - a for a, b in zip(depths, depths[1:])]
    raw = diffs[len(diffs) // 2] if diffs else 0
    return raw - 1


def succeeds_at(src, depth):
    try:
        Interpreter().run(src.replace("DEPTH", str(depth)))
        return True
    except PlanesError as e:
        if e.tag == "recursion-too-deep":
            return False
        raise
    except RecursionError:
        return False


def measure_ceiling(src):
    lo, hi = 1, 4000
    while succeeds_at(src, hi):
        hi *= 2
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if succeeds_at(src, mid):
            lo = mid
        else:
            hi = mid
    return lo


def main():
    print("# Frames per Planes call, and the recursion ceiling")
    print(f"# python: {sys.version.split()[0]}, "
          f"sys.recursionlimit = {sys.getrecursionlimit()}")
    for label, src in (("if-based (sweep benchmark)", COUNTDOWN),
                       ("when-based (interp.planes shape)", WHEN_COUNTDOWN)):
        frames = measure_frames_per_call(src)
        ceiling = measure_ceiling(src)
        print(f"{label}: FRAMES_PER_PLANES_CALL={frames}  "
              f"RECURSION_CEILING={ceiling}")


if __name__ == "__main__":
    main()
