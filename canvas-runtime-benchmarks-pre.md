## Pre-Build Benchmarks — feat/canvas-runtime
**Date:** 2026-07-27 (pre-build)
**Commit:** b4fae43

There is no prior painting behaviour to compare against, so what is measured
here is the cost of one `runProgram` call — the per-frame unit the tick loop
(§3) depends on. All cases run under plain `node` (no `--stack-size` flag),
via `runProgram` imported from `js/browser_main.mjs`, matching the environment
`paint.html` itself will run in (a browser tab has its own default stack,
not a Node CLI flag).

| case | what | mean ms (20 runs) |
|---|---|---|
| 1 | `index.html`'s sample program, as-is | 0.1555 |
| 2 | a 20-line arithmetic-only program (no effects) | 0.1724 |
| 3 | a 20-line program emitting 200 `show` lines | 0.6190 |
| 4 | a recursive program at depth 100 | 1.2120 |
| 5 | the same recursive program, depth where it first fails | ceiling: **depth 639** |

Case 5 method: `recurse of n` (`give 1 + (recurse of (n - 1))`, base case at
`n <= 0`) run at increasing depth until `runProgram` returns an error tagged
`recursion-too-deep`; binary search located the exact boundary. Under plain
`node` (no stack-size tuning), depths 1–638 succeed and 639 is the first to
fail. This is the ceiling `paint/turtle.planes` (§4) is written against —
its recursion depth must stay well inside 639.
