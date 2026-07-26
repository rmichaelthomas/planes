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
    Fail,
    Field,
    ForEach,
    Foreign,
    FuncDef,
    Give,
    If,
    IsNothing,
    ListLit,
    ListPlus,
    Not,
    Note,
    Nothing,
    Num,
    OrFail,
    RecordLit,
    RecordUpdate,
    Round,
    Rule,
    Show,
    Str,
    Use,
    Var,
    When,
    Why,
    WriteTo,
)
from planes_num import Number
from planes_text import escape_string_literal
from rules import check

INDENT = "  "

# Sub-expressions that need parens wherever they are read at less than full
# precedence -- i.e. anywhere but as the outermost expression of a statement.
# BinOp/Not/IsNothing were the original set; S6's composition generator showed
# it was incomplete -- ListPlus (`x plus y`), OrFail (`x or fail as t`),
# RecordUpdate (`b with ...`), and ForEach (`for each ...: body`) are all
# low-precedence and are otherwise split, or swallow a following token, when
# embedded. (`first` and `round` render as primaries and need no grouping.)
_COMPOUND = (BinOp, Not, IsNothing, ListPlus, OrFail, RecordUpdate, ForEach)

# Expression node kinds that may stand alone as a statement (parse_statement's
# final `return self.parse_expr()`). Listed explicitly so render_stmt raises
# on a node that is neither a known statement nor a renderable expression,
# rather than routing an unknown node blindly through render_expr (A.5: no
# safe fallback -- every dispatch is a real case).
_EXPR_STMT = (Num, Str, Bool, Nothing, Var, ListLit, RecordLit, RecordUpdate,
              ListPlus, BinOp, Not, IsNothing, Field, Call, Round, ForEach,
              OrFail)


# ================================================================ comma-list elements
#
# The composition defect (S6): an expression whose rendering ends in a GREEDY
# comma-extensible list is misparsed when it appears as an element of an
# enclosing comma-separated list -- the element's own commas are read as the
# enclosing list's separators. Two renderings have such a tail:
#
#   * a call, `name of (a), (b)` -- the `of` argument list extends on a
#     following primary (even `name of (a), k2` swallows `k2` as a second arg);
#   * a record update, `base with a: 1, b: 2` -- the `with` field list extends
#     on a following `name: expr`.
#
# The parser is correct; the renderer is emitting text whose meaning differs
# from the AST it was given. The fix is parenthesisation, applied identically in
# render.py and render.mjs: wrap such an element in parens, which stops the
# greedy list at the paren boundary and reparses to the same AST (parens are
# transparent). Applied uniformly, matching this module's existing "always
# group, never rank precedence" philosophy -- an unnecessary wrap on a
# last/only element is still correct, and both implementations wrap the same way.


def _greedy_tail(node):
    """The greedy comma-extensible list, if any, that terminates
    render_expr(node) at top level:

      "of"   -- a call's argument list (extends on a following primary);
      "with" -- a record update's field list (extends on a following
                `name: expr`);
      None   -- render(node) ends in a self-delimiting token (bracket,
                keyword, or atom).

    Recursive through the renderings that end in a sub-expression: a `for each`
    expression ends in its body; a BinOp / `not` / `plus` ends in its trailing
    operand -- unless render_operand parenthesises that operand (a _COMPOUND
    operand is wrapped and so ends in ')'). Everything else ends self-delimited.
    """
    if isinstance(node, Call):
        return "of" if node.args else None
    if isinstance(node, RecordUpdate):
        return "with"
    if isinstance(node, ForEach):
        return _greedy_tail(node.body[0])
    if isinstance(node, BinOp):
        return None if isinstance(node.right, _COMPOUND) else _greedy_tail(node.right)
    if isinstance(node, Not):
        return None if isinstance(node.expr, _COMPOUND) else _greedy_tail(node.expr)
    if isinstance(node, ListPlus):
        return None if isinstance(node.item, _COMPOUND) else _greedy_tail(node.item)
    return None


