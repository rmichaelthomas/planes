# CORE_SUBSET.md — the port surface for self-hosting

> **Corrected by S2 §A.8 (this build).** The sweep's original derivation made
> one wrong call — it placed the seven effect kinds *outside* the core because
> the pure lexer and parser use none. §2a corrects that: **the core includes
> all seven effect kinds**, because an interpreter performs whatever effects it
> interprets. S2 also ruled `with` into the core (prediction-justified, §4) and
> added `join`/`rest` to the builtins (§1.2). The sections below are corrected
> in place; the corrected headline is **half the keywords and all of the
> effects**, not "none of the effects."

**Status: a proposal for the constructs; the effect-kind and `with` questions
are ruled by S2 §A.8.** It goes to the architect. Checkpoint
v10.0 §127's obligation is to derive the core — the subset of Planes that
`interp.planes` will be written in, and therefore the subset a second host
must implement to run it — *from evidence, not taste*. Every member below
names a program that cannot be written without it. Every non-member names the
evidence that it went unused.

The evidence base is the two largest Planes programs in existence,
`grammar/lexer.planes` (564 lines, 52 functions) and `grammar/parser.planes`
(1118 lines, 98 functions), inventoried mechanically by
`probe/selfhost/phase6_inventory.py` (tokenized with the language's own
`lexer.tokenize`, not eyeballed — transcript at
`probe/selfhost/transcripts/phase6_inventory.txt`), plus what Phases 1–5 of
`PROBE_SELFHOST.md` show `interp.planes` needs beyond what the lexer and
parser needed.

---

## 1. The proposed core

Each member lists a justifying program: one that cannot be written without it.
Counts are combined token occurrences across the two grammar programs.

### 1.1 Constructs (syntax)

| Member | Used | Justifying program — cannot be written without it |
|---|---|---|
| function def `to NAME of p: … give` | to 150, give 304 | `grammar/parser.planes` — recursive descent is functions calling functions |
| function call `NAME of args` (`of`) | of 577 | every program; `of` is the single most-used word in the language |
| assignment `NAME = expr` | pervasive | every function body binds intermediate results |
| `if / else` | if 126, else 166 | `grammar/lexer.planes` per-character classification |
| shape dispatch `when subj is { … } / else` | when 44, is 46 | `grammar/parser.planes` node dispatch; **`interp.planes`'s `eval` (Phase 2)** — the *only* substitute for the absent `isinstance` |
| bounded iteration `for each x in xs [where c]` | for/each 18, in 19, where 3 | the association-idiom env lookup (Phase 1); every token/list walk |
| record literal `{ f: v, … }` | 270 `{` | tokens, AST nodes, and closures-as-data (Phase 5) are all records |
| list literal `[ … ]` + `plus` | `[` 26, plus 38 | the token stream; the association-list environment (Phase 1) |
| field access `.name` | pervasive | `token.kind`, `node.left`, `entry.value` — every record read |
| operators `+ - * / < > <= >= == != in` | in 19, arith/compare pervasive | position arithmetic in the lexer; every comparison in dispatch |
| boolean `and / or / not` | and 28, or 51, not 3 | compound guards in `parse_*` |
| literals: number, string, `true`/`false`, `nothing` | true 17, false 25, nothing 6 | everywhere; `nothing` is the "no result" of a failed scan |
| recursion (self-call via `to`/`give`) | — | `grammar/parser.planes`; **`interp.planes`'s `eval`, and the fixpoint (Phase 4)** |
| error handling `or fail as tag: …` | fail 10, as 10 | `grammar/parser.planes` error recovery; the interpreter's own guarded evaluation |
| module use `use NAME` (+ `from`) | use 2, from 2 | `grammar/lexer.planes` reads its tables via `use vocabulary` |

### 1.2 Builtins (of 10, after S2 added `join` and `rest`)

| Member | Used | Justifying program |
|---|---|---|
| `text of` | 116 | `grammar/parser.planes` renders each AST node to canonical text |
| `count of` | 13 | list/string lengths; the fixpoint's convergence test (Phase 4) is `count of grown == count of reached` |
| `join of` | new (S2 §A.2) | `render.planes`'s O(n) string building — the answer to the O(n²) repeated-`+` the sweep measured; no program predating S2 could use it |
| `rest of` | new (S2 §A.3) | `parser.planes`'s cons-list navigation — advancing past the front of a token list, the access pattern the cons-list ceiling is about |

