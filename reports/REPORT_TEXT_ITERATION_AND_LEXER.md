# Text Is Iterable, the Bracket Misparse Closed, and the Lexer Written in Planes — Session Report

**Date:** July 25, 2026
**Session type:** Three conformance fixes plus Route B stage one, resumed and completed — not a feature build in the ordinary sense; each fix closes a lock the interpreter was found to contradict, and the lexer is checked by agreement with `lexer.py`, not designed from scratch.
**Mandate:** Fix `for each` to iterate a string's code points (v9.0 §105), turn the `s[1]` silent misparse into a syntax error, verify loop accumulation (v4.0 §58) still holds, then write `lexer.planes` and check it against `lexer.py` across the full corpus, self-tokenizing at the end.
**Result:** All three conformance fixes shipped (the third needed no code change — it already held). `lexer.planes` is complete for every token class `lexer.py` produces except one: `STRING`, verified impossible to express in the language as it stands, not merely unattempted. 556/556 tests passing (523 baseline + 33 new), `ruff`/`mypy`/`audit_locked_vs_built.py`/`grammar_gen.py --check` all clean, reserved-word count unchanged at 32. Agreement across the 29-file corpus: 2 PASS (files with no string literal), 27 PARTIAL (agree up to their first string literal, diverge there, nowhere else), 0 SKIPPED, 0 unexplained. Self-tokenization holds up to the same documented gap.

---

## 1. What Shipped, and What Did Not

**Shipped:**
- `interp.py`: `eval_foreach` accepts `str` alongside `list`/`tuple`, iterating code points (Phase 1).
- `parser.py`: `parse_postfix` raises a syntax error naming `first n of x` when `[` follows a completed primary, closing the silent misparse `PROBE_LEXER.md` found (Phase 2).
- `probe/accumulate_in_loop.planes` + a permanent `test_text.py` assertion: loop accumulation already worked; no fix needed (Phase 3).
- `probe/fold_tokens.planes`: the fold-lexer's innermost loop, proven on the first attempt (Phase 4).
- `grammar_gen.py`'s third emitter, `grammar/vocabulary.planes`: keywords/builtins/operators as generated Planes zero-argument functions (Phase 5 — corrected mid-build from an initial plain-binding design that does not actually cross a module boundary; see §2 below).
- `grammar/lexer.planes`: a complete lexer for every token class except `STRING` — character classification, the fold/lookahead-buffer state machine for names/operators/numbers/fingerprints, comments, line-splitting, and indentation via a cons-list stack (Phase 6).
- `test_lexer_in_planes.py` + `lexer-in-planes-verification.md`: the agreement test and its per-file table, plus self-tokenization (Phase 7).

**Not shipped:** `STRING` tokenization. Not incomplete — verified impossible without a language change or a host effect this build's design avoids. Full argument in §4.

---

## 2. The Conformance Fixes, Each as a Defect Against Its Lock

### Phase 1 — `for each` over a string (defect against v9.0 §105)

§105 locks text as a sequence of Unicode code points. `count of` a string already counted code points; `first n of` a string already returned a prefix string. `for each` was the outlier: `eval_foreach` (`interp.py:779-784`) tested `isinstance(source.value, (list, tuple))` and raised `not-a-collection` for a string, in direct conflict with the same lock the other two operations honored. Fixed with a one-line `isinstance` widening — Python's native string iteration is already code-point iteration, so no further logic was needed. The comprehension form still yields a list (the result follows the body, not the source, matching every other `for each`); an empty string iterates zero times; `where` filtering is unchanged; a number or record still raises `not-a-collection`, now naming strings as acceptable in the fix text.

**Did `shapes.py` need a matching change?** No, and this was read, not assumed. `walk()`'s `ForEach` handling (`shapes.py:573-585`) widens the loop variable to `UNKNOWN` unconditionally and never inspects `node.source`'s *runtime* type — it only walks `node.source` as an expression for effects, which is source-type-agnostic. The two AST-only scans that also touch `ForEach` — `assigned_in` (`shapes.py:763`) and `calls_in` (`shapes.py:816`) — recurse into `n.body` without ever branching on what `n.source` evaluates to. All three sites are, by construction, blind to whether a `for each` source is a list or a string. `test_oracle_effect_inside_string_for_each` in `test_shapes.py` confirms this by running the actual runtime-effect oracle over a program containing a string `for each`.

### Phase 2 — the bracket misparse (a missing syntax error, not a missing feature)

