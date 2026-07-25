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
from parser import parse
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


def canonical_program(stmts):
    """The canonical text form of a whole program: canonical() per
    top-level statement, joined -- matches grammar/parser.planes's own
    canonical-of-program."""
    out = []
    for s in stmts:
        _render_node(s, "", out)
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


def planes_canonical_expr(src):
    """Canonical form of one expression, parsed by grammar/parser.planes."""
    i = _get_interp()
    return i.call("canonical-of-expr-source", [_traced(src)], i.env).value


def planes_canonical_program(src):
    """Canonical form of a whole program, parsed by grammar/parser.planes."""
    i = _get_interp()
    return i.call("canonical-of-program-source", [_traced(src)], i.env).value


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


# ================================================================ Phase 2: expressions
#
# The recursive precedence chain, checked fragment by fragment against
# parser.py's own parse() -- one program per fragment, exactly one
# top-level statement, compared via the same canonical form the fixture
# proved agrees.

def assert_expr_agrees(src):
    prog = parse(src + "\n")
    assert len(prog) == 1, f"expected exactly one statement, got {len(prog)}: {prog}"
    py_form = canonical(prog[0])
    planes_form = planes_canonical_expr(src)
    assert planes_form == py_form, (
        f"\nsrc: {src!r}\n--- planes ---\n{planes_form}\n--- python ---\n{py_form}")


LITERAL_FRAGMENTS = ["1", "42", "0.1", "3.14", '"hello"', '"a \\"quoted\\" word"',
                    "true", "false", "nothing"]
VARIABLE_FRAGMENTS = ["x", "my-var", "state"]
FIELD_ACCESS_FRAGMENTS = ["r.x", "r.x.y", "node.left.right"]
CALL_OF_FRAGMENTS = ["f of x", "f of x, y", "f of x, y, z", "count of xs", "text of n"]
CALL_PAREN_FRAGMENTS = ["f(x)", "f(x, y)", "f()", "f(x, y, z)"]
PAREN_FRAGMENTS = ["(1 + 2)", "(x)", "((1 + 2) * 3)"]
UNARY_FRAGMENTS = ["-x", "-5", "-(1 + 2)"]
MULTIPLICATIVE_FRAGMENTS = ["2 * 3", "10 / 2", "2 * 3 / 4", "a * b * c"]
ADDITIVE_FRAGMENTS = ["1 + 2", "1 - 2", "1 + 2 - 3", "2 + 3 * 4", "(2 + 3) * 4"]
PLUS_FRAGMENTS = ["xs plus 1", "xs plus a + b"]
COMPARISON_FRAGMENTS = ["1 < 2", "1 <= 2", "1 > 2", "1 >= 2", "1 == 2", "1 != 2",
                        "x in xs", "x is nothing", "detail of id + 1"]
NOT_FRAGMENTS = ["not true", "not x == y"]
AND_OR_FRAGMENTS = ["true and false", "true or false", "a and b or c",
                    "is-digit of c or is-lower-hex or is-upper-hex"]
BUILTIN_FORM_FRAGMENTS = ["first 2 of xs", "first (n) of x",
                          "round total to 2 places", "round total to n"]
COMPLEX_FRAGMENTS = ["1 + 2 * 3 == 7 and not false",
                     '"read " + text of size + " bytes"',
                     "is-name-start of c or is-digit of c"]


def test_literals_agree():
    for src in LITERAL_FRAGMENTS:
        assert_expr_agrees(src)


def test_variables_agree():
    for src in VARIABLE_FRAGMENTS:
        assert_expr_agrees(src)


def test_field_access_agrees():
    for src in FIELD_ACCESS_FRAGMENTS:
        assert_expr_agrees(src)


def test_calls_with_of_agree():
    for src in CALL_OF_FRAGMENTS:
        assert_expr_agrees(src)


def test_calls_with_parens_agree():
    for src in CALL_PAREN_FRAGMENTS:
        assert_expr_agrees(src)