def _comma_element(node, sep):
    """Render `node` as an element of a comma-separated list, parenthesising it
    when its greedy tail would be swallowed by the list's own separator.

    `sep` is "record" -- the following separator is `, name: expr` (between
    record-literal or record-update fields) -- or "list" -- the following
    separator is `, expr` (between list items). A call's `of` list swallows
    either kind of sibling; a record update's `with` list swallows only a
    `name: expr`, so it is dangerous only between record fields.
    """
    text = render_expr(node)
    tail = _greedy_tail(node)
    dangerous = tail == "of" or (tail == "with" and sep == "record")
    return f"({text})" if dangerous else text


def _field_base(node):
    """The base of a `X.name` field access. Like render_operand -- parenthesise
    a _COMPOUND base -- but ALSO parenthesise a base with a greedy tail (S6):
    `(f of a, b).kind` rendered bare as `f of (a), (b).kind` binds `.kind` to
    the argument `(b)`, not the call, and `(p with a: 1).b` bare binds `.b` to
    the field value. The following `.` is the enclosing separator here.
    """
    if isinstance(node, _COMPOUND) or _greedy_tail(node) is not None:
        return f"({render_expr(node)})"
    return render_expr(node)


# Expressions whose own trailing structure swallows a following keyword or `:`
# delimiter: an or-fail's `as tag[:...]`, a record update's `with` fields, a
# for-each's `: body`. Distinct from _COMPOUND -- a BinOp before `:` (`if x > 0:`)
# does NOT collide, so these positions must NOT wrap it, or every comparison
# condition would gain needless parens.
_OPEN_TRAILING = (OrFail, RecordUpdate, ForEach)


def _delimited(node):
    """An expression read up to a trailing keyword or `:` delimiter -- a for-each
    source or `where`, an `if`/`when` subject, a `write` value or destination, a
    `fail` message, an or-fail inner (S6). Parenthesise the kinds whose trailing
    structure would otherwise swallow that delimiter."""
    if isinstance(node, _OPEN_TRAILING):
        return f"({render_expr(node)})"
    return render_expr(node)


# ================================================================ expressions

def render_operand(node):
    """An expression in a position where the grammar reads at less than
    full precedence (a BinOp side, a Field base, a Round argument): safe
    regardless of what `node` is, because a compound node is wrapped."""
    text = render_expr(node)
    return f"({text})" if isinstance(node, _COMPOUND) else text


def _is_zero_literal(node):
    """A `Num` node holding zero, whichever way the zero got there.

    `parse_primary` builds a source `0` as `Num(Number.parse("0"))`;
    `parse_unary` builds the zero it SYNTHESISES for a unary minus as
    `Num(0)`, a raw Python int. Both mean the same literal, so both answer
    yes here -- and `ast_equal` below compares numeric leaves by value for
    the same reason.
    """
    return isinstance(node, Num) and _num_eq(node.value, 0)


def _num_eq(a, b):
    """Numeric leaf equality across the raw-int / Number split."""
    if not (_is_num(a) and _is_num(b)):
        return False
    return Number.of(a) == Number.of(b)


def _is_num(v):
    return isinstance(v, (Number, int)) and not isinstance(v, bool)


def _is_negation(node):
    """A `BinOp` the parser SYNTHESISED for a unary minus, `-X`.

    `parse_unary` desugars `-X` to `BinOp("-", Num(0), X)` -- a node no source
    text writes directly, and so a node the grammar-derived composition matrix
    could not reach. Rendering it as `0 - X` was arithmetically right and
    canonically wrong twice over: it lost the source form, and it did not
    round-trip, because the synthesised zero is a raw int where a parsed `0` is
    a `Number` and `ast_equal` compared their Python types.

    A subtraction from a literal zero renders as the unary form whether the
    zero was synthesised or written, because the renderer cannot tell them
    apart in the JavaScript implementation (whose parser builds a real
    `PlanesNumber` zero) and the two implementations must render identically.
    `0 - X` and `-X` are the same program; the canonical form picks the
    shorter, source-idiomatic one.
    """
    return node.op == "-" and _is_zero_literal(node.left)


