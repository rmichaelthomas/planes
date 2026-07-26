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

C1 gave this file the `__main__` runner every other suite here has. It had none,
and `scripts/ci.sh` runs each suite as `python3 test_*.py` — so importing the
module was the whole of what the gate did with it and none of these tests ran.
That is also why the one `pytest.mark.parametrize` is now a plain loop: nothing
else in this repo needs pytest, and a suite the gate cannot run is not a gate.
"""
import json
import os
import sys
import tempfile

from host import TestHost as _TestHost  # (aliased: not a test class)
from interp import Deriv, Interpreter, Number, Traced

INTERP_PLANES = "grammar/interp.planes"


# --------------------------------------------------------------- the harness

def _fresh():
    i = Interpreter()
    i.run_file(INTERP_PLANES)
    return i


def _t(v):
    return Traced(v, Deriv("literal", "<host value>", v))


def _inert_io(*, clock=0, randoms=None, files=None, responses=None,
              envs=None, foreigns=None, modules=None):
    """An inert io configuration for `execute-program-with`.

    The input tables are association lists of the shape `interp.planes` scans:
    files/responses/envs/foreigns as { key, ... } pairs, randoms as a bare list
    drawn head-first.

    A file and a response both carry `body` — RAW TEXT, what a host's read or
    ask actually hands back, which `interp.planes` then parses itself (C1). An
    env or foreign carries `value`, an already-wrapped tagged interp.planes
    value: those return a host value rather than a serialised one, so there is
    nothing to parse.
    """
    return {
        "mode": "inert",
        "log": [],
        # build 4: interp.py's self.output (show text AND why lines, in run
        # order) and self.annotations (`because:` by name), threaded.
        "output": [],
        "annotations": [],
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


def test_show_log_agrees_with_interp_py():
    for src in ('show "a"\n',
                'show text of 42\nshow "b"\n',
                'to f of n: show text of n\nx = f of 7\ny = f of 8\n',
                'for each w in ["p", "q"]:\n  show w\n'):
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


def _bare(v):
    """A value record with every `deriv` slot cleared.

    Build 4 fills the slot these hand-built expectations were written against
    (`deriv: None`), because provenance now rides on every value exactly as
    interp.py's Traced does. An assertion about what a value IS compares the
    bare record; where a value CAME FROM is asserted separately, against
    interp.py's own `why` output.
    """
    if isinstance(v, list):
        return [_bare(x) for x in v]
    if not isinstance(v, dict):
        return v
    return {k: (None if k == "deriv" else _bare(val)) for k, val in v.items()}


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


def test_write_then_read_in_one_inert_run_sees_what_was_written():
    # C1: the inert files table is read-write within a run. The reference
    # already does this — TestHost.write fills its own files dict and
    # TestHost.read serves it back — so the oracle needs no special setup.
    src = ('use file\n'
           'write { query: "2 + 2", result: 4 } to "cache/answer.json"\n'
           'back = read "cache/answer.json"\n'
           'show back\n')
    state = assert_effect_log_agrees(src)
    assert _log(state)[:2] == [("write", "cache/answer.json"),
                               ("read", "cache/answer.json")]
    shown = [t for (k, t) in _log(state) if k == "show"]
    # the bytes read back are json.planes's, and they are to_json's
    assert shown == ['{\n  "query": "2 + 2",\n  "result": 4\n}']
    _theirs, out = py_effects(src)
    assert shown == out


def test_the_bytes_the_inert_table_holds_are_the_bytes_the_reference_holds():
    src = ('use file\n'
           'write [1, 2, 3] to "a.json"\n'
           'write "text" to "b.json"\n'
           'write { n: 5, xs: [1, 2] } to "c.json"\n')
    state = run_inert(src)
    assert state["status"] == "normal", state
    mine = {f["path"]: f["body"] for f in _io_of(state)["files"]}
    host = _TestHost(files={})
    Interpreter(host=host).run(src)
    assert mine == host.files, f"\nplanes: {mine}\nreference: {host.files}"


def test_a_rewrite_of_the_same_path_is_what_a_later_read_sees():
    src = ('use file\n'
           'write "first" to "p.txt"\n'
           'write "second" to "p.txt"\n'
           'show read "p.txt"\n')
    state = assert_effect_log_agrees(src)
    assert [t for (k, t) in _log(state) if k == "show"] == ['"second"']


def test_an_inert_write_reaches_no_real_filesystem():
    """Constraint: inert mode reaches nothing real. The destination is an
    absolute path in a fresh temp directory, so the check is not confounded by
    anything already on disk."""
    d = tempfile.mkdtemp(prefix="planes-inert-")
    path = os.path.join(d, "must-not-exist.json")
    src = (f'use file\nwrite {{ a: 1 }} to "{path}"\n'
           f'show read "{path}"\n')
    state = run_inert(src)
    assert state["status"] == "normal", state
    assert [t for (k, t) in _log(state) if k == "show"] == ['{\n  "a": 1\n}']
    assert os.listdir(d) == [], os.listdir(d)


def test_the_write_then_read_corpus_program_runs_self_hosted_and_agrees():
    """corpus/cache-store.planes — the program the report named as unreachable
    for exactly this reason. It now runs on interp.planes and produces the
    reference's output, byte for byte."""
    src = open("corpus/cache-store.planes", encoding="utf-8").read()
    state = run_inert(src)
    assert state["status"] == "normal", state
    mine = _io_of(state)["output"]
    host = _TestHost()
    ip = Interpreter(host=host)
    ip.run(src)
    assert mine == ip.output, f"\nplanes: {mine}\nreference: {ip.output}"


