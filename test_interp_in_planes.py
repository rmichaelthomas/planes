"""Agreement test: interp.py vs. grammar/interp.planes (Route B stage three).

grammar/interp.planes is an expression evaluator for Planes, written in
Planes, checked by agreement with interp.py's own eval() -- interp.py's
output is the specification, exactly as grammar/lexer.planes was checked
against lexer.py (test_lexer_in_planes.py) and grammar/parser.planes against
parser.py (test_parser_in_planes.py).

interp.py produces raw Python values (Number, str, bool, None, list, dict);
grammar/interp.planes produces tagged Planes value records. They cannot be
compared directly, so both sides render an evaluated value to a canonical
value *text* form and the test compares the two strings (A.5). The canonical
form:

  * numbers render through Number.text() -- an exact rational, never a
    float: 2 / 3 is "~0.666666666666", 0.1 + 0.2 is "0.3";
  * strings render escaped and quoted (the same four escapes on both sides),
    so a quote or newline survives the comparison;
  * records render their fields in interp.py's stored (insertion) order;
  * `1`, `"1"`, and `true` render distinctly, so the form names the type.

Build 1 is the expression evaluator only: literals, variables, operators,
records, lists, field access, and calls to pure functions. Statements,
control flow, and effects are builds 2 and 3 -- an effect-bearing node
(`ask`, `read`) reaches a case that fails with a tag naming build 3 (A.6).
"""
import sys

from interp import Deriv, Interpreter, PlanesError, Traced, is_num
from parser import parse
from planes_num import Number
from planes_text import escape_string_literal

# ============================================== the canonical value form (Python side)