def render_expr(node):
    if isinstance(node, Num):
        return node.value.text() if hasattr(node.value, "text") else str(node.value)
    if isinstance(node, Str):
        return f'"{escape_string_literal(node.value)}"'
    if isinstance(node, Bool):
        return "true" if node.value else "false"
    if isinstance(node, Nothing):
        return "nothing"
    if isinstance(node, Var):
        return node.name
    if isinstance(node, ListLit):
        return "[" + ", ".join(_comma_element(i, "list") for i in node.items) + "]"
    if isinstance(node, ListPlus):
        return f"{render_operand(node.base)} plus {render_operand(node.item)}"
    if isinstance(node, RecordLit):
        fields = ", ".join(f"{k}: {_comma_element(v, 'record')}"
                           for k, v in node.fields)
        return "{ " + fields + " }" if fields else "{}"
    if isinstance(node, RecordUpdate):
        # `base with name: expr, ...` (v5.0 §72). The base is an operand
        # (parenthesised if compound); each field value re-renders as a full
        # expression, parenthesised when its greedy tail would collide with the
        # `with` list's own commas (S6). Chains render left to right, since a
        # RecordUpdate base is itself rendered here -- `p with a: 1 with b: 2`
        # round-trips.
        fields = ", ".join(f"{k}: {_comma_element(v, 'record')}"
                           for k, v in node.fields)
        return f"{render_operand(node.base)} with {fields}"
    if isinstance(node, BinOp):
        if node.op == "first":
            # `first N of L` (S6). Both operands are parse_unary(), and each is
            # parenthesised so it reads as a single closed primary: a bare Var
            # count (`first k of parts`) is otherwise swallowed as the call
            # `k of parts`, and a sub-unary list (`first k of a plus b`) is
            # otherwise split by precedence. render_operand alone does not cover
            # either -- it wraps only _COMPOUND -- so wrap both, matching this
            # module's always-group philosophy.
            return f"first ({render_expr(node.left)}) of ({render_expr(node.right)})"
        if _is_negation(node):
            # The parser's synthesised unary minus, rendered back as itself.
            return f"-{render_operand(node.right)}"
        return f"{render_operand(node.left)} {node.op} {render_operand(node.right)}"
    if isinstance(node, Not):
        return f"not {render_operand(node.expr)}"
    if isinstance(node, IsNothing):
        return f"{render_operand(node.expr)} is nothing"
    if isinstance(node, Field):
        # `X.name` (S6). render_operand wraps a _COMPOUND base, but a base with
        # a greedy tail also needs wrapping: `(call).kind` rendered bare as
        # `call.kind` binds `.kind` to the call's last argument, not the call.
        return f"{_field_base(node.obj)}.{node.name}"
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
    where = f" where {_delimited(node.where)}" if node.where is not None else ""
    body = render_expr(node.body[0])
    return f"for each {node.var} in {_delimited(node.source)}{where}: {body}"


def render_writeto_inline(node):
    return f"write {_delimited(node.value)} to {_delimited(node.dest)}"


def render_orfail(node):
    inner = (render_writeto_inline(node.expr) if isinstance(node.expr, WriteTo)
             else _delimited(node.expr))
    return f"{inner} or fail as {node.tag}"


# ================================================================ statements

def render_because_suffix(node):
    if node.annotation is None:
        return ""
    return f' because "{escape_string_literal(node.annotation.text)}"'


def render_assign(node):
    prefix = "let " if node.is_let else ""
    return f"{prefix}{node.name} = {render_expr(node.expr)}{render_because_suffix(node)}"


def render_rule(node):
    verb = "may not" if node.assertion == "forbid" else "may"
    text = f"rule [{node.name}] {node.subject} {verb} {node.kind}"
    if node.target is not None:
        text += f' to "{escape_string_literal(node.target)}"'
    if node.supersedes is not None:
        text += f" supersedes [{node.supersedes}]"
        if node.supersedes_fingerprint is not None:
            text += f" @{node.supersedes_fingerprint}"
    return text + render_because_suffix(node)


def render_note(node, indent):
    lines = [indent + "note:"]
    for kind, value in node.entries:
        if kind == "from":
            lines.append(indent + INDENT + f'from "{escape_string_literal(value)}"')
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
    text += f' from "{escape_string_literal(node.target)}"'
    if node.declared:
        if not node.effects:
            text += " doing nothing"
        else:
            claims = []
            for kind, where in node.effects:
                if where is None:
                    claims.append(kind)
                elif where[0] == "literal":
                    claims.append(f'{kind} "{escape_string_literal(where[1])}"')
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
    lines = [indent + f"if {_delimited(node.cond)}:"]
    lines.append(render_block(node.then, indent + INDENT, markers))
    if node.els:
        lines.append(indent + "else:")
        lines.append(render_block(node.els, indent + INDENT, markers))
    return "\n".join(lines)


