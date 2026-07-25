"""Agreement test: parser.py vs. grammar/parser.planes (Route B stage two).

grammar/parser.planes is a parser for Planes, written in Planes, checked
by agreement with parser.py's own parse() -- parser.py's output is the
specification, exactly as grammar/lexer.planes was checked against
lexer.py's tokenize() (test_lexer_in_planes.py).

parser.py produces Python dataclass AST objects; grammar/parser.planes
produces Planes records. They cannot be compared directly, so both sides
instead emit a canonical AST *text* form -- one node per line, indentation
for depth, node type then its fields in a fixed order, leaf values quoted
and escaped via planes_text.escape_string_literal so quotes and newlines
survive -- and the test compares the two strings. A canonical text form
distinguishes structures that would render identically as source, and it
fails informatively: a diff points at the exact node that disagrees.
Rendering both sides to source instead would need a renderer written in
Planes, which is a different build.

REPORT_PARSER_IN_PLANES.md carries the ladder rung reached and the full
per-file corpus agreement table this harness produces.
"""
import sys

from interp import Deriv, Interpreter, Traced
from lexer import (
    Assign,
    BinOp,
    Bool,
    Builtin,
    Call,
    Field,
    FuncDef,
    Give,
    If,
    IsNothing,
    ListLit,
    ListPlus,
    Not,
    Nothing,
    Num,
    Round,
    Show,
    Str,
    Var,
)
from planes_text import escape_string_literal

# ================================================================ the canonical form (Python side)

# Every AST node class this harness knows how to render, in the order
# fields print (dataclasses.fields() preserves declaration order, so this
# set exists only to recognize a node -- field order comes from lexer.py
# itself, not duplicated here).
AST_NODE_TYPES = (
    Num, Str, Bool, Nothing, Var, ListLit, ListPlus, BinOp, Not, IsNothing,
    Field, Assign, FuncDef, Call, Give, Show, If, Round, Builtin,
)


def _is_node(v):
    return isinstance(v, AST_NODE_TYPES)


def _render_scalar(v):
    if v is None:
        return "nothing"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return f'"{escape_string_literal(v)}"'
    return str(v)


def _render_value(name, v, indent, out):
    if v is None or isinstance(v, (bool, str)) or (
            not isinstance(v, list) and not _is_node(v)
            and not isinstance(v, tuple)):
        out.append(f"{indent}{name}: {_render_scalar(v)}")
        return
    if _is_node(v):
        out.append(f"{indent}{name}:")
        _render_node(v, indent + "  ", out)
        return
    if isinstance(v, list):
        out.append(f"{indent}{name}: [{len(v)}]")
        for item in v:
            _render_list_item(item, indent + "  ", out)
        return
    if isinstance(v, tuple):
        # A (name, expr) pair -- RecordLit/RecordUpdate field, or a plain
        # (str, str) parameter-like pair. Node-valued second element
        # recurses; everything else renders as a scalar.
        key, val = v
        if _is_node(val):
            out.append(f"{indent}{name}: \"{escape_string_literal(str(key))}\"")
            _render_node(val, indent + "  ", out)
        else:
            out.append(f"{indent}{name}: (\"{escape_string_literal(str(key))}\", "
                       f"{_render_scalar(val)})")
        return
    out.append(f"{indent}{name}: {_render_scalar(v)}")


def _render_list_item(item, indent, out):
    if _is_node(item):
        out.append(f"{indent}-")
        _render_node(item, indent + "  ", out)
    elif isinstance(item, tuple) and len(item) == 2 and _is_node(item[1]):
        key, val = item
        out.append(f"{indent}- \"{escape_string_literal(str(key))}\":")
        _render_node(val, indent + "  ", out)
    else:
        out.append(f"{indent}- {_render_scalar(item)}")


def _render_node(node, indent, out):
    out.append(f"{indent}{type(node).__name__}")
    for f in node.__dataclass_fields__:
        _render_value(f, getattr(node, f), indent + "  ", out)


def canonical(node):
    """The canonical text form of one parser.py AST node."""
    out = []
    _render_node(node, "", out)
    return "\n".join(out)


# ================================================================ the canonical form (Planes side)

_interp = None


def _get_interp():
    global _interp
    if _interp is None:
        _interp = Interpreter()
        _interp.run_file("grammar/parser.planes")
    return _interp


def _traced(v):
    return Traced(v, Deriv("literal", repr(v), v, []))


def planes_canonical_node(record_src):
    """Canonical form of a hand-built Planes AST record (a `{ kind: ...
    }` literal, not parsed from program source) -- used by Phase 1's
    fixture proof, before any parsing exists at all."""
    i = _get_interp()
    i.run(f"fixture = {record_src}\n")
    fixture = i.env.get("fixture")
    return i.call("canonical-of-node", [fixture, _traced("")], i.env).value


# ================================================================ Phase 1: the fixture proof
#
# A hand-built three-node AST (BinOp("+", Num(1), Num(2))), fed through
# both canonical-form emitters independently -- no parser involved on
# either side yet. This is the harness's own self-test: if the two
# emitters agree here, string comparison is a valid oracle for every
# later phase; if they disagree, nothing downstream can be trusted.

def test_fixture_binop_plus_two_nums_matches_by_hand():
    node = BinOp("+", Num(1), Num(2))
    expected = ('BinOp\n'
                '  op: "+"\n'
                '  left:\n'
                '    Num\n'
                '      value: 1\n'
                '  right:\n'
                '    Num\n'
                '      value: 2')
    assert canonical(node) == expected, canonical(node)


def test_fixture_both_emitters_agree():
    node = BinOp("+", Num(1), Num(2))
    py_form = canonical(node)
    planes_record = ('{ kind: "BinOp", op: "+", left: { kind: "Num", value: 1 }, '
                     'right: { kind: "Num", value: 2 } }')
    planes_form = planes_canonical_node(planes_record)
    assert planes_form == py_form, f"planes:\n{planes_form!r}\npython:\n{py_form!r}"


if __name__ == "__main__":
    fails = []
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            fails.append(name)
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
