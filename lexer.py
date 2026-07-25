"""Planes prototype — substrate.

Tasks 1-3: values, provenance, functions, collections, records,
comprehensions, and the effects the HN scraper needs.

Gate: does this help run `x = 5; y = 3; z = x + y; why z`?
"""
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

# ================================================================ grammar as data
#
# The language's vocabulary — token classes, reserved words, builtin names,
# effect kinds, and the field-name token set — is loadable data, not code an
# agent has to recall (grammar/README.md, addendum v4.2 section 69.1).
# grammar/vocabulary.json is the single source of truth; this module and
# parser.py both load it rather than each carrying their own literal.

GRAMMAR_FORMAT_VERSION = 1
_REQUIRED_VOCAB_KEYS = ("token_classes", "keywords", "builtins",
                        "effect_kinds", "field_name_token_kinds")


class GrammarDataError(Exception):
    """The vocabulary file could not be loaded — refuse, don't guess.

    lexer.py cannot import interp.py's PlanesError (interp.py imports
    lexer.py; the reverse would be a cycle), so this is a small standalone
    exception in the same tag/detail/fix shape, matching the refuse-don't-
    guess contract records_from_json already keeps for the record format.
    """
    def __init__(self, tag, detail="", fix=""):
        self.tag = tag
        self.detail = detail
        self.fix = fix
        msg = tag
        if detail:
            msg += f": {detail}"
        if fix:
            msg += f"\n  try: {fix}"
        super().__init__(msg)


class PlanesSyntaxError(Exception):
    """A malformed program — refuse, don't guess.

    Defined here rather than in parser.py because tokenize() below must be
    able to raise it (an unrecognized string escape, or a trailing
    backslash that consumes the string's closing quote): parser.py already
    imports lexer.py, so the reverse import would cycle. parser.py picks
    this up via `from lexer import *` and keeps raising it exactly as
    before; PlanesAmbiguity still subclasses it there.
    """
    pass


def _load_vocabulary():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "grammar", "vocabulary.json")
    fix = "reinstall planes, or regenerate with python3 grammar_gen.py"
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise GrammarDataError(
            "grammar-data-missing",
            f"{path} could not be read ({e.strerror or e})", fix) from e
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise GrammarDataError(
            "grammar-data-missing", f"{path} is not valid JSON ({e})", fix) from e
    version = doc.get("format")
    if version != GRAMMAR_FORMAT_VERSION:
        raise GrammarDataError(
            "grammar-data-missing",
            f"{path} format {version!r} is not {GRAMMAR_FORMAT_VERSION}",
            "regenerate with a matching version of planes")
    missing = [k for k in _REQUIRED_VOCAB_KEYS if k not in doc]
    if missing:
        raise GrammarDataError(
            "grammar-data-missing",
            f"{path} is missing: {', '.join(missing)}", fix)
    return doc


_VOCAB = _load_vocabulary()

# ================================================================ tokens

# Order is load-bearing — FINGERPRINT must precede NUMBER, OP must follow
# NAME — and grammar/vocabulary.json preserves it (test_grammar_data.py
# asserts this); JSON array order is what this list trusts.
TOKEN_SPEC = [(t["name"], t["pattern"]) for t in _VOCAB["token_classes"]]
TOKEN_RE = re.compile("|".join(f"(?P<{n}>{p})" for n, p in TOKEN_SPEC))

# Reserved words are only those that carry structure: a word the parser must
# see to know the shape of a statement. Everything else that used to be a
# keyword — count, text, lower, upper, whole, ask, read — is now an ordinary
# builtin function, callable as `count of xs` exactly like a user's own
# `detail of id`, and shadowable by a user function of the same name.
#
# The test is in test_names.py: every word NOT in this set must work as a
# function name. In a language whose names read as prose, `count` and `text`
# and `read` are words people reach for.
#
# grammar/vocabulary.json is where the six-category grouping this comment
# used to carry now lives, as data (`keyword_categories`) — the comment
# groupings were real structure, and the JSON file is the only other place
# that structure is recorded.
KEYWORDS = {e["word"] for e in _VOCAB["keywords"]}


@dataclass
class Token:
    kind: str
    value: str
    line: int

    def __repr__(self):
        return f"{self.kind}({self.value!r})"


# The four escapes a STRING literal may contain (v9.0 §105: text is a
# sequence of Unicode code points, and the literal syntax must be able to
# denote any such sequence — REPORT_STRING_ESCAPES.md). No numeric escapes
# (\x41, A): those reintroduce the opacity a magic-number `chr of n`
# builtin was declined for. Resolved here, at token construction, so a Str
# AST node always holds already-resolved text (parser.py, interp.py do not
# need to know escapes exist).
STRING_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "t": "\t"}

