# Planes Static Effect Analyser — Session Report

**Date:** July 23, 2026
**Session type:** Implementation. Continues the substrate prototype.
**Mandate:** Build the static effect analyser. Validate against the runtime log as oracle.
**Result:** Built. 75/75 tests passing. Four Shapes use cases working. Two soundness bugs found and fixed.

---

## 1. What Was Built

`shapes.py` (330 lines) computes a program's total effect surface **without
running it**, plus `shapes_cli.py` exposing it as four artifacts.

| Component | File | Lines |
|---|---|---|
| Static analyser | `shapes.py` | 330 |
| Analyser CLI | `shapes_cli.py` | 165 |
| Analyser tests | `test_shapes.py` | 28 tests |
| Language tests | `test_planes.py` | 47 tests |

The surface of the HN scraper, computed with zero network calls:

```
network:
  ask https://hacker-news.firebaseio.com/v0/item/{...}.json (computed)
  ask https://hacker-news.firebaseio.com/v0/topstories.json
file:
  write results.json
console:
  show found {...} (computed)
```

### The core mechanism

Not a tree walk. A function's effects include the effects of everything it
calls, transitively, and calls can be mutually recursive — so this is a
**fixed-point computation over the call graph**. Effect sets grow until they
stop growing; termination is guaranteed because sets only grow and the
vocabulary is closed.

`test_mutual_recursion_terminates` covers the case that would hang a naive
implementation.

### Target descriptions

A literal target is reported exactly. A computed one keeps its known parts:

```
"https://api/" + text of id + ".json"  →  https://api/{...}.json (computed)
```

Enough to see the host and the shape while marking what is unknown. This
matters because "asks a fixed endpoint" and "asks a URL built at runtime"
are different facts, and Shapes has to be able to say which.

---

## 2. The Oracle

The central test: **for any program, every effect that occurs at runtime
must appear in the static surface.** An unsound surface is worse than none —
it would tell a user a package is safe when it is not.

`check_oracle()` runs a program, then checks every logged effect against the
computed surface, matching literals exactly and computed targets by their
literal chunks in order. It runs against the HN scraper, the ordinary
program, a pure program, a recursive function, a comprehension, and an
untaken branch.

**All pass.**

### Adversarial probing

Passing tests I wrote myself is not evidence of soundness, so I tried
actively to smuggle an effect past the analyser — nine constructions, now
permanent in `test_shapes.py`:

effect in a `where` clause · in a comprehension source · inside `or fail` ·
in a function nested inside a function · in an `if` condition · as an
argument to another call · in a list literal · behind a field access ·
in a function called before it is defined

**Zero escapes.** Two cases produced runtime errors rather than analyser
misses, and both turned out to be defects elsewhere (§4).

---

## 3. The Four Shapes Use Cases

All working, all against real files.

**Read a boundary surface fast.** `shapes_cli.py hn.planes --functions`
gives a per-function breakdown in one command.

**Diff an upgrade.** The case the destination exists for:

```
$ shapes_cli.py --diff demo/v1.planes demo/v2.planes
NEW BOUNDARIES CROSSED: network
  + network: ask https://telemetry.example.com/collect?data={...} (computed)
```

Exit code 1 when a new boundary appears, so it drops into CI as a gate.

**Search packages by behaviour.**

```
$ shapes_cli.py --search network demo/pkgs
fetcher          ask {...} (computed)
sneaky           ask https://collect.example.com/?v={...} (computed)
```

**A fact an agent can act on before installing.** `--json` emits boundaries,
kinds, targets, computed flags, declared modules, and undeclared effects.

---

## 4. Bugs Found

Two soundness bugs and two defects. The soundness bugs matter most, and both
were found by building a demo rather than by writing more tests.

### 4.1 A library reported as pure — SOUNDNESS

Indexing a five-package corpus, **every package reported `pure`**, including
one that does nothing but make network calls.

The cause: a library has no top-level statements. Its effects live behind
functions the consumer calls, so the top-level walk found nothing.

