"""Planes canonical renderer — AST back to source text.

Forked from Liminate's renderer, not shared (U-Q12, planes v2.0 §33): the
two languages' grammars diverge enough that a shared renderer would need
its own dialect-switching, which is worse than two small modules.

`render(parse(src))` must parse to an equal AST for every program in the
repo — not byte-identical to the original source, but canonical: the same
formatting decision applied everywhere, every call rendered `name of
(args)`, every compound sub-expression parenthesised. Two things follow
from "canonical, not literal":

- Source position is not preserved. A `line` field on a node is where a
  token happened to fall in someone's original layout, not part of what
  the program means, so round-trip equality here is checked with
  `ast_equal`, which ignores `line` (see its docstring for why parenthesised
  full re-formatting makes exact reformatting-independent equality the
  honest bar, not accidental line-number agreement).
- Every compound sub-expression (BinOp, Not, IsNothing) is parenthesised
  wherever it is not already the outermost expression of its statement.
  This trades minimal-parens prettiness for a renderer with no precedence
  table to get wrong: correctness falls out of always grouping, not out of
  correctly ranking `+` against `and` against `in`.

Calls are the one place the grammar itself forced a design decision, not a
style one. `name(args)` looks safe but is not: `parse_primary`'s `(`
branch decides between "argument list" and "parenthesised sub-expression
that continues" by peeking at the token *after* the closing paren — so
`ask("url") + x` parses `("url") + x` as `ask`'s single argument, not as
`ask("url")` plus `x`. `name of (arg1), (arg2)` has no such lookahead: `of`
takes exactly the parenthesised primaries that follow, at unary precedence,
so wrapping every argument in parens is always safe, for single- and
multi-word names alike (multi-word names cannot use `(` at all — the
parser only merges NAME tokens into a multi-word call ahead of a following
`of`). So every call below renders as `name of (arg1), (arg2), ...`, or a
bare `name` for zero arguments.
"""
import dataclasses

from lexer import (
    Assign,
    BinOp,
    Bool,
    Builtin,
    Call,
    Field,
    ForEach,
    Foreign,
    FuncDef,
    Give,
    If,
    IsNothing,
    ListLit,
    Not,
    Note,
    Nothing,
    Num,
    OrFail,
    RecordLit,
    Round,
    Rule,
    Show,
    Str,
    Use,
    Var,
    Why,
    WriteTo,
)
from rules import check

INDENT = "  "

# Sub-expressions that need parens wherever they are not the outermost
# expression of their statement (see module docstring).
_COMPOUND = (BinOp, Not, IsNothing)


# ================================================================ expressions

def render_operand(node):
    """An expression in a position where the grammar reads at less than
    full precedence (a BinOp side, a Field base, a Round argument): safe
    regardless of what `node` is, because a compound node is wrapped."""
    text = render_expr(node)
    return f"({text})" if isinstance(node, _COMPOUND) else text


def render_expr(node):
    if isinstance(node, Num):
        return node.value.text() if hasattr(node.value, "text") else str(node.value)
    if isinstance(node, Str):
        return f'"{node.value}"'
    if isinstance(node, Bool):
        return "true" if node.value else "false"
    if isinstance(node, Nothing):
        return "nothing"
    if isinstance(node, Var):
        return node.name
    if isinstance(node, ListLit):
        return "[" + ", ".join(render_expr(i) for i in node.items) + "]"
    if isinstance(node, RecordLit):
        fields = ", ".join(f"{k}: {render_expr(v)}" for k, v in node.fields)
        return "{ " + fields + " }" if fields else "{}"
    if isinstance(node, BinOp):
        if node.op == "first":
            return f"first {render_operand(node.left)} of {render_operand(node.right)}"
        return f"{render_operand(node.left)} {node.op} {render_operand(node.right)}"
    if isinstance(node, Not):
        return f"not {render_operand(node.expr)}"
    if isinstance(node, IsNothing):
        return f"{render_operand(node.expr)} is nothing"
    if isinstance(node, Field):
        return f"{render_operand(node.obj)}.{node.name}"
    if isinstance(node, Call):
        return render_call(node)
    if isinstance(node, Round):
        return (f"round {render_operand(node.value)} to "
                f"{render_operand(node.places)} places")
    if isinstance(node, ForEach):
        return render_foreach_expr(node)
    if isinstance(node, OrFail):
        return render_orfail(node)
    if isinstance(node, Builtin):
        # Dead code: the parser no longer builds this node (test_coverage.py
        # marks it unreachable). Kept as a named failure, not a silent
        # fall-through, if that ever stops being true.
        raise ValueError("render_expr: Builtin is unreachable by design")
    raise ValueError(f"render_expr: unhandled node type {type(node).__name__}")


