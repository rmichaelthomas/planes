# Post — retention window=900 (feat/retention-window-and-seals)

Machine: Apple M1 Pro (or current host), Python 3.14.6, Darwin 25.5.0 arm64.

`benchmarks/world_shape.planes`'s shape at S=64, checkpointed at tick 1/100/300/600 (four independent full runs, 0..checkpoint-1 ticks each — deterministic and pure, so this gives the same final world value a single continuous run would at each point).

Window: **900 generations** (≈10 ticks of full history at §5.4's measured 89 Deriv nodes/tick).

| tick | reachable `Deriv` count | RSS growth from tick 1 |
|---:|---:|---:|
| 1 | 22 | 0.00 MB |
| 100 | 22 | 8.75 MB |
| 300 | 22 | 30.64 MB |
| 600 | 22 | 69.73 MB |

Fitted slope: **0.00 Deriv nodes/tick**, **117411.9 bytes/tick** RSS growth.

Extrapolated to a 30-minute soak at 60 ticks/second (108,000 ticks) — EXTRAPOLATION, not measured directly:

- extrapolated reachable `Deriv` count: **22**
- extrapolated RSS growth: **12,678.4 MB**

