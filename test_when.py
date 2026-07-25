"""Tests for `when` (shape dispatch) — the third locked-but-unbuilt
construct of v5.0 §74, closed in this build.

Locked semantics, verbatim: "dispatch is `when` over record shape, with
field binding. Not type tags, not a type system." "It asks whether a
record has these fields with these values and binds the rest. It is
derivation-visible — which branch matched is a structural fact `why` can
report."
"""
import sys

from interp import Interpreter, PlanesError
from shapes import analyse


def run(src, **kw):
    return Interpreter(**kw).run(src)


def interp(src, **kw):
    i = Interpreter(**kw)
    i.run(src)
    return i


OP_NODE = 'node = { kind: "op", left: 1, right: 2 }\n'
LITERAL_NODE = 'node = { kind: "literal", value: 5 }\n'

DISPATCH = ('when node is { kind: "op", left, right }:\n'
            '  show text of (left + right)\n'
            'else:\n'
            '  when node is { kind: "literal", value }:\n'
            '    show text of value\n'
            '  else:\n'
            '    show "unknown"\n')


# ================================================================ the locked example

def test_matching_shape_binds_and_runs_the_body():
    out = run(OP_NODE + DISPATCH)
    assert out == ["3"]


def test_a_different_matching_branch_in_the_chained_ladder():
    out = run(LITERAL_NODE + DISPATCH)
    assert out == ["5"]


def test_neither_branch_matches_falls_to_the_final_else():
    out = run('node = { kind: "unknown-kind" }\n' + DISPATCH)
    assert out == ["unknown"]


# ================================================================ match vs. bind

def test_bare_name_binds_the_fields_value():
    out = run('node = { a: 1, b: 2 }\n'
              'when node is { a, b }:\n'
              '  show text of (a + b)\n')
    assert out == ["3"]


def test_colon_entry_requires_an_equal_value():
    out = run('node = { a: 1 }\n'
              'when node is { a: 1 }:\n'
              '  show "matched"\n'
              'else:\n'
              '  show "no"\n')
    assert out == ["matched"]

    out2 = run('node = { a: 2 }\n'
               'when node is { a: 1 }:\n'
               '  show "matched"\n'
               'else:\n'
               '  show "no"\n')
    assert out2 == ["no"]


def test_missing_field_is_a_non_match_not_an_error():
    out = run('node = { a: 1 }\n'
              'when node is { b: 1 }:\n'
              '  show "matched"\n'
              'else:\n'
              '  show "missing field falls to else"\n')
    assert out == ["missing field falls to else"]


def test_extra_fields_on_the_subject_do_not_prevent_a_match():
    """A shape pattern names what must hold, not the whole record."""
    out = run('node = { kind: "op", left: 1, right: 2, extra: "ignored" }\n'
              'when node is { kind: "op" }:\n'
              '  show "matched"\n')
    assert out == ["matched"]


def test_no_else_and_no_match_runs_nothing():
    i = interp('node = { a: 1 }\nwhen node is { b: 1 }:\n  show "unreached"\n')
    assert i.output == []


# ================================================================ guarded equal (invariant 4)

def test_type_mismatched_match_constraint_raises_not_silently_misses():
    try:
        run('node = { a: 1 }\nwhen node is { a: "1" }:\n  show "matched"\nelse:\n  show "no"\n')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "cannot-compare"


def test_matching_on_a_record_field_uses_equal_not_identity():
    out = run('node = { a: { x: 1 } }\n'
              'when node is { a: { x: 1 } }:\n'
              '  show "matched"\n')
    assert out == ["matched"]


# ================================================================ not a type system (invariant 5)

def test_dispatch_is_on_shape_and_value_never_a_type_tag():
    """Two records with completely different field sets both match their
    own pattern -- there is no notion of a record's 'type' anywhere."""
    out1 = run('node = { kind: "a" }\nwhen node is { kind: "a" }:\n  show "a"\n')
    out2 = run('node = { totally: "different", fields: 1 }\n'
               'when node is { totally: "different" }:\n'
               '  show "b"\n')
    assert out1 == ["a"] and out2 == ["b"]


