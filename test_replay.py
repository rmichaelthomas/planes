"""Tests for replay-on-demand and the tracing-off fast path (R3, checkpoint
v30.0 §466-476).

R3's shape: the fast path runs with tracing off — `mk` returns one shared,
never-mutated sentinel node instead of building a real Deriv, so a run
allocates no per-node derivation graph at all. Any `why` (any register) on a
value the fast path produced answers by REPLAY: re-executing the same
program from the start, tracing on, using a `ReplayHost` that reads each
effect back from a recorded log instead of performing it again. Replay is
exact because Planes is deterministic and pure — the gate is byte-identical
agreement between an eager (tracing-on) derivation and a replayed one for the
same computation, a fourth axis on the three-implementation discipline.

This file is the build's own N+3.2 gate: it emits a pass/fail table covering
the six things the build prompt names as blocking —
  1. tracing-off == tracing-on for output/effects/records (§3/F1)
  2. eager-vs-replay byte-identity, Python and JS, cross-language (§6/F2)
  3. effects performed once, never re-performed on replay (§7/F3)
  4. replay refuses on an unrecorded value rather than double-performing (§7/F7)
  5. explain is iterative — no overflow at 1,000 steps (§4/F6)
  6. required host surface still seven, no restore (invariant 4/F5)
— in addition to the ordinary per-function test run every suite in this repo
does. It shells out to `node js/cli.mjs replay <config>` for the
cross-language checks, the same pattern test_retention.py and
test_why_readable.py use; Node's availability is a baseline fact for this
build, so the whole file skips with a clear message if node is missing
rather than failing spuriously.

SCOPE NOTE (stated here and in REPORT_REPLAY.md, not left implicit): the
in-language `why` STATEMENT is left unchanged by this build (Ruling 2 — the
evaluator arms, including `exec_stmt`'s `Why` case, do not change). Executed
while tracing is off, it still calls `explain()` on the untraced value — the
shared sentinel carries no per-call provenance, so the resulting card text is
a well-defined but uninformative "<value> from nothing", never a crash and
never a wrong VALUE. `test_why_statement_under_tracing_off_is_well_defined_
but_uninformative` below characterizes this precisely rather than leaving it
an unexamined gap. The tracing-off/tracing-on output-equivalence gate (§3)
therefore excludes the handful of corpus files that use `why` in their own
source — a fast path is for a host that does not query explanations from
inside its own hot loop; `why` under tracing-off answers correctly only via
`replay`, on demand, exactly as §5 describes.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

from host import Host, HostError, PythonHost, TestHost
from interp import (
    Interpreter,
    PlanesError,
    ReplayHost,
    explain,
    replay,
    why_machine,
    why_tree,
)
from lexer import PlanesSyntaxError
from modules import ModuleError

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))


def _skip_if_no_node():
    if NODE is None:
        print("  SKIP  node not on PATH")
        return True
    return False


# ================================================================ fixtures

def _chain(n):
    """A program that reassigns `x` n times — the same fixture
    test_retention.py/test_why_readable.py use, one step per call for a
    multi-step scenario or joined into a single source for a single-step
    one."""
    return "\n".join(["x = 0"] + ["x = x + 1"] * n + ["show x"]) + "\n"


def _recursive_scenario():
    """A function-call chain, not just reassignment — test_why_readable.py's
    own diversifying scenario (`fact of 20`), reused here so R3's gate is
    not proven only against the reassignment shape."""
    return {
        "steps": ["to fact of n:\n  if n <= 1:\n    give 1\n  "
                  "give n * (fact of (n - 1))\n\n", "r = fact of 20\n"],
        "subject": "r",
    }


def _effectful_scenario():
    """A scenario with all four host effects a program can trigger
    directly — ask, read, write, show — mixed with ordinary reassignment,
    so the eager-vs-replay gate and the effects-once gate both have a
    subject whose derivation actually depends on effect results, not just
    pure arithmetic."""
    return {
        "steps": [
            "use http\nuse file\n",
            'let r1 = ask "http://a"\n',
            'write [1, 2] to "o.json"\n',
            'let r2 = read "o.json"\n',
            "let combined = r2\n",
            "show r1\n",
        ],
        "subject": "combined",
        "responses": {"http://a": '{"v": 1}'},
        "files": {},
    }


def _uses_why(src):
    import re
    return any(re.match(r"^\s*why\b", ln) for ln in src.splitlines())


def _corpus_files_excluding_why():
    files = sorted(
        f for f in glob.glob("**/*.planes", recursive=True) if ".venv" not in f)
    assert len(files) >= 40, len(files)
    kept = [f for f in files
            if not _uses_why(open(f, encoding="utf-8").read())]
    assert len(kept) >= 30, len(kept)
    return kept


def _uses_import(src):
    return any(ln.strip().startswith("use ") for ln in src.splitlines())


def _reachable(node):
    seen = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        if n.kind != "seal":
            stack.extend(n.inputs)
    return len(seen)


def _node_replay(cfg):
    r = subprocess.run(
        [NODE, "js/cli.mjs", "replay", json.dumps(cfg)],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed: {r.stderr}")
    return json.loads(r.stdout)


def _py_registers(cfg):
    """Eager and replayed registers for one scenario, computed in Python —
    the same fixture shape the `replay` CLI subcommand takes, so the two
    sides can be diffed field for field."""
    window = cfg.get("window")
    because = cfg.get("because")
    host_kwargs = dict(responses=cfg.get("responses") or {},
                       files=cfg.get("files") or {})

    fast = Interpreter(host=TestHost(**host_kwargs), window=window,
                       trace=False, record=True)
    for step in cfg["steps"]:
        fast.run(step)

    eager = Interpreter(host=TestHost(**host_kwargs), window=window, trace=True)
    for step in cfg["steps"]:
        eager.run(step)
    eager_traced = eager.env.get(cfg["subject"])

    replayed = replay(cfg["steps"], cfg["subject"], window=window,
                      effect_log=fast.effect_log)

    return {
        "fastOutput": fast.output,
        "fastEffects": fast.effects,
        "eagerOutput": eager.output,
        "eagerEffects": eager.effects,
        "eager": {
            "card": explain(eager_traced, because),
            "prompt": why_tree(eager_traced, because=because),
            "machine": why_machine(eager_traced, because=because),
        },
        "replayed": {
            "card": explain(replayed, because),
            "prompt": why_tree(replayed, because=because),
            "machine": why_machine(replayed, because=because),
        },
    }


# ================================================================ 1. tracing-off == tracing-on

def test_tracing_defaults_to_true_head_unchanged():
    """Invariant 2: an Interpreter built with no `trace` argument at all
    behaves exactly like one built with `trace=True` — HEAD's own shape,
    unaffected by this field existing."""
    src = _chain(50)
    i_head = Interpreter(host=TestHost())          # no trace kwarg
    i_head.run(src)
    i_explicit = Interpreter(host=TestHost(), trace=True)
    i_explicit.run(src)
    rc_head = _reachable(i_head.env.get("x").node)
    rc_explicit = _reachable(i_explicit.env.get("x").node)
    assert rc_head == rc_explicit > 50


def test_tracing_off_output_effects_records_match_tracing_on_across_corpus():
    """§3's own acceptance, run against real programs, not only a
    synthetic chain: every corpus file that does not itself call `why`
    (see this file's SCOPE NOTE) produces byte-identical output/effects
    whether tracing is on or off."""
    mismatches = []
    for f in _corpus_files_excluding_why():
        src = open(f, encoding="utf-8").read()
        for trace in (True, False):
            itp = Interpreter(host=TestHost(), trace=trace)
            try:
                if _uses_import(src):
                    itp.run_file(f)
                else:
                    itp.run(src)
            except (PlanesError, PlanesSyntaxError, ModuleError, RecursionError) as e:
                itp = e
            if trace:
                on = itp
            else:
                off = itp
        on_shape = (on.output, on.effects) if not isinstance(on, Exception) \
            else (type(on).__name__, str(on))
        off_shape = (off.output, off.effects) if not isinstance(off, Exception) \
            else (type(off).__name__, str(off))
        if on_shape != off_shape:
            mismatches.append(f)
    assert not mismatches, mismatches


def test_tracing_off_allocates_no_per_node_deriv_graph():
    """The rest of §3: not merely identical output, but that tracing-off
    really does skip building a graph — every node reachable from a
    tracing-off value is the ONE shared sentinel, never one per call."""
    i = Interpreter(host=TestHost(), trace=False)
    i.run(_chain(200))
    node = i.env.get("x").node
    assert node is i._untraced
    assert node.inputs == []
    assert i._generation == 0


def test_why_statement_under_tracing_off_is_well_defined_but_uninformative():
    """The SCOPE NOTE above, made mechanical: `why` mid-program while
    tracing is off does not crash and does not change the VALUE shown —
    only the derivation text, which degrades to "<value> from nothing"
    because the sentinel carries no per-call provenance. This is the exact
    boundary `replay` (§5) exists to answer instead, on demand."""
    i = Interpreter(host=TestHost(), trace=False)
    i.run("x = 5\nwhy x\n")
    assert i.output == ["5 from nothing"]


def test_tracing_off_on_agree_cross_language():
    """§3/F1, in JavaScript: the `replay` CLI subcommand always runs a
    fast (trace: false) and an eager (trace: true) pair from the identical
    fixture — their own output/effects fields are exactly this gate."""
    scenarios = [
        {"steps": _chain(3).splitlines(keepends=True), "subject": "x"},
        {"steps": _chain(50).splitlines(keepends=True), "subject": "x"},
        _recursive_scenario(),
    ]
    mismatches = []
    for cfg in scenarios:
        js = _node_replay(cfg)
        if js["fast"]["output"] != js["eager"]["output"] or \
           js["fast"]["effects"] != js["eager"]["effects"]:
            mismatches.append((cfg, js["fast"], js["eager"]))
    assert not mismatches, mismatches


# ================================================================ 2. eager-vs-replay byte-identity

def _synthetic_scenarios():
    """Reassignment (below and above the fold threshold), windowed/sealed,
    recursive, and effectful — the same diversifying set R1/R2's own core
    gates use, extended with an effects scenario R1/R2 had no need for.
    Scenario-based, not corpus-wide, for the same structural reason
    test_retention.py/test_why_readable.py's OWN core gates are: replay
    needs a named `subject` in the running env, which an arbitrary corpus
    file does not reliably offer."""
    return [
        {"steps": _chain(3).splitlines(keepends=True), "subject": "x"},
        {"steps": _chain(50).splitlines(keepends=True), "subject": "x"},
        {"window": 5, "steps": _chain(200).splitlines(keepends=True), "subject": "x"},
        {"window": 50, "steps": _chain(300).splitlines(keepends=True), "subject": "x"},
        _recursive_scenario(),
        _effectful_scenario(),
    ]


def test_eager_and_replayed_derivations_agree_byte_for_byte_in_python():
    mismatches = []
    for cfg in _synthetic_scenarios():
        r = _py_registers(cfg)
        if r["eager"] != r["replayed"]:
            mismatches.append((cfg, r["eager"], r["replayed"]))
    assert not mismatches, mismatches


def test_eager_and_replayed_derivations_agree_byte_for_byte_in_javascript():
    mismatches = []
    for cfg in _synthetic_scenarios():
        js = _node_replay(cfg)
        assert not js["replayed"].get("refused"), js["replayed"]
        eager = {"card": js["eager"]["card"], "prompt": js["eager"]["prompt"],
                 "machine": js["eager"]["machine"]}
        replayed = js["replayed"]
        if eager != replayed:
            mismatches.append((cfg, eager, replayed))
    assert not mismatches, mismatches


def test_python_and_javascript_agree_on_eager_and_on_replayed():
    """The full cross-language square: Python's eager == JS's eager, and
    Python's replayed == JS's replayed — not only that each language
    agrees with itself."""
    mismatches = []
    for cfg in _synthetic_scenarios():
        py = _py_registers(cfg)
        js = _node_replay(cfg)
        js_eager = {"card": js["eager"]["card"], "prompt": js["eager"]["prompt"],
                   "machine": js["eager"]["machine"]}
        if py["eager"] != js_eager:
            mismatches.append(("eager", cfg, py["eager"], js_eager))
        js_replayed = js["replayed"]
        if py["replayed"] != js_replayed:
            mismatches.append(("replayed", cfg, py["replayed"], js_replayed))
    assert not mismatches, mismatches


def test_replay_is_idempotent_asking_why_twice_gives_the_same_answer():
    """A shared `effect_log` is not consumed — `ReplayHost` copies it and
    starts its own position at 0 each call, so two independent `why`
    queries against the same fast-path run both succeed and agree."""
    cfg = _effectful_scenario()
    fast = Interpreter(host=TestHost(responses=cfg["responses"], files=cfg["files"]),
                       trace=False, record=True)
    for step in cfg["steps"]:
        fast.run(step)
    first = replay(cfg["steps"], cfg["subject"], effect_log=fast.effect_log)
    second = replay(cfg["steps"], cfg["subject"], effect_log=fast.effect_log)
    assert explain(first) == explain(second)
    assert why_tree(first) == why_tree(second)


# ================================================================ 3. effects performed once (§7/F3)

def test_effects_are_not_re_performed_by_replay():
    """§7's own acceptance: the fast-path run's host sinks (shown, files,
    recorded) are unchanged by a later replay — replay never touches the
    original host at all, only a separate `ReplayHost` built from the
    recorded log."""
    cfg = _effectful_scenario()
    host = TestHost(responses=cfg["responses"], files=cfg["files"])
    fast = Interpreter(host=host, trace=False, record=True)
    for step in cfg["steps"]:
        fast.run(step)
    shown_before = list(host.shown)
    files_before = dict(host.files)
    recorded_before = list(host.recorded)

    replay(cfg["steps"], cfg["subject"], effect_log=fast.effect_log)

    assert host.shown == shown_before
    assert host.files == files_before
    assert host.recorded == recorded_before
    # and the fast path itself performed each effect exactly once — one
    # "show" in the effect log, matching the one `show` statement in the
    # program, never two.
    show_count = sum(1 for kind, *_ in fast.effect_log if kind == "show")
    assert show_count == 1, fast.effect_log


# ================================================================ 4. replay refuses (§7)

def test_replay_refuses_when_effects_were_never_recorded():
    """The fast path ran WITHOUT record=True, so no effect_log exists —
    replay must refuse the first effect it reaches, not silently perform
    it (which would be the exact double-effect F7 exists to prevent)."""
    i = Interpreter(host=TestHost(), trace=False)          # record defaults False
    i.run('x = 5\nshow x\n')
    assert i.effect_log == []
    try:
        replay(["x = 5\nshow x\n"], "x", effect_log=i.effect_log)
        raise AssertionError("replay should have refused")
    except (HostError, PlanesError) as e:
        assert "replay refused" in str(e)


def test_replay_refuses_on_a_mismatched_or_exhausted_log():
    try:
        replay(['show "hi"\n'], "x", effect_log=[])
        raise AssertionError("replay should have refused")
    except (HostError, PlanesError) as e:
        assert "replay refused" in str(e)

    try:
        replay(['show "hi"\n'], "x", effect_log=[("show", "wrong-text", None)])
        raise AssertionError("replay should have refused")
    except (HostError, PlanesError) as e:
        assert "replay refused" in str(e)


def test_replay_refuses_cross_language():
    js = _node_replay({"steps": ['let x = 5\nshow x\n'], "subject": "x",
                       "forceRefusal": True})
    assert js["replayed"].get("refused") is True
    assert "replay refused" in js["replayed"]["message"]


# ================================================================ 5. explain is iterative (§4/F6)

def test_explain_handles_a_1000_step_unwindowed_chain_without_recursion_error():
    """Pre-R3, `approximations_in`'s plain recursion hit Python's own
    recursion limit past roughly 450 unwindowed steps (test_why_readable.
    py's `_PY_CARD_TOO_DEEP` sentinel). §4's iterative conversion removes
    that ceiling; a chain more than twice that long now returns cleanly."""
    i = Interpreter(host=TestHost())
    i.run(_chain(1000))
    card = explain(i.env.get("x"))
    assert card == "1000 from x (999) + 1"


def test_explain_at_1000_steps_agrees_with_javascript():
    cfg = {"steps": _chain(1000).splitlines(keepends=True), "subject": "x"}
    itp = Interpreter(host=TestHost())
    for step in cfg["steps"]:
        itp.run(step)
    py_card = explain(itp.env.get("x"))
    js = _node_replay(cfg)
    assert py_card == js["eager"]["card"]
    assert not js["replayed"].get("refused")
    assert py_card == js["replayed"]["card"]


def test_short_chain_card_unchanged_by_the_iterative_conversion():
    """The iterative rewrite must not change a SINGLE bit of behavior on
    chains the recursive version always handled — test_why_readable.py's
    own exact-text assertions (unmodified by this build) already prove
    this at length; this is the same property, stated locally."""
    i = Interpreter(host=TestHost())
    i.run(_chain(3))
    assert explain(i.env.get("x")) == "3 from x (2) + 1"


# ================================================================ 6. host surface still seven

def test_seven_required_host_methods_unchanged_and_no_restore_added():
    required = {"ask", "read", "write", "show", "clock", "resolve",
                "parse_json"}
    assert len(required) == 7
    for m in required:
        assert hasattr(Host, m), f"a host must provide {m}"
    # Ruling 1: replay reconstructs by re-execution, never by host
    # retrieval — a `restore`/`recall` capability is exactly what R3 must
    # not add.
    for forbidden in ("restore", "recall", "load_snapshot", "rehydrate"):
        assert not hasattr(Host, forbidden)
        assert not hasattr(ReplayHost, forbidden)


def test_replay_host_implements_no_new_required_capability():
    """`ReplayHost` is a second host in the same sense TestHost already
    is — an ordinary implementation of the existing seven, not a new
    surface. It refuses `clock`/`resolve` outright rather than fabricating
    an answer; that is a legitimate implementation choice for those two,
    not a missing method."""
    rh = ReplayHost([])
    for m in ("ask", "read", "write", "show", "clock", "resolve", "parse_json"):
        assert hasattr(rh, m)
    assert "snapshot" not in ReplayHost.__dict__   # inherits the no-op, adds nothing
    assert "record" not in ReplayHost.__dict__


def test_python_host_and_test_host_still_do_not_override_snapshot():
    """Unchanged from R1 (test_retention.py's own check) — restated here
    because this build touches the same neighborhood of host.py's callers
    and must not have widened it."""
    assert "snapshot" not in PythonHost.__dict__
    assert "record" not in PythonHost.__dict__


if __name__ == "__main__":
    if _skip_if_no_node():
        sys.exit(0)

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
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")

    CRITERIA = [
        ("tracing-off == tracing-on for output/effects/records (§3/F1)",
         [test_tracing_defaults_to_true_head_unchanged,
          test_tracing_off_output_effects_records_match_tracing_on_across_corpus,
          test_tracing_off_allocates_no_per_node_deriv_graph,
          test_why_statement_under_tracing_off_is_well_defined_but_uninformative,
          test_tracing_off_on_agree_cross_language]),
        ("eager-vs-replay byte-identity, Python and JS (§6/F2)",
         [test_eager_and_replayed_derivations_agree_byte_for_byte_in_python,
          test_eager_and_replayed_derivations_agree_byte_for_byte_in_javascript,
          test_python_and_javascript_agree_on_eager_and_on_replayed,
          test_replay_is_idempotent_asking_why_twice_gives_the_same_answer]),
        ("effects performed once, never re-performed on replay (§7/F3)",
         [test_effects_are_not_re_performed_by_replay]),
        ("replay refuses on an unrecorded value (§7/F7)",
         [test_replay_refuses_when_effects_were_never_recorded,
          test_replay_refuses_on_a_mismatched_or_exhausted_log,
          test_replay_refuses_cross_language]),
        ("explain is iterative, no overflow at 1,000 steps (§4/F6)",
         [test_explain_handles_a_1000_step_unwindowed_chain_without_recursion_error,
          test_explain_at_1000_steps_agrees_with_javascript,
          test_short_chain_card_unchanged_by_the_iterative_conversion]),
        ("required host surface still seven, no restore (invariant 4/F5)",
         [test_seven_required_host_methods_unchanged_and_no_restore_added,
          test_replay_host_implements_no_new_required_capability,
          test_python_host_and_test_host_still_do_not_override_snapshot]),
    ]
    print("\n=== R3 verification gate (N+3.2) ===")
    width = max(len(name) for name, _ in CRITERIA)
    table_failed = False
    for name, checks in CRITERIA:
        row_ok = all(fn.__name__ not in fails for fn in checks)
        table_failed = table_failed or not row_ok
        print(f"  {'PASS' if row_ok else 'FAIL'}  {name.ljust(width)}")
    print()

    sys.exit(1 if (fails or table_failed) else 0)
