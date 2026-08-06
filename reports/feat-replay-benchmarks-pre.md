# Pre — tracing on (HEAD/main shape)

Machine: Apple M1 Pro (or current host), Python 3.14.6, Darwin 25.5.0 arm64.

`benchmarks/world_shape.planes`'s shape at S=64, checkpointed at tick 1/100/300/600 (four independent full runs, 0..checkpoint-1 ticks each — deterministic and pure, so this gives the same final world value a single continuous run would at each point).

Tracing: **on** (`trace=True`, the default — the literal HEAD/main shape).

| tick | reachable `Deriv` count | wall time |
|---:|---:|---:|
| 1 | 275 | 7.574 ms |
| 100 | 9,086 | 278.074 ms |
| 300 | 26,886 | 865.975 ms |
| 600 | 53,586 | 1755.311 ms |

Fitted slope: **89.00 Deriv nodes/tick**, **2927.60 µs/tick** wall time.

Extrapolated to a 30-minute soak at 60 ticks/second (108,000 ticks) — EXTRAPOLATION, not measured directly:

- extrapolated reachable `Deriv` count: **9,612,186**
- extrapolated wall time: **316.17 s**

