"""S5, Phase 2 — the JS analyser's derivation graph, checked against shapes.py.

The effect surface says WHAT a program touches; the derivation graph says WHERE
a value came from — the static analogue of `why`. A.3 names it as one of the
canonical forms: origins_of and the derivation tree, canonically rendered.

js/shapes.mjs carries a StaticDeriv on every effect, mirroring shapes.py's field
names and meanings. This drives the same programs through both analysers with
file=None (so a derivation's `file` field is null on both sides and only
structure is compared) and checks, per declared effect:

  * origins_of — every (name, file) the target provably derives from;
  * the full derivation tree — kind, label, origin, file, inputs, expanded.

The programs are shared with test_js_shapes.py plus the derivation-specific
cases from test_shapes.py: a parameter origin, an empty origin for a bare
literal, a literal reached through a variable, a re-escaped quote in a literal
label, and the unknown provenance node widening produces at a branch join.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from shapes import analyse
from test_js_shapes import INLINE

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))


def _js_deriv(path):
    r = subprocess.run([NODE, "js/cli.mjs", "shapes-deriv", path], cwd=REPO,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed on {path}: {r.stderr}")
    return json.loads(r.stdout)


def _py_deriv_tree(node):
    """The nested form js/shapes.mjs's derivTree emits — fully expanded, shared
    nodes re-walked (the graph is an acyclic DAG built bottom-up)."""
    if node is None:
        return None
    return {
        "kind": node.kind,
        "label": node.label,
        "origin": node.origin,
        "file": node.file,
        "inputs": [_py_deriv_tree(i) for i in node.inputs],
    }


def _py_derivation_form(surface):
    return [
        {
            "kind": e.kind,
            "boundary": e.boundary,
            "target": e.target,
            "computed": e.computed,
            "origins": [[n, f] for n, f in surface.origins_of(e)],
            "derivation": _py_deriv_tree(e.derivation),
        }
        for e in surface.declared
    ]


# Derivation-specific programs, on top of INLINE.
DERIV_CASES = INLINE + [
    # a named parameter shows up in origins
    ('use http\nto send of payload:\n'
     '  give ask "https://collector.example.com/?d=" + payload\n\n'
     'x = send of "secret"\n'),
    # a bare literal derives from nothing
    'use http\nx = ask "https://example.com/a.json"',
    # a literal reached through a variable
    'use http\nlet u = "https://x"\nx = ask u',
    # a literal label re-escapes a quote (const()'s Str case)
    'use http\nlet u = "a\\"b"\nx = ask u',
    # widening at a branch join produces an unknown provenance node
    ('use http\nlet u = "https://example.com/default.json"\n'
     'if 1 > 0:\n  let u = "https://example.com/other.json"\nx = ask u'),
    # a target built from ask output claims no false provenance
    ('use http\nto get of url:\n  give ask url\n\n'
     'xs = for each u in [1, 2]: get of u'),
]


def test_derivation_and_origins_agree():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "p.planes")
        for src in DERIV_CASES:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(src)
            py = _py_derivation_form(analyse(src))
            js = _js_deriv(p)
            assert js == py, (f"src:\n{src}\n  py={json.dumps(py)}\n"
                              f"  js={json.dumps(js)}")


def test_origins_reaches_a_named_parameter():
    """A concrete check that the shared form is not vacuously agreeing: the
    parameter `payload` must appear in the ask effect's origins."""
    src = ('use http\nto send of payload:\n'
           '  give ask "https://collector.example.com/?d=" + payload\n\n'
           'x = send of "secret"\n')
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "p.planes")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(src)
        js = _js_deriv(p)
    asks = [e for e in js if e["kind"] == "ask"]
    assert asks, "no ask effect found"
    names = {n for e in asks for n, _f in e["origins"]}
    assert "payload" in names, names


if __name__ == "__main__":
    if NODE is None:
        print("  SKIP  node not on PATH")
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
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
