# Pre — unbounded retention (HEAD/main shape)

Machine: Apple M1 Pro (or current host), Python 3.14.6, Darwin 25.5.0 arm64.

`benchmarks/world_shape.planes`'s shape at S=64, checkpointed at tick 1/100/300/600 (four independent full runs, 0..checkpoint-1 ticks each — deterministic and pure, so this gives the same final world value a single continuous run would at each point).

Window: **unbounded** (no `window` argument — the literal HEAD/main shape).

| tick | reachable `Deriv` count | RSS growth from tick 1 |
|---:|---:|---:|
| 1 | 275 | 0.00 MB |
| 100 | 9,086 | 9.32 MB |
| 300 | 26,886 | 30.36 MB |
| 600 | 53,586 | 62.90 MB |

Fitted slope: **89.00 Deriv nodes/tick**, **105528.6 bytes/tick** RSS growth.

Extrapolated to a 30-minute soak at 60 ticks/second (108,000 ticks) — EXTRAPOLATION, not measured directly:

- extrapolated reachable `Deriv` count: **9,612,186**
- extrapolated RSS growth: **11,396.3 MB**

