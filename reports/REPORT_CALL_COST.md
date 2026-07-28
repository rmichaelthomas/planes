# REPORT — What a Call Costs: the Library Differential and the Ladder

**Build:** `feat/call-cost-measurement`, base `main` at `5bf28af`.
**Question:** the sine build (PR #41) reported roughly 5 microseconds per
interpreted call in the JS implementation, with the builtin itself only
0.08ms of bloom's 2.44ms tick. The builtin was never the cost; the call
chain around it was, and nothing in the repo measured where it went. This
build produces two measurements and changes nothing it measures — no
interpreter, numeric, parser, lexer, analyser, or renderer file is touched
(`git diff --stat main -- '*.py'` and `git diff --stat main -- js/ paint/
grammar/ js/paint/` show only new files under `scripts/`, `benchmarks/`,
`reports/`).

**Framing, preserved from the build prompt.** bloom's tick is 2.44ms against
a 16.7ms frame budget — about 15%. **This is not a performance problem** and
nothing below reports it as one. It is an instrument for a question open
since early in the chain (A-Q2: allocation or arithmetic?), and a
precondition for A-Q3 (what an optimiser would be permitted to change) —
which this build does not decide.

**SHAs captured at branch time**, before anything else:

| path | blob SHA |
|---|---|
| `scripts/measure_frames_per_call.py` | `3479546a0dffb69ce81c3c81d88753cc5d74ee6a` |
| `paint/bloom.planes` | `a541fdc1b80706ce54249ad75368ab5f17f864b8` |
| `paint/draw.planes` | `605282cbb862f70dd1f66470eecdbf9209f112b3` |
| `reports/REPORT_VALUES.md` | `61a55d98dab19b2a7fbf554e0cf29e3406893e2a` |

Verified absent at `5bf28af`: no `benchmarks/` directory; no inline twin of
any program (`paint/` held five files — three programs, two libraries); no
time-per-call measurement (`scripts/` held exactly four `measure_*` scripts —
`measure_association_idiom.py`, `measure_effect_surface.py`,
`measure_frames_per_call.py`, `measure_interp_planes.py` — none timing a call).

---

## 1. Method

Two independent measurements, run separately, cross-checked against each
other in §6.

### 1.1 The differential (`scripts/measure_library_differential.mjs`)

Runs `paint/bloom.planes` (the library arm — `use draw`, `use math`) and
`benchmarks/bloom_inline.planes` (the inline arm — `use math` only, every
`draw.planes` helper call replaced by the inline `show` string it expands
to) over the same 200-tick range under Node, through the exact path
`paint.html` and the paint test suite already use — `stepGraph`
(`js/paint/loop.mjs`) over `BrowserModuleLoader` (`js/module_loader_browser.mjs`)
with an fs-backed `fetch` stub. **The two streams are asserted
byte-identical across the whole tick range before any timing figure is
computed** — the correctness anchor and the twin's own staleness detector
(§3.2 of the build prompt): if `paint/bloom.planes` changes later without a
matching update to the twin, this assertion breaks loudly instead of the
measurement quietly comparing two different pictures.

**bloom only, not turtle or snake — a scoping choice, stated here rather
than left as an omission.** bloom has the highest drawing-call density of
the three example programs (140 `draw`-prefixed calls per tick, constant
across ticks — verified below), so its library overhead is the **upper
bound** on the effect, which is the decision-relevant figure. turtle is a
single static run: one measurement, not a per-tick one. snake is
logic-heavy with far fewer drawing calls per tick. Writing three twins would
triple the hand-derivation and the staleness surface (§3.2 above) for two
numbers that would only sit below the bound bloom already measures.

### 1.2 The ladder (`scripts/measure_call_cost.mjs`, `scripts/measure_call_cost.py`)

Decomposes the cost of one interpreted call by subtraction. Each rung is a
tiny program that adds ONE thing to an otherwise-identical call:

| # | Body | Isolates |
|---|---|---|
| 1 | `to noop: give nothing` | dispatch + environment allocation |
| 2 | `to ident of x: give x` | + parameter binding |
| 3 | `to add1 of x: give x + 1` | + one rational op and its derivation record |
| 4 | `to add3 of x: give x + 1 + 1 + 1` | rung 4 − rung 3 = two arithmetic ops with no extra call |
| 5 | `to txt of x: give text of x` | a derived value with no gcd (compare to rung 3) |
| 6 | `to c of x,y,r: show "draw circle " + text of x + " " + text of y + " " + text of r` | the `draw.planes` `circle` helper's body exactly |
| 7 | assignment to an outer-scope name, recursion depth 1 vs depth 8 | the `Env.set` parent-chain walk, if any |

**Each rung and the control run through the ordinary program entry point**
(`runProgram` in JS, `Interpreter(host=TestHost()).run(src)` in Python) —
nothing reaches into the interpreter's internals. `TestHost`/`BrowserHost`
are used explicitly so rung 6's `show` calls never touch real stdout, which
would otherwise add I/O cost to the very thing being measured.

**Why a nested `for each` loop, not recursion, drives the iteration count.**
Planes recursion has a ceiling around ~140–200 levels
(`scripts/measure_frames_per_call.py` measures it directly) — far short of
the hundreds of thousands of iterations a 200ms floor needs at
sub-microsecond per-call costs. `for each` iterates with a native host-language
loop (`interp.py`'s `eval_foreach` is a plain Python `for`), never a
Planes-level call, so it never touches that ceiling. A flat list of that
many elements would also mean a multi-megabyte source literal, parsed every
trial — nesting two `for each` loops over the same modest list (length `L`,
`N = L*L` total iterations) keeps the source text under ~20KB while `N`
scales quadratically with `L`. The nesting's own overhead (one extra `Env`
per level) is identical between a rung and its control, so it cancels in
the subtraction exactly like the loop overhead does.

**Timer discipline:**
- Node: `process.hrtime.bigint()`, not `performance.now()` (deliberately
  coarsened, well above the 5us signal this ladder resolves).
- Python: `time.perf_counter_ns()`.
- Never a single call timed. Each rung's `L` is calibrated (adaptive
  doubling from the observed elapsed time, since cost scales quadratically
  in `L`) so one run takes **at least 200ms**; the iteration count `N` is
  reported per rung.
