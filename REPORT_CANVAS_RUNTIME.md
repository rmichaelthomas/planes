# REPORT — Planes Draws: A Canvas Runtime That Adds Nothing to the Language

**Branch:** `feat/canvas-runtime` · **Base:** `main` at `b4fae43` ("Planes shows its work", #36)
**Counts:** 32 / 10 / 7 / 7, unchanged · **JS tests:** 47 → **108 passed** · **Suites:** 56 files, 1124 oks
**Node:** v22.23.1 · No `grammar/`, no `*.py`, no `js/*.mjs` implementation module changed except one guard in `js/browser_main.mjs`

A second page — `paint.html` — runs a Planes program and paints its `show`
output onto a canvas, then re-runs it on a tick with the prior state threaded
back in through the VFS. A recursive tree, a generative bloom of rings, and a
playable, losable snake game, all written in Planes, all running in a browser
tab with no install, no server, no bundler and no CDN.

---

## Did the language need anything?

**No.** Every drawing, every animation, every keypress and every state update
in all three examples is expressible with the language exactly as it stood at
`b4fae43` — 32 reserved words, 10 builtins, 7 effect kinds, 7 required host
methods, none added, none removed. Two things had to be *written in Planes*
that a language with more arithmetic surface would have gotten for free (a
modulo operator, in `mod`; a rotation, never gotten at all — see below) but
"had to write it in the language" is a different claim from "the language
needed it added," and the distinction is the entire point of this build.

---

## The three programs' computed surfaces, verbatim

```
=====turtle=====
console:
  show clear
  show line {...} {...} (computed)
  show move {...} {...} (computed)
  show pen 0.36 0.24 0.14
  show width 2

why — where each target comes from (nothing was run):
  show line {...} {...} (computed)
      why → derives from: tip-x, tip-y
  show move {...} {...} (computed)
      why → derives from: fork-x, fork-y

=====bloom=====
console:
  show circle {...} {...} {...} (computed)
  show clear
  show pen {...} {...} 0.65 (computed)
  show width 2

why — where each target comes from (nothing was run):
  show circle {...} {...} {...} (computed)
      why → derives from: center-x, center-y, radius
  show pen {...} {...} 0.65 (computed)
      why → derives from: hue

=====snake=====
file:
  write state.json
console:
  show box {...} {...} {...} {...} (computed)
  show clear
  show dot {...} {...} {...} (computed)
  show pen 0.1 0.1 0.1
  show pen 0.2 0.55 0.2
  show pen 0.45 0.85 0.25
  show pen 0.85 0.15 0.15
  show text 140 180 GAME OVER  -  press Reset to play again
  show text 8 16 score: {...} (computed)

why — where each target comes from (nothing was run):
  show box {...} {...} {...} {...} (computed)
      why → derives from: seg-px, seg-py
  show dot {...} {...} {...} (computed)
      why → derives from: apple-cx, apple-cy
```

`turtle` and `bloom` touch nothing but `console`. `snake` touches exactly
`console` and `file: write state.json` — A.3's promised two-line surface,
computed, not asserted. **No program's surface touches `network` or
`ambient`, and no `foreign` declaration appears anywhere in `paint/`.**

---

## The frame rate, and where the per-tick time goes

Full numbers in `canvas-runtime-benchmarks-post.md`; the headline:

- **`snake.planes`: 0.4811 ms/tick → 2078 ticks/second.** **`bloom.planes`:
  0.5285 ms/tick → 1892 ticks/second.** Both measured under plain `node`,
  mean of 200 ticks, via `step()` (prelude composition + full `runProgram`).
- **Prelude composition is never more than 0.71% of a tick.** It is not where
  the time goes, for either program.
- **The rest splits differently by program, and the reason is visible:**
  parsing is **73.8%** of a `snake.planes` tick (it is long on branching —
  four direction checks, a wall check, a self-collision scan, an apple check
  — and short on arithmetic), but only **34.9%** of a `bloom.planes` tick
  (short source, but its `mod`/`triangle` helpers actually recurse, so
  evaluation is the larger share of a larger total). **The program is
  re-parsed from scratch on every tick — `step()` has no cache — and for the
  branch-heavy example that dominates.** This bears directly on the
  allocation-versus-arithmetic question this build's rulings left open: at
  these tick rates it is not arithmetic that costs, it is re-deriving the AST
  every frame.
- **The interpreter is nowhere near the bottleneck for how the page actually
  plays.** `paint.html` throttles `snake.planes` to one tick per 8 animation
  frames (≈7.5 ticks/second against a 60Hz `requestAnimationFrame`) — not
  because 2078 ticks/second is too slow, but because it is far too *fast* for
  a human to steer a grid-stepped game. See the disproof below; this throttle
  is the fix for it.

---

## The recursion ceiling, and what `turtle.planes` actually uses

**639** — the depth at which a single-chain recursive Planes function first
raises `recursion-too-deep` under plain `node` (`canvas-runtime-benchmarks-pre.md`,
case 5; binary search, depths 1–638 succeed, 639 is the first to fail).

`turtle.planes`'s `tree` function reaches a **structurally exact** peak
recursion depth of **9** (`starting-depth = 8`, decremented to the base case
at `remaining-depth = 0`, so 9 nested calls sit on the stack at the deepest
point of any single downward path — branching adds total call *count*, not
stack *depth*, since only one branch is ever active on the stack at once, the
same fact that makes `recurse(n)` in case 5 a valid stand-in for any
single-chain recursive function). **9 of 639 is 1.4% of the measured
ceiling** — turtle draws its whole 255-node, 513-line picture with enormous
headroom to spare.

---

## Every protocol verb added beyond A.5

**None.** `pen`, `width`, `move`, `line`, `circle`, `dot`, `rect`, `box`,
`text`, `clear` — the ten verbs A.5 specified, no more, no fewer. All three
example programs express everything they draw — a recursive tree, ten
pulsating rings, a snake's body/head/apple/score/game-over text — inside that
whitelist.

---

## What this build disproved about this prompt

**The tick loop, read literally, produces an unplayable game — not because
the interpreter is slow, but because it is fast.** §3 states the loop is
`requestAnimationFrame` and caps at one `runProgram` call per animation frame;
nothing in the prompt says a tick may run *slower* than the display's own
rate. Taken at face value — one Planes tick per callback, no throttle — a
human playtest of `snake.planes` died into the right-hand wall before a single
arrow-key press could take effect: at 60 ticks/second a snake crosses a
24-cell board in 400 milliseconds, and a live Playwright session confirmed it
exactly this way (screenshot in the build log: game over, at the initial
heading, well before any key event had time to land). **A per-program tick
throttle (`stepEveryNFrames`, still bounded by "never more than one
`runProgram` call per animation frame" — it only ever skips callbacks, never
adds a second call to one) was necessary and is not named anywhere in the
prompt.** `bloom.planes` needed none (a generative piece has no reaction time
to miss); a keyboard-steered, grid-stepped game does. This is a genuine gap in
§3 as written, found by actually trying to play the thing rather than by
reading the spec.

A smaller, second finding: the language has neither a modulo operator nor any
trigonometric builtin, and — since browser-loaded `paint/*.planes` files
cannot share code with each other (the module-graph loader is Node-only,
`js/run_file.mjs`, and `paint.html` runs each file as one standalone
`runProgram` call) — the same doubling-reduction `mod` helper had to be
written twice, byte-for-byte identical, once in `bloom.planes` and once in
`snake.planes`. Not a defect in the language (§7 anticipates exactly this:
"the protocol needs a verb that is not in A.5's list... report it," and the
answer here was "no protocol verb was missing, a *language-level* arithmetic
gap was filled in Planes itself, twice, because files here cannot import each
other") — but a real, measurable cost of "no shared code between the three
examples" that the prompt did not flag.

---

## What remains

- **`grammar/json.planes` as the state route (A.3) — deliberately unattempted, and the benchmark now says why it should stay that way for now.** Routing `state.json` through the interpreted JSON parser instead of the harness's own `JSON.parse` would add a second full parse-and-walk to the already-parse-dominated `snake.planes` tick (73.8% parse share measured above) before anything about it has been profiled. Worth measuring before attempting — a **runtime** question, not a language one; `read`/`write`/JSON-as-text already exist, nothing new would be added to try it.
- **A per-tick parse cache**, keyed on the unchanged program source (the textarea only changes when a human edits it), is the next lever if a program ever needed more than ~2000 ticks/second of headroom. **Runtime**, not language.
- **The `stepEveryNFrames` throttle** introduced above to make `snake.planes` humanly playable. **Runtime** (page/loop-level), not language — no Planes program contains a tick, a callback, or a wait (A.2 holds).
- **Nothing outstanding is language.** Counts stay 32 / 10 / 7 / 7, `scripts/ci.sh` is green, and the metacircular/self-hosted stack (`grammar/*.planes`) was not touched by this build at all.