# ================================================================ not a record -> error

def test_subject_not_a_record_raises():
    try:
        run('when 5 is { a: 1 }:\n  show "x"\n')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "not-a-record"


# ================================================================ derivation-visibility

def test_why_shows_which_branch_matched():
    def boom(u):
        raise RuntimeError("nope")
    i = interp('use http\n'
              'x = (ask "https://example.com/a.json") or fail as err:\n'
              '    when err is { tag: "err" }:\n'
              '      show "matched-branch"\n'
              '    else:\n'
              '      show "else-branch"\n'
              'why x\n', http=boom)
    tree = "\n".join(i.output)
    assert "matched" in tree
    assert "tag" in tree


def test_why_shows_the_else_branch_did_not_match():
    def boom(u):
        raise RuntimeError("nope")
    i = interp('use http\n'
              'x = (ask "https://example.com/a.json") or fail as err:\n'
              '    when err is { tag: "something-else" }:\n'
              '      show "matched-branch"\n'
              '    else:\n'
              '      show "else-branch"\n'
              'why x\n', http=boom)
    tree = "\n".join(i.output)
    assert "did not match" in tree


# ================================================================ is nothing (parser conflict)

def test_is_nothing_still_works_alongside_when():
    i = interp('x = 5\nb = x is nothing\n'
               'node = { a: 1 }\n'
               'when node is { a: 1 }:\n'
               '  show text of b\n')
    assert i.output == ["false"]


def test_is_remains_free_as_an_ordinary_name_where_unrelated():
    """`is` is read positionally only right after a comparison-level
    expression when followed by NOTHING or opening a when-pattern -- it
    stays an ordinary name everywhere else (test_names.py's ceiling)."""
    i = interp('to is of x:\n  give x + 1\n\nshow text of (is of 5)\n')
    assert i.output == ["6"]


# ================================================================ shapes.py soundness (invariant 3)

def test_when_produces_no_effect_of_its_own():
    s = analyse(OP_NODE + 'when node is { kind: "op" }:\n  show "x"\nelse:\n  show "y"\n')
    assert s.kinds() == ["show"]


def test_shapes_walks_both_branches_for_effects():
    """A static surface is what the program CAN do -- both when-branches'
    effects belong in it, whichever one a given run actually takes."""
    s = analyse('use http\nuse file\n'
               'node = { a: 1 }\n'
               'when node is { a: 1 }:\n'
               '  x = ask "https://example.com/a.json"\n'
               'else:\n'
               '  write [1] to "o.json"\n')
    assert s.kinds() == ["ask", "write"]


def test_shapes_walks_match_constraint_expressions():
    s = analyse('use http\nnode = { a: 1 }\n'
               'when node is { a: (count of [1, 2]) }:\n'
               '  show "matched"\n')
    # count of is pure -- nothing to find here, but this must not raise
    # and must not report a spurious effect.
    assert s.kinds() == ["show"]


def test_shapes_never_raises_on_when():
    analyse('node = { a: "x" }\nwhen node is { a: 1 }:\n  show "x"\nelse:\n  show "y"\n')


def test_the_oracle_holds_when_the_match_itself_touches_a_boundary():
    """A match constraint's own expression can perform an effect; it must
    show up in both the runtime log and the static surface identically."""
    def stub(u):
        return '"op"'
    s = analyse('use http\nnode = { kind: "op" }\n'
               'when node is { kind: (ask "https://example.com/a.json") }:\n'
               '  show "matched"\n'
               'else:\n'
               '  show "no"\n')
    i = interp('use http\nnode = { kind: "op" }\n'
              'when node is { kind: (ask "https://example.com/a.json") }:\n'
              '  show "matched"\n'
              'else:\n'
              '  show "no"\n', http=stub)
    runtime_kinds = {e[0] for e in i.effects}
    assert runtime_kinds <= set(s.kinds())


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
