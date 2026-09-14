"""The metacircular check, extended to the Swift analyser.

The Swift counterpart of test_js_metacircular_shapes.py, with `planes-swift` in
place of `node js/cli.mjs`: run EffectSurface.swift over grammar/lexer.planes,
grammar/parser.planes, and grammar/interp.planes, and compare against shapes.py
on the same files. It needs only the analyser — nothing here runs the stages.

A prediction is under test — made before interp.planes existed: a Planes
interpreter's static effect surface is every effect kind it has a reason to
claim, always — sound, maximally imprecise, and correct rather than a failure
of the analyser. `send` (B1, Sprint B) is the one kind excepted by name:
nothing in interp.planes's own graph carries the program's data out.
shapes.py confirmed the rest, and the JavaScript analyser agreed. The Swift
analyser should report the same set, and if it does not, one of the analysers
is wrong.
"""
import json
import subprocess
import sys

from lexer import EFFECT_KINDS
from shapes import analyse_file
from shapes_cli import as_json
from swift_host import REPO, SWIFT, command

STAGES = ["grammar/lexer.planes", "grammar/parser.planes", "grammar/interp.planes"]


def _swift_shapes(path):
    r = subprocess.run(command("shapes", path), cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"planes-swift failed on {path}: {r.stderr}")
    return json.loads(r.stdout)


def test_the_three_grammar_stage_surfaces_agree():
    """Every stage's published surface is identical between the two analysers."""
    for path in STAGES:
        py = as_json(analyse_file(path), path)
        sw = _swift_shapes(path)
        assert sw == py, f"{path}:\n  py={json.dumps(py)}\n  swift={json.dumps(sw)}"


def test_the_interpreter_static_surface_is_all_but_send_kinds_on_both_analysers():
    """The prediction, discharged by a second independent analyser. `send`
    is excepted by name (B1) — see core_check.py's confirmation 2 for the
    same exception, argued once."""
    expected_kinds = sorted(set(EFFECT_KINDS) - {"send"})
    assert len(expected_kinds) == 7, expected_kinds

    py = as_json(analyse_file("grammar/interp.planes"), "grammar/interp.planes")
    sw = _swift_shapes("grammar/interp.planes")

    assert py["kinds"] == expected_kinds, f"shapes.py: {py['kinds']}"
    assert sw["kinds"] == expected_kinds, f"EffectSurface.swift: {sw['kinds']}"
    assert sw["kinds"] == py["kinds"], "the two analysers must agree"


def test_the_lexer_and_parser_stages_are_pure_on_both_analysers():
    """A lexer and a parser transform data; they touch nothing outside
    themselves. Both analysers must say so."""
    for path in ["grammar/lexer.planes", "grammar/parser.planes"]:
        py = as_json(analyse_file(path), path)
        sw = _swift_shapes(path)
        assert py["kinds"] == [] and py["boundaries"] == [], f"{path} py: {py}"
        assert sw["kinds"] == [] and sw["boundaries"] == [], f"{path} swift: {sw}"


if __name__ == "__main__":
    if SWIFT is None:
        print("  SKIP  swift not on PATH")
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
