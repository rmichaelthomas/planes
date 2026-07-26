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
from interp import Deriv, Interpreter, PlanesError, Traced
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


# ============================================================ Phase 3: branching


def test_if_statement_chooses_branch_and_rebinds():
    src = ("x = 5\n"
           "result = 0\n"
           "if x > 3:\n"
           "  result = 100\n"
           "else:\n"
           "  result = 200\n")
    assert_program_var_agrees(src, "result")


def test_if_statement_false_branch():
    src = ("x = 1\n"
           "result = 0\n"
           "if x > 3:\n"
           "  result = 100\n"
           "else:\n"
           "  result = 200\n")
    assert_program_var_agrees(src, "result")


def test_if_statement_no_else():
    src = ("x = 1\n"
           "seen = false\n"
           "if x > 3:\n"
           "  seen = true\n")
    assert_program_var_agrees(src, "seen")


def test_if_condition_not_yes_no_fails():
    src = ("x = 5\n"
           "if x:\n"
           "  y = 1\n")
    state = planes_execute(src)
    assert state["status"] == "fail"
    assert state["error"]["tag"] == "not-a-yes-no"
    # interp.py refuses the same way
    itp = Interpreter()
    try:
        itp.run(src)
        raise AssertionError("interp.py did not fail")
    except PlanesError as e:
        assert e.tag == "not-a-yes-no", e.tag


def test_when_match_and_bind():
    # `body` bound from the record (a `when` field cannot be a builtin name like
    # `text`, so the corpus binds a plain name).
    src = ('current = { kind: "NAME", body: "ab" }\n'
           'result = "start"\n'
           "when current is { kind: \"NAME\", body }:\n"
           '  result = "matched " + body\n'
           "else:\n"
           '  result = "no match"\n')
    assert_program_var_agrees(src, "result")


def test_when_no_match_runs_else():
    src = ('current = { kind: "OP", text: "+" }\n'
           'result = "start"\n'
           "when current is { kind: \"NAME\" }:\n"
           '  result = "yes"\n'
           "else:\n"
           '  result = "no"\n')
    assert_program_var_agrees(src, "result")


def test_when_missing_field_no_match():
    src = ('r = { a: 1 }\n'
           'out = "init"\n'
           "when r is { b: 2 }:\n"
           '  out = "has b"\n'
           "else:\n"
           '  out = "no b"\n')
    assert_program_var_agrees(src, "out")


def test_when_bind_only_pattern():
    src = ('point = { x: 3, y: 4 }\n'
           "when point is { x, y }:\n"
           "  s = x + y\n"
           "else:\n"
           "  s = 0\n")
    assert_program_var_agrees(src, "s")


def test_when_subject_not_a_record_fails():
    src = ("when 5 is { kind: \"NAME\" }:\n"
           "  y = 1\n")
    state = planes_execute(src)
    assert state["status"] == "fail"
    assert state["error"]["tag"] == "not-a-record"
    itp = Interpreter()
    try:
        itp.run(src)
        raise AssertionError("interp.py did not fail")
    except PlanesError as e:
        assert e.tag == "not-a-record", e.tag


def test_nested_if_inside_when():
    src = ('cmd = { verb: "go", n: 5 }\n'
           'msg = "none"\n'
           "when cmd is { verb: \"go\", n }:\n"
           "  if n > 3:\n"
           '    msg = "far"\n'
           "  else:\n"
           '    msg = "near"\n')
    assert_program_var_agrees(src, "msg")


# ============================================================ Phase 4: bindings and output


def planes_output(src):
    """The show output interp.planes produces running src (the interpreted
    program's `show` delegates to the host, so it lands in interp.py's output)."""
    i = _get()
    before = len(i.output)
    i.call("execute-program", [_t(src)], i.env)
    return list(i.output[before:])


def interp_output(src):
    itp = Interpreter()
    itp.run(src)
    return list(itp.output)


def assert_output_agrees(src):
    planes = planes_output(src)
    py = interp_output(src)
    assert planes == py, f"\nsrc:\n{src}\n--- planes ---\n{planes}\n--- python ---\n{py}"


