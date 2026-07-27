# REPORT — S3d, `interp.planes` Build 3: Effects, the Host Boundary, and Route B Closed

**Branch:** `feat/interp-planes-effects` · **Base:** `main` at `f5c702b`
**Suite:** 849 passed · **Counts:** 32 / 10 / 7 / 8 · **`host.py`:** untouched (`git-blob 5ee27f9d`)

When this lands, `lexer.planes → parser.planes → interp.planes` is a complete
self-hosted Planes implementation. What remains to get off Python is a **second
host**, not more language.

---

## What shipped, phase by phase, against §A

| Phase | Shipped | Against |
|---|---|---|
| 1 | The mode tag and the effect boundary; `show` in both modes | A.1 |
| 2 | Output effects — `show`, `write` — in both modes, agreement in inert | A.1 |
| 3 | Input effects — `ask`, `read`, `clock`, `random`, `env` — deterministic in inert | A.2 |
| 4 | `foreign` declarations resolving with declared effects; the four programs | A.2, A.7 |
| 5 | The effect surface: `shapes` on `interp.planes` reports all seven | A.3 |
| 6 | The core-conformance checker, wired into `scripts/ci.sh` | A.4 |
| 7 | Re-measurement, self-hosting, Route B assessed | A.5, A.7 |

The derivation slot stays `nothing` throughout (A.6); dispatch is flat `if …
give` with **zero `when` statements** in `interp.planes` (A.6); `Traced`/`Deriv`
in `interp.py` and all of `host.py` are untouched (invariant 4).

---

## The boundary: how the mode tag works, and what `"inert"` made testable

