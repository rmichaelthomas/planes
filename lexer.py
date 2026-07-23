"""Planes prototype — substrate.

Tasks 1-3: values, provenance, functions, collections, records,
comprehensions, and the effects the HN scraper needs.

Gate: does this help run `x = 5; y = 3; z = x + y; why z`?
"""
import re
import json
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional


# ================================================================ tokens

TOKEN_SPEC = [
    ("COMMENT", r"#[^\n]*"),
    ("NUMBER",  r"\d+(\.\d+)?"),
    ("STRING",  r'"[^"]*"'),
    ("NAME",    r"[A-Za-z_][A-Za-z0-9_]*(-[A-Za-z0-9_]+)*"),
    ("OP",      r"->|==|!=|<=|>=|[+\-*/=<>().,;:\[\]]"),
    ("WS",      r"[ \t]+"),
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
    "if", "else", "for", "each", "in", "where",
    # operators and connectives
    "and", "or", "not", "of", "as", "fail", "with",
    "foreign", "from", "doing",
    # literals
    "true", "false", "nothing",
    # operations with distinctive syntax the parser must recognise
    "first", "round", "places",
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
class BinOp:
    op: str
    left: Any
    right: Any
@dataclass
class Not:      expr: Any
@dataclass
class Field:
    obj: Any
    name: str
@dataclass
class Assign:
    name: str
    expr: Any
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
@dataclass
class Give:     expr: Any
@dataclass
class Show:     expr: Any
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
class OrFail:
    expr: Any
    tag: str
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
@dataclass
class WriteTo:
    value: Any
    dest: Any
@dataclass
class Round:
    value: Any
    places: Any
