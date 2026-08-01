"""The host-error-reachability-and-fix-clauses build: `reports/
REPORT_ERROR_MESSAGES.md` found two effect builtins that silently dropped
into a raw host exception instead of raising a Planes error, and nine fix
clauses that misdirected for at least one situation their raise site can
fire from. This is the permanent regression guard for both halves — not a
one-off script (test_gate.py's retirement rule forbids a `verify_*`/
`verify-*` file the gate does not run; these assertions live here instead,
where the gate already runs them).

Sections:
  A. `read`/`ask` reach a Planes error through the real host, not a traceback
  B. the nine corrected fix clauses, byte-identical across all three
     implementations wherever a site has a counterpart
  C. `compare()`'s ordering clause is unchanged — the #3 split must not
     regress it back to sharing text with `equal()`
  D. the sine-clause completeness note
"""
import os
import shutil
import sys
import tempfile

from host import PythonHost
from interp import Interpreter, PlanesError
from test_builtin_guards import _js, _js_message, _py, _py_message
from test_interp_in_planes import _env_literal, _get_interp, _traced
from test_interp_statements_in_planes import planes_execute

NODE = shutil.which("node")

# ================= A. read/ask reach a Planes error through the real host


def test_a_missing_file_through_the_real_host_is_a_planes_error():
    """The bug this build closed: interp.py's read used to catch HostError
    only, and PythonHost.read calls open() directly and wraps nothing, so a
    real missing file escaped as an uncaught FileNotFoundError."""
    d = tempfile.mkdtemp()
    path = os.path.join(d, "definitely-gone.json")
    try:
        Interpreter(host=PythonHost()).run(f'use file\nr = read "{path}"')
        raise AssertionError("should raise")
    except PlanesError as e:
        assert e.tag == "no-such-file"


def test_an_unreachable_url_through_the_real_host_is_a_planes_error():
    """Same shape: PythonHost.ask calls urlopen directly, and
    urllib.error.URLError (an OSError subclass) used to escape uncaught.
    Port 1 on localhost refuses the connection immediately — no real
    network needed."""
    try:
        Interpreter(host=PythonHost()).run(
            'use http\nr = ask "http://127.0.0.1:1/"')
        raise AssertionError("should raise")
    except PlanesError as e:
        assert e.tag == "ask-failed"


# ================= B. the nine corrected fix clauses
#
# Each entry: a Planes source that fires the site, the expected tag, and the
# corrected fix text. `selfhosted` is None for the three sites with no
# grammar/interp.planes counterpart (unrecognized-record-format and
# write-failed are Python/JS-only; recursion-too-deep's guard is inherited
# for free from the outer interpreter's own RecursionError, not a raise
# grammar/interp.planes makes itself; grammar-data-missing is a lexer/
# parser bootstrap concern, not something the self-hosted program raises).

NOTHING_FIX = (
    "test for absence with `is nothing` — if the nothing is inside a "
    "compared list or record rather than the whole value (the path names "
    "which), test that inner value with `is nothing` directly rather than "
    "rewriting the whole comparison"
)

EQUAL_CROSS_TYPE_FIX = (
    "compare same-kind values — numbers with numbers, text with text, "
    "lists with lists (compared element by element), or records with "
    "records (compared field by field)"
)

NOT_A_YES_NO_FIX = (
    "compare it against something explicit rather than a bare value — "
    "e.g. `if count of items > 0:` for an if, `x > 0 and y` for an "
    "and/or operand, or `for each x in xs where x > 0:` for a where clause"
)

RECURSION_FIX = (
    "if recursing over a collection, replace it with one `for each` pass "
    "threading a state record forward — or a cons-list stack for nested "
    "structure; if recursing on a plain number with no collection "
    "involved, `for each` has nothing to iterate over, so restructure the "
    "computation to avoid unbounded recursion depth instead"
)

