# REPORT — R3: Replay-on-Demand and Iterative `explain`

**Build:** `feat/replay-on-demand-and-iterative-explain`, branched from `main`
at `7541cef` (R2, PR #78).

---

## 1. SHA table

Captured via `git rev-parse HEAD:<path>` at branch time (before any edit in
this build landed):

| path | blob SHA | matches build prompt §2? |
|---|---|---|
| `interp.py` | `f9afde31ab3c1c8db9ee29eccdd81984b16df5bc` | yes |
| `js/interp.mjs` | `509ebb7787010bd63e70c5d8d1f28ccba1540afe` | yes |
| `host.py` | `89114cf010088485fae453349473535030998e43` | yes |
| `js/host.mjs` | `1839637104e0f021137138e4d9a8f47b0cfe092c` | **no — moved from `cdf48d5`** |
| `js/cli.mjs` | `af432fc5c06848a83e397fd022ab99e3e688ee0d` | (no SHA given; read at build time) |
| `test_retention.py` | `458d8c999779a09846f707f75b7ba5903a956c1a` | yes |
| `test_why_readable.py` | `ffd3936fd58cd2f983623faf34098f2a4d638036` | yes |

`js/host.mjs` moved since the build prompt was written — the prompt itself
flagged this as possible ("confirm the JS surface matches before relying on
snapshot symmetry; read at R3 build time if it moved") and it did. Read in
full at branch time: the required surface is still exactly seven (`ask`,
`read`, `write`, `show`, `clock`, `resolve`, `parseJson`) plus the optional
`record`/`snapshot` pair, matching `host.py` field for field. The file's own
header comment names why it moved — a prior build (C4) found `toJson` had no
caller and removed it, restating the seam claim at seven rather than
spending it. No drift relevant to this build.

## 2. Verified absence (S1)

```
$ git show 7541cef:interp.py    | grep -ic "def replay\|ReplayHost\|self.tracing\|trace=False\|effect_log"  -> 0
$ git show 7541cef:js/interp.mjs | grep -ic "function replay\|ReplayHost\|this.tracing\|effectLog"          -> 0
```

No trace mode, no replay driver, no effect log existed anywhere in either
interpreter at branch time. Confirmed, not assumed.

## 3. Rulings honored (binding on this build, per the build prompt's §1)

**Ruling 1 — no new host capability.** `interp.py`/`js/interp.mjs` gained a
`ReplayHost`/`ReplayHost` class — an ordinary second implementation of the
*existing* `Host` surface, the same seam `TestHost` already proves is real.
`host.py`/`js/host.mjs` were not touched. No `restore`/`recall` method was
added anywhere; `test_replay.py` asserts this directly (§6 below,
`test_seven_required_host_methods_unchanged_and_no_restore_added`). Replay
reconstructs by re-executing `steps` from the start on a fresh `Interpreter`,
never by asking a host to hand back a subgraph.

**Ruling 2 — the toggle lives in `mk`.** `Interpreter.mk`/`Interpreter.mk`
(Python/JS) is the only place either file reads the new `tracing` field.
Every one of the ~40 call sites that build a `Deriv` through `mk` — every
`eval`/`eval_binop`/`eval_foreach`/`builtin` arm in both languages — is
byte-for-byte unchanged. The one deliberate exception, made explicit rather
than left implicit (see §5 below), is that the in-language `Why` statement's
own `exec_stmt` case is *also* unchanged — R3 does not special-case it either,
for the same ruling.

## 4. What was built

**The tracing-off fast path (§3).** `Interpreter(..., trace=True)` — a new
constructor parameter, default `True`, so an unmodified caller's behavior is
identical to pre-build HEAD (invariant 2). Stored as `self.tracing`/
`this.tracing` (not `self.trace`/`this.trace` — that name was already taken
by the existing show/why observation log). `mk` checks it first, ahead of
even the generation stamp: when tracing is off, `mk` returns one shared,
never-mutated sentinel `Deriv` (`self._untraced`/`this._untraced`, built once
per `Interpreter` instance) instead of allocating a new node — no generation
is spent, no window check runs, no `Deriv` is allocated at all.
`Traced.value` still carries the real per-call value; only the provenance
graph is skipped.

**The effect log (§7).** A new `Interpreter.effect_log`/`effectLog` list,
populated by a new `log_effect(kind, target, result)`/`log_effect` method
called at each of the four host-effect call sites a program can trigger
directly — `show`, `write`, `ask`, `read` — right beside the existing
`maybe_record` call. Gated on the *existing* `record` toggle rather than a
third flag: a replay that needs this log requires the fast-path run to have
set `record=True`, exactly as `self.records` already does. `call_foreign` (an
arbitrary host function behind a `foreign` declaration) is **not** logged —
it is a claim against an unbounded host surface, not one of the five
required capabilities, and is out of R3's replay scope. This is a stated
scope decision, not a silent gap (§5 below).

**`ReplayHost` and `replay()` (§5, §6).** `ReplayHost` answers `ask`/`read`/
`write`/`show` by popping the next `(kind, target, result)` entry off a
recorded `effect_log`, asserting it matches what was expected, and returning
the recorded `result` — never touching the real world. `clock` and `resolve`
are refused outright (`clock` is never reached during replay because
`record=False`; `resolve`/foreign calls are outside R3's effect log,
documented rather than silently proxied to a real host). `parse_json` is
real, not replayed — it is pure computation over already-recorded text, not
a fresh effect.

`replay(steps, subject, window=None, effect_log=None)` builds a fresh
`Interpreter(host=ReplayHost(effect_log), window=window, trace=True,
record=False)` and re-runs `steps` (the same ordered list of source
snippets the fast-path run itself executed) from the start, then returns
`env.get(subject)`. Because Planes is deterministic and pure, and because
the replay `Interpreter` uses the identical `window` and reads back the
identical effect results in the identical order, its `mk` calls build the
identical `Deriv` graph, with the identical generation numbers, that an
eager (`trace=True`) run of the same `steps` would have built — including
sealing at the identical generation if the value's derivation is old enough
to cross a window (§5's "anchors at the seal's recorded generation" falls
out of re-execution; no separate mechanism reconstructs a seal specially).
The result is usable with `explain`/`why_tree`/`why_machine`/`origins`
exactly as an eager run's value would be.

**Iterative `approximations_in` (§4, ruled by the build prompt into this
build).** The one plain-recursive walk left in the why surface —
`explain`'s own body is a thin, already-shallow wrapper, but its call to
`approximations_in` walks the **full** derivation (not one layer) looking
for any approximate number anywhere in it, so a long unwindowed chain — the
exact shape `replay` reconstructs — could exceed the recursion limit past
roughly 450 steps in Python. Converted to an explicit stack, construction
order, matching `_cut`/`_seal`/`_why_next_stop`'s established iterative
idiom in both languages: a node is pushed once per reference but processed
(and its approximation, if any, recorded) only the first time it is popped
— `seen` gates at pop-time exactly as the recursive form gated at
call-entry, so dedup and result order are unchanged. `explain` itself
required no other edit. Verified at 1,000 unwindowed steps in both
languages (`test_replay.py`), and unchanged on every short chain
`test_why_readable.py` (untouched by this build) already pins.

**`_PY_CARD_TOO_DEEP` retired: kept, not removed.** `test_why_readable.py`'s
sentinel is left in place as a guard rather than deleted — the corpus-wide
comparison it protects still runs, and if any future change reintroduces a
recursive walk anywhere in the card path, the guard fires again instead of
the test suite silently passing on a divergence it can no longer see. It is
now, per §4's own acceptance, dead in practice: no corpus file's card hits it.

## 5. Scope decisions made and stated here (not left implicit)

**The `Why` statement is unchanged under tracing-off, and produces a
well-defined but uninformative card.** Ruling 2 says the toggle lives in
`mk` and the evaluator arms — including `exec_stmt`'s `Why` case — do not
change. Taken literally and followed: a `why` statement executed while
tracing is off still calls `explain()` on the untraced value. The shared
sentinel carries no per-call provenance, so the resulting text degrades to
`"<value> from nothing"` — never a crash, never a wrong VALUE (the value
itself is computed identically regardless of tracing), just an
uninformative derivation. `test_replay.py`'s
`test_why_statement_under_tracing_off_is_well_defined_but_uninformative`
characterizes this precisely. The §3 tracing-off/tracing-on output-equivalence
gate therefore excludes the handful of corpus files (5 of ~45) that call
`why` in their own source — a fast path is for a host that does not query
explanations from inside its own hot loop (a per-tick render loop, the
production shape this build targets); a program that wants an explanation
mid-run gets one correctly only via `replay`, on demand, which is what §5
actually builds. This was the one point in the build prompt genuinely
underdetermined by the two rulings given; the alternative (threading a
self-replay through `exec_stmt`'s `Why` case, reconstructing "everything run
so far, plus a prefix of the statement list currently executing") would
mean `Why` sprouting real tracing-mode awareness — exactly what Ruling 2
says not to do — for a shape (`why` mid-fast-path) the fast path's own use
case does not need. Flagged here for the architect to strike or confirm.

**`foreign` effects are outside R3's replay scope.** §7's own examples name
"a write, an ask, a show" — three of the four effects this build's
`effect_log` covers (plus `read`, the fourth of the five required host
capabilities). `call_foreign` goes through `host.resolve()` and an arbitrary
host function call, not one of the five effect methods, and is a *claim*
(§97: `"foreign-declaration"` anchor, not a witnessed `"host"` one) rather
than a witnessed effect. Logging and replaying an arbitrary host function's
raw return value was judged out of proportion to this build's scope; a
replay that reaches a `foreign` call refuses (`ReplayHost.resolve` names the
refusal), rather than silently re-invoking the real function. Named here,
not silently dropped.

## 6. Cross-language and gate — `test_replay.py`

19/19 passing. The build prompt's own N+3.2 table:

```
=== R3 verification gate (N+3.2) ===
  PASS  tracing-off == tracing-on for output/effects/records (§3/F1)
  PASS  eager-vs-replay byte-identity, Python and JS (§6/F2)
  PASS  effects performed once, never re-performed on replay (§7/F3)
  PASS  replay refuses on an unrecorded value (§7/F7)
  PASS  explain is iterative, no overflow at 1,000 steps (§4/F6)
  PASS  required host surface still seven, no restore (invariant 4/F5)
```

**Matrix actually run** (§6's own instruction to state it): each language's
own eager-vs-replay agreement (Python eager vs. Python replayed; JS eager
vs. JS replayed), plus the full cross-language square (Python eager vs. JS
eager; Python replayed vs. JS replayed) — four comparisons per scenario,
across six synthetic scenarios (a short and a long reassignment chain, a
windowed/sealed chain, a recursive function-call chain, and an effectful
chain mixing `ask`/`read`/`write`/`show` with reassignment). Python-eager
vs. JS-replayed and vice versa were not additionally added, per the build
prompt's own allowance — each language's eager-vs-replay holds, and the
existing cross-language `why` gate (`test_why_readable.py`, R2, unmodified
and still 13/13) already covers eager-vs-eager cross-language agreement, so
the two together imply the mixed case without a fifth redundant comparison.

The cross-language checks shell out to a new `node js/cli.mjs replay
<config-json>` subcommand (mirroring `retention`/`whytree`'s own pattern):
runs a `steps` sequence twice — once fast (`trace: false, record: true`),
once eager (`trace: true`) — from an identical fixture, then replays using
the fast run's own `effectLog` (or, with `forceRefusal: true`, an empty one,
to exercise §7/F7's named refusal cross-language on purpose) and reports all
three registers for both the eager and replayed value, plus the fast/eager
output and effects for §3's own equivalence check.

**§3's own corpus-wide check** (not only synthetic scenarios): every corpus
file that does not call `why` (see §5's scope note) is run twice, `trace=True`
and `trace=False`, and its output/effects diffed — a real "corpus of
programs" gate, in Python. §6's core gate stays scenario-based, like R1's
and R2's own core gates, for the same structural reason: `replay` needs a
named `subject` already bound in the running environment, which an
arbitrary corpus file does not reliably offer.

## 7. Full suite

- `.venv/bin/python3 -m pytest -q`: **1,362 passed** (including the new
  `test_replay.py`), 12 pre-existing collection warnings (unrelated —
  `TestHost.__init__`), 5 subtests, no failures.
- `test_retention.py` (R1, unmodified): **17/17**, unchanged.
- `test_why_readable.py` (R2, unmodified): **13/13**, unchanged.
- `node --test "js/test/*.test.mjs"`: **805/805**, unchanged (matches R1's
  own reported count exactly).
- `core_check.py`: clean — `grammar/interp.planes` and every module it
  reaches through `use` still conform to the declared core; port surface
  unchanged (all seven effect kinds, 29/32 keywords, 11/13 builtins).
- `audit_locked_vs_built.py`: clean — every locked construct still has code
  evidence in both implementations.
- `.venv/bin/python3 -m ruff check`: clean on every file this build touches
  or adds.
- `.venv/bin/python3 -m mypy interp.py test_replay.py scripts/measure_replay.py`:
  clean.

## 8. A mechanical consequence, not a language change

Same as R1's own §8: `grammar/errors.json` embeds each `raise
PlanesError(...)` call site's source line
(`"source": "interp.py:N"`). Adding `mk`'s tracing-off branch, `log_effect`,
and the `ReplayHost`/`replay` section (with its docstrings) above and around
existing raise sites shifted line numbers throughout the back half of the
file, so `grammar_gen.py --check` failed on line-number drift alone.
Regenerated (`.venv/bin/python3 grammar_gen.py`); `git diff
grammar/errors.json` touches only `"source"` fields — every tag, template,
and slot is byte-identical to what was on `main`. `grammar/rules.json` and
`grammar/vocabulary.planes` show no diff at all.

## 9. Benchmarks (N+3.4)

**Method.** `scripts/measure_replay.py`, mirroring
`scripts/measure_retention_window.py`'s own method exactly: reuses
`benchmarks/world_shape.planes`'s generator
(`scripts/measure_update_cost.py`'s `build_world_src_for`,
`count_reachable_derivs`) unmodified, at S=64, checkpointed at tick
1/100/300/600, each arm its own subprocess (avoiding one arm's allocator
state contaminating the other's timing). Two arms — traced (`trace=True`,
the pre-build/HEAD shape) and fast (`trace=False, record=True`) — plus a
third, separate subprocess measuring the cost of one `why`: given the fast
arm's own `effect_log` at tick=600, how long `replay()` + `explain()`
together actually take.

**Pre** (`reports/feat-replay-benchmarks-pre.md`, tracing on):

| tick | reachable `Deriv` count | wall time |
|---:|---:|---:|
| 1 | 275 | 7.574 ms |
| 100 | 9,086 | 278.074 ms |
| 300 | 26,886 | 865.975 ms |
| 600 | 53,586 | 1755.311 ms |

Fitted slope: **89.00 Deriv nodes/tick** (matching `REPORT_UPDATE_COST.md`
§5.4 and R1's own "unbounded" arm exactly — the same fixture, the same
count, a cross-check that this build changed nothing about the traced
path) and **2927.60 µs/tick** wall time.

**Post** (`reports/feat-replay-benchmarks-post.md`, tracing off):

| tick | reachable `Deriv` count | wall time |
|---:|---:|---:|
| 1 | 1 | 5.118 ms |
| 100 | 1 | 182.054 ms |
| 300 | 1 | 548.791 ms |
| 600 | 1 | 1091.566 ms |

Fitted slope: **0.00 Deriv nodes/tick** — the reachable count is 1 (the one
shared sentinel) at every checkpoint, regardless of how much history has
run: `mk` under tracing-off allocates nothing per node, exactly as §3
requires, and the acceptance criterion holds at the digit, not just in
proportion. Wall time falls to **1815.98 µs/tick**, a **~38% reduction**
per tick even though the interpreter still does everything else a tick
does (arithmetic, comprehensions, effect logging under `record=True`) —
the derivation graph was a real, measurable fraction of a tick's own cost,
not merely its retained memory.

**Replay cost of one `why`, at tick=600: 1768.794 ms** — essentially
identical to the traced arm's own full run to that checkpoint (1755.311 ms).
This is expected and is the whole point, stated as a number rather than a
claim: replay re-executes the entire program from the start, so it costs
what an eager run of that program costs — a **toll paid once, only when a
`why` is actually asked**, not a ceiling paid on every one of the (in this
run) 600 ticks that already happened. Extrapolated to a 30-minute soak at
60 ticks/second (108,000 ticks, the same extrapolation R1's own report
uses): the traced arm's per-tick overhead compounds to **316.17 s** of
extra wall time across the soak; the fast arm's compounds to **196.13 s**
of BASE interpreter work (the tick logic itself, unavoidable in either
arm) with **zero** additional graph-retention cost — and answering however
many `why`s were actually asked during that soak costs roughly one replayed
run's worth of wall time *each*, not a per-tick tax paid 108,000 times over.
This closes v28.0 §428's "toll, not a ceiling" claim with a number: the
toll, measured, is ~1.8 s per `why` at 600 ticks of accumulated history: the
ceiling it replaces, extrapolated, was 316 s and 9.6M retained `Deriv`
nodes over a 30-minute soak, paid whether or not anyone ever asked.

## 10. What this does not decide

The machine-export provenance bound (v29.0 §454 / v30.0 §476) is untouched
— architect's to schedule, as the build prompt names. The `_cut` RSS/CPU
optimization R1's own report named as a live cost (REPORT_RETENTION.md §6)
is untouched — a different track, not this build's. A-Q3 (persistent data
structures, structural sharing) remains open: this build operationalizes
its licence criterion (eager-vs-replay byte-identity, §6's gate) but builds
no optimiser and no persistent data structure, per the build prompt's own
instruction. Concurrency/Tier 5 stays untriggered — replay's correctness
here rests on single-threaded, deterministic re-execution, and nothing in
this build introduces anything that would break that. `tutor.html` (v26.0
§408) is untouched, as instructed.

R1 and R2's own surfaces (window, seal, generation, PIN, snapshot, the
three readable registers, aggregate folding) are unchanged — verified by
running their own unmodified test files, not merely by not having edited
them: `test_retention.py` still 17/17, `test_why_readable.py` still 13/13.

The scope decision in §5 (the `Why` statement's own behavior under
tracing-off) is the one item this report hands forward by name for the
architect to strike or confirm, per this build's own §475.1 allowance to
make a determinate ruling rather than defer, while still surfacing it
rather than treating it as settled beyond appeal.
