# REPORT — The second guarantee, self-hosted

**Build:** S8, `feat/why-self-hosted`, on `047e7cd` (PR #25's merge commit).
**Question:** Planes makes two guarantees — *what does this program do*, and
*where did this value come from*. The self-hosted stack delivered the first and
not the second: `grammar/interp.planes` carried a `deriv` slot on every value
and never filled it. This build fills it, and measures the prediction that made
the deferral acceptable three builds ago.

---

## 1. A.1 — was the fill-not-rewrite prediction right?

**Yes, for the fill. Not for the whole feature.** The distinction is the
finding, and it is worth more than either half on its own.

### 1.1 Call sites changed

`grammar/interp.planes`: **+343 / −54 lines**. Every provenance attachment goes
through one of two new constructors, `derived` and `derived-at`, so the sites
are countable exactly.

| | count |
|---|---|
| provenance attachment sites (`derived` / `derived-at` calls) | **37** |
| …of those, a one-line wrap of an already-built value, no other change | **33** |
| …of those, in a function whose signature also changed | **4** |
| functions containing an attachment | **26** |
| **existing functions whose signature changed** | **3** |
| new functions added | **17** |

The three signature changes, and why each was unavoidable:

| function | change | why |
|---|---|---|
| `run-body` | `+name, +arg-derivs` | the `call` step's label is the callee's name and its inputs are the *caller's* argument derivs; `run-body` received neither |
| `run-foreach` | `+source-deriv` | the `comprehension` step's first input is the source's deriv |
| `foreach-item-step` | `+source-deriv` | the `item` step's only input is the source's deriv |

All three are the same shape: a derivation step whose inputs come from a scope
the function did not already see. Nothing else in the evaluator moved. In
particular `apply-op`, `apply-plus`, `eval-builtin`, `values-equal`, and every
`make-*` constructor are **unchanged and still derivation-blind** — provenance
is attached by the caller, exactly as `interp.py`'s `apply_op` has no idea
derivation exists.

Three functions gained a parallel accumulator in an existing loop
(`eval-list-node`, `eval-record-node`, `run-foreach`) to collect input derivs in
the same pass rather than a second one. That is a fill too, but a two-line one
rather than a one-line one.

### 1.2 Did the status record's shape have to move?

**No.** It is still exactly four fields:

```planes
to normal-of of value, env:
  give { status: "normal", value: value, env: env, error: nothing }
```

The `deriv` slot lives on the value, as ruled, and the value already had it.
Nothing that threads a status record was touched for provenance.

### 1.3 What it cost in frames

**Nothing measurable.** All six numbers, before and after the complete fill:

| measurement | baseline (`047e7cd`) | after |
|---|---|---|
| `INTERPRETED_EVAL_NESTING_DEPTH` | 139 | **139** |
| `INTERPRETED_RECURSION_DEPTH` | 32 | **32** |
| frames per interpreted call | 35 | **35** |
| `INTERPRETED_STATEMENT_NESTING` | 33 | **33** |
| `FULL_PIPELINE_NESTING_DEPTH` | 23 | **23** |
| `MAX_ENV_LEN_AT_RECURSION_DEPTH` | 4 (depth 120) | **4 (depth 120)** |
| `MAX_ENV_LEN_AT_CALL_CHAIN` | 63 (chain 60) | **63 (chain 60)** |

`interp.py`'s own frames-per-Planes-call is likewise unchanged (4 if-based,
5 when-based; ceilings 245 / 196).

The reason is structural rather than lucky: every attachment is a **leaf**. A
deriv is built either at a literal (which returns immediately) or *after* a
recursive descent has already returned. Nothing was added to the per-cycle cost
of the call spine, so the ceiling — determined by frames per cycle — does not
move.

### 1.4 Where the prediction was wrong

The prediction was that *populating derivation later would be a fill rather than
a rewrite*. The **producing** half was a fill, and a clean one. The **reading**
half was not a fill at all: there was no slot for it.

