#!/usr/bin/env python3
"""Phase 3 (PROBE_SELFHOST.md) — string building at renderer scale.

render.py renders a whole file to canonical source: it builds one large
string. It does so with Python's str.join (interp.py:1090, 1105, 1140 are
all Python-side joins). Planes has no join — the builtins are count, lower,
upper, text, whole, ask, read, normalize, and none of them fold a list of
fragments into a string. The only string-building tool in the language is
`+`, and `+` on two strings copies both (interp.py apply_op: `return a + b`).
Building a string incrementally by repeated `+` is therefore O(n^2) in the
final length. This script measures how much that costs, and confirms there
is no O(n) alternative.

Nothing is changed. Timing host-side (time.perf_counter), Planes has no
wall-clock builtin. Method is this file; environment printed in the header.
"""
import platform
import sys
import time

sys.path.insert(0, ".")
from interp import Deriv, Interpreter, Traced  # noqa: E402

# Build a string of ~target bytes by appending a fixed chunk `reps` times,
# entirely in Planes: `acc = acc + chunk` inside a `for each` over a range
# list. Every iteration re-copies the growing `acc` — the quadratic.
BUILD_BY_PLUS = """
to build of chunks:
  acc = ""
  for each chunk in chunks:
    acc = acc + chunk
  give acc
"""

# The list-of-fragments alternative the phase asks about: accumulate with
# `plus` (cheap, measured in Phase 1), then try to collapse to one string.
# The collapse still has to use `+` in a loop — there is no join — so it is
# the SAME quadratic. This function is here to demonstrate that the absence
# of join is what forecloses the O(n) path, not a failure of `plus`.
ACC_THEN_COLLAPSE = """
to collect of chunks:
  frags = []
  for each chunk in chunks:
    frags = frags plus chunk
  give frags

to collapse of frags:
  acc = ""
  for each frag in frags:
    acc = acc + frag
  give acc
"""


def traced(v):
    return Traced(v, Deriv("literal", repr(v), v, []))


def chunks_for(target_bytes, chunk="x" * 16):
    n = max(1, target_bytes // len(chunk))
    return [chunk] * n, n * len(chunk)


def header():
    print("# Phase 3 — string building at renderer scale")
    print(f"# machine: {platform.platform()}")
    print(f"# python:  {platform.python_version()} ({sys.implementation.name})")
    print("# timer:   time.perf_counter, host-side")
    print()


def measure_build():
    print("## (1) building a string by repeated `+` in a Planes loop")
    print(f"{'target':>9}  {'actual_bytes':>12}  {'chunks':>7}  {'seconds':>10}  {'us/byte':>9}")
    interp = Interpreter()
    interp.run(BUILD_BY_PLUS)
    rows = {}
    for target in (1024, 10 * 1024, 100 * 1024, 200 * 1024, 400 * 1024):
        chunks, actual = chunks_for(target)
        arg = traced(chunks)
        start = time.perf_counter()
        interp.call("build", [arg], interp.env)
        elapsed = time.perf_counter() - start
        rows[actual] = elapsed
        us_byte = elapsed / actual * 1e6
        print(f"{target:>9}  {actual:>12}  {len(chunks):>7}  "
              f"{elapsed:>10.5f}  {us_byte:>9.4f}")
    print()
    return rows


def show_quadratic(rows):
    print("## (1b) is it quadratic? ratio of times vs ratio of sizes")
    sizes = sorted(rows)
    for a, b in zip(sizes, sizes[1:]):
        size_ratio = b / a
        time_ratio = rows[b] / rows[a] if rows[a] > 0 else float("inf")
        # For O(n^2), a size ratio of ~10 gives a time ratio of ~100.
        print(f"# size {a:>7} -> {b:>7} (x{size_ratio:.0f}):  "
              f"time x{time_ratio:.1f}   (linear would be x{size_ratio:.0f}, "
              f"quadratic x{size_ratio**2:.0f})")
    print()


def measure_collapse():
    print("## (2) accumulate-with-plus then collapse — no join means still quadratic")
    print(f"{'bytes':>8}  {'plus_collect_s':>14}  {'collapse_s':>11}")
    interp = Interpreter()
    interp.run(ACC_THEN_COLLAPSE)
    for target in (1024, 10 * 1024, 100 * 1024):
        chunks, actual = chunks_for(target)
        arg = traced(chunks)
        t0 = time.perf_counter()
        frags = interp.call("collect", [arg], interp.env)
        t1 = time.perf_counter()
        interp.call("collapse", [frags], interp.env)
        t2 = time.perf_counter()
        print(f"{actual:>8}  {t1-t0:>14.5f}  {t2-t1:>11.5f}")
    print("# `plus` collection is linear-ish; the collapse is the quadratic, "
          "and there is no builtin that would replace it.")
    print()


def project_render():
    print("## projection — rendering a lexer.planes-sized file")
    print("# grammar/lexer.planes is 564 lines; its canonical source is on the")
    print("# order of 15-20 KB of text. Locate that between the 10KB and 100KB")
    print("# rows above: the quadratic means it is closer to the 10KB cost than")
    print("# linear interpolation would suggest, but well under the 100KB cost.")
    print()


def main():
    header()
    rows = measure_build()
    show_quadratic(rows)
    measure_collapse()
    project_render()


if __name__ == "__main__":
    main()
