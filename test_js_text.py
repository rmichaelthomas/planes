"""S4, Phase 2 — Planes text in JS, checked against planes_text.py.

js/planes_text.mjs holds the four STRING escapes and their inverse, plus the
code-point helpers JavaScript needs and Python does not: Planes text is a
sequence of Unicode code points, and JS strings are UTF-16, so "😀" is one
element to Planes but length 2 to a naive JS string. This test drives escapes,
their inverse, and code-point length/iteration through both implementations and
compares — covering surrogate pairs, where UTF-16 and code points differ
(failure mode 2).
"""
import json
import os
import shutil
import subprocess
import sys

from planes_text import escape_string_literal, resolve_string_escapes

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))


def _node_text(ops):
    r = subprocess.run(
        [NODE, "js/cli.mjs", "text", json.dumps(ops)],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed: {r.stderr}")
    return json.loads(r.stdout)


def py_text_op(op):
    name, *a = op
    if name == "resolve":
        return resolve_string_escapes(a[0])
    if name == "escape":
        return escape_string_literal(a[0])
    if name == "cplen":
        return str(len(a[0]))               # Python str: a code-point count
    if name == "cps":
        return list(a[0])                   # compared as a decoded list, not a string
    if name == "badresolve":
        try:
            resolve_string_escapes(a[0])
            return "NO-ERROR"
        except ValueError as e:
            return "BAD:" + e.args[0]
    raise AssertionError(f"unknown op {name}")


def _agree(ops):
    got = _node_text(ops)
    want = [py_text_op(op) for op in ops]
    assert got == want, "\n".join(
        f"{op}: js={g!r} py={w!r}"
        for op, g, w in zip(ops, got, want) if g != w)


# ======================================================= the four escapes and their inverse

def test_resolve_and_escape_agree_for_every_legal_escape():
    _agree([["resolve", r'a\"b'], ["resolve", r"a\\b"], ["resolve", r"a\nb"],
            ["resolve", r"a\tb"], ["resolve", "plain"], ["resolve", ""]])
    _agree([["escape", 'a"b'], ["escape", "a\\b"], ["escape", "a\nb"],
            ["escape", "a\tb"], ["escape", 'a"b\\c\nd\te']])


def test_an_illegal_escape_names_the_bad_character_on_both():
    _agree([["badresolve", r"a\zb"], ["badresolve", r"\q"], ["badresolve", r"x\9"]])


# ================================================= code-point semantics (surrogate pairs)

def test_code_point_length_counts_code_points_not_utf16_units():
    _agree([["cplen", "😀"], ["cplen", "a😀b"], ["cplen", "😀😀"],
            ["cplen", "plain"], ["cplen", ""], ["cplen", "café"],
            ["cplen", "𝕏 marks"], ["cplen", "👨‍👩‍👧"]])


def test_code_point_iteration_splits_astral_chars_whole():
    _agree([["cps", "a😀b"], ["cps", "😀"], ["cps", "abc"],
            ["cps", "café"], ["cps", "x𝕏y"]])


def test_escape_of_astral_text_passes_the_char_through_whole():
    # No escape applies to an astral char, so escapeStringLiteral must leave it
    # intact — not split it into two lone surrogates.
    _agree([["escape", "say 😀"], ["escape", 'q"😀'], ["escape", "𝕏\t𝕐"]])


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
