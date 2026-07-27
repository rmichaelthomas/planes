# PROBE_SELFHOST.md — the self-hosting sweep

**A probe sweep. It ships no production code.** Six earlier builds each
closed one defect and discovered the next; every one asked *what does this
component need*. This one asks the question for everything remaining at once:
what does `interp.planes` — the interpreter written in its own language —
require that the language does not yet give, measured across environment
lookup, structural traversal, string building, iteration, and function
representation, in one pass.

Deliverables: this report, `CORE_SUBSET.md`, and the probe scripts and
transcripts under `probe/selfhost/`. The diff touches no production file.

- **Method for every timing:** host-side `time.perf_counter`, because Planes
  has no wall-clock builtin (the same method `scripts/measure_association_idiom.py`
  established). Machine and Python version are printed at the head of each
  transcript. Every number here is a measurement; none is estimated.
- **Method for every capability verdict:** a probe program and its verbatim
  result. Transcripts live in `probe/selfhost/transcripts/`.

---

## §0 — Baseline and the `interp.py` reading

**Baseline (all green, unchanged by this build):** 637 tests passing across
the `test_*.py` suite; `ruff`, `mypy` (55 source files after the probe
scripts), `audit_locked_vs_built.py` (no drift), `grammar_gen.py --check` (up
to date). Counts confirmed in `grammar/vocabulary.json`: **32 keywords / 8
builtins / 7 effect kinds**. HEAD `135ecb4`; branch `probe/selfhost-sweep`.

**The `interp.py` reading (§0 step 5 — a deliverable, never done in this
planning chain).** `interp.py` is 1154 lines. It is what `interp.planes` must
eventually reproduce. Its shape:

- **A tree-walking evaluator with hand-written `isinstance` dispatch.** Two
  dispatchers carry the language: `exec_stmt` (~12 statement kinds: `Use`,
  `Foreign`, `Rule`, `Note`, `FuncDef`, `Assign`, `Give`, `Show`, `Why`, `If`,
  `When`, `Fail`) and `eval` (~20 expression kinds). Two more dispatch on
  strings: `eval_binop` (`and`/`or`/`first`, else `apply_op`) and `builtin`
  (the 8 builtin names). No visitor, no dict dispatch — a linear `if
  isinstance(...)` chain, 35 `isinstance` sites in the two main methods.
- **Every value is a `Traced(value, Deriv)`** — provenance travels alongside
  the value, as a derivation-graph node. This is the `why` machinery.
- **The environment is a mutable Python `dict` chain** (`Env.vars` +
  `Env.parent`); `get` walks outward, `set` mutates in place.
- **User functions are already inert data:** `Function(name, params, body,
  env)` — an AST body plus a captured defining environment. `invoke` binds
  params in a fresh `Env(fn.env)` and execs the body.

**What `interp.py` does that Planes has no obvious way to express** — the
largest known unknown this build was built to answer:

1. **Non-local control flow via host exceptions.** `give` (return) is a Python
   `_Give` exception; error propagation and `or fail` ride `PlanesError`;
   depth exhaustion is a caught `RecursionError`. Planes has `or fail as` but
   no `give`-as-exception and no general throw/catch. A self-hosted `eval`
   must express return and error propagation by **threading a result/status
   record forward**, not by unwinding a stack.
2. **A mutable, in-place environment.** `Env.set` walks the parent chain and
   *mutates* `scope.vars[name]`. Planes has no mutable dict and no in-place
   mutation; records and lists are immutable. The environment must become the
   **association idiom** (Phase 1), rebuilt rather than mutated.
3. **`isinstance` type dispatch over ~20 node classes.** Planes has no
   `isinstance` and no "what type is this record". The substitute is
   `when…is` shape dispatch (Phase 2) — 32 arms where `interp.py` has 32
   isinstance cases.
4. **Host libraries** — `urllib`, `json`, `unicodedata`, `os` — are the
   `foreign`/host boundary by design, not a language gap. `interp.planes`
   delegates them to a host exactly as `interp.py` does.

The number model (`planes_num`), being native, is not a gap. Points 1–3 are.

**Cross-cutting: the recursion ceiling is exactly 140, measured
(`transcripts/phase0_recursion_ceiling.txt`).** A self-calling countdown
succeeds at depth 140 and raises `recursion-too-deep` at 141. This is not a
Phase-4-only concern: a recursive-descent `eval` written in Planes spends
Planes-level frames per AST level, so **the usable interpreted-program depth
is a fraction of 140** — the deepest structural risk the sweep surfaces (see
REPORT_SELFHOST_SWEEP.md).

---

## §1 — Phase 1: environment lookup at interpreter scale

**Probe:** `probe/selfhost/phase1_env_lookup.py` ·
**Transcript:** `transcripts/phase1_env_lookup.txt`

