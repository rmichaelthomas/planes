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


def planes_eval_program(defs_src, expr_src, bindings=None):
    """Evaluate an expression through grammar/interp.planes against an
    environment carrying the program's function values plus bindings."""
    i = _get_interp()
    fenv = i.call("functions-env-of", [_traced(defs_src)], i.env)
    i.run(f"__vars = {_env_literal(bindings or {})}\n")
    vars_t = i.env.get("__vars")
    full = i.call("append-all", [vars_t, fenv], i.env)
    node = i.call("node-of-source", [_traced(expr_src)], i.env)
    val = i.call("eval", [node, full], i.env)
    return i.call("canonical-of-value", [val], i.env).value


def interp_eval_program(defs_src, expr_src, bindings=None):
    """The oracle: hoist the program's function definitions into interp.py,
    then evaluate the expression against the same bindings."""
    itp = Interpreter()
    itp.hoist(parse(defs_src), itp.env)
    env = itp.env
    for k, v in (bindings or {}).items():
        env.bind_local(k, Traced(v, Deriv("name", k, v, [])))
    node = parse(expr_src + "\n")[0]
    return itp.eval(node, env).value


def assert_eval_program_agrees(defs_src, expr_src, bindings=None):
    py_form = canonical(interp_eval_program(defs_src, expr_src, bindings))
    planes_form = planes_eval_program(defs_src, expr_src, bindings)
    assert planes_form == py_form, (
        f"\ndefs:\n{defs_src}\nexpr: {expr_src!r}"
        f"\n--- planes ---\n{planes_form!r}\n--- python ---\n{py_form!r}")


def assert_planes_fails(src, tag, bindings=None):
    """Only grammar/interp.planes refuses the expression with this tag -- used
    where interp.py fully implements the behaviour (effects) so the two tags
    legitimately differ, and A.6 only requires the Planes side to name build 3."""
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


# ============================================== Phase 3: operators
#
# Binary and unary, every precedence level parser.py produces and interp.py
# evaluates, checked against interp.py's own eval() including its coercion
# and type-guard behaviour.


def test_eval_arithmetic():
    for src in ["1 + 2", "10 - 3", "4 * 5", "2 + 3 * 4", "(2 + 3) * 4",
                "100 - 40 - 10", "2 * 3 * 4"]:
        assert_eval_agrees(src)


def test_eval_unary_minus():
    for src in ["-5", "-(1 + 2)", "0 - 7", "-x"]:
        assert_eval_agrees(src, {"x": Number.of(9)})


def test_eval_division_is_exact_rational_not_float():
    # A.5 ruling 1, verified explicitly: division.
    assert_eval_agrees("2 / 3")          # ~0.666666666666, never 0.666...667
    assert_eval_agrees("1 / 3")
    assert_eval_agrees("10 / 4")         # 2.5, terminating
    assert_eval_agrees("22 / 7")
    # The Planes result reads as an exact rational, not a float.
    assert planes_eval("2 / 3") == "~0.666666666666"
    assert planes_eval("10 / 4") == "2.5"


def test_eval_repeated_addition_is_exact():
    # A.5 ruling 1, verified explicitly: repeated addition where a float
    # implementation visibly diverges. 1/3 + 1/3 + 1/3 is exactly 1 (a float
    # gives 0.9999999999999999); 0.1 + 0.2 is exactly 0.3 (a float gives
    # 0.30000000000000004).
    assert_eval_agrees("1 / 3 + 1 / 3 + 1 / 3")
    assert planes_eval("1 / 3 + 1 / 3 + 1 / 3") == "1"
    assert_eval_agrees("0.1 + 0.2")
    assert planes_eval("0.1 + 0.2") == "0.3"


def test_eval_string_concatenation():
    for src in ['"a" + "b"', '"read " + "bytes"', '"" + "x"']:
        assert_eval_agrees(src)


