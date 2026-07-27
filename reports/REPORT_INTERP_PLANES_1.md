# REPORT — S3b, `interp.planes` Build 1: The Expression Evaluator

**Branch:** `feat/interp-planes-expressions` · **Base:** `main` at `d4dbc3f`
**Result:** shipped, all seven phases plus gate. Full suite **749 green** (685
baseline + 64 new). `ruff`, `mypy`, `audit_locked_vs_built.py`,
`grammar_gen.py --check` clean at every commit. Parser agreement **31/31**,
lexer agreement **100%**, both self-hosting assertions holding. Counts
unchanged: **32 reserved words / 10 builtins / 7 effect kinds / 8 host
methods**.

`grammar/interp.planes` evaluates Planes expressions to values, checked by
agreement with `interp.py`'s own `eval()` through a canonical value-text form.
The three Planes stages — `lexer.planes` → `parser.planes` → `interp.planes` —
run as one pipeline for the first time.

---

## What shipped, phase by phase (against §A)

**Phase 1 — the canonical value form (oracle before evaluator).** A helper in
`test_interp_in_planes.py` renders an `interp.py` value to canonical text;
`grammar/interp.planes`'s `canonical-of-value` renders the same form via
`show`. Numbers render through `interp.py`'s `Number.text()` — exact rationals,
never a float; strings escape+quote via `escape-string-literal` (reused from
`parser.planes`, the same four escapes); records render fields in stored order;
`1`, `"1"`, and `true` render distinctly. Committed with 12 cases passing and
**no evaluator** (A.5, §1).

**Phase 2 — literals and variables.** The flat `eval` dispatch established with
its first four cases plus `Var`, each arm `if … give` and falling through when
unmatched — no nested `when`/`else` ladder (A.1). The environment is one flat
list of `{ name, value }` scanned first-match-wins (A.2), read by static field
access only. The value record carries a `deriv` slot, `nothing` throughout
(A.3). `node-of-source` wires tokenize → parse so the evaluator consumes the
AST the parser already produces (A.4).

**Phase 3 — operators.** Every precedence level: `+ - * /`, the six
comparisons, `== != in`, `first n of`, `and`/`or` (short-circuit), unary minus,
`not`, `is nothing`. `interp.py`'s coercion and type guards reproduced by
reading `interp.py`. The arithmetic is metacircular and exact for free (A.5
ruling 1, verified below).

**Phase 4 — records, lists, field access, `with`, `plus`, `round`, builtins.**
Record values are a tagged list of `{ key, value }` pairs, so field access is a
list scan on each pair's static key — never a dynamic record lookup (A.2). Of
the ten builtins, the eight pure ones are in scope (`count text lower upper
whole normalize join rest`); `ask` and `read` are effects and fail naming build
3 (A.6). `text of` reproduces `interp.py`'s `fmt`, distinct from the canonical
form.

**Phase 5 — calls to pure functions.** A function is a tagged value in the
environment; applying it binds parameters, prepends them, and passes the
extended list down (A.2). A function whose body is not a single give-expression
is control flow — build 2 — and fails naming it (A.6).

**Phase 6 — the pipeline, connected.** `evaluate-source` is one Planes call:
source text in, canonical value out.

---

## Baseline ceilings, and the ceiling after Phase 6

Measured at `§0` with the default Python recursion limit (what `interp.py`
relies on to raise `recursion-too-deep`), by binary search for the largest
self-recursion depth that succeeds:

| shape | baseline (§0) | after Phase 6 |
|---|---|---|
| `if`-based | **245** (246 raises) | **245** |
| `when`-based | **245** (246 raises) | **245** |

The ceiling is a property of arbitrary Planes recursion on `interp.py`,
independent of `interp.planes`, so Phase 6 leaves it unchanged.

---

## The interpreted-depth fraction (as a number, with the method)

