# PROBE_LEXER.md — Phase 0 capability probe

**Build:** The lexer, written in Planes (Route B stage one)
**Base:** `main` at `24a0f65`
**Purpose:** answer, empirically, whether Planes can walk a string one code
point at a time — the load-bearing unknown the build prompt names as unsettled
by v9.0 §105/§105.1. This phase is blocking: per the build prompt, if
capability 1 or 2 comes back MISSING, the build stops here and the finding
*is* the deliverable.

All six probes live under `probe/` and were run as
`python3 planes.py probe/<name>.planes` against this repo, unmodified, at
`24a0f65`.

A note on the transcripts below: `planes.py`'s CLI prints every `show`d line
twice — once live, from `host.show` during execution, and again from the
CLI's own `for line in lines: print(line)` over the interpreter's returned
output. This is pre-existing behavior, present on every fixture in the repo
(verified against `ordinary.planes`, which also prints its one `show` line
twice), not an artifact of these probes. Transcripts are reproduced exactly
as printed.

---

## 1. Walk a string

**Question:** does `for each c in some-string:` iterate code points, or does
it error?

**Program (`probe/walk_string.planes`):**

```
s = "abc"
for each c in s:
  show c
```

**Result, verbatim:**

```
error — not-a-collection: cannot loop over abc
  try: for each needs a list
(exit: 1)
```

**Why:** `eval_foreach` (`interp.py:779-784`) checks
`isinstance(source.value, (list, tuple))` before iterating and raises
`PlanesError("not-a-collection", ...)` immediately if the source is
anything else, strings included. There is no separate code path for text.

**Verdict: MISSING**

---

## 2. Take a character at a position

**Question:** is there any way to get the *n*th code point? `first n of`
gives a prefix — is there a drop, a rest, a slice, an index?

**Program (`probe/index_string.planes`):**

```
s = "abc"
c = s[1]
show c
```

**Result, verbatim:**

```
abc
abc
(exit: 0)
```

No error — which is worse than an error. Parsing the AST directly shows why:

```
Assign Assign(name='s', expr=Str(value='abc'), ...)
Assign Assign(name='c', expr=Var(name='s'), ...)
ListLit ListLit(items=[Num(value=1)])
Show Show(expr=Var(name='c'), ...)
```

`c = s[1]` does not parse as indexing at all. `parse_primary` returns
`Var("s")` for a bare name not in `known_funcs` with no postfix handling for
`[` (there is no postfix-index production anywhere in `parser.py`), so the
assignment statement completes as `c = s` — binding `c` to the *whole
string*, not a character. The leftover `[1]` tokens are then read as a
second, independent statement: a list literal `[1]`, evaluated and silently
discarded because nothing binds, shows, or asserts it. `c` ends up `"abc"`,
not `"b"`, and nothing signals that this happened.

Beyond this specific misparse, the grammar has exactly one string-extraction
primitive: `first n of x` (`parser.py:986-993`), a single fixed production —
number, `of`, expression. No offset parameter, no `last`, no `drop`, no
`rest`, no general slice. `first 1 of s` yields only the code point at
position 0 (confirmed: `test_text.py`'s
`test_first_of_string_returns_a_string`). No construct in the language
yields the code point at any position other than 0 without already holding
a string that starts there — which is exactly what advancing through a
string one character at a time would require, and exactly what is missing.

**Verdict: MISSING**

---

## 3. Compare characters

**Question:** does `c == "a"` work? Does `c >= "0" and c <= "9"` order code
points?

**Program (`probe/compare_chars.planes`):**

```
c = "a"
show c == "a"
d = "5"
show d >= "0" and d <= "9"
```

**Result, verbatim:**

```
true
true
true
true
(exit: 0)
```

(Two `show` statements, each printed twice by the CLI — see the header note.)

**Verdict: WORKS.** `compare()` (`interp.py:972-984`) orders same-type
values with Python's native `<`/`>`/`<=`/`>=`, which for `str` is code-point
order; `equal()` handles `==`/`!=` for same-type values without normalizing.

---

## 4. Accumulate a list immutably

**Question:** does `tokens plus new-token` grow a list as v5.0 §72 says?

**Program (`probe/accumulate_list.planes`):**

```
tokens = []
new-token = "x"
tokens = tokens plus new-token
tokens = tokens plus "y"
show tokens
```

**Result, verbatim:**

```
[2 items]
[2 items]
(exit: 0)
```

`show` on a list prints a `[N items]` summary rather than its contents —
confirmed as standard rendering (`python3 planes.py -e 'xs = [1, 2, 3]; show
xs'` also prints `[3 items]`), not a probe artifact. Reading the bound value
directly confirms the actual contents: `i.env.get("tokens").value ==
['x', 'y']`.

**Verdict: WORKS.**

---

## 5. Build and read records

**Question:** `{ kind: "NAME", text: t }`, then `.kind` and `.text`.

**Program (`probe/records.planes`):**

```
tok = { kind: "NAME", text: "total" }
show tok.kind
show tok.text
```

**Result, verbatim:**

```
NAME
total
NAME
total
(exit: 0)
```

**Verdict: WORKS.**

---

## 6. Dispatch on shape

**Question:** `when tok is { kind: "OP" }:` — the §74 mechanism shipped at
#8.

**Program (`probe/dispatch_shape.planes`):**

```
tok = { kind: "OP", text: "+" }
when tok is { kind: "OP" }:
  show "operator"
else:
  show "other"
```

**Result, verbatim:**

```
operator
operator
(exit: 0)
```

**Verdict: WORKS.**

---

## Summary

| # | Capability | Verdict |
|---|---|---|
| 1 | Walk a string | **MISSING** |
| 2 | Take a character at a position | **MISSING** |
| 3 | Compare characters | WORKS |
| 4 | Accumulate a list immutably | WORKS |
| 5 | Build and read records | WORKS |
| 6 | Dispatch on shape | WORKS |

## Verdict on Phase 0, and what happens next

**Capabilities 1 and 2 are both MISSING.** Per the build prompt's own
blocking rule (§1): *"If capability 1 or 2 is MISSING, stop and report...
Do not invent a workaround. Report it, and stop."*

This is not a narrow gap in one corner of the grammar. Four of the six
probed capabilities (3, 4, 5, 6 — comparison, accumulation, records, shape
dispatch) work cleanly and would carry a lexer's token-building and
classification logic without friction. What is absent is the one thing that
sits underneath all of it: a way to advance through a string's code points
one at a time. `for each` refuses non-list sources outright, and the only
string-extraction primitive the grammar has — `first n of` — returns a
growing *prefix*, never an isolated character at an arbitrary position, and
there is no complementary operation (`rest`, `drop`, `last`, a slice, an
index) to turn a prefix into "the one new character plus what's left."

A lexer's innermost loop — look at the current code point, decide what kind
of token starts here, consume characters until the token ends, repeat from
the next position — has no expression in the language as it stands at
`24a0f65`.

**Per the build prompt's provenance section, this voids Phases 1-4.** No
workaround is written; per invariant 1 (§6) and failure mode 1 (§7), a
language gap is a finding, not a build obstacle to route around by adding a
builtin or changing `interp.py`. What would closing this gap actually take?
Not a large one: a single new distinctive-syntax construct in the shape of
`first`/`round` — something like a `rest n of x` (the complement of `first`,
returning everything after the first *n* elements/code points, for both
strings and lists) — plus a lexer/parser/interp change to support it. That
is a small, well-scoped language change, not a rewrite; but it *is* a
language change, and this build's mandate is explicit that language changes
are out of scope and belong in a gap inventory, not a commit.