def render_foreach_stmt(node, indent, markers):
    where = f" where {_delimited(node.where)}" if node.where is not None else ""
    header = indent + f"for each {node.var} in {_delimited(node.source)}{where}:"
    body = render_block(node.body, indent + INDENT, markers)
    return header + "\n" + body


def render_when(node, indent, markers):
    # `when SUBJECT is { field: expr, bindname, ... }:` — a match entry
    # renders as `field: expr`, a binding entry as the bare field name. A match
    # value is a record-field position (comma-separated `name: expr`), so it
    # parenthesises a greedy tail the same way a record literal's does (S6). The
    # else block, when present, is an ordinary block (a nested when there is how
    # an if-elif ladder is written). Mirrors render_if.
    entries = []
    for fname, (kind, arg) in node.pattern:
        entries.append(f"{fname}: {_comma_element(arg, 'record')}"
                       if kind == "match" else fname)
    header = indent + f"when {_delimited(node.subject)} is {{ {', '.join(entries)} }}:"
    lines = [header, render_block(node.body, indent + INDENT, markers)]
    if node.els:
        lines.append(indent + "else:")
        lines.append(render_block(node.els, indent + INDENT, markers))
    return "\n".join(lines)


def _statement_orfail(node):
    """The or-fail-with-handler at this statement's top, or None. A handler is a
    statement-level continuation (`... or fail as tag:` then a block), so it can
    appear as a bare OrFail statement or wrapped inside the Assign/Give whose
    value it is (the corpus shapes; parse_or_fail attaches it there)."""
    if isinstance(node, OrFail) and node.handler is not None:
        return node
    if isinstance(node, (Assign, Give)) and isinstance(node.expr, OrFail) \
            and node.expr.handler is not None:
        return node.expr
    return None


def _without_handler(node):
    """A copy of `node` with its or-fail handler cleared, so the existing
    single-line render paths produce the head line."""
    if isinstance(node, OrFail):
        return dataclasses.replace(node, handler=None)
    return dataclasses.replace(
        node, expr=dataclasses.replace(node.expr, handler=None))


def render_stmt(node, indent, markers):
    # An or-fail HANDLER block turns an otherwise single-line statement into a
    # block (S6): `x = EXPR or fail as tag:` then the indented handler. Render
    # the head line without the handler through the ordinary path, then the
    # block. render_orfail is single-line and (correctly) renders no handler;
    # this is where the handler is put back.
    orfail = _statement_orfail(node)
    if orfail is not None:
        head = render_stmt(_without_handler(node), indent, markers)
        block = render_block(orfail.handler, indent + INDENT, markers)
        return head + ":\n" + block

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
    if isinstance(node, When):
        return render_when(node, indent, markers)
    if isinstance(node, WriteTo):
        return indent + render_writeto_inline(node)
    if isinstance(node, OrFail):
        return indent + render_orfail(node)
    if isinstance(node, Fail):
        return indent + f"fail {_delimited(node.message)} as {node.tag}"
    if isinstance(node, If):
        return render_if(node, indent, markers)
    if isinstance(node, ForEach):
        return render_foreach_stmt(node, indent, markers)
    # A bare expression statement (parse_statement's fallthrough to
    # parse_expr). Every expression node kind is dispatched explicitly by
    # render_expr; a node that is neither a statement above nor a renderable
    # expression raises here, naming the kind, rather than being rendered by
    # a happens-to-be-safe fallback (A.5).
    if isinstance(node, _EXPR_STMT):
        return indent + render_expr(node)
    raise ValueError(f"render_stmt: unhandled node type {type(node).__name__}")


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

    A numeric leaf is compared by VALUE, not by Python type, and so is tested
    before the type test below. `Num(0)` — the zero `parse_unary` synthesises
    for a negation — and `Num(Number.parse("0"))` — a zero the source wrote —
    are the same literal; calling them different is a false negative about the
    program, and it is the reason a negative literal did not round-trip
    (S7, fixed here). The JavaScript `astEqual` has always compared
    PlanesNumber leaves this way; this brings the two level.
    """
    if _is_num(a) or _is_num(b):
        return _num_eq(a, b)
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
