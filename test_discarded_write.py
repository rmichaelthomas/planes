"""The discarded-write build: A-Q9's silent wrong answer becomes a named
error, checked before a program runs and agreeing byte-for-byte across all
three implementations.

The rule (repeated where it is enforced, not just where it is designed):
report `discarded-write` when a `let` binding sits inside a loop body, its
right-hand side reads the very name it binds, and that name is already
bound in an enclosing scope -- the exact shape that discarded a loop's
accumulated total in the A-Q9 cold-start run (reports/REPORT_VALUES.md's
V-Q5 explains why `let` shadows locally in the first place; V-Q1's
reasoning -- a value that is true about the computation and useless about
the mistake should not enter the derivation graph silently -- is why this
is an error rather than a warning).

Sections:
  A. the exact case, refused, naming the variable and the fix
  B. all four conditions required -- one test per condition removed
  C. cross-implementation agreement -- Python, JavaScript, self-hosted
  D. no behaviour change to `let` / `=` / scoping
  E. the repo sweep -- a permanent regression guard, not a one-off script
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

from interp import Deriv, Interpreter, PlanesError, Traced
from modules import load_graph, names_in_graph
from parser import find_discarded_writes, parse

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))

HAZARD_SRC = (
    'use file\n'
    'let total = 0\n'
    'for each order in [{ amount: 3 }, { amount: 4 }]:\n'
    '  let total = total + order.amount\n'
    'write total to "total.json"\n'
)

FIXED_SRC = (
    'use file\n'
    'total = 0\n'
    'for each order in [{ amount: 3 }, { amount: 4 }]:\n'
    '  total = total + order.amount\n'
    'write total to "total.json"\n'
)


def _skip_if_no_node():
    if NODE is None:
        print("  SKIP  node not on PATH")
        return True
    return False


# ================================================================ A. the exact case

def test_the_a_q9_case_is_refused_naming_the_variable_and_the_fix():
    try:
        Interpreter(fs={}).run(HAZARD_SRC)
        assert False, "should have raised discarded-write"
    except PlanesError as e:
        assert e.tag == "discarded-write"
        assert "'total'" in e.detail
        assert "discarded" in e.detail
        assert "let" in e.fix
        assert "bare assignment" in e.fix


def test_the_corrected_form_writes_the_correct_sum():
    i = Interpreter(fs={})
    i.run(FIXED_SRC)
    assert json.loads(i.fs["total.json"]) == 7


def test_the_check_runs_before_any_statement_executes():
    """Refused at parse time, not mid-loop: a hazard program that would ask
    or write on its very first line still never reaches it."""
    src = ('use file\n'
           'let seen = 0\n'
           'for each n in [1, 2, 3]:\n'
           '  write "should never run" to "side-effect.json"\n'
           '  let seen = seen + n\n')
    i = Interpreter(fs={})
    try:
        i.run(src)
        assert False, "should have raised discarded-write"
    except PlanesError as e:
        assert e.tag == "discarded-write"
    assert i.fs == {}, "the write inside the loop body must never have run"


# ================================================================ B. all four conditions required

def test_condition_1_let_outside_a_loop_does_not_fire():
    src = 'let total = 0\nlet total = total + 1\n'
    assert find_discarded_writes(parse(src)) == []


def test_condition_2_bare_assignment_inside_a_loop_does_not_fire():
    src = ('total = 0\n'
           'for each n in [1, 2, 3]:\n'
           '  total = total + n\n')
    assert find_discarded_writes(parse(src)) == []


def test_condition_3_a_let_whose_right_hand_side_does_not_read_its_own_name_does_not_fire():
    src = ('total = 0\n'
           'for each n in [1, 2, 3]:\n'
           '  let total = n\n')
    assert find_discarded_writes(parse(src)) == []


def test_condition_4_a_genuinely_new_local_with_no_enclosing_binding_does_not_fire():
    src = ('for each n in [1, 2, 3]:\n'
           '  let total = n\n')
    assert find_discarded_writes(parse(src)) == []


def test_all_four_together_is_what_fires():
    assert find_discarded_writes(parse(
        'let total = 0\n'
        'for each n in [1, 2, 3]:\n'
        '  let total = total + n\n')) == ["total"]


# ================================================================ soundness: branches don't leak

def test_a_binding_in_one_if_branch_does_not_leak_into_its_sibling():
    """Found during this build's own self-review: `then` and `els` are
    mutually exclusive at runtime, so a name only one of them binds must
    not read as bound to the other -- the same reasoning shapes.py states
    for its own `consts.child()` per branch."""
    src = ('if false:\n'
           '  amt = 5\n'
           'else:\n'
           '  for each n in [1, 2, 3]:\n'
           '    let amt = amt + n\n')
    assert find_discarded_writes(parse(src)) == []


def test_a_binding_from_a_sibling_statement_in_the_same_loop_body_still_counts():
    """The other direction of the same fix: a name bound earlier in the
    SAME statement list (not a sibling branch) is a real ancestor once a
    nested loop is reached."""
    src = ('for each order in [1]:\n'
           '  total = 0\n'
           '  for each part in [1, 2]:\n'
           '    let total = total + part\n')
    assert find_discarded_writes(parse(src)) == ["total"]


def test_the_hazard_still_fires_through_a_nested_if():
    src = ('total = 0\n'
           'for each n in [1, 2, 3]:\n'
           '  if true:\n'
           '    let total = total + n\n')
    assert find_discarded_writes(parse(src)) == ["total"]


# ================================================================ C. cross-implementation agreement

def _js_run(src, files=None):
    with tempfile.NamedTemporaryFile("w", suffix=".planes", delete=False,
                                     encoding="utf-8") as f:
        f.write(src)
        path = f.name
    try:
        cfg = json.dumps({"files": files or {}})
        r = subprocess.run([NODE, "js/cli.mjs", "run", path, cfg],
                           cwd=REPO, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)
    finally:
        os.unlink(path)


def test_python_and_javascript_agree_byte_for_byte_on_the_hazard_message():
    if _skip_if_no_node():
        return
    py_e = None
    try:
        Interpreter(fs={}).run(HAZARD_SRC)
    except PlanesError as e:
        py_e = e
    assert py_e is not None and py_e.tag == "discarded-write"

    js = _js_run(HAZARD_SRC)
    assert js["tag"] == "discarded-write"
    assert js["message"] == str(py_e), (js["message"], str(py_e))
    assert js["output"] == [], "must be refused before anything shows"
    assert js["files"] == {}, "must be refused before anything writes"


def test_python_and_javascript_agree_the_fixed_form_runs_and_writes_the_sum():
    if _skip_if_no_node():
        return
    i = Interpreter(fs={})
    i.run(FIXED_SRC)
    py_result = json.loads(i.fs["total.json"])

    js = _js_run(FIXED_SRC)
    assert js["tag"] is None, js
    js_result = json.loads(js["files"]["total.json"])
    assert py_result == js_result == 7


def _planes_interp():
    """grammar/interp.planes, loaded once through interp.py -- test_builtin_
    guards.py's own harness shape."""
    interp = Interpreter()
    interp.run_file("grammar/interp.planes")
    return interp


