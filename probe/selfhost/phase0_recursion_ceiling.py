#!/usr/bin/env python3
"""Cross-cutting measurement — the recursion ceiling, measured not carried.

Every phase touches recursion: it is Planes' only "repeat until" (Phase 4),
its only way to walk a nested AST (Phase 2), and the way a self-hosted `eval`
would call itself on sub-expressions (Phase 5). The ~140 ceiling is carried
from PROBE_PARSER.md / #14. Because a recursive-descent interpreter written in
Planes lives or dies on this number, this re-measures it directly rather than
trusting the carried figure — the same discipline Phase 4 step 1 applied to
the absence of `while`.

Method: a self-calling countdown `to countdown of n: if n <= 0 give 0 else
give countdown of (n - 1)`, run at increasing depths until the interpreter
raises `recursion-too-deep`. The largest depth that still succeeds is the
ceiling. Nothing is changed.
"""
import sys

sys.path.insert(0, ".")
from interp import Interpreter, PlanesError  # noqa: E402

COUNTDOWN = """
to countdown of n:
  if n <= 0:
    give 0
  else:
    give countdown of (n - 1)

answer = countdown of DEPTH
"""


def succeeds_at(depth):
    src = COUNTDOWN.replace("DEPTH", str(depth))
    try:
        Interpreter().run(src)
        return True
    except PlanesError as e:
        if e.tag == "recursion-too-deep":
            return False
        raise
    except RecursionError:
        return False


def main():
    print("# Recursion ceiling — measured directly")
    print(f"# python: {sys.version.split()[0]}, default sys.recursionlimit = "
          f"{sys.getrecursionlimit()}")
    # Binary search for the largest depth that still succeeds.
    lo, hi = 0, 4000
    # find an hi that fails
    while succeeds_at(hi):
        hi *= 2
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if succeeds_at(mid):
            lo = mid
        else:
            hi = mid
    print(f"# largest self-call depth that succeeds: {lo}")
    print(f"# first depth that raises recursion-too-deep: {hi}")
    print()
    print("# what this means for a self-hosted interpreter:")
    print("# a Planes `eval` calling itself on sub-expressions spends one")
    print("# Planes-level frame per AST level PLUS the frames for statement")
    print("# and call nesting, so the usable AST/round depth is well under")
    print(f"# {lo}, not equal to it.")


if __name__ == "__main__":
    main()
