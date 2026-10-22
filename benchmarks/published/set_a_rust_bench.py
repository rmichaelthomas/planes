#!/usr/bin/env python3
"""Parity-gated native Rust comparison for H7 record updates and invoices."""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUST_MANIFEST = REPO / "rust" / "planes-spike" / "Cargo.toml"
RUST_BIN = REPO / "rust" / "planes-spike" / "target" / "release" / "planes-spike"
TMP_DIR = Path("/tmp/planes_h7_bench")

sys.path.insert(0, str(REPO / "benchmarks" / "published"))
import gen_jobs  # noqa: E402
import set_a_bench as h7  # noqa: E402

h7.JOBS_DIR = gen_jobs.DEFAULT_JOBS_DIR


def write_invoice_data(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "".join(f"{quantity},{cents}\n" for quantity, cents in gen_jobs.invoice_lines()),
        encoding="utf-8",
    )


def require_agreement(outputs: dict[str, str]) -> str:
    if not outputs:
        raise RuntimeError("no runtime results were collected")
    expected = next(iter(outputs.values()))
    if any(output != expected for output in outputs.values()):
        details = "; ".join(f"{runtime}={output!r}" for runtime, output in outputs.items())
        raise RuntimeError(f"runtime results differ; timing is blocked: {details}")
    return expected


def require_all_agreement(case_outputs: dict[str, dict[str, str]]) -> dict[str, str]:
    if not case_outputs:
        raise RuntimeError("no workload results were collected")
    expected = {}
    failures = []
    for case, outputs in case_outputs.items():
        try:
            expected[case] = require_agreement(outputs)
        except RuntimeError as error:
            failures.append(f"{case}: {error}")
    if failures:
        raise RuntimeError("runtime results differ; all timing is blocked: " + "; ".join(failures))
    return expected


def command_output(command: list[str]) -> tuple[str, str]:
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f"{command!r} failed ({result.returncode}): {result.stderr}")
    return result.stdout.strip(), result.stderr.strip()


def lines_output(command: list[str]) -> str:
    return "\n".join(h7._lines(command_output(command)[0]))


def javascript_planes_output(key: str) -> str:
    command = ["node", "js/cli.mjs", "run", h7.job_path(key, "planes")]
    stdout, _ = command_output(command)
    envelope = json.loads(stdout)
    if envelope.get("tag") is not None:
        raise RuntimeError(f"JavaScript Planes runtime refused {key}: {envelope.get('message')}")
    return "\n".join(envelope["output"])


def rust_command(key: str, invoice_path: Path) -> list[str]:
    if key == "invoice":
        return [str(RUST_BIN), "invoice", str(invoice_path)]
    return [str(RUST_BIN), "records", str(gen_jobs.RU_N_RECORDS), str(gen_jobs.RU_N_BUMPS)]


def runtime_commands(key: str, invoice_path: Path) -> dict[str, list[str]]:
    rust = rust_command(key, invoice_path)
    return {
        "Rust": rust,
        "Planes Python": [sys.executable, "planes.py", h7.job_path(key, "planes")],
        "Planes JavaScript": ["node", "js/cli.mjs", "run", h7.job_path(key, "planes")],
        "Plain Python": [sys.executable, h7.job_path(key, "py")],
        "Plain JavaScript": ["node", h7.job_path(key, "mjs")],
    }


def collect_output(runtime: str, command: list[str]) -> str:
    stdout, _ = command_output(command)
    if runtime == "Planes JavaScript":
        envelope = json.loads(stdout)
        if envelope.get("tag") is not None:
            raise RuntimeError(f"JavaScript Planes runtime tagged result: {envelope}")
        return "\n".join(envelope["output"])
    return "\n".join(h7._lines(stdout))


def median_process_ms(command: list[str], runs: int) -> float:
    samples = []
    for _ in range(runs):
        started = time.perf_counter_ns()
        command_output(command)
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    return statistics.median(samples)