def test_show_scalars():
    src = ('show 42\n'
           'show 2 / 3\n'
           'show "hello"\n'
           'show true\n'
           'show false\n'
           'show nothing\n')
    assert_output_agrees(src)


def test_show_uses_fmt_for_lists_and_records():
    # fmt: a list shows as "[N items]", a record as "{record}", a string bare.
    src = ('show [1, 2, 3]\n'
           'show { x: 1, y: 2 }\n'
           'show "plain string"\n')
    assert_output_agrees(src)


def test_show_computed_values():
    src = ('total = 100\n'
           'show "total is " + text of total\n'
           'items = [1, 2, 3, 4]\n'
           'show count of items\n')
    assert_output_agrees(src)


def test_show_returns_the_value_and_sequences():
    src = ('x = 5\n'
           'show x\n'
           'y = x + 1\n'
           'show y\n')
    assert_output_agrees(src)
    assert_program_var_agrees(src, "y")


def test_let_binds_new_name():
    src = ("let a = 1\n"
           "let b = a + 1\n")
    assert_program_var_agrees(src, "a")
    assert_program_var_agrees(src, "b")


def test_reassignment_rebinds_in_place_env_stays_flat():
    # Reassignment rebinds where the name lives; the environment does not grow.
    src = ("total = 0\n"
           "total = total + 1\n"
           "total = total + 2\n"
           "total = total + 3\n")
    assert_program_var_agrees(src, "total")
    state = planes_execute(src)
    # exactly one binding for `total`, and no functions -> a single-entry env.
    assert len(state["env"]) == 1, state["env"]


def test_reassignment_of_shadowing_let():
    src = ("x = 10\n"
           "x = 20\n"
           "x = x + 5\n")
    assert_program_var_agrees(src, "x")
    state = planes_execute(src)
    assert len(state["env"]) == 1


def test_non_show_effects_fail_naming_build_3():
    # A.5: show is in scope; every other effect fails naming build 3.
    for src, _kind in [
        ('write 5 to "out.txt"\n', "write"),
        ('x = ask "http://example.com"\n', "ask"),
        ('x = read "notes.txt"\n', "read"),
    ]:
        state = planes_execute(src)
        assert state["status"] == "fail", (src, state["status"])
        assert state["error"]["tag"] == "build-3-effect", (src, state["error"])


# ============================================================ Phase 5: for each


def test_foreach_accumulate_over_list():
    src = ("total = 0\n"
           "for each x in [10, 20, 30]:\n"
           "  total = total + x\n")
    assert_program_var_agrees(src, "total")


def test_foreach_accumulate_over_string_code_points():
    # A string iterates its code points -- one-code-point strings.
    src = ('acc = []\n'
           'for each c in "abc":\n'
           "  acc = acc plus c\n"
           "n = count of acc\n")
    assert_program_var_agrees(src, "acc")
    assert_program_var_agrees(src, "n")


def test_foreach_string_builds_text():
    src = ('out = ""\n'
           'for each c in "planes":\n'
           "  out = out + c\n")
    assert_program_var_agrees(src, "out")


def test_comprehension_with_where():
    src = ("people = [{ owed: 5 }, { owed: 0 }, { owed: 3 }, { owed: 0 }]\n"
           "owing = for each p in people where p.owed > 0: p\n"
           "n = count of owing\n")
    assert_program_var_agrees(src, "owing")
    assert_program_var_agrees(src, "n")


def test_comprehension_maps_values():
    src = ("xs = [1, 2, 3, 4]\n"
           "doubled = for each x in xs: x * 2\n")
    assert_program_var_agrees(src, "doubled")


def test_foreach_where_filters_before_body():
    src = ("total = 0\n"
           "for each x in [1, 2, 3, 4, 5, 6] where x > 3:\n"
           "  total = total + x\n")
    assert_program_var_agrees(src, "total")


def test_foreach_loop_var_does_not_leak():
    # The loop variable and body-local lets are per-iteration; neither persists.
    src = ("marker = 1\n"
           "for each x in [7, 8, 9]:\n"
           "  y = x\n")
    state = planes_execute(src)
    assert env_lookup(state, "x") is None
    assert env_lookup(state, "y") is None
    assert env_lookup(state, "marker") == "1"
    # interp.py agrees: x is not defined afterward.
    itp = Interpreter()
    itp.run(src)
    assert not itp.env.has("x")


