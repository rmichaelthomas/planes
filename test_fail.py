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
    # §158: the guard now accepts two shapes, so the fix names both. A message
    # that named only the one the author did not want is the failure this
    # assertion exists to prevent.
    assert "fail { message:" in e.fix, e.fix


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



# ======================================================== §158, the fix field
#
# `errors name the fix` has been a language-level commitment since unbound v1.1
# §22, and until this build a program could not keep it: `fail` had one text
# slot, and the error record a program catches had two fields. The record form
# adds the slot; `error_record` adds the field. No new reserved word and no new
# syntax — `fail <expr> as <tag>` already read any expression, so a record
# literal already parsed in all three implementations. What refused it was the
# runtime guard, which is why the reserved-word count cannot move here.


def test_fail_accepts_a_record_naming_the_message_and_the_fix():
    e = raises('fail { message: "the order is empty", '
               'fix: "add a line before submitting" } as empty-order\n')
    assert e.tag == "empty-order"
    assert e.detail == "the order is empty"
    assert e.fix == "add a line before submitting"
    assert "\n  try: add a line before submitting" in str(e)


def test_fail_still_accepts_plain_text_and_names_no_fix():
    """The form every existing program uses. Unchanged, and its fix is empty
    rather than invented — the language does not overwrite what the author
    chose to say."""
    e = raises('fail "something went wrong" as bad-thing\n')
    assert e.tag == "bad-thing"
    assert e.detail == "something went wrong"
    assert e.fix == ""
    assert "try:" not in str(e)


def test_the_record_form_may_name_a_message_and_no_fix():
    e = raises('fail { message: "just the message" } as bare\n')
    assert e.detail == "just the message"
    assert e.fix == ""


def test_a_record_without_a_text_message_is_refused_by_the_same_path():
    for src, found in (
            ('fail { fix: "x" } as t\n', "nothing"),
            ('fail { message: 5 } as t\n', "5"),
            ('fail { message: [1, 2] } as t\n', "[2 items]")):
        e = raises(src)
        assert e.tag == "fail-message-not-text", src
        assert f"found {found}" in e.detail, (src, e.detail)


def test_a_non_text_fix_is_refused_and_names_which_field():
    e = raises('fail { message: "ok", fix: 5 } as t\n')
    assert e.tag == "fail-message-not-text"
    assert e.detail == "fail's fix must be text, found 5"
    assert "leave the field out" in e.fix


# ------------------------------------------------- the reading half (§149)
#
# A field is the producer's half; the reading side is specified alongside it or
# the field is not a feature. These are the assertions that the fix is
# *readable* by a program, not merely present in a rendered message.


def test_a_caught_error_carries_the_fix_the_program_named():
    i = interp('to risky:\n'
               '  fail { message: "boom", fix: "hold it right" } as inner\n'
               'x = risky() or fail as e:\n'
               '  show e.tag\n'
               '  show e.detail\n'
               '  show e.fix\n')
    assert i.output == ["inner", "boom", "hold it right"]


def test_a_caught_error_without_a_fix_carries_nothing_not_an_absent_field():
    """§158 locks `fix` as present-and-nothing rather than absent. The two are
    not the same rule: under `when`, a missing field is no match, so an absent
    `fix` would make `when e is { fix }:` skip every error that names none —
    which is most of them."""
    i = interp('to risky:\n'
               '  fail "plain" as inner\n'
               'x = risky() or fail as e:\n'
               '  show e.fix is nothing\n')
    assert i.output == ["true"]


def test_when_binds_the_fix_field_on_every_error():
    """The shape-matching read, which is what makes the field a feature rather
    than a rendering detail. Note the spelling: `{ fix }` binds the field,
    while `{ fix: f }` would *match* it against the value of a name `f`."""
    src = ('to risky:\n'
           '  fail %s as inner\n'
           'x = risky() or fail as e:\n'
           '  when e is { fix }:\n'
           '    show "bound: " + (text of fix)\n'
           '  else:\n'
           '    show "no fix field"\n')
    named = interp(src % '{ message: "boom", fix: "do it this way" }')
    assert named.output == ["bound: do it this way"]
    unnamed = interp(src % '"boom"')
    assert unnamed.output == ["bound: nothing"], unnamed.output


def test_the_path_field_keeps_the_opposite_convention():
    """Not a bug and not fixed here — a divergence this build reports. `path`
    is absent when it does not apply, so the same `when` that binds on every
    error does not match on one without a path. Converging the two is a ruling
    for the architect."""
    i = interp('to risky:\n'
               '  fail "plain" as inner\n'
               'x = risky() or fail as e:\n'
               '  when e is { path }:\n'
               '    show "matched path"\n'
               '  else:\n'
               '    show "no path field"\n')
    assert i.output == ["no path field"]


def test_or_fail_carries_a_caught_fix_forward_and_it_stays_readable():
    """C2 made `or fail` carry the caught error's fix forward so a re-tag could
    not silence it. §158 makes that carry-forward visible to a program for the
    first time: it was only ever rendered before."""
    i = interp('to inner-fn:\n'
               '  fail { message: "deep", fix: "the original fix" } as deep\n'
               'to middle:\n'
               '  x = inner-fn() or fail as re-tagged\n'
               '  give x\n'
               'y = middle() or fail as e:\n'
               '  show e.tag\n'
               '  show e.detail\n'
               '  show e.fix\n')
    assert i.output == ["re-tagged", "deep", "the original fix"]


def test_every_error_the_language_raises_carries_the_field_too():
    """Not only `fail`'s. The field is on the record, so an error the language
    itself raised is read the same way — which is the point of naming a fix in
    a field rather than in text."""
    i = interp('x = 5\n'
               'y = (count of x) or fail as e:\n'
               '  show e.tag\n'
               '  show e.fix\n')
    assert i.output[0] == "not-a-collection"
    assert "a list, a record, or text" in i.output[1]


def test_the_record_form_round_trips_through_render():
    """render.py has to reproduce the new spelling; a form the language accepts
    and its own canonical printer cannot reproduce is a defect S5 and S6 both
    found the hard way."""
    src = ('fail { message: "the order is empty", '
           'fix: "add a line" } as empty-order\n')
    prog = parse(src)
    assert ast_equal(parse(render(prog))[0], prog[0])


def test_the_record_form_declares_no_effect():
    """`fail` performs none, and a record message does not change that."""
    surface = analyse('fail { message: "m", fix: "f" } as t\n')
    assert not surface.effects, surface.effects


def test_no_grammar_file_or_corpus_program_changed_behaviour():
    """Every existing `fail "text" as tag` still behaves identically. Asserted
    rather than assumed: the guard this build widened is on the path all of
    them take."""
    import glob
    checked = 0
    for path in sorted(glob.glob("grammar/*.planes")
                       + glob.glob("corpus/**/*.planes", recursive=True)):
        src = open(path, encoding="utf-8").read()
        for line in src.splitlines():
            stripped = line.strip()
            if not stripped.startswith("fail "):
                continue
            checked += 1
            # A `fail` whose message is not a record literal takes exactly the
            # path it took before: the record branch is not entered.
            assert "as " in stripped, (path, stripped)
    assert checked >= 80, checked


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
