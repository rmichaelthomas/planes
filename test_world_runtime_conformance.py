"""test_world_runtime_conformance.py — cross-implementation gate for Build 2.

Extends test_world_ir_conformance.py's byte-identical-agreement discipline
(Build 1) from hand-fed envelope dicts to envelopes an actual RUNNING
program emits: Python (interp.py + world_ir.py) and JavaScript
(js/interp.mjs + js/world_ir.mjs) must produce the identical canonical
outcome string for world_runtime_demo.planes's own emission (Phase 1)
and for every tick world_runtime.py / js/world_runtime.mjs advances through
(Phase 3).

Self-hosted Planes emission is explicitly OUT OF REACH this build (build
prompt failure mode S2): Build 1's self-hosted parser (grammar/world_ir.planes)
validates an envelope handed to it, but nothing in this build wires a
self-hosted mirror of `Show`'s emission hook — doing so would mean editing
grammar/interp.planes's own evaluator, which is not part of this build's file
inventory and is a materially larger, separate piece of work. This gate
therefore covers Python and JS only; self-hosted emission is named here, in
the open, as its own follow-on rather than left silently uncovered — see
`test_self_hosted_emission_is_a_named_follow_on_not_a_silent_gap` below and
reports/REPORT_WORLD_RUNTIME.md.
"""
import json
import os
import subprocess
import sys

import world_ir as w
from host import TestHost
from interp import Interpreter, to_host
from world_runtime import WorldRuntime

REPO = os.path.dirname(os.path.abspath(__file__))
NODE = "node"
DEMO = "world_runtime_demo.planes"
TICK_COUNT = 5
DELIM = "\n===TICK===\n"


# ======================================================== Phase 1: one emission

def python_demo_emission_outcome():
    itp = Interpreter(host=TestHost())
    itp.run_file(DEMO)
    assert len(itp.world_envelopes) == 1
    return w.canonical_outcome_string(itp.world_envelopes[0].raw)


_JS_EMISSION_SCRIPT = """
import { Interpreter } from "./js/interp.mjs";
import { runFile } from "./js/run_file.mjs";
import { canonicalOutcomeString } from "./js/world_ir.mjs";
import { emitWorld } from "./js/world_emit_node.mjs";
import { loadGrammar } from "./js/loader_node.mjs";
import { TestHost } from "./js/host.mjs";

loadGrammar();
const itp = new Interpreter({ host: new TestHost(), emitWorld });
await runFile(itp, "world_runtime_demo.planes");
if (itp.worldEnvelopes.length !== 1) {
  throw new Error(`expected exactly 1 world envelope, got ${itp.worldEnvelopes.length}`);
}
process.stdout.write(canonicalOutcomeString(itp.worldEnvelopes[0].raw));
"""


def js_demo_emission_outcome():
    r = subprocess.run(
        [NODE, "--input-type=module", "-e", _JS_EMISSION_SCRIPT],
        capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        raise AssertionError(f"js emission script exited {r.returncode}: {r.stderr}")
    return r.stdout


def test_python_and_js_agree_on_the_demo_programs_emitted_envelope():
    py = python_demo_emission_outcome()
    js = js_demo_emission_outcome()
    assert py == js, f"--- python ---\n{py}\n--- js ---\n{js}"
    assert py.startswith("world-ir-outcome: accept")


# ================================================== Phase 3: per-tick agreement

def python_tick_outcomes(n=TICK_COUNT):
    rt = WorldRuntime(DEMO, host=TestHost())
    lines = [w.canonical_outcome_string(to_host(rt.init().value))]
    for _ in range(n):
        lines.append(w.canonical_outcome_string(to_host(rt.advance().value)))
    return DELIM.join(lines)


_JS_TICKS_SCRIPT = f"""
import {{ WorldRuntime }} from "./js/world_runtime.mjs";
import {{ canonicalOutcomeString }} from "./js/world_ir.mjs";
import {{ toHost }} from "./js/interp.mjs";
import {{ TestHost }} from "./js/host.mjs";

const rt = new WorldRuntime("world_runtime_demo.planes", {{ host: new TestHost() }});
await rt.load();
const lines = [canonicalOutcomeString(toHost(rt.init().value))];
for (let i = 0; i < {TICK_COUNT}; i++) {{
  lines.push(canonicalOutcomeString(toHost(rt.advance().value)));
}}
process.stdout.write(lines.join({json.dumps(DELIM)}));
"""


def js_tick_outcomes():
    r = subprocess.run(
        [NODE, "--input-type=module", "-e", _JS_TICKS_SCRIPT],
        capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        raise AssertionError(f"js ticks script exited {r.returncode}: {r.stderr}")
    return r.stdout


def test_python_and_js_agree_on_every_tick_of_a_persistent_run():
    py = python_tick_outcomes()
    js = js_tick_outcomes()
    py_ticks = py.split(DELIM)
    js_ticks = js.split(DELIM)
    assert len(py_ticks) == TICK_COUNT + 1
    assert len(js_ticks) == TICK_COUNT + 1
    for i, (p, j) in enumerate(zip(py_ticks, js_ticks)):
        assert p == j, f"tick {i} diverges:\n--- python ---\n{p}\n--- js ---\n{j}"
        assert f"situation.x: {i}" in p


# ================================================================= the gate

def test_the_gate_is_capable_of_failing():
    """The failability proof (build prompt §N+3.2), the same narrower
    in-process claim test_world_ir_conformance.py's own version makes: the
    comparison is not vacuously true for mismatched strings."""
    py = python_demo_emission_outcome()
    tampered = py.replace("wayfinder-1", "tampered-id")
    assert py != tampered, "the comparison must be able to observe this divergence"


def test_self_hosted_emission_is_a_named_follow_on_not_a_silent_gap():
    """S2: if self-hosted emission is out of reach this build, the gate
    says so explicitly rather than leaving it silently uncovered. Build 1's
    self-hosted VALIDATOR (grammar/world_ir.planes) is unaffected and still
    covered by test_world_ir_conformance.py; what this build does not add
    is a self-hosted EMITTER — a mirror of interp.py's/js/interp.mjs's Show
    case inside grammar/interp.planes itself, which is not in this build's
    file inventory (§2) and edits the self-hosted evaluator directly."""
    assert not os.path.exists(os.path.join(REPO, "grammar", "world_runtime.planes")), (
        "a self-hosted world_runtime.planes now exists — this test's own "
        "premise (self-hosted emission is a follow-on, not yet built) is "
        "stale; extend this conformance gate to a three-way comparison "
        "and update this test and the module docstring together")


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
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