- One further, larger, untimed warm-up run precedes the timed trials, sized
  to `max(1000, ceil(0.1 * N))` iterations, discarding JIT warm-up from the
  figure.
- **7 trials**, median and minimum reported — not the mean.
- **The empty-loop control is measured the same way, at the SAME `L` as the
  rung it is subtracted from** — not independently calibrated to its own
  200ms floor. This is the correct comparison: subtraction requires holding
  `N` constant, and the control's absolute wall-clock (which can be well
  under 200ms for a cheap rung) is never reported as a figure in its own
  right, only as a subtrahend.
- Machine: Apple M1 Pro, Darwin 25.5.0 arm64. Node `v22.23.1`. Python `3.14.6`.

**The closure criterion for A-Q2, stated here, before any ladder number
appears below:**

- If rungs 1–2's marginal cost (dispatch + environment allocation, with or
  without parameter binding) exceeds rung 4's isolated per-operation
  arithmetic marginal (rung 4 − rung 3, divided by 2) by **more than
  roughly 3×**, allocation dominates and A-Q2 closes on **allocation**.
- If the reverse holds by more than roughly 3×, A-Q2 closes on
  **arithmetic**.
- If the two are within that band of each other, **the dichotomy was
  false**, and that closes A-Q2 too — with the finding stated as such,
  not as an inconclusive result.

The self-hosted interpreter runs the same eight rungs (`grammar/interp.planes`
under `interp.py`, via `execute-program` — the same pattern
`scripts/run_corpus_through_planes.py` uses) at `L=4` (`N=16`), 3 trials, for
the record only. It is metacircular — every cost below is paid twice over —
so its numbers are reported separately and never compared numerically
against the native figures.

---

## 2. The differential

`scripts/measure_library_differential.mjs`, 200 ticks, first 20 discarded
as JIT warm-up before computing medians (both arms' streams are still
checked for byte-identity across the full 200). All figures below are the
median of 5 independent runs of the script; the range across those 5 runs
is given alongside each, since at bloom's call density the total-per-tick
figure sits close to a noise floor (see below).

