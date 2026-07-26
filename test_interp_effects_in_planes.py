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


# =============================================================== Phase 2: write

def _txt(s):
    return {"kind": "text", "value": s, "deriv": None}


def _num(n):
    return {"kind": "number", "value": n, "deriv": None}


def _lst(items):
    return {"kind": "list", "items": items, "deriv": None}


def assert_effect_log_agrees(src, *, files=None, responses=None, py_responses=None,
                             now=0, clock=0, randoms=None, envs=None, foreigns=None):
    """The inert interp.planes effect log agrees with interp.py's, in order,
    across every kind — the general agreement assertion phases 2-4 use. Files
    are [{path, body}] on the Planes side and {path: body} for interp.py;
    py_responses is interp.py's raw response table (JSON strings) when the
    program asks."""
    state = run_inert(src, files=files or [], responses=responses or [],
                      clock=clock, randoms=randoms or [], envs=envs or [],
                      foreigns=foreigns or [])
    assert state["status"] == "normal", state
    mine = _log(state)
    theirs, _out = py_effects(
        src,
        files={f["path"]: f["body"] for f in (files or [])},
        responses=py_responses or {},
        now=now)
    assert mine == theirs, f"\ninterp.planes: {mine}\ninterp.py:     {theirs}"
    return state


def test_write_inert_logs_destination_and_agrees():
    src = ('use file\n'
           'write [1, 2, 3] to "out.json"\n'
           'show "done"\n')
    state = assert_effect_log_agrees(src)
    assert _log(state) == [("write", "out.json"), ("show", "done")]


def test_write_without_use_file_fails_module_check_like_interp_py():
    state = run_inert('write 5 to "x"\n')
    assert state["status"] == "fail"
    assert state["error"]["tag"] == "module-not-used"


def test_write_real_mode_bytes_match_interp_py():
    # real mode, hermetic via a TestHost outer interpreter: interp.planes writes
    # through the outer host's `write`, which serialises the unwrapped raw value
    # with the same to_json interp.py uses -- so the bytes are identical.
    src = ('use file\nwrite [1, 2, 3] to "out.json"\n')
    ho = _TestHost(files={})
    ir = Interpreter(host=ho)
    ir.run_file(INTERP_PLANES)
    ir.call("execute-program", [_t(src)], ir.env)
    hp = _TestHost(files={})
    ip = Interpreter(host=hp)
    ip.run(src)
    assert ho.files.get("out.json") == hp.files.get("out.json")
    assert ho.files.get("out.json") is not None


def test_write_dest_from_a_variable_and_a_show_of_a_read_shape():
    # write's destination resolved from a binding, threaded through the log.
    src = ('use file\n'
           'name = "report.json"\n'
           'write { ok: true } to name\n')
    state = assert_effect_log_agrees(src)
    assert _log(state) == [("write", "report.json")]


def test_multiple_writes_ordered_in_the_log():
    src = ('use file\n'
           'for each p in ["a.txt", "b.txt", "c.txt"]:\n'
           '  write "x" to p\n')
    state = assert_effect_log_agrees(src)
    assert _log(state) == [("write", "a.txt"), ("write", "b.txt"),
                           ("write", "c.txt")]


# ============================================ Phase 3: input effects (5 kinds)

def test_read_inert_returns_file_body_and_logs_agree():
    src = ('use file\n'
           'body = read "notes.txt"\n'
           'show body\n')
    state = assert_effect_log_agrees(src, files=[{"path": "notes.txt", "body": "hello"}])
    assert _log(state) == [("read", "notes.txt"), ("show", "hello")]
    body = next(b["value"] for b in state["env"] if b["name"] == "body")
    assert body == _txt("hello")


def test_read_without_use_file_fails_module_check():
    state = run_inert('x = read "n.txt"\n', files=[{"path": "n.txt", "body": "z"}])
    assert state["status"] == "fail"
    assert state["error"]["tag"] == "module-not-used"


def test_read_missing_file_fails_like_interp_py():
    state = run_inert('use file\nx = read "gone.txt"\n')
    assert state["status"] == "fail"
    assert state["error"]["tag"] == "no-such-file"


