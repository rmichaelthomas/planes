# Value-Model Semantics — Session Report

**Date:** July 23, 2026
**Session type:** Implementation. Three locked decisions from the opening question — what are the values, and what can you do with them.
**Mandate:** Scope-walking assignment (V-Q5), record literals (v2.0 §35), and equality through the guard `<` already uses (V-Q1), which also retires `truthy` as a third notion of sameness.
**Result:** Built. 333/333 tests passing (309 prior + 24 new). `gate.planes` runs clean. Two existing test fixtures changed, both intentional and reported below.

---

## 1. The Decisions

### V-Q5 — assignment rebinds where the name is already bound

`Env.set` used to always write to the current scope. `eval_foreach` builds a
fresh `Env` per iteration, so `total = total + p.owed` inside a loop read the
outer `total` correctly and then discarded the write. Accumulation across a
loop was impossible, and `if` (which reuses the outer env directly) disagreed
with `for each` about whether assignment escapes.

`Env.set` now walks the parent chain and rebinds wherever the name already
lives, falling to a local bind only for a genuinely new name. `let` is the
explicit local-shadow marker — `Env.bind_local` always binds in the current
scope, which is what a function parameter and a loop variable need: without
it, a parameter that happens to share a name with a variable in the closure
would rebind the closure's copy instead of shadowing it. Both `invoke` and
`eval_foreach` now use `bind_local` for exactly that reason.

### Records — literals, not just JSON

Every record in the language arrived from `from_foreign` — a program could
read a record but never write one. `{ first: "Ada", last: "Lovelace" }` now
parses and evaluates directly, nesting arbitrarily since a field's value is
an ordinary expression (v2.0 §35 falls out for free rather than needing
separate handling).

### V-Q1 — equality through the same guard `<` uses

`compare()` already refuses `5 < "5"` with `cannot-compare`, naming both
values. `==` and `!=` bypassed it entirely, computing raw Python `a == b` —
so `5 == "5"` was a silent, well-typed `false`. The reasoning that mattered:
Planes has `why`, and a derivation exists to answer *what combined to make
this value*. A `false` from a cross-type comparison is true about the
computation and useless about the mistake, and it enters the derivation
graph as a fact indistinguishable from an intended comparison. The number
model already refuses rather than rounds silently past `MAX_DENOMINATOR`;
equality now refuses rather than answers. Numbers are the sole
cross-representation exception (`1 == 1.0` is `true`) because they are one
value under two spellings, not two types.

`nothing == nothing` is now also an error — `nothing` carries no shape to
compare, so the fix is a new `is nothing` test, not a comparison. Since
`truthy` was a third, looser notion of sameness (`truthy(0)` is `false` but
`0 == false` is now an error), leaving it in place while tightening `==`
would have traded one inconsistency for a subtler one. `if`, `where`, `and`,
`or`, and `not` all now route through a new `condition()` guard requiring an
actual yes/no value. `truthy` itself is deleted, not merely unused — the
strongest available proof that no path still reaches it.

---

## 2. Three Things Found During the Build, Fixed in the Same Build

Per the standing term from the prior session (a gap named in a report is
fixed in the build that names it): three real gaps surfaced while making the
gate program runnable, none of them part of the four locked decisions, all
of them blocking `gate.planes` from working at all.

### Multi-line bracketed literals didn't parse

The tokenizer emits `BEGIN`/`END` purely from physical-line indentation, with
no awareness of bracket nesting. A list or record literal spanning indented
lines — exactly the shape `gate.planes` requires for its `people` list —
picked up stray `BEGIN`/`END` tokens neither `[...]` nor the new `{...}`
handling accounted for. Added `Parser.skip_bracket_ws`, which consumes
`EOL`/`;`/`BEGIN`/`END` uniformly inside brackets (brackets already carry the
structure; the indentation tokens mean nothing there), used at the same three
points in both `[` and `{` handling. Trailing commas fell out of the same
fix for both list and record literals.

### `.first` didn't parse on any record, ever

`parse_postfix` required `NAME` after a dot; `first` (like `round`, `to`,
`from`, and every other reserved word) tokenizes to its own kind, so
`person.first` failed to parse — for a JSON record fetched over the network
exactly as much as for a literal. This predates this build entirely; it
surfaced because the required gate program reads `person.first`. Fixed by
accepting any token whose value is a reserved word, not just `NAME`, after a
dot — a field name is not a position where a keyword can be structural,
matching the reasoning already used for record-literal keys.

### `is` stays unreserved

The build prompt's own risk note flagged this and asked for `test_names.py`
to be checked before proceeding. It failed: `test_reserved_list_is_only_
structural_words` enforces a hard ceiling of 30 with an explicit rationale —
"a rise is only legitimate when the word has no other spelling" — and the
same test's docstring records the established answer for exactly this
situation: `may` is recognized positionally inside `parse_rule`, never
reserved, so a program that never writes `rule` still has `may` free as a
name. `is` now works the same way — recognized positionally in
`parse_comparison` only when it sits where a comparison operator could —
so `is nothing` parses and `is` remains available as an ordinary function or
variable name. Reserved list stays at 30.

---

## 3. Two Judgment Calls Not Fully Scripted

**`not` routes through `condition()` too.** The build prompt's site list for
replacing `truthy` named `if` (both sites) and `where`, and separately said
`and`/`or` route through `condition`. It did not name `not`. But invariant 2
says plainly: "no path may reach truthy" — and `Not`'s implementation was
`not truthy(v.value)`. Left alone, `truthy` would still be one call away.
Checked every use of `not` in the repo first: all two (`not false`, both in
tests) are already boolean literals, so there was nothing to break. Routed
`not` through `condition()` for the invariant to hold as stated rather than
as approximately true.