def _planes_call_inert(interp, fn, src):
    """execute-program-with of src, (default-io) -- the hermetic entry
    point (mode: "inert", every table empty), never execute-program's
    real-io: a test must not reach the real filesystem or network, and
    execute-program does exactly that for a real `write`."""
    io_config = interp.call("default-io", [], interp.env)
    src_arg = Traced(src, Deriv("literal", "<test>", src, []))
    return interp.call("execute-program-with", [src_arg, io_config], interp.env)


def test_the_self_hosted_interpreter_agrees_byte_for_byte_too():
    """grammar/interp.planes's own check-discarded-writes / find-discarded-
    writes, exercised by running IT through interp.py and calling
    execute-program-with the way test_builtin_guards.py's own harness
    does — inert, so no real effect reaches the filesystem."""
    py_e = None
    try:
        Interpreter(fs={}).run(HAZARD_SRC)
    except PlanesError as e:
        py_e = e
    assert py_e is not None

    interp = _planes_interp()
    try:
        _planes_call_inert(interp, "execute-program-with", HAZARD_SRC)
        assert False, "should have raised discarded-write"
    except PlanesError as e:
        assert e.tag == py_e.tag == "discarded-write"
        assert e.detail == py_e.detail
        assert e.fix == py_e.fix


def test_the_self_hosted_interpreter_runs_the_fixed_form_clean():
    """The corrected form is not refused: execute-program-with completes
    with status "normal" instead of raising discarded-write. The written
    value itself is already checked byte-for-byte in Python and JavaScript
    above; this only needs to show the self-hosted side does not also
    refuse a program it must not."""
    interp = _planes_interp()
    result = _planes_call_inert(interp, "execute-program-with", FIXED_SRC)
    assert result.value["status"] == "normal"