**Calls per tick: 140, constant across every tick sampled, in both arms** —
verified by the script (`CALLS_CONSTANT_ACROSS_TICKS=true`), so it is a
clean denominator for a per-call figure.

| Figure (JS, Node) | Median | Range across 5 runs |
|---|---|---|
| Library (bloom.planes) median ns/tick, total | 1,897,979 | — |
| Inline (bloom_inline.planes) median ns/tick, total | 1,929,479 | — |
| **Δ, total (library − inline)** | **−41,854 ns** | −96,938 to −12,521 |
| Δ as % of library, total | **−2.2%** | −5.2% to −0.7% |
| Per-call library overhead, total | **−299.0 ns/call** | −692 to −89 |

**The sign is not what naive expectation predicts, and the reason why is
the finding.** `tick` is rendered into the entry source's own prelude
(`composePrelude`, `js/paint/loop.mjs`), so the entry text differs every
tick and is never a cache hit — every real tick genuinely re-parses the
whole entry, in the shipped page exactly as here. A `use`d file's text does
not change tick to tick and IS cache-hit (`BrowserModuleLoader`'s
`astCache`). Splitting the parse from the execution (parsing each arm's
actual per-tick entry text directly, via `js/parser.mjs`, sampled over 30
post-warmup ticks) shows why:

| Figure (JS, Node) | Median | Range across 5 runs |
|---|---|---|
| Library parse-only median ns | 304,546 | 303,904–308,097 |
| Inline parse-only median ns | 382,596 | 374,813–382,739 |
| **Parse Δ (inline − library)** | **≈ +78,050 ns, ~25% larger to parse** | stable across all 5 runs |
| Library exec-only median ns (total − parse) | 1,585,475 | 1,568,179–1,604,264 |
| Inline exec-only median ns (total − parse) | 1,554,300 | 1,546,313–1,592,497 |
| **Exec Δ (library − inline)** | **+32,672 ns** | −24,318 to +57,951 |
| Per-call library overhead, exec-only | **+233.4 ns/call** | −174 to +414 |

Moving `draw.planes`'s helper bodies out of the entry and into a `use`d
library doesn't just organise the code — it changes what gets **re-parsed
every tick** (the entry, smaller in the library arm) and not only what gets
**called** (the library arm dispatches 140 more calls than the inline arm).
The parse-side saving is the larger and the far more stable of the two
effects at this call density; the call-side cost is in the direction naive
expectation predicts (positive in 4 of 5 runs, matching the ladder's rung
1–6 figures in magnitude) but noisy enough here that its sign alone is not
load-bearing — see §5 for why the ladder, not the differential, is the
clean source for that number.

---

## 3. The ladder

**JavaScript, Node `v22.23.1`, Apple M1 Pro.** Marginal = rung − control, at
the same `N`, per call.

| Rung | `N` | Median ns/call | Min ns/call |
|---|---:|---:|---:|
| 1 — noop | 622,521 | 279.3 | 278.7 |
| 2 — ident (param binding) | 546,121 | 386.2 | 382.0 |
| 3 — add1 (rational op + deriv) | 310,249 | 592.2 | 576.6 |
| 4 — add3 (3 arithmetic ops) | 278,784 | 876.0 | 851.0 |
| 5 — txt (derived, no gcd) | 438,244 | 490.2 | 488.6 |
| 6 — c (draw.planes circle body) | 146,689 | 1,407.6 | 1,344.7 |
| 7a — recur, depth 1 (2 calls total) | 158,404 | 1,565.3 | 1,549.5 |
| 7b — recur, depth 8 (9 calls total) | 32,761 | 7,185.1 | 6,853.2 |

Derived (JS): arithmetic marginal ≈ **141.9 ns/op** (median), 137.2 (min).
Rung 5 − rung 3 ≈ **−102.0 ns** (median), meaning `text of` (no gcd) is
*cheaper* than `x + 1` (gcd + derivation record) — see §5.
Depth 8 − depth 1 ≈ **5,619.8 ns** over 7 extra calls in the chain ≈ **803
ns/extra call** — squarely inside the 279–1,565 ns range rungs 1–7a already
establish for an ordinary call of similar complexity.

