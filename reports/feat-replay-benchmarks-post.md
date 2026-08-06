# Post — tracing off (feat/replay-on-demand-and-iterative-explain)

Machine: Apple M1 Pro (or current host), Python 3.14.6, Darwin 25.5.0 arm64.

`benchmarks/world_shape.planes`'s shape at S=64, checkpointed at tick 1/100/300/600 (four independent full runs, 0..checkpoint-1 ticks each — deterministic and pure, so this gives the same final world value a single continuous run would at each point).

Tracing: **off** (`trace=False, record=True` — the R3 fast path).

| tick | reachable `Deriv` count | wall time |
|---:|---:|---:|
| 1 | 1 | 5.118 ms |
| 100 | 1 | 182.054 ms |
| 300 | 1 | 548.791 ms |
| 600 | 1 | 1091.566 ms |

Fitted slope: **0.00 Deriv nodes/tick**, **1815.98 µs/tick** wall time.

Extrapolated to a 30-minute soak at 60 ticks/second (108,000 ticks) — EXTRAPOLATION, not measured directly:

- extrapolated reachable `Deriv` count: **1**
- extrapolated wall time: **196.13 s**

Replay cost of ONE `why` (replay() + explain(), tick=600): **1768.794 ms** — reconstructs 53,586 Deriv nodes, a 162-character card.

