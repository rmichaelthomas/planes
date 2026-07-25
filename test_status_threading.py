"""A.6's five status-record rules, pinned against demo/status_threading.planes
(S2 §A.6 / Phase 5 — the state-record idiom made corpus evidence rather than
folklore). One test per rule, each naming the rule it exercises; Rule 1 is
tested hardest. Plus the analyser pin: a complete effect surface across the
whole recursive idiom, and origins_of tracing a value threaded through the
record shape.
"""
import sys

from interp import Deriv, Interpreter, Traced
from shapes import analyse, analyse_file

DEMO = "demo/status_threading.planes"


def load():
    i = Interpreter()
    i.run(open(DEMO).read())
    return i


def t(v):
    return Traced(v, Deriv("literal", repr(v), v, []))


def call(i, fn, *args):
    return i.call(fn, [t(a) for a in args], i.env).value


def start(i):
    return call(i, "normal-state", [])


# ---- Rule 1: pass-through is the substitute for early exit (tested hardest)

def test_rule1_passthrough_a_later_statement_never_runs():
    # A block whose LATER statement would give a visibly wrong answer if it
    # ran after a non-normal status: give 1, then give 999. The result must be
    # 1 — the second give never ran, though the block walked to its end.
    i = load()
    body = [{"kind": "give", "value": 1}, {"kind": "give", "value": 999}]
    r = call(i, "apply-function", body, start(i))
    assert r["value"] == 1, "Rule 1: the second give ran — pass-through failed"


# ---- Rule 2: give stops at the function boundary

def test_rule2_give_stops_and_resets_at_the_function_boundary():
    i = load()
    r = call(i, "apply-function", [{"kind": "give", "value": 7}], start(i))
    assert r["status"] == "normal", "Rule 2: status must reset to normal at the boundary"
    assert r["value"] == 7


# ---- Rule 3: fail does NOT stop at the function boundary; or-fail catches it

def test_rule3_fail_propagates_past_the_boundary_until_or_fail():
    i = load()
    prog = [{"kind": "fail", "tag": "boom"}]
    uncaught = call(i, "apply-function", prog, start(i))
    assert uncaught["status"] == "fail", "Rule 3: the boundary must NOT reset a fail"
    caught = call(i, "or-fail", prog, start(i))
    assert caught["status"] == "normal", "Rule 3: or fail resets to normal"
    assert caught["value"]["tag"] == "boom", "Rule 3: the caught value is the error record"


# ---- Rule 4: the environment rides in the record

def test_rule4_the_environment_rides_in_the_record():
    i = load()
    r = call(i, "apply-function", [{"kind": "bind", "name": "x", "value": 42}], start(i))
    assert call(i, "lookup-env", r["env"], "x") == 42


# ---- Rule 5: a step never reads value without checking status first

def test_rule5_a_step_reads_nothing_on_a_nonnormal_status():
    # A fail state carries value = nothing. Handed to exec-stmt with a
    # statement that WOULD read and overwrite value if it ran, the state comes
    # back untouched — proving run-stmt never inspected value under a non-normal
    # status (exec-stmt checks status first).
    i = load()
    fail_state = {"status": "fail", "value": None, "env": [],
                  "error": {"tag": "x", "detail": ""}}
    r = call(i, "exec-stmt", {"kind": "give", "value": 5}, fail_state)
    assert r["status"] == "fail"
    assert r["value"] is None, "Rule 5: value was read/overwritten under a non-normal status"


# ---- the analyser pin (as Phase 3 does)

def test_analyser_is_total_and_complete_across_the_idiom():
    # The analyser sees through the whole recursive status-threading idiom
    # without going UNKNOWN-everywhere or crashing: the surface is exactly the
    # demo's show effects, complete and total.
    s = analyse_file(DEMO)
    assert set(s.kinds()) == {"show"}, f"expected only show effects, got {s.kinds()}"
    assert len(s.effects) == 11, f"expected 11 show effects, found {len(s.effects)}"


def test_origins_of_traces_a_value_threaded_through_the_record():
    # A value threaded through a status-record shape and into an effect traces,
    # via origins_of, back to the name it was threaded under (Rule 4's env/value
    # ride in the record; the analyser sees through the field access).
    src = ('data = ["a", "b"]\n'
           'state = { status: "normal", value: data, env: [], error: nothing }\n'
           'threaded = state.value\n'
           'use http\n'
           'r = ask (join of threaded)\n')
    s = analyse(src)
    ask = [e for e in s.effects if e.kind == "ask"][0]
    labels = [lbl for lbl, _ in s.origins_of(ask)]
    assert "threaded" in labels, f"origins_of should trace the threaded value, got {labels}"


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
