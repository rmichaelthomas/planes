# Planes Rust experiment

This is an isolated Rust implementation of two existing Planes H7 workloads. It is a learning and measurement experiment, not a Rust interpreter and not a supported Planes execution target.

The bounded library implements checked rational arithmetic for the invoice calculation and immutable integer-record updates for the record workload. It accepts generated CSV rows in the native CLI; it does not parse Planes source. Each workload's output is checked against the Planes Python and JavaScript implementations and their plain Python and JavaScript counterparts before native timing starts.

## Run the native comparison

From the repository root:

```sh
python3 benchmarks/published/set_a_rust_bench.py --runs 5 --out /tmp/planes-rust-h7-results.json
```

The harness regenerates H7 inputs, times a clean optimized Rust build, checks output equality across all five implementations, then measures process-level runs. The Rust CLI also supports repeated in-process runs, timed separately from process startup. The JSON report contains exact output and machine/toolchain information.

## Run the browser comparison

Install the `wasm32-unknown-unknown` target for a Rust stable toolchain, then from the repository root build and serve the page:

```sh
rustup target add wasm32-unknown-unknown
cargo build --release --target wasm32-unknown-unknown --manifest-path rust/planes-spike/Cargo.toml
python3 -m http.server 8000
```

Open `http://127.0.0.1:8000/rust/planes-spike/demo.html`. The local-only page compares direct JavaScript with Rust compiled to WebAssembly for the same H7 inputs, verifies output equality before timing, and reports module fetch/initialization separately. It is kept out of the deployed Planes site. The browser invoice fixture is committed at `rust/planes-spike/data/h7_invoice.csv`; its test confirms it still matches the deterministic H7 generator.

## Checks

```sh
cargo fmt --manifest-path rust/planes-spike/Cargo.toml -- --check
cargo test --manifest-path rust/planes-spike/Cargo.toml --test runtime
python3 -m unittest benchmarks.published.test_rust_bench -v
python3 rust/planes-spike/tests/test_invoice_fixture.py -v
node rust/planes-spike/tests/wasm_outputs.mjs
```

The WebAssembly output checks expect the module to have been built first. See `results.md` for measurements and limitations.