def test_eval_comparisons_numbers():
    for src in ["1 < 2", "2 < 1", "2 <= 2", "3 > 5", "5 >= 5", "5 >= 6",
                "1 == 1", "1 == 2", "1 != 2", "1 != 1"]:
        assert_eval_agrees(src)


def test_eval_comparisons_text():
    for src in ['"a" < "b"', '"b" <= "b"', '"z" > "a"', '"x" == "x"', '"x" != "y"']:
        assert_eval_agrees(src)


def test_eval_boolean_equality():
    for src in ["true == true", "true == false", "true != false", "false != false"]:
        assert_eval_agrees(src)


def test_eval_and_or_short_circuit():
    for src in ["true and true", "true and false", "false and true",
                "true or false", "false or true", "false or false",
                "true and false or true", "1 == 1 and 2 == 2"]:
        assert_eval_agrees(src)


def test_eval_not():
    for src in ["not true", "not false", "not (1 == 2)", "not (1 == 1)"]:
        assert_eval_agrees(src)


def test_eval_is_nothing():
    assert_eval_agrees("nothing is nothing")
    assert_eval_agrees("here is nothing", {"here": None})
    assert_eval_agrees("here is nothing", {"here": Number.of(5)})


def test_eval_first_of_list_and_text():
    assert_eval_agrees("first 2 of xs", {"xs": [Number.of(1), Number.of(2), Number.of(3)]})
    assert_eval_agrees("first 0 of xs", {"xs": [Number.of(1), Number.of(2)]})
    assert_eval_agrees('first 3 of "hello"')
    assert_eval_agrees('first 0 of "hello"')


def test_eval_in_membership():
    assert_eval_agrees("x in xs", {"x": Number.of(2), "xs": [Number.of(1), Number.of(2)]})
    assert_eval_agrees("x in xs", {"x": Number.of(9), "xs": [Number.of(1), Number.of(2)]})
    assert_eval_agrees('"b" in "abc"')
    assert_eval_agrees('"z" in "abc"')
    # lenient: a cross-type element is not a match, not an error (Python `in`).
    assert_eval_agrees("x in xs", {"x": "1", "xs": [Number.of(1)]})


def test_eval_list_equality_via_bindings():
    same = {"xs": [Number.of(1), Number.of(2)], "ys": [Number.of(1), Number.of(2)]}
    diff = {"xs": [Number.of(1), Number.of(2)], "ys": [Number.of(1), Number.of(3)]}
    length = {"xs": [Number.of(1)], "ys": [Number.of(1), Number.of(2)]}
    assert_eval_agrees("xs == ys", same)
    assert_eval_agrees("xs == ys", diff)
    assert_eval_agrees("xs == ys", length)
    assert_eval_agrees("xs != ys", diff)


def test_eval_operator_errors_same_tag():
    assert_eval_fails("1 / 0", "divided-by-zero")
    assert_eval_fails('1 + "a"', "cannot-combine")
    assert_eval_fails('1 < "a"', "cannot-compare")
    assert_eval_fails("nothing == 1", "cannot-compare")
    assert_eval_fails("1 == true", "cannot-compare")
    assert_eval_fails("1 and true", "not-a-yes-no")
    assert_eval_fails('"a" - "b"', "not-a-number")


# ============================================== Phase 4: records, lists, field access, builtins


def test_eval_list_literals():
    for src in ["[]", "[1, 2, 3]", '[1, "two", true]', "[[1], [2, 3]]", "[nothing]"]:
        assert_eval_agrees(src)


def test_eval_record_literals():
    for src in ["{}", "{ x: 1 }", "{ x: 1, y: 2 }", '{ name: "a", age: 3 }',
                "{ a: { b: 1 } }", "{ items: [1, 2], ok: true }"]:
        assert_eval_agrees(src)


def test_eval_field_access():
    r = {"x": Number.of(1), "y": Number.of(2)}
    assert_eval_agrees("r.x", {"r": r})
    assert_eval_agrees("r.y", {"r": r})
    nested = {"outer": {"inner": Number.of(7)}}
    assert_eval_agrees("r.outer.inner", {"r": nested})