`PROBE_LEXER.md` §2 established, by direct AST inspection, that `c = s[1]` parses as two statements: `Assign(c, Var(s))`, binding `c` to the *whole string*, followed by a discarded `ListLit([1])` — silently wrong, not merely unsupported. This is not an amber case (amber refuses when the name table admits two *viable* parses; here there is exactly one parse and it is not the one anyone means). Fixed in `parse_postfix`, the sole call site of `parse_primary`, right after its `.field` loop exits: an immediately-following `[` now raises `PlanesSyntaxError` naming `first n of x` as what exists. No indexing was added — the fix closes a hole, it does not open a feature. Guarded against over-firing by running the full 29-file corpus through the real module loader (`shapes.analyse_file`, not standalone parsing, since some files depend on cross-file `known_funcs`): 28 files analyse clean, and `demo/clash/main.planes` still raises its documented, pre-existing module-collision error — not a new syntax error. `test_bracket_misparse.py` covers the raise cases and ten legitimate-bracket non-regression cases.

### Phase 3 — loop accumulation (v4.0 §58): confirmed, not fixed

`probe/accumulate_in_loop.planes` (`acc = acc plus c` inside a `for each` statement body, accumulating across iterations of a string) produced the correct result — 3 code points in, `["a", "b", "c"]` out — on the first run. This exercises `Env.set`'s scope-walking assignment (`interp.py:257-265`), which rebinds a name where it already lives by walking up the environment chain — a path no existing test touched, since every prior `for each` test used the comprehension form, whose result list is a different mechanism. No defect, no fix. Promoted to a permanent test in `test_text.py` rather than left as a one-off probe.

---

## 3. Phase 4 — the Fold, Proven First Try

`probe/fold_tokens.planes` splits `"a+bc"` into `NAME`/`OP` tokens using only `for each` over a string, character comparison, `plus`, record literals with `.field`, `with` for record update, and `when ... is` dispatch — including a `when` match constraint against a *variable*, not a literal (`when current is { kind: next-kind }`), confirmed against `interp.py`'s `exec_when` to evaluate the match arm's expression in the current environment rather than treating it as a literal pattern. Output on the first run: `[{kind:"NAME",text:"a"}, {kind:"OP",text:"+"}, {kind:"NAME",text:"bc"}]` — exactly as expected. This is the load-bearing result the rest of the build rests on: it proved the innermost loop before any of the larger lexer was written.

---

## 4. The Language Gap Phase 6 Found — and Why It Is Not Fixed Here

**Capability 2 (arbitrary-position access), withdrawn as a requirement per this build's ruling, was correctly not needed.** The fold-lexer design never asked for it. But a second, independent gap surfaced while writing `STRING` support, one the original `PROBE_LEXER.md` had no reason to find, because it only shows up once you actually try to tokenize quoted text:

**There is no way to write a Planes expression that evaluates to a string containing a double quote.** `grammar/vocabulary.json`'s own `STRING` pattern (`"[^\"]*"`) has no escape sequences, so the character class inside the quotes structurally excludes a quote — verified empirically, not assumed: parsing `x = """` gives `Assign(x, Str(""))`, with the third quote silently unmatched; `x = """"` gives two separate empty strings. No sequence of quote characters ever produces one *containing* a quote, for the same structural reason no source file can express a quote spanning a line break (tokenization splits on newline before any pattern is tried, so embedding a raw newline inside what looks like one string literal just produces two separate, unclosed lines instead). No builtin converts between a code point and its numeric value — `count`/`lower`/`upper`/`text`/`whole`/`ask`/`read`/`normalize`, the entire closed set, does none of this. A `read` or `ask` effect could fetch a quote character from outside the program, but that reintroduces exactly the effect Phase 5's design exists to avoid, and this build adds no new host method to route around it. An exclusion-based approximation — "not alnum, not an operator, not `#`/`@`, not space, so it must be a quote" — is unsound, not just inelegant: `gate.planes`'s own string content contains an apostrophe (`"...March's reconciliation..."`), which is none of those things either, and would end the string early. Checked against the real corpus, not hypothesized.

A companion problem — detecting a **newline**, needed for `tokenize`'s own line-splitting — turned out to have a genuine solution and is *not* a gap: unlike a quote, a newline never needs to be told apart from arbitrary string content, because every character this lexer treats specially outside a string sits at or above the space code point, and a newline is the only one below it any well-formed source file contains. `c < " "` detects it soundly (verified against the interpreter's own `compare()`), which is why `split-lines` and the rest of Phase 6's indentation machinery could be written at all despite the quote finding.

**What closing the STRING gap would cost.** Given the ruling that declined a new `rest`/index construct in this build's own preamble, the narrowest fix in the same spirit would be a small, closed addition — something like a `code point N` / `chr of n` builtin (or the reverse, a way to ask a character's numeric value) — one new builtin, not a keyword, and not a change to the parser's grammar at all. That is a real, bounded piece of work, smaller than the `rest`-construct proposal the prior report priced out. It is still a language change, and per this build's own invariant 1, it is reported here, not written into this branch.