An interpreter resolves a name on every reference. `interp.py` uses a mutable
dict; `interp.planes` cannot (no mutable dict; no computed-key record access),
so it must use the association idiom: a list of `{name, value}` records
scanned by `for each … where`.

**(1) Flat lookup, seconds per lookup** (median of 400, half hits/half misses;
no early exit, so O(n) either way):

| entries | s/lookup |
|--:|--:|
| 10 | 0.0000317 |
| 50 | 0.0001345 |
| 200 | 0.0005183 |
| 500 | **0.0013028** |

The carried figure (~1.3 ms at 500 entries) is **CONFIRMED**: 0.00130 s. Cost
is linear in entries.

**(2) Nested scopes** (a miss walks outward through every frame, 20 bindings
each): 3 frames 0.000166 s, 5 frames 0.000273 s, 10 frames (200 total) 0.000543 s
— essentially identical to the flat 200-entry cost (0.000518 s). **The chain
structure adds nothing; cost is total-entries-walked.**

**(3) Rebinding** — `plus` (append a binding) and `with` (update a field), at
env scale: **~3–4.6 µs, nearly flat to 500** (`plus` 500 → 0.0000037 s; `with`
500 → 0.0000046 s). Two-to-three orders of magnitude cheaper than a lookup at
the same scale.

**The mechanism, and the phase's real answer.** Lookup is a Planes-level `for
each` — every entry pays the interpretation tax. Rebinding is a single
Python-level copy (`base.value + [item]` / dict merge) — one step regardless
of size. That asymmetry is why "an interpreter rebinds constantly" is the
wrong worry: rebinding is cheap; **the scan is the cost**.

**Projection to a lexer.planes-sized program** (564 lines, ~3835 tokens;
each `Var` = one lookup), total seconds of pure name-resolution:

| env size | 500 refs | 2000 refs | 8000 refs |
|--:|--:|--:|--:|
| 10 | 0.016 | 0.063 | 0.25 |
| 50 | 0.067 | 0.27 | 1.08 |
| 200 | 0.26 | 1.04 | 4.15 |
| 500 | 0.65 | 2.61 | **10.42** |

**Verdict (with numbers).** `unbound` §42 (optimize below the visible line) is
**adequate up to an environment of ~50 entries** — a lexer-sized program then
resolves in well under a second even at thousands of references. It stops
covering it at **N ≈ 200 flat entries**: at 200 entries × 2000 refs the cost
is ~1 s, and at 500 entries × thousands of refs it is 3–10 s — visible, and
forced entirely by whether the interpreter flattens all bindings into one
list. A **scoped** environment (small local frames, the global frame consulted
only on a miss) keeps the working set small and stays under the line; a
**flat** environment does not. The language answer §42 defers is therefore not
"make lookup faster" but "keep scopes small" — a design constraint on how
`interp.planes` structures its environment, not a new construct.

---

## §2 — Phase 2: generic structural traversal

**Probe:** `probe/selfhost/phase2_traversal.planes` ·
**Transcripts:** `transcripts/phase2_absence.txt`, `transcripts/phase2_dispatch.txt`

**Can a Planes function act on an arbitrary record without knowing its
fields? No — genuinely absent.** `for each f in record` raises
`not-a-collection: cannot loop over {record}`. No builtin enumerates fields
(the 8 are `count lower upper text whole ask read normalize`). Computed field
access `r.[k]` does not exist by design (a field name must be a literal known
when the source is written — `demo/association.planes`'s own comment).

**Can `when…is` shape dispatch substitute? Yes.** `phase2_traversal.planes`
dispatches on AST-node-shaped records the way `eval` dispatches with
`isinstance`, matching the discriminating field and binding the rest:
`describe of num → "a number: 7"`, `op → "an operator: +"`, `var → "a
variable: x"`, unknown-kind → the final `else`.

**How many shapes before it is unmanageable? 32 — the AST node count.**
`lexer.py` declares 33 dataclasses; one is `Token`, leaving **32 AST node
kinds**. The Python walkers already hand-dispatch exactly this many:
`render.py` has **32** `isinstance(node, …)` cases, `interp.py`'s `eval`/`exec_stmt`
**35**, `shapes.py` **62** (it walks nodes in several passes). These files are
maintained at that case count today.

**Is field enumeration a gap, or is hand-dispatch the correct answer?
Hand-dispatch is correct — and it is forced.** Two independent reasons:

1. #13's standing instruction (a new AST node is not added until every
   exhaustive dispatch has a *case*, never a safe fallback) makes explicit
   per-kind dispatch a **feature**: the compiler-of-record for "did you handle
   the new node?" is the set of dispatch sites, and enumeration would erase
   exactly that check.
