# P-Q9: The Implementation Host — Session Report

**Date:** July 23, 2026
**Session type:** Decision, with the implementation the decision required.
**Mandate:** P-Q9 — what is the implementation host. Open since the inception checkpoint.
**Result:** **Python stays.** But the question turned out to be smaller than nine sessions of deferral implied, and measuring it is what showed that. 213/213 tests passing. A host seam now exists, and three latent defects surfaced while extracting it.

---

## 1. The Question Was Wrong

P-Q9 was carried for nine sessions as "what language should Planes be
implemented in" — a question that sounds foundational and gets deferred
because it sounds foundational.

Measuring the actual coupling took twenty minutes and reframed it. Of
everything that looks host-shaped:

| | verdict |
|---|---|
| exact rationals | implementation — any host with bignums |
| JSON at the boundary | implementation — any host with a codec |
| HTTP | implementation |
| module resolution | implementation — needs a filesystem |
| `importlib` dispatch | implementation — **one function** |
| `from "module.function"` | **opaque to the language** |

The last row is the one the previous report got wrong. It called the target
string "the only Python-shaped syntax in the language." It is not syntax at
all. The parser stores it as a string and imposes no structure; the analyser
uses it as a label and never parses it; only the interpreter interprets it,
in one place, by splitting on a dot.

`foreign f of x from "node:fs#readFile"` parses today. `crate::mod::fn`
analyses today. The string is host-specific *by design*, which is exactly
why changing hosts needs no language change.

**So P-Q9 is not "which language". It is "what must a host provide".**

---

## 2. The Answer: Five Capabilities and a Resolver

`host.py` names the whole surface: `ask`, `read`, `write`, `show`, `clock`,
plus `resolve` for foreign names and a JSON codec at the boundary.

That is small, and it is small for a traceable reason. **The effect
vocabulary was closed in the Shapes session** — `ask`, `read`, `write`,
`show`, `clock`, `random`, `env` — because an open vocabulary cannot be
searched or diffed across packages. A host cannot be asked for more than
the language can name, so closing the vocabulary for Shapes bounded the host
surface as a side effect, three sessions before anyone asked what a host was.

`test_the_host_surface_matches_the_effect_vocabulary` pins that
correspondence so it cannot quietly drift.

---

## 3. The Decision

**Python stays**, and the reasoning is now recorded rather than inherited:

- Every requirement the language has accumulated is met. Exact rationals
  need bignums and rationals: `Fraction`. Foreign resolution needs dynamic
  loading: `importlib`. Both are stdlib.
- The prototype runs real programs against the live network, both
  destinations work end to end, and 213 tests pass. That is evidence, not a
  plan.
- The alternatives cost more than they return *at this stage*. A faster host
  matters when there is a program slow enough to care, and there is not one.

What changed is that the choice is now **reversible at a known price**. The
host surface is eight methods. A second host is a piece of work with a size,
not a rewrite — and `TestHost` already proves the seam is real by being a
second host that passes the whole suite.

The honest framing: this is not "Python is right for Planes forever." It is
"Python is right for Planes now, the cost of being wrong is eight methods,
and here is the file where that cost lives."

---

## 4. Three Defects the Extraction Surfaced

None were the point of the session. All three were invisible until the
implicit host became explicit.

### 4.1 The test suite had been writing real files for sessions

Removing the in-memory default made four tests fail immediately with
`KeyError: 'out.json'` — they were writing to the repository, and
`a.json`, `big.json`, `o.json`, `out.json` were sitting in the working
directory.

The old default silently kept files in memory *sometimes*, so "what the test
says happens" and "what actually happens" had drifted apart with nothing
failing.

Fixed, and then made structural:
`test_the_suite_does_not_touch_the_real_world` runs every suite as a
subprocess and fails if any of them leaves a file behind.

**This is the argument for the seam in miniature.** An implicit host lets
behaviour drift from description. An explicit one makes the drift a test
failure.

### 4.2 One of my own tests, written this session, leaked too

The coverage cases added an hour earlier wrote `a.json` and `o.json`. The
hermeticity test caught its own author.

### 4.3 `Builtin` is dead code

Surfaced by the node-coverage work: the parser stopped constructing
`Builtin` when builtins became ordinary functions two sessions ago. Six
sites of unreachable handling remain in `interp.py` and `shapes.py`. Marked
unreachable with a test asserting the parser really does not build it, so
the marker cannot become an opt-out.

---

## 5. What Is Not Built

- **A second real host.** `TestHost` proves the seam but shares Python's
  runtime. A genuinely different host is untried, and until one exists the
  seam is argued rather than demonstrated.
- **Removing the dead `Builtin` node.** Marked, not deleted; a removal
  refactor mid-session is how regressions arrive.
- **`random` and `env` as host capabilities.** Reachable only through
  `foreign` today. They are in the vocabulary but not on `Host`.
- **Host selection from the command line.** `planes.py` always uses
  `PythonHost`.
- **Foreign types, private functions, versioning, selective import** —
  unchanged.

---

## 6. What This Closes

P-Q9 was the last open question from the inception checkpoint that blocked
anything. The remaining items — private functions, versioning, selective
import, a second host — are all *known work*, not open questions. Nothing
outstanding requires a decision before it can be started.

That is a different state from any previous session, and it is worth saying
plainly rather than burying in a recommendation.

---

## 7. Recommendation for the Next Session

**Publish the Shapes index.**

The inception checkpoint's wedge argument was that Shapes is usable before
the language has any adoption, because it can analyse and publish facts
about code to people who never write a line of Planes. That claim has been
true for four sessions and untested for all four.

Concretely: `shapes_cli.py --index` and `--search` work on a corpus today.
What does not exist is anything a person outside this session could use —
a published surface for a real set of packages, or a documented format
someone else could produce.

The reason to do it now rather than build more language: every remaining
language item is known work that will still be known work in a month,
whereas the wedge claim is the one load-bearing assumption in the whole
chain that has never been checked against a person who is not the architect.

If it is wrong, everything downstream of it is differently shaped, and the
cost of finding out rises with every session that assumes it.

---

## 8. Test Summary

```
test_planes.py    50/50    language
test_shapes.py    59/59    analyser, modules, namespacing, renaming
test_numbers.py   31/31    exactness, rounding, boundaries, limits
test_names.py     15/15    every builtin name usable as a name
test_foreign.py   37/37    FFI, declarations, targets, oracle over foreigns
test_host.py      14/14    the host seam, swapping, opacity of targets
test_coverage.py   7/7     oracle reaches every node; suite touches nothing
                  -------
                  213/213
```

No new reserved words. Anti-drift greps clean.
