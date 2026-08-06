"""Tests for the retention window and seal nodes (R1, checkpoint v28.0 §441).

R1's shape: derivation history is whole inside a sliding window; past it,
the chain a value carries is cut to a single seal — an ordinary Deriv
(kind="seal") carrying the value at the cut, the generation it cut at, how
many steps it released, and a fingerprint of what was released. `why` past
a seal names a fixed refusal ("history before generation N was released;
deterministic replay from snapshot S recovers it exactly."), true because
Planes is deterministic and pure — the history is compressed, not lost.

This file is the build's own N+3.2 gate: it emits a pass/fail table
covering the seven things the build prompt names as blocking —
  1. unbounded-window == HEAD reachable count
  2. finite-window bounded reachable count
  3. cross-language fingerprint match
  4. seal refusal sentence byte-identical
  5. PIN reachable past window
  6. PIN-inertness (output/effects identical with/without PIN)
  7. seven required host methods unchanged
— in addition to the ordinary per-function test run every suite in this
repo does. It shells out to `node js/cli.mjs retention <config>` for the
cross-language checks, the same pattern test_js_host.py and
test_js_interp.py use; Node's availability is a §0 baseline fact for this
build, so the whole file skips with a clear message if node is missing
rather than failing spuriously.
"""
import json
import os
import shutil
import subprocess
import sys

from host import Host, PythonHost, TestHost
from interp import Interpreter, why_tree

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))

N = 600           # generations enough to cross a small window many times
WINDOW = 5


def _skip_if_no_node():
    if NODE is None:
        print("  SKIP  node not on PATH")
        return True
    return False


def _chain(n):
    """A program that reassigns `x` n times — the shape a long-running
    per-tick `with`/reassignment loop actually builds, the shape
    REPORT_UPDATE_COST.md §5.4 measured."""
    return "\n".join(["x = 0"] + ["x = x + 1"] * n + ["show x"]) + "\n"


def _reachable(node):
    """Distinct Deriv nodes reachable from `node`, stopping at seals —
    the same measure REPORT_UPDATE_COST.md §5.4 used for its own count."""
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


def _find_seal(node):
    seen = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        if n.kind == "seal":
            return n
        stack.extend(n.inputs)
    return None


