#!/usr/bin/env python3
"""Phase 1 (PROBE_SELFHOST.md) — environment lookup at interpreter scale.

An interpreter resolves a name on every reference. interp.py does it with a
mutable Python dict chain (Env.get walks self.vars then self.parent). Planes
has no mutable dict and no computed-key record access (a field name must be a
literal known when the source is written — demo/association.planes's own
comment), so interp.planes cannot use a record as its environment. Its only
option is the association idiom: a list of {name, value} records, scanned by
`for each ... where`. This script measures what that costs at interpreter
scale.

Nothing is changed. Timing is host-side (time.perf_counter around
interp.call), exactly as scripts/measure_association_idiom.py does it, because
Planes has no wall-clock builtin. Every number printed is a measurement; the
method is this file.

Environment: run `python3 probe/selfhost/phase1_env_lookup.py` from the repo
root. Reported machine + Python version are printed in the header so a rerun
is comparable.
"""
import platform
import statistics
import sys
import time

sys.path.insert(0, ".")
from interp import Deriv, Interpreter, Traced  # noqa: E402

# --- the idioms under test, verbatim Planes -------------------------------

# (1) flat association lookup: demo/association.planes's own `lookup`, the
# idiom Ruling 1 blessed. Note there is no early exit — `for each` visits
# every entry and the last match wins, so cost is O(n) on a hit OR a miss.
FLAT_LOOKUP = """
to lookup of table, key:
  result = nothing
  for each entry in table where entry.name == key:
    result = entry.value
  give result
"""

# (2) nested-scope lookup: the environment as a list of frames (innermost
# last, so the last match shadows). A genuine miss — or a hit in the
# outermost frame — walks every frame and every entry, which is the
# "a miss walks outward" worst case the phase asks for.
CHAIN_LOOKUP = """
to lookup-chain of frames, key:
  found = nothing
  for each frame in frames:
    for each entry in frame where entry.name == key:
      found = entry.value
  give found
"""

# (3) rebinding: the two immutable-copy operations an interpreter leans on.
# `plus` appends a fresh binding to an association list; `with` produces an
# updated record. Both copy, so both are O(size).
REBIND_PLUS = """
to add-binding of table, entry:
  give table plus entry
"""
REBIND_WITH = """
to rebind of env, v:
  give env with slot0: v
"""


def traced(v):
    return Traced(v, Deriv("literal", repr(v), v, []))


def build_table(n):
    return [{"name": f"func-{i}", "value": i} for i in range(n)]


def build_frames(nframes, per_frame):
    # innermost last; the target name lives only in the outermost (first)
    # frame, so every lookup walks the whole chain.
    frames = []
    for f in range(nframes):
        frames.append([{"name": f"f{f}-v{i}", "value": i} for i in range(per_frame)])
    return frames


def time_calls(interp, fn_name, arg_builder, reps):
    """Median seconds/call over `reps` calls, plus the raw list for spread."""
    samples = []
    for i in range(reps):
        args = arg_builder(i)
        start = time.perf_counter()
        interp.call(fn_name, args, interp.env)
        samples.append(time.perf_counter() - start)
    return statistics.median(samples), samples


def header():
    print("# Phase 1 — environment lookup at interpreter scale")
    print(f"# machine: {platform.platform()}")
    print(f"# python:  {platform.python_version()} ({sys.implementation.name})")
    print("# timer:   time.perf_counter, host-side, median of N calls")
    print()


def measure_flat():
    print("## (1) flat association lookup — seconds per lookup")
    print(f"{'entries':>8}  {'reps':>5}  {'median_s/lookup':>16}  {'min_s':>10}  {'max_s':>10}")
    interp = Interpreter()
    interp.run(FLAT_LOOKUP)
    results = {}
    for n in (10, 50, 200, 500):
        table = traced(build_table(n))
        # realistic mix: half hits spread across the table (incl. the last,
        # worst-case entry), half misses. A miss is full-scan by construction.
        def arg_builder(i, table=table, n=n):
            if i % 2 == 0:
                return [table, traced(f"func-{i % n}")]
            return [table, traced("not-a-real-function")]
        reps = 400
        med, samples = time_calls(interp, "lookup", arg_builder, reps)
        results[n] = med
        print(f"{n:>8}  {reps:>5}  {med:>16.8f}  {min(samples):>10.8f}  {max(samples):>10.8f}")
    print()
    return results