def test_foreach_over_non_collection_fails():
    src = ("for each x in 5:\n"
           "  y = x\n")
    state = planes_execute(src)
    assert state["status"] == "fail"
    assert state["error"]["tag"] == "not-a-collection"


def test_foreach_nested_builds_pairs():
    src = ("pairs = []\n"
           "for each a in [1, 2]:\n"
           "  for each b in [10, 20]:\n"
           "    pairs = pairs plus (a + b)\n")
    assert_program_var_agrees(src, "pairs")


def test_foreach_show_output_agrees():
    src = ("for each n in [1, 2, 3]:\n"
           "  show n\n")
    assert_output_agrees(src)


# ============================================================ Phase 6: failure


def assert_program_fails_agree(src, expected_tag):
    state = planes_execute(src)
    assert state["status"] == "fail", (src, state)
    assert state["error"]["tag"] == expected_tag, (src, state["error"])
    itp = Interpreter()
    try:
        itp.run(src)
        raise AssertionError(f"interp.py did not fail on {src!r}")
    except PlanesError as e:
        assert e.tag == expected_tag, (src, e.tag, expected_tag)


def test_fail_statement_top_level():
    assert_program_fails_agree('fail "boom" as my-error\n', "my-error")


def test_fail_statement_detail_is_the_message():
    state = planes_execute('fail "something went wrong" as trouble\n')
    assert state["error"]["tag"] == "trouble"
    assert state["error"]["detail"] == "something went wrong"


def test_fail_message_must_be_text():
    assert_program_fails_agree("fail 5 as boom\n", "fail-message-not-text")


def test_fail_halts_the_block():
    # Rule 3: after a fail every later statement is pass-through.
    src = ('x = 1\n'
           'fail "stop" as halt\n'
           'x = 999\n')
    state = planes_execute(src)
    assert state["status"] == "fail"
    assert state["error"]["tag"] == "halt"
    assert env_lookup(state, "x") == "1"


def test_or_fail_catches_runtime_error_and_yields_tag():
    src = ("answer = (1 / 0) or fail as e: e.tag\n")
    assert_program_var_agrees(src, "answer")


def test_or_fail_handler_default_value():
    src = ("safe = (1 / 0) or fail as e: -1\n"
           "ok = (2 + 3) or fail as e: -1\n")
    assert_program_var_agrees(src, "safe")   # -1, the handler ran
    assert_program_var_agrees(src, "ok")     # 5, the handler did not run


def test_or_fail_reads_detail():
    src = ('msg = (1 / 0) or fail as e: "caught: " + e.detail\n')
    assert_program_var_agrees(src, "msg")


def test_or_fail_no_handler_retags():
    # `x or fail as tag` with no handler re-tags the failure and propagates.
    assert_program_fails_agree("y = (1 / 0) or fail as wrapped\n", "wrapped")


def test_fail_propagates_across_call_levels_caught_above():
    # Rule 3, the boundary explicitly: a fail raised several call levels deep,
    # caught by an or fail above all of them. The status resets to normal and
    # the { tag, detail } arrives as the value (its .tag read here).
    src = ("to level3 of x: give x / 0\n"
           "to level2 of x: give level3 of x\n"
           "to level1 of x: give level2 of x\n"
           "answer = (level1 of 5) or fail as e: e.tag\n")
    assert_program_var_agrees(src, "answer")


def test_give_stops_at_boundary_fail_does_not():
    # Rule 2 vs Rule 3, contrast: a function that gives is caught as a normal
    # value at the boundary (the give does not escape); a function that fails
    # sends the fail on past the boundary until or fail catches it.
    give_src = ("to g: give 7\n"
                "result = g\n")
    gstate = planes_execute(give_src)
    assert gstate["status"] == "normal"
    assert env_lookup(gstate, "result") == "7"

    fail_src = ("to bad of x: give x / 0\n"
                "caught = (bad of 1) or fail as e: e.tag\n")
    assert_program_var_agrees(fail_src, "caught")


def test_or_fail_not_triggered_passes_value_through():
    src = ("v = (10 * 5) or fail as e: 0\n")
    assert_program_var_agrees(src, "v")