def rust_warm_ms_per_run(key: str, invoice_path: Path, repeats: int = 100, samples: int = 5) -> float:
    command = [*rust_command(key, invoice_path), "--repeat", str(repeats)]
    durations = []
    for _ in range(samples):
        stdout, stderr = command_output(command)
        if "\n".join(h7._lines(stdout)) != _expected_output(key):
            raise RuntimeError("Rust warm run changed its output; timing is blocked")
        count, elapsed_ns = stderr.split()
        if int(count) != repeats:
            raise RuntimeError("Rust warm-run counter does not match requested repetitions")
        durations.append(int(elapsed_ns) / int(count) / 1_000_000)
    return statistics.median(durations)


def _expected_output(key: str) -> str:
    if key == "invoice":
        return "due 2854966.72"
    return "total 2550000"


def machine_info() -> dict[str, str]:
    details = {
        "os": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "node": command_output(["node", "--version"])[0],
        "rustc": command_output(["rustc", "--version"])[0],
        "cargo": command_output(["cargo", "--version"])[0],
    }
    try:
        profile = json.loads(command_output(["system_profiler", "-json", "SPHardwareDataType"])[0])
        hardware = profile["SPHardwareDataType"][0]
        details["cpu"] = hardware.get("chip_type") or hardware.get("cpu_type") or "unavailable"
    except (FileNotFoundError, RuntimeError, KeyError, IndexError, json.JSONDecodeError):
        try:
            details["cpu"] = command_output(["sysctl", "-n", "machdep.cpu.brand_string"])[0]
        except (FileNotFoundError, RuntimeError):
            details["cpu"] = "unavailable"
    return details


def run_benchmark(runs: int) -> dict:
    jobs_dir = gen_jobs.main()
    h7.JOBS_DIR = jobs_dir
    invoice_path = TMP_DIR / "invoice_rust_input.csv"
    write_invoice_data(invoice_path)

    subprocess.run(["cargo", "clean", "--manifest-path", str(RUST_MANIFEST)],
                   cwd=REPO, capture_output=True, text=True, timeout=180, check=True)
    build_start = time.perf_counter_ns()
    build = subprocess.run(
        ["cargo", "build", "--release", "--manifest-path", str(RUST_MANIFEST)],
        cwd=REPO, capture_output=True, text=True, timeout=180,
    )
    if build.returncode:
        raise RuntimeError(f"Rust release build failed: {build.stderr}")
    build_ms = (time.perf_counter_ns() - build_start) / 1_000_000

    keys = ("record_updates", "invoice")
    outputs_by_case = {
        key: {name: collect_output(name, command) for name, command in runtime_commands(key, invoice_path).items()}
        for key in keys
    }
    expected_by_case = require_all_agreement(outputs_by_case)

    cases = {}
    for key in keys:
        outputs = outputs_by_case[key]
        expected = expected_by_case[key]
        commands = runtime_commands(key, invoice_path)
        process_ms = {name: median_process_ms(command, runs) for name, command in commands.items()}
        cases[key] = {
            "expected_output": expected,
            "outputs": outputs,
            "cold_process_median_ms": process_ms,
            "rust_warm_in_process_median_ms_per_run": rust_warm_ms_per_run(key, invoice_path),
            "rust_warm_repeat_count": 100,
            "rust_warm_samples": 5,
        }

    return {
        "experiment": "Planes H7 bounded Rust runtime spike",
        "machine": machine_info(),
        "rust_release_build_ms": build_ms,
        "wall_clock_runs_per_runtime": runs,
        "workload_source": "benchmarks/published/gen_jobs.py deterministic H7 data",
        "scope": "record-update and invoice workload subset; not whole-language conformance",
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5, help="cold process timings per runtime (default: 5)")
    parser.add_argument("--out", type=Path, default=Path("/private/tmp/planes-rust-h7-results.json"))
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    result = run_benchmark(args.runs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Parity passed for both workloads. Results written to {args.out}")


if __name__ == "__main__":
    main()
