# Addendum — The Wedge Has a Bootstrap Problem

**Date:** July 23, 2026
**Status:** Correction to my own recommendation, made before acting on it.
**Trigger:** The architect asked "publish it where? To a repo?"

---

## 1. What the Question Exposed

I ended the previous session recommending "publish the Shapes index" without
saying where or to whom. That vagueness was load-bearing, and one question
collapsed it.

Two things fell out, one a defect and one a hole in the chain's founding
argument.

---

## 2. The Defect: the Published Format Contradicted Itself

`shapes_cli.py --json` on `sneaky.planes` emitted:

```json
"boundaries": ["network"],
"effects": []
```

Both from the same surface, in the same document. The human view reported the
**declared** surface; the JSON reported only **top-level** effects. A consumer
parsing `effects` would have concluded the package does nothing — while
`sneaky.planes` exists in the corpus precisely because it hides a beacon two
calls deep.

This is the library-reported-as-pure failure, for the **fourth** time, and the
first time in machine-readable output. It survived because only the human view
was ever checked.

Fixed: `effects` now reports the declared surface, `runs_on_load` reports what
executes at load, both facts are present and neither is silently substituted
for the other. Added `format`, `kind`, and `complete`. Four tests now assert
the two views agree; one of them iterates the whole corpus.

**The step I called "publish" was blocked by the artifact being wrong.** I
would not have found that by publishing it.

---

## 3. The Hole: the Wedge Needs Planes Code, and None Exists

The inception checkpoint says Shapes "can index and publish analysis of code
to people who never write a line of Planes."

Read strictly, that is analysis **of Planes code**, published **to**
non-writers. It still requires Planes code to exist. Nobody has written any
outside this repository, and there is no reason anyone would before the
language is worth writing in.

**The wedge, as written, has a bootstrap problem.** I did not notice it for
five sessions. Neither did the checkpoint. My recommendation last session —
"publish the index, it tests the wedge" — could not have tested the wedge,
because the corpus would have been five demo files I wrote myself.

That is a worse error than the JSON bug. The JSON bug was a defect in a
thing that exists; this was a plan that could not have produced the evidence
it claimed to.

---

## 4. Two Ways Out, and They Are Different Products

### A. Shapes without Planes

Point the analyser at a language people already write.

I probed this rather than assert it: **40 lines of Python over `ast`**
reproduces the core — fixed point over the call graph, transitive effect
propagation, effects inherited by callers:

```
helper     ['pure']
beacon     ['network']
compute    ['network']      <- inherited two calls deep
```

What ports is the **architecture and the discipline**, which is where the
actual thinking went:

- fixed point over the call graph, not a tree walk
- a closed effect vocabulary, so surfaces are comparable
- declared vs. derived, never conflated
- undeclared means unknown, never pure
- a runtime oracle checking the static surface
- diffing surfaces, with a new destination failing a build

What does not port is the language. This is Shapes as a Python tool, and it
can index PyPI on day one — real packages, real consumers, no bootstrap.

The cost is honest and should be stated: it makes Planes-the-language a
separate bet rather than the thing the wedge feeds. It may also be the more
valuable product.

### B. Drop the wedge framing

Accept that indexing needs Planes code first, stop calling it a wedge, and
take the ordinary path: make the language worth writing, then index it.

Slower, and it is precisely the path the wedge was invented to avoid — but it
is coherent, which the current framing is not.

---

## 5. What "Publish" Actually Means

Four distinct things, and I had blurred them:

1. **A repo.** `rmichaelthomas/planes` does not exist — verified this
   session and at session start. I can populate a repo but cannot create
   one. It makes the work exist outside a transcript. It does not test
   anything.
2. **A format spec.** What a `shapes.json` means, versioned, so someone else
   could produce or consume one. This was blocked by §2 and is now unblocked.
3. **An index of real packages.** Blocked by §3 under the current framing;
   available immediately under option A.
4. **A person who is not the architect reading one and reacting.** The only
   thing that is actually evidence, and not a coding task.

---

## 6. Recommendation, Revised

**Decide between A and B before writing more code.** They diverge immediately
and every session spent on the language is a session that assumes B without
saying so.

If **A**: the next session is a Python effect analyser reusing this
architecture, aimed at PyPI. The prototype above suggests days, not weeks,
and the wedge claim gets its first real test against packages people
already depend on.

If **B**: the wedge language should come out of the checkpoint, because
leaving it in means the chain keeps citing a justification that does not hold.

**A repo is worth creating either way**, and is the one step only the
architect can take. Populating it is a small task I can do in a single
session once it exists.

I do not think this is my call. It changes what the project is.

---

## 7. Test Summary

```
test_planes.py    50/50
test_shapes.py    63/63    +4: the published format agrees with itself
test_numbers.py   31/31
test_names.py     15/15
test_foreign.py   37/37
test_host.py      14/14
test_coverage.py   7/7
                  -------
                  217/217
```