---

## 5. Agreement Table Summary and Self-Tokenization

**2 PASS, 27 PARTIAL, 0 SKIPPED**, across all 29 corpus files (`lexer-in-planes-verification.md` has the full per-file table). The two PASS files — `demo/pkgs/fetcher.planes`, `demo/pkgs/mathlib.planes` — are the only two corpus files with no string literal at all, and match `lexer.py`'s output token-for-token, including `BEGIN`/`END`/`EOL`/`EOF` and line numbers. Every PARTIAL result was checked, per file, to diverge at *exactly* the first `STRING` token `lexer.py` produces and nowhere else — not asserted in aggregate, not eyeballed.

**Self-tokenization holds, up to the same gap.** `lexer.planes` tokenizing its own source, and `grammar/vocabulary.planes`'s source, both agree with `lexer.py` for every token up to their own first quoted string (the `note:` header in each file), then diverge for the identical, already-understood reason — no new divergence, no crash, no infinite loop. This is the first bootstrap assertion in this domain's history, and it holds as far as the language currently allows it to.

---

## 6. What This Build Disproved About This Prompt

The prompt's own framing declined the prior `rest n of x` proposal on the grounds that a fold-based lexer needs iteration, not indexing — and that framing was correct as far as it went. What it did not anticipate, and could not have without someone actually writing the `STRING` branch, is that **the gap this build would hit is not about sequence access at all.** It is about literal representability: a fold-lexer needs zero indexing to walk a string, exactly as argued, but it turns out to need a way to name the quote character it is folding over, and *that* capability was never on either build's radar because neither `PROBE_LEXER.md`'s six probes nor this prompt's ruling had reason to test "can this language express its own string-delimiter as a value." Every one of Phase 0's original six probes still holds, and the fold design's own bet (no indexing needed) also holds. The prompt was right about what it argued and silent about a gap orthogonal to that argument, one only visible from inside the specific problem of tokenizing quoted text.

A smaller thing this build disproved about *itself*, not the prompt: Phase 5's first draft (plain top-level bindings for `keywords`/`builtins`/`operators`) looked correct, passed every existing invariant, and was wrong — `use` only hoists function definitions across a module boundary, not top-level variable bindings, so `lexer.planes` would have gotten `unknown-name` on every reference to the vocabulary tables the moment it tried to `use vocabulary`. Caught before `lexer.planes` was written, by testing the cross-module reference directly rather than trusting that a clean `grammar_gen.py --check` meant the design worked end to end.

---

## 7. Is Route B Stage Two — the Parser — a Weekend or a Month?

**A weekend for a *token-consuming* parser, once the STRING gap closes; not before, for a full one.** Concretely:

- Every non-`STRING` construct this lexer produces — `NAME`, keyword-uppercased tokens, `OP` (all seven multi-character spellings and every single-character one), `NUMBER` (integer and decimal), `FINGERPRINT`, `BEGIN`/`END`/`EOL`/`EOF` — is complete, verified, and matches `lexer.py` exactly. A recursive-descent parser consuming this token stream needs nothing further from the lexer for any construct that does not itself involve a string literal: arithmetic, records, `when` dispatch, `for each`, rules (their names and effect kinds are `NAME`/keyword tokens, not strings), function definitions.
- `STRING` tokens are the one gap, and they are *load-bearing* for a real parser: every corpus file but two uses one, for exactly the things you would expect (URLs, file paths, messages, field values). A parser that cannot consume `STRING` tokens cannot parse the corpus, full stop.
- The gap itself, per §4, is small and precisely scoped: one new builtin (a code-point-to-character conversion, or its inverse), not a parser or grammar change. Once that lands, `STRING` tokenization in `lexer.planes` is a bounded, mechanical addition to the state machine already built (open on quote, accumulate until the matching quote, exactly like every other pending-state branch already in the file) — hours, not days, given the fold architecture is already in place and every other token class already demonstrates the pattern.
- After that: the parser itself, consuming a token stream this lexer can now produce completely, is the kind of build this repo's own `REPORT_*.md` chain shows landing in a single session (`with`/`plus`/`when` at v5.0 §72/§74, tier-2 language and the record plane, each closed in one build).

So: **the lexer is a weekend's work, and it is done modulo one small, precisely-costed builtin.** The parser is very plausibly *also* a weekend once that lands — but "once that lands" is a real gate, not a formality, and this build's mandate does not cross it.
