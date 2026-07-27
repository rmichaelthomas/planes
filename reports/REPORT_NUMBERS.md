# The Numeric Tower — Session Report

**Date:** July 23, 2026
**Session type:** Implementation. The last item that was research rather than labour.
**Mandate:** Build the numeric tower. `why` on a value that has silently lost precision is worse than no `why` at all.
**Result:** Built. 133/133 tests passing. Numbers are exact rationals; approximation is visible; rounding is a named operation.

---

## 1. The Decision

Three candidates: IEEE floats (status quo), `Decimal`, exact rationals.

**Exact rationals.** The reason is Why, and it is not a taste argument.

Why exists to answer *what combined to make this number*. A derivation
containing a silent rounding step does not answer that question — it answers
a question about the answer. Floats round on almost every operation.
`Decimal` fixes addition but rounds on division at whatever precision
happens to be configured. Both put a lie inside the derivation graph, and
the lie is invisible at exactly the moment someone is staring at a number
asking why it is wrong.

Exact rationals never round. `1 / 3` stays one third for as long as it is
one third, so `why` reports arithmetic that actually happened.

Verified against IEEE floats:

| | float | Planes |
|---|---|---|
| `0.1 + 0.2 == 0.3` | false | true |
| `round 2.675 to 2 places` | 2.67 | **2.68** |
| `1.1 * 3` | 3.3000000000000003 | 3.3 |
| `0.1 * 3` | 0.30000000000000004 | 0.3 |
| `9007199254740993 * 2` | 18014398509481984 | **18014398509481986** |

All five are tests.

---

## 2. Three Design Choices That Followed

### Approximation is visible, not hidden

A value with no finite decimal form prints with a leading `~`:

```
show text of (1 / 3)   →   ~0.333333333333
```

It remains exact internally — `(1 / 3) * 3` is exactly `1`, and that is a
test. The marker says only that the *text* is an approximation. The
alternative, printing `0.333333333333` unmarked, would reintroduce the
original problem in the one place a user actually looks.

### Rounding is an operation with a name

```
due = round total to 2 places
```

Which means it appears in the derivation like anything else:

```
due = 64.92
  round to 2 places = 64.92
    total = 64.917525
```

The user can see precision being given up, and see exactly where. That is
the whole difference between this and a float: not that rounding never
happens, but that it never happens without being written down.

### Foreign numbers become exact at the boundary

JSON numbers are floats. Converting on entry means a value that arrived as
`0.1` is one tenth from then on, so arithmetic on fetched data is as exact
as arithmetic on literals.

```
item.price * item.qty + 0.2    →  0.5    (floats: 0.5000000000000001)
```

Conversion uses the shortest decimal that round-trips, not the float's full
binary expansion, so a JSON `0.1` becomes one tenth rather than
`0.1000000000000000055`.

On the way out, whole numbers write as JSON numbers and non-whole exact
values write as text — because writing `0.3` as a JSON float would undo at
the last step everything the rest of the system protects.

---

## 3. The Cost, Measured

Exact rationals have a real cost and it should be stated plainly rather than
waved at. Adding fractions with unrelated denominators grows the
denominator toward the least common multiple.

I measured the harmonic sum, which is the worst realistic case:

| distinct fractions summed | denominator | time |
|---|---|---|
| 200 | 293 bits | 0.001s |
| 1000 | 1438 bits | 0.005s |
| 2000 | 2876 bits | 0.010s |
| 5000 | — | **refused**, 0.015s |

Past the bound an operation is **refused**, not silently rounded, with an
error naming the fix. A refusal is visible; a rounding is not.

### The bound was wrong on the first attempt

I initially set it at 10^40. Measuring showed that **summing 200 fractions
hit it** — and summing 200 ratios is an average, not a pathological case. A
user computing a mean over a modest dataset would have hit a hard error.

Raised to 2^4000, which covers several thousand distinct fractions while
keeping arithmetic fast and the refusal fast. Worth recording that the first
bound was chosen by intuition and was wrong by two orders of magnitude in
the direction that hurts users; the measurement is what fixed it.

---

## 4. A Bug Found Immediately

Writing the very first test of this session:

```
count = 7 / 2
```

`count` is a reserved word. I hit the exact trap flagged in the previous
session's report, in my own test, one minute after starting. The diagnostic
built last session caught it and named the fix, which is the system working
— but it confirms that the reserved list including `count`, `text`, `read`,
`show`, `first` is a genuine usability problem, not a theoretical one.

`round` and `places` are now reserved too, making it worse. **Shrinking the
reserved vocabulary deserves to be a real agenda item**, not a note.

---

## 5. What Changed in the Language

- Number literals are exact: `0.1` is one tenth, not the nearest float.
- All arithmetic routes through exact rationals.
- `round X to N places` — new, named, visible in derivations.
- `whole of X` — round to an integer.
- Arithmetic on a non-number is an error naming the value, not a crash.
- Comparing a number with text is an error naming both.
- `count of` returns a number, not a raw integer.

Everything else is unchanged. All 102 prior tests still pass without
modification, which is the strongest evidence that this was a substitution
at the value layer and not a redesign.

---

## 6. What Is Not Built

- **A money type.** Currency is arithmetic on exact numbers plus a rounding
  convention, and rounding conventions differ by jurisdiction. That is a
  library, and it needs the library story first.
- **Fixed-scale decimals.** No way to say "this value has exactly 2 decimal
  places and must stay that way".
- **Integer-only operations.** No `//`, no `mod`. Division always produces
  an exact rational.
- **Number formatting.** No thousands separators, no currency symbols, no
  control over displayed places outside `round`.
- **Overflow.** Integers are unbounded, so there is none — which is correct
  but means no way to opt into machine integers where speed matters.
- **Selective import, private functions, versioning** — unchanged from last
  session.

---

## 7. Where This Leaves the Two Destinations

**Why** is now sound end to end. A derivation traces from a value, through
arithmetic that did not round, through function calls, across a network
boundary, to the URL the data entered from — with every intermediate value
true. That was the claim the destination rested on, and it is now
demonstrated rather than asserted.

**Shapes** is unaffected. The analyser walks the new `Round` node and the
oracle still holds on every example program.

They remain distinct. Nothing in this session shared machinery between them.

---

## 8. Recommendation for the Next Session

**Shrink the reserved vocabulary.** It has now caused a silent failure
(last session) and an immediate self-inflicted error (this session), and
every feature added makes it worse. The words `count`, `text`, `first`,
`read`, `show`, `lower`, `upper`, `whole`, `places` are all ordinary nouns
in a language selling prose-like names. Most could be contextual keywords
recognised only in the position where they mean something.

This is a parser change with a clear test: take every reserved word, use it
as a function name, and require that the program runs.

After that, **selective import and rename-on-import**, which is still the
only answer to a collision between two modules a consumer does not control.

---

## 9. Test Summary

```
test_planes.py    50/50   language
test_shapes.py    52/52   analyser, modules, namespacing, oracle
test_numbers.py   31/31   exactness, rendering, rounding, boundaries, limits
                  -------
                  133/133
```

Anti-drift greps still clean.
