# HostRules cost — measured results (H4)

Koncord v1.10 §272.4 records the per-page rule-check cost as unmeasured. This is that measurement: `swift/Sources/HostRulesBench` loads a synthetic rules fixture scaled up from `demo/rules/exception.planes`'s shape (one default-deny rule plus many named permits, each with `because`), and checks it against a synthetic 150-effect page of asks (a mix of clean hits on permitted endpoints, permitted hosts with an unnamed tracking query string, and hosts no rule mentions at all).

**Date:** captured at run time by this program.  
**Commit (base):** `0d8207e50774995446f580798b829b2c55e032ed`  
**Build configuration:** `release` (`swift run -c release HostRulesBench`; release matters — debug is meaningfully slower and not what a shipped host runs).  
**Page size:** 150 asks. **Iterations:** 2000 (load), 1000 (check-a-page), per rule-count configuration.

## Machine specs (live capture, never invented)

| | |
|---|---|
| CPU | Apple M1 Pro |
| cores | 10 |
| OS | macOS 26.5.2 |

**Other agents were building concurrently on this machine while this ran (this repo's Sprint A work was split across several parallel git worktrees). These numbers are an upper bound on the real cost, not a clean-room measurement** — CPU contention from sibling builds can only make a check look slower than it is, never faster.

## 50 rules

Page outcome (one representative check, same every iteration since the fixture is fixed): 60/150 admitted, 90 violation(s), 43 cleared-by-permit, 0 vacuous rule(s).

All times in microseconds (µs).

| | min | p50 | p95 | p99 | max | mean | n |
|---|---|---|---|---|---|---|---|
| load/compile the rules | 1788.04 | 1942.50 | 2898.96 | 3749.54 | 6549.42 | 2093.25 | 2000 |
| check a page (150 asks) | 1058.42 | 1123.29 | 1352.58 | 1941.54 | 3323.54 | 1163.48 | 1000 |

## 200 rules

Page outcome (one representative check, same every iteration since the fixture is fixed): 60/150 admitted, 90 violation(s), 60 cleared-by-permit, 0 vacuous rule(s).

All times in microseconds (µs).

| | min | p50 | p95 | p99 | max | mean | n |
|---|---|---|---|---|---|---|---|
| load/compile the rules | 7275.17 | 7816.96 | 10425.79 | 12966.96 | 42315.46 | 8240.46 | 2000 |
| check a page (150 asks) | 2805.75 | 2984.75 | 3261.08 | 3602.04 | 4643.96 | 3006.14 | 1000 |
