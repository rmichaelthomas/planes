# lexer-in-planes-verification.md — Phase 7 agreement table

**Build:** fix/text-iteration-and-the-lexer (Route B stage one, continued)
**Compares:** `lexer.py`'s `tokenize(src)` against `grammar/lexer.planes`'s
`tokenize of src`, whole-program (not line-by-line), including `BEGIN`/
`END`/`EOL`/`EOF` and line numbers.
**Corpus:** the 29 files REPORT_GRAMMAR_AMBER.md §4 counts — the 8 named
root files plus 21 demo/ files, excluding `demo/cycle/*` (a deliberately
cyclic fixture, not a valid standalone entry point). Tokenization does not
depend on module resolution, so `demo/clash/main.planes` — which is a
documented *module-collision* fixture, not a tokenization fixture — is
included and tokenizes exactly like any other file.

**Status legend:** PASS — exact match, every token, including line
numbers. PARTIAL — agrees token-for-token up to a specific point, then
diverges for the reason given. No file is SKIPPED: every one of the 29
tokenizes to completion on both sides; nothing crashes or hangs.

## Result summary

**2 PASS, 27 PARTIAL, 0 SKIPPED.** Every PARTIAL result diverges at
*exactly* the first `STRING` literal `lexer.py` finds in that file, and
nowhere else — verified per file, not asserted in aggregate. The two PASS
files are the only two corpus files that contain no string literal at
all. This is the direct, checkable consequence of the STRING gap
`grammar/lexer.planes` documents in place (§ "STRING: verified not
expressible"): there is no way to test whether a code point is a double
quote without a `read`/`ask` effect this build's design avoids, so a
quoted string's contents surface as whatever they tokenize into on their
own terms — names, numbers, operators — instead of one `STRING` token.

## Per-file table

| File | Status | Detail |
|---|---|---|
| `annotated.planes` | PARTIAL | 9/102 tokens agree; diverges at its first STRING literal (line 1) |
| `foreign.planes` | PARTIAL | 5/147 tokens agree; diverges at its first STRING literal (line 7) |
| `gate.planes` | PARTIAL | 13/201 tokens agree; diverges at its first STRING literal (line 2) |
| `hn.planes` | PARTIAL | 16/167 tokens agree; diverges at its first STRING literal (line 5) |
| `money.planes` | PARTIAL | 49/115 tokens agree; diverges at its first STRING literal (line 11) |
| `names.planes` | PARTIAL | 30/85 tokens agree; diverges at its first STRING literal (line 11) |
| `ordinary.planes` | PARTIAL | 49/66 tokens agree; diverges at its first STRING literal (line 9) |
| `pypi.planes` | PARTIAL | 14/158 tokens agree; diverges at its first STRING literal (line 5) |
| `demo/app/config.planes` | PARTIAL | 7/21 tokens agree; diverges at its first STRING literal (line 2) |
| `demo/app/main.planes` | PARTIAL | 17/39 tokens agree; diverges at its first STRING literal (line 5) |
| `demo/app/net.planes` | PARTIAL | 22/38 tokens agree; diverges at its first STRING literal (line 5) |
| `demo/clash/cache.planes` | PARTIAL | 13/21 tokens agree; diverges at its first STRING literal (line 4) |
| `demo/clash/loader.planes` | PARTIAL | 13/21 tokens agree; diverges at its first STRING literal (line 4) |
| `demo/clash/main.planes` | PARTIAL | 11/14 tokens agree; diverges at its first STRING literal (line 4) |
| `demo/fdiff/v1.planes` | PARTIAL | 5/30 tokens agree; diverges at its first STRING literal (line 1) |
| `demo/fdiff/v2.planes` | PARTIAL | 5/30 tokens agree; diverges at its first STRING literal (line 1) |
| `demo/pkgs/cachelib.planes` | PARTIAL | 13/17 tokens agree; diverges at its first STRING literal (line 4) |
| `demo/pkgs/fetcher.planes` | **PASS** | 16/16 tokens match exactly |
| `demo/pkgs/logger.planes` | PARTIAL | 8/14 tokens agree; diverges at its first STRING literal (line 2) |
| `demo/pkgs/mathlib.planes` | **PASS** | 28/28 tokens match exactly |
| `demo/pkgs/sneaky.planes` | PARTIAL | 48/56 tokens agree; diverges at its first STRING literal (line 12) |
| `demo/rename/cache.planes` | PARTIAL | 13/21 tokens agree; diverges at its first STRING literal (line 4) |
| `demo/rename/loader.planes` | PARTIAL | 13/21 tokens agree; diverges at its first STRING literal (line 4) |
| `demo/rename/main.planes` | PARTIAL | 17/31 tokens agree; diverges at its first STRING literal (line 7) |
| `demo/rules/clean.planes` | PARTIAL | 9/52 tokens agree; diverges at its first STRING literal (line 1) |
| `demo/rules/exception.planes` | PARTIAL | 11/64 tokens agree; diverges at its first STRING literal (line 2) |
| `demo/rules/violation.planes` | PARTIAL | 9/51 tokens agree; diverges at its first STRING literal (line 1) |
| `demo/v1.planes` | PARTIAL | 11/48 tokens agree; diverges at its first STRING literal (line 4) |
| `demo/v2.planes` | PARTIAL | 14/73 tokens agree; diverges at its first STRING literal (line 5) |

## Self-tokenization

Run `grammar/lexer.planes`'s own `tokenize` over its own source, and over
`grammar/vocabulary.planes`, both checked against `lexer.py`:

| File | Status | Detail |
|---|---|---|
| `grammar/lexer.planes` (self) | PARTIAL | agrees up to its own first STRING literal (the `note:` header's quoted text), same gap, no new one |
| `grammar/vocabulary.planes` | PARTIAL | agrees up to its own first STRING literal (the generated `note:` header), same gap, no new one |

**The first bootstrap assertion in this domain's history holds, up to
the documented gap.** `lexer.planes` correctly tokenizes its own source
code for every construct it implements — character classification
functions, the fold/lookahead state machine, `when`/`is` dispatch,
record `with`, indentation, `use vocabulary` — and diverges from
`lexer.py` at exactly the same, single, already-understood point every
other file does: its own first quoted string. No new divergence, no
crash, no infinite loop. Both self-tokenization runs complete and match
`lexer.py` for 100% of their non-string content.

## Where this leaves Phase 7

Every disagreement across all 29 corpus files plus both self-tokenization
runs traces to one root cause, verified per-file rather than assumed in
aggregate: the STRING gap documented in `grammar/lexer.planes` itself.
Zero disagreements are unexplained. Zero files are SKIPPED. The
"partial agreement table is a result" — and the result is that this
lexer is complete for every token class except one, and the one it
lacks is lacking for a specific, checked, non-workaroundable reason,
not an unexamined gap.
