"""Planes prototype — substrate.

Tasks 1-3: values, provenance, functions, collections, records,
comprehensions, and the effects the HN scraper needs.

Gate: does this help run `x = 5; y = 3; z = x + y; why z`?
"""
import re
from dataclasses import dataclass
from typing import Any, Optional

# ================================================================ tokens

TOKEN_SPEC = [
    ("COMMENT",     r"#[^\n]*"),
    # A rule fingerprint — @ plus exactly six hex characters — has to be
    # its own token, ahead of NUMBER and NAME: most fingerprints start
    # with a digit, and NUMBER would otherwise split "@3f9c2d" into a
    # number and a name at the first letter.
    ("FINGERPRINT", r"@[0-9a-fA-F]{6}"),
    ("NUMBER",      r"\d+(\.\d+)?"),
    ("STRING",      r'"[^"]*"'),
    ("NAME",        r"[A-Za-z_][A-Za-z0-9_]*(-[A-Za-z0-9_]+)*"),
    # `@` also appears in OP, as a fallback: a malformed fingerprint (wrong
    # length, non-hex characters) then tokenizes as a lone '@' the parser
    # can catch and name the fix for, rather than silently vanishing.
    ("OP",          r"->|==|!=|<=|>=|[+\-*/=<>().,;:\[\]{}@]"),
    ("WS",          r"[ \t]+"),
]
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
KEYWORDS = {
    # statement shape
    "to", "give", "let", "use", "show", "write", "why",
    # control flow
    "if", "else", "for", "each", "in", "where", "when",
    # operators and connectives
    "and", "or", "not", "of", "as", "fail", "with", "plus",
    "foreign", "from", "doing",
    # literals
    "true", "false", "nothing",
    # operations with distinctive syntax the parser must recognise
    "first", "round", "places",
    # rule plane — a compile-time-only constraint, never executed
    "rule",
}


@dataclass
class Token:
    kind: str
    value: str
    line: int

    def __repr__(self):
        return f"{self.kind}({self.value!r})"


def tokenize(src):
    """Indentation-sensitive. Emits EOL, BEGIN, END."""
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
        for m in TOKEN_RE.finditer(stripped):
            kind, val = m.lastgroup, m.group()
            if kind in ("WS", "COMMENT"):
                continue
            if kind == "NAME" and val in KEYWORDS:
                kind = val.upper()
            out.append(Token(kind, val, lineno))
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
# copies drift.
EFFECT_KINDS = {
    "ask":    "network",     # request-with-response
    "read":   "file",
    "write":  "file",
    "show":   "console",
    "clock":  "ambient",     # the current time
    "random": "ambient",     # entropy
    "env":    "ambient",     # environment variables, process arguments
}


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
