"""Planes text — STRING literal escapes, and their inverse.

The four escapes a STRING literal may contain (v9.0 §105: text is a
sequence of Unicode code points, and the literal syntax must be able to
denote any such sequence — fix/string-escapes-and-bootstrap,
REPORT_STRING_ESCAPES.md). No numeric escapes (`\\x41`, `A`): those
reintroduce the opacity a magic-number `chr of n` builtin was declined
for.

Why this lives here and not in lexer.py
----------------------------------------
It did, briefly (added there by fix/string-escapes-and-bootstrap,
alongside the escape-aware tokenizer that needed it). Four modules now
need one direction or the other — `lexer.py` (resolution, at token
construction), `render.py` and `interp.py` and `shapes.py`
(`escape_string_literal`, wherever a string-typed AST field is printed
back as a quoted Planes literal) — and none of the last three is the
lexer. It moves to a leaf module, on the pattern `planes_num.py` already
establishes: pure, no project dependencies, importable by anything,
including `rules.py`, which otherwise depends on nothing in this project
at all (its own docstring: "hashlib... is the one import this file has
ever needed — stdlib, not a `shapes` coupling"). A four-line escape
table is not that coupling.

Deliberately does not raise `PlanesSyntaxError` — that class stays in
`lexer.py` (fix/string-escapes-and-bootstrap moved it there for a stated
reason: `tokenize()` must be able to raise it, and `lexer.py` cannot
import `parser.py`, where it used to live). This module has no notion of
"which line" a malformed escape is on, and importing `PlanesSyntaxError`
from `lexer.py` here would make `lexer.py` and `planes_text.py` import
each other. `resolve_string_escapes` raises a plain `ValueError` instead;
`lexer.py` catches it and adds source position.
"""

STRING_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "t": "\t"}

# The inverse of STRING_ESCAPES, for any code path that prints a string
# value back as Planes source (render.py's Str case, interp.py's runtime
# Deriv label and `why`/`explain` output, shapes.py's static derivation
# labels, rules.py's violation/conflict messages) rather than as a plain
# value (interp.py's fmt, for `show`/`why`'s printed derivation,
# deliberately does not re-quote at all). A single character-at-a-time
# pass, each character mapped independently to its escaped form (or left
# as itself) -- no ordering hazard from a separate backslash-doubling
# pass, since backslash is just another entry here, produced once per
# original character.
STRING_UNESCAPE = {v: "\\" + k for k, v in STRING_ESCAPES.items()}


def resolve_string_escapes(raw):
    """`raw` is a STRING token's content between its delimiting quotes,
    exactly as STRING's regex matched it — an escape is still the two raw
    source characters (e.g. backslash then `n`). `grammar/vocabulary.json`'s
    STRING pattern (`(?:\\.|[^"\\])*`) only ever matches a backslash
    paired with a following character, so a backslash here is never the
    last character of `raw`; an unmatched trailing backslash instead
    fails the STRING match entirely, at the tokenizer level, before this
    function is ever called.

    Raises `ValueError(nxt)` — `nxt` the offending character — if `raw`
    contains a backslash not followed by one of the four legal escapes.
    The caller adds source position and the four-escapes fix text; this
    module stays a pure text transform, nothing project-specific.
    """
    out = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == "\\":
            nxt = raw[i + 1]
            if nxt not in STRING_ESCAPES:
                raise ValueError(nxt)
            out.append(STRING_ESCAPES[nxt])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def escape_string_literal(s):
    """`s`, re-escaped as the content of a Planes STRING literal — the
    exact text between the delimiting quotes that STRING's own regex
    would need to see to resolve back to `s`. `render(parse(src))` must
    parse to an equal AST for every program (render.py's module
    docstring); without this, a string containing a quote, backslash,
    newline, or tab renders to source that either reparses to a
    different value or does not reparse at all (fix/string-escapes-and-
    bootstrap: none of those four could occur in a string before that
    build, so nothing exercised the gap until then)."""
    return "".join(STRING_UNESCAPE.get(c, c) for c in s)
