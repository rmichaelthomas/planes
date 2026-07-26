"""S5, Phase 6 — the metacircular check, extended to the analyser.

The prior build ran the three .planes stages on the JS implementation and found
nothing. This extends it: run js/shapes.mjs over grammar/lexer.planes,
grammar/parser.planes, and grammar/interp.planes, and compare against shapes.py
on the same files.

A prediction is under test — this chain's own, made before interp.planes
existed: a Planes interpreter's static effect surface is ALL SEVEN KINDS,
always — sound, maximally imprecise, and correct rather than a failure of the
analyser. shapes.py confirmed it. shapes.js should report the same seven, and if
it does not, one of the two analysers is wrong. Two analysers agreeing on an
all-seven surface is stronger evidence than one.
"""
import json
import os
import shutil
import subprocess
import sys

from lexer import EFFECT_KINDS
from shapes import analyse_file
from shapes_cli import as_json

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))

STAGES = ["grammar/lexer.planes", "grammar/parser.planes", "grammar/interp.planes"]


def _js_shapes(path):
    r = subprocess.run([NODE, "js/cli.mjs", "shapes", path], cwd=REPO,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed on {path}: {r.stderr}")
    return json.loads(r.stdout)


def test_the_three_grammar_stage_surfaces_agree():
    """Every stage's published surface is identical between the two analysers."""
    for path in STAGES:
        py = as_json(analyse_file(path), path)
        js = _js_shapes(path)
        assert js == py, f"{path}:\n  py={json.dumps(py)}\n  js={json.dumps(js)}"


def test_the_interpreter_static_surface_is_all_seven_kinds_on_both_analysers():
    """The prediction, discharged by a second independent analyser."""
    all_seven = sorted(EFFECT_KINDS)
    assert len(all_seven) == 7, all_seven

    py = as_json(analyse_file("grammar/interp.planes"), "grammar/interp.planes")
    js = _js_shapes("grammar/interp.planes")

    assert py["kinds"] == all_seven, f"shapes.py: {py['kinds']}"
    assert js["kinds"] == all_seven, f"shapes.js: {js['kinds']}"
    assert js["kinds"] == py["kinds"], "the two analysers must agree"


def test_the_lexer_and_parser_stages_are_pure_on_both_analysers():
    """A lexer and a parser transform data; they touch nothing outside
    themselves. Both analysers must say so."""
    for path in ["grammar/lexer.planes", "grammar/parser.planes"]:
        py = as_json(analyse_file(path), path)
        js = _js_shapes(path)
        assert py["kinds"] == [] and py["boundaries"] == [], f"{path} py: {py}"
        assert js["kinds"] == [] and js["boundaries"] == [], f"{path} js: {js}"


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