**Copy-by-default is not weakened, because there is nothing to weaken it
against.** The build prompt asked for a stop-and-report if record-literal
assignment does not currently copy. It does not — no dict is ever copied
anywhere in this interpreter, for records arriving from JSON exactly as much
as for record literals. But there is also no field-mutation syntax anywhere
in the parser — only `NAME =` and `let NAME =` exist as assignment targets.
With no way to write through one alias and observe it through another,
sharing the underlying dict is an implementation detail, not an aliasing
violation: `p2 = p1` already shares `p1`'s dict today, and `{ a: existing }`
shares `existing`'s dict the same way. Verified directly — `inner_dict is
outer['a']` is `True` for both the pre-existing case and the new one. Not
treated as a stop condition since record literals introduce no new path,
merely reach the existing one from one more syntax.

---

## 4. What Changed in the Language

- `total = total + n` inside `for each` now accumulates; `let` shadows locally.
- Function parameters and loop variables always bind locally (`bind_local`),
  even when they share a name with something in the closure.
- `{ field: expr, ... }` record literals — nest arbitrarily, trailing comma
  accepted, duplicate keys are a syntax error, keyword-shaped field names
  (`to`, `from`, `first`, ...) work as both keys and as `.field` access.
- List and record literals may now span multiple indented lines.
- `==`/`!=` raise `cannot-compare` on cross-type operands, naming both —
  except numbers, which compare across representations (`1 == 1.0`).
- `nothing == nothing` is an error; `x is nothing` is the replacement.
- `if`, `where`, `and`, `or`, `not` all require an actual yes/no value,
  raising `not-a-yes-no` otherwise. `truthy` is deleted.

Everything else is unchanged — the rule plane, the four relations,
actions-not-calls, the four declaration sites, the effect vocabulary, and
generated markers were not touched, per unbound v3.1 §54's exclusion list.

---

## 5. What Existing Tests Changed, and Why

Two assertions, both in `test_shapes.py`'s `ADVERSARIAL` fixtures, both
relying on truthy coercion of a non-empty list as a loop condition:

- `"effect in a where-clause"` — `probe of i` returned a raw list from
  `ask`; `where probe of i` depended on a 3-item list being truthy. Changed
  the function body to `count of (ask ...) > 0`, an honest yes/no value,
  preserving exactly what the case tests (an effect hidden inside a
  `where`-clause still gets caught by the static analyser).
- `"effect in an if-condition"` — the same shape, same fix, inside `if`.

Both changes preserve the test's stated intent; neither weakens what the
adversarial suite checks. Two new `test_coverage.py` entries were added
(`RecordLit`, `IsNothing`) because that file's own oracle requires one case
per AST node — not a changed assertion, a required addition for two new
node types.

No other existing test's assertion changed.

---

## 6. What Is Not Built

- **Record field mutation.** There is still no `x.field = value` syntax —
  records remain read-only once constructed, exactly as before this build.
  This is why the copy-by-default question in §3 has no observable answer
  yet; the day a mutation primitive is added, aliasing stops being free.
- **List literal mutation or a `for` that writes back.** Out of scope here
  and untouched.
- **A general defaulting idiom.** `x or "default"` never existed in this
  repo (checked: zero occurrences in `.planes` files and test sources
  outside literal-boolean cases) and still doesn't — `or` now requires both
  operands to be yes/no.
- **Everything unbound v3.1 §54 parked**: the rule plane, the four
  relations, actions-not-calls, the four declaration sites, the effect
  vocabulary, generated markers.

---

## 7. Recommendation for the Next Session

**Field-name generality deserves a second look.** Record-literal keys accept
a curated list of 13 keyword-shaped words (matching the build prompt's given
code); field *access* now accepts any reserved word at all, found necessary
mid-build to make `person.first` parse. The asymmetry is harmless today
(you can already read `.round` or `.rule` off foreign JSON; you cannot yet
*write* a literal with those keys) but is worth naming as a deliberate,
recorded choice rather than leaving it implicit.

**A checkpoint is owed** recording V-Q1 and V-Q5 as locked (per this
session's provenance note), plus the two build-time findings in §2 — the
multi-line-literal gap and the `.first` field-access gap both predate this
build and were fixed here because the gate required it, not because they
were in scope on their own.

---

## 8. Test Summary

```
test_planes.py       50/50    language
test_numbers.py      31/31    exactness, rendering, rounding, boundaries, limits
test_shapes.py       72/72    analyser, modules, namespacing, oracle
test_names.py        15/15    reserved-word ceiling, shadowing
test_rules.py        63/63    rule plane, permits, vacuous rules
test_foreign.py      37/37    FFI, effect declarations
test_host.py         14/14    host boundary
test_coverage.py      7/7     AST-node oracle coverage
test_assertions.py   20/20    unearned-assertion guard
test_values.py       24/24    this build — binding, records, equality
                     --------
                     333/333

Baseline was 309, not the 289 stated in the build prompt — the 289 figure
predates the prior session's test_assertions.py (20 tests), which already
landed at HEAD (4c0e190) before this build started. Reconciled by measuring
the actual repo state rather than trusting the stated number; recorded here
so the discrepancy is visible rather than silently absorbed.
```

Anti-drift greps still clean. `rules.py` and `shapes.py` untouched.
`verify_values.py` (committed to the branch) reproduces all of the above.
