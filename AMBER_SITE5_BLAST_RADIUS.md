# AMBER_SITE5_BLAST_RADIUS.md

**Build:** fix/recursion-leak-and-fifth-amber-site, Phase 2a
**Question:** how often does the `f of x <op> y` shape — `of` binding its
argument to a single primary, tighter than every binary operator, so
`countdown of n - 1` parses as `(countdown of n) - 1` — actually appear in
the real corpus, and is the existing parse what the author meant each time?
**Method:** `scripts/find_amber_site5_candidates.py`, a detection-only pass
using the real tokenizer (`lexer.tokenize`), not a text regex. It flags
every `NAME of <bare primary>` immediately followed by a binary-operator
token (`+ - * / < > <= >= == != and or plus in`) — the same shape a fifth
amber site would refuse on, since amber refuses by syntactic shape, not by
asking whether the ambiguity is real. Nothing was changed to produce this
report; the parser is untouched.
**Corpus scanned:** every `.planes` file under the repo root, `demo/`,
`grammar/`, and `probe/` (36 files).

## Result: 8 candidate sites, in 3 files

| # | File:line | Fragment | Existing parse | Author's evident intent | Match? |
|---|---|---|---|---|---|
| 1 | `demo/rules/clean.planes:7` | `"read " + text of size + " bytes"` | `("read " + (text of size)) + " bytes"` | string concatenation | **yes** |
| 2 | `demo/rules/violation.planes:8` | `"read " + text of size + " bytes"` | `("read " + (text of size)) + " bytes"` | string concatenation | **yes** |
| 3 | `grammar/lexer.planes:17` | `is-digit of c or is-lower-hex or is-upper-hex` | `(is-digit of c) or is-lower-hex or is-upper-hex` | boolean OR of three predicates | **yes** |
| 4 | `grammar/lexer.planes:25` | `is-alpha of c or c == "_"` | `(is-alpha of c) or (c == "_")` | boolean OR of two conditions | **yes** |
| 5 | `grammar/lexer.planes:28` | `is-name-start of c or is-digit of c` | `(is-name-start of c) or (is-digit of c)` | boolean OR of two predicates | **yes** |
| 6 | `grammar/lexer.planes:386` | `"line " + text of line-no + ": unterminated..."` | `("line " + (text of line-no)) + "..."` | string concatenation | **yes** |
| 7 | `grammar/lexer.planes:391` | `"line " + text of line-no + ": unterminated..."` | `("line " + (text of line-no)) + "..."` | string concatenation | **yes** |
| 8 | `hn.planes:10` | `ask "https://..." + text of story-id + ".json"` | `ask ("https://..." + (text of story-id) + ".json")` | string concatenation, inside `ask`'s own juxtaposition argument | **yes** |

## Per-instance judgment

Every one of the 8 falls into one of two shapes, and in both, the
*alternate* reading (the one amber would exist to warn about) does not
even type-check under this language's guarded semantics:

- **`text of X + "literal"` (5 instances: #1, #2, #6, #7, #8).** The
  alternate reading is `text of (X + "literal")` — concatenating a number
  (`size`, `line-no`, `story-id`) with a string *before* converting to
  text. `apply_op`'s `+` only accepts string+string, list+list, or
  number+number (`interp.py` `cannot-combine`); a number-plus-string
  would raise immediately. No author intending real code would write
  this and mean the alternate reading — it would never run.
- **`pred of c or other-pred` (3 instances: #3, #4, #5).** The alternate
  reading is `pred of (c or other-pred)` — passing a boolean-combination
  expression to a one-argument character predicate. `is-digit`,
  `is-alpha`, and friends are written to compare `c` against character
  literals; passing them a boolean value produces nonsense results, not
  a runtime error, but nothing about `grammar/lexer.planes`'s logic (a
  lexer classifying one character at a time) supports reading it that
  way — the OR-of-predicates reading is the only one that makes the
  function's own name and surrounding logic cohere.

**In all 8 cases, the existing parse is what the author meant.** Zero
instances match the ruling's own paradigm case — `f of x - 1`, arithmetic
inside the argument — anywhere in the real corpus. Every hit is a `+`
(string concatenation) or `or` (boolean chain), never `- * / < > <= >= ==
!=`.

## Decision (Phase 2b): decline

Per the build prompt's own framing, this is the "many instances, or any
where the current parse is clearly what was meant" branch, not the "zero
or few, all clearly intentional" branch — and it is not a close call: it
is **8 for 8**.

The reasoning is not just volume. Amber's other four sites refuse by
*shape*, not by semantic judgment of which reading the author "really"
meant — that is the whole design (`raise_amber_multiword` fires whenever
both a short and long name are simultaneously defined, regardless of which
one a human reader would obviously intend). A fifth site built the same
way would refuse on the syntactic shape alone, with no way to tell "this
`+` is clearly concatenation" from "this `-` is clearly a mistake." Landing
it would therefore refuse **all 8** of these existing, correct, currently-
passing corpus files — turning working code into a syntax error for a
distinction the language's own type-checking already makes moot at
runtime. That is the fire-rate-nonzero outcome Phase 2b's second branch
exists to catch, discovered here at the measurement stage rather than
after landing and reverting.

**Ruling 3 is declined.** The parser is unchanged: no fifth entry in
`grammar/vocabulary.json` or `grammar/messages/amber.json`, no new
`raise_amber_*` method, no site-count change anywhere it is currently
asserted (`grammar/messages/amber.json`'s four templates by distinct
`site` location, `PROBE_PARSER.md`, `REPORT_FAIL_AND_PARSER_PROBE.md`,
`REPORT_GRAMMAR_AMBER.md` — all historical/generated and left as they
are). Amber stays at four sites; fire rate stays zero on the corpus,
unchanged by this measurement.

This is not a failure to execute Ruling 3 — it is Ruling 3 executed
exactly as written: "measured first," and the measurement is the answer.