def test_eval_field_access_missing_is_nothing():
    # interp.py's obj.value.get(name): a missing field is nothing, not an error.
    assert_eval_agrees("r.z", {"r": {"x": Number.of(1)}})


def test_eval_field_access_non_record_fails():
    assert_eval_fails("r.x", "not-a-record", {"r": Number.of(5)})


def test_eval_record_update_with():
    r = {"x": Number.of(1), "y": Number.of(2)}
    assert_eval_agrees("r with x: 9", {"r": r})           # existing key, in place
    assert_eval_agrees("r with z: 5", {"r": r})           # new key, appended
    assert_eval_agrees("r with x: 9, y: 8", {"r": r})


def test_eval_list_plus():
    assert_eval_agrees("xs plus 4", {"xs": [Number.of(1), Number.of(2)]})
    assert_eval_agrees("xs plus 1", {"xs": []})


def test_eval_round():
    assert_eval_agrees("round 3.14159 to 2 places")
    assert_eval_agrees("round total to 0 places", {"total": Number.parse("3.7")})
    assert_eval_agrees("round (2 / 3) to 4 places")


def test_eval_builtin_count():
    assert_eval_agrees("count of xs", {"xs": [Number.of(1), Number.of(2), Number.of(3)]})
    assert_eval_agrees('count of "hello"')
    assert_eval_agrees("count of r", {"r": {"a": Number.of(1), "b": Number.of(2)}})
    assert_eval_agrees("count of xs", {"xs": []})


def test_eval_builtin_text():
    assert_eval_agrees("text of 5")
    assert_eval_agrees("text of (2 / 3)")
    assert_eval_agrees("text of true")
    assert_eval_agrees("text of nothing")
    assert_eval_agrees("text of xs", {"xs": [Number.of(1), Number.of(2)]})
    assert_eval_agrees("text of r", {"r": {"a": Number.of(1)}})
    assert_eval_agrees('"read " + text of size + " bytes"', {"size": Number.of(42)})


def test_eval_builtin_case_and_normalize():
    assert_eval_agrees('lower of "HELLO"')
    assert_eval_agrees('upper of "hi there"')
    assert_eval_agrees('normalize of "abc"')
    assert_eval_agrees("lower of s", {"s": "MixedCase"})


def test_eval_builtin_whole():
    assert_eval_agrees("whole of 3.7")
    assert_eval_agrees("whole of x", {"x": Number.parse("2.4")})
    assert_eval_agrees("whole of 5")


def test_eval_builtin_join():
    assert_eval_agrees("join of parts", {"parts": ["a", "b", "c"]})
    assert_eval_agrees("join of parts", {"parts": []})
    assert_eval_agrees('join of ["x", "y"]')


def test_eval_builtin_rest():
    assert_eval_agrees("rest of xs", {"xs": [Number.of(1), Number.of(2), Number.of(3)]})
    assert_eval_agrees("rest of xs", {"xs": [Number.of(1)]})


def test_eval_builtin_errors_same_tag():
    assert_eval_fails("join of x", "cannot-join", {"x": Number.of(5)})
    assert_eval_fails("join of xs", "cannot-join", {"xs": [Number.of(1)]})
    assert_eval_fails("rest of xs", "empty-list", {"xs": []})
    assert_eval_fails('rest of "hi"', "not-a-list")
    assert_eval_fails('whole of "x"', "not-a-number")


def test_eval_effects_fail_naming_build_3():
    # A.6: ask and read are effects (build 3). interp.py fully implements them,
    # so its tag legitimately differs (module-not-used); the Planes side must
    # reach a case that fails naming build 3, never a silent stub.
    assert_planes_fails('ask "http://example.com"', "build-3-effect")
    assert_planes_fails('read "notes.txt"', "build-3-effect")