Method: run deeply-nested expressions and binary-search the largest nesting
before `recursion-too-deep`. To isolate the evaluator from the parser, a deep
`BinOp` AST record was built directly (parsed into a node by `parser.py`, with
Python's limit raised only for that build, then restored) and handed to `eval`
— so only `interp.planes`'s own recursion is exercised.

| what | usable depth | fraction of 245 | Planes frames / level |
|---|---|---|---|
| **eval alone** (node pre-built) | **140** | **0.57** | ~1.8 |
| **full pipeline** (source → value) | **23** | 0.094 | ~10.7 |
| **function-call chain** | **88** | 0.36 | ~2.8 |

The headline number is **eval reaches 140 levels** of interpreted expression
nesting — fraction **140/245 ≈ 0.57**, about 1.8 Planes frames per level, so
the evaluator is frame-thrifty. **But the full pipeline is parse-bound at 23
levels**: `parser.planes` spends ~10.7 frames per nesting level, far more than
the evaluator's ~1.8, so when source runs the whole way through, the *parser*
is the bottleneck, not the evaluator. A function call costs ~2.8 frames, so an
interpreted call chain nests ~88 deep.

---

## Environment sizes, lookup cost, and the visible line

Because A.2's model prepends parameters to the *call* environment and passes
the extended list down, the environment **grows with call depth**: at the
deepest frame of an 88-function chain 88 calls deep it holds **~176 live
bindings** (88 functions + 88 accumulated parameters, 87 of them shadowed and
dead). That **exceeds the ~50-entry visibility point** — but only at
pathological depth; a realistic build-1 expression (no control flow) nests a
handful of calls and keeps the environment small.

Worst-case `env-find` lookup (scan to the last binding):

| bindings | 10 | 25 | 50 | 100 | 200 |
|---|---|---|---|---|---|
| ms | 0.05 | 0.11 | 0.21 | 0.53 | 0.83 |

At 50 bindings lookup is 0.21 ms; even at 200 it is under a millisecond. So the
association idiom stays under the visible line for realistic scopes, and only
*approaches* it at maximum interpreted depth — where the cost is the
environment's O(depth) growth, not the per-lookup scan. This is `interp.py`'s
one structural advantage the flat list gives up: `interp.py` gives each call a
fresh `Env(fn.env)`, so its per-frame scope is O(1) in depth. **Finding for
build 2:** prune dead bindings, or thread a separate function table, before
interpreted recursion (build 2's control flow) makes deep call chains routine.

---

## Exact rational verification (A.5 ruling 1)

The metacircular arithmetic — `interp.planes` evaluating `a + b` performs
`a.value + b.value` in Planes, run by the host's own exact-rational operator —
was verified explicitly and agrees with `interp.py` on every case:

| expression | canonical value | a float would give |
|---|---|---|
| `2 / 3` | `~0.666666666666` | `0.6666666666666666` |
| `10 / 4` | `2.5` | `2.5` |
| `1 / 3 + 1 / 3 + 1 / 3` | `1` | `0.9999999999999999` |
| `0.1 + 0.2` | `0.3` | `0.30000000000000004` |

Division, repeated addition, and two cases where a float visibly diverges all
render identically on both sides. The exact-rational form is free precisely
because the Planes side never does arithmetic itself — the host does.

---

## The parser's node representation: clean to consume

Clean. `parser.planes` tags every node with a `kind` string matching the
Python class name (`"Num"`, `"BinOp"`, `"Call"`, …), wrapped in a `{ node,
cursor }` status record from which `interp.planes` reads `.node`. Field names
match the Python dataclasses, with two worth noting:

- `RecordLit.fields` and `RecordUpdate.fields` are a list of `{ key, value }`
  records (not `(name, expr)` tuples) — which is exactly the shape a record
  *value* wants, so consuming it is direct.
- Builtins are `Call` nodes, never a `Builtin` node (`parser.py` never emits
  one either), so the evaluator routes them the way `interp.py`'s `call()` does
  — one code path, not two.
- `Round`'s places field is named `places-value`, read as `node.places-value`.

One source-writing nuance, not a representation problem: `first n of x` and
`round x to n` greedily read a bare-name operand as a call (`n of x`), so a
name operand must be parenthesized (`first (n.value) of …`). The parser corpus
already relies on this (`first (n) of x`); it cost one syntax error to
rediscover.

A bonus consistency result: **`parser.planes` parses `interp.planes` and agrees
with `parser.py`** (27,178 chars, verified out of band). All three Planes
stages now parse each other.

---

## The pipeline result — the first three-stage Planes run

`evaluate-source of src` tokenizes with `lexer.planes`, parses with
`parser.planes`, evaluates with `interp.planes`, and renders — one Planes call,
the only Python in the path being the host running the outermost interpreter.
`"1 + 2 * 3"` goes in; `7` comes out. `"{ x: 1, y: [2, 3] }"` goes in;
`{x: 1, y: [2, 3]}` comes out. `"2 / 3"` goes in; `~0.666666666666` comes out.
`evaluate-with` does the same for an expression against a program's functions:
`double of 21` → `42`. Fourteen fragments and a two-function program run the
whole pipeline and agree with `interp.py` as the oracle.

---

## Where `interp.py` was harder to reproduce than expected

1. **Record values cannot be native records.** Planes cannot build a record
   with runtime field names, so a record *value* is never a native record but a
   tagged `{ kind: "record", fields: [...] }` list of pairs. This is forced, not
   chosen — and it means equality cannot be delegated to the host's `==`,
   because two value records both carry `deriv: nothing`, and `interp.py`'s
   `equal()` refuses `nothing == nothing`. Equality is therefore reproduced
   structurally (`values-equal`), mirroring `equal()` arm for arm.
2. **`in` is lenient where `==` is strict.** `interp.py`'s `in` is Python's
   `in`, which uses `==` and returns `false` across types rather than raising;
   `==` itself is guarded and raises. Membership needed a separate lenient
   compare (`raw-eq`, `values-equal` wrapped in `or fail` → `false`).
3. **`lower`/`upper`/`normalize` coerce via `str()`.** `interp.py` runs
   `str(arg.value)`, which for a non-text value leaks Python's `repr`
   (`str(True)` is `"True"`, a list is its Python repr). Reproduced for the
   sensible inputs (text and number) and refused for the rest — a deliberate
   non-reproduction of a host-repr leak, noted rather than mirrored.
4. **`text of` (fmt) is not the canonical form.** `text of` is `interp.py`'s
   `fmt` — a display summary (`"[n items]"`, `"{record}"`, a string with no
   quotes) — distinct from the structural canonical form, so it needed its own
   reproduction.

None of these blocked the build; each is a case where the value representation
had to do work the host got from Python's type system for free.

---

## §A premise that did not survive baseline

**A.7 stated the ceiling was "196 for `when`-based shapes and 245 for
`if`-based."** Measured at baseline, **both are 245.** `interp.py`'s `When`
case was folded into `exec_stmt` (its comment: "folding halves the per-arm
cost"), and that folding — landed by S2 or a later build — raised the
`when`-based ceiling to match `if`-based. The premise was a report-basis figure
from before that fix, exactly the kind of stale causal claim §A's premise note
and failure mode 8 warn about. Reported, and the build proceeded on the
measured 245.

---

## What this build disproved about the prompt

Never empty.

**The prompt frames the interpreted-depth question around the evaluator's
recursion — but the evaluator is not the constraint.** A.7 says "an expression
evaluator recurses once per nesting level, which is shallow," and asks for
"the usable interpreted depth" as "the load-bearing unknown for builds 2 and
3." Measured: the evaluator reaches **140** levels (0.57 of the ceiling, ~1.8
frames per level) — genuinely shallow, as predicted. But the **full pipeline
caps at 23**, because `parser.planes` spends ~10.7 frames per nesting level, an
order of magnitude more than the evaluator. So the load-bearing unknown for
builds 2 and 3 is not the evaluator's depth at all — it is the **parser's**.
The prompt's instinct that eval is shallow is correct; its framing that eval's
depth is the number to watch is not.

A smaller one: **Phase 4's implicit worry about duplicate record keys is moot.**
`interp.py` builds a record as a dict (last key wins), but the *parser* rejects
a duplicate field at parse time (`field 'x' appears twice`), so a dup-key record
never reaches `eval`. The upsert logic written for it is still needed — for
`with` — but the literal case it was written against cannot occur.

---

## Build 2 scoped: statements and control flow

Build 2 adds the five status rules' statement forms: `if`/`else`, `when`, `let`
and reassignment, `show`, the `for each` statement, `or fail as`, and `fail`.
The evaluator's flat dispatch and the value representation carry over unchanged;
what is new is that statements *sequence* and *branch*, and that a function body
becomes a block rather than a lone `give`.

**Is the interpreted-depth fraction survivable for whole programs?** Partly, and
the constraint has two faces:

- **Nesting** is parse-bound at 23 levels (above). A whole program's expression
  nesting rarely approaches this, so ordinary code is fine — but a generated or
  deeply-nested expression will hit the *parser* first, and build 2 should
  measure interpreted *statement* nesting the same way.
- **Recursion** is the real exposure. Build 2 introduces interpreted control
  flow, so an interpreted *recursive* function spends frames per interpreted
  call level (~2.8 here, more once a body is a block), on top of the host's own
  per-call frames. At 88 interpreted call levels the ceiling is reached — and a
  naively recursive interpreted program (a countdown, a tree walk) will exhaust
  that quickly. Build 2 must either accept that interpreted programs recurse far
  less deeply than programs run directly on `interp.py`, or flatten its own hot
  paths as S3a did — and prune the environment's O(depth) growth (above) so a
  deep call chain does not also carry a 176-binding scope.

The honest summary: expression evaluation is comfortably within the ceiling;
interpreted *recursion* is where build 2 will feel it, and the number to carry
forward is ~2.8 frames per interpreted call, deepening as statement blocks
replace lone expressions.