**Python `3.14.6`, Apple M1 Pro (same machine).**

| Rung | `N` | Median ns/call | Min ns/call |
|---|---:|---:|---:|
| 1 — noop | 81,796 | 1,996.3 | 1,985.0 |
| 2 — ident (param binding) | 67,081 | 3,093.0 | 3,061.1 |
| 3 — add1 (rational op + deriv) | 27,889 | 6,074.1 | 6,029.8 |
| 4 — add3 (3 arithmetic ops) | 20,164 | 11,037.2 | 10,930.5 |
| 5 — txt (derived, no gcd) | 51,529 | 4,292.6 | 4,242.2 |
| 6 — c (draw.planes circle body) | 14,400 | 14,543.4 | 14,508.3 |
| 7a — recur, depth 1 (2 calls total) | 14,161 | 15,857.7 | 15,559.1 |
| 7b — recur, depth 8 (9 calls total) | 3,600 | 74,486.4 | 73,792.8 |

Derived (Python): arithmetic marginal ≈ **2,481.6 ns/op** (median), 2,450.4
(min). Rung 5 − rung 3 ≈ **−1,781.5 ns** (median) — the same direction as
JS. Depth 8 − depth 1 ≈ **58,628.7 ns** over 7 extra calls ≈ **8,376
ns/extra call** — again inside the range (1,996–15,858 ns) rungs 1–7a
establish, not scaled up with depth.

**Self-hosted, for the record only (`interp.py` running
`grammar/interp.planes`, `L=4`, `N=16`, 3 trials — NOT comparable to the
figures above):**

| Rung | Median ns/call |
|---|---:|
| 1 — noop | 1,155,057 |
| 2 — ident | 1,515,289 |
| 3 — add1 | 1,726,818 |
| 4 — add3 | 2,424,664 |
| 5 — txt | 2,050,385 |
| 6 — c | 5,521,766 |
| 7a — depth 1 | 5,810,919 |
| 7b — depth 8 | 14,764,448 |

Roughly 580× the Python-native noop figure and roughly 4,100× the
JS-native one — interesting precisely because it pays every layer's cost
twice over (metacircular: the self-hosted interpreter is itself an
interpreted Planes program), not because it is a number to act on.

---

## 4. A-Q2 — allocation or arithmetic?

Applying §1's criterion, stated before these numbers were computed:

- **JS:** rung 1 (279.3 ns) vs. rung 4's isolated per-op arithmetic marginal
  ×2 (141.9 × 2 = 283.8 ns) — **a ratio of 1.02×.** Rung 2 (386.2 ns, +param
  binding) vs. the same 283.8 ns — **a ratio of 1.36×.** Neither exceeds
  the 3× band.
- **Python:** rung 1 (1,996.3 ns) vs. rung 4's isolated per-op arithmetic
  marginal ×2 (2,481.6 × 2 = 4,963.1 ns) — **a ratio of 2.49×**, arithmetic
  the larger side this time. Rung 2 (3,093.0 ns) vs. 4,963.1 ns — **a ratio
  of 1.60×.** Neither exceeds the 3× band either.

**A-Q2 closes on: the dichotomy was false.** In JS, allocation and
arithmetic sit almost exactly at parity (2 arithmetic ops cost almost
exactly one bare dispatch). In Python, arithmetic's per-operation cost is
somewhat larger than a bare dispatch — Python's rational-number arithmetic
(gcd normalisation, a Python-level function call per operation) costs more
relative to its own dispatch overhead than V8's does — but the two sides
remain within the same order of magnitude in both implementations, never
separated by the 3× that would make one number decide the call's cost on
its own. **The question presupposed one side would turn out to dominate;
neither does, in either implementation, and that is the answer.**

---

## 5. What this does not measure