For an application that is correct. For a library it is exactly the lie
Shapes exists to prevent — and Shapes indexes packages, so this was the
primary use case failing silently.

The fix separates two questions that were conflated:

- `effects` — what running this file performs. Right for an application.
- `declared` — what any function here can do if called. Right for a library.

Package queries now read `declared`. `sneaky.planes`, whose network call sits
two hops behind an innocuously-named `compute`, is correctly indexed as
touching `collect.example.com`. `mathlib` is correctly pure.

**This bug would have shipped a package index that marked exfiltration as
harmless.** It was invisible until a corpus existed to index.

### 4.2 Interpreter and analyser disagreed on forward references — SOUNDNESS

The analyser saw a function called before its definition; the interpreter
raised `unknown-function`. When the two disagree about what a program can do,
the surface is not a description of the program.

Fixed by hoisting definitions in `interp.py`: source order controls
execution, not visibility. The analyser was the one telling the truth.

### 4.3 Multi-word function names could not take arguments

`to phone home of settings:` parsed, but `phone home of settings` at a call
site did not — the multi-word probe only handled zero-argument calls. Found
while writing the diff demo.

### 4.4 The anti-drift test fired on a comment

`test_no_governance_vocabulary_in_source` went red because I wrote "Source
order **govern**s execution" in a docstring. A substring false positive.

I renamed the word rather than weakening the check. The test is a tripwire;
loosening it the first time it fires defeats its purpose.

---

## 5. What the Analyser Gets Right by Design

**Untaken branches are in the surface.** A `write` inside an `if` that does
not fire this run still appears. The surface is what a program *can* do.
`test_oracle_effect_in_untaken_branch` asserts both halves: the effect is in
the surface, and it did not run.

**Effects deduplicate by site, not by execution.** Three calls to one
function are one effect. A comprehension calling `ask` over 10,000 items is
one network effect, not 10,000.

**The analyser never executes anything.** `test_analysis_does_not_execute`
computes the HN scraper's surface with no interpreter and no HTTP function in
scope at all.

**Missing `use` declarations are caught statically**, without running the
program that would have failed.

---

## 6. What Is Not Built

- **Cross-file modules.** `use http` toggles a builtin; there is no import
  graph. Real package indexing needs one.
- **FFI.** Still Tier 0. A foreign call is currently invisible to the
  analyser — it would report `unresolved`, which is honest but not useful.
- **Effect targets through variables.** `let u = "https://..."` then `ask u`
  reports `{...}`, losing the host. Constant propagation would fix most
  real cases and is not hard.
- **`why` across the analyser.** Shapes and Why still share no machinery.
  Whether they should is open.

---

## 7. Assessment Against the Two Destinations

**Shapes** now has a working runtime *and* static half, validated against
each other. The wedge property holds: `--index` and `--search` analyse and
publish facts about code without anyone writing a line of Planes.

**Why** was already working and is untouched by this session.

They remain distinct, as required. Shapes consumes effects; Why consumes
derivations. No machinery is shared, and nothing in this session tried to
collapse them.

The anti-drift greps are still clean. The demo corpus is a package index, a
logger, a cache, a fetcher, and a telemetry beacon — no governance
vocabulary appeared anywhere in a session about analysing what programs do.

---

## 8. Recommendation for the Next Session

**Constant propagation for effect targets**, then **cross-file modules**.

Constant propagation is small, immediately visible in output quality
(`{...}` becoming a real host in the common case), and testable against the
same runtime oracle already in place. Cross-file modules are the thing
standing between this and a real package index — and the library/application
distinction found in §4.1 is exactly the groundwork that makes them
tractable.

The numeric tower remains the second priority, unchanged from last session,
and for the same reason: `why` on a money value that has silently lost
precision is worse than no `why` at all.

---

## 9. Test Summary

```
test_planes.py    47/47   language: values, functions, collections, effects
test_shapes.py    28/28   analyser: oracle, libraries, diffing, adversarial
                  -----
                  75/75
```
