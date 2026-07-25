"""Tests for the Tier 2 error-handling changes (planes v9.0 A.4-A.5).

A.4: a comparison error carries a `path` — the list-index/record-field
steps from the root to a nested mismatch.

A.5: an error is a record, not just a renamed exception. `or fail as tag`
still renames-and-reraises by default (unchanged); followed by `:` and a
block, it instead catches, binds `tag` to an ordinary {tag, detail, [path]}
record, and runs the block — discriminated with the language's existing
if/field-access machinery. No new keyword, no new dispatch mechanism.
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


def val(src, name, **kw):
    return interp(src, **kw).env.get(name)


# ================================================================ A.4 -- comparison path

def test_top_level_mismatch_has_empty_path():
    try:
        run('x = (5 == "5")')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "cannot-compare"
        assert e.path == []


def test_path_through_nested_list():
    try:
        run('x = ([1, [2, "3"]] == [1, [2, 3]])')
        assert False, "should raise"
    except PlanesError as e:
        assert e.path == [1, 1]


def test_path_through_nested_record():
    try:
        run('x = ({a: {b: 1}} == {a: {b: "1"}})')
        assert False, "should raise"
    except PlanesError as e:
        assert e.path == ["a", "b"]


def test_non_comparison_error_has_no_path():
    """path is None -- not applicable -- for an unrelated error."""
    try:
        run('x = 1 / 0')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "divided-by-zero"
        assert e.path is None


def test_or_fail_rename_preserves_path():
    src = ('x = ([1, "2"] == [1, 2])\n'
           '  or fail as bad-compare\n')
    try:
        run(src)
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "bad-compare"
        assert e.path == [1]


# ================================================================ A.5 -- errors are records

def test_or_fail_without_handler_still_renames_and_reraises():
    """Unchanged default behavior -- no handler means no catch."""
    def boom(url):
        raise RuntimeError("connection refused")
    try:
        run('use http\nx = ask "https://example.com/a.json"\n'
            '  or fail as api-down',
            http=boom)
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "api-down"


def test_handler_binds_tag_detail_record():
    def boom(url):
        raise RuntimeError("connection refused")
    src = ('use http\n'
           'x = ask "https://example.com/a.json"\n'
           '  or fail as err:\n'
           '    show err.tag\n'
           '    show err.detail\n')
    assert run(src, http=boom) == ["err", "connection refused"]


def test_handler_not_run_on_success():
    src = ('use http\n'
           'x = ask "https://example.com/a.json"\n'
           '  or fail as err:\n'
           '    show "should not print"\n'
           'show x\n')
    assert run(src, http=lambda u: '"ok"') == ["ok"]


def test_handler_discriminates_with_if_and_field_access():
    """The '§74 shape dispatch' this build reuses: ordinary if + dot access."""
    def boom(url):
        raise RuntimeError("nope")
    src = ('use http\n'
           'x = ask "https://example.com/a.json"\n'
           '  or fail as err:\n'
           '    if err.tag == "err":\n'
           '      show "matched"\n'
           '    else:\n'
           '      show "unreached"\n')
    assert run(src, http=boom) == ["matched"]


def test_comparison_error_caught_by_handler_carries_path():
    src = ('x = ([1, [2, "3"]] == [1, [2, 3]])\n'
           '  or fail as err:\n'
           '    show err.tag\n'
           '    show text of (count of err.path)\n')
    assert run(src) == ["cannot-compare", "2"]


def test_error_without_path_has_no_path_field():
    src = ('use http\n'
           'x = ask "https://example.com/a.json"\n'
           '  or fail as err:\n'
           '    show (err.path is nothing)\n')
    assert run(src, http=lambda u: (_ for _ in ()).throw(RuntimeError("x"))) == ["true"]


def test_error_record_is_traceable_by_why():
    def boom(url):
        raise RuntimeError("nope")
    src = ('use http\n'
           'x = ask "https://example.com/a.json"\n'
           '  or fail as err:\n'
           '    why err\n')
    out = run(src, http=boom)
    assert out, "why produced output for the error record"


def test_write_to_or_fail_handler():
    src = ('use file\n'
           'write [1] to "o.json"\n'
           '  or fail as err:\n'
           '    show "unreached"\n'
           'show "wrote fine"\n')
    assert run(src, fs={}) == ["wrote fine"]


def test_bare_or_fail_statement_with_handler():
    def boom(u):
        raise RuntimeError("down")
    src = ('use http\n'
           '(ask "https://x/y") or fail as err:\n'
           '  show err.detail\n')
    assert run(src, http=boom) == ["down"]


def test_same_line_or_fail_with_handler():
    def boom(u):
        raise RuntimeError("down")
    src = 'use http\nx = ask "u" or fail as err:\n  show err.tag\n'
    assert run(src, http=boom) == ["err"]


# ================================================================ A.5 -- oracle soundness

def test_handler_effects_appear_in_static_surface():
    """A handler block's effects must show up in the static surface even
    though the analyser never executes anything (invariant 5 -- the
    runtime effect log and static surface always agree)."""
    src = ('use http\nuse file\n'
           'x = ask "https://example.com/a.json"\n'
           '  or fail as err:\n'
           '    write [err.tag] to "err.json"\n')
    s = analyse(src)
    assert s.kinds() == ["ask", "write"]


def test_shapes_never_raises_on_a_handler():
    """The analyser stays total (invariant 2)."""
    src = ('use http\n'
           'x = ask "https://example.com/a.json"\n'
           '  or fail as err:\n'
           '    y = 1 + 2\n')
    analyse(src)     # must not raise


def test_runtime_effects_are_a_subset_of_the_static_surface():
    src = ('use http\nuse file\n'
           'x = ask "https://example.com/a.json"\n'
           '  or fail as err:\n'
           '    write [err.tag] to "err.json"\n')
    s = analyse(src)
    static_kinds = set(s.kinds())

    def boom(url):
        raise RuntimeError("boom")
    i = Interpreter(http=boom, fs={})
    i.run(src)
    runtime_kinds = {e[0] for e in i.effects}
    assert runtime_kinds <= static_kinds, (runtime_kinds, static_kinds)

    i2 = Interpreter(http=lambda u: '"ok"', fs={})
    i2.run(src)
    runtime_kinds2 = {e[0] for e in i2.effects}
    assert runtime_kinds2 <= static_kinds, (runtime_kinds2, static_kinds)


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