`why` is not `deriv`. Answering "where did this value come from" needs
`explain`, `render` and `origins` — and none of the three had any counterpart in
the self-hosted stack. Seven of the 17 new functions (`explain-of`,
`render-deriv`, `render-call-deriv`, `join-derivs`, `ends-with`, `origins-of`,
`origins-walk`) are that reader, roughly 90 lines, written from scratch against
`interp.py`. Two more (`exec-why`, `set-annotation`) are the statement and the
`because:` table it reads.

So the honest statement of the measurement is: **the deferral left a slot for
the data and no slot for the question.** A prediction that says "the field is
already there" is true and is not the same as "the feature is a fill". Worth
carrying forward: when a build defers a guarantee behind a field, the field is
the cheap half.

One thing the fill genuinely *did* deliver that a rewrite would not have: the
`deriv` slot's presence meant no caller of a value ever had to change. The
evaluator's 26 attachment functions were edited; not one of its *consumers* was.

### 1.5 One measurement the fill produced for free

`ends-with` exists because Planes has `first n of` for a prefix and **no suffix
operation at all** — `rest` is list-only. `interp.py`'s `render()` asks whether
an op label ends in `" of"`, and answering that in Planes takes a one-pass loop.
That is not a defect, but it is the first time the self-hosted stack has needed
a suffix and found none.

---

## 2. A.2 — `why` and `origins_of` agreement

`test_why_in_planes.py`, three layers, all against `interp.py` as the
specification.

**1. One case per derivation step**, 61 programs covering every kind the graph
can hold — literal, name, op (all fourteen operator forms including both
short-circuit arms), field, call (both `interp.py` shapes), item,
comprehension, record, list, effect, foreign — plus `because:` set and popped
on an unannotated rebind, and `show`/`why` interleaving order. **All agree.**

