"""world_test_sink.py — the deterministic null-sink performer (Horizon
Phase 1: the engine-kernel spike, build prompt §4; design doc §23.4,
§25's "deterministic test performer").

A sink is anything with a `consume(delta, elapsed_seconds)` method;
`WorldKernel` does not depend on this class directly (see world_kernel.py —
`step()` returns `(delta, elapsed)` and leaves dispatch to the caller,
exactly so a sink call can never fall inside the timed span). `TestSink` is
this build's own sink: it renders nothing, consumes every delta, and proves
it actually received well-formed deltas by folding each one into a running
semantic-hash chain rather than by holding them all in memory — the deltas
themselves are discarded after that fold, only the timings and the chain's
final hash survive a soak.

Never average-only (design doc §16's closing line: "Average FPS alone is
insufficient") — `percentiles()` reports p50/p95/p99/p99.9, min, max, mean,
count, and the full sorted distribution.
"""
import hashlib
import math

from world_delta import canonical_delta_string

_CHAIN_SEED = "world-kernel-sink-chain-v1"


class TestSink:
    """Records per-tick step-cost timings and a semantic-hash chain over
    the deltas it consumes. Renders nothing; touches no host effect."""

    def __init__(self):
        self.timings = []
        self.chain_hash = hashlib.sha256(_CHAIN_SEED.encode()).hexdigest()
        self.count = 0

    def consume(self, delta, elapsed_seconds):
        """Fold one `(delta, elapsed_seconds)` pair in. `elapsed_seconds`
        is recorded for the percentile table; `delta` is folded into the
        hash chain and then dropped — nothing here retains a delta."""
        self.timings.append(elapsed_seconds)
        self.chain_hash = hashlib.sha256(
            (self.chain_hash + canonical_delta_string(delta)).encode()
        ).hexdigest()
        self.count += 1

    def percentiles(self):
        """p50/p95/p99/p99.9, min, max, mean, count, and the sorted
        distribution (seconds). Nearest-rank method: for percentile `p`
        over `n` sorted samples, index `ceil(p * n) - 1`, clamped to
        `[0, n-1]` — simple, deterministic, and the same convention this
        repo's other measurement scripts use for reporting a table rather
        than a fitted distribution."""
        if not self.timings:
            raise ValueError("no timings recorded — step() was never called")
        ordered = sorted(self.timings)
        n = len(ordered)

        def pct(p):
            idx = min(n - 1, max(0, math.ceil(p * n) - 1))
            return ordered[idx]

        return {
            "count": n,
            "min": ordered[0],
            "max": ordered[-1],
            "mean": sum(ordered) / n,
            "p50": pct(0.50),
            "p95": pct(0.95),
            "p99": pct(0.99),
            "p999": pct(0.999),
            "distribution": ordered,
        }
