// js/world_test_sink.mjs — the JavaScript deterministic null-sink performer
// (Horizon Phase 1: the engine-kernel spike). Mirrors world_test_sink.py's
// contract exactly; see that file's module docstring for the full
// rationale (build prompt §4; design doc §16, §23.4, §25).

import { canonicalDeltaString } from "./world_delta.mjs";
import { sha256Hex } from "./sha256.mjs";

const CHAIN_SEED = "world-kernel-sink-chain-v1";

export class TestSink {
  constructor() {
    this.timings = [];
    this.chainHash = sha256Hex(CHAIN_SEED);
    this.count = 0;
  }

  // Fold one { delta, elapsedSeconds } pair in. elapsedSeconds is recorded
  // for the percentile table; delta is folded into the hash chain and then
  // dropped.
  consume(delta, elapsedSeconds) {
    this.timings.push(elapsedSeconds);
    this.chainHash = sha256Hex(this.chainHash + canonicalDeltaString(delta));
    this.count += 1;
  }

  // p50/p95/p99/p99.9, min, max, mean, count, and the sorted distribution
  // (seconds). Nearest-rank method, matching world_test_sink.py's
  // percentiles() exactly: index ceil(p * n) - 1, clamped to [0, n-1].
  percentiles() {
    if (this.timings.length === 0) {
      throw new Error("no timings recorded — step() was never called");
    }
    const ordered = [...this.timings].sort((a, b) => a - b);
    const n = ordered.length;
    const pct = (p) => ordered[Math.min(n - 1, Math.max(0, Math.ceil(p * n) - 1))];

    return {
      count: n,
      min: ordered[0],
      max: ordered[n - 1],
      mean: ordered.reduce((a, b) => a + b, 0) / n,
      p50: pct(0.50),
      p95: pct(0.95),
      p99: pct(0.99),
      p999: pct(0.999),
      distribution: ordered,
    };
  }
}