The interpreter's configuration — the mode tag and, in inert mode, the supplied
input tables — rides in one `io` record together with the output accumulator
(`log`). **That record is carried as a reserved `__io__` binding in the
environment**, so it threads exactly as every binding does (Rule 4: the env
rides in the status record). The consequence is the load-bearing one: wherever
the environment threads correctly — which build 2 already exercises through
lists, operators, calls, branches, and loops — the effect log threads with it,
and an effect and a binding "happen" at the same threaded moment. A
sub-expression's effect is never lost because effect propagation is *identical
to* the environment propagation build 2 already tests. The only two seams that
cross a function boundary are `apply-function-node` (inject the caller's io into
the callee) and `run-body` (carry the callee's io back out).

Dispatch is flat on the tag (A.1): `if io.mode == "inert": give <data>` else
perform. **No record of callables anywhere** — `io` holds only data (lists of
`{path, body}` / `{url, value}` / `{name, value}`), and dispatch is on the mode
string, never a stored function (A.1, failure mode 1 avoided).

**What `"inert"` made testable that would otherwise have needed real effects:**
every agreement test. A program that writes a file, asks a url, reads the clock,
or draws a random number is checked against `interp.py` (run under `TestHost`)
on the whole ordered `(kind, target)` effect sequence — without either side
touching the filesystem, the network, or the real clock. `test_all_seven_
effect_kinds_in_one_inert_program_agree` runs all seven in one program and the
sequences match exactly. The one delicate seam (an effect inside a function
body surviving into the caller's log) has its own test.

---

## Phase 5's surface, reported exactly — the prediction held

`shapes` on `grammar/interp.planes`:

```
ask      network  {computed}
clock    ambient  time.time
env      ambient  os.getcwd
random   ambient  random.random
read     file     {computed}
show     console  {computed}
write    file     {computed}
```

**All seven kinds. None missing, none unexpected. A.3 HELD.** The four
first-class effects are `{computed}` (the interpreter reads/writes/asks wherever
the interpreted program names), the three ambient effects carry the host targets
of `interp.planes`'s own `host-clock` / `host-random` / `host-getcwd` foreigns.
This is soundness taken to its limit and precision to zero, exactly as A.3
argued: an interpreter performs whatever the program it runs performs, so its
static surface is everything.

- **The analyser stays total over the interpreter** — a `Surface` out, no raise.
- **`origins_of` works across it:** `ask`←`url`, `read`←`path`, `show`←`shown`,
  `write`←`dest`; the ambient targets are host names with no origins.

A refutation would have been the more valuable result (A.3, §PROVENANCE). It came
out exactly as predicted, on the first real interpreter — which is itself worth
recording: the prediction was made before any of this existed and survived
contact with the artifact unchanged.

---

## The core's real size — the port surface for a second host

`core_check.py` (modelled on `audit_locked_vs_built.py`, inverted) confirms
`interp.planes` uses nothing outside the declared core (`grammar/core.json`),
reusing the language's own `lexer.tokenize` and failing closed. **It conforms
(exit 0)** and is wired into `scripts/ci.sh`. The measured core:

| | Core | Full | Excluded |
|---|---|---|---|
| keywords | **28** | 32 | `let`, `rule`, `when`, `why` |
| builtins | **10** | 10 | — |
| effect kinds | **7** | 7 | — |

**This is much larger than `CORE_SUBSET.md`'s "half the keywords, three
builtins" prediction, and it is the single most useful figure this build
produces:** a second host must implement 28 keywords, all 10 builtins, and all 7
effect kinds to run `interp.planes`. The prediction was too small because it was
derived from two *pure* programs (the lexer and the parser); an *interpreter*
uses nearly the whole language to implement it — it delegates every builtin to
the host (so all ten are core, not three), and it needs `round`/`places`,
`first`, `foreign`/`doing`, and the rest to reproduce the constructs it
interprets.

### Did `with` survive confirmation? Yes.

`with` is used at `interp.planes:1251` (the io update, `io with log: …`) — the
canonical state-record-threading case `CORE_SUBSET.md §4` predicted. It stays in
the core, the one prediction-justified member discharged. A side finding:
`parser.planes:2265` already uses `with` (`attach with annotation: …`), so
`CORE_SUBSET.md`'s "the grammar programs use it zero times" was wrong *before*
`interp.planes` existed.

---

## The runnable corpus count, and the blocking construct for each remaining

**RUNNABLE 26 / 28** build-1+2 programs (up from 24), through all three Planes
stages, zero divergences.

- **`demo/fdiff/v1.planes`, `v2.planes`** moved from BLOCKED to RUNNABLE. They
  call a foreign whose target (`mylib.post`) the host cannot load. `interp.py`
  refuses it (`foreign-not-found`); `interp.planes` refuses it
  (`foreign-needs-host`). Both refuse to run a foreign the host cannot provide,
  with matching output up to the refusal — that is agreement, and the boundary
  now behaves as `interp.py` does.

Two remain BLOCKED, each named with its exact cost (A.7):

- **`foreign.planes`** — arbitrary host-function resolution. It uses
  `builtins.sorted/max/min`, which `interp.py` resolves for real.
  `interp.planes` cannot: it has **no dynamic `host.resolve`**, and that is the
  one remaining build-3 boundary — the second host's single non-effect method
  (`host.resolve` / `importlib`). The effect surface itself is closed: with the
  pure results supplied, an inert run agrees on the effect log and output
  (`test_foreign_pure_result_supplied_matches_the_real_builtin`). A secondary
  gap in the same file is `why spread` — provenance, deferred with the `deriv`
  slot (A.6).
- **`probe/parser/cursor_scales.planes`** — `recursion-too-deep`. Interpreted
  recursion (32) is shallower than the host's; A.7 says accept it, name it, do
  not raise. A next-build finding, unrelated to effects.

---

## Can Planes parse JSON without a host? No.

`interp.py`'s `ask` returns parsed JSON (`host.parse_json` then `from_foreign`).
Reproducing it exposed the one place the host boundary is irreducible:
**Planes has no JSON parser, and no runtime type probe, so `interp.planes`
cannot re-wrap a host-parsed value into its tagged value model on its own.** In
real mode `ask` returns the result's text form (the fetch happens, the shape
flattens); in inert mode the supplied response is already a tagged value, which
is *why* inert is the tested path. The answer belongs in the report either way
(A.3, Phase 3): parsing and type-detecting a value at the boundary is a host
capability, not a language one — the same lesson `host.py`'s `parse_json` /
`to_json` already record, now confirmed from the interpreter's side.

---

## §7 measurements, as numbers, re-established with effects present

Python 3.14.6, `recursionlimit` 1000. Every number re-measured this phase, never
carried (A.7's opening note).

| Measure | Build 2 | Build 3 | Note |
|---|---|---|---|
| Host recursion ceiling (`if`) | 245 (4 fr/call) | **245** | a CPython property, unchanged |
| Host recursion ceiling (`when`) | 196 (5 fr/call) | **196** | unchanged |
| Interpreted **recursion depth** | 32 (35 fr/call) | **32 (35 fr/call)** | **unchanged — the io threading cost zero frames on the spine** |
| Interpreted statement nesting | 33 | **33** | unchanged |
| Interpreted expression nesting | 139 | **139** | unchanged |
| Full pipeline nesting | 23 | **23** | parse-bound, unchanged |
| Env at recursion depth | 2 | **4** | +2 (the `__io__` effect config), **constant to depth 120** |
| Env at a 60-deep call chain | 62 | **63** | +1 (`__io__`), constant per chain |

**A.5, honored.** Effects were added and interpreted recursion depth did **not**
move — the accumulator rides in the environment, which already threads, so it
added no frame to the `eval-node → … → run-body` spine. The environment gained a
constant two bindings (the effect config) and still does not grow with call
depth (invariant 6). Nothing was trampolined, restructured, or raised.

---

## All three self-hosting assertions still hold

Verified by the self-hosting suite (35 tests) and `parser_corpus_agreement.py`
(31/31, `interp.planes` included):

1. **`lexer.planes` self-tokenizes** — the Planes lexer tokenizes its own source,
   agreeing with `lexer.py`.
2. **`parser.planes` self-parses** — agreeing with `parser.py`.
3. **`parser.planes` parses the interpreter** — `interp.planes` (now ~1400
   lines, +effects) parses to **117 top-level nodes**, agreeing with `parser.py`.

**Can `interp.planes` interpret a program that uses all seven effect kinds, end
to end, in `"inert"` mode with agreement against `interp.py`? Yes** — a single
program performing `show`, `read`, `ask`, `write`, `clock`, `random`, and `env`
runs through all three Planes stages and its whole effect sequence matches
`interp.py`'s (`test_all_seven_effect_kinds_in_one_inert_program_agree`).

---

## Where `interp.py`'s effect behaviour was harder to reproduce than expected

- **`clock`/`random`/`env` have no execution path of their own.** They are
  foreign-only — there is no `clock` statement or builtin; `interp.py` reaches
  them solely through `foreign … doing clock`. So Phase 3's "input effects"
  could not be built without the *foreign* machinery (Phase 4's nominal
  subject), which is why foreign landed in Phase 3.
- **Real-mode `write` needs the raw value, not the tagged one.** `interp.py`
  writes `to_json(value)`; `interp.planes`'s value is `{ kind: "number", value:
  5 }`. `unwrap-value` bridges it so the outer host serialises `5` — byte
  identical to `interp.py` (asserted). A record cannot be rebuilt with runtime
  field names in Planes, so a real-mode record write falls back to canonical
  text; the inert path never needs it.
- **`ask`'s JSON parse** — see above; the irreducible host capability.
- **The module check is the interpreter's, and the host's, twice.**
  `interp.planes` tracks the interpreted program's `use file`/`use http`
  (`io.modules`) *and* must itself declare `use file`/`use http`, because in
  real mode it performs those effects on the outer host, which checks *its*
  modules. Two module checks at two levels for one effect.

---

## §A premises at baseline

Every §A premise survived baseline. The one that needed care was A.2's split of
`clock`/`random`/`env` from `foreign` — the prompt lists them as Phase 3 input
effects and `foreign` as Phase 4, but they are foreign-only, so the mechanism
had to be built in Phase 3. Resolved toward §A's evident intent (failure mode
10): the code is one foreign path, the phases are a reporting split.

---

## What this build disproved about this prompt

**Never empty** (§PROVENANCE). Build 1's entry: the load-bearing unknown was the
wrong *component*. Build 2's: a performance note was a semantic divergence.
Build 3's:

**`CORE_SUBSET.md`'s core was wrong in two directions at once, and this prompt
inherited it as settled.** A.4 asked to *confirm* `with` and *confirm* the seven
effect kinds — framed as tidy discharges of a proposal. The proposal was wrong
where it was most confident:

1. It ruled **`when`** into the core as "the *only* substitute for the absent
   `isinstance`" — the strongest justification any construct had. `interp.planes`
   dispatches with flat `if k == "Num"` on the node kind and uses **zero**
   `when`. The one construct declared indispensable is unused.
2. It put the builtins at "three or four of ten." `interp.planes` uses **all
   ten**, because a metacircular interpreter delegates every builtin to the
   host. The port surface is not "half the keywords and three builtins"; it is
   **28 of 32 keywords and all ten builtins** — nearly the whole language.

The prompt treated the core as a thing to *check off*. It was a thing to
*measure*, and the measurement moved it by more than a factor of two. The A.4
framing ("confirm `with` is used, or remove it") anticipated the small
corrections and missed the large one — that a core derived from two pure
programs underestimates an interpreter's port surface by the entire margin that
matters to a second host.

---

## Route B, assessed

**The self-hosted stack is complete.** `lexer.planes → parser.planes →
interp.planes` tokenizes, parses, and *runs* Planes programs — expressions,
statements, control flow, lexical scoping, recursion, failure, and now all seven
effect kinds through a host boundary — checked at every stage by agreement with
the Python reference. 26 of 28 corpus programs run identically through three
Planes stages; the two holdouts are named (host-resolve, recursion depth), and
neither is a language gap.

**What remains before a second host could run it — scoped against the measured
core:**

A second host must implement, to run `interp.planes`:

1. **The 28 core keywords, all 10 builtins, all 7 effect kinds** — the port
   surface `core_check.py` measures and pins. This is the language surface; it
   is fixed and enumerated.
2. **The eight `host.py` methods** — `ask`, `read`, `write`, `show`, `clock`,
   `record`, `resolve`, plus the JSON boundary (`parse_json`/`to_json`). Of
   these, **`resolve` (dynamic foreign loading) is the one thing `interp.planes`
   itself cannot stand in for** — it is why `foreign.planes` is the last blocked
   program. The effect capabilities (`ask`/`read`/`write`/`show`/`clock`) are
   the ambient/foreign surface Phase 3 exercises; a second host reimplements
   them in its own runtime.
3. **A JSON parse/serialise at the boundary** — the one capability Phase 3
   proved is *not* expressible in Planes. A second host provides it, exactly as
   `PythonHost` does with `json`.
4. **Enough interpreted recursion depth** to run real recursive programs — the
   32-frame ceiling is the second host's to raise, not the language's. On a
   compiled route there is no interpretive multiplier at all (A.5).

That is the whole of it: a bounded, enumerated surface — 28 keywords, 10
builtins, 7 effects, 8 host methods, one JSON boundary — with `resolve` and
recursion depth as the two items `interp.planes` running on CPython cannot
demonstrate for itself. **Route B is closed; the second host is a piece of work
with a known size, not a rewrite.**
