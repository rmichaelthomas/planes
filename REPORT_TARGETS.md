# Foreign Effect Targets — Session Report

**Date:** July 23, 2026
**Session type:** Implementation. Closes the weakest part of the foreign surface.
**Mandate:** Foreign effect targets. `doing ask` says the function reaches the network but not which host.
**Result:** Built. 192/192 tests passing. **A bug the oracle should have caught, didn't** — and fixing the gap was the most valuable part of the session.

---

## 1. Why Targets

Checked against the diff use case first, as the mandate required. Two
versions of a package:

```
v1: foreign send of x from "mylib.post" doing ask
v2: foreign send of x from "mylib.post" doing ask
```

Identical declarations. If the library changed which host it posts to, the
diff shows **nothing** — `doing ask` is the same string either way. The one
thing Shapes exists to tell you is invisible.

With targets:

```
v1: ... doing ask "https://api.example.com/events"
v2: ... doing ask "https://collect.tracking.io/beacon"

$ shapes_cli.py --diff v1.planes v2.planes
NEW DESTINATIONS: https://collect.tracking.io/beacon
```

Identical Planes code, identical effect kinds, and the diff catches it.

---

## 2. Three Forms, and the One That Matters

```
doing ask "https://api.example.com"    a fixed destination
doing ask url                          whatever the caller passes
doing ask                              not stated
```

The middle form is the valuable one. A declaration naming a parameter lets
**existing constant propagation** resolve the real destination at each call
site:

```
foreign fetch of url from "u.urlopen" doing ask url
r = fetch of "https://pypi.org/pypi/requests/json"

→ ask https://pypi.org/pypi/requests/json (declared, not verified)
```

A host name now survives a foreign boundary. That machinery was built two
sessions ago for native code and needed no changes — it applied directly.

The third form renders as `(destination not stated)` rather than looking
like a fixed target, following the same principle as the undeclared-foreign
default: never let a gap read as an answer.

A target naming something that is not a parameter is a syntax error that
lists the parameters.

---

## 3. The Bug the Oracle Missed

Changing `effects` from `("clock",)` to `(("clock", None),)` broke the
runtime effect log:

```
logged: [(('clock', None), 'time.time')]
```

Every foreign call logged a **tuple where the effect kind should be**. The
runtime log — the ground truth the static surface is checked against — was
unreadable for the entire FFI feature.

**All 179 tests still passed.**

The oracle exists precisely to catch this class of thing, and it was only
ever exercised on `.planes` files with no foreign declarations. FFI shipped
last session with an untested runtime path.

Fixed twice over: the logging bug itself, and the gap that hid it. The
oracle now runs over foreign calls, and `test_runtime_logs_a_string_kind_not_a_tuple`
pins the specific failure.

**The lesson is about coverage shape, not about this bug.** A safety
mechanism that only runs on the code paths that existed when it was written
degrades silently as features are added. Worth asking of every new feature:
does the oracle reach this?

---

## 4. A New Destination Now Fails a Build

`--diff` previously exited 1 only on a **new boundary**. A changed
destination inside a boundary the program already touched exited 0 — so the
tracking-beacon case above would have passed CI.

`SurfaceDiff.is_significant()` now covers both, and the render distinguishes
them: `NEW BOUNDARIES CROSSED` outranks `NEW DESTINATIONS` when both apply.

---

## 5. A Rendering Decision

When a call site resolves a parameter target, the generic declaration
surface still holds the vague version, so both appeared:

```
ask https://pypi.org/pypi/requests/json (declared, not verified)
ask {...} (computed) (declared, not verified)
```

The second is noise — `{...}` printed beside the answer it stands in for.
Suppressed when a resolved entry of the same kind and boundary exists, but
**kept for uncalled declarations**, because a library exposing a fetch
function still has network reach whether or not this file calls it.

That is the same distinction as `effects` versus `declared`, applied one
level down.

---

## 6. What Is Not Built

- **Multiple destinations per foreign.** A declaration states one target per
  effect kind. A host function reaching two services cannot say so.
- **Verifying a target.** Still a claim. Sandboxing to observe real syscalls
  would upgrade claims to facts and remains large.
- **Targets for native effects through parameters.** A Planes function taking
  a URL and calling `ask` on it resolves per call site already, but there is
  no way to *declare* that relationship, which would help when the analyser
  cannot see the call site.
- **Foreign types, a non-Python host, private functions, versioning,
  selective import** — unchanged.

---

## 7. Recommendation for the Next Session

**The implementation host (P-Q9), open since the first session.**

It is now genuinely ripe. FFI was always the thing that would decide it, and
FFI exists. The concrete question: `foreign ... from "module.function"` is
Python-shaped, and every design decision since has been made against a
Python host without that being an explicit choice.

Three things to settle, and all three are now answerable rather than
speculative:

1. **Is Python the host, or the prototype's host?** The prototype runs, the
   whole test suite passes, and both destinations work end to end. That is
   evidence, not a plan.
2. **What does `from "..."` mean on another host?** The target string is the
   only Python-shaped syntax in the language.
3. **What breaks?** Exact rationals, structured concurrency (never built),
   and the effect vocabulary all assume things about a runtime.

The alternative worth weighing is **shipping what exists**: the language
runs real programs against the live network, Shapes and Why both work, and
`shapes_cli.py --index` is usable on code nobody wrote in Planes. The wedge
argument from the inception checkpoint says that surface can be published
before the language has any adoption — and it can be published now.

That is a decision for the architect, not the analytical partner. Both paths
are defensible and they diverge sharply.

---

## 8. Test Summary

```
test_planes.py    50/50    language
test_shapes.py    59/59    analyser, modules, namespacing, renaming
test_numbers.py   31/31    exactness, rounding, boundaries, limits
test_names.py     15/15    every builtin name usable as a name
test_foreign.py   37/37    FFI, declarations, targets, oracle over foreigns
                  -------
                  192/192
```

Anti-drift greps clean. No new reserved words this session: the target
syntax reuses positions that were already unambiguous.
