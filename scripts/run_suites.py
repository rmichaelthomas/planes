#!/usr/bin/env python3
"""Run the test suites, timed, with optional parallelism.

Every `test_*.py` in the repo root is a standalone script with a `__main__`
runner that exits non-zero on failure. This runner dispatches them; it does not
change what any of them asserts.

Three things it adds over `for f in test_*.py; do python3 "$f"; done`:

  * per-suite wall-clock timing, written to `.ci-logs/timings.tsv`, so the
    gate's cost is measured rather than guessed (A.0);
  * a worker pool, so the suites do not queue behind each other (A.2);
  * leak surveillance — it watches the repo root for `*.json` files appearing
    while a suite runs, and records what it sees to `.ci-logs/leaks.json`.

That last one is why the gate got most of its time back. `test_coverage.py`'s
`test_the_suite_does_not_touch_the_real_world` re-ran *every other suite* as a
subprocess to look for filesystem leaks, which made the gate run the whole
suite twice: 248.9 s of 488.7 s, and 1801 of 3602 `node` spawns, measured. The
observation it needs is available for free from a runner that is already
running every suite, so the runner makes it and hands it over. The assertion is
unchanged and still evaluated on every gate run — it now watches the real run
rather than a second synthetic one, which is strictly the stronger observation.

Three passes, in order:

  1. EXCLUSIVE suites, serially — they mutate state other suites read.
  2. everything else, in parallel.
  3. DEFERRED (`test_coverage.py`), once the leak record is complete.

Output ordering never depends on scheduling: logs are captured per suite and
replayed in filename order. `PLANES_JOBS=1` runs everything one at a time in
that same order, which is the pre-existing serial behaviour.

Usage:
    python3 scripts/run_suites.py [--skip NAME ...] [--only NAME ...]

Environment:
    PLANES_JOBS   worker count (default: CPU count). 1 == serial.
    PLANES_SUITE  set by this runner for each child, so an external
                  instrument (e.g. a `node` shim counting spawns) can
                  attribute a subprocess to the suite that spawned it.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGDIR = os.path.join(REPO, ".ci-logs")
LEAK_RECORD = os.path.join(LOGDIR, "leaks.json")

# Suites that mutate state another suite reads. Running them concurrently with
# anything else is a race, so they get the repo to themselves. Each entry names
# what it touches — a list of names with no reasons attached is a list nobody
# can ever shorten.
EXCLUSIVE = {
    # Rewrites grammar/vocabulary.json in place (first as corrupt JSON, then
    # with format 999) and restores it in a `finally`. Any suite importing
    # lexer or parser inside that window would load a corrupt grammar.
    "test_grammar_data.py",
    # Creates demo/cycle/ and demo/broken/ with .planes files; eight suites
    # walk demo/ and would pick them up mid-flight.
    "test_shapes.py",
    # Creates demo/_deriv_subject/ with .planes files — same hazard.
    "test_rules.py",
}

# Runs last, alone, once the leak record covering every other suite exists.
DEFERRED = {"test_coverage.py"}

_lock = threading.Lock()
_leaks: dict[str, list[str]] = {}
_baseline: set[str] = set()
_inflight: set[str] = set()


def discover(only: list[str], skip: list[str]) -> list[str]:
    names = sorted(f for f in os.listdir(REPO)
                   if f.startswith("test_") and f.endswith(".py"))
    if only:
        wanted = set(only)
        names = [n for n in names if n in wanted]
        missing = wanted - set(names)
        if missing:
            print(f"no such suite: {', '.join(sorted(missing))}", file=sys.stderr)
            sys.exit(2)
    if skip:
        unknown = set(skip) - set(names)
        if unknown:
            # A skip list that has drifted off the suite names would silently
            # stop skipping — and silently start running the slow tier again.
            print(f"--skip names no such suite: {', '.join(sorted(unknown))}",
                  file=sys.stderr)
            sys.exit(2)
        names = [n for n in names if n not in skip]
    return names


def _json_now() -> set[str]:
    return {os.path.basename(p) for p in glob.glob(os.path.join(REPO, "*.json"))}


def run_one(name: str, extra_env: dict | None = None) -> tuple[str, int, float]:
    env = dict(os.environ)
    env["PLANES_SUITE"] = name
    env.update(extra_env or {})
    log_path = os.path.join(LOGDIR, name + ".log")
    with _lock:
        _inflight.add(name)
    start = time.time()
    with open(log_path, "wb") as log:
        proc = subprocess.run([sys.executable, name], cwd=REPO, env=env,
                              stdout=log, stderr=subprocess.STDOUT)
    elapsed = time.time() - start
    with _lock:
        _inflight.discard(name)
        new = sorted(_json_now() - _baseline)
        if new:
            # Under parallelism the suite that wrote the file is not certain —
            # record who else was running, and say so. PLANES_JOBS=1 gives
            # exact attribution.
            others = sorted(_inflight)
            _leaks[name] = new + ([f"(concurrent: {', '.join(others)})"]
                                  if others else [])
            for f in new:
                os.remove(os.path.join(REPO, f))
    return name, proc.returncode, elapsed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", action="append", default=[])
    ap.add_argument("--only", action="append", default=[])
    args = ap.parse_args()

    names = discover(args.only, args.skip)
    if not names:
        print("no suites to run", file=sys.stderr)
        return 2

    os.makedirs(LOGDIR, exist_ok=True)
    for stale in os.listdir(LOGDIR):
        os.remove(os.path.join(LOGDIR, stale))

    jobs = int(os.environ.get("PLANES_JOBS") or os.cpu_count() or 1)
    jobs = max(1, min(jobs, len(names)))

    global _baseline
    _baseline = _json_now()

    exclusive = [n for n in names if n in EXCLUSIVE]
    deferred = [n for n in names if n in DEFERRED]
    parallel = [n for n in names if n not in EXCLUSIVE and n not in DEFERRED]

    started = time.time()
    results = [run_one(n) for n in exclusive]
    if jobs == 1:
        results += [run_one(n) for n in parallel]
    else:
        # Threads, not processes: each worker's work is a blocking
        # subprocess.run, so the GIL is released for its whole duration.
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            results += list(pool.map(run_one, parallel))

    # Every suite but the deferred one has now been watched. Hand the record
    # over through the environment rather than through the file alone: only a
    # child this runner spawned sees the variable, so a stale record left in
    # .ci-logs can never be mistaken for a fresh one.
    watched = sorted(n for n in names if n not in DEFERRED)
    # `complete` says whether this run watched every suite on disk. It is true
    # for the gate, which never skips; `--fast` sets it false, and the leak
    # check downgrades to "partial" rather than either failing or — the worse
    # outcome — passing as though it had seen everything.
    on_disk = sorted(f for f in os.listdir(REPO)
                     if f.startswith("test_") and f.endswith(".py"))
    with open(LEAK_RECORD, "w", encoding="utf-8") as fh:
        json.dump({"suites": watched, "leaks": _leaks, "jobs": jobs,
                   "complete": set(names) == set(on_disk)}, fh)
    results += [run_one(n, {"PLANES_LEAK_RECORD": LEAK_RECORD})
                for n in deferred]
    elapsed = time.time() - started

    by_name = {n: (rc, secs) for n, rc, secs in results}

    # Replay in filename order — never in completion order.
    for name in names:
        with open(os.path.join(LOGDIR, name + ".log"), encoding="utf-8",
                  errors="replace") as fh:
            sys.stdout.write(fh.read())

    with open(os.path.join(LOGDIR, "timings.tsv"), "w", encoding="utf-8") as fh:
        fh.write("suite\tseconds\texit\n")
        for name in names:
            rc, secs = by_name[name]
            fh.write(f"{name}\t{secs:.3f}\t{rc}\n")

    failures = [n for n in names if by_name[n][0] != 0]
    oks = suites = 0
    for name in names:
        with open(os.path.join(LOGDIR, name + ".log"), encoding="utf-8",
                  errors="replace") as fh:
            text = fh.read()
        oks += sum(1 for line in text.splitlines()
                   if line.startswith("  ok    "))
        suites += sum(1 for line in text.splitlines() if line.endswith(" passing"))

    print(f"\n== suites: {len(names)} files, {suites} reporting, "
          f"{oks} oks, {jobs} job(s), {elapsed:.1f}s wall ==")
    if suites != len(names):
        # A file that reports nothing ran nothing. Two files sat in this state
        # at b173190 (68 tests, all passing, none counted) because neither had
        # a `__main__` runner — REPORT_HOST_BOUNDARY.md §5's failure, twice.
        silent = [n for n in names
                  if not open(os.path.join(LOGDIR, n + ".log"), encoding="utf-8",
                              errors="replace").read().rstrip().endswith("passing")]
        print(f"WARNING: {len(names) - suites} suite file(s) reported no "
              f"result: {', '.join(silent)}", file=sys.stderr)
    if failures:
        print("FAILED: " + ", ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
