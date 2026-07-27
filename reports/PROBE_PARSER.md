# PROBE_PARSER.md — the parser's capability probe

**Build:** feat/fail-primitive-and-parser-probe (Phase 3)
**Base:** `main` at `d7687f7`, then this build's own Phase 1 (`planes_text.py`)
and Phase 2 (`fail <message> as <tag>`) commits
**Purpose:** answer, empirically, what a parser written in Planes — Route B
stage two — would need, and which of those needs the language already meets.
**Not blocking.** Per §6, a MISSING verdict here is a finding, not a stop
condition; this phase's whole output is the inventory itself. This phase does
not write a parser.

All probes live under `probe/parser/` and were run as
`python3 planes.py probe/parser/<name>.planes` against this repo at this
build's Phase 2 commit. Per `PROBE_LEXER.md`'s header note, `planes.py`'s CLI
prints every `show`d line twice (once live during execution, once from the
CLI's own loop over the returned output) — pre-existing, not a probe artifact.
Transcripts are reproduced exactly as printed, once per distinct probe run.

---

## 1. Recursion to fixed depth

**Question:** can a `to` function call itself? How deep before anything
breaks, and what breaks — a Planes error or a Python `RecursionError`
leaking through?

**First attempt, and a real finding before the intended one.** The obvious
program —

```
to countdown of n:
  if n <= 0:
    show "done"
  else:
    countdown of n - 1

countdown of 5
```

— overflowed the Python stack at `n = 5`, not a depth problem. Reading the
parsed AST directly:

```
els=[BinOp(op='-', left=Call(name='countdown', args=[Var(name='n')], line=5), right=Num(value=1))]
```

`countdown of n - 1` parses as `(countdown of n) - 1`, not `countdown of
(n - 1)`: `of`'s argument binds to a single unary-precedence primary, so the
trailing `- 1` attaches to the *call's result*, not inside the argument.
`countdown` is called with the same, never-decreasing `n` forever. This is
exactly why `render.py`'s canonical renderer parenthesises every call
argument (`name of (arg1), (arg2)`, its own module docstring) — not a style
preference, a precedence fact a parser (and any Planes programmer) must get
right. **Corrected:**

```
to countdown of n:
  if n <= 0:
    show "done"
  else:
    countdown of (n - 1)

countdown of 5
```

**Result, verbatim (`probe/parser/recursion_depth.planes`):**

```
done
done
(exit: 0)
```

**The actual depth question**, checked directly against the interpreter
(Python's default `sys.getrecursionlimit()` of 1000, unmodified): a binary
search over `countdown of N` found **the last depth that succeeds is 140;
141 raises a raw, uncaught `RecursionError`** — not a `PlanesError`, not any
Planes-shaped failure. `interp.py`'s call chain
(`exec_stmt → eval → eval_binop/eval → call → invoke → exec_block → exec_stmt`,
read directly from the traceback) costs roughly 1000 ÷ 140 ≈ 7 Python stack
frames per one level of Planes-level recursion, and nothing in `interp.py`
catches `RecursionError` anywhere — confirmed by grep, zero hits.

**Verdict: WORKS WITH FRICTION.** Recursion itself works cleanly and
correctly for realistic depths. Two frictions: (1) a naked arithmetic
expression in a call argument silently means something other than what it
looks like — the language works as specified, but the specification is easy
to get wrong without already knowing to parenthesise; (2) the depth ceiling
(~140 at Python's default limit) is real, and exceeding it is an unhandled
host-language crash, not a Planes error a program (or a future `fail`-based
error handler) can catch or report cleanly.

---

## 2. Mutual recursion

**Question:** can two `to` functions call each other, including a forward
reference (the earlier-defined function calling the later-defined one)?

**Program (`probe/parser/mutual_recursion.planes`):**

```
to is-even of n:
  if n == 0:
    give true
  else:
    give is-odd of (n - 1)

to is-odd of n:
  if n == 0:
    give false
  else:
    give is-even of (n - 1)

show is-even of 10
show is-odd of 10
```

**Result, verbatim:**

```
true
false
true
false
(exit: 0)
```

**Verdict: WORKS.** `is-even`'s body references `is-odd`, defined later in
the source — resolves cleanly, because `to` definitions register into
`self.funcs` as ordinary top-level statements execute in order, before the
final `show` calls either one; nothing about definition order inside the
mutual pair matters once both are registered before use.

---

## 3. Returning a record with a payload and a position

**Question:** a parse step returns *(node, next-index)*. Does a record
carrying a node and a cursor round-trip through a call cleanly?

**Program (`probe/parser/record_payload_and_position.planes`):**

```
to make-result of node, next-index:
  give { node: node, index: next-index }

to advance of r:
  new-node = r.node + "-advanced"
  give make-result of new-node, (r.index + 1)

r1 = make-result of "some-node", 5
r2 = advance of r1
show r1.node
show r1.index
show r2.node
show r2.index
```

**Result, verbatim:**

```
some-node
5
some-node-advanced
6
some-node
5
some-node-advanced
6
(exit: 0)
```

**Verdict: WORKS.** Both fields survive a full round trip through two
function calls; `r1` is untouched by `advance` building `r2` (record
immutability, v5.0 §72, holding exactly as elsewhere). Confirms multi-field
records pass through calls, and multi-argument calls with bare
comma-separated arguments (`make-result of new-node, (r.index + 1)`) parse
correctly.

---

## 4. A cursor over a token list

**Question:** with no indexing (declined at #11 and vindicated for the
lexer), how does a parser advance? Establish the idiom.

**The idiom that works, and the scale trap sitting right next to it.**
`grammar/lexer.planes`'s own indent stack already proves the shape: a
cons-list of records (`{ head: x, rest: <cons-or-nothing> }`) gives O(1)
"look at the front" and "drop the front" via ordinary field access — `.rest`
has none of `first n of`'s prefix-only limit, because it is not indexing at
all.

**Program (`probe/parser/cursor_idiom.planes`)** builds one from a plain
Planes list (`to-cons`, via `reverse-into` then a recursive `unreverse` to
restore source order — `for each` only ever walks forward, so a single pass
naturally builds the list in reverse), then exercises `current`/`advance`/
`at-end` and a small recursive `drain` that rebuilds a plain list one item
at a time via `plus`:

**Result, verbatim (4-item list):**

```
10
20
false
[4 items]
4
10
20
false
[4 items]
4
(exit: 0)
```

Confirmed directly (not just by the `[4 items]` summary): `drained ==
items == [10, 20, 30, 40]`, exact content match, not merely matching count.

**The trap:** both `unreverse` and `drain` recurse once per list item.
Capability 1 found the ceiling at 140. Checked directly: `drain` (and
`unreverse`, inside `to-cons`) over a **200**-item list raises
`RecursionError` — well inside real file sizes (`grammar/lexer.planes`
self-tokenizes to 3835 tokens, per `lexer-in-planes-verification.md`).
**The cons-list cursor is correct at any scale but cannot be *built* or
*fully drained* by per-item recursion at real token-stream sizes.**

**The idiom that actually scales**, checked directly
(`probe/parser/cursor_scales.planes`, 200 tokens — comfortably past the
140-item ceiling — and additionally verified to 20,000 tokens against the
interpreter directly, not committed as a literal): a single `for each` pass
over the *original Planes list* (a host-language loop, so it costs zero
Planes-level recursion depth regardless of list length) threading a state
record that carries a cons-list **stack** for nested structure — exactly
`grammar/lexer.planes`'s indent-stack shape, generalised from tracking
indentation to tracking arbitrary nesting. The stack is pushed and popped
one element at a time (O(1) field construction, never walked in full), so
its own depth is not bounded by the recursion ceiling either — verified with
a stack that grows to depth 10,000 without incident, in the same scale
check.

**Result, verbatim (`cursor_scales.planes`, 200 tokens, alternating
open/close so nesting depth never exceeds 1):**

```
200
1
0
200
1
0
(exit: 0)
```

**Verdict: WORKS WITH FRICTION.** The cons-list-of-records idiom for a
forward cursor is correct and directly analogous to `lexer.planes`'s own
proven indent-stack pattern. But the naive way to *use* it — recursive
descent that materialises "the rest of the tokens" once and recurses per
token consumed — hits the depth ceiling well within real file sizes. The
idiom that scales is closer to the lexer's own architecture than to
textbook recursive descent: **one `for each` pass over the whole token
list, threading a state record whose nested-structure tracking (a shallow
stack, bounded by grammar nesting depth, not token count) is where the
cons-list pattern belongs** — recursion reserved for genuinely
grammar-nesting-bounded structure (capability 6, and site 3's bracket
matching below), never for a loop over the token stream itself.

---

## 5. Building a nested tree

**Question:** records containing lists containing records, several levels
deep, then reading a leaf back out.

**Program (`probe/parser/nested_tree.planes`)** builds a 4-level tree
(`program.body` → a block record → `.statements` → a binop record →
`.left`/`.right` → leaf number records) and reads a leaf value back out
through every level, using `for each … where` to pick a specific element
out of each list (since `first n of` always returns a list, even for `n =
1` — reading a *specific* element back out uses the same proven `for each`
idiom as everywhere else, not an index that does not exist for records any
more than for strings or lists).

**Result, verbatim:**

```
block
binop
+
1
2
block
binop
+
1
2
(exit: 0)
```

**Verdict: WORKS.** Nesting to 4 levels (records-in-lists-in-records-in-
lists) builds and reads back correctly, with no depth limit encountered at
this scale — an AST is built once per parse (not per token, unlike
capability 4's per-item recursion), so its shape does not interact with the
depth-140 ceiling the same way a token-count-scaled loop does.

---

## 6. Raising a parse error with a message

**Question:** the Phase 2 primitive (`fail … as …`), exercised from a `to`
function nested a few calls deep. Does it propagate to the top?

**Program (`probe/parser/nested_fail_propagation.planes`)** chains nine
functions named after `parser.py`'s actual precedence levels —
`parse-program → parse-statement → parse-expr → parse-comparison →
parse-additive → parse-multiplicative → parse-unary → parse-postfix →
parse-primary` — where `parse-primary` is the only one that does anything:
`fail "unexpected token" as parse-error`.

**Result, verbatim:**

```
error — parse-error: unexpected token
(exit: 1)
```

**Verdict: WORKS.** Propagates cleanly through all nine levels (a *fixed*
chain depth, unrelated to capability 1's ceiling, which only bites *self*-
recursion scaled to input size — a fixed-depth precedence chain of even
`parser.py`'s actual ~10 levels costs a small, constant number of Python
frames, nowhere near 140). No handler anywhere in the chain: `run()` itself
receives the `PlanesError`, exactly the same as any other uncaught failure,
confirmed directly rather than assumed from Phase 2's `test_fail.py`
coverage of the same shape at a shallower depth.

---

## 7. Amber's four sites

**Question, per phase 3's framing:** for each of the four guess sites, what
would a Planes parser have to decide? This is the research question, not a
coding task — a written statement per site, not an implementation.

**One shared prerequisite, found while reading all four sites together, not
assumed:** every one of `parser.py`'s four amber checks
(`raise_amber_multiword` / site 1, `check_juxtaposition_ambiguity` / site 2,
`check_paren_arglist_ambiguity` / site 3, `check_rename_name_ambiguity` /
site 4) looks up a **dynamically-built string** — accumulated token text,
not a name known when the parser's own source was written — against
`Parser.known_funcs`, a `{name: arity}` table. Checked directly whether
Planes can do this at all: `r.k` reads the field *literally* named `"k"`
(confirmed: returns `nothing` against `{a: 1, b: 2}` even though `k = "a"`),
and `r[k]` / `r["a"]` are both flat syntax errors — *"Planes has no index or
slice syntax"* — for records exactly as for strings and lists (#11).
**Planes has no dynamic, string-keyed lookup into a record at all.**

The workaround, checked directly (`probe/parser/dynamic_lookup.planes`):
represent the table as a **list** of `{name, arity}` records and do a
linear `for each … where entry.name == key` scan. Correct
(`lookup of known-funcs, "word count"` → `1`; `lookup of known-funcs,
"nonexistent"` → `nothing`), built from nothing but already-proven
capabilities (`for each`, `==`, records, lists) — O(*n*) instead of a
hash table's O(1), a real but non-blocking cost for a table sized in the
tens to low hundreds of entries a real program's `known_funcs` would hold.
Every site below inherits this same fix; it is stated once here, not
re-derived per site.

Real, verified-firing fragments and their actual refusal text (not
paraphrased), one per site:

### Site 1 — multiword name ambiguity (`raise_amber_multiword`)

**Fragment** (`test_amber.py`'s own `test_site1_fires_when_a_shorter_and_
longer_name_both_match`):
```
to word:
  give 1

to word count:
  give 2

r = word count
```
**Refusal, verbatim:**
```
line 7: two readings are possible here, and nothing says which

  reading A:  word  then  count
              the value `word`, then whatever parses next on its own
  reading B:  word count
              one call to `word count`

both `word` and `word count` are defined, so the parser will not choose between them
try: parenthesise the one you mean -- `(word count)` -- or rename one of the functions so only one reading is possible
```

**What a Planes parser has to decide:** on a bare `NAME` token, look ahead
across every immediately-following `NAME` token (the cursor idiom,
capability 4 — `current`/`advance`, never consuming until the decision is
made), and for **every** prefix length `k = 0, 1, 2, …` — not just the
first or the longest — build the joined text (string concatenation, proven
by `PROBE_LEXER.md` capability 3) and look it up in the known-funcs table
(the dynamic-lookup workaround above). Collect every hit into a list
(`plus`, proven), and once lookahead stops, if `count of hits >= 2`, build
an amber-shaped message enumerating every reading — a loop over the hits
list, concatenating a letter (`A`, `B`, …), the reading's own text, and a
gloss per entry — and `fail` it (Phase 2). Nothing here exceeds already-
proven capabilities plus the shared dynamic-lookup workaround; the
`k = 0, …` lookahead loop is the one piece with no direct precedent in
`lexer.planes` (which never needed unbounded NAME-token lookahead — its
own name-continuation logic is a single-character decision, not a
multi-token one), but capability 4 established that peek/advance over a
cons-list is exactly this shape.

### Site 2 — juxtaposition ambiguity (`check_juxtaposition_ambiguity`)

**Fragment** (`test_amber.py`'s `test_site2_fires_when_head_takes_an_arg_
and_the_next_name_is_zero_arity`):
```
to main:
  give 1

r = ask main
```
**Refusal, verbatim:**
```
line 4: `ask main` reads two ways, and nothing says which

  reading A:  ask (main)
              one call to `ask`, passing the result of calling `main`
  reading B:  ask  then  main
              `ask` with no argument, then a separate call to `main`

`ask` takes an argument and `main` is also a defined function, so the parser will not choose between them
try: `ask (main)` to call `main` first and pass its result to `ask` -- or write them as two separate statements if you meant them apart
```

**What a Planes parser has to decide:** simpler than site 1 — given a
known function name immediately followed by a second bare `NAME`, look up
**both** names' arities (the same dynamic-lookup workaround) and branch on
the pair: head arity 0 → never ambiguous (no argument is ever considered);
next name not in the table → unambiguously the argument; next name found
with arity 0 → both readings fit, refuse; otherwise → unambiguously the
argument. Three-way branching over two lookups — ordinary `if`/`else`
(proven throughout this and every prior probe), no new capability beyond
the shared workaround.

### Site 3 — paren-arglist ambiguity (`check_paren_arglist_ambiguity`)

**Fragment** (`test_amber.py`'s `test_site3_fires_when_arity_is_exactly_
one`):
```
use http
to base:
  give "https://example.com"

x = ask (base) + "/x.json"
```
**Refusal, verbatim:**
```
line 5: two readings are possible here, and nothing says which

  reading A:  ask(base) + "/x.json"
              one call to `ask`, argument = everything up to and including `+ "/x.json"`
  reading B:  (ask(base)) + "/x.json"
              one call to `ask`, argument = `base` alone; `+ "/x.json"` applies to the call's result, not inside it

`ask` takes exactly one argument, so both readings have the right shape
try: `ask(base)` with nothing after the parens on this call, or restructure so `ask` clearly applies to just one thing
```

**What a Planes parser has to decide, and the one genuinely new piece
beyond the shared workaround:** the message itself needs the *source text*
between the matching parens (`paren_src`) and the *source text* of
whatever trails the closing paren (`rest_src`) — not just a yes/no
ambiguity verdict. That needs two things nothing in probes 1–6 directly
established: (a) **bracket matching** — walk the cursor forward from the
opening `(`, counting depth (`+1` per `(`, `-1` per `)`), stopping when
depth returns to 0, to find the matching close; a small counting loop over
the cursor idiom (capability 4), bounded by the *paren nesting depth of
one call's argument*, not token count, so it does not reach anywhere near
the depth-140 ceiling for realistic source; and (b) **rendering a token
span back to readable text** — concatenating each token's own text with a
space between, across however many tokens sit inside the parens. Neither
is exercised by any prior probe, but both reduce directly to already-
proven pieces (cursor idiom, string concatenation, `for each`) with no
capability this build found missing — just more assembly than sites 1–2
need.

### Site 4 — rename-clause ambiguity (`check_rename_name_ambiguity`)

**Fragment** (`test_amber.py`'s `test_site4_fires_on_an_ambiguous_rename_
source`):
```
use cache with load record as cached load
```
(with both `load` and `load record` in the used module's exported names)

**Refusal, verbatim:**
```
line 1: `load record` reads two ways, and nothing says which

  reading A:  load | record
              `load`, leaving `record` unaccounted for
  reading B:  load record
              `load record` alone

more than one exported name matches this text, so the parser will not choose between them
try: rename to match only one exported name exactly -- a shorter or longer phrase
```

**What a Planes parser has to decide:** check *every prefix* of an
already-fully-consumed multi-word name against the export table (the
dynamic-lookup workaround, again) — `parser.py`'s own implementation gets
the parts via `name.split(" ")`, a **string-split operation Planes has no
builtin for at all** (checked against the 8-builtin closed set:
`count`/`lower`/`upper`/`text`/`whole`/`ask`/`read`/`normalize` — none
splits). **Not a gap this build is reporting**, though: `read_multiword_
name` (the function that built the joined string in the first place)
already walked the name token-by-token before joining it — a Planes-native
rewrite would keep the individual token texts as a list (via `plus`) from
that point, never re-joining and re-splitting a string it already had in
parts. The Python implementation's specific data-structure choice (join
now, split later) does not transfer; the *problem* — checking every prefix
of a multi-word name against a table — is fully solvable with capabilities
already proven, once the source keeps `parts` as a list instead of a
string. Worth stating precisely because it is exactly the kind of thing a
line-by-line port would trip on without ever needing to.

---

## Summary

| # | Capability | Verdict |
|---|---|---|
| 1 | Recursion to fixed depth | **WORKS WITH FRICTION** (140-deep ceiling, `RecursionError` leaks uncaught; `of` binds tighter than `-`) |
| 2 | Mutual recursion | WORKS |
| 3 | Record with payload + position | WORKS |
| 4 | Cursor over a token list | **WORKS WITH FRICTION** (cons-list idiom correct; must be built/consumed via `for each` + shallow stack, not per-token recursion) |
| 5 | Nested tree | WORKS |
| 6 | Raising a parse error, nested | WORKS |
| 7 | Amber's four sites | Written per-site above; shared prerequisite (dynamic record lookup) MISSING, workaround verified WORKS WITH FRICTION |

**Nothing here is MISSING outright** — every capability a parser needs has
either a direct answer or a verified, capability-preserving workaround. Two
frictions recur across every "WORKS WITH FRICTION" and all four amber
sites: **the ~140 recursion ceiling binds any per-token recursive
algorithm, and Planes has no dynamic/string-keyed record lookup at all** —
both worked around (an iterative `for each` + shallow-stack idiom; a
linear-scan list-of-records table) with capabilities this build and its
predecessors already proved, at the cost of O(*n*) lookups instead of
O(1) and a parser architecture closer to the lexer's single-pass fold than
to naive textbook recursive descent.

See `REPORT_FAIL_AND_PARSER_PROBE.md` for the scoped build estimate this
inventory supports.