def test_ask_inert_returns_supplied_response_and_logs_agree():
    src = ('use http\n'
           'r = ask "https://api.example.com/x"\n')
    # log agreement (interp.py logs the same ask regardless of the body)
    state = assert_effect_log_agrees(
        src,
        responses=[{"url": "https://api.example.com/x", "value": _txt("ok")}],
        py_responses={"https://api.example.com/x": '"ok"'})
    assert _log(state) == [("ask", "https://api.example.com/x")]
    r = next(b["value"] for b in state["env"] if b["name"] == "r")
    assert r == _txt("ok")


def test_ask_without_use_http_fails_module_check():
    state = run_inert('r = ask "https://x"\n',
                      responses=[{"url": "https://x", "value": _txt("y")}])
    assert state["status"] == "fail"
    assert state["error"]["tag"] == "module-not-used"


def test_clock_foreign_inert_is_the_fixed_value_and_logs_agree():
    src = ('foreign now from "time.time" doing clock\n'
           'a = now\n'
           'b = now\n')
    # both draws return the same fixed clock; interp.py logs (clock, time.time)
    state = assert_effect_log_agrees(src, clock=1000000)
    assert _log(state) == [("clock", "time.time"), ("clock", "time.time")]
    for name in ("a", "b"):
        v = next(x["value"] for x in state["env"] if x["name"] == name)
        assert v == _num(1000000)


def test_random_foreign_inert_draws_the_sequence_head_first():
    src = ('foreign roll from "random.random" doing random\n'
           'a = roll\n'
           'b = roll\n'
           'c = roll\n')
    state = assert_effect_log_agrees(src, randoms=[11, 22, 33])
    assert _log(state) == [("random", "random.random")] * 3
    drawn = [next(x["value"] for x in state["env"] if x["name"] == n)["value"]
             for n in ("a", "b", "c")]
    assert drawn == [11, 22, 33]


def test_random_foreign_inert_runs_out_fails_cleanly():
    src = ('foreign roll from "random.random" doing random\n'
           'a = roll\n'
           'b = roll\n')
    state = run_inert(src, randoms=[7])
    assert state["status"] == "fail"
    assert state["error"]["tag"] == "no-random-supplied"


def test_env_foreign_inert_reads_supplied_table_and_logs_agree():
    src = ('foreign home from "os.getcwd" doing env\n'
           'h = home\n')
    state = assert_effect_log_agrees(src, envs=[{"name": "home", "value": _txt("/work")}])
    assert _log(state) == [("env", "os.getcwd")]
    h = next(b["value"] for b in state["env"] if b["name"] == "h")
    assert h == _txt("/work")


def test_ask_param_destination_resolves_at_the_call_site():
    # a foreign whose ask destination is a parameter: the log records the real
    # url passed at the call, matching interp.py's dest resolution.
    src = ('foreign report of ep from "builtins.str" doing ask ep\n'
           's = report of "https://metrics/x"\n')
    state = assert_effect_log_agrees(
        src, foreigns=[{"name": "report", "value": _txt("sent")}])
    assert _log(state) == [("ask", "https://metrics/x")]


def test_all_seven_effect_kinds_in_one_inert_program_agree():
    # show, write, ask, read, clock, random, env — end to end, one program,
    # inert, agreeing with interp.py on the whole effect sequence.
    src = (
        'use file\n'
        'use http\n'
        'foreign now from "time.time" doing clock\n'
        'foreign roll from "random.random" doing random\n'
        'foreign home from "os.getcwd" doing env\n'
        'show "start"\n'
        'body = read "in.txt"\n'
        'resp = ask "https://api/x"\n'
        'write body to "out.txt"\n'
        't = now\n'
        'r = roll\n'
        'h = home\n'
    )
    state = assert_effect_log_agrees(
        src,
        files=[{"path": "in.txt", "body": "data"}],
        responses=[{"url": "https://api/x", "value": _txt("ok")}],
        py_responses={"https://api/x": '"ok"'},
        clock=1234, randoms=[9],
        envs=[{"name": "home", "value": _txt("/w")}])
    kinds = [k for (k, _t) in _log(state)]
    assert kinds == ["show", "read", "ask", "write", "clock", "random", "env"]
    assert set(kinds) == {"show", "read", "ask", "write", "clock", "random", "env"}
