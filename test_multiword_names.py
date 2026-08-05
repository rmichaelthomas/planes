"""Multi-word names, called bare, as a STATEMENT.

test_names.py pins a multi-word name in *expression* position (`r = daily
count`). It does not pin the form checkpoint v26.0 section 405's teaching
plan depends on: a child's own English-phrase name, called bare on its own
line, with nothing assigning its result. That is the shape `paint/scene.planes`
and every starter program built on it actually use (`start`, `sky of "..."`,
etc. are all statement-position calls, and section 405 promises a child her
*own* zero-argument phrase works the same way).

Per the tutor.html build prompt section 3.4: if assertion 1 or 2 here fails,
that is a finding against checkpoint section 405, to be reported before
continuing the build rather than silently worked around.
"""
import os
import tempfile

from interp import Interpreter


def run(src, **kw):
    return Interpreter(**kw).run(src)


def test_multiword_zero_arg_name_called_bare_as_a_statement():
    """Assertion 1: `to the way it looked driving home:` with a
    `background of ...` body, called bare on its own line as a statement,
    produces the expected output line."""
    src = (
        'to the way it looked driving home:\n'
        '  show "background 0.5 0.1 200"\n'
        '\n'
        'the way it looked driving home\n'
    )
    assert run(src) == ["background 0.5 0.1 200"]


def test_multiword_zero_arg_name_called_bare_from_a_used_module():
    """Assertion 2: the same, defined in a `use`d module and called from
    the entry program."""
    with tempfile.TemporaryDirectory() as d:
        lib_path = os.path.join(d, "words.planes")
        entry_path = os.path.join(d, "entry.planes")
        with open(lib_path, "w") as f:
            f.write(
                'to the way it looked driving home:\n'
                '  show "background 0.5 0.1 200"\n'
            )
        with open(entry_path, "w") as f:
            f.write(
                'use words\n'
                '\n'
                'the way it looked driving home\n'
            )
        i = Interpreter()
        out = i.run_file(entry_path)
        assert out == ["background 0.5 0.1 200"]


def test_a_two_word_and_a_four_word_name_both_work_as_bare_statements():
    """Assertion 3: a two-word and a four-word name both work."""
    src = (
        'to morning light:\n'
        '  show "two words"\n'
        '\n'
        'to just before the storm:\n'
        '  show "four words"\n'
        '\n'
        'morning light\n'
        'just before the storm\n'
    )
    assert run(src) == ["two words", "four words"]


def test_a_hyphenated_equivalent_also_works_as_a_bare_statement():
    """Assertion 4: a hyphenated equivalent (`the-way-it-looked-driving-home`)
    also works — a single NAME token this time, rather than several joined
    at parse time."""
    src = (
        'to the-way-it-looked-driving-home:\n'
        '  show "background 0.5 0.1 200"\n'
        '\n'
        'the-way-it-looked-driving-home\n'
    )
    assert run(src) == ["background 0.5 0.1 200"]


if __name__ == "__main__":
    import sys
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