def test_three_implementations_agree_this_is_the_349th_shape():
    """The build prompt's own framing: one new error tag is one new shape
    in the three-way agreement space this repo maintains
    (test_all_three_implementations_agree_on_tag_detail_and_fix in
    test_builtin_guards.py sweeps 348 expression shapes; this is not one of
    those -- it is a whole-program shape, so it gets its own case here
    rather than a forced fit into that generator's single-expression form).
    All three agree: Python raises it, JavaScript raises the byte-identical
    message, and the self-hosted interpreter -- running on top of
    interp.py -- raises the identical tag/detail/fix too."""
    if _skip_if_no_node():
        return
    tags = set()

    try:
        Interpreter(fs={}).run(HAZARD_SRC)
    except PlanesError as e:
        tags.add(("python", e.tag, e.detail, e.fix))

    js = _js_run(HAZARD_SRC)
    tags.add(("js", js["tag"], _js_detail(js["message"]), _js_fix(js["message"])))

    try:
        _planes_call_inert(_planes_interp(), "execute-program-with", HAZARD_SRC)
    except PlanesError as e:
        tags.add(("planes", e.tag, e.detail, e.fix))

    assert len(tags) == 3, tags
    by_impl = {t[0]: t[1:] for t in tags}
    assert by_impl["python"] == by_impl["js"] == by_impl["planes"], by_impl


FIX_MARKER = "\n  try: "


def _js_detail(message):
    head = message.split(FIX_MARKER, 1)[0]
    return head.split(": ", 1)[1] if ": " in head else ""


def _js_fix(message):
    return message.split(FIX_MARKER, 1)[1] if FIX_MARKER in message else ""


# ================================================================ D. no behaviour change

def test_let_still_shadows_locally_when_the_hazard_shape_is_not_present():
    """The one case this build must never touch: `let` inside a loop whose
    right-hand side does NOT read the shadowed name still silently
    shadows, exactly as V-Q5 left it -- this build narrows detection to a
    named signature, not a ban on `let` in a loop."""
    i = Interpreter()
    i.run('total = 0\n'
         'for each n in [1, 2, 3]:\n'
         '  let total = n\n'
         'show text of total')
    assert i.output == ["0"]


def test_bare_assignment_accumulation_is_completely_unaffected():
    i = Interpreter()
    i.run('total = 0\n'
         'for each n in [1, 2, 3, 4, 5]:\n'
         '  total = total + n\n'
         'show text of total')
    assert i.output == ["15"]


# ================================================================ E. the repo sweep (permanent)

def _all_dot_planes_files():
    return sorted(set(
        glob.glob("corpus/*.planes") +
        glob.glob("demo/*.planes") + glob.glob("demo/**/*.planes", recursive=True) +
        glob.glob("paint/*.planes") + glob.glob("paint/**/*.planes", recursive=True) +
        glob.glob("grammar/*.planes")))


def test_no_existing_planes_file_in_the_repo_trips_the_check():
    """Phase 5's sweep, graduated into a permanent regression guard rather
    than a one-off verification script (this repo's own retirement rule,
    scripts/ci.sh C6/Ruling 3): every .planes file under corpus/, demo/,
    paint/, and grammar/ -- including grammar/interp.planes itself, the
    largest single file in the self-hosted stack and now the one carrying
    this very check's own implementation -- parses clean and trips
    nothing. demo/app/net.planes needs its module graph (a multi-word call
    resolved from a sibling file) to parse at all, so it is checked
    separately, through the same graph loader run_file uses."""
    fired = []
    for f in _all_dot_planes_files():
        if f == os.path.join("demo", "app", "net.planes"):
            continue
        src = open(f, encoding="utf-8").read()
        prog = parse(src)
        v = find_discarded_writes(prog)
        if v:
            fired.append((f, v))

    graph = load_graph("demo/app/main.planes")
    known = names_in_graph(graph)
    for p, src in graph:
        v = find_discarded_writes(parse(src, known))
        if v:
            fired.append((p, v))

    assert not fired, f"discarded-write fired on existing, reviewed code:\n{fired}"


if __name__ == "__main__":
    fails = []
    tests = [(k, f) for k, f in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            fails.append(name)
        except Exception as e:                                   # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
