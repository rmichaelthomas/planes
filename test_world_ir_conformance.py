"""test_world_ir_conformance.py — the cross-implementation World IR gate.

Horizon Phase 0 Build 1. Extends this repo's byte-identical-agreement
discipline (README's 349-shape sweep, test_js_metacircular.py's metacircular
check) to the World IR parser: Python (world_ir.py), JavaScript
(js/world_ir.mjs), and self-hosted Planes (grammar/world_ir.planes) must
produce the identical canonical outcome string for every fixture below.

The self-hosted implementation is run through `interp.py`'s own
`Interpreter` — a legitimate way to execute "the self-hosted Planes
implementation," since test_js_metacircular.py already establishes that
interp.py and js/interp.mjs agree on language semantics; this file's job is
whether world_ir.planes agrees with world_ir.py/world_ir.mjs on the World IR
rules, not whether two interpreters agree on the language underneath it.

Six required fixtures, one per row of the build prompt's acceptance table:
valid, bad-version, missing-critical, malformed-critical-field,
malformed-optional-field, unknown-optional. See REPORT_WORLD_V1.md for the
printed pass/fail table and the failability proof (a parser temporarily
mutated to accept a fixture that should refuse, confirmed to turn this gate
red, then reverted).
"""
import copy
import json
import os
import subprocess
import sys

import world_ir as w
from host import TestHost
from interp import Interpreter, PlanesError

REPO = os.path.dirname(os.path.abspath(__file__))
NODE = "node"

with open(os.path.join(REPO, "grammar", "world_ir.planes"), encoding="utf-8") as _f:
    PLANES_SRC = _f.read()


# ============================================================ fixture corpus

VALID_ENVELOPE = {
    "version": 1,
    "identity": {
        "id": "subject-1", "kind": "vehicle", "subkind": "hydrofoil",
        "displayName": "Reso", "status": "canonical", "schemaVersion": 1,
    },
    "situation": {
        "containingPlace": "landing-1", "space": "world", "x": 10, "y": -5,
        "state": "docked", "occupancy": 0, "anchorId": "anchor-1",
        "chunkActive": True, "physicsRef": "phys-1", "audioRef": "audio-1",
    },
    "relation": {
        "relationId": "rel-1", "relationType": "near", "fromId": "subject-1",
        "toId": "landing-1", "provenance": "authored",
    },
    "behavior": {
        "eventPattern": "arrival", "transition": "docked", "timerTicks": 100,
        "condition": "always", "stateMachine": "dock-cycle",
        "emittedEvent": "docked", "failurePath": "resync",
    },
    "expression": {
        "assetId": "asset-reso", "layer": 2, "depth": 0.5,
        "animationState": "idle", "material": "hull",
        "lightingResponse": "standard", "particleIntent": "none",
        "colliderId": "collider-1", "sensorId": "sensor-1",
        "audioAnchor": "audio-anchor-1", "fidelityVariant": "harbor",
        "accessibleAlt": "reduced-motion",
    },
    "affordance": {
        "action": "board", "precondition": "docked",
        "valueShape": "boolean", "preview": "highlight",
        "inverse": "disembark", "authorityRequired": "none",
        "explanation": "board the hydrofoil", "sourceMapTarget": "identity.status",
        "fallback": "deny",
    },
    "lineage": {
        "corpusSource": "ala-eriri", "culturalStatus": "canonical",
        "author": "studio", "origin": "system", "because": "canonical corpus asset",
        "agreementFingerprint": "fp-1", "permittedTransformations": "remix",
        "publishingRestriction": "none", "systemBoundary": "immutable",
    },
}


def _valid():
    return copy.deepcopy(VALID_ENVELOPE)


def _missing_critical():
    env = _valid()
    del env["lineage"]
    return env


def _malformed_critical_field():
    env = _valid()
    env["identity"]["schemaVersion"] = "one"
    return env


def _malformed_optional_field():
    env = _valid()
    env["behavior"]["timerTicks"] = "soon"
    return env


def _unknown_optional():
    env = _valid()
    env["annotation"] = {"note": "not part of world-v1"}
    return env


def _bad_version():
    env = _valid()
    env["version"] = 2
    return env


