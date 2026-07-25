#!/usr/bin/env python3
"""Phase 6: measure the association idiom (Ruling 1, fix/recursion-leak-
and-fifth-amber-site) against a known_funcs-sized table -- tens to low
hundreds of entries, PROBE_PARSER.md capability 7's own estimate of what
a real program's known_funcs table would hold. REPORT_RECURSION_AND_
AMBER_SITE5.md left this unmeasured; this build closes that item.

Uses demo/association.planes's own idiom verbatim (a list of {name,
value} records, `for each entry in table where entry.name == key` scan)
at three table sizes, timing from the host side since Planes has no
wall-clock builtin of its own. Changes nothing; only measures.
"""
import sys
import time

sys.path.insert(0, ".")
from interp import Deriv, Interpreter, Traced  # noqa: E402

LOOKUP_SRC = """
to lookup of table, key:
  result = nothing
  for each entry in table where entry.name == key:
    result = entry.value
  give result
"""


def traced(v):
    return Traced(v, Deriv("literal", repr(v), v, []))


def build_table(n):
    return [{"name": f"func-{i}", "value": i} for i in range(n)]


def measure(n, lookups):
    interp = Interpreter()
    interp.run(LOOKUP_SRC)
    table = traced(build_table(n))
    # A realistic lookup mix: half hits spread across the table
    # (including the worst case, the last entry), half misses.
    keys = []
    for i in range(lookups):
        if i % 2 == 0:
            keys.append(f"func-{i % n}")
        else:
            keys.append("not-a-real-function")
    start = time.perf_counter()
    for k in keys:
        interp.call("lookup", [table, traced(k)], interp.env)
    elapsed = time.perf_counter() - start
    return elapsed


def main():
    print("table_size  lookups  total_seconds  seconds_per_lookup", file=sys.stderr)
    for n in (25, 100, 250):
        lookups = 200
        elapsed = measure(n, lookups)
        print(f"{n:10}  {lookups:7}  {elapsed:13.4f}  {elapsed / lookups:.6f}")


if __name__ == "__main__":
    main()