def render_call(node):
    if not node.args:
        return node.name
    args = ", ".join(f"({render_expr(a)})" for a in node.args)
    return f"{node.name} of {args}"


def render_foreach_expr(node):
    where = f" where {render_expr(node.where)}" if node.where is not None else ""
    body = render_expr(node.body[0])
    return f"for each {node.var} in {render_expr(node.source)}{where}: {body}"


def render_writeto_inline(node):
    return f"write {render_expr(node.value)} to {render_expr(node.dest)}"


def render_orfail(node):
    inner = (render_writeto_inline(node.expr) if isinstance(node.expr, WriteTo)
             else render_expr(node.expr))
    return f"{inner} or fail as {node.tag}"


# ================================================================ statements

def render_because_suffix(node):
    if node.annotation is None:
        return ""
    return f' because "{node.annotation.text}"'


def render_assign(node):
    prefix = "let " if node.is_let else ""
    return f"{prefix}{node.name} = {render_expr(node.expr)}{render_because_suffix(node)}"


def render_rule(node):
    verb = "may not" if node.assertion == "forbid" else "may"
    text = f"rule [{node.name}] {node.subject} {verb} {node.kind}"
    if node.target is not None:
        text += f' to "{node.target}"'
    if node.supersedes is not None:
        text += f" supersedes [{node.supersedes}]"
        if node.supersedes_fingerprint is not None:
            text += f" @{node.supersedes_fingerprint}"
    return text + render_because_suffix(node)


def render_note(node, indent):
    lines = [indent + "note:"]
    for kind, value in node.entries:
        if kind == "from":
            lines.append(indent + INDENT + f'from "{value}"')
        elif kind == "derives-from":
            lines.append(indent + INDENT + f"derives-from [{value}]")
    return "\n".join(lines)


def render_use(node):
    text = f"use {node.module}"
    for old, new in node.renames:
        text += f" with {old} as {new}"
    return text


def render_foreign(node):
    text = f"foreign {node.name}"
    if node.params:
        text += " of " + ", ".join(node.params)
    text += f' from "{node.target}"'
    if node.declared:
        if not node.effects:
            text += " doing nothing"
        else:
            claims = []
            for kind, where in node.effects:
                if where is None:
                    claims.append(kind)
                elif where[0] == "literal":
                    claims.append(f'{kind} "{where[1]}"')
                else:   # ("param", name)
                    claims.append(f"{kind} {where[1]}")
            text += " doing " + ", ".join(claims)
    return text


def render_funcdef(node, indent, markers):
    header = f"to {node.name}"
    if node.params:
        header += " of " + ", ".join(node.params)
    header += ":"
    body = render_block(node.body, indent + INDENT, markers)
    return indent + header + "\n" + body


def render_if(node, indent, markers):
    lines = [indent + f"if {render_expr(node.cond)}:"]
    lines.append(render_block(node.then, indent + INDENT, markers))
    if node.els:
        lines.append(indent + "else:")
        lines.append(render_block(node.els, indent + INDENT, markers))
    return "\n".join(lines)


def render_foreach_stmt(node, indent, markers):
    where = f" where {render_expr(node.where)}" if node.where is not None else ""
    header = indent + f"for each {node.var} in {render_expr(node.source)}{where}:"
    body = render_block(node.body, indent + INDENT, markers)
    return header + "\n" + body


def render_stmt(node, indent, markers):
    if isinstance(node, Use):
        return indent + render_use(node)
    if isinstance(node, Foreign):
        return indent + render_foreign(node)
    if isinstance(node, Rule):
        return indent + render_rule(node)
    if isinstance(node, Note):
        return render_note(node, indent)
    if isinstance(node, FuncDef):
        return render_funcdef(node, indent, markers)
    if isinstance(node, Assign):
        return indent + render_assign(node)
    if isinstance(node, Give):
        return indent + f"give {render_expr(node.expr)}"
    if isinstance(node, Show):
        return indent + f"show {render_expr(node.expr)}"
    if isinstance(node, Why):
        return indent + f"why {render_expr(node.expr)}"
    if isinstance(node, WriteTo):
        return indent + render_writeto_inline(node)
    if isinstance(node, OrFail):
        return indent + render_orfail(node)
    if isinstance(node, If):
        return render_if(node, indent, markers)
    if isinstance(node, ForEach):
        return render_foreach_stmt(node, indent, markers)
    # A bare expression statement (parse_statement's fallback).
    return indent + render_expr(node)


# ================================================================ the generated marker