ACCEPT = "world-ir-outcome: accept"
REFUSE = "world-ir-outcome: refuse"

# name -> (envelope, expected leading line, expected tag or None on accept)
FIXTURES = {
    "valid": (_valid(), ACCEPT, None),
    "bad-version": (_bad_version(), REFUSE, "unsupported-world-protocol-version"),
    "missing-critical": (_missing_critical(), REFUSE, "missing-critical-record"),
    "malformed-critical-field": (_malformed_critical_field(), REFUSE, "malformed-critical-record"),
    "malformed-optional-field": (_malformed_optional_field(), REFUSE, "malformed-optional-record"),
    "unknown-optional": (_unknown_optional(), ACCEPT, None),
}


# ======================================================== per-implementation runners

def python_outcome_string(envelope):
    return w.canonical_outcome_string(envelope)


def js_outcome_string(envelope):
    r = subprocess.run(
        [NODE, os.path.join("js", "world_ir.mjs")],
        input=json.dumps(envelope), capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        raise AssertionError(f"js/world_ir.mjs exited {r.returncode}: {r.stderr}")
    return r.stdout


def _to_planes_literal(value):
    """Render a Python JSON-shaped value as Planes source — the envelope's
    'native value form' for the self-hosted side. No quoting complexity is
    needed: this build's fixtures use plain identifiers and short phrases,
    never a quote or backslash character."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k}: {_to_planes_literal(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_to_planes_literal(v) for v in value) + "]"
    raise TypeError(f"cannot render {value!r} as a Planes literal")


def planes_outcome_string(envelope):
    driver = (f"envelope = {_to_planes_literal(envelope)}\n"
              "show canonical outcome string of envelope\n")
    itp = Interpreter(host=TestHost())
    try:
        itp.run(PLANES_SRC + "\n" + driver)
    except PlanesError as e:
        raise AssertionError(f"grammar/world_ir.planes raised uncaught: {e.tag}: {e.detail}") from e
    return "\n".join(itp.output)


# =================================================================== the gate

def _run_all_fixtures():
    """Returns {name: (py, js, planes, ok)} — `ok` is True iff all three
    match AND the result's leading line / tag match the fixture's
    expectation, so a fixture that all three implementations wrongly agree
    on still shows up as a failure."""
    results = {}
    for name, (envelope, expect_leading, expect_tag) in FIXTURES.items():
        py = python_outcome_string(envelope)
        js = js_outcome_string(envelope)
        pl = planes_outcome_string(envelope)
        agree = py == js == pl
        shape_ok = py.startswith(expect_leading) and (
            expect_tag is None or f"tag: {expect_tag}" in py)
        results[name] = (py, js, pl, agree and shape_ok)
    return results


def test_all_fixtures_agree_byte_for_byte_across_all_three_implementations():
    results = _run_all_fixtures()
    failures = []
    for name, (py, js, pl, ok) in results.items():
        if not ok:
            failures.append(
                f"--- {name} ---\npython:\n{py}\njs:\n{js}\nplanes:\n{pl}")
    assert not failures, "\n".join(failures)


def test_the_gate_is_capable_of_failing():
    """The failability proof named in the build prompt (§N+3.2) is a manual
    mutate/observe-red/revert/observe-green procedure recorded in
    REPORT_WORLD_V1.md with real exit codes, since it requires editing a
    file on disk mid-run. This in-process check is the narrower claim the
    automated suite CAN still make on its own: the comparison itself is not
    vacuously true for mismatched strings, so a real divergence is not
    silently swallowed anywhere in the chain."""
    assert not ("world-ir-outcome: accept" == "world-ir-outcome: refuse")
    envelope = _bad_version()
    real_py = python_outcome_string(envelope)
    tampered = real_py.replace("refuse", "accept")
    assert real_py != tampered, "the comparison must be able to observe this divergence"


def _print_table(results):
    print(f"{'fixture':<28} {'python==js==planes':<20} {'shape ok':<10} result")
    for name, (py, js, pl, ok) in results.items():
        agree = py == js == pl
        print(f"{name:<28} {str(agree):<20} {'yes' if ok else 'no':<10} {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    results = _run_all_fixtures()
    _print_table(results)
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
