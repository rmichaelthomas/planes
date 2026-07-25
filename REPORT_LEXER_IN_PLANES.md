# The Lexer, Written in Planes — Session Report

**Date:** July 25, 2026
**Session type:** Probe with a deliverable — Route B (self-hosted interpreter) stage one, per the build prompt's own framing: not a feature build, a test of whether the language can carry a real program.
**Mandate:** Write a lexer for Planes, in Planes, checked against `lexer.py`'s output on the existing corpus. Phase 0 (capability probe) is blocking; if capability 1 or 2 comes back MISSING, stop and report rather than invent a workaround.
**Result:** Halted at Phase 0, exactly as the build prompt's own provenance section anticipated as a live possibility. Two of six probed capabilities are MISSING. Phases 1-4 are void. 523/523 tests still passing (unchanged from baseline), `ruff check .` and `mypy .` clean, `audit_locked_vs_built.py` and `python3 grammar_gen.py --check` both exit 0. No language file touched.

---

## 1. What Shipped, and What Did Not

**Shipped:**
- `probe/` — six minimal `.planes` programs, one per required capability, each run against this repo unmodified at `24a0f65`.
- `PROBE_LEXER.md` — the six verdicts, exact transcripts, and the reasoning behind each, including a structural trace (not just an empirical guess) of why capability 2 fails the way it does.
- This report.

**Not shipped, and why:** everything from Phase 1 onward — `grammar/vocabulary.planes`, the `grammar_gen.py` emitter, `lexer.planes`, `test_lexer_in_planes.py`, `lexer-in-planes-verification.md`. The build prompt is explicit, in three separate places (§1, §6 invariant 7/§7 failure mode 1, and the provenance section's closing paragraph), that a MISSING result on capability 1 or 2 voids everything below Phase 0. It came back MISSING on both. Writing any of Phases 1-4 anyway — even "just the vocabulary table, since that doesn't need string-walking" — would have been exactly the failure mode the prompt names first: fixing the language's absence by working around it instead of reporting it. The vocabulary emitter in particular was tempting to do anyway, since it's genuinely independent of string-walking and would have been real, uncontroversial progress — it was left undone on the view that "the finding is the entire deliverable" (the prompt's own words) means stopping *here*, not cherry-picking the parts of the plan that don't depend on the blocked capability.

---

## 2. The Six Capability Verdicts

| # | Capability | Verdict |
|---|---|---|
| 1 | Walk a string (`for each c in some-string:`) | **MISSING** |
| 2 | Take a character at a position | **MISSING** |
| 3 | Compare characters (`==`, `>=`/`<=` ordering) | WORKS |
| 4 | Accumulate a list immutably (`plus`) | WORKS |
| 5 | Build and read records (`{ }`, `.field`) | WORKS |
| 6 | Dispatch on shape (`when ... is { }`) | WORKS |

Full transcripts and reasoning: `PROBE_LEXER.md`.

---

## 3. The Language Gap, and What It Would Cost to Close

One gap, with two faces:

**No iteration over a string's code points.** `eval_foreach` (`interp.py:779-784`) requires its source to be a Python `list` or `tuple` and raises `not-a-collection` on anything else, strings included. There is no separate code path that would let a string stand in for a sequence in a `for each`.

**No way to isolate a code point at an arbitrary position.** The grammar's only string-extraction primitive is `first n of x` (`parser.py:986-993`) — a single fixed production, no offset argument, returning a growing prefix. There is no `last`, no `drop`, no `rest`, no slice, no index. `first 1 of s` gives the code point at position 0 and nothing else does. Worse than a clean refusal: the natural syntax a user would reach for, `s[1]`, does not raise a syntax error at all. It silently misparses into two unrelated statements (`c = s`, binding the *whole string*, followed by a discarded list-literal expression `[1]`) — confirmed by parsing the probe program's AST directly, not inferred from behavior alone.

**What closing it would cost.** Both faces trace to the same missing primitive: a complement to `first` that returns *the rest* of a string or list after the first *n* elements — `rest n of x`, in the same distinctive-syntax shape as `first`/`round`. With that one construct, capability 1 becomes expressible as ordinary recursion (take the first code point, recurse on the rest, stop when the count is zero) even without fixing `for each` directly, and capability 2 falls out as a special case. This is a small, well-scoped addition — one new keyword, one new `BinOp` case in the lexer's AST, one parser production mirroring `first`'s, one `eval_binop` branch — not a rewrite of the value model or the parser's structure. It is still a language change, which is exactly why it does not appear as a commit in this branch: per the build prompt's invariant 1, this build's mandate is to report the gap, not close it.

A second, smaller finding, worth recording even though it doesn't block anything on its own: `s[1]` failing *silently* rather than with a syntax error is a sharper problem than the missing capability itself. A future author reaching for bracket indexing gets a program that runs, produces a plausible-looking result, and is wrong. If `rest`/index syntax is ever added, closing this silent-misparse hole (making `[` after a primary expression a syntax error today, ahead of any real indexing feature landing) is worth doing as its own small fix, independent of and probably before the larger `rest` addition.

---

## 4. Agreement Table

Not applicable. Phase 3 (the agreement test against `lexer.py`) was never reached — there is no `lexer.planes` to check it against.

## 5. Self-Tokenization

Not applicable, for the same reason. Phase 4 was never reached.

---

## 6. What This Build Disproved About This Prompt

Every report in this chain carries this section, and this one is not empty either. The build prompt's own provenance section flagged this as the load-bearing unknown and said, in as many words, that Phases 1-4 would be void if Phase 0 came back MISSING — so in the narrowest sense, the prompt predicted its own possible outcome correctly and nothing was disproved about *that* structure.

What the prompt's optimistic framing got wrong is more specific: §2 (Phase 1) argued at length, correctly, that the vocabulary table should be *generated* rather than hand-duplicated, and structured the whole phase around extending `grammar_gen.py`. That reasoning is sound on its own terms and is still true today — but the phase ordering assumed Phase 1 could reasonably be scoped and estimated independently of Phase 0's result, when in fact Phase 1's entire justification ("so `lexer.planes` performs no `read` effect") presupposes a `lexer.planes` that Phase 0 shows cannot be written yet. The generated-vocabulary design is correct and worth keeping for whenever this build is re-attempted — it just isn't this session's work to do, and the prompt's own "estimated 5 phases plus gate" framing implicitly treated Phase 0 as a checkpoint within the build rather than as the gate on the build's existence.

---

## 7. Is Route B a Weekend or a Month?

**Neither, as scoped.** Route B stage one — a self-hosted lexer — is currently **not buildable at all**, at any time budget, because the language cannot express its innermost loop. The honest framing is a two-step estimate:

- **Closing the language gap** (adding a `rest`/complement-of-`first` construct, end to end: lexer, parser, interpreter, tests, docs) is a small, well-understood change — a few hours to a day for someone fluent in this codebase's conventions, based on the shape of comparable additions already in the repo (`with`/`plus` at v5.0 §72, `when` at §74 — each landed as a single-session build per the existing `REPORT_*.md` chain).
- **Then** writing the lexer itself, once string-walking exists, is very plausibly a weekend: four of six required primitives already work cleanly (comparison, list accumulation, records, shape dispatch), and this session's reading of `lexer.py` found nothing else in its output contract that looks language-blocking — the regex-free character classification the build prompt anticipated as the hard part is mechanical once iteration exists, and indentation handling (flagged as the likely hardest remaining piece) is a stateful loop over already-classified lines, not a new expressiveness problem.

So: **a weekend, gated behind a small language change that has to happen first and is out of this build's mandate to make.** That gate is the answer this build was commissioned to produce.