`upper of` appears **once** (parser.planes) — by §127 obligation 4 ("a
construct appearing once for convenience is not core"), it is a convenience,
not core. Listed here as a borderline the architect should rule on. So the
core builtin set is on the order of `text`, `count`, `join`, `rest` — 4 of the
10, with `upper` borderline.

### 1.4 Effect kinds — all seven (S2 §A.8)

All seven effect kinds (`ask read write show clock random env`) are core. The
sweep's derivation put them outside the core because the pure lexer and parser
use none; §2a is the correction — an interpreter performs whatever effects it
interprets, so its static effect surface is all seven, always.

### 1.3 The one addition Phases 1–5 make beyond the lexer/parser core

| Member | Status | Justifying program |
|---|---|---|
| record update `with` | **in the core, prediction-justified (S2 §A.8) — see §4** | measured for rebinding at env scale (Phase 1); the grammar programs and Phase 5's demo use it **zero** times (fresh record construction instead), so it is the sole core member with no program behind it — to be confirmed or removed when `interp.planes` exists |

Everything else Phases 1–5 require — records, recursion, `for each`, the
association idiom, `when…is`, closures-as-data — is already in §1.1. Phase 5's
central result is that `interp.planes` needs **no new construct** to represent
user functions: an inert `{ param, body, env }` record applied by
interpretation is built entirely from members already in the core
(`probe/selfhost/phase5_closures_as_data.planes` proves it end to end).

---

## 2. Not core — with the evidence

`probe/selfhost/phase6_inventory.py` found these **unused** across all 1682
lines of the two grammar programs (or used only as documentation):

| Non-member | Evidence | §127 predicted? |
|---|---|---|
| `let` | 0 keyword uses — plain `=` suffices everywhere | — |
| `show`, `write` | 0 uses — the grammar programs are pure functions; **effects are the host's job, not the interpreter's** | — |
| `why` | 0 uses — provenance query is a tool, not a language primitive |
| `round`, `places` | 0 uses | — |
| `foreign`, `doing` | 0 uses — the grammar programs are pure Planes | **yes** |
| `rule` | 0 uses | **yes** |
| `note:` / `because:` | `note:` appears 2× — both are file-header docstrings, identical behaviour with or without them; `because` 0× | **yes** |
| the record plane (§95–102 boundary-crossing Record/Anchor/`maybe_record`) | a runtime `record=` toggle, never a syntax token — nothing to reproduce in a v1 interpreter | **yes** |
| builtins `lower`, `whole`, `ask`, `read`, `normalize` | 0–0 uses | — |
| positional `may`, `supersedes`, `derives-from` | 0 uses | — |

> **CORRECTED (S2 §A.8): the seven effect kinds are core — see §2a.** The
> sweep's original derivation placed all seven effect kinds here, on the
> evidence that `grammar/lexer.planes` and `grammar/parser.planes` use zero of
> them. That inference is wrong, and §2a is the correction. Effect kinds are
> the one place a derivation from two *pure* programs gets the core wrong.

**§127's prediction is CONFIRMED, not refuted.** The four items it named —
the `note:`/`because:` planes, the record plane, `rule`, and `foreign` — are
each either unused or used only as documentation. Nothing in the inventory
forces any of them into the core.

## 2a. The effect kinds ARE core — the one correction (S2 §A.8)

The lexer and the parser are pure functions: they transform text to tokens
and tokens to an AST, crossing no boundary, so a core derived from them finds
zero effects. An **interpreter is not pure.** `interp.planes` performs whatever
effects the program it runs performs — its static effect surface is **all seven
kinds, always** (`ask read write show clock random env`). That is sound and
maximally imprecise: indirection taken to its limit, not a failure of the
analyser. A second host cannot run `interp.planes` without the effects, because
the programs `interp.planes` interprets will ask, read, write, show, clock,
randomize, and read the environment.

**Ruling: the core includes all seven effect kinds** — either directly, or via
`foreign` plus a host implementing them, which is the same port cost either
way. The effects re-enter at the host beneath `interp.planes`, exactly where
they enter beneath `interp.py` today; but "at the host" is still inside the
port surface a second implementation must provide.

One caution on wording: §127's "record plane" is the **provenance-recording
subsystem** (§95–102: `Record`, `Anchor`, `maybe_record`, the `record=`
toggle), which is correctly not core. It must not be confused with **record
literals** `{ … }`, which are the single most-used data construct (270
occurrences) and are unambiguously core. The prediction is about the former.

---

## 3. How much smaller is the core than the language

The full surface, after S2 added `join` and `rest`, is **32 keywords / 10
builtins / 7 effect kinds** (+ 6 positional words) = 55 named elements.

The corrected core is roughly **~18 keywords / 3 builtins / all 7 effect
kinds**, plus records, lists, operators, and literals — on the order of **half
the keywords and all of the effects**. (Recount of the builtins: the two
largest programs use `text`, `count`, and one occurrence of `upper` — 3 of
the 10; `join` and `rest`, added by S2, are core for `render.planes`'s O(n)
string building and `parser.planes`'s cons-list navigation respectively, so
the interpreter-era core builtin set is on the order of `text`, `count`,
`join`, `rest`.)

**The earlier claim that a second host need implement no effect was wrong**
(§2a). A second host that runs `interp.planes` need not implement `foreign`
the record plane, `rule`/`note`/`because`, or `why` — but it **must** implement
all seven effect kinds, because the programs `interp.planes` interprets use
them. Any second-host scoping done against the uncorrected "half the keywords,
none of the effects" figure is wrong by exactly the amount that matters: the
whole effect surface.

---

## 4. `with` is in the core — prediction-justified (S2 §A.8)

**Ruling: `with` is in the core, and is the sole member justified by prediction
rather than by an existing program** — marked as such, to be confirmed or
removed when `interp.planes` actually exists.

- **Phase 1 measured it** as a rebinding primitive and found it cheap (~4 µs,
  flat to 500 fields — `probe/selfhost/transcripts/phase1_env_lookup.txt`).
- **The two largest programs never use it.** `grammar/lexer.planes` threads its
  lexer state forward by writing a fresh record literal at every step, never
  `state with out: …`; and Phase 5's `demo/status_threading.planes` threads its
  status record the same way (fresh `{ status, value, env, error }` each step).
  The entire argument for `with` is A.6's state-record threading, which an
  interpreter does on every step — so `with`'s ergonomic case is real even
  though no program yet proves it necessary.

Every other core member (§1) has a program behind it that cannot be written
otherwise. `with` alone rides on a prediction about how `interp.planes` will be
written. It stays in the core with that caveat attached; the first real
`interp.planes` either uses it (confirmed) or threads fresh records throughout
(and `with` leaves the core).

### 4a. Added later — §1.1's `when` row held, and was briefly overruled

*This section is an addendum, not a revision: nothing above it has been changed.*

`with`'s prediction was discharged — `grammar/interp.planes:117` uses it, and
`core_check.py` confirms it on every run. But a different §1 row turned out to
need defending, and this is the record of it.

**§1.1 lists `when subj is { … } / else` as core**, justified by
`grammar/parser.planes`'s node dispatch and called *"the only substitute for the
absent `isinstance`"*. `grammar/core.json` later **excluded** `when`, on the
stated grounds that this claim was refuted — that dispatch is flat `if k == …`
and `when` is never needed.

The evidence for that exclusion was real but partial:

| | `when` tokens |
|---|---|
| `grammar/parser.planes` when §1.1 was written (`135ecb4`) | **28** |
| `grammar/parser.planes` by the time the exclusion was written | **0** — rewritten to flat `if` |
| `grammar/interp.planes` | **0** — flat `if k == …`, exactly as claimed |
| `grammar/lexer.planes` | **16**, and never rewritten |

So `when`'s named justifying program had stopped using it, the interpreter never
used it, and the exclusion looked airtight. It was airtight *about those two
files*. `grammar/lexer.planes` — which §1.1 names one row above, as the
justifying program for `if / else` — kept its sixteen, in `to step of state, c:`,
the loop every character of every program passes through. Nothing could say so,
because `core_check.py`'s `violations()` read a single file and the graph was
never followed.

A host implementing only the core as declared then **could not have run the
interpreter the core was the port surface for.** Measured by running
`interp.planes` on exactly such a host: it refused at `grammar/lexer.planes:89`,
and all sixteen sites proved reachable at evaluation time on one ordinary corpus
file. Widening the core by `when` and nothing else made the whole corpus run
under restriction, byte-identical to the unrestricted run.

`when` is back in the core, where §1.1 put it. The port surface is 29 keywords,
not 28. The lesson is not that the exclusion was careless — it is that **a core
derived from one file cannot be checked against one file**, and for three builds
it was both.

## 5. Sketch of the core-conformance checker (sketch only — not built)

Modelled on `audit_locked_vs_built.py`, which confirms every *locked* construct
has code evidence. The core checker inverts that: it confirms `interp.planes`
uses *nothing outside* the ruled core.

```
# core_check.py  (SKETCH — do not build in this probe)
CORE = load("grammar/core.json")        # the ruled core, once §1 is a ruling
toks = lexer.tokenize(open("interp.planes").read())
violations = []
for t in toks:
    if t.kind is a keyword-token and t.value not in CORE.keywords:
        violations.append((t.line, "keyword", t.value))
    if t.kind == "NAME" and t.value in ALL_BUILTINS and t.value not in CORE.builtins:
        violations.append((t.line, "builtin", t.value))
    # NOTE (S2 §A.8): effect kinds are NOT flagged — all seven are core,
    # because an interpreter performs whatever effects it interprets.
exit(1 if violations else 0)   # print each: interp.planes:LINE uses non-core X
```

It reuses the language's own `lexer.tokenize` (so the checker and the language
never disagree about what a token is), reads the core from a single JSON source
of truth (as `grammar/vocabulary.json` is the source of truth for the full
surface), and fails closed. Building it is out of scope for this probe by §6
step 6; it waits on §1 becoming a ruling.

---

## 6. One-paragraph summary

The core is about **half the keywords and all seven effect kinds**. Everything
`grammar/lexer.planes` and `grammar/parser.planes` needed across 1682 lines is
a compact set — functions, records, lists, `if`, `when…is`, `for each`,
recursion, `or fail`, `text`/`count`, and the operators — to which S2 adds
`join`, `rest`, `with` (prediction-justified), and the correction that all
seven **effect kinds are core** (§2a): an interpreter performs whatever effects
it interprets, so a second host must implement every one. §127's four predicted
non-core items — the annotation planes, the record (provenance) plane,
`foreign`, `rule` — are all confirmed unused and stay outside the core, along
with `why` and five of the ten builtins. The surprising part is not what is in
the core but that the one thing a derivation from two *pure* programs got wrong
is the very thing an interpreter exists to do: cross boundaries.
