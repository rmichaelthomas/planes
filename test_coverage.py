"""Does the oracle reach every part of the language?

The oracle — every runtime effect must appear in the static surface — is the
one check that can catch an unsound analyser. It is only as good as the code
it runs over.

That is not hypothetical. FFI shipped with an untested runtime path: every
foreign call logged its effect kind as a tuple rather than a string, making
the runtime effect log unreadable for the whole feature, and a suite of 179
tests could not see it. The oracle existed, was correct, and never ran over a
foreign declaration.

So this file tests the test. It walks every AST node type the language can
produce and requires that an oracle run exercises each one. A feature added
without a corresponding oracle case fails here rather than in production.
"""
import io
import contextlib
import os
import sys

import lexer
from parser import parse
from test_foreign import check_oracle


# Every node type a program can contain. Derived from the module rather than
# listed by hand, so a new node is covered the moment it is defined.
ALL_NODES = {
    name for name, obj in vars(lexer).items()
    if hasattr(obj, "__dataclass_fields__") and name != "Token"
}


# One oracle-checkable program per node type. Each must both run and be
# analysable, so every case ends with an effect the surface can be compared
# against — an oracle run with no effects proves nothing.
# A case is a source string, or a (source, interpreter kwargs) pair when the
# node needs a stubbed boundary. Tests never touch the real network.
COVERAGE = {
    "Num":     'use file\nx = 1\nwrite [x] to "o.json"',
    "Str":     'use file\ns = "a"\nwrite [s] to "o.json"',
    "Bool":    'use file\nb = true\nwrite [b] to "o.json"',
    "Nothing": 'use file\nn = nothing\nwrite [1] to "o.json"',
    "Var":     'use file\nx = 1\ny = x\nwrite [y] to "o.json"',
    "ListLit": 'use file\nxs = [1, 2]\nwrite xs to "o.json"',
    "RecordLit": 'use file\nr = { a: 1 }\nwrite [r] to "o.json"',
    "BinOp":   'use file\nx = 1 + 2\nwrite [x] to "o.json"',
    "Not":     'use file\nb = not false\nwrite [b] to "o.json"',
    "IsNothing": 'use file\nn = nothing\nb = n is nothing\nwrite [b] to "o.json"',
    "Field":   ('use http\nr = ask "https://example.com/a.json"\n'
                'show text of r.name',
                {"http": lambda u: '{"name": "x"}'}),
    "Assign":  'use file\nx = 1\nwrite [x] to "o.json"',
    "Why":     'use file\nx = 1 + 1\nwhy x\nwrite [x] to "o.json"',
    "Use":     'use file\nwrite [1] to "o.json"',
    "FuncDef": 'use file\nto one:\n  give 1\n\nwrite [one] to "o.json"',
    "Call":    'use file\nto twice of n:\n  give n * 2\n\n'
               'write [twice of 2] to "o.json"',
    "Give":    'use file\nto one:\n  give 1\n\nwrite [one] to "o.json"',
    "Show":    'show "hello"',
    "ForEach": 'use file\nys = for each x in [1, 2]: x * 2\n'
               'write ys to "o.json"',
    "If":      'use file\nif 1 > 0:\n  write [1] to "a.json"\n'
               'else:\n  write [2] to "b.json"',
    "OrFail":  'use file\nwrite [1] to "o.json"\n'
               'r = (read "o.json") or fail as no-file',
    # `Builtin` is unreachable: builtins became ordinary functions, so the
    # parser now emits Call for `count of xs`. The node and its handling in
    # interp.py and shapes.py are dead code. Listed here so the node-coverage
    # test stays honest about why it is not exercised.
    "Builtin": None,
    "WriteTo": 'use file\nwrite [1] to "o.json"',
    "Round":   'use file\nx = round 2.675 to 2 places\nwrite [x] to "o.json"',
    "Foreign": 'foreign now from "time.time" doing clock\nt = now',
    "Rule":    'rule [no-telemetry] anything may not ask\n'
               'use file\nwrite [1] to "o.json"',
}


def nodes_in(src):
    """Every node type appearing in a parsed program."""
    found = set()
    stack = list(parse(src))
    while stack:
        n = stack.pop()
        found.add(type(n).__name__)
        for f in getattr(n, "__dataclass_fields__", {}):
            v = getattr(n, f)
            if hasattr(v, "__dataclass_fields__"):
                stack.append(v)
            elif isinstance(v, list):
                stack.extend(x for x in v
                             if hasattr(x, "__dataclass_fields__"))
    return found


