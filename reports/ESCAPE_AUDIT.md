# ESCAPE_AUDIT.md — Phase 1, corpus backslash audit

**Build:** fix/string-escapes-and-bootstrap
**Base:** `main` at `fdad13b`
**Purpose:** find every backslash inside a string literal across all `.planes`
files in the repo, before the grammar changes meaning. Per §1 of the build
prompt this is blocking: if the set is non-empty, each occurrence is a
migration that must preserve its runtime value.

## Method

1. Enumerated every `.planes` file in the repo (root, `demo/`, `grammar/`,
   `probe/`) with `find . -name "*.planes" -not -path "./.venv/*"` — 40 files.
2. Ran a fixed-string search (`grep -qF '\'`) against each file individually,
   so no regex metacharacter in the pattern itself could produce a false
   negative.
3. For every file that matched, read the surrounding lines directly to
   determine whether the backslash sits inside a `"..."` string literal or
   outside one (comment, identifier, etc.).

## Result: the set is empty

**Zero backslashes appear inside any string literal in the corpus.**

One file contains backslashes at all: `grammar/lexer.planes`, at five line
numbers — 31, 36, 56, 295, 332. Every one of them is inside a `#` prose
comment (Planes' comment syntax, confirmed by reading `grammar/lexer.planes`
itself, e.g. lines 5–9), written by the prior build (PR #11) to document
*in English* the exact defect this build fixes: that `\t` and `\n` were not
writable inside a Planes string literal. None of the five is inside a `"..."`
token. Read in place:

| File | Line | Text | Inside a string literal? |
|---|---|---|---|
| `grammar/lexer.planes` | 31 | `# own note on the STRING token class) -- "\t" in a Planes source file is` | No — `#` comment |
| `grammar/lexer.planes` | 36 | `# silent one: grep -rlP '\t\|\x0b\|\x0c\|\r' across every root and demo/` | No — `#` comment |
| `grammar/lexer.planes` | 56 | `# "\n" < " " is true, '"' < " " is false, every other corpus character` | No — `#` comment |
| `grammar/lexer.planes` | 295 | `#     own STRING pattern is \`"[^\"]*"\`, no escape sequences, so the` | No — `#` comment |
| `grammar/lexer.planes` | 332 | `# lexer.py splits on "\n" before anything else and only then applies` | No — `#` comment |

No other `.planes` file — not `grammar/vocabulary.planes`, not any file in
`demo/`, not any file in `probe/`, not any root fixture (`gate.planes`,
`hn.planes`, `money.planes`, `names.planes`, `ordinary.planes`, `pypi.planes`,
`foreign.planes`, `annotated.planes`) — contains a backslash anywhere, inside
or outside a string.

## Before/after meaning

Since no string literal in the corpus contains a backslash, **no string's
runtime value changes under the new grammar.** Before this build, a
double-quoted STRING token's content was every code point between the
quotes, verbatim, with no character treated specially. After this build, the
same is true *except* that the two-character sequences `\"`, `\\`, `\n`,
`\t` resolve to a single code point (`"`, `\`, newline, tab respectively).
Because none of those two-character sequences occurs in any corpus string
today, every existing string literal in the repository tokenizes to the
exact same value it did before. There is nothing to migrate.

## Conclusion

**The set is empty.** No fixture required updating. No corpus string's
meaning is at risk under the new grammar. Phase 2 may proceed without a
migration step, per §1: "If the set is empty: say so explicitly and continue."
