## Post-Build Benchmarks — feat/canvas-runtime
**Date:** 2026-07-27 (post-build)
**Commit:** 81f2051

Method as in the pre-build doc: plain `node` (no `--stack-size`), `step()` from
`js/paint/loop.mjs` (which composes the prelude and calls `runProgram`),
mean of 200 ticks unless noted.

| case | what | result |
|---|---|---|
| 6 | `snake.planes` — mean ms/tick over 200 ticks | 0.4811 ms → **2078 fps** |
| 7 | `bloom.planes` — mean ms/tick over 200 ticks | 0.5285 ms → **1892 fps** |
| 8 | prelude composition cost alone, share of case 6 | 0.0034 ms → **0.71%** of a snake tick |
| 9 | peak interpreted recursion depth reached by `turtle.planes` | **9** (`starting-depth = 8`, plus the base-case call at `remaining-depth = 0`) |

Case 6's key sequence cycles ArrowRight/ArrowDown/ArrowLeft/ArrowUp every 20
ticks so the run exercises real state threading (turning, not just dying into
the first wall). Case 9 is a structural count, not a search: `tree`'s single
active call chain is bounded by its `remaining-depth` parameter exactly the
way `recurse` was in case 5 (branching adds total call *count*, not stack
*depth* — only one branch is ever on the stack at a time), so 9 is exact, not
estimated. Against the 639-deep ceiling measured in case 5
(`canvas-runtime-benchmarks-pre.md`), `turtle.planes` uses 1.4% of the
interpreter's headroom.

### Where the per-tick time goes

Parsing `composePrelude(...) + "\n" + source` alone (`js/parser.mjs`'s
`parse`, no evaluation), mean of 200 calls:

| program | parse-only (ms) | full tick (ms) | parse's share |
|---|---|---|---|
| `snake.planes` | 0.3549 | 0.4811 | **73.8%** |
| `bloom.planes` | 0.1844 | 0.5285 | **34.9%** |

The two programs split differently, and the reason is visible in what each
one spends its tick on. `snake.planes` is long on branching (four direction
checks, a wall check, a self-collision scan, an apple check) but does almost
no arithmetic — parsing that much source dominates its tick. `bloom.planes`
is short on source but its `mod`/`triangle` helpers actually recurse
(O(log(tick/period)) deep, ten rings deep) — real evaluation work, so parsing
is a smaller share of a larger total. Prelude composition (case 8) is
negligible either way, well under 1%.

**Per-tick cost is dominated by parsing the program, not evaluating it, for at
least one of the two ticking examples (`snake.planes`, 73.8%) — and the
program genuinely is re-parsed from scratch on every tick, since `step()` has
no cache and re-runs `parse` inside `runProgram` each call.** This bears
directly on the allocation-versus-arithmetic question this build's rulings
left open: at these tick rates it isn't arithmetic that's expensive, it's
re-deriving the AST every frame — a per-tick parse cache (keyed on the
unchanged program source, which never varies within a session unless the
textarea is edited) is the obvious next lever if a program ever needed more
headroom than ~2000 ticks/second affords, and it is a runtime change, not a
language one.

### Plain answers

- **Frame rate a Planes game achieves in a browser today:** in the 1,800–2,100
  ticks/second range measured here under Node — `paint.html` itself throttles
  `snake.planes` to roughly 7.5 ticks/second (`stepEveryNFrames: 8` against a
  60Hz `requestAnimationFrame`) because a human cannot steer a grid-stepped
  game at 2,000 moves a second, not because the interpreter is slow. The
  interpreter is nowhere near the bottleneck; the display's own paint rate is.
- **Where the per-tick time goes:** mostly parsing, for the branch-heavy
  example; mostly evaluation, for the arithmetic-heavy one. Neither ever
  spends more than 1% composing the prelude.
- **Did the language need anything added:** no. Counts are unchanged at
  32/10/7/7 after this measurement pass, same as before it.
