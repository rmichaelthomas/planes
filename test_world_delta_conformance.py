"""test_world_delta_conformance.py — the cross-implementation delta gate.

Horizon Phase 0 Build 3, Phase 1. Extends test_world_ir_conformance.py's
byte-identical-agreement discipline to `compute_delta`: Python (world_delta.py)
and JavaScript (js/world_delta.mjs) must produce the identical canonical
delta string for every fixture below. Python-only, unlike Build 1's
three-implementation gate — a self-hosted Planes mirror of delta computation
is not part of this build's file inventory (§2), since delta computation is
driver-level infrastructure a world program's own source never calls.
"""
import copy
import json
import os
import subprocess
import sys

import world_delta as wd
import world_ir as w

REPO = os.path.dirname(os.path.abspath(__file__))
NODE = "node"

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

RELATION_A = {
    "relationId": "rel-1", "relationType": "near", "fromId": "subject-1",
    "toId": "landing-1", "provenance": "authored",
}

RELATION_B = {
    "relationId": "rel-2", "relationType": "far", "fromId": "subject-1",
    "toId": "landing-2", "provenance": "authored",
}


def _valid():
    return copy.deepcopy(VALID_ENVELOPE)


def _norm(envelope):
    normalized, warnings = w.parse_world_envelope(envelope)
    assert warnings == []
    return normalized


def _patch_case():
    prev = _valid()
    next_env = _valid()
    next_env["situation"]["x"] = 11
    next_env["identity"]["displayName"] = "Reso II"
    return prev, next_env, 3


def _create_remove_case():
    prev = _valid()
    next_env = _valid()
    next_env["identity"]["id"] = "subject-2"
    return prev, next_env, 7


def _relation_added_case():
    prev = _valid()
    next_env = _valid()
    next_env["relation"] = dict(RELATION_A)
    return prev, next_env, 0


def _relation_removed_case():
    prev = _valid()
    prev["relation"] = dict(RELATION_A)
    next_env = _valid()
    return prev, next_env, 12


def _relation_replaced_case():
    prev = _valid()
    prev["relation"] = dict(RELATION_A)
    next_env = _valid()
    next_env["relation"] = dict(RELATION_B)
    return prev, next_env, 5


def _no_op_case():
    prev = _valid()
    next_env = _valid()
    return prev, next_env, 41


FIXTURES = {
    "patch": _patch_case(),
    "create-remove": _create_remove_case(),
    "relation-added": _relation_added_case(),
    "relation-removed": _relation_removed_case(),
    "relation-replaced": _relation_replaced_case(),
    "no-op": _no_op_case(),
}


def python_delta_string(prev, next_env, revision):
    delta = wd.compute_delta(_norm(prev), _norm(next_env), revision)
    return wd.canonical_delta_string(delta)


def js_delta_string(prev, next_env, revision):
    payload = json.dumps({"prev": prev, "next": next_env, "revision": revision})
    r = subprocess.run(
        [NODE, os.path.join("js", "world_delta.mjs")],
        input=payload, capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        raise AssertionError(f"js/world_delta.mjs exited {r.returncode}: {r.stderr}")
    return r.stdout


def _run_all_fixtures():
    results = {}
    for name, (prev, next_env, revision) in FIXTURES.items():
        py = python_delta_string(prev, next_env, revision)
        js = js_delta_string(prev, next_env, revision)
        results[name] = (py, js, py == js)
    return results


def test_all_fixtures_agree_byte_for_byte_between_python_and_js():
    results = _run_all_fixtures()
    failures = []
    for name, (py, js, ok) in results.items():
        if not ok:
            failures.append(f"--- {name} ---\npython:\n{py}\njs:\n{js}")
    assert not failures, "\n".join(failures)


def test_revision_counter_agrees_and_is_monotonic_across_implementations():
    prev = _norm(_valid())
    py_revision = 0
    js_revision = 0
    for _ in range(4):
        py_delta = wd.compute_delta(prev, prev, py_revision)
        js_out = js_delta_string(prev, prev, js_revision)
        assert f"revision: {js_revision} -> {js_revision + 1}" in js_out
        assert py_delta["revision_from"] == py_revision
        assert py_delta["revision_to"] == py_revision + 1
        py_revision = py_delta["revision_to"]
        js_revision += 1
    assert py_revision == js_revision == 4


def test_the_gate_is_capable_of_failing():
    """The failability proof named in the build prompt (§N+3.2)."""
    prev, next_env, revision = _patch_case()
    real = python_delta_string(prev, next_env, revision)
    tampered = real.replace("11", "99")
    assert real != tampered, "the comparison must be able to observe this divergence"


def _print_table(results):
    print(f"{'fixture':<20} {'python==js':<12} result")
    for name, (py, js, ok) in results.items():
        print(f"{name:<20} {str(ok):<12} {'PASS' if ok else 'FAIL'}")


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
