"""Tests for `fail <message> as <tag>` — feat/fail-primitive-and-parser-probe,
Ruling 2.

Before this build, a `to` function had no way to manufacture a failure:
`... or fail as tag` only ever renamed or caught one an expression already
produced. `fail <message> as <tag>` raises the same `{tag, detail}` shape
(v9.0 §106) directly, from ordinary code, with `message` an unrestricted
expression — not a literal-only slot (Ruling 2 item 4).
"""
import sys

from interp import Interpreter, PlanesError
from parser import parse
from render import ast_equal, render
from shapes import analyse


def run(src, **kw):
    return Interpreter(**kw).run(src)


def interp(src, **kw):
    i = Interpreter(**kw)
    i.run(src)
    return i


def raises(src, **kw):
    try:
        run(src, **kw)
        assert False, "should raise"
    except PlanesError as e:
        return e


# ================================================================ the basic shape

def test_fail_raises_a_planes_error_with_the_given_tag_and_message():
    e = raises('fail "something went wrong" as bad-thing\n')
    assert e.tag == "bad-thing"
    assert e.detail == "something went wrong"


def test_fail_produces_the_same_record_shape_or_fail_as_produces():
    """v9.0 §106: the error record is {tag, detail} either way."""
    src = ('to risky:\n'
           '  fail "boom" as risky-broke\n\n'
           'x = risky() or fail as caught:\n'
           '  show caught.tag\n'
           '  show caught.detail\n')
    out = run(src)
    assert out == ["risky-broke", "boom"]


# ================================================================ message is an ordinary expression

def test_message_may_be_a_variable():
    e = raises('m = "dynamic reason"\nfail m as some-tag\n')
    assert e.detail == "dynamic reason"


def test_message_may_be_a_concatenation():
    e = raises('fail "part one " + "part two" as some-tag\n')
    assert e.detail == "part one part two"


def test_message_may_be_a_function_call_result():
    src = ('to describe of n:\n'
           '  give "value was " + text of n\n\n'
           'fail describe of 42 as bad-value\n')
    e = raises(src)
    assert e.detail == "value was 42"


def test_non_string_message_raises_a_clear_error_naming_the_fix():
    e = raises('fail 42 as bad-type\n')
    assert e.tag == "fail-message-not-text"
    assert "text of" in e.fix


# ================================================================ propagation (Ruling 2 item 3)

def test_a_fail_inside_a_called_function_propagates_through_or_fail_as():
    """The same channel every other failure uses: `or fail as` catches a
    PlanesError regardless of where it was raised, not only ones the
    interpreter itself produces."""
    src = ('to risky:\n'
           '  fail "inner reason" as inner-tag\n\n'
           'x = risky() or fail as outer-tag\n')
    e = raises(src)
    assert e.tag == "outer-tag"
    assert e.detail == "inner reason"


def test_an_uncaught_fail_propagates_all_the_way_to_run():
    """No handler anywhere: the same as any other uncaught PlanesError."""
    src = ('to a:\n'
           '  b()\n\n'
           'to b:\n'
           '  fail "deep failure" as deep-tag\n\n'
           'a()\n')
    e = raises(src)
    assert e.tag == "deep-tag"
    assert e.detail == "deep failure"


# ================================================================ no new effect kind

def test_fail_alone_contributes_no_effect_kind():
    s = analyse('fail "x" as some-tag\n')
    assert s.effects == []
    assert s.kinds() == []


def test_an_effect_inside_the_message_is_still_in_the_static_surface():
    """A static surface is what the program CAN do (v9.0 invariant 2):
    message is evaluated even though fail always raises after it, so an
    effect inside it must not vanish from the surface."""
    src = 'use http\nfail (text of (ask "https://x.example.com")) as some-tag\n'
    s = analyse(src)
    assert ("ask", "https://x.example.com") in [(e.kind, e.target) for e in s.effects]


def test_analyser_stays_total_over_a_program_containing_fail():
    """v9.0 invariant 2: the analyser never executes and must stay total.
    A bare top-level fail (which would actually raise if run) must not
    stop static analysis."""
    s = analyse('use file\nfail "x" as some-tag\nwrite [1] to "o.json"\n')
    assert any(e.kind == "write" for e in s.effects), \
        "analysis must continue past a fail statement, not stop at it"


# ================================================================ round-trip

def test_fail_statement_round_trips():
    src = 'fail "something went wrong" as bad-thing\n'
    prog = parse(src)
    prog2 = parse(render(prog))
    assert len(prog) == len(prog2)
    assert all(ast_equal(a, b) for a, b in zip(prog, prog2))


def test_fail_with_escaped_quote_in_message_round_trips():
    src = 'fail "a\\"b" as bad-thing\n'
    prog = parse(src)
    prog2 = parse(render(prog))
    assert all(ast_equal(a, b) for a, b in zip(prog, prog2))


# ================================================================ no new reserved word

def test_fail_and_as_were_already_reserved():
    """Ruling 2: fail and as are both already reserved by or-fail-as's
    own grammar; this build's statement form spends no new word. The
    ceiling itself (32) is test_names.py's job; this just confirms the
    two words this construct reuses were already in that set."""
    from lexer import KEYWORDS
    assert "fail" in KEYWORDS
    assert "as" in KEYWORDS


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
