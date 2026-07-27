# Addendum — Sprint Close: The Host, the Checking Apparatus, and a Hole in the Founding Argument

**Date:** July 23, 2026
**Status:** Addendum. Closes the implementation sprint that began with the substrate prototype.
**Relationship to prior documents:** Extends REPORT.md through REPORT_WEDGE.md. Retracts nothing. Corrects two claims made in earlier reports in this chain (§5).
**Scope:** This addendum covers the sprint. It does **not** make the publish decision, which is deferred to a fast follow (§7).

---

## 1. What the Sprint Produced

A working general-purpose language with two destinations implemented and
checked against each other.

```
3,340 lines of implementation across nine modules
  217 tests across seven suites
   11 session reports, plus this addendum
```

Both destinations work end to end, across every boundary the language has:

**Why** traces a value's derivation through arithmetic that never rounded,
through function calls, across a network boundary, across a foreign boundary,
back to the URL or host function the data entered from.

**Shapes** computes a program's total effect surface without running it,
follows imports across files, resolves real destinations through constant
propagation, and diffs two versions to report a new boundary or a new
destination — failing a build on either.

The session gate from the Planes Inception Checkpoint §15 — *write one
ordinary program with no rules in it, and verify Shapes can analyse it and
Why can trace it* — has been met and is now a standing test
(`test_ordinary_program_needs_no_governance`,
`test_ordinary_program_is_traceable`).

The rule plane remains parked, as §8 of the checkpoint requires. No
governance vocabulary appears in any source file, enforced by a grep test
that has fired three times on prose and never on drift.

---

## 2. P-Q9 Is Closed, and Was the Wrong Question

P-Q9 — *what is the implementation host* — was carried for nine sessions as
"what language should Planes be implemented in." That framing is why it kept
being deferred: it sounds foundational.

Measuring the actual coupling took twenty minutes. Exact rationals, JSON at
the boundary, HTTP, module resolution, dynamic dispatch: all implementation,
satisfiable by any host with bignums and dynamic loading. And the foreign
target string — which REPORT_TARGETS.md called "the only Python-shaped syntax
in the language" — **is not syntax at all**. The parser stores it opaquely;
the analyser never reads it. `node:fs#readFile` parses today.

So the question is *what must a host provide*, and the answer is eight
methods in `host.py`: five effect capabilities, a foreign resolver, and a
JSON codec.

**Decision: Python stays.** Recorded rather than inherited. Every accumulated
requirement is met by the stdlib; the prototype runs real programs against
the live network; 217 tests pass. The alternatives cost more than they return
at this stage.

What changed is that the choice is now reversible at a **known price**. A
second host is eight methods, not a rewrite — and `TestHost` already
demonstrates the seam by being a second host that passes the entire suite.

### Why the host surface is small

Not by design at the time. The effect vocabulary was closed three sessions
earlier, for Shapes, because an open vocabulary cannot be searched or diffed
across packages. A host cannot be asked for more than the language can name.
**Closing the vocabulary for one destination bounded the host surface as a
side effect, before anyone asked what a host was.**

`test_the_host_surface_matches_the_effect_vocabulary` now pins that
correspondence so it cannot drift apart silently.

---

## 3. The Checking Apparatus Became a Thing That Is Itself Checked

The most consequential work this sprint was not a feature.

The oracle — *every runtime effect must appear in the static surface* — is
the one check capable of catching an unsound analyser. It was correct. It was
also only ever exercised on code paths that existed when it was written.

FFI shipped with an untested runtime path and a real bug: every foreign call
logged its effect kind as a tuple rather than a string, making the runtime
effect log unreadable for the entire feature. **179 tests passed.**

Measured afterwards: the oracle reached 17 of 23 AST node types. `Round`,
`Why`, `Not`, `Bool`, `Nothing` had never been exercised by an oracle run.
All were sound — but latent is what FFI was, right up until it wasn't.

`test_coverage.py` makes it structural rather than remembered:

- `ALL_NODES` is derived from the lexer module, not hand-listed, so a node
  added without a coverage case fails immediately with the node named.
  Verified by adding a fake node and watching it fail.
- Every node marked unreachable must really be unreachable, so the marker
  cannot become an opt-out.
- Every logged effect kind must be a string — the specific shape of the bug
  that hid.
- The suite must not touch the real filesystem.

That last one caught something nobody was looking for: **the test suite had
been writing real files into the repository for several sessions.** The
implicit in-memory default hid it; removing the default made four tests fail
instantly. One of the leaking cases was written an hour earlier, in this
sprint, by me. The hermeticity test caught its own author.

**The generalisation worth keeping:** a safety mechanism that only runs on
the code paths present at the time it was written degrades silently as
features are added. The FFI bug was not caused by a missing test. It was
caused by a passing suite. What was missing was any mechanical way to ask
whether the checking apparatus had grown along with the thing it checks — and
a discipline you have to remember is one you eventually don't.

---

## 4. One Pattern, Four Appearances

*A thing this file does not call is still part of what this file offers.*

