"""Names.

The mandate for this session: take every word that is not structural and
require that it works as a function name. In a language whose selling point
is names that read as prose, `count` and `text` and `read` are words people
reach for, and a language that silently refuses them is hostile.
"""
import sys

from interp import Interpreter, PlanesError
from lexer import KEYWORDS
from parser import BUILTIN_NAMES


def run(src, **kw):
    return Interpreter(**kw).run(src)


def val(src, name, **kw):
    i = Interpreter(**kw)
    i.run(src)
    return i.env.get(name)


# Words that used to be reserved and are now ordinary. Each must work as a
# user's own function name.
FORMER_KEYWORDS = ["count", "text", "lower", "upper", "whole", "ask", "read"]


# ================================================================ the mandate

def test_every_builtin_name_works_as_a_function_name():
    """The headline test. Define a function named after each builtin and
    require the program runs and the user's definition is the one used."""
    failures = []
    for word in sorted(BUILTIN_NAMES):
        src = f"to {word} of x:\n  give 99\n\nr = {word} of 1"
        try:
            v = val(src, "r")
            if v.value != 99:
                failures.append(f"{word}: user definition was not used")
        except Exception as e:
            failures.append(f"{word}: {type(e).__name__}: {e}")
    assert not failures, "these words are not usable as names:\n  " + \
                         "\n  ".join(failures)


def test_every_builtin_name_works_as_a_zero_arg_function():
    failures = []
    for word in sorted(BUILTIN_NAMES):
        src = f"to {word}:\n  give 7\n\nr = {word}"
        try:
            if val(src, "r").value != 7:
                failures.append(f"{word}: wrong value")
        except Exception as e:
            failures.append(f"{word}: {type(e).__name__}: {e}")
    assert not failures, "\n  ".join(failures)


def test_every_builtin_name_works_inside_a_multiword_name():
    failures = []
    for word in sorted(BUILTIN_NAMES):
        src = f"to daily {word}:\n  give 5\n\nr = daily {word}"
        try:
            if val(src, "r").value != 5:
                failures.append(f"daily {word}: wrong value")
        except Exception as e:
            failures.append(f"daily {word}: {type(e).__name__}: {e}")
    assert not failures, "\n  ".join(failures)


def test_reserved_list_is_only_structural_words():
    """A word stays reserved only if the parser must see it to know the
    shape of a statement.

    The ceiling is 32, and every rise is argued for in a report:

    - 25 after the vocabulary was cut from 32.
    - 26 with `with`, for rename-on-import: a consumer of two colliding
      modules cannot edit either one, so the fix must live at the point of
      use. `taking`, for selective import, was rejected the same session —
      it only prevents collisions that are already loud errors.
    - 29 with `foreign`, `from`, `doing`, for FFI. Each was checked against
      reusing an existing word: `as` already means rename, `with` already
      means rename-pairs, and overloading either would give one word two
      meanings in two statements.
    - 30 with `rule`, for the effect-only rule-plane slice (REPORT_RULES.md).
      No existing word could carry it without giving that word two meanings
      in two statements. `may` and `not` were deliberately left unreserved:
      `not` already carried logical negation and needed no new grant, and
      `may` is read positionally inside `parse_rule` only, so a program that
      never writes `rule` still has `may` free as an ordinary name.
    - 32 with `plus` and `when`, closing the two constructs v5.0 §72/§74
      locked but never built. `plus` is not spellable as `+`: `+` on two
      lists concatenates (v9.0 A.1's homogeneity rule requires both sides
      the same type), but `xs plus item` appends a bare item without first
      wrapping it in a list — a different operation, not a stylistic
      choice. `when` is not spellable as `if`: `if` branches on a boolean
      condition the program already computed; `when` computes the
      condition itself, testing a record's shape and binding its fields in
      the same step (§74) — folding that into `if` would need pattern
      syntax inside a condition expression, which is the same new grammar
      either way.

    A rise is only legitimate when the word has no other spelling. If the
    argument is weaker than that, drop the feature instead.
    """
    assert len(KEYWORDS) <= 32, f"reserved list has grown to {len(KEYWORDS)}"
    for word in FORMER_KEYWORDS:
        assert word not in KEYWORDS, f"{word!r} should no longer be reserved"


def test_structural_words_are_still_reserved():
    for word in ("to", "give", "if", "else", "for", "each", "in",
                 "where", "let", "use", "why", "and", "or", "not", "of"):
        assert word in KEYWORDS, f"{word!r} must stay reserved"


# ================================================================ builtins still work

def test_builtins_work_when_not_shadowed():
    assert run("show text of (count of [1, 2, 3])") == ["3"]
    assert run('show lower of "ABC"') == ["abc"]
    assert run('show upper of "abc"') == ["ABC"]
    assert run("show text of (whole of 3.7)") == ["4"]


def test_user_definition_shadows_a_builtin():
    src = ('to count of xs:\n'
           '  give 999\n\n'
           'r = count of [1, 2, 3]')
    assert val(src, "r").value == 999


def test_shadowing_is_local_to_the_program():
    """A program that does not shadow still gets the builtin."""
    assert val("r = count of [1, 2, 3]", "r").value == 3


def test_builtin_arity_error_names_the_form():
    try:
        run("r = count of 1, 2")
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "wrong-arity"
        assert "count of x" in e.fix


# ================================================================ call syntax

def test_juxtaposed_argument_takes_the_whole_expression():
    """`ask "a" + text of n` is one call on the concatenation."""
    import json
    seen = []

    def stub(url):
        seen.append(url)
        return json.dumps({"ok": 1})

    run('use http\n'
        'n = 7\n'
        'x = ask "https://example.com/" + text of n + ".json"', http=stub)
    assert seen == ["https://example.com/7.json"]


def test_of_binds_tightly_but_juxtaposition_does_not():
    """The two call forms differ deliberately, and both are tested."""
    src = ("to double of n:\n  give n * 2\n\n"
           "a = double of 5 + 1")          # (double of 5) + 1
    assert val(src, "a").value == 11


def test_parenthesised_argument_continuing_an_expression():
    """`ask (base) + "/x"` is one argument, not an argument list."""
    import json
    seen = []

    def stub(url):
        seen.append(url)
        return json.dumps({})

    run('use http\n'
        'to base:\n'
        '  give "https://example.com"\n\n'
        'x = ask (base) + "/x.json"', http=stub)
    assert seen == ["https://example.com/x.json"]


def test_argument_list_still_works():
    src = "to add of a, b:\n  give a + b\n\nr = add(2, 3)"
    assert val(src, "r").value == 5


# ================================================================ analyser

def test_analyser_sees_effects_through_the_new_call_form():
    from shapes import analyse
    s = analyse('use http\nx = ask "https://example.com/a.json"')
    assert s.touches("network")
    assert s.at("network")[0].target == "https://example.com/a.json"


def test_shadowed_ask_is_not_an_effect():
    """If a user defines their own `ask`, it is not a network call."""
    from shapes import analyse
    s = analyse('to ask of x:\n  give x\n\nr = ask of 1')
    assert not s.touches("network"), \
        "a user function named ask must not be read as a network effect"


if __name__ == "__main__":
    fails = []
    tests = [(k, f) for k, f in sorted(globals().items()) if k.startswith("test_")]
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