def canonical(v):
    """The canonical text form of one interp.py value. The oracle the
    Planes side is checked against."""
    if v is None:
        return "nothing"
    if isinstance(v, bool):
        return "true" if v else "false"
    if is_num(v):
        return Number.of(v).text()
    if isinstance(v, str):
        return '"' + escape_string_literal(v) + '"'
    if isinstance(v, list):
        return "[" + ", ".join(canonical(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {canonical(val)}" for k, val in v.items()) + "}"
    raise AssertionError(f"canonical: cannot render {v!r} ({type(v).__name__})")


# ============================================== building a Planes value-record literal
#
# A test helper that emits the grammar/interp.planes value-record literal for
# a raw value -- the input the Planes renderer consumes, mirroring what the
# Planes `eval` will later produce. Phase 1 uses it to prove the two
# canonical emitters agree on hand-built values, before any evaluator exists.


def _num_lit(v):
    n = Number.of(v)
    if n.is_whole():
        return str(n.as_int())
    q = n.q
    return f"{q.numerator} / {q.denominator}"


def planes_lit(v):
    """A grammar/interp.planes value-record literal (Planes source) for a raw
    value -- exactly the tagged record the Planes evaluator represents this
    value as."""
    if v is None:
        return '{ kind: "nothing", value: nothing, deriv: nothing }'
    if isinstance(v, bool):
        return '{ kind: "boolean", value: %s, deriv: nothing }' % (
            "true" if v else "false")
    if is_num(v):
        return '{ kind: "number", value: %s, deriv: nothing }' % _num_lit(v)
    if isinstance(v, str):
        return '{ kind: "text", value: "%s", deriv: nothing }' % escape_string_literal(v)
    if isinstance(v, list):
        return '{ kind: "list", items: [%s], deriv: nothing }' % ", ".join(
            planes_lit(x) for x in v)
    if isinstance(v, dict):
        fields = ", ".join(
            '{ key: "%s", value: %s }' % (k, planes_lit(val)) for k, val in v.items())
        return '{ kind: "record", fields: [%s], deriv: nothing }' % fields
    raise AssertionError(f"planes_lit: cannot build {v!r}")


# ================================================================ the Planes side, loaded once

_interp = None


def _get_interp():
    global _interp
    if _interp is None:
        _interp = Interpreter()
        _interp.run_file("grammar/interp.planes")
    return _interp


def _traced(v):
    return Traced(v, Deriv("literal", repr(v), v, []))


def planes_canonical_value(record_src):
    """Canonical text of a hand-built Planes value record (a `{ kind: ... }`
    literal), rendered by grammar/interp.planes's canonical-of-value."""
    i = _get_interp()
    i.run(f"fixture = {record_src}\n")
    fixture = i.env.get("fixture")
    return i.call("canonical-of-value", [fixture], i.env).value


# ============================================== evaluating an expression, both sides


def _env_literal(bindings):
    """A grammar/interp.planes environment literal (a flat list of
    { name, value } bindings) for a {name: raw-value} mapping."""
    parts = ['{ name: "%s", value: %s }' % (k, planes_lit(v))
             for k, v in bindings.items()]
    return "[%s]" % ", ".join(parts)


def planes_eval(src, bindings=None):
    """Evaluate one expression source through grammar/interp.planes against
    an environment, returning the canonical text of the resulting value."""
    i = _get_interp()
    i.run(f"__env = {_env_literal(bindings or {})}\n")
    env = i.env.get("__env")
    node = i.call("node-of-source", [_traced(src)], i.env)
    val = i.call("eval", [node, env], i.env)
    return i.call("canonical-of-value", [val], i.env).value


def interp_eval(src, bindings=None):
    """The oracle: evaluate one expression source through interp.py's own
    eval() against the same bindings, returning the raw value."""
    itp = Interpreter()
    env = itp.env
    for k, v in (bindings or {}).items():
        env.bind_local(k, Traced(v, Deriv("name", k, v, [])))
    node = parse(src + "\n")[0]
    return itp.eval(node, env).value


def assert_eval_agrees(src, bindings=None):
    """The Planes evaluation of an expression equals interp.py's, compared
    through the canonical value form."""
    py_form = canonical(interp_eval(src, bindings))
    planes_form = planes_eval(src, bindings)
    assert planes_form == py_form, (
        f"\nsrc: {src!r}  bindings: {bindings!r}"
        f"\n--- planes ---\n{planes_form!r}\n--- python ---\n{py_form!r}")


def assert_eval_fails(src, tag, bindings=None):
    """Both implementations refuse the expression with the same error tag."""
    try:
        interp_eval(src, bindings)
        raise AssertionError(f"interp.py did not fail on {src!r}")
    except PlanesError as e:
        assert e.tag == tag, f"interp.py tag {e.tag!r} != {tag!r} for {src!r}"
    try:
        planes_eval(src, bindings)
        raise AssertionError(f"grammar/interp.planes did not fail on {src!r}")
    except PlanesError as e:
        assert e.tag == tag, f"planes tag {e.tag!r} != {tag!r} for {src!r}"


# ================================================================ Phase 1: the canonical-form proof
#
# Hand-built value records, fed through both canonical emitters
# independently -- no evaluator involved on either side yet. This is the
# harness's own self-test: if the two emitters agree here, string comparison
# is a valid oracle for every later phase; if they disagree, nothing
# downstream can be trusted. The same ordering that carried both prior stages.


def assert_value_agrees(v):
    """The Python value's canonical form equals the Planes rendering of its
    tagged value-record."""
    py_form = canonical(v)
    planes_form = planes_canonical_value(planes_lit(v))
    assert planes_form == py_form, (
        f"\nvalue: {v!r}\n--- planes ---\n{planes_form!r}\n--- python ---\n{py_form!r}")


def test_canonical_whole_number_by_hand():
    assert canonical(Number.of(5)) == "5"
    assert planes_canonical_value(
        '{ kind: "number", value: 5, deriv: nothing }') == "5"


def test_canonical_exact_rational_two_thirds_by_hand():
    # The load-bearing A.5 case: an exact rational, never a float. A float
    # implementation would print 0.6666666666666666; the exact form truncates
    # at 12 places with a leading `~` so the approximation is visible.
    two_thirds = Number.of(2) / Number.of(3)
    assert canonical(two_thirds) == "~0.666666666666"
    assert planes_canonical_value(
        '{ kind: "number", value: 2 / 3, deriv: nothing }') == "~0.666666666666"


def test_canonical_terminating_decimal_by_hand():
    # 0.1 + 0.2 is exactly 0.3 -- the case where a float visibly diverges.
    assert canonical(Number.parse("0.3")) == "0.3"
    assert planes_canonical_value(
        '{ kind: "number", value: 3 / 10, deriv: nothing }') == "0.3"


def test_canonical_escaped_string_by_hand():
    s = 'he said "hi"\nbye\ttab\\end'
    expected = '"he said \\"hi\\"\\nbye\\ttab\\\\end"'
    assert canonical(s) == expected
    assert planes_canonical_value(planes_lit(s)) == expected


def test_canonical_distinguishes_types_by_hand():
    # 1, "1", and true must render distinctly (A.5 ruling 4).
    assert canonical(Number.of(1)) == "1"
    assert canonical("1") == '"1"'
    assert canonical(True) == "true"
    assert planes_canonical_value(planes_lit(Number.of(1))) == "1"
    assert planes_canonical_value(planes_lit("1")) == '"1"'
    assert planes_canonical_value(planes_lit(True)) == "true"


def test_canonical_nothing_by_hand():
    assert canonical(None) == "nothing"
    assert planes_canonical_value(planes_lit(None)) == "nothing"


def test_canonical_booleans_by_hand():
    assert canonical(False) == "false"
    assert planes_canonical_value(planes_lit(False)) == "false"


def test_canonical_empty_list_and_record_by_hand():
    assert canonical([]) == "[]"
    assert canonical({}) == "{}"
    assert planes_canonical_value('{ kind: "list", items: [], deriv: nothing }') == "[]"
    assert planes_canonical_value('{ kind: "record", fields: [], deriv: nothing }') == "{}"


def test_canonical_heterogeneous_list_agrees():
    assert_value_agrees([Number.of(1), "two", True, None])


def test_canonical_nested_record_agrees():
    v = {"name": "x", "inner": {"age": Number.of(3), "tags": ["a", "b"]}}
    assert canonical(v) == '{name: "x", inner: {age: 3, tags: ["a", "b"]}}'
    assert_value_agrees(v)


def test_canonical_list_of_records_agrees():
    v = [{"id": Number.of(1)}, {"id": Number.of(2)}]
    assert_value_agrees(v)


# The battery of scalar fixtures, both sides agreeing.
FIXTURES = [
    Number.of(0), Number.of(42), Number.of(-5),
    Number.of(1) / Number.of(4),       # 0.25, terminating
    Number.of(1) / Number.of(3),       # ~0.333333333333
    Number.parse("3.14"),
    "", "plain", 'with "quotes"', "with\nnewline",
    True, False, None,
    [], [Number.of(1), Number.of(2), Number.of(3)],
    {}, {"a": Number.of(1)},
]


def test_canonical_fixture_battery_agrees():
    for v in FIXTURES:
        assert_value_agrees(v)


# ============================================== Phase 2: literals and variables
#
# The evaluator's first four cases plus variable reference, each parsed by
# grammar/parser.planes and evaluated by grammar/interp.planes, checked
# against interp.py's own eval().


def test_eval_number_literals():
    for src in ["0", "42", "3.14", "0.1"]:
        assert_eval_agrees(src)


def test_eval_string_literals():
    for src in ['"hello"', '""', '"a \\"quoted\\" word"', '"line\\nbreak"']:
        assert_eval_agrees(src)


def test_eval_boolean_and_nothing_literals():
    for src in ["true", "false", "nothing"]:
        assert_eval_agrees(src)


def test_eval_variable_reference():
    assert_eval_agrees("x", {"x": Number.of(5)})
    assert_eval_agrees("greeting", {"greeting": "hi"})
    assert_eval_agrees("flag", {"flag": True})
    assert_eval_agrees("here", {"here": None})


def test_eval_variable_among_several_bindings():
    env = {"a": Number.of(1), "b": "two", "c": [Number.of(3)]}
    assert_eval_agrees("a", env)
    assert_eval_agrees("b", env)
    assert_eval_agrees("c", env)


def test_eval_unknown_name_fails_same_tag():
    assert_eval_fails("missing", "unknown-name")


def test_env_first_match_wins_shadowing():
    # A.2: innermost bindings first, first match wins. interp.py's Env is a
    # dict and cannot hold two bindings for one name, so this is checked
    # Planes-side directly: an env with two `x` bindings resolves to the
    # first, exactly as a function parameter shadows an outer binding.
    i = _get_interp()
    i.run('__shadow = [{ name: "x", value: '
          '{ kind: "number", value: 1, deriv: nothing } }, '
          '{ name: "x", value: '
          '{ kind: "number", value: 2, deriv: nothing } }]\n')
    env = i.env.get("__shadow")
    node = i.call("node-of-source", [_traced("x")], i.env)
    val = i.call("eval", [node, env], i.env)
    assert i.call("canonical-of-value", [val], i.env).value == "1"


if __name__ == "__main__":
    fails = []
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
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
