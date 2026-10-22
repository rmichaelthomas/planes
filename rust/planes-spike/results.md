# Planes Rust experiment results

Date: 2026-10-21. Machine: MacBook Pro with Apple M1 Pro, macOS 26.5.2, arm64, 16 GB memory. Native benchmark: Python 3.14.7, Node.js 22.23.1, Homebrew Rust/Cargo 1.97.1. The isolated WebAssembly build used Rust stable 1.99.1 with `wasm32-unknown-unknown` installed under `/private/tmp`; it did not change the system Rust setup.

## Native H7 comparison

All five implementations produced the same output for both generated workloads before any timing was collected.

| Workload | Matching output | Rust clean release build | Rust process median | Planes Python | Planes JavaScript | Plain Python | Plain JavaScript | Rust warm operation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2,000 records × 50 updates | `total 2550000` | 1,505.65 ms | 3.91 ms | 1,379.45 ms | 265.09 ms | 33.25 ms | 69.63 ms | 0.0692 ms/run |
| 5,000 invoice lines | `due 2854966.72` | same build | 5.75 ms | 559.65 ms | 160.60 ms | 62.05 ms | 67.17 ms | 1.4740 ms/run |

Process medians use five launches per implementation. The Rust warm number uses five samples of 100 in-process runs. Rust's warm timer starts after input parsing and focuses on the bounded operation; its process median includes process startup and input loading. The other process timings include each interpreter's startup and workload execution. The H7 Planes programs are generated from `benchmarks/published/gen_jobs.py` and run as written.

These figures show this hand-written Rust implementation is much faster than the two Planes interpreter paths on these particular workloads. They do not show that Rust generally runs Planes programs faster: this Rust code directly implements two selected behaviors, without parsing or interpreting Planes, and uses an optimized release build. Plain Python and JavaScript are also included as more direct workload baselines.

## Browser comparison

On the local ChatGPT in-app browser, Chromium 155.0.0.0, both outputs matched. The first page load fetched and initialized WebAssembly in 181.40 ms; a reload with cached bytes took 6.80 ms. Warm medians were 0.1382 ms for JavaScript and 0.0922 ms for Rust/WebAssembly on record updates, and 0.8333 ms for JavaScript and 3.3611 ms for Rust/WebAssembly on the invoice. The Rust/WebAssembly invoice path was slower in that browser run, demonstrating that workload shape and implementation details matter. Browser timings are device- and session-dependent; rerun `planes-rust.html` for live figures. Native Rust compile time is measured separately by the harness.

The browser's direct JavaScript and WebAssembly paths both read the same deterministic 5,000-row invoice fixture and apply the same 2,000 × 50 record workload. The page compares result strings before taking timing samples.

## Limits

- The Rust project does not parse or execute Planes source. It encodes only the invoice and immutable record-update operations needed for these two H7 cases.
- Invoice arithmetic uses checked exact rationals and rounds once to two decimal places, half away from zero. The experiment has bounded integer and precision limits and returns errors on checked overflow.
- WebAssembly initialization time includes module fetch and instantiation; it is not a compiler measurement. Compilation is the Cargo build measured by the native harness.
- This remains outside the Planes supported runtime targets. No release, distribution, or product integration is proposed by these results.