def measure_chain():
    print("## (2) nested-scope lookup — a miss walks outward through every frame")
    print(f"{'frames':>7}  {'per_frame':>9}  {'total':>6}  {'reps':>5}  {'median_s/lookup':>16}")
    interp = Interpreter()
    interp.run(CHAIN_LOOKUP)
    results = {}
    per_frame = 20  # a plausible per-scope binding count for interp.planes
    for nframes in (3, 5, 10):
        frames = traced(build_frames(nframes, per_frame))
        def arg_builder(i, frames=frames):
            # always a miss => full outward walk (the worst case asked for)
            return [frames, traced("not-bound-anywhere")]
        reps = 400
        med, _ = time_calls(interp, "lookup-chain", arg_builder, reps)
        results[nframes] = med
        print(f"{nframes:>7}  {per_frame:>9}  {nframes*per_frame:>6}  {reps:>5}  {med:>16.8f}")
    print()
    return results


def measure_rebind():
    print("## (3) rebinding cost — immutable copy operations at env scale")
    print(f"{'op':>6}  {'size':>6}  {'reps':>5}  {'median_s/op':>14}")
    ip = Interpreter()
    ip.run(REBIND_PLUS)
    iw = Interpreter()
    iw.run(REBIND_WITH)
    results = {}
    for n in (10, 50, 200, 500):
        table = traced(build_table(n))
        entry = traced({"name": "new", "value": n})
        def plus_args(i, table=table, entry=entry):
            return [table, entry]
        med_plus, _ = time_calls(ip, "add-binding", plus_args, 400)
        results[("plus", n)] = med_plus
        print(f"{'plus':>6}  {n:>6}  {400:>5}  {med_plus:>14.8f}")
    # `with` needs a record of N fields to be a fair scale comparison.
    for n in (10, 50, 200, 500):
        rec = traced({f"slot{i}": i for i in range(n)})
        def with_args(i, rec=rec):
            return [rec, traced(i)]
        med_with, _ = time_calls(iw, "rebind", with_args, 400)
        results[("with", n)] = med_with
        print(f"{'with':>6}  {n:>6}  {400:>5}  {med_with:>14.8f}")
    print()
    return results


def project_workload(flat_results):
    """(2 in the phase spec) Cost interpretation of a lexer.planes-sized
    program. grammar/lexer.planes is 564 lines; REPORT_STRING_ESCAPES.md
    carries the figure that it self-tokenizes to 3835 tokens. A tree-walking
    interpreter resolves a name on every Var node it evaluates. We do not
    have the exact Var count without an AST pass, so we bracket it: a token
    stream of ~3835 tokens contains on the order of one name reference per
    handful of tokens. We report the cost at a spread of reference counts so
    the reader can locate the real program between the brackets, rather than
    fabricate a single Var count and call it measured.
    """
    print("## projection — interpreting a lexer.planes-sized program")
    print("# 564 lines; ~3835 tokens (REPORT_STRING_ESCAPES.md, carried not re-measured).")
    print("# Each Var evaluation = one env lookup. Cost = lookups * seconds/lookup.")
    print(f"{'env_entries':>11}  {'500_refs':>10}  {'2000_refs':>10}  {'8000_refs':>10}")
    for n in (10, 50, 200, 500):
        per = flat_results[n]
        row = [f"{per*r:>10.4f}" for r in (500, 2000, 8000)]
        print(f"{n:>11}  {row[0]}  {row[1]}  {row[2]}")
    print("# columns are total seconds of pure name-resolution, at that env size.")
    print()


def main():
    header()
    flat = measure_flat()
    measure_chain()
    measure_rebind()
    project_workload(flat)


if __name__ == "__main__":
    main()