# ============================================== Phase 6: the pipeline, connected


def planes_pipeline(src):
    """Source text -> canonical value, entirely through grammar/interp.planes's
    evaluate-source: tokenize -> parse -> eval -> render, one Planes call."""
    i = _get_interp()
    return i.call("evaluate-source", [_traced(src)], i.env).value


def assert_pipeline_agrees(src):
    py_form = canonical(interp_eval(src))
    planes_form = planes_pipeline(src)
    assert planes_form == py_form, (
        f"\nsrc: {src!r}\n--- planes pipeline ---\n{planes_form!r}"
        f"\n--- python ---\n{py_form!r}")


def test_pipeline_source_to_canonical_end_to_end():
    # The first three-stage Planes run: lexer.planes -> parser.planes ->
    # interp.planes, no Python in the path but the host running the outermost
    # interpreter. Each fragment goes from source text straight to a canonical
    # value string in one call.
    for src in ["1 + 2 * 3", "(2 + 3) * 4", "2 / 3", "0.1 + 0.2",
                '"a" + "b" + "c"', "not (1 == 2)", "true and (1 < 2)",
                "{ x: 1, y: [2, 3], ok: true }", "[1, 2, 3] plus 4",
                "first 2 of [9, 8, 7]", '"read " + text of 42 + " bytes"',
                "{ a: 1 } with a: 9", "count of [1, 2, 3]", "1 / 3 + 1 / 3 + 1 / 3"]:
        assert_pipeline_agrees(src)


def test_pipeline_with_functions_end_to_end():
    i = _get_interp()
    defs = ("to add of a, b: give a + b\n"
            "to twice of x: give add of x, x\n")
    expr = "twice of (add of 3, 4)"
    planes_form = i.call("evaluate-with", [_traced(defs), _traced(expr)], i.env).value
    py_form = canonical(interp_eval_program(defs, expr))
    assert planes_form == py_form, (planes_form, py_form)


def test_pipeline_depth_within_and_past_the_limit():
    # The interpreted-expression-nesting limit is real (parse-bound at ~23
    # levels; eval alone reaches ~140). Robust margins: a shallow nest
    # evaluates; a deep one raises recursion-too-deep, honestly, not a wrong
    # value.
    def nested(n):
        s = "1"
        for _ in range(n):
            s = "1 + (" + s + ")"
        return s
    assert planes_pipeline(nested(15)) == "16"
    try:
        planes_pipeline(nested(60))
        raise AssertionError("expected recursion-too-deep past the usable depth")
    except PlanesError as e:
        assert e.tag == "recursion-too-deep", e.tag


# ============================================== Phase 5: calls to pure functions


def test_call_single_param_function():
    defs = "to double of x: give x + x\n"
    assert_eval_program_agrees(defs, "double of 21")
    assert_eval_program_agrees(defs, "double of (double of 5)")


def test_call_multi_param_function():
    defs = "to add of a, b: give a + b\n"
    assert_eval_program_agrees(defs, "add of 3, 4")
    assert_eval_program_agrees(defs, "add of 10, (add of 1, 2)")


def test_function_calls_another_function():
    defs = ("to add of a, b: give a + b\n"
            "to twice of x: give add of x, x\n")
    assert_eval_program_agrees(defs, "twice of 5")
    assert_eval_program_agrees(defs, "twice of (twice of 3)")


def test_function_uses_a_builtin():
    defs = "to loud of s: give upper of s\n"
    assert_eval_program_agrees(defs, 'loud of "hello"')


def test_function_returns_record_and_list():
    defs = ("to point of x, y: give { x: x, y: y }\n"
            "to pair of a, b: give [a, b]\n")
    assert_eval_program_agrees(defs, "point of 1, 2")
    assert_eval_program_agrees(defs, "pair of 3, 4")
    assert_eval_program_agrees(defs, "(point of 1, 2).x")