def _line_span(node, seen=None):
    """Every source line this node's subtree touches — the AST-native
    replacement for scanning text, since the renderer works from parsed
    nodes, not from the original source."""
    seen = seen if seen is not None else set()
    if not hasattr(node, "__dataclass_fields__") or id(node) in seen:
        return set()
    seen.add(id(node))
    lines = set()
    ln = getattr(node, "line", None)
    if ln:
        lines.add(ln)
    for f in node.__dataclass_fields__:
        v = getattr(node, f)
        if hasattr(v, "__dataclass_fields__"):
            lines |= _line_span(v, seen)
        elif isinstance(v, (list, tuple)):
            for x in v:
                if hasattr(x, "__dataclass_fields__"):
                    lines |= _line_span(x, seen)
    return lines


def compute_markers(rules, surface, declaring_file=None):
    """source line -> [rule names] for every site an active rule reaches.

    Both violations and cleared matches count (unbound v2.0 §31): a permit
    clearing a forbid still means the forbid rule reached that site, and
    the marker's job is to say a rule reaches here, not to say whether it
    is happy about it. Vacuous entries have no effect and so no site to
    mark.
    """
    if not rules:
        return {}
    if surface is None:
        raise ValueError(
            "render(): rules given without surface -- markers need a "
            "computed effect surface\n"
            "  try: render(prog, rules=found, surface=analyse(src))")
    results = check(rules, surface, declaring_file=declaring_file)
    markers = {}
    for v in results:
        if v.effect is None:      # vacuous: no site to mark
            continue
        markers.setdefault(v.effect.site, []).append(v.rule.name)
    return markers


def _marker_lines(stmt, indent, markers):
    if not markers:
        return []
    hit = _line_span(stmt) & set(markers)
    names, seen = [], set()
    for ln in sorted(hit):
        for name in markers[ln]:
            if name not in seen:
                seen.add(name)
                names.append(name)
    return [indent + f"~ [{name}] applies here" for name in names]


def render_block(stmts, indent, markers):
    out = []
    for s in stmts:
        out.extend(_marker_lines(s, indent, markers))
        out.append(render_stmt(s, indent, markers))
    return "\n".join(out)


# ================================================================ entry points

def render(prog, rules=None, surface=None):
    """Canonical source text for a program.

    When `rules` and `surface` are supplied, governed instruction sites
    carry a generated marker (unbound v2.0 §31) — computed here, every
    time, from `rules.check()`. The marker is output only: nothing in this
    module or the parser reads a `~` line back in, so it cannot go stale
    the way a hand-written comment can — the next render recomputes it
    against whatever the rule set says now.
    """
    markers = compute_markers(rules, surface)
    body = render_block(prog, "", markers)
    return body + "\n" if body else ""


def strip_annotations(prog):
    """A copy of this program with every annotation removed: `Note`
    statements dropped, `Because` fields cleared, at any nesting depth.

    The mechanism the inertness test (Phase 2) runs against — proving the
    annotation plane erasable, rather than assuming it, is the whole point
    of unbound v1.0 §4 item 3.
    """
    def strip_stmts(stmts):
        return [strip_one(s) for s in stmts if not isinstance(s, Note)]

    def strip_one(s):
        if isinstance(s, Assign) and s.annotation is not None:
            return dataclasses.replace(s, annotation=None)
        if isinstance(s, Rule) and s.annotation is not None:
            return dataclasses.replace(s, annotation=None)
        if isinstance(s, If):
            return dataclasses.replace(
                s, then=strip_stmts(s.then), els=strip_stmts(s.els))
        if isinstance(s, ForEach):
            return dataclasses.replace(s, body=strip_stmts(s.body))
        if isinstance(s, FuncDef):
            return dataclasses.replace(s, body=strip_stmts(s.body))
        return s

    return strip_stmts(prog)


def ast_equal(a, b):
    """Structural equality that ignores `line`.

    `line` is source position, not program meaning, and the canonical
    renderer does not (and must not) preserve the original text's exact
    layout — see the module docstring. Comparing `render(parse(src))`'s
    reparse against the original AST with plain `==` would fail on line
    numbers alone even when every other field matches, which is not the
    guarantee round-trip is supposed to check.
    """
    if type(a) is not type(b):
        return False
    if hasattr(a, "__dataclass_fields__"):
        for f in a.__dataclass_fields__:
            if f == "line":
                continue
            if not ast_equal(getattr(a, f), getattr(b, f)):
                return False
        return True
    if isinstance(a, (list, tuple)):
        if isinstance(a, tuple) != isinstance(b, tuple):
            return False
        if len(a) != len(b):
            return False
        return all(ast_equal(x, y) for x, y in zip(a, b))
    return a == b