**Rung 3 mixes rational arithmetic with the allocation of its derivation
record, and the ladder cannot fully separate them** — stated before the
numbers that bear on it, per the build prompt. Rung 5 (`text of`, a derived
value with no gcd) narrows the gap by comparison rather than closing it:
in both implementations, rung 3 is **markedly higher** than rung 5 (JS:
592.2 vs. 490.2 ns, +20.8%; Python: 6,074.1 vs. 4,292.6 ns, +41.5%) —
by §5.2's own stated rule, this means **gcd/rational-normalisation is a
real, measurable cost**, not merely the allocation of a derivation record
that a `text of` call would pay just as much of. Separating the two
exactly would need an interpreter build with derivation tracking disabled,
which is out of scope here and would change the thing being measured.

**The differential's total-per-tick figure is noisy at bloom's call
density.** 140 calls' worth of dispatch overhead (a few hundred
microseconds by the ladder's own per-call figures) sits close to the same
order of magnitude as run-to-run scheduler/GC noise on this machine, which
is why its sign varies across repeated runs (§2). The ladder's 200ms floor,
7-trial median/min protocol, and JIT warm-up discard exist precisely to
push a measurement's signal above that noise floor — the differential, by
design the cheaper and more "real" measurement, does not have that
protocol applied to it, and its exec-only per-call figure (233 ns, JS)
should be read as directionally consistent with the ladder's rungs 1–6
rather than as a second precise instrument.

**No rung was dropped for requiring an interpreter-file change.** All
eight ran through the ordinary program entry point with no interpreter,
parser, lexer, or analyser file touched.

---

## 6. Findings, not actions

**V-Q5's O(scope-depth) concern does not apply to recursion depth, and the
ladder confirms it empirically in both implementations.** `interp.py`'s
`Interpreter.call` builds each call frame's environment as `Env(fn.env)` —
`fn.env` is captured **once**, at hoist time, as the function's own
top-level definition environment (`interp.py:1181`, `js/interp.mjs:967`
mirrors it identically) — not as the *caller's* current environment. So
every call to a recursive function, at any recursion depth, sits exactly
two `Env.set` hops from a name declared outside it: its own local scope,
then that fixed top-level scope. Recursion depth cannot deepen the walk.
The ladder's rung 7 measures this directly rather than asserting it: dividing
the depth-8-minus-depth-1 delta by the 7 extra calls in the chain gives
**≈803 ns/call (JS)** and **≈8,376 ns/call (Python)** — both squarely
inside the range rungs 1–6 already establish for an *ordinary* call of
similar complexity, in their respective implementation. If assignment cost
scaled with recursion depth, the depth-8 chain's marginal cost would exceed
that range; it does not, in either implementation. **This closes the
carried-forward question from the sine build's report** (turtle recurses
to depth 8, bloom's `rings` to depth 10) **without finding a cost there** —
the concern would apply to nested `for each` loops or closures, which do
chain to the *enclosing* environment (`eval_foreach`'s `inner = Env(env)`,
not a fixed captured one), but not to recursive function calls.

**Modularising `draw.planes`'s helpers out of the entry source measurably
changes per-tick PARSE cost, not only per-tick CALL cost — and the parse
effect is the larger and more stable of the two at bloom's call density
(§2).** Every real tick re-parses the whole entry (because `tick` is
rendered into its own prelude), while a `use`d file's text is cached across
ticks. This is a genuine, load-bearing property of how a ticking program
pays for its own source today — worth recording as a fact about the
system, not as a change to propose. Whether anything should be done about
it — and if so, whether the answer belongs to the entry/prelude
architecture or to something else — is exactly the kind of question A-Q3
exists to adjudicate, and it is not decided here.

**Rational arithmetic (gcd normalisation) is a real cost, not merely
derivation-record bookkeeping**, confirmed in both implementations by the
rung 3 vs. rung 5 comparison in §5.

**The two implementations disagree on which side of A-Q2's dichotomy sits
closer to the other, but agree that neither dominates.** JS sits almost
exactly at parity; Python leans arithmetic by roughly 2.5×, still short of
the 3× threshold. Every figure in this report names its implementation for
exactly this reason — a single bare number from either language would have
told a different, and incomplete, story on its own.