# The inverse of STRING_ESCAPES, for any code path that prints a string
# value back as Planes source (render.py's Str case, interp.py's why_tree
# `because` line) rather than as a plain value (interp.py's fmt, for
# `show`/`why`'s printed derivation, deliberately does not re-quote at
# all). A single character-at-a-time pass, each character mapped
# independently to its escaped form (or left as itself) -- no ordering
# hazard from a separate backslash-doubling pass, since backslash is
# just another entry here, produced once per original character.
STRING_UNESCAPE = {v: "\\" + k for k, v in STRING_ESCAPES.items()}


def escape_string_literal(s):
    """`s`, re-escaped as the content of a Planes STRING literal — the
    exact text between the delimiting quotes that STRING's own regex
    would need to see to resolve back to `s`. `render(parse(src))` must
    parse to an equal AST for every program (render.py's module
    docstring); without this, a string containing a quote, backslash,
    newline, or tab renders to source that either reparses to a
    different value or does not reparse at all (fix/string-escapes-and-
    bootstrap: none of those four could occur in a string before this
    build, so nothing exercised the gap until now)."""
    return "".join(STRING_UNESCAPE.get(c, c) for c in s)


def _resolve_string_escapes(raw, lineno):
    """`raw` is a STRING token's content between its delimiting quotes,
    exactly as STRING's regex matched it — an escape is still the two raw
    source characters (e.g. backslash then `n`). STRING's pattern
    (`(?:\\.|[^"\\])*`) only ever matches a backslash paired with a
    following character, so a backslash here is never the last character
    of `raw`; an unmatched trailing backslash instead fails the STRING
    match entirely and is caught in tokenize() as an unterminated string.
    """
    out = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == "\\":
            nxt = raw[i + 1]
            if nxt not in STRING_ESCAPES:
                raise PlanesSyntaxError(
                    f"line {lineno}: unrecognized escape '\\{nxt}' in a "
                    f"string literal -- the four recognized escapes are "
                    f'\\" \\\\ \\n \\t')
            out.append(STRING_ESCAPES[nxt])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def tokenize(src):
    """Indentation-sensitive. Emits EOL, BEGIN, END.

    Scans each line at an explicit position (`TOKEN_RE.match(stripped,
    pos)`, anchored, rather than `TOKEN_RE.finditer`) so a position where
    no token class matches is visible as such, instead of finditer's
    default of silently skipping ahead to the next match. The only place
    that currently matters is a `"` that fails to start a valid STRING
    match — a trailing backslash consumed the closing quote as an escape
    (`\\"`) instead of ending the string, so the string is unterminated;
    every other kind of stray character is skipped exactly as before.
    """
    out = []
    indents = [0]
    lineno = 0
    for lineno, raw in enumerate(src.split("\n"), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent > indents[-1]:
            indents.append(indent)
            out.append(Token("BEGIN", "", lineno))
        while indent < indents[-1]:
            indents.pop()
            out.append(Token("END", "", lineno))
        pos, n = 0, len(stripped)
        while pos < n:
            m = TOKEN_RE.match(stripped, pos)
            if m is None:
                if stripped[pos] == '"':
                    raise PlanesSyntaxError(
                        f"line {lineno}: unterminated string literal -- a "
                        f"backslash right before the closing quote escapes "
                        f'that quote (\\") instead of ending the string; '
                        f"the four recognized escapes are "
                        f'\\" \\\\ \\n \\t -- write \\\\ for a literal '
                        f"trailing backslash")
                pos += 1
                continue
            kind, val = m.lastgroup, m.group()
            if kind in ("WS", "COMMENT"):
                pos = m.end()
                continue
            if kind == "NAME" and val in KEYWORDS:
                kind = val.upper()
            elif kind == "STRING":
                val = '"' + _resolve_string_escapes(val[1:-1], lineno) + '"'
            out.append(Token(kind, val, lineno))
            pos = m.end()
        out.append(Token("EOL", "", lineno))
    while len(indents) > 1:
        indents.pop()
        out.append(Token("END", "", lineno))
    out.append(Token("EOF", "", lineno + 1))
    return out


# The closed vocabulary of effect kinds, grouped by boundary. Lives here,
# rather than in shapes.py where it originated, because the parser also
# needs it — to validate a rule's effect kind at parse time — and parser.py
# cannot import shapes.py (shapes.py imports parser.py; the reverse would be
# a cycle). Closed is the point: an open vocabulary cannot be searched or
# diffed across packages, and duplicating it in two files would let the two
# copies drift. Source of truth is grammar/vocabulary.json.
EFFECT_KINDS = {e["kind"]: e["boundary"] for e in _VOCAB["effect_kinds"]}


# ================================================================ AST

@dataclass
class Num:      value: Any
@dataclass
class Str:      value: str
@dataclass
class Bool:     value: bool
@dataclass
class Nothing:  pass
@dataclass
class Var:      name: str
@dataclass
class ListLit:  items: list
@dataclass
class RecordLit:
    fields: list   # list of (name, expr) pairs, source order preserved
@dataclass
class RecordUpdate:
    """`base with name: expr, ...` (v5.0 §72) — a new record differing in
    the named fields; the base is untouched. Distinct from the `with` in
    `use x with a as b`, which the Use statement parses entirely on its
    own and never reaches expression parsing."""
    base: Any
    fields: list   # list of (name, expr) pairs, same shape as RecordLit
@dataclass
class ListPlus:
    """`base plus item` (v5.0 §72) — a new list with item appended; the
    base is untouched."""
    base: Any
    item: Any
@dataclass
class BinOp:
    op: str
    left: Any
    right: Any
@dataclass
class Not:      expr: Any
@dataclass
class IsNothing: expr: Any
@dataclass
class Field:
    obj: Any
    name: str
@dataclass
class Assign:
    name: str
    expr: Any
    is_let: bool = False
    annotation: Any = None       # a Because, or None — the rationale, never evaluated
@dataclass
class Why:      expr: Any
@dataclass
class Use:
    module: str
    # Renames, as (original, new). The answer to a collision between two
    # modules a consumer does not control — the consumer cannot edit either
    # module, so the fix has to live at the point of use.
    renames: tuple = ()
@dataclass
class FuncDef:
    name: str
    params: list
    body: list
@dataclass
class Call:
    name: str
    args: list
    line: int = 0
@dataclass
class Give:     expr: Any
@dataclass
class Show:
    expr: Any
    line: int = 0
@dataclass
class ForEach:
    var: str
    source: Any
    where: Any
    body: list
    is_expr: bool = False
@dataclass
class If:
    cond: Any
    then: list
    els: list
@dataclass
class When:
    """`when subject is { field: expr, bindname, ... }: ... else: ...`
    (v5.0 §74) — dispatch on record shape and field binding, never on a
    type tag. `pattern` is a list of (field, matcher) pairs; a matcher is
    either ("match", expr) — the field must equal this value — or
    ("bind", name) — bind the field's value into the branch. A missing
    field is simply no match, not an error; a present-but-wrong-type
    match constraint raises through the same guarded equal() as `==`
    (§59) — no separate, silently-lenient comparison path."""
    subject: Any
    pattern: list
    body: list
    els: list
@dataclass
class OrFail:
    expr: Any
    tag: str
    # An optional handler block, opened by `:` right after the tag. When
    # present, a failure does not propagate: `tag` binds to the error as an
    # ordinary record ({tag, detail}, plus path when the error is a
    # comparison mismatch) and the block runs, discriminated with the
    # existing if/field-access machinery — no new dispatch mechanism.
    # None keeps the original rename-and-reraise behavior.
    handler: Any = None
@dataclass
class Builtin:
    name: str
    arg: Any
@dataclass
class Foreign:
    """A function implemented outside Planes.

    `doing` is a claim by whoever wrote the declaration, not a fact the
    analyser derived. Omitting it does NOT mean pure — it means unknown,
    and unknown is reported.
    """
    name: str
    params: list
    target: str
    # (kind, target) pairs. Target is one of:
    #   ("literal", "https://api.example.com")  a fixed destination
    #   ("param",   "url")                      whatever the caller passes
    #   None                                    not stated
    effects: tuple = ()
    declared: bool = False      # was `doing` written at all
    line: int = 0                # for the violation message, when a rule
                                  # matches an effect this declaration claims
@dataclass
class WriteTo:
    value: Any
    dest: Any
    line: int = 0
@dataclass
class Round:
    value: Any
    places: Any
@dataclass
class Rule:
    """A constraint on what the program may do.

    Evaluated, never executed (unbound v2.0 §33). The checker reads it; the
    interpreter must not.
    """
    name: str                    # bracketed label, brackets stripped
    subject: str                 # what the rule applies to; "anything" is the wildcard
    kind: str                    # an effect kind from EFFECT_KINDS
    target: Optional[str] = None # a specific destination, or None for any
    line: int = 0                # for the violation message
    supersedes: Optional[str] = None  # name of an earlier rule this replaces
    # Appended rather than inserted earlier so every existing positional
    # Rule(...) construction (four in test_rules.py alone) keeps working
    # and defaults to the behavior that shipped before permits existed.
    assertion: str = "forbid"    # "forbid" (may not) or "permit" (may)
    supersedes_fingerprint: Optional[str] = None  # the @xxxxxx a supersedes
                                                   # clause was written against
    annotation: Any = None       # a Because, or None — the rationale, never evaluated


@dataclass
class Because:
    """Rationale attached to a statement. Never executes."""
    text: str
    line: int = 0
@dataclass
class Note:
    """A standalone annotation block. Never executes."""
    entries: list   # list of (kind, value): ("from", "..."), ("derives-from", "rule-name")
    line: int = 0
