"""Tests for planes_text.py — the leaf module holding the four STRING
escapes and their inverse (feat/fail-primitive-and-parser-probe, Ruling
1). Functional coverage of the two directions as they're actually used
lives where they're used (test_text.py, test_render.py, test_annotation.py,
test_shapes.py, test_rules.py); this file covers the module's own
properties: that it stays a leaf (no project imports), and that its two
functions are exact inverses of each other, directly.
"""
import ast
import sys

import planes_text
from planes_text import escape_string_literal, resolve_string_escapes


def _own_imports():
    tree = ast.parse(open("planes_text.py").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module)
    return names


# ================================================================ leaf-module invariant

def test_planes_text_imports_nothing_from_this_project():
    """Ruling 1: 'imports nothing from this project. Stdlib only, or
    nothing at all.' Four modules (lexer, render, interp, shapes) plus
    rules -- which otherwise depends on nothing in this project at all
    -- import from here, so this module must depend on nothing itself,
    or the leaf property it exists to provide is fiction."""
    assert _own_imports() == set(), _own_imports()


def test_planes_text_has_no_project_module_names_in_its_namespace():
    """Belt and suspenders on the same claim, from the loaded module
    rather than its source text: nothing this repo defines (lexer,
    parser, interp, shapes, rules, render, host, modules, planes_num)
    appears as an attribute of the already-imported module."""
    project_modules = {"lexer", "parser", "interp", "shapes", "rules",
                       "render", "host", "modules", "planes_num"}
    assert not (project_modules & set(dir(planes_text)))


# ================================================================ the two directions agree

def test_resolve_and_escape_are_inverses_for_every_legal_escape():
    for raw_body in (r'a\"b', r"a\\b", r"a\nb", r"a\tb", "plain", ""):
        resolved = resolve_string_escapes(raw_body)
        assert escape_string_literal(resolved) == raw_body, raw_body


def test_resolve_raises_value_error_naming_the_bad_character():
    """planes_text raises a plain ValueError -- it has no notion of
    source position, and cannot construct a PlanesSyntaxError without
    importing lexer.py, which would make the two modules import each
    other (lexer.py already imports planes_text for resolution)."""
    try:
        resolve_string_escapes(r"a\zb")
        assert False, "should raise"
    except ValueError as e:
        assert e.args[0] == "z"


def test_escape_string_literal_round_trips_through_the_regex_shape():
    """The exact property lexer.py's STRING regex depends on: escaping
    a value and wrapping it in quotes must never let an internal quote
    terminate the literal early."""
    value = 'a"b\\c\nd\te'
    literal_body = escape_string_literal(value)
    assert '"' not in literal_body.replace('\\"', '')
    assert resolve_string_escapes(literal_body) == value


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
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