def test_write_real_mode_of_a_record_carries_the_json_one_layer_encoded():
    """The residual real-mode limit, pinned so it cannot drift.

    interp.planes performs a real write by executing a Planes `write`, and the
    OUTER host JSON-encodes whatever it is handed. A record cannot be handed
    over AS a record — Planes records take static field names — so it goes over
    serialised, and arrives one layer deep. What C1 changed is what that layer
    contains: the reference's exact bytes, where it used to be canonical Planes
    text. Closing the last layer needs a raw-write host method (a ninth,
    proposed in REPORT_HOST_BOUNDARY.md and not built).
    """
    src = 'use file\nwrite { a: 1, b: "x" } to "out.json"\n'
    ho = _TestHost(files={})
    ir = Interpreter(host=ho)
    ir.run_file(INTERP_PLANES)
    ir.call("execute-program", [_t(src)], ir.env)
    hp = _TestHost(files={})
    ip = Interpreter(host=hp)
    ip.run(src)
    theirs, mine = hp.files["out.json"], ho.files["out.json"]
    # the payload IS the reference's bytes, exactly ...
    assert json.loads(mine) == theirs
    # ... one JSON layer too deep, which is the whole of what remains
    assert mine != theirs
    assert json.loads(theirs) == {"a": 1, "b": "x"}


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
    assert _bare(body) == _txt("hello")


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
        responses=[{"url": "https://api.example.com/x", "body": '"ok"'}],
        py_responses={"https://api.example.com/x": '"ok"'})
    assert _log(state) == [("ask", "https://api.example.com/x")]
    r = next(b["value"] for b in state["env"] if b["name"] == "r")
    assert _bare(r) == _txt("ok")


def test_ask_inert_parses_a_json_response_like_interp_py():
    # C1: the inert response table carries the RAW body, and interp.planes
    # parses it with grammar/json.planes — no host parse_json on this path. The
    # oracle is interp.py given the same raw body, so the two sides now share
    # one stub instead of one holding a pre-parsed value.
    body = '{"n": 7, "who": "ada", "tags": ["a", "b"], "ok": true, "gone": null}'
    src = ('use http\n'
           'r = ask "https://api/x"\n'
           'show r.who\n'
           'show text of r.n\n'
           'show text of (count of r.tags)\n'
           'show text of r.ok\n')
    state = assert_effect_log_agrees(
        src,
        responses=[{"url": "https://api/x", "body": body}],
        py_responses={"https://api/x": body})
    shown = [t for (k, t) in _log(state) if k == "show"]
    assert shown == ["ada", "7", "2", "true"], shown
    r = next(b["value"] for b in state["env"] if b["name"] == "r")
    assert r["kind"] == "record"
    assert [f["key"] for f in r["fields"]] == ["n", "who", "tags", "ok", "gone"]


def test_ask_inert_parses_an_exact_number_out_of_a_response():
    # A JSON number arrives as an exact number, not a float — the same
    # guarantee from_foreign gives interp.py, reached without a host.
    body = '{"rate": 0.1, "count": 3}'
    src = ('use http\n'
           'r = ask "https://api/x"\n'
           'show text of (r.rate + r.rate + r.rate)\n')
    state = assert_effect_log_agrees(
        src,
        responses=[{"url": "https://api/x", "body": body}],
        py_responses={"https://api/x": body})
    # three tenths exactly, not 0.30000000000000004
    assert [t for (k, t) in _log(state) if k == "show"] == ["0.3"]


def test_ask_inert_falls_back_to_the_text_when_the_body_is_not_json():
    # interp.py's `try: from_foreign(parse_json(body)) except: body`, reproduced
    # with json.planes's refusal standing in for the raise.
    body = "not json at all"
    src = ('use http\n'
           'r = ask "https://api/x"\n'
           'show r\n')
    state = assert_effect_log_agrees(
        src,
        responses=[{"url": "https://api/x", "body": body}],
        py_responses={"https://api/x": body})
    assert [t for (k, t) in _log(state) if k == "show"] == [body]
    r = next(b["value"] for b in state["env"] if b["name"] == "r")
    assert _bare(r) == _txt(body)