**2. The derivation graph, not just its rendered line.** Reusing the canonical
form the analyser port already defined for comparing derivation trees
(`test_js_shapes_derivation.py`'s `_py_deriv_tree`): kind / label / origin /
inputs, fully expanded, shared nodes re-walked. Its `file` field is the static
analyser's and has no runtime counterpart, so it is the only field that does not
carry over; nothing was invented. 14 programs, **all agree**.

**3. The corpus.** Every program in `corpus/`, with a `why <name>` appended for
every top-level binding it produced, and the whole output list compared:

> **43 of 50 corpus programs, 130 derivations, all agreeing.**

The seven that do not run on both are named, not dropped:

| program | why |
|---|---|
| `allowed-hosts`, `api-batch`, `stock-check`, `weather-fetch`, `quantity-check` | fail identically on `interp.py` under a hermetic `TestHost` — their own `or fail` tags for unstubbed network. They produce no derivable value on either side. |
| `cache-store` | `interp.planes`'s inert mode has no write-then-read within a run (its `files` table is input-only). Pre-existing, unrelated to derivation. |
| `fastest-responses` | a pure foreign (`doing nothing`) with no supplied inert result returns `nothing`. Pre-existing, unrelated to derivation. |

### `origins_of`

**Reachable, and agreeing.** `origins-of` is implemented in
`grammar/interp.planes` and checked against `interp.py`'s `origins()` across
file, network, foreign, and comprehension provenance — including a value read
inside a function, passed out, and folded into an arithmetic result, whose
origins still name `file:a.txt`.

### The one thing that is not reachable — a named finding

`why_tree` (the `--why NAME` full tree) prints `(same as above)` for a
subgraph it has already emitted, and decides that by **Python object
identity** (`id(n) in seen`). A value language has no object identity: two
structurally identical derivs *are* the same value. Substituting structural
equality would diverge on a program as small as `1 + 1`, where `interp.py`
prints both literal nodes and a structural dedup would print one.

So: the *graph* agrees (layer 2 proves it), and the *information* is fully
present in the self-hosted stack. Only that one rendering shortcut cannot be
reproduced, and shipping a knowingly-divergent `why-tree-of` would have been
worse than naming the gap. `planes.py --why NAME` remains a Python-side
affordance.

### `why` performs nothing

`interp.py` appends a `why` line to `self.output` and to no effect list.
Reproduced exactly: the line lands in a threaded `output` accumulator on the io
record beside `show`'s, in run order, and the effect log is untouched — so
asking where a value came from widens no effect surface. In real mode the line
reaches the host through a Planes `show`, byte-identical to `interp.py`'s
output, and still logs no effect.

---

## 3. A.3 — the negative-literal render defect

### The mechanism, and a divergence found on the way

`parse_unary` desugars `-X` into `BinOp("-", Num(0), X)`. `render` emitted
`0 - X`: arithmetically right, canonically wrong twice over. It lost the source
form, and it did not round-trip.

The round-trip half turned out to be a **divergence between the two
implementations**, which no prior build had reason to look for:

| | synthesised zero |
|---|---|
| `parser.py:772` | `Num(0)` — a raw Python `int` |
| `js/parser.mjs:768` | `Num(new PlanesNumber(0n))` — a real number |

`render.py`'s `ast_equal` compared Python types, so `Num(int 0)` and
`Num(Number 0)` were "different" and the Python round-trip failed. JavaScript's
`astEqual` has always compared `PlanesNumber` leaves by value, so **the JS
implementation already round-tripped a negative literal and the Python one did
not.** The corpus found the Python half; the fix closes both.

### The fix, in both implementations

1. **Render a subtraction from a literal zero as the unary form.** The renderer
   cannot tell a synthesised zero from a written one — JavaScript builds a real
   `PlanesNumber` for both — so a source-written `0 - X` canonicalises to `-X`
   too. Same program, shorter form, and both implementations render identically.
2. **`ast_equal` compares a numeric leaf by value, before the type test.** This
   brings Python level with JavaScript, and it is the half that made the
   round-trip fail rather than merely look wrong.

Before: **14 of 15** distilled negation shapes failed. After: **23 of 23** pass,
on both implementations, byte-identical render output.

### Every canonical-text change, with its reason

102 renderable files were rendered before and after and diffed. **Exactly one
file changes, in two lines:**

| file:line | before | after | reason |
|---|---|---|---|
| `grammar/parser.planes:63` | `result = 0 - 1` | `result = -1` | a subtraction from a literal zero is the unary form |
| `grammar/parser.planes:69` | `if result == (0 - 1):` | `if result == (-1):` | same |

No other file's canonical text moves. `grammar/parser.planes` itself is
unchanged on disk (invariant 2) — only its rendering.

---

## 4. A.4 — the composition matrix reaches synthesised nodes

**This is the class fix, and it matters more than its instance.** The matrix was
derived from the *grammar*: `_INNER` lists the kinds `render_expr` emits,
`_CONTAINER` the positions a production reads a sub-expression. Every inner is
written down as source — so a node the parser *builds* and no source text
*writes* is unreachable by construction. That is exactly where this defect
lived.

### The list is derived, not written

`_parser_synthesis_sites()` reads `parser.py`'s own AST and reports every
construction of an AST node containing a sub-node built entirely from constants
— the exact signature of "the source did not supply this".

> **1 site derived: `parser.py:772`, `BinOp('-', Num(0), self.parse_unary())`.**

A broader sweep (any node constructor with a constant argument) confirms it:
the only other constants in node constructions are the operator strings
`"or"`, `"and"`, `"in"`, `"first"`, which the source *does* write.

The authored part is only the source fragment that reaches each site — a
deriver cannot invent `(-1)` from `Num(0)`.
`test_every_synthesised_node_is_in_the_matrix` fails if a derived site has no
fragment, so the **coverage obligation** is machine-derived even though the
fragment is not: a new desugaring in the parser lands in the matrix before it
lands in the corpus.

### What the extension found

| | pairs | reachable | failures |
|---|---|---|---|
| before | 680 | 680 | 0 |
| after | **816** | **816** | **0** |

The matrix also gained `and`, `or`, and `in` — the three BinOp precedence levels
it had only ever sampled through `+` and `>`.

**No second defect.** The synthesised negation was the whole class: once it
renders as itself, every one of its 34 container compositions round-trips on
both implementations with byte-identical text. That is a weaker headline than
S6's forty defects and a stronger result about the codebase.

---

## 5. A.5 — the two messages, and the catalogue counted

### The messages

Both came from the parser's generic `expect`, which reported a mismatch and
named nothing:

```
x = { k: f of a, k2: 9 }   ->  line 1: expected }, found ':'
let rule = 1               ->  line 1: expected name, found 'rule'
```

`expect` now has two ways to name a fix, **identical in `parser.py` and
`js/parser.mjs`, byte for byte**:

* **A reserved word where a NAME was wanted gets its own message.** That is
  never a punctuation slip — it is the 42-name reserved surface (32 keywords +
  10 builtins) being hit. The builtin half already errored naming the collision;
  the keyword half now says the same thing in the same voice, and the two point
  at each other:

  ```
  line 1: 'rule' is a keyword, so it cannot be used as a name
    keyword names are reserved like builtins; pick another name
  ```

  One change, every name position: a `let`, a parameter list, a loop variable.

* **Every other site may pass a `fix=` clause.** The record close passes the
  greedy-tail diagnosis, which is the actual cause of `found ':'`:

  ```
  line 1: expected }, found ':'
    a record is `{ name: value, ... }`; a call or `with` used as a field value
    takes the rest of the list, so parenthesise it: `{ k: (f of a, b), k2: 9 }`
  ```

Both raises are literal f-strings rather than a message assembled in a variable,
so `grammar_gen.py` can read them and the catalogue records the fix clause it
counts. `test_error_messages.py` asserts the clause per message, in both
implementations.

### The catalogue, counted

`errors_coverage.py`, wired into `scripts/ci.sh` as a report that exits 0 by
construction. **The first measurement of a commitment asserted since v1.1 §22
and never counted.** (The prompt's summary-basis figure was 82 entries; the
generator produces 95 at this build's baseline and 97 after.)

| bucket | count | share |
|---|---|---|
| **names a fix** | **70** | 72% |
| delegates to `amber.json` templates that all carry one | 6 | 6% |
| unreadable — assembled away from the raise site | 9 | 9% |
| **NAMES NO FIX — the shortfall** | **12** | **12%** |

Two deliberate choices in the measurement:

* **"unreadable" is never counted as a pass.** Nine `PlanesError` sites build
  their message elsewhere, so the catalogue cannot see whether they name a fix.
  An unknown is reported as an unknown.
* **The shortfall is measured structurally.** Three of the twelve (the lexer's
  string-literal errors) *do* name their fix, inline in prose — and are counted
  as shortfall anyway, because a catalogue an author or a tool reads needs the
  fix in a field or on its own line. The shortfall doubles as the work list for
  making those fixes structural.

The remaining nine are genuine: two arity messages, `whole of` on a non-number,
three parser token expectations (including `expect`'s own no-fix path, which is
honest — most of its call sites have no context-specific fix to give), one
duplicate-record-field, and two rules-report lines that are informational rather
than errors.

---

## 6. Does the self-hosted stack now deliver both guarantees?

**Yes.**

`grammar/interp.planes` — 1,700 lines of Planes, running on either host —
evaluates a Planes program and, for every value it produces, answers where that
value came from: the one-line `why`, the full derivation graph, and
`origins_of`'s list of every boundary the value crossed. All three agree with
`interp.py` across 43 corpus programs and 130 derivations, and across every kind
of derivation step the graph can hold.

Two qualifications, both stated rather than buried:

* `why_tree`'s `(same as above)` shortcut is not reproducible in a value
  language (§2). The information is present; that one rendering is not.
* Three corpus programs' *values* are unreachable in the self-hosted stack for
  reasons that predate this build and have nothing to do with derivation —
  inert-mode gaps in write-then-read and pure-foreign results.

**And with no language addition.** Counts are still **32 / 10 / 7 / 8** — no new
keyword, builtin, effect kind, or host method. `core_check` still reports
`interp.planes` inside the declared core (28 of 32 keywords, 10 of 10 builtins,
7 of 7 effect kinds). `why` needed nothing the language did not already have,
which is the strongest available answer to §8's first stop condition.

---

## 7. What this build disproved about this prompt

**The structural fix in §6 did not work. This is the fourth consecutive
self-contradictory invariant, and §6 was written last specifically to prevent
it.**

Invariant 3 enumerates what may change and closes with **"Nothing else."** A.6
opens with **"Nothing is out of bounds that these rulings need."** These
contradict the moment a ruling needs a file neither sentence enumerates — and
A.1 and A.5 both did:

| file changed | not in invariant 3 | required by |
|---|---|---|
| `scripts/measure_interp_planes.py` | ✓ | A.1 — its `repr(v)` label walks the new derivation DAG exponentially |
| `scripts/run_corpus_through_planes.py` | ✓ | A.1 — same |
| `scripts/measure_association_idiom.py` | ✓ | A.1 — same |
| `scripts/ci.sh` | ✓ | A.5 / §9 — "catalogue check wired in as a report" |
| `errors_coverage.py` (new) | ✓ | A.5 — "add a check … reporting rather than failing" |

The failure is **not** the one §6 was designed against. §6's diagnosis was
*ordering* — an invariant written before the ruling it would forbid — and the
fix was to derive §6 from §A after §A was complete. That worked: no invariant
here forbids anything a ruling requires. The contradiction that survived is
about **enumeration**: an exhaustive whitelist plus a "nothing else" cannot
coexist with a general permission, because no author can enumerate the files a
ruling will turn out to need. Discovering that
`scripts/measure_interp_planes.py` had to change required *making* the change
first and watching a 13-second suite run unbounded.

The correction, if a fifth prompt wants one: **do not enumerate scope and then
close it.** State the intent ("this build may change what its rulings require,
and must enumerate what it changed in the report") and let the report carry the
list. That is what §A.6 already says; invariant 3 should have restated it, not
narrowed it.

Two smaller under-specifications, resolved toward §A's evident intent per
failure mode 10, and named rather than routed out:

* **A.4 "derive the list from the parser's construction sites rather than by
  hand"** is not fully satisfiable: a deriver can find `Num(0)` but cannot
  invent the source fragment `(-1)` that reaches it. Resolved as: derive the
  *sites* and the *coverage obligation* mechanically, author only the fragments,
  and fail the test when a derived site has no fragment. Failure mode 5's
  warning ("a written list of synthesised nodes") is honoured — there is no
  written list, only a written fragment per derived key.
* **A.2 "reuse the existing derivation canonical form"** — the analyser port's
  form carries a `file` field with no runtime counterpart. Reuse therefore meant
  dropping exactly one field, which is noted in the test rather than treated as
  a new form.

Finally, one prompt figure was stale in a way §0's baseline caught, exactly as
the PROVENANCE note anticipated: `grammar/errors.json` ships **95** entries at
baseline, not 82.

---

## 8. What remains

**Guarantee: nothing.** Both guarantees are now self-hosted, on both hosts.

**Runtime**, all pre-existing and all previously named:

* `interp.planes` inert mode has no write-then-read within a run, and a pure
  foreign with no supplied result returns `nothing`. Two corpus programs are
  unreachable in the self-hosted stack for these reasons.
* `interp.planes` real mode cannot resolve an arbitrary foreign
  (`foreign-needs-host`); `ask` returns the response's text form rather than
  parsed JSON, because Planes has no JSON parser and no runtime type probe;
  `write` of a record falls back to its canonical text.

**Neither runtime nor guarantee:**

* The 12-entry catalogue shortfall — a work list, now measured and reported
  every CI run.
* `why_tree`'s identity-based dedup (§2).
* Nine catalogue entries whose message is assembled away from the raise site, so
  the generator cannot capture it. Making `grammar_gen.py` follow those would
  raise the readable share above 91%.
* Planes has no suffix operation (§1.5).

---

## 9. Verification

`scripts/ci.sh` green. Counts **32 / 10 / 7 / 8**. `grammar/lexer.planes` and
`grammar/parser.planes` unchanged. `grammar_gen.py --check` exits 0 after
regeneration. Metacircular re-run after the canonical output changed: the JS
host runs the *modified* `grammar/interp.planes` and still agrees with
`interp.py` on the corpus, and both analysers still find the same surface on all
three grammar stages.
