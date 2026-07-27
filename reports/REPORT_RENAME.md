# Rename on Import — Session Report

**Date:** July 23, 2026
**Session type:** Implementation. Closes the oldest outstanding item.
**Mandate:** Selective import and rename-on-import. Check the design against a real example rather than assuming.
**Result:** Rename shipped. **Selective import rejected** — checking against the real case showed it does not solve the problem it was proposed for. 155/155 tests passing.

---

## 1. The Recommendation Was Half Wrong

Last session I recommended "selective import and rename-on-import," and
suggested selective import probably wins on grain. Writing both against the
actual collision case showed otherwise.

The real case is `demo/clash`: two modules, `loader` and `cache`, both
exporting `load record`. The consumer can edit neither.

```
CANDIDATE A — selective import
  use loader taking load record
  use cache taking load record        <- still collides
```

**Selective import does not solve it.** Narrowing what a module brings in
does nothing when both modules export the colliding name and the consumer
needs both. The feature I ranked first was answering a different question.

Renaming is the load-bearing feature:

```
use loader
use cache with load record as load cached
```

Checking against a real example rather than assuming is what caught this,
which is exactly why the mandate said to.

---

## 2. Selective Import Was Then Rejected Outright

Having found it does not solve the motivating problem, the question became
whether it earns a reserved word on its own merits.

- **Purpose:** limit what a module brings in.
- **Benefit:** smaller name surface, fewer accidental collisions.
- **But:** collisions are already errors, caught at load, with a suggested
  fix. Nothing is silent.

So `taking` would prevent an error the user already sees and can already
fix. It does not earn a keyword — especially one session after cutting the
reserved list from 32 to 25 precisely because ordinary words were being
consumed.

**One new reserved word (`with`), not two.** The list is now 26.

---

## 3. Why `with ... as ...`

`as` was already reserved and already means "call it this instead" in
`or fail as api-down`. Reusing it is consistent rather than novel.

A qualified-alias form was also considered:

```
use loader as fetching
r = fetching load record of "requests"
```

Rejected: with multi-word names, `fetching load record` is ambiguous — the
parser cannot tell where the qualifier ends and the name begins. The flat
namespace decided two sessions ago rules this family out, which is a
reminder that early decisions keep paying out.

Multi-word names also forced a parsing rule: `load record as load cached`
needs a boundary, and the terminators are reserved words, which is exactly
why they can serve as one.

---

## 4. A Rename Replaces, It Does Not Alias

The first implementation registered the function under **both** names — the
original and the new one. That reintroduces the collision it was written to
fix: `load record` would still be ambiguous across two modules.

Corrected so a rename **replaces** the exported name. The defining module
still reaches its own functions by their own names, through a separate
local table that never enters the shared namespace.

That last part had to be fixed twice. In the analyser, registering the
original name alongside the exported one meant `cache`'s definition
overwrote `loader`'s, and the surface reported the file read but **not the
network call** — a missing effect, which is the failure mode that matters
most. Fixed by keeping local names in `self.local`, resolved at call sites,
never in `self.funcs`.

**Both bugs were the same mistake in two places**: treating a rename as
additive when it is substitutive.

---

## 5. Renaming Can Create a Collision Too

```
use a                            # exports `greet`
use b with hello as greet        # renames `hello` to `greet`
```

This is now a collision and is reported as one. The check runs over
*effective* names — after renames — rather than declared names, so it
catches both directions. `test_renaming_into_an_existing_name_still_collides`
pins it.

---

## 6. The Reserved-List Guard Fired

`test_reserved_list_is_only_structural_words` failed the moment `with` was
added: *"reserved list has grown to 26"*. Written last session precisely to
catch this, and it caught it one session later.

I raised the ceiling to 26 and recorded the rationale in the test's
docstring — including that `taking` was considered and rejected — so the
next person to hit this sees the standard rather than just the number.

Raising the ceiling is only legitimate because the word earns its place.
If the argument had been weaker the right move would have been to drop the
feature.

---

## 7. What Is Not Built

- **Selective import.** Rejected this session, with reasons. Revisit only
  if a case appears that renaming cannot handle.
- **Private functions.** Every function in a module is still exported.
- **Versioning.** Two versions of a module in one graph remains unhandled.
- **Renaming a builtin on import.** `use lib with count as lib count` works
  for user functions; shadowing a builtin at import is untested.
- **FFI.** Still Tier 0, still the largest structural gap.

---

## 8. Recommendation for the Next Session

**FFI.** It is now the oldest untouched item and the only remaining Tier 0
question. Everything else outstanding — private functions, versioning,
selective import — is well-understood work that can wait.

FFI matters because it decides two things at once: the implementation host
(unresolved since the first session), and whether Shapes can see across a
foreign boundary at all. Today a foreign call would be invisible to the
analyser, and an effect surface with an invisible hole is worth less than
one that reports the hole.

The design question to settle first, against a real example: whether a
foreign function **declares** its effects at the boundary, or whether the
analyser is expected to derive them from the host language. Given that the
whole system rests on not publishing guesses as facts, declaration is the
likely answer — but that should be checked, not assumed.

---

## 9. Test Summary

```
test_planes.py    50/50    language
test_shapes.py    59/59    analyser, modules, namespacing, renaming, oracle
test_numbers.py   31/31    exactness, rounding, boundaries, limits
test_names.py     15/15    every builtin name usable as a name
                  -------
                  155/155
```

Anti-drift greps clean.
