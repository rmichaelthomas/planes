# Canvas Runtime Verification (§9.2)

Run at commit `81f2051c59db5bc837c4a8628fe8cac72523793b`.

| Category | Check | Result | Detail |
|---|---|---|---|
| Protocol | every verb in the A.5 whitelist parses | PASS |  |
| Protocol | wrong arity returns null | PASS |  |
| Protocol | an unknown verb returns null | PASS |  |
| Protocol | a `~`-prefixed number is accepted and the ~ is dropped | PASS |  |
| Loop | composePrelude's output parses as valid Planes | PASS |  |
| Loop | a three-tick sequence threads state correctly | PASS |  |
| Loop | a first tick with nothing state works | PASS |  |
| Loop | an erroring program returns the error rather than throwing | PASS |  |
| Loop | a recursion-too-deep error is reported as itself | PASS |  |
| Surfaces | turtle.planes's surface computes without error | PASS |  |
| Surfaces | bloom.planes's surface computes without error | PASS |  |
| Surfaces | snake.planes's surface computes without error | PASS |  |
| Surfaces | turtle.planes's surface is console only | PASS |  |
| Surfaces | bloom.planes's surface is console only | PASS |  |
| Surfaces | snake.planes's surface is exactly console and file:write state.json | PASS |  |
| Surfaces | no example program's surface touches network | PASS |  |
| Isolation | no third-party origin appears in a src/href in paint.html | PASS |  |
| Isolation | no `foreign` declaration in any paint/*.planes file | PASS |  |
| Isolation | reserved words / builtins / effect kinds are unchanged at 32 / 10 / 7 | PASS |  |
| Isolation | the host surface is unchanged at 7 methods | PASS |  |
| Regression | index.html's sample program runs and matches its expected output | PASS |  |

**21/21 checks passed.**

All checks passed, including both blocking categories (C, D).