def test_function_with_field_access_on_argument():
    defs = "to name-of of r: give r.name\n"
    assert_eval_program_agrees(defs, "name-of of person",
                               {"person": {"name": "Ada", "age": Number.of(36)}})


def test_user_function_shadows_builtin():
    # interp.py: a name in funcs is never routed to a builtin.
    defs = "to count of x: give x + 100\n"
    assert_eval_program_agrees(defs, "count of 5")


def test_zero_arg_function_by_bare_name():
    defs = "to seven: give 3 + 4\n"
    assert_eval_program_agrees(defs, "seven")
    assert_eval_program_agrees(defs, "seven + 1")
    assert_eval_program_agrees(defs, "seven * seven")


def test_nested_calls():
    defs = "to inc of n: give n + 1\n"
    assert_eval_program_agrees(defs, "inc of (inc of (inc of 0))")


def test_call_arity_and_unknown_errors():
    defs = "to add of a, b: give a + b\n"
    # wrong arity, agreeing tag
    for expr in ["add of 1", "add of 1, 2, 3"]:
        py_raised = planes_raised = None
        try:
            interp_eval_program(defs, expr)
        except PlanesError as e:
            py_raised = e.tag
        try:
            planes_eval_program(defs, expr)
        except PlanesError as e:
            planes_raised = e.tag
        assert py_raised == "wrong-arity" == planes_raised, (expr, py_raised, planes_raised)
    # unknown function
    try:
        planes_eval_program(defs, "nope of 1")
        raise AssertionError("expected failure")
    except PlanesError as e:
        assert e.tag == "unknown-function", e.tag


def test_non_expression_body_fails_naming_build_2():
    # A function whose body is not a single give-expression is control flow --
    # build 2. interp.py evaluates it (statements are already built there), so
    # this is asserted Planes-side: it must fail naming build 2, not stub.
    defs = ("to f of x:\n"
            "  let y = x + 1\n"
            "  give y\n")
    try:
        planes_eval_program(defs, "f of 5")
        raise AssertionError("expected build-2 failure")
    except PlanesError as e:
        assert e.tag == "build-2-statements", e.tag


def _program_fail_tag(defs_src, expr_src, side, bindings=None):
    """The error tag raised by one side evaluating expr against defs, or None
    if it did not raise a PlanesError."""
    try:
        if side == "py":
            interp_eval_program(defs_src, expr_src, bindings)
        else:
            planes_eval_program(defs_src, expr_src, bindings)
        return None
    except PlanesError as e:
        return e.tag


def test_lexical_scoping_callee_cannot_see_caller_binding():
    # A.1, the divergence test. `inner` references `secret`, a name bound only
    # in `outer`'s frame. Under dynamic scoping (build 1's `params + call-env`)
    # `inner` sees `outer`'s `secret` and computes a value; under lexical
    # scoping (`params + globals-of call-env`, and interp.py's Env(fn.env)) it
    # does not, and both implementations fail with unknown-name. This is the
    # only kind of program that distinguishes the two, and without it the fix
    # is unpinned.
    defs = ("to inner of x: give x + secret\n"
            "to outer of secret: give inner of 1\n")
    py = _program_fail_tag(defs, "outer of 5", "py")
    planes = _program_fail_tag(defs, "outer of 5", "planes")
    assert py == "unknown-name", f"interp.py tag {py!r} (dynamic scoping leak?)"
    assert planes == "unknown-name", f"planes tag {planes!r} (dynamic scoping leak?)"


def test_lexical_scoping_functions_still_globally_visible():
    # The fix drops caller locals but must keep every function reachable at any
    # depth: mutual recursion and calls between functions still resolve, because
    # globals-of preserves the function bindings. A three-deep call chain agrees.
    defs = ("to a of n: give b of (n + 1)\n"
            "to b of n: give c of (n + 1)\n"
            "to c of n: give n * 10\n")
    assert_eval_program_agrees(defs, "a of 0")


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