2. `render.py` demonstrates 32 hand-written cases are maintainable. A
   `render.planes` would carry ~32 `when…is` arms — the same shape, one arm
   per kind.

**One honest caution.** A `when…is` ladder *can* degrade to a final `else`
safe-fallback (my probe's last arm) — which #13 forbids. Planes has no
compile-time exhaustiveness check that every node kind has an arm; the
discipline is enforced by review, not by the language. If self-hosting wants
#13's guarantee mechanically, *that* — an exhaustiveness check over `when`
ladders — is the real gap, not field enumeration.

---

## §3 — Phase 3: string building at renderer scale

**Probe:** `probe/selfhost/phase3_string_building.py` ·
**Transcript:** `transcripts/phase3_string_building.txt`

**Is there a join? No. That absence is the finding.** Every `.join` in the
codebase is Python's (`interp.py:1090,1105,1140`, `lexer.py`, `parser.py`).
The 8 Planes builtins contain none that folds a list of fragments into a
string. The only string-building tool is `+`, and `+` on two strings copies
both (`apply_op: return a + b`).

**(1) Building a string by repeated `+`** (seconds, and µs/byte):

| bytes | seconds | µs/byte |
|--:|--:|--:|
| 1 024 | 0.0005 | 0.52 |
| 10 240 | 0.0021 | 0.20 |
| 102 400 | 0.154 | 1.51 |
| 204 800 | 0.344 | 1.68 |
| 409 600 | **1.253** | 3.06 |

**It is O(n²), measured.** At large sizes a ×2 in size gives ~×3.6 in time and
µs/byte roughly doubles — the signature of a per-byte cost that grows linearly
with n. Building a 400 KB string via `+` costs 1.25 s.

**(2) The list-of-fragments idiom does not escape it.** Accumulating fragments
with `plus` then collapsing them is the *same* quadratic, because there is no
join — the collapse is another `+`-loop (100 KB: 0.128 s to collect + 0.074 s
to collapse). And `plus` in a growing loop is *itself* O(n²) (each append
copies the growing list) — the collect column is quadratic too. **Both
incremental string-building and incremental list-building are quadratic**; the
cheap-single-op result from Phase 1 does not survive being run n times.

**Verdict.** `render.py` renders whole files; a `render.planes` building its
output by `+`/`plus` inherits the quadratic. §42 **covers it up to ~tens of
KB**: a lexer.planes-sized canonical source (~15–20 KB) renders in single-digit
ms (between the 10 KB = 2 ms and 100 KB = 154 ms rows, nearer the former). It
stops covering it around **100 KB (>0.15 s, visible)** and becomes a wall by
**~400 KB (>1 s)**. The language answer §42 defers is a **join** (fold a list
of fragments in one O(n) pass) — the single most load-bearing absence Phase 3
found.

---

## §4 — Phase 4: bounded and unbounded iteration

**Probe:** `probe/selfhost/phase4_fixpoint.planes` ·
**Transcript:** `transcripts/phase4_fixpoint.txt`

**Confirmed by SEARCH, not assumption (Phase 4 step 1).** The 32 keywords are
`to give let use show write why if else for each in where when and or not of
as fail with plus foreign from doing true false nothing first round places
rule` — **no `while`, no `repeat`, no `until`, no `loop`, no `times`, no
`range`.** `[1..5]` is a syntax error. The only iteration is `for each … in
<collection>`. (`in` *does* work as a membership operator — `2 in xs` → true.)

**How `shapes.py` does its fixed point** (`analyse_prog`, lines 337–360): a
monotone `while changed:` loop that grows each function's effect set until no
round changes anything; it terminates because effect sets only grow and the
vocabulary is finite (7 kinds), and the round count is bounded by the number
of functions. The iteration count is **data-dependent** — not a collection
`for each` can walk.

**Can a fixed point be expressed at all today? YES — via recursion.**
`phase4_fixpoint.planes` computes a transitive closure: one growth round is a
`for each` over the edges (the collection you *do* have), and the outer "repeat
until stable" is a self-call that stops when a round adds nothing. Result:
`reachable count: 5` over a 4-edge chain — a genuine monotone fixpoint. The
recursion depth equals the **round count**, so it works while a program
converges in under ~140 rounds (the measured ceiling). For `shapes.py`'s
fixpoint the rounds are bounded by the function count, so small and medium
programs are fine; a very large one is not.

**What `shapes.planes` would require:** nothing new for the round itself (a
`for each` over the functions). Only the outer *repeat-until-stable* needs
either recursion (works to ~140 rounds) or a new construct (to exceed it).

**Costed candidates — costed, not chosen.**

| candidate | what it costs |
|---|---|
| **`repeat … until <cond>`** (new reserved word) | Breaks the 32-keyword ceiling (`test_names.py` enforces it). Needs parser support for a body + condition, and — because Planes is immutable — a **state-record-threading** model so the loop carries state forward and returns it. Semantically it is sugar over the recursion already possible, but it **escapes the ~140 ceiling**. Cleanest fit for data-dependent iteration. |
| **`for each n times` / bounded range** | Needs a range (absent) or a `times` reserved word (breaks the ceiling). A bounded loop is only a *safe approximation* when a convergence bound is known (for the fixpoint, the function count is such a bound) — you iterate the bound and no-op after convergence, wasting rounds. Still needs immutable state threading. Does not naturally express "until stable". |
| **fixpoint builtin** (`fixpoint of f from seed`) | A 9th builtin (**Invariant 2 forbids builtins reaching 9 this build**), and it requires **first-class functions as arguments** — which Phase 5 shows do not exist. Most powerful (expresses "until stable" directly), most invasive. |

The candidates answer "escape the ceiling for large fixpoints", not "enable
fixpoints at all" — recursion already enables them up to ~140 rounds.

---

## §5 — Phase 5: closures and first-class functions

**Probe:** `probe/selfhost/phase5_closures_as_data.planes` ·
**Transcripts:** `transcripts/phase5_absence.txt`, `transcripts/phase5_closures.txt`

**Can a record hold something callable, called back out? No — functions are
not first-class.** `r = { f: double }` raises `wrong-arity: 'double' takes 1
value, given 0` — a bare function name is a zero-arg *call*, not a reference.
`r.f of 3` is a syntax error — a call names a literal function, never an
expression. Functions cannot be stored, passed, or called indirectly.

**Can an interpreter represent user functions as inert data and apply them by
interpretation? YES — and it works end to end.**
`phase5_closures_as_data.planes` is a miniature interpreter: `eval-expr`
dispatches an expression AST (`lit`/`var`/`add`) by shape under an
association-idiom env; a *closure* is the record `{ param, body, env }`;
`apply-closure` binds the parameter on top of the **captured** env and
interprets the body. Results:

- `add5` (a closure) **stored in a record field, retrieved, and applied to 10
  → 15** — a closure survives storage and retrieval, which the
  direct-function-value path forbids.
- `add5 of 100 → 105`, `add20 of 3 → 23` — **distinct captured `n`** proves it
  closes over its defining scope.

This is exactly how `interp.py` already represents functions (`Function =
params + body + env`). **Phase 5's answer: `interp.planes` needs no new
construct for functions — the inert-data-plus-interpretation representation is
built entirely from records, recursion, and `when…is`, all already core.** The
phase's own hypothesis ("that is probably the real answer") is confirmed.

**Discovered rough edge (not fixed here — this build fixes nothing).** A
multi-line record or list literal parses at the top level but **breaks inside
an indented function body** (`transcripts/phase5_closures.txt` context; repro
in the report). Writing `interp.planes`/`render.planes` — which construct
deeply nested AST records — will require keeping each literal on one line
inside function bodies, a real ergonomic cost. Logged for the architect.

---

## §6 — Phase 6: the core subset, derived

Full derivation is in **`CORE_SUBSET.md`**; inventory transcript at
`transcripts/phase6_inventory.txt`.

Mechanically tokenizing `grammar/lexer.planes` + `grammar/parser.planes` (1682
lines, the two largest Planes programs) with the language's own lexer: **22 of
32 keywords used, 3 of 8 builtins, 0 of 7 effect kinds.** The unused surface —
`let show write why with foreign doing round places rule`, five builtins, all
seven effect kinds — is the first evidence of what is not core. Adding what
Phases 1–5 require adds essentially one borderline (`with`). §127's prediction
that the `note:`/`because:` planes, the record plane, `rule`, and `foreign`
are not core is **CONFIRMED** by the inventory. The core is about **half** the
named language and **none** of its effects. `CORE_SUBSET.md` §5 sketches (does
not build) the conformance checker.

---

## §7 — Consistency invariants (held)

1. **No production file changed.** `git diff main --stat` touches only
   `probe/selfhost/`, `PROBE_SELFHOST.md`, `CORE_SUBSET.md`, and the session
   report. No `.py` outside `probe/` in the diff.
2. **Counts unchanged: 32 / 8 / 7.** This build proposes; it adds nothing.
   `rest of xs` (§130) is **not** implemented here — builtins stay at 8.
3. **Test count unchanged at 637.** Probes are run, not asserted.
4. **`ruff`, `mypy`, `audit_locked_vs_built.py`, `grammar_gen.py --check`
   clean** — including the new `probe/selfhost/*.py`.
5. **Every measurement is a measurement** — method (host-side `perf_counter`)
   and environment (macOS arm64, CPython 3.14.6) stated per transcript.
6. **Every capability verdict carries its transcript** — the probe program and
   its verbatim result, under `probe/selfhost/transcripts/`.