# ================================================================ the test

UNREACHABLE = {n for n, src in COVERAGE.items() if src is None}


def test_every_node_type_has_a_coverage_case():
    """A new AST node must arrive with an oracle case, or an explicit None
    marking it unreachable."""
    missing = ALL_NODES - set(COVERAGE)
    assert not missing, (
        "these node types have no oracle coverage case:\n  "
        + "\n  ".join(sorted(missing))
        + "\nAdd one to COVERAGE in this file.")


def test_every_coverage_case_actually_contains_its_node():
    """A case that does not produce the node it claims covers nothing."""
    wrong = []
    for node, src in sorted(COVERAGE.items()):
        if src is None:
            continue
        src = src[0] if isinstance(src, tuple) else src
        try:
            if node not in nodes_in(src):
                wrong.append(f"{node}: its case does not produce a {node}")
        except Exception as e:
            wrong.append(f"{node}: case failed to parse — {e}")
    assert not wrong, "\n  ".join([""] + wrong)


def test_the_oracle_holds_for_every_node_type():
    """The point of the file: run the oracle over the whole language."""
    failures = []
    for node, src in sorted(COVERAGE.items()):
        if src is None:
            continue
        src, kw = src if isinstance(src, tuple) else (src, {})
        kw.setdefault("fs", {})      # never touch the real disk
        try:
            check_oracle(src, **kw)
        except AssertionError as e:
            failures.append(f"{node}: {e}")
        except Exception as e:
            failures.append(f"{node}: {type(e).__name__}: {e}")
    assert not failures, "\n  ".join([""] + failures)


def test_runtime_effect_kinds_are_always_strings():
    """The specific shape of the bug this file exists because of.

    A logged effect kind that is not a string makes the runtime log — the
    ground truth the static surface is checked against — unreadable, without
    failing anything that only inspects the surface.
    """
    from interp import Interpreter
    bad = []
    for node, src in sorted(COVERAGE.items()):
        if src is None:
            continue
        src, kw = src if isinstance(src, tuple) else (src, {})
        kw.setdefault("fs", {})
        i = Interpreter(**kw)
        try:
            i.run(src)
        except Exception:
            continue
        for e in i.effects:
            if not isinstance(e[0], str):
                bad.append(f"{node}: logged kind {e[0]!r}")
    assert not bad, "\n  ".join([""] + bad)


def test_unreachable_nodes_are_actually_unreachable():
    """A node marked unreachable must really be one — otherwise the marker
    is a way to opt out of coverage."""
    import parser as parser_mod
    src = open(parser_mod.__file__).read()
    for node in sorted(UNREACHABLE):
        assert f"{node}(" not in src, \
            f"{node} is marked unreachable but the parser still builds it"


def test_the_suite_does_not_touch_the_real_world():
    """No test may write to the real filesystem.

    Found while extracting the host seam: four tests had been writing real
    files to the repository for several sessions. The old in-memory default
    hid it — remove the default and the leak became visible immediately.

    That is the argument for the seam in miniature. An implicit host lets
    'what actually happens' drift away from 'what the test says happens',
    and nothing fails. An explicit one makes the drift a test failure.
    """
    import glob
    import subprocess

    suites = sorted(glob.glob("test_*.py"))
    before = set(glob.glob("*.json"))
    leaks = {}
    for suite in suites:
        if suite == os.path.basename(__file__):
            continue
        subprocess.run([sys.executable, suite],
                       capture_output=True, timeout=300)
        now = set(glob.glob("*.json")) - before
        if now:
            leaks[suite] = sorted(now)
            for f in now:
                os.remove(f)

    assert not leaks, (
        "these suites wrote real files:\n  "
        + "\n  ".join(f"{k}: {', '.join(v)}" for k, v in leaks.items())
        + "\nPass an in-memory host, e.g. `interp(src, fs={})`.")


def test_coverage_is_derived_not_listed():
    """ALL_NODES comes from the lexer module, so a node added without a
    coverage case fails automatically rather than being silently ignored."""
    assert "Foreign" in ALL_NODES
    assert "Round" in ALL_NODES
    assert len(ALL_NODES) >= 20


if __name__ == "__main__":
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
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