1. **Library functions** (Shapes session). Indexing a five-package corpus,
   every package reported `pure`, including one that only makes network
   calls. A library has no top-level statements; its effects sit behind
   functions the consumer calls.
2. **Renamed exports** (rename session). Registering a function under both
   its original and renamed name meant one module's definition overwrote
   another's, and the surface reported a file read but **not** the network
   call.
3. **Foreign declarations** (FFI session). A library declaring
   `foreign now ... doing clock` and exposing it reported as pure, because an
   unused declaration is not in any function body.
4. **The published JSON** (this session). `--json` emitted
   `"boundaries": ["network"]` beside `"effects": []` for the same package,
   in the same document — the human view reporting the declared surface, the
   machine view reporting only top-level effects.

The fourth is the worst, because it is the one a consumer would have parsed.
It survived because only the human view was ever checked.

Four instances is not three coincidences plus one. It is a shape the design
keeps producing, and it deserves a standing question at review:
**does this report what the file *offers*, or only what it *runs*?**

---

## 5. Corrections to Earlier Reports in This Chain

Made in place, with the original claims left visible.

**REPORT_FOREIGN.md** claimed "179/179 tests passing. Both destinations now
work across a foreign boundary." The second half was not established: the
oracle never ran over a foreign declaration, and the runtime path was broken.
A correction block now sits under the original claim.

The same report's closing line — "anti-drift greps clean" — closes every
report in the chain and means one specific thing: no governance vocabulary in
the source. **It is not a statement that the session's work was verified.**
That report ended with that line and a green suite and was wrong about the
second thing. The two claims are now visibly separated.

**REPORT_TARGETS.md** called the foreign target string the only Python-shaped
syntax in the language. It is not syntax at all (§2).

---

## 6. What Is Not Built

Named rather than deferred silently, per the standing terms.

- **A second real host.** `TestHost` shares Python's runtime. Until a
  genuinely different host exists, the seam is argued rather than
  demonstrated.
- **Dead `Builtin` node.** The parser stopped constructing it two sessions
  ago; six sites of unreachable handling remain in `interp.py` and
  `shapes.py`. Marked with a test, not deleted — a removal refactor at sprint
  close is how regressions arrive.
- **`random` and `env` as host capabilities.** In the vocabulary, reachable
  only through `foreign`, not on `Host`.
- **Verifying a foreign claim.** Sandboxing to observe real syscalls would
  upgrade a claim to a fact. Large.
- **Private functions, module versioning, selective import.** All known work.
- **Structured concurrency.** Carried from unbound as locked, never built,
  and now a year of sessions old without being exercised. Worth re-examining
  rather than continuing to carry.

---

## 7. The Deferred Decision

Recorded so the fast follow does not have to reconstruct it.

The inception checkpoint's wedge argument holds that Shapes is usable before
Planes has any adoption, because it can index and publish analysis of code to
people who never write a line of Planes.

**Read strictly, that requires Planes code to exist, and none does** outside
this repository. The wedge has a bootstrap problem that went unnoticed for
five sessions, including by the checkpoint that states it. Full argument in
REPORT_WEDGE.md §3.

Two exits, and they are different products:

**A. Shapes without Planes.** Point the analyser at a language people already
write. Probed rather than asserted: forty lines of Python over `ast`
reproduce the core — fixed point over the call graph, effects inherited
transitively, `compute` picking up network reach from a function two calls
down. What ports is the architecture and the discipline, which is where the
thinking went. What does not port is the language. It can index real packages
on day one.

**B. Drop the wedge framing.** Accept that indexing needs Planes code first
and take the ordinary path: make the language worth writing, then index it.
Coherent, slower, and precisely what the wedge was invented to avoid.

**A repo is worth creating under either.** `rmichaelthomas/planes` does not
exist — verified twice this sprint by full listing. It makes the work exist
outside a transcript. It does not by itself test anything.

**Recommendation for the fast follow:** make this decision before writing
more language code. Every session spent on the language quietly assumes B
without saying so, and the cost of discovering the wedge is wrong rises with
each one.

---

## 8. Standing Terms

Unchanged and observed throughout: questions raised in session are handled in
session; uncertainty is resolved to a recommendation rather than returned as
a flag; announced actions are taken immediately; locked material is carried
explicitly or marked parked, never dropped silently.

Added by this sprint's evidence: **a green suite is not verification.** It is
a statement about the tests that exist. Whether those tests reach the code
they are supposed to check is a separate question, and it should be asked
mechanically rather than remembered.

---

## 9. Test Summary

```
test_planes.py    50/50    language: values, functions, collections, effects
test_shapes.py    63/63    analyser, modules, namespacing, renaming,
                           runtime oracle, published-format agreement
test_numbers.py   31/31    exactness, rounding, boundaries, precision limits
test_names.py     15/15    every builtin name usable as a function name
test_foreign.py   37/37    FFI, declarations, targets, oracle over foreigns
test_host.py      14/14    the host seam, swapping, target opacity
test_coverage.py   7/7     oracle reaches every node; suite touches nothing
                  -------
                  217/217
```

Anti-drift greps clean — meaning only that no governance vocabulary appears
in the source.
