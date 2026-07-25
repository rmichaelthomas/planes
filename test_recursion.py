"""Tests for the recursion depth leak -- fix/recursion-leak-and-fifth-amber-
site, Ruling 2.

PROBE_PARSER.md capability 1 found the last Planes-level depth that
succeeds is 140; 141 raised a raw, uncaught Python RecursionError, not any
Planes-shaped failure. `unbound` v1.1 §22 item 1 locks that errors name the
fix, and a Python traceback names nothing. `invoke()` now catches
RecursionError narrowly -- only around the recursive re-entry through a
function's own body, nowhere else in the call machinery -- and re-raises
as a PlanesError naming the function and the iterative `for each` idiom
that replaces per-item recursion (PROBE_PARSER.md capability 4).

These tests assert the error's *shape* -- PlanesError, not RecursionError,
naming the function that recursed -- not a specific depth number, so they
do not break if the interpreter's call chain changes how many Python
frames one Planes-level call costs.
"""
import sys

from interp import Interpreter, PlanesError


def run(src, **kw):
    return Interpreter(**kw).run(src)


# Far past any plausible ceiling (measured at 140 in this build, see
# REPORT_RECURSION_AND_AMBER_SITE5.md) -- the point of these tests is the
# error's shape, not the exact depth, so a generous margin is deliberate.
DEEP = 2000


def countdown_src(n):
    return ('to countdown of n:\n'
            '  if n <= 0:\n'
            '    show "done"\n'
            '  else:\n'
            '    countdown of (n - 1)\n\n'
            f'countdown of {n}\n')


def mutual_src(n):
    return ('to is-even of n:\n'
            '  if n == 0:\n'
            '    give true\n'
            '  else:\n'
            '    give is-odd of (n - 1)\n\n'
            'to is-odd of n:\n'
            '  if n == 0:\n'
            '    give false\n'
            '  else:\n'
            '    give is-even of (n - 1)\n\n'
            f'show is-even of {n}\n')


# ================================================================ the leak is closed

def test_self_recursion_past_the_ceiling_raises_planes_error_not_recursion_error():
    try:
        run(countdown_src(DEEP))
        assert False, "should raise"
    except RecursionError:
        assert False, "RecursionError leaked past the Planes call boundary"
    except PlanesError as e:
        assert e.tag == "recursion-too-deep", e.tag
        assert "countdown" in e.detail, e.detail


def test_self_recursion_error_names_the_iterative_fix():
    try:
        run(countdown_src(DEEP))
        assert False, "should raise"
    except PlanesError as e:
        assert "for each" in e.fix, e.fix
        assert "cons-list" in e.fix, e.fix


def test_mutual_recursion_past_the_ceiling_raises_planes_error_not_recursion_error():
    try:
        run(mutual_src(DEEP))
        assert False, "should raise"
    except RecursionError:
        assert False, "RecursionError leaked past the Planes call boundary"
    except PlanesError as e:
        assert e.tag == "recursion-too-deep", e.tag
        assert "is-even" in e.detail or "is-odd" in e.detail, e.detail


# ================================================================ safe depth is unaffected

def test_self_recursion_at_a_safe_depth_still_works():
    assert run(countdown_src(10)) == ["done"]


def test_mutual_recursion_at_a_safe_depth_still_works():
    assert run(mutual_src(10)) == ["true"]


# ================================================================ catchable (v9.0 §106)

def test_recursion_too_deep_is_catchable_by_or_fail_as():
    src = ('to countdown of n:\n'
           '  if n <= 0:\n'
           '    show "done"\n'
           '  else:\n'
           '    countdown of (n - 1)\n\n'
           f'countdown of {DEEP} or fail as caught:\n'
           '  show caught.tag\n')
    assert run(src) == ["recursion-too-deep"]


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
