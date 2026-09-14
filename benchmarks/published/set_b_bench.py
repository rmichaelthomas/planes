#!/usr/bin/env python3
"""set_b_bench.py -- H7 Set B: effect-surface time over the 51-program corpus.

docs/planes_sprint_2026_09_hardening.md, decision #21 (H7) asks for the
time `python3 shapes_cli.py <file> --json` and `node js/cli.mjs shapes
<file>` take across every corpus program (per-file median of 5, and the
total), process startup reported separately, plus the fraction of corpus
programs whose surface crosses a foreign boundary.

DEFINITION OF "CROSSES A FOREIGN BOUNDARY": a program whose `--json` surface
has at least one effect with `"declared": true`. `declared` marks an effect
that came from a `foreign ... doing ...` line -- a claim the program's
author wrote, not one the analyser derived from a builtin it understands
(shapes.py's own effect construction sets it exactly there; the boundary
named "foreign" in BOUNDARIES is one case of this, but `declared` also
catches a `foreign` function whose `doing` clause names an ordinary
boundary such as `ambient` -- e.g. corpus/env-config.planes's `os.getcwd`
read, which is `declared: true` at the `ambient` boundary, not `foreign`).
This is the precise, JSON-derived definition; the corpus also has a raw
count of programs with a literal `foreign` keyword line, reported alongside
for comparison.

Usage:  python3 benchmarks/published/set_b_bench.py [--runs N] [--out PATH]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORPUS_GLOB = os.path.join(REPO, "corpus", "*.planes")

DEFAULT_RUNS = 5


def corpus_files():
    return sorted(glob.glob(CORPUS_GLOB))


def timed_subprocess(cmd, runs):
    times = []
    last_stdout = None
    for _ in range(runs):
        t0 = time.perf_counter()
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=60)
        times.append(time.perf_counter() - t0)
        if r.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd)} failed: {r.stderr}")
        last_stdout = r.stdout
    return times, last_stdout


def median_ms(times):
    return round(statistics.median(times) * 1000, 3)


def startup_baseline(runs):
    py_times, _ = timed_subprocess([sys.executable, "-c", "pass"], runs)
    node_times, _ = timed_subprocess(["node", "-e", ""], runs)
    return {
        "python_startup_median_ms": median_ms(py_times),
        "node_startup_median_ms": median_ms(node_times),
    }


def has_foreign_declared(surface_json):
    return any(e.get("declared") is True for e in surface_json.get("effects", []))


def has_literal_foreign_keyword(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("foreign "):
                return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    files = corpus_files()
    print(f"{len(files)} corpus files", file=sys.stderr)

    baseline = startup_baseline(args.runs)

    per_file = []
    n_foreign_declared = 0
    n_foreign_keyword = 0
    py_total_median_ms = 0.0
    js_total_median_ms = 0.0

    for path in files:
        rel = os.path.relpath(path, REPO)
        py_times, py_stdout = timed_subprocess(
            [sys.executable, "shapes_cli.py", rel, "--json"], args.runs)
        js_times, js_stdout = timed_subprocess(
            ["node", "js/cli.mjs", "shapes", rel], args.runs)

        py_json = json.loads(py_stdout)
        js_json = json.loads(js_stdout)

        declared = has_foreign_declared(py_json)
        if has_foreign_declared(js_json) != declared:
            raise RuntimeError(f"{rel}: python/js surfaces disagree on declared effects")
        if declared:
            n_foreign_declared += 1
        if has_literal_foreign_keyword(path):
            n_foreign_keyword += 1

        py_med = median_ms(py_times)
        js_med = median_ms(js_times)
        py_total_median_ms += py_med
        js_total_median_ms += js_med

        per_file.append({
            "file": rel,
            "python_median_ms": py_med,
            "python_min_ms": round(min(py_times) * 1000, 3),
            "js_median_ms": js_med,
            "js_min_ms": round(min(js_times) * 1000, 3),
            "declared_effect": declared,
        })

    n = len(files)
    results = {
        "runs_per_case": args.runs,
        "n_files": n,
        "startup_baseline": baseline,
        "python_total_median_ms": round(py_total_median_ms, 3),
        "js_total_median_ms": round(js_total_median_ms, 3),
        "python_per_file_median_ms": round(py_total_median_ms / n, 3),
        "js_per_file_median_ms": round(js_total_median_ms / n, 3),
        "n_foreign_declared": n_foreign_declared,
        "foreign_declared_fraction": round(n_foreign_declared / n, 4),
        "n_foreign_keyword_literal": n_foreign_keyword,
        "foreign_keyword_fraction": round(n_foreign_keyword / n, 4),
        "per_file": per_file,
    }

    payload = json.dumps(results, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)


if __name__ == "__main__":
    main()
