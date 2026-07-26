"""S3d (build 3) — effects, the host boundary, agreement in `"inert"` mode.

`grammar/interp.planes` performs effects through a boundary that dispatches on a
mode tag (A.1). In `"real"` mode the outer host performs the effect; in
`"inert"` mode nothing is performed — an output effect appends to a log threaded
through the status record, an input effect reads from supplied data. `"inert"`
is what makes effect agreement testable: an interpreted program that writes a
file, asks a url, or reads the clock is checked against `interp.py` without
either side touching the filesystem, the network, or the real clock.

The agreement oracle is `interp.py` run under `TestHost` (host.py), whose effect
log is `self.effects`. Both sides are normalised to `(kind, target)` pairs in
order and compared. Values (`show` output, final bindings) are compared through
the same canonical form the build-1/build-2 harnesses use.

Grows phase by phase: Phase 1 `show`; Phase 2 adds `write`; Phase 3 adds `ask`,
`read`, `clock`, `random`, `env`; Phase 4 adds `foreign` and the corpus.
"""
import pytest

from host import TestHost as _TestHost  # (aliased: not a test class)
from interp import Deriv, Interpreter, Number, Traced

INTERP_PLANES = "grammar/interp.planes"


# --------------------------------------------------------------- the harness

def _fresh():
    i = Interpreter()
    i.run_file(INTERP_PLANES)
    return i


def _t(v):
    return Traced(v, Deriv("literal", repr(v), v))


def _inert_io(*, clock=0, randoms=None, files=None, responses=None,
              envs=None, foreigns=None, modules=None):
    """An inert io configuration for `execute-program-with`.

    The input tables are association lists of the shape `interp.planes` scans:
    files/responses/envs/foreigns as { key, ... } pairs, randoms as a bare list
    drawn head-first. `value` fields are already-wrapped tagged interp.planes
    values (a pure interpreted value never needs the host to build it).
    """
    return {
        "mode": "inert",
        "log": [],
        "modules": list(modules or []),
        "clock": clock,
        "randoms": list(randoms or []),
        "files": files or [],
        "responses": responses or [],
        "envs": envs or [],
        "foreigns": foreigns or [],
    }


def _io_of(state):
    """The reserved __io__ record out of a final program env."""
    for b in state["env"]:
        if b["name"] == "__io__":
            return b["value"]
    raise AssertionError("no __io__ binding in program env")


def _log(state):
    """The accumulated effect log, as ordered (kind, target) pairs."""
    return [(e["kind"], e["target"]) for e in _io_of(state)["log"]]


def run_inert(src, **cfg):
    i = _fresh()
    state = i.call("execute-program-with", [_t(src), _t(_inert_io(**cfg))], i.env).value
    return state


def run_real(src):
    """Real mode: the outer host performs. Returns (state, outer_output)."""
    i = _fresh()
    state = i.call("execute-program", [_t(src)], i.env).value
    return state, list(i.output)


# ------------------------------------------------------- the interp.py oracle

def _norm_py_effects(effects):
    """interp.py's self.effects, normalised to (kind, target). Every entry is
    (kind, target, ...) — show/write/ask/read carry a trailing length we drop;
    a foreign effect is already (kind, dest)."""
    return [(e[0], e[1]) for e in effects]


def py_effects(src, *, files=None, responses=None, now=None):
    """Run `src` through interp.py under a TestHost and return its (kind,
    target) effect log — the oracle an inert interp.planes run agrees with."""
    host = _TestHost(responses=responses or {}, files=dict(files or {}),
                     now=now if now is not None else 0)
    i = Interpreter(host=host)
    i.run(src)
    return _norm_py_effects(i.effects), list(i.output)


def assert_show_log_agrees(src):
    """The inert interp.planes show-log agrees with interp.py's, in order."""
    state = run_inert(src)
    assert state["status"] == "normal", state
    mine = _log(state)
    theirs, out = py_effects(src)
    assert mine == theirs, f"\ninterp.planes: {mine}\ninterp.py:     {theirs}"
    # the shown texts themselves also agree with interp.py's output
    shown = [t for (k, t) in mine if k == "show"]
    assert shown == out, f"\nshown: {shown}\noutput: {out}"


# =============================================================== Phase 1: show

def test_show_real_mode_performs_and_logs():
    # execute-program defaults to "real": the outer host prints, and the effect
    # is still logged (interp.py appends ("show", text) whether or not a real
    # host is present).
    state, out = run_real('show "hello"\nshow text of (1 + 2)\n')
    assert state["status"] == "normal"
    assert out == ["hello", "3"]
    assert _io_of(state)["mode"] == "real"
    assert _log(state) == [("show", "hello"), ("show", "3")]


def test_show_inert_mode_logs_without_performing():
    state = run_inert('show "hello"\nshow text of (1 + 2)\n')
    assert state["status"] == "normal"
    assert _io_of(state)["mode"] == "inert"
    assert _log(state) == [("show", "hello"), ("show", "3")]


def test_show_effect_threads_out_of_a_function_body():
    # The one delicate seam: an effect performed inside a callee must survive
    # into the caller's log. Two calls, both shows, in order.
    src = ('to greet of who: show ("hi " + who)\n'
           'a = greet of "x"\n'
           'b = greet of "y"\n')
    state = run_inert(src)
    assert _log(state) == [("show", "hi x"), ("show", "hi y")]


def test_show_effect_threads_through_nested_expression_positions():
    # An effect can sit arbitrarily deep in an expression. show is a statement,
    # but a show inside a for-each body and after branches proves the log
    # threads through control flow, left to right.
    src = ('for each n in [1, 2, 3]:\n'
           '  show text of n\n'
           'if true:\n'
           '  show "then"\n')
    state = run_inert(src)
    assert _log(state) == [("show", "1"), ("show", "2"), ("show", "3"),
                           ("show", "then")]


@pytest.mark.parametrize("src", [
    'show "a"\n',
    'show text of 42\nshow "b"\n',
    'to f of n: show text of n\nx = f of 7\ny = f of 8\n',
    'for each w in ["p", "q"]:\n  show w\n',
])
def test_show_log_agrees_with_interp_py(src):
    assert_show_log_agrees(src)


def test_number_import_is_available():
    # guard: Number import used by later phases resolves
    assert Number.of(1).text() == "1"