def test_parenthesised_expressions_agree():
    for src in PAREN_FRAGMENTS:
        assert_expr_agrees(src)


def test_unary_operators_agree():
    for src in UNARY_FRAGMENTS:
        assert_expr_agrees(src)


def test_multiplicative_agrees():
    for src in MULTIPLICATIVE_FRAGMENTS:
        assert_expr_agrees(src)


def test_additive_agrees():
    for src in ADDITIVE_FRAGMENTS:
        assert_expr_agrees(src)


def test_plus_connective_agrees():
    for src in PLUS_FRAGMENTS:
        assert_expr_agrees(src)


def test_comparison_agrees():
    for src in COMPARISON_FRAGMENTS:
        assert_expr_agrees(src)


def test_not_agrees():
    for src in NOT_FRAGMENTS:
        assert_expr_agrees(src)


def test_and_or_agree():
    for src in AND_OR_FRAGMENTS:
        assert_expr_agrees(src)


def test_first_and_round_builtin_forms_agree():
    for src in BUILTIN_FORM_FRAGMENTS:
        assert_expr_agrees(src)


def test_complex_expressions_agree():
    for src in COMPLEX_FRAGMENTS:
        assert_expr_agrees(src)


# ================================================================ Phase 3: the statement walker
#
# The ladder (section 3): assignment, show, ... -- each rung tested here
# as it lands. A whole small program per fragment, compared via
# canonical_program/canonical-of-program (one canonical form per
# top-level statement, joined) rather than the single-node form Phase 2
# uses.

def assert_program_agrees(src):
    prog = parse(src)
    py_form = canonical_program(prog)
    planes_form = planes_canonical_program(src)
    assert planes_form == py_form, (
        f"\nsrc:\n{src}\n--- planes ---\n{planes_form}\n--- python ---\n{py_form}")


ASSIGNMENT_PROGRAMS = [
    "x = 1\n",
    "x = 1 + 2\n",
    'name = "widget"\n',
    "x = 1\ny = 2\n",
    "x = 1\ny = x + 1\nz = y * 2\n",
]

SHOW_PROGRAMS = [
    'show "hello"\n',
    "show 1 + 2\n",
    "x = 5\nshow x\n",
    'x = 1\nshow "x is"\nshow x\n',
]


def test_assignment_statements_agree():
    for src in ASSIGNMENT_PROGRAMS:
        assert_program_agrees(src)


def test_show_statements_agree():
    for src in SHOW_PROGRAMS:
        assert_program_agrees(src)


IF_PROGRAMS = [
    'if x < 5:\n  show "small"\n',
    'if x < 5:\n  show "small"\nelse:\n  show "big"\n',
    "if x < 5: show x\n",
    "if x < 5: show x\nelse: show 0\n",
    'if x < 5:\n  y = 1\n  show y\nelse:\n  y = 2\n  show y\n',
    ('if x < 5:\n  if y < 5:\n    show "both small"\n  else:\n    show "x small only"\n'
     'else:\n  show "x big"\n'),
    'x = 1\nif x == 1:\n  show "one"\nshow "done"\n',
]


def test_if_else_statements_agree():
    for src in IF_PROGRAMS:
        assert_program_agrees(src)


FUNCDEF_PROGRAMS = [
    "to main:\n  give 1\n",
    "to square of n:\n  give n * n\n",
    "to add of a, b:\n  give a + b\n",
    "to fetch stories:\n  give 1\n",
    'to classify of n:\n  if n < 0:\n    give "negative"\n  else:\n    give "non-negative"\n',
    "to square of n: give n * n\n",
    "to outer of x:\n  y = x + 1\n  give y\n\nto main:\n  show outer of 5\n",
]


def test_funcdef_statements_agree():
    for src in FUNCDEF_PROGRAMS:
        assert_program_agrees(src)


GIVE_PROGRAMS = [
    "to f:\n  give 5\n",
    "to f of x:\n  give x + 1\n",
]


def test_give_statements_agree():
    for src in GIVE_PROGRAMS:
        assert_program_agrees(src)


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
