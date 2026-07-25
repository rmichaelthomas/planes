# lexer-in-planes-verification.md — full agreement table

**Build:** fix/string-escapes-and-bootstrap (Route B stage one, closed)
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
numbers. No file is SKIPPED: every one of the 29 tokenizes to completion
on both sides; nothing crashes or hangs.

## Result summary: 29 PASS, 0 PARTIAL

**Every corpus file matches `lexer.py`'s token stream exactly, in full —
not up to a point, the whole stream.** The prior build
(fix/text-iteration-and-the-lexer, PR #11) left 27 of these 29 PARTIAL,
each diverging at exactly its first `STRING` literal: there was no way
to write a Planes string literal containing a double quote, so
`grammar/lexer.planes` had no way to test "is this character a quote"
and could not tokenize `STRING`. fix/string-escapes-and-bootstrap closed
that gap directly, in the grammar: `\"` (among `\\` `\n` `\t`) makes the
quote character writable, and `grammar/lexer.planes`'s new STRING
section uses exactly that to detect and tokenize a string correctly,
including its own escape sequences. Every file that was PARTIAL for that
one, single, already-understood reason is now PASS for the same reason
closed.

## Per-file table

| File | Status | Tokens |
|---|---|---|
| `annotated.planes` | **PASS** | 102/102 |
| `foreign.planes` | **PASS** | 147/147 |
| `gate.planes` | **PASS** | 201/201 |
| `hn.planes` | **PASS** | 167/167 |
| `money.planes` | **PASS** | 115/115 |
| `names.planes` | **PASS** | 85/85 |
| `ordinary.planes` | **PASS** | 66/66 |
| `pypi.planes` | **PASS** | 158/158 |
| `demo/app/config.planes` | **PASS** | 21/21 |
| `demo/app/main.planes` | **PASS** | 39/39 |
| `demo/app/net.planes` | **PASS** | 38/38 |
| `demo/clash/cache.planes` | **PASS** | 21/21 |
| `demo/clash/loader.planes` | **PASS** | 21/21 |
| `demo/clash/main.planes` | **PASS** | 14/14 |
| `demo/fdiff/v1.planes` | **PASS** | 30/30 |
| `demo/fdiff/v2.planes` | **PASS** | 30/30 |
| `demo/pkgs/cachelib.planes` | **PASS** | 17/17 |
| `demo/pkgs/fetcher.planes` | **PASS** | 16/16 |
| `demo/pkgs/logger.planes` | **PASS** | 14/14 |
| `demo/pkgs/mathlib.planes` | **PASS** | 28/28 |
| `demo/pkgs/sneaky.planes` | **PASS** | 56/56 |
| `demo/rename/cache.planes` | **PASS** | 21/21 |
| `demo/rename/loader.planes` | **PASS** | 21/21 |
| `demo/rename/main.planes` | **PASS** | 31/31 |
| `demo/rules/clean.planes` | **PASS** | 52/52 |
| `demo/rules/exception.planes` | **PASS** | 64/64 |
| `demo/rules/violation.planes` | **PASS** | 51/51 |
| `demo/v1.planes` | **PASS** | 48/48 |
| `demo/v2.planes` | **PASS** | 73/73 |

`demo/pkgs/fetcher.planes` and `demo/pkgs/mathlib.planes` are the only
two corpus files with no string literal at all — they were already PASS
before this build (`test_exactly_two_corpus_files_have_no_string_literal`
establishes this, not assumes it) and remain PASS now for the same
reason plus the new one: every file matches exactly, string-bearing or
not.

## Self-tokenization — the bootstrap assertion, closed

Run `grammar/lexer.planes`'s own `tokenize` over its own source, and over
`grammar/vocabulary.planes`, both checked against `lexer.py`:

| File | Status | Tokens |
|---|---|---|
| `grammar/lexer.planes` (self) | **PASS** | 3835/3835 |
| `grammar/vocabulary.planes` | **PASS** | 159/159 |

**Complete self-tokenization now holds, stated in those words.** A
lexer for Planes, written in Planes, tokenizes its own source —
`grammar/lexer.planes`, 3835 tokens including every STRING literal in
its own doc comments and pending-state records, and the generated
`grammar/vocabulary.planes`, 159 tokens — to the exact same stream
`lexer.py` produces. Nothing is approximate, nothing stops early, no
divergence survives anywhere in either file. This is the first closed
bootstrap assertion in this domain's history: the previous build closed
every other construct and left this one gap, checked and named rather
than guessed around; this build closes the gap itself, in the grammar,
and the self-tokenization runs are now a permanent test
(`test_lexer_planes_tokenizes_itself_exactly`,
`test_lexer_planes_tokenizes_vocabulary_planes_exactly` in
`test_lexer_in_planes.py`), not a probe.

## Where this leaves Route B stage one

Zero disagreements remain across all 29 corpus files and both
self-tokenization runs. `grammar/lexer.planes` tokenizes every
construct `lexer.py` produces a token for, including `STRING` with its
four escapes, with no known remaining gap in tokenization itself. The
one gap this build's own STRING section documents in place — that a
`to` function has no way to raise a custom-message error the way
`lexer.py` raises `PlanesSyntaxError` on malformed input — is untested
by this corpus (every string in it is well-formed; ESCAPE_AUDIT.md)
and is a narrower, separate gap in error-signaling from ordinary Planes
code, not in tokenization. See REPORT_STRING_ESCAPES.md for its cost.
