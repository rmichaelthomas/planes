#!/usr/bin/env python3
"""set_a_bench.py -- H7 Set A: four ordinary jobs, three languages each.

docs/planes_sprint_2026_09_hardening.md, decision #21 (H7) asks for word
count, record updates, invoice arithmetic and a file transform, each
written in Planes, plain Python and plain Node, measured end to end
(including interpreter startup) with the Planes reference interpreter
(`python3 planes.py`) and the JavaScript one (`node js/cli.mjs run` --
README.md's own documented invocation, "the JavaScript implementation"),
5 runs each, median and min reported.

WHY A FIXED /tmp PATH, NOT tempfile.gettempdir(). The job programs
(themselves generated fresh by gen_jobs.py before every run -- see its
module docstring for why none is committed to the repo) bake in an
absolute path to their shared input, since there is no way to pass a
Planes program an argument -- the host is 7 methods, none of them argv.
tempfile.gettempdir() can rotate between shells on macOS, which would
silently orphan a path a generated .planes file names moments later in the
same run. A fixed, well-known directory under /tmp is stable across runs
and is still a temp dir, never the repo (gen_jobs.py's TMP_DIR).

WHY THE JS PLANES VARIANT PASSES A HOSTCONFIG JSON BLOB. js/cli.mjs's `run`
and `run-file` subcommands both construct a TestHost (in-memory) -- there
is no wiring from either to NodeHost (js/host_node.mjs), the JS analogue of
CliHost that touches the real filesystem; NodeHost today backs only the
low-level `host` probe subcommand. So a Planes program's `read` needs its
input pre-loaded into the hostconfig's `files` map, and its `write` lands
in the returned JSON's `files` map rather than on disk. This is a real,
reported gap, not a benchmarking artifact papered over -- see results.md.

Usage:  python3 benchmarks/published/set_a_bench.py [--runs N] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP_DIR = "/tmp/planes_h7_bench"

sys.path.insert(0, os.path.join(REPO, "benchmarks", "published"))
import gen_jobs  # noqa: E402

# Job programs are never committed to the repo -- see gen_jobs.py's module
# docstring: the metacircular suites glob every **/*.planes file under the
# repo, and these programs broke three of them. gen_jobs.main() (called in
# main() below) writes them fresh, here, before every timed run.
JOBS_DIR = gen_jobs.DEFAULT_JOBS_DIR

DEFAULT_RUNS = 5

JOBS = [
    {"key": "hello", "files": []},
    {"key": "word_count", "files": [gen_jobs.WORD_COUNT_INPUT]},
    {"key": "record_updates", "files": []},
    {"key": "invoice", "files": []},
    {"key": "file_transform", "files": [gen_jobs.FILE_TRANSFORM_INPUT]},
]


def job_path(key, ext):
    return os.path.join(JOBS_DIR, f"{key}.{ext}")


def _lines(text):
    text = text.strip("\n")
    return text.split("\n") if text else []


def run_planes_py(key):
    r = subprocess.run(
        [sys.executable, "planes.py", job_path(key, "planes")],
        cwd=REPO, capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"planes.py {key} failed: {r.stderr}")
    return _lines(r.stdout)


def _js_hostconfig(files):
    if not files:
        return None
    blob = {"files": {p: open(p, encoding="utf-8").read() for p in files}}
    return json.dumps(blob)


def run_planes_js(key, hostconfig):
    cmd = ["node", "js/cli.mjs", "run", job_path(key, "planes")]
    if hostconfig is not None:
        cmd.append(hostconfig)
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"js run {key} failed: {r.stderr}")
    data = json.loads(r.stdout)
    if data.get("tag") is not None:
        raise RuntimeError(f"js run {key} tagged {data['tag']}: {data.get('message')}")
    return data["output"], data


def run_plain_py(key):
    r = subprocess.run(
        [sys.executable, job_path(key, "py")],
        cwd=REPO, capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"plain python {key} failed: {r.stderr}")
    return _lines(r.stdout)


def run_plain_js(key):
    r = subprocess.run(
        ["node", job_path(key, "mjs")],
        cwd=REPO, capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"plain node {key} failed: {r.stderr}")
    return _lines(r.stdout)


FT_OUT_PLANES = os.path.join(TMP_DIR, "file_transform_output_planes.csv")
FT_OUT_PY = os.path.join(TMP_DIR, "file_transform_output_py.csv")
FT_OUT_MJS = os.path.join(TMP_DIR, "file_transform_output_mjs.csv")


def check_correctness(key, hostconfig):
    """Runs all four variants once each and asserts they produce the same
    output -- the gate H7 requires before any of the four is timed."""
    planes_py_out = run_planes_py(key)
    planes_js_out, planes_js_data = run_planes_js(key, hostconfig)
    plain_py_out = run_plain_py(key)
    plain_js_out = run_plain_js(key)

    assert planes_py_out == planes_js_out == plain_py_out == plain_js_out, (
        f"{key}: stdout diverges\n"
        f"  planes.py : {planes_py_out}\n"
        f"  planes-js : {planes_js_out}\n"
        f"  plain py  : {plain_py_out}\n"
        f"  plain js  : {plain_js_out}\n"
    )

    if key == "file_transform":
        planes_py_doc = json.loads(open(FT_OUT_PLANES, encoding="utf-8").read())
        planes_js_doc = json.loads(planes_js_data["files"][FT_OUT_PLANES])
        plain_py_doc = open(FT_OUT_PY, encoding="utf-8").read()
        plain_js_doc = open(FT_OUT_MJS, encoding="utf-8").read()
        assert planes_py_doc == planes_js_doc == plain_py_doc == plain_js_doc, (
            f"{key}: written file content diverges")

    return planes_py_out


def timed(cmd_fn, runs):
    """cmd_fn takes no args, returns the parsed output (discarded --
    correctness was already checked separately). Returns the list of wall
    times in seconds."""
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        cmd_fn()
        times.append(time.perf_counter() - t0)
    return times


def summarize(times):
    return {
        "runs": len(times),
        "median_ms": round(statistics.median(times) * 1000, 2),
        "min_ms": round(min(times) * 1000, 2),
        "max_ms": round(max(times) * 1000, 2),
        "all_ms": [round(t * 1000, 2) for t in times],
    }


def machine_info():
    def sysctl(name):
        return subprocess.run(["sysctl", "-n", name], capture_output=True, text=True).stdout.strip()

    node_version = subprocess.run(
        ["node", "--version"], capture_output=True, text=True).stdout.strip()
    info = {
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "node_version": node_version,
    }
    if platform.system() == "Darwin":
        info["cpu_brand"] = sysctl("machdep.cpu.brand_string")
        info["ncpu"] = sysctl("hw.ncpu")
        info["memsize_bytes"] = sysctl("hw.memsize")
        info["macos_version"] = subprocess.run(
            ["sw_vers", "-productVersion"], capture_output=True, text=True).stdout.strip()
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    print("regenerating job sources and shared inputs...", file=sys.stderr)
    gen_jobs.main()

    results = {"machine": machine_info(), "runs_per_case": args.runs, "jobs": {}}

    for job in JOBS:
        key = job["key"]
        hostconfig = _js_hostconfig(job["files"])
        print(f"checking correctness: {key}", file=sys.stderr)
        output = check_correctness(key, hostconfig)

        print(f"timing: {key}", file=sys.stderr)
        t_planes_py = timed(lambda k=key: run_planes_py(k), args.runs)
        t_planes_js = timed(lambda k=key, h=hostconfig: run_planes_js(k, h), args.runs)
        t_plain_py = timed(lambda k=key: run_plain_py(k), args.runs)
        t_plain_js = timed(lambda k=key: run_plain_js(k), args.runs)

        results["jobs"][key] = {
            "output": output,
            "planes_py": summarize(t_planes_py),
            "planes_js": summarize(t_planes_js),
            "plain_py": summarize(t_plain_py),
            "plain_js": summarize(t_plain_js),
        }

    # ratios: Planes vs plain, computed from medians, hello-world-adjusted
    # (interpreter startup subtracted) as well as raw.
    hello = results["jobs"]["hello"]
    for key, job in results["jobs"].items():
        if key == "hello":
            continue
        job["ratio_planes_py_over_plain_py"] = round(
            job["planes_py"]["median_ms"] / job["plain_py"]["median_ms"], 2)
        job["ratio_planes_js_over_plain_js"] = round(
            job["planes_js"]["median_ms"] / job["plain_js"]["median_ms"], 2)
        adj_planes_py = max(job["planes_py"]["median_ms"] - hello["planes_py"]["median_ms"], 0.001)
        adj_plain_py = max(job["plain_py"]["median_ms"] - hello["plain_py"]["median_ms"], 0.001)
        adj_planes_js = max(job["planes_js"]["median_ms"] - hello["planes_js"]["median_ms"], 0.001)
        adj_plain_js = max(job["plain_js"]["median_ms"] - hello["plain_js"]["median_ms"], 0.001)
        job["ratio_planes_py_over_plain_py_startup_adjusted"] = round(
            adj_planes_py / adj_plain_py, 2)
        job["ratio_planes_js_over_plain_js_startup_adjusted"] = round(
            adj_planes_js / adj_plain_js, 2)

    payload = json.dumps(results, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)


if __name__ == "__main__":
    main()
