# Foreign Function Interface — Session Report

**Date:** July 23, 2026
**Session type:** Implementation. The last Tier 0 question.
**Mandate:** FFI. Settle first, against a real example, whether a foreign function declares its effects or the analyser derives them.
**Result:** Declaration, as predicted — but the interesting decision turned out to be the *default*. 179/179 tests passing. Both destinations now work across a foreign boundary.

> **Correction, added the following session.** The claim above is too strong.
> 179/179 passed, but the oracle — the check that every runtime effect appears
> in the static surface — was only ever exercised on files with no foreign
> declarations. FFI shipped with an untested runtime path, and it was in fact
> broken: every foreign call logged its effect kind as a tuple rather than a
> string, making the runtime effect log unreadable for the whole feature. The
> suite could not see it. See REPORT_TARGETS.md §3.

---

## 1. The Design Question, Settled

Written against the real list of things Planes needs from a host — `sorted`,
`max`, `time.time`, `os.getcwd`, eventually `sqlite3`:

**Candidate A — the analyser derives effects from the host.** To decide that
`builtins.sorted` is pure, Shapes must analyse CPython. For `sqlite3.connect`
it must analyse a C extension. Impossible in general — and the failure is
**silent**: an analyser that cannot see inside reports "pure", which is a
guess published as a fact. That is precisely the library-reported-as-pure bug
from the Shapes session, reintroduced at the host boundary.

**Candidate B — the foreign function declares.** Readable, checkable, and the
analyser never guesses.

```
foreign sort of xs from "builtins.sorted" doing nothing
foreign now      from "time.time"         doing clock
foreign grab of u from "x.y"              doing ask, clock
```

Declaration wins, as expected. But the expected answer was the easy half.

---

## 2. The Real Question Was the Default

A declaration can lie. Can Planes catch it?

**No.** At runtime Planes calls into the host and cannot see what happens
inside — that is what a foreign boundary *is*. A declaration has the same
epistemic status as a package manifest: a claim by the author.

So the design work is not preventing false claims. It is making sure the
system never presents a claim as something stronger, and never lets a
foreign call contribute silence. Three consequences:

1. **Declared effects are marked as claims.**
   `clock time.time (declared, not verified)`

2. **An undeclared foreign is `unknown`, not pure.** This is the headline
   safety property. Omitting `doing` must not mean "no effects", because
   that is the exact shape of the failure this whole system exists to
   prevent.

3. **A surface containing an unknown says it is incomplete.**
   ```
   foreign:
     unknown — m.f declares no effects
   this surface is incomplete: a foreign function states no effects
   ```

An effect surface with an invisible hole is worth less than one that reports
the hole. That was the argument for doing FFI at all, and it turned out to be
the argument for how.

---

## 3. Both Destinations Cross the Boundary

**Shapes** reports foreign effects, attributed, with holes named.

**Why** treats a foreign boundary as a place values enter the program,
exactly like the network:

```
spread = 37
  - = 37
    top = 41
      biggest = 41   <- entered at foreign:builtins.max
    low = 4
      smallest = 4   <- entered at foreign:builtins.min

entered the program at:
  foreign:builtins.max
  foreign:builtins.min
```

That fell out of the existing derivation machinery without new work, which is
the strongest evidence so far that the `origin` concept was the right shape.

---

## 4. Three Effect Kinds That Needed Deciding

`clock`, `random`, and `env` are now effects, grouped under a new **ambient**
boundary.

The argument: they make a function's result depend on something outside the
program. A function that reads the clock cannot be reproduced from its
derivation, and a package index that called it pure would be wrong in a way
that matters — it is the difference between a value you can re-derive and one
you cannot.

The vocabulary stays closed at seven: `ask`, `read`, `write`, `show`,
`clock`, `random`, `env`. `test_effect_vocabulary_stays_closed` pins the set,
because an open vocabulary cannot be searched or diffed across packages.

---

## 5. A Bug Found, Same Class as Before

A library that declares `foreign now from "time.time" doing clock` and
exposes it reported as **pure** — `declared` only aggregated function bodies,
and an unused foreign declaration was not in any body.

This is the third appearance of one pattern: *a thing that is not called by
this file is still part of what this file offers*. It showed up with library
functions in the Shapes session, with renamed exports last session, and now
with foreign declarations. Fixed by adding foreign effects to the declared
surface whether or not anything calls them.

Worth naming as a recurring shape rather than three unrelated bugs.

---

## 6. Three New Reserved Words, Each Argued

`foreign`, `from`, `doing`. The list goes 26 → 29, and the guard test fired
as designed.

- **`foreign`** — introduces a form with no other spelling.
- **`from`** — `as` was considered and rejected: it already means rename, and
  overloading it would give one word two meanings.
- **`doing`** — `with` was considered and rejected for the same reason.

The ceiling in `test_reserved_list_is_only_structural_words` now carries the
full history of every rise, including the two features rejected for not
earning a word (`taking` for selective import). A rise is legitimate only
when the word has no other spelling; weaker than that, drop the feature.

---

## 7. What Is Not Built

- **A host beyond Python.** `foreign ... from "module.function"` is
  Python-shaped. A different host needs a different target syntax, and the
  question of what the *real* implementation host should be (P-Q9, open since
  session one) is now answerable but not answered.
- **Verifying a claim.** Sandboxing a foreign call to observe its syscalls is
  possible in principle and would upgrade a claim to a fact. Large.
- **Foreign types.** Only numbers, text, lists, records and booleans cross.
  A host object has no representation.
- **Declaring targets.** A foreign declaration says `ask`, not
  `ask https://specific.host`, so a foreign network call is untargeted in the
  surface. *(Built the following session — see REPORT_TARGETS.md.)*
- **Private functions, versioning, selective import** — unchanged.

---

## 8. Recommendation for the Next Session

**Foreign effect targets.** A declaration currently says *what kind* of
effect but not *where*. `doing ask` tells a reader the function reaches the
network; it does not say which host. For the diff use case — "this package
now sends to a domain it did not before" — the target is the whole point,
and it is the one place where the foreign surface is meaningfully weaker than
the native one.

The syntax likely already exists: `doing ask "https://api.example.com"`. The
work is threading targets through `foreign_effects` and deciding what a
declaration means when the target is computed by the host rather than fixed.

After that, the host question (P-Q9) is finally ripe: FFI is what decides it,
and FFI now exists.

---

## 9. Test Summary

```
test_planes.py    50/50    language
test_shapes.py    59/59    analyser, modules, namespacing, renaming, oracle
test_numbers.py   31/31    exactness, rounding, boundaries, limits
test_names.py     15/15    every builtin name usable as a name
test_foreign.py   24/24    FFI, declarations, claims, the unknown default
                  -------
                  179/179
```

Anti-drift greps clean.

**A note on this line, added later.** "Anti-drift greps clean" closes every
report in this chain, and it means one specific thing: no governance
vocabulary appeared in the source. It is not a statement that the session's
work was verified. This report ended with that line and a green suite, and
was wrong about the second thing. The two claims are worth keeping visibly
separate.