CANNOT_COMBINE_FIX = (
    "convert first — `text of n` to build text, or `number of t` to do "
    "arithmetic — but only for a text/number pairing; if either side is a "
    "list or record, neither conversion is meaningful: use `plus` to "
    "append to a list, `with` to update a record, or rewrite the "
    "expression"
)

IN_TEXT_FIX = (
    "`in` over text looks for text — wrap the left side with `text of`, "
    "but only when it is a number, yes/no value, or nothing; if it is a "
    "list or record, `text of` gives an opaque placeholder, not its "
    "contents, so the search will not find what was probably intended"
)

SINE_FIX = (
    "sine takes an angle in degrees as a number — e.g. sine of 30; if "
    "this is text, convert it first with number of"
)

# (label, program-source, bare-expression-or-None, tag, fix). The bare
# expression is what grammar/interp.planes's build-1 evaluator takes
# (test_interp_in_planes.py's harness) — None where the site is a statement
# (not-a-yes-no via `if`) or has no self-hosted counterpart at all.
CASES = [
    ("nothing == a number", "show text of (nothing == 5)",
     "nothing == 5", "cannot-compare", NOTHING_FIX),
    ("a list compared with a record", "show text of ([1] == { a: 1 })",
     "[1] == { a: 1 }", "cannot-compare", EQUAL_CROSS_TYPE_FIX),
    ("a list plus a number", "show text of ([1, 2] + 5)",
     "[1, 2] + 5", "cannot-combine", CANNOT_COMBINE_FIX),
    ("a number in text", 'show text of (1 in "a1b")',
     '1 in "a1b"', "not-text", IN_TEXT_FIX),
    ("sine of text", 'show text of (sine of "5")',
     'sine of "5"', "not-a-number", SINE_FIX),
]

# not-a-yes-no fires from `if`, a statement — checked through
# test_interp_statements_in_planes.py's execute-program harness instead.
NOT_A_YES_NO_SRC = "if 5:\n  show 1\n"

# Sites with no self-hosted counterpart at all (see the module docstring):
# unrecognized-record-format and write-failed are Python/JS-only;
# recursion-too-deep and grammar-data-missing are not raises
# grammar/interp.planes makes itself.
JS_ONLY_CASES = [
    ("plain numeric recursion past the depth ceiling",
     "to countdown of n:\n"
     "  if n <= 0:\n"
     "    give 0\n"
     "  else:\n"
     "    give countdown of n - 1\n"
     "show text of (countdown of 5000)\n",
     "recursion-too-deep", RECURSION_FIX),
]


def _planes_eval_fails(expr):
    """Evaluate one bare expression through grammar/interp.planes, returning
    the PlanesError it raises. Mirrors test_interp_in_planes.py's harness."""
    i = _get_interp()
    i.run("__env = " + _env_literal({}) + "\n")
    env = i.env.get("__env")
    node = i.call("node-of-source", [_traced(expr)], i.env)
    try:
        i.call("eval", [node, env], i.env)
        raise AssertionError(f"grammar/interp.planes did not fail on {expr!r}")
    except PlanesError as e:
        return e


def test_the_nine_corrected_clauses_are_exact_in_python():
    for label, src, _expr, _tag, fix in CASES:
        msg = _py_message(src)
        assert f"\n  try: {fix}" in msg, f"{label}:\n{msg}"
    msg = _py_message(NOT_A_YES_NO_SRC)
    assert f"\n  try: {NOT_A_YES_NO_FIX}" in msg, msg


def test_the_nine_corrected_clauses_are_byte_identical_in_javascript():
    if NODE is None:
        return
    srcs = [src for _label, src, _expr, _tag, _fix in CASES] + [NOT_A_YES_NO_SRC]
    srcs += [src for _label, src, _tag, _fix in JS_ONLY_CASES]
    for src in srcs:
        py = _py_message(src)
        js = _js_message(src)
        assert py == js, f"{src!r}:\n  py={py!r}\n  js={js!r}"


def test_the_recursion_clause_is_exact_in_python():
    _label, src, _tag, fix = JS_ONLY_CASES[0]
    msg = _py_message(src)
    assert f"\n  try: {fix}" in msg, msg


