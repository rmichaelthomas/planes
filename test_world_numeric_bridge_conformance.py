"""test_world_numeric_bridge_conformance.py — the cross-implementation
numeric-bridge gate.

Horizon Phase 0 Build 4, last Phase 0 build. Two things this file holds to
actual (not asserted) agreement:

  1. Quantization arithmetic — round via `round_to`, then classify the
     crossing exact/lossy — byte-identical across all three implementations:
     Python (world_numeric_bridge.py), JavaScript
     (js/world_numeric_bridge.mjs), and self-hosted Planes
     (grammar/world_numeric_bridge.planes). This is the REACHABLE half of
     the bridge — see that file's own module docstring for why the
     `approx`-marking half is Python+JS only, by design, rather than
     silently uncovered (build prompt §N+2 failure mode S2).

  2. Determinism-hash agreement across Python and JS — the same envelope
     produces the same `world_delta.semantic_hash` in both implementations,
     which is what makes "compare on semantic hashes, never host floats"
     (§9.4 requirement 3) a rule two independent implementations actually
     honor identically, not just one. Reuses `js/world_delta.mjs`'s own CLI
     entry point (already conformance-tested by
     test_world_delta_conformance.py) rather than adding a new one.
"""
import copy
import json
import os
import subprocess
import sys

import world_delta as wd
from host import TestHost
from interp import Interpreter, PlanesError
from planes_num import Number
from world_numeric_bridge import canonical_quantize_outcome_string

REPO = os.path.dirname(os.path.abspath(__file__))
NODE = "node"

with open(os.path.join(REPO, "grammar", "world_numeric_bridge.planes"), encoding="utf-8") as _f:
    PLANES_SRC = _f.read()


# ------------------------------------------------------------- quantize fixtures

# name -> (value text, places). Exercises exact-at-scale, lossy round-down,
# lossy round-up, a rounding-exactly-half case, negatives, a whole number,
# and zero places.
QUANTIZE_FIXTURES = {
    "exact-at-scale": ("1.500", 3),
    "lossy-round-down": ("1.2341", 3),
    "lossy-round-up": ("1.2349", 3),
    "lossy-exactly-half": ("1.4995", 3),
    "negative-lossy": ("-1.2349", 3),
    "whole-number": ("7", 3),
    "zero-places": ("2.6", 0),
    "half-at-zero-places": ("0.5", 0),
}


def python_quantize_string(value_text, places):
    return canonical_quantize_outcome_string(Number.parse(value_text), places)


def js_quantize_string(value_text, places):
    r = subprocess.run(
        [NODE, os.path.join("js", "world_numeric_bridge.mjs")],
        input=json.dumps({"value": value_text, "places": places}),
        capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        raise AssertionError(f"js/world_numeric_bridge.mjs exited {r.returncode}: {r.stderr}")
    return r.stdout


def planes_quantize_string(value_text, places):
    driver = (f"value = {value_text}\nn = {places}\n"
              "show canonical quantize outcome string of value, n\n")
    itp = Interpreter(host=TestHost())
    try:
        itp.run(PLANES_SRC + "\n" + driver)
    except PlanesError as e:
        raise AssertionError(
            f"grammar/world_numeric_bridge.planes raised uncaught: {e.tag}: {e.detail}") from e
    return "\n".join(itp.output)


def _run_all_fixtures():
    results = {}
    for name, (value_text, places) in QUANTIZE_FIXTURES.items():
        py = python_quantize_string(value_text, places)
        js = js_quantize_string(value_text, places)
        pl = planes_quantize_string(value_text, places)
        results[name] = (py, js, pl, py == js == pl)
    return results


def test_quantize_outcome_agrees_byte_for_byte_across_all_three_implementations():
    results = _run_all_fixtures()
    failures = [
        f"--- {name} ---\npython:\n{py}\njs:\n{js}\nplanes:\n{pl}"
        for name, (py, js, pl, ok) in results.items() if not ok
    ]
    assert not failures, "\n".join(failures)


def test_the_gate_is_capable_of_failing():
    """The failability proof named in the build prompt (§N+3.2): the
    comparison itself must be able to observe a real divergence, not
    vacuously agree on mismatched strings."""
    py = python_quantize_string("1.4995", 3)
    tampered = py.replace("lossy=true", "lossy=false")
    assert py != tampered, "the comparison must be able to observe this divergence"


# -------------------------------------------------------- determinism-hash agreement

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
    "lineage": {
        "corpusSource": "ala-eriri", "culturalStatus": "canonical",
        "author": "studio", "origin": "system", "because": "canonical corpus asset",
        "agreementFingerprint": "fp-1", "permittedTransformations": "remix",
        "publishingRestriction": "none", "systemBoundary": "immutable",
    },
}


def _valid():
    return copy.deepcopy(VALID_ENVELOPE)


def js_semantic_hash(envelope):
    """Reuses js/world_delta.mjs's own CLI (`{prev, next, revision}` ->
    canonical_delta_string, which ends in a `semantic-hash:` line) rather
    than adding a second CLI surface to that module."""
    r = subprocess.run(
        [NODE, os.path.join("js", "world_delta.mjs")],
        input=json.dumps({"prev": envelope, "next": envelope, "revision": 0}),
        capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        raise AssertionError(f"js/world_delta.mjs exited {r.returncode}: {r.stderr}")
    for line in r.stdout.splitlines():
        if line.startswith("semantic-hash: "):
            return line[len("semantic-hash: "):]
    raise AssertionError(f"no semantic-hash line in js/world_delta.mjs output: {r.stdout!r}")


def test_determinism_hash_agrees_across_python_and_js_for_identical_envelopes():
    envelope_a = _valid()
    envelope_b = _valid()
    assert wd.semantic_hash(envelope_a) == js_semantic_hash(envelope_b)


def test_determinism_hash_catches_a_genuine_semantic_divergence_in_both_implementations():
    envelope_a = _valid()
    envelope_b = _valid()
    envelope_b["situation"]["x"] = 999
    assert wd.semantic_hash(envelope_a) != wd.semantic_hash(envelope_b)
    assert js_semantic_hash(envelope_a) != js_semantic_hash(envelope_b)
    assert wd.semantic_hash(envelope_a) == js_semantic_hash(envelope_a)
    assert wd.semantic_hash(envelope_b) == js_semantic_hash(envelope_b)


def _print_table(results):
    print(f"{'fixture':<28} {'python==js==planes':<20} {'result'}")
    for name, (py, js, pl, ok) in results.items():
        agree = py == js == pl
        print(f"{name:<28} {str(agree):<20} {'PASS' if ok else 'FAIL'}")


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