def test_ask_without_use_http_fails_module_check():
    state = run_inert('r = ask "https://x"\n',
                      responses=[{"url": "https://x", "body": '"y"'}])
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
        assert _bare(v) == _num(1000000)


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
    assert _bare(h) == _txt("/work")


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
        responses=[{"url": "https://api/x", "body": '"ok"'}],
        py_responses={"https://api/x": '"ok"'},
        clock=1234, randoms=[9],
        envs=[{"name": "home", "value": _txt("/w")}])
    kinds = [k for (k, _t) in _log(state)]
    assert kinds == ["show", "read", "ask", "write", "clock", "random", "env"]
    assert set(kinds) == {"show", "read", "ask", "write", "clock", "random", "env"}


# ================================== Phase 4: foreign declarations + the corpus

def test_foreign_pure_result_supplied_matches_the_real_builtin():
    # A pure foreign (`doing nothing`) computed for real by interp.py
    # (builtins.sorted) and supplied to interp.planes: same output, no effect
    # logged on either side.
    src = ('foreign srt of xs from "builtins.sorted" doing nothing\n'
           'ordered = srt of [3, 1, 2]\n'
           'show text of (count of ordered)\n'
           'show text of ordered\n')
    state = run_inert(src, foreigns=[{"name": "srt",
                                      "value": _lst([_num(1), _num(2), _num(3)])}])
    assert state["status"] == "normal"
    # a pure foreign logs no effect; the shows are the whole log
    assert [k for (k, _t) in _log(state)] == ["show", "show"]
    # interp.py runs the real builtin (sorted [3,1,2] -> [1,2,3]); the supplied
    # result matches, so the outputs agree exactly
    _theirs, out = py_effects(src)
    shown = [t for (k, t) in _log(state) if k == "show"]
    assert shown == out


def test_foreign_unloadable_target_refused_like_interp_py():
    # demo/fdiff/*: a foreign to a target the host cannot load (mylib.post).
    # interp.py refuses foreign-not-found; interp.planes refuses
    # foreign-needs-host. Both refuse to run a foreign the host cannot provide.
    src = open("demo/fdiff/v1.planes").read()
    # interp.planes, real mode
    ir = _fresh()
    st = ir.call("execute-program", [_t(src)], ir.env).value
    assert st["status"] == "fail"
    assert st["error"]["tag"] == "foreign-needs-host"
    # interp.py
    from interp import PlanesError
    ip = Interpreter()
    try:
        ip.run(src)
        raise AssertionError("interp.py should refuse the missing target")
    except PlanesError as e:
        assert e.tag == "foreign-not-found"


def test_foreign_ask_declared_effect_logs_and_returns_supplied():
    # foreign.planes's shape: an ask-declaring foreign with a param destination,
    # the destination resolved to the real url at the call, the effect logged,
    # and the supplied result returned.
    src = ('foreign report of endpoint from "builtins.str" doing ask endpoint\n'
           'sent = report of "https://metrics.example.com/readings"\n'
           'show "ok"\n')
    state = run_inert(src, foreigns=[{"name": "report", "value": _txt("done")}])
    assert state["status"] == "normal"
    assert _log(state) == [("ask", "https://metrics.example.com/readings"),
                           ("show", "ok")]
    sent = next(b["value"] for b in state["env"] if b["name"] == "sent")
    assert _bare(sent) == _txt("done")


# =========================================== Phase 5: the effect surface (A.3)

def test_effect_surface_of_interp_planes_is_all_seven_kinds():
    # A.3's prediction, checked against the real artifact: the static effect
    # surface of the interpreter is all seven kinds, because it performs
    # whatever the program it runs performs. Sound and maximally imprecise.
    from lexer import EFFECT_KINDS
    from shapes import analyse_file
    surface = analyse_file("grammar/interp.planes", follow=True)  # total: no raise
    kinds = {e.kind for e in surface.declared}
    assert kinds >= set(EFFECT_KINDS), (
        f"missing {set(EFFECT_KINDS) - kinds}")
    assert kinds == set(EFFECT_KINDS), f"unexpected {kinds - set(EFFECT_KINDS)}"


def test_effect_surface_analyser_stays_total_and_origins_do_not_crash():
    from shapes import analyse_file
    surface = analyse_file("grammar/interp.planes", follow=True)
    # origins_of walks the derivation graph of every effect without raising.
    for e in surface.declared:
        origins = surface.origins_of(e)
        assert isinstance(origins, list)


if __name__ == "__main__":
    fails = []
    tests = [(k, f) for k, f in sorted(globals().items())
             if k.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            fails.append(name)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
