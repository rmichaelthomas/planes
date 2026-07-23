# Shrinking the Reserved Vocabulary — Session Report

**Date:** July 23, 2026
**Session type:** Implementation. Fixes a usability problem that caused failures in two consecutive sessions.
**Mandate:** Shrink the reserved list. Test: every non-structural word must work as a function name.
**Result:** 32 reserved words → 25. All seven removed words work as names. 148/148 tests passing.

---

## 1. The Problem

The reserved list had grown to 32 words and included ordinary nouns:
`count`, `text`, `first`, `read`, `show`, `lower`, `upper`, `whole`,
`places`. In a language selling names that read as prose, those are exactly
the words people reach for.

It had already caused two failures:

- **Last session**, silently: `to first thing:` returned nothing from the
  name prescan, so the function became invisible to every caller with no
  error anywhere.
- **The session before**, immediately: I typed `count = 7 / 2` in the first
  test I wrote and hit it myself, one minute in.

Adding `round` and `places` for the numeric tower made it worse. Every
feature was making the language harder to write in.

---

## 2. The Insight

`count of xs`, `lower of s`, `whole of n` were **already call syntax** —
character-for-character identical to a user's `detail of id`. They were
keywords for no reason except that the parser had a branch for them.

So they do not need to be keywords. They can be **builtin functions**: names
the parser knows about only so a bare `count of xs` reads as a call rather
than a variable, with no knowledge of what they do.

That removed seven words at once: `count`, `text`, `lower`, `upper`,
`whole`, `ask`, `read`.

A word now stays reserved only if the parser must see it to know the *shape*
of a statement. What remains:

```
to give let use show write why        statement shape
if else for each in where             control flow
and or not of as fail                 operators and connectives
true false nothing                    literals
first round places                    operations with distinctive syntax
```

`first`, `round`, and `places` stay because `first 30 of xs` and
`round x to 2 places` are not call syntax — they have their own grammar.
Converting them is possible but is a syntax change, not a lookup change.

---

## 3. Shadowing Is Total, and the Analyser Respects It

Because builtins are ordinary functions, a user definition replaces one
completely:

```
to read of source:
  give "no file is touched"
```

A program that does this performs **no file effect**, and `shapes` reports
none. `test_shadowed_ask_is_not_an_effect` pins this: a user function named
`ask` must not be read as a network call.

This is a real soundness requirement that fell out of the change. An
analyser that saw the *name* `ask` and assumed a network effect would be
reporting a fact about the language rather than about the program.

---

## 4. A Genuine Syntax Tension, Resolved

Removing the `ask` keyword surfaced a conflict between the two call forms.

`ask "https://" + text of n + ".json"` must take the **whole expression**.
But `detail of id + 1` must be `(detail of id) + 1` — locked three sessions
ago, and correct.

Both are right. They are different call forms and should behave differently:

- **`f of x` binds tightly** — "apply this to that one thing"
- **`f x` takes the whole expression** — "apply this to what follows"

Stating it that way makes it a rule rather than an exception, and both
readings are now tested.

### The ambiguity underneath

`f (a) + b` is genuinely ambiguous: an argument list `f(a)` followed by
`+ b`, or one argument `(a) + b`. `add(2, 3)` and `ask (base) + "/x"` look
identical up to the closing paren.

Resolved by lookahead: scan to the matching close paren, and if an
arithmetic or comparison operator follows, the parens were a sub-expression.
`add(2, 3)` is an argument list; `ask (base) + "/x"` is one argument. Both
are tested.

This ambiguity was always latent in the grammar — juxtaposition just made it
reachable.

---

## 5. The Mandate Test

`test_names.py` does what the recommendation asked for: takes every builtin
name and requires it works as a function name — as a one-argument function,
as a zero-argument function, and inside a multi-word name, with the user's
definition being the one that runs.

```
test_every_builtin_name_works_as_a_function_name
test_every_builtin_name_works_as_a_zero_arg_function
test_every_builtin_name_works_inside_a_multiword_name
```

Each iterates the whole set and reports every failure at once, so a future
addition to the builtin list is checked automatically.

Two guards keep the list from regrowing:

- `test_reserved_list_is_only_structural_words` fails if the list exceeds 25.
- `test_structural_words_are_still_reserved` fails if a structural word is
  removed by accident.

---

## 6. What Broke and How It Was Caught

**The analyser went blind.** It looked for `Builtin` AST nodes; `ask` became
a `Call`. 24/52 shapes tests failed instantly, including the oracle. Fixed
by recognising effect builtins as calls — and, importantly, only when
nothing else defines that name.

**The anti-drift test fired twice on my own comments** — first on "swallow"
(contains *allow*), then on "takes precedence" after I reworded. Both were
false positives from substring matching, both fixed by rewording rather than
weakening the check. Third session running that this tripwire has caught
prose rather than drift, which is a small cost for a check that would catch
the real thing.

---

## 7. What Is Not Built

- **`first`, `round`, `places` as functions.** Each has its own grammar
  (`first 30 of xs`, `round x to 2 places`). Converting them means changing
  the syntax, not just the lookup.
- **`show` and `write` as functions.** Both are statements with effects, and
  making them shadowable needs a decision about what `show` shadowing means
  for a program's console surface.
- **A builtin listing.** No way to ask the language what builtins exist.
- **Selective import, private functions, versioning** — unchanged.

---

## 8. Recommendation for the Next Session

**Selective import and rename-on-import.** It is now the oldest outstanding
item and the only answer to a collision between two modules a consumer does
not control. Today the advice is "rename one of them," which a consumer
cannot do for third-party code.

The design question worth resolving first: whether `use net taking fetch
package` (selective) or `use net as fetching` (qualified alias) fits the
grain better. Given this session's evidence that prose-like reading is what
the whole syntax is organised around, selective import probably wins — but
that should be checked against a real example rather than assumed.

---

## 9. Test Summary

```
test_planes.py    50/50    language
test_shapes.py    52/52    analyser, modules, namespacing, oracle
test_numbers.py   31/31    exactness, rounding, boundaries, limits
test_names.py     15/15    every builtin name usable as a name
                  -------
                  148/148
```

Anti-drift greps clean.