def test_the_corrected_clauses_agree_in_the_self_hosted_interpreter():
    """The subset of CASES grammar/interp.planes itself can raise, plus
    not-a-yes-no through the statement-level harness."""
    for label, _src, expr, tag, fix in CASES:
        e = _planes_eval_fails(expr)
        assert e.tag == tag, f"{label}: tag {e.tag!r} != {tag!r}"
        assert str(e).endswith(f"\n  try: {fix}"), f"{label}:\n{e}"

    state = planes_execute(NOT_A_YES_NO_SRC)
    assert state["status"] == "fail"
    assert state["error"]["tag"] == "not-a-yes-no"
    assert state["error"]["fix"] == NOT_A_YES_NO_FIX, state["error"]["fix"]


# ================= C. compare()'s ordering clause is unchanged


def test_orderings_ordering_clause_did_not_move():
    """The #3 split: equal()'s cross-type clause changed above; compare()'s
    (`<` `>` `<=` `>=`) did not, because the audit found it already correct
    — only numbers and text can ever be ordered, same-typed or not."""
    msg = _py_message("show text of ([1] < [2])")
    assert msg.endswith(
        "\n  try: compare numbers with numbers, or text with text"), msg
    if NODE is not None:
        assert _js_message("show text of ([1] < [2])") == msg


# ================= D. `whole of`'s clause says what `whole of` does
#
# The clause used to read "rounds a number toward zero", which describes
# TRUNCATION and is not what this builtin does — `whole of 2.5` is 3 and
# `whole of -3.7` is -4. Two builds reported it before one fixed it, and the
# reason it survived that long is the gap this section closes: **nothing
# compared the message against the behaviour.** Every other assertion in this
# file pins a clause's TEXT, which a wrong-but-stable clause passes forever.
#
# So this asserts both halves and the relationship between them: the three
# implementations agree on the words, and the words are true of the arithmetic
# in the hosts that can run it.

WHOLE_FIX = (
    "whole of rounds a number to the nearest whole, half away from zero; "
    "if this is text, convert it first with number of — a boolean, a list, "
    "a record, or nothing has no path to becoming a number"
)

# Every case that distinguishes round-half-away-from-zero from truncation
# toward zero, from rounding half-to-even, and from a floor.
#
#   input   this builtin   truncation   half-to-even   floor
#    2.5         3              2            2           2
#   -3.7        -4             -3           -4          -4
#   -2.5        -3             -2           -2          -3
#    2.4         2              2            2           2
#   -0.5        -1              0            0          -1
ROUNDING_CASES = [("2.5", "3"), ("-3.7", "-4"), ("-2.5", "-3"),
                  ("2.4", "2"), ("-0.5", "-1")]


def test_whole_ofs_clause_is_exact_in_all_three_implementations():
    src = 'show text of (whole of "5")'
    msg = _py_message(src)
    assert msg.endswith(f"\n  try: {WHOLE_FIX}"), msg
    if NODE is not None:
        assert _js_message(src) == msg
    e = _planes_eval_fails('whole of "5"')
    assert e.tag == "not-a-number", e.tag
    assert str(e).endswith(f"\n  try: {WHOLE_FIX}"), str(e)


def test_whole_of_actually_rounds_half_away_from_zero():
    """The half the text alone could never catch. If someone rewrites
    `whole of` to truncate, the clause above still reads correctly and this
    fails — which is the direction the original defect ran, in reverse."""
    assert "nearest whole, half away from zero" in WHOLE_FIX
    for value, expected in ROUNDING_CASES:
        src = f"show text of (whole of {value})\n"
        kind, tag, out = _py(src)
        assert kind == "ok", f"whole of {value}: {kind} {tag}"
        assert out == [expected], f"whole of {value} gave {out}, not [{expected!r}]"
        if NODE is not None:
            assert _js(src) == (kind, tag, out), f"whole of {value}: py {out} != js"


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