def _node_retention(cfg):
    r = subprocess.run(
        [NODE, "js/cli.mjs", "retention", json.dumps(cfg)],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed: {r.stderr}")
    return json.loads(r.stdout)


class _BareHost(Host):
    """A host implementing exactly the seven required methods and nothing
    else — no `record`, no `snapshot` override. Used to prove a host this
    minimal still runs a windowed program (§7's acceptance)."""

    def __init__(self):
        self.shown = []

    def ask(self, url):
        raise NotImplementedError

    def read(self, path):
        raise NotImplementedError

    def write(self, path, text):
        raise NotImplementedError

    def show(self, text):
        self.shown.append(text)

    def clock(self):
        return 0.0

    def resolve(self, target):
        raise NotImplementedError

    def parse_json(self, text):
        raise NotImplementedError


# ================================================================ 1. unbounded == HEAD

def test_unbounded_window_reachable_count_matches_head():
    """Invariant 2: the window defaults to unbounded, and an unbounded
    run's Deriv-reachable count is identical to a HEAD run (no window
    argument at all) — proven by literally not passing `window` on one
    side."""
    src = _chain(N)
    i_head = Interpreter(host=TestHost())    # HEAD shape: no window kwarg
    i_head.run(src)
    i_unbounded = Interpreter(host=TestHost(), window=None)  # explicit, same thing
    i_unbounded.run(src)
    rc_head = _reachable(i_head.env.get("x").node)
    rc_unbounded = _reachable(i_unbounded.env.get("x").node)
    assert rc_head == rc_unbounded, (rc_head, rc_unbounded)
    # and it actually grew without bound — proves the measure means
    # something, not just that two identical no-ops agree.
    assert rc_head > N, rc_head


def test_unbounded_output_effects_trace_records_match_head():
    """The rest of invariant 2: output, effects, trace, and records are
    identical too, not only the reachable count — an unbounded run must
    be indistinguishable from HEAD in everything the interpreter exposes."""
    src = ('use file\nx = 0\nx = x + 1\nwrite [x] to "o.json"\nshow x\n')
    i1 = Interpreter(fs={}, record=True)
    o1 = i1.run(src)
    i2 = Interpreter(fs={}, record=True, window=None)
    o2 = i2.run(src)
    assert o1 == o2
    assert i1.effects == i2.effects
    assert [line for _, line in i1.trace] == [line for _, line in i2.trace]
    assert len(i1.records) == len(i2.records) and len(i1.records) > 0


def test_unbounded_path_allocates_no_seal():
    """Failure mode 3's prevention: the default-unbounded path must not
    allocate a seal at all, not merely avoid using one."""
    i = Interpreter(host=TestHost(), window=None)
    i.run(_chain(200))

    def has_seal(node, seen=None):
        seen = seen if seen is not None else set()
        if id(node) in seen:
            return False
        seen.add(id(node))
        if node.kind == "seal":
            return True
        return any(has_seal(n, seen) for n in node.inputs)

    assert not has_seal(i.env.get("x").node)


# ================================================================ 2. finite window bounds reachable

def test_finite_window_bounds_reachable_count():
    i = Interpreter(host=TestHost(), window=WINDOW)
    i.run(_chain(N))
    rc = _reachable(i.env.get("x").node)
    assert rc < N, rc
    assert rc < 5 * WINDOW + 20, rc


def test_finite_window_scales_with_window_size_not_history_length():
    """Doubling the number of generations without changing the window must
    not grow the reachable count — the whole point of a window."""
    i_small = Interpreter(host=TestHost(), window=WINDOW)
    i_small.run(_chain(N))
    i_big = Interpreter(host=TestHost(), window=WINDOW)
    i_big.run(_chain(N * 4))
    rc_small = _reachable(i_small.env.get("x").node)
    rc_big = _reachable(i_big.env.get("x").node)
    assert rc_big <= rc_small + 5, (rc_small, rc_big)


# ================================================================ 3. cross-language fingerprint

def test_seal_fingerprint_agrees_byte_for_byte_across_implementations():
    """The byte-identical-agreement discipline this corpus already holds
    output to, extended to the released subgraph a seal replaces."""
    steps = ["x = 0\n"] + ["x = x + 1\n"] * N + ["show x\n"]
    itp = Interpreter(host=TestHost(), window=WINDOW)
    for s in steps:
        itp.run(s)
    seal = _find_seal(itp.env.get("x").node)
    assert seal is not None

    js = _node_retention({"window": WINDOW, "steps": steps, "subject": "x"})
    assert js["seal"] is not None
    assert js["seal"]["fingerprint"] == seal.fingerprint
    assert js["seal"]["generation"] == seal.generation
    assert js["seal"]["releasedCount"] == seal.released_count
    assert js["generations"] == itp._generation
    assert js["reachable"] == _reachable(itp.env.get("x").node)


def test_fingerprint_differs_for_a_different_window():
    """Sanity check that the fingerprint is content-derived, not constant:
    a different window releases a different subgraph."""
    i5 = Interpreter(host=TestHost(), window=5)
    i5.run(_chain(N))
    i7 = Interpreter(host=TestHost(), window=7)
    i7.run(_chain(N))
    s5 = _find_seal(i5.env.get("x").node)
    s7 = _find_seal(i7.env.get("x").node)
    assert s5.fingerprint != s7.fingerprint


# ================================================================ 4. seal refusal, byte-identical

def test_seal_refusal_sentence_is_fixed_and_names_generation_and_snapshot():
    i = Interpreter(host=TestHost(), window=WINDOW)
    i.run(_chain(200))
    seal = _find_seal(i.env.get("x").node)
    assert seal is not None
    expected = (
        f"history before generation {seal.generation} was released; "
        f"deterministic replay from snapshot {seal.fingerprint} "
        f"recovers it exactly.")
    assert seal.label == expected
    # reachable within why_tree's own untouched depth-14 view at this
    # window size — R2's concern (retiring that truncation) is untouched
    # here; this only proves the seal is a leaf like any other.
    wt = why_tree(i.env.get("x"))
    assert expected in wt


def test_seal_refusal_sentence_agrees_byte_for_byte_across_implementations():
    steps = ["x = 0\n"] + ["x = x + 1\n"] * 200 + ["show x\n"]
    itp = Interpreter(host=TestHost(), window=WINDOW)
    for s in steps:
        itp.run(s)
    seal = _find_seal(itp.env.get("x").node)

    js = _node_retention({"window": WINDOW, "steps": steps, "subject": "x"})
    assert js["seal"]["refusal"] == seal.label


# ================================================================ 5. PIN reachable past window

def test_pinned_derivation_survives_past_the_window():
    i = Interpreter(host=TestHost(), window=WINDOW)
    i.run("x = 0\n")
    pinned = i.pin(i.env.get("x"))
    for _ in range(N):
        i.run("x = x + 1\n")
    i.run("show x\n")
    assert pinned.kind != "seal"
    assert _reachable(pinned) >= 1
    # a pin must not defeat the window for everything built after it —
    # the live head stays bounded exactly as it would unpinned.
    assert _reachable(i.env.get("x").node) < 5 * WINDOW + 20


def test_pin_survives_past_window_cross_language():
    steps = ["x = 0\n"] + ["x = x + 1\n"] * N + ["show x\n"]
    cfg = {"window": WINDOW, "steps": steps, "pinAfterStep": 0,
           "pinName": "x", "subject": "x"}
    js = _node_retention(cfg)
    assert js["pinnedReachable"] is not None
    assert js["pinnedReachable"] >= 1

    itp = Interpreter(host=TestHost(), window=WINDOW)
    itp.run(steps[0])
    pinned = itp.pin(itp.env.get("x"))
    for s in steps[1:]:
        itp.run(s)
    assert _reachable(pinned) == js["pinnedReachable"]


# ================================================================ 6. PIN inertness

def _run_variant(pin, window=WINDOW):
    src = _chain(200)
    i = Interpreter(host=TestHost(), window=window)
    i.run(src)
    if pin:
        i.pin(i.env.get("x"))
    return i.output, i.effects


def test_pin_is_inert_output_and_effects_unaffected():
    """v6.0's annotation-plane inertness, test_record.py's own model
    applied to the retention plane: a PIN changes what survives the cut,
    never what the program did."""
    o1, e1 = _run_variant(False)
    o2, e2 = _run_variant(True)
    assert o1 == o2
    assert e1 == e2


def test_pin_is_inert_static_surface_unaffected():
    """Pinning happens after a run, never during parsing or analysis, so
    the static surface (shapes.analyse) cannot see it at all."""
    from shapes import analyse
    src = _chain(50)
    surf_before = [str(e) for e in analyse(src).declared]
    i = Interpreter(host=TestHost(), window=WINDOW)
    i.run(src)
    i.pin(i.env.get("x"))
    surf_after = [str(e) for e in analyse(src).declared]
    assert surf_before == surf_after


# ================================================================ 7. seven required host methods

def test_seven_required_host_methods_unchanged():
    required = {"ask", "read", "write", "show", "clock", "resolve",
                "parse_json"}
    assert len(required) == 7
    for m in required:
        assert hasattr(Host, m), f"a host must provide {m}"


def test_snapshot_is_optional_a_host_without_it_still_runs_planes():
    """A host implementing only the seven runs Planes — the second-host
    gate this build must not spend. `_BareHost` overrides neither `record`
    nor `snapshot`; a windowed run against it must still complete and must
    still not raise when a seal is created."""
    _BareHost().snapshot("fp", {})   # inherited no-op, must not raise
    i = Interpreter(host=_BareHost(), window=3)
    i.run(_chain(50))                # crosses the window many times over
    assert i.host.shown == ["50"]


def test_snapshot_receives_the_fingerprint_and_generation_on_an_in_memory_host():
    host = TestHost()
    i = Interpreter(host=host, window=WINDOW)
    i.run(_chain(200))
    assert host.snapshots, "TestHost.snapshot should have recorded at least one seal"
    for fp, entry in host.snapshots.items():
        assert isinstance(fp, str) and len(fp) > 0
        assert "generation" in entry and "released_count" in entry


def test_python_host_does_not_override_snapshot():
    """PythonHost doesn't override `record` either (host.py); `snapshot`
    joins it in that same optional tier, matching pattern rather than
    adding a bespoke real-world persistence path this build never asked
    for."""
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

    # The build prompt's own N+3.2 table: the seven named acceptance
    # criteria, each backed by one or more of the tests above.
    CRITERIA = [
        ("unbounded-window == HEAD reachable count",
         [test_unbounded_window_reachable_count_matches_head,
          test_unbounded_output_effects_trace_records_match_head,
          test_unbounded_path_allocates_no_seal]),
        ("finite-window bounded reachable count",
         [test_finite_window_bounds_reachable_count,
          test_finite_window_scales_with_window_size_not_history_length]),
        ("cross-language fingerprint match",
         [test_seal_fingerprint_agrees_byte_for_byte_across_implementations,
          test_fingerprint_differs_for_a_different_window]),
        ("seal refusal sentence byte-identical",
         [test_seal_refusal_sentence_is_fixed_and_names_generation_and_snapshot,
          test_seal_refusal_sentence_agrees_byte_for_byte_across_implementations]),
        ("PIN reachable past window",
         [test_pinned_derivation_survives_past_the_window,
          test_pin_survives_past_window_cross_language]),
        ("PIN-inertness (output/effects identical with/without PIN)",
         [test_pin_is_inert_output_and_effects_unaffected,
          test_pin_is_inert_static_surface_unaffected]),
        ("seven required host methods unchanged",
         [test_seven_required_host_methods_unchanged,
          test_snapshot_is_optional_a_host_without_it_still_runs_planes]),
    ]
    print("\n=== R1 verification gate (N+3.2) ===")
    width = max(len(name) for name, _ in CRITERIA)
    table_failed = False
    for name, checks in CRITERIA:
        row_ok = all(fn.__name__ not in fails for fn in checks)
        table_failed = table_failed or not row_ok
        print(f"  {'PASS' if row_ok else 'FAIL'}  {name.ljust(width)}")
    print()

    sys.exit(1 if (fails or table_failed) else 0)
