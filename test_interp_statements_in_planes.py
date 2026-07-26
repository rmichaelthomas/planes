"""Agreement test: interp.py vs. grammar/interp.planes for statements and
control flow (Route B stage three, build 2).

Build 1 evaluated expressions; build 2 runs programs -- statements that
sequence and branch, function bodies that are blocks. Every evaluation and
execution step threads one status record (A.3), and these tests pin each of
the five rules, naming which rule each exercises, with Rule 1 (pass-through as
the substitute for early exit) tested hardest.

Where a program has no top-level `give` and no unresolved effect, its result is
checked against interp.py's own run() by comparing a chosen top-level variable
through the canonical value form the build-1 harness established.
"""
from interp import Deriv, Interpreter, Traced
from test_interp_in_planes import canonical

_interp = None


def _get():
    global _interp
    if _interp is None:
        _interp = Interpreter()
        _interp.run_file("grammar/interp.planes")
    return _interp


def _t(v):
    return Traced(v, Deriv("literal", repr(v), v, []))


def planes_execute(src):
    """Run a program's top-level statements through interp.planes's exec-block,
    returning the final status record as a Python dict."""
    i = _get()
    return i.call("execute-program", [_t(src)], i.env).value


def canon_value(valrec):
    """Canonical text of a tagged Planes value record (a Python dict)."""
    i = _get()
    return i.call("canonical-of-value", [_t(valrec)], i.env).value


def env_lookup(state, name):
    """Canonical text of a name in the final environment, or None if unbound."""
    i = _get()
    b = i.call("env-find", [_t(state["env"]), _t(name)], i.env).value
    if not b["found"]:
        return None
    return canon_value(b["value"])


def assert_program_var_agrees(src, varname):
    """interp.planes execute-program and interp.py run() agree on one top-level
    variable's value, through the canonical form."""
    state = planes_execute(src)
    assert state["status"] == "normal", (state["status"], state.get("error"))
    planes_form = env_lookup(state, varname)
    itp = Interpreter()
    itp.run(src)
    py_form = canonical(itp.env.get(varname).value)
    assert planes_form == py_form, (
        f"\nsrc:\n{src}\nvar: {varname}"
        f"\n--- planes ---\n{planes_form!r}\n--- python ---\n{py_form!r}")


# ============================================================ the five rules (A.3)


def test_rule1_passthrough_later_statements_do_not_run():
    # Rule 1, tested hardest: pass-through is the substitute for early exit. The
    # block gives 1, then a statement that would rebind the answer to 999. After
    # the give (a non-normal status) every remaining step is pass-through, so
    # 999 never happens -- the given value is 1 and the binding is untouched. If
    # Rule 1 were violated (the block ran on), the value would be 999.
    src = ("answer = 1\n"
           "give answer\n"
           "answer = 999\n")
    state = planes_execute(src)
    assert state["status"] == "give"
    assert canon_value(state["value"]) == "1"
    assert env_lookup(state, "answer") == "1"


def test_rule1_passthrough_over_many_later_statements():
    # Rule 1 again, with a longer tail of would-be-wrong work after the give.
    src = ("total = 10\n"
           "give total\n"
           "total = total + 5\n"
           "total = total * 100\n"
           "total = 0\n")
    state = planes_execute(src)
    assert state["status"] == "give"
    assert canon_value(state["value"]) == "10"


def test_rule2_give_resets_to_normal_at_function_boundary():
    # Rule 2: `give` stops at the function boundary. A function that gives 42 is
    # called from a normal top-level statement; the caller's status is normal
    # and the value is 42 -- the give did not escape the function.
    src = ("to f: give 42\n"
           "result = f\n")
    state = planes_execute(src)
    assert state["status"] == "normal"
    assert env_lookup(state, "result") == "42"


def test_rule3_fail_propagates_and_halts_the_block():
    # Rule 3: a fail propagates outward, and (with no `or fail` to catch it)
    # halts the block -- every later statement is pass-through. Here the fail is
    # a runtime error (unknown-name) raised by an assignment's expression.
    src = ("x = missing\n"
           "y = 1\n")
    state = planes_execute(src)
    assert state["status"] == "fail"
    assert state["error"]["tag"] == "unknown-name"
    assert env_lookup(state, "y") is None


def test_rule4_env_rides_in_the_record():
    # Rule 4: the environment rides in the record, not threaded separately. Bind
    # x, then read it back out in a later statement's expression.
    src = ("x = 42\n"
           "y = x + 1\n")
    state = planes_execute(src)
    assert state["status"] == "normal"
    assert env_lookup(state, "x") == "42"
    assert env_lookup(state, "y") == "43"


def test_rule5_no_value_read_after_fail():
    # Rule 5: a step never inspects `value` without first checking `status`.
    # After a failed assignment (value is nothing), a later statement that would
    # compute on the result is pass-through and never touches it -- no crash,
    # and the fail stands with its original tag.
    src = ("bad = missing\n"
           "worse = bad + 1\n"
           "give worse\n")
    state = planes_execute(src)
    assert state["status"] == "fail"
    assert state["error"]["tag"] == "unknown-name"


# ============================================================ sequencing agreement


def test_sequencing_lets_agree_with_interp_py():
    src = ("a = 1\n"
           "b = a + 2\n"
           "c = b * b\n"
           "d = c - a\n")
    for v in ["a", "b", "c", "d"]:
        assert_program_var_agrees(src, v)


def test_sequencing_rebind_reads_latest_value():
    # A later read sees the latest binding (first match wins over the shadowed
    # one). Agreement with interp.py, which rebinds in place.
    src = ("n = 1\n"
           "m = n + 10\n"
           "n = 5\n"
           "p = n + 100\n")
    assert_program_var_agrees(src, "m")   # bound while n == 1
    assert_program_var_agrees(src, "p")   # bound while n == 5
    assert_program_var_agrees(src, "n")


def test_sequencing_records_and_lists():
    src = ("r = { x: 1, y: 2 }\n"
           "xs = [r.x, r.y, r.x + r.y]\n"
           "r2 = r with y: 9\n")
    assert_program_var_agrees(src, "xs")
    assert_program_var_agrees(src, "r2")


def test_top_level_call_result_agrees():
    src = ("to add of a, b: give a + b\n"
           "s = add of 3, 4\n"
           "t = add of s, s\n")
    assert_program_var_agrees(src, "s")
    assert_program_var_agrees(src, "t")
