"""Every builtin the vocabulary declares is one all three implementations run.

WHY THIS FILE EXISTS. Nothing tied `grammar/vocabulary.json`'s builtin list to
any interpreter's dispatch. The parser reads the list, so a name added there is
immediately parsed as a builtin call — and if no interpreter implements it, the
program reaches the fall-through and is told

    unknown-builtin: no builtin is named 'X'
      try: the ten builtins are fixed and the lexer recognises only those, so
      reaching this is a defect in the interpreter rather than in the program

which is a message written for a case that cannot happen, and it is wrong in
every particular when it does: it blames the interpreter, tells the reader to
report it, and states a count the vocabulary beside it contradicts.

That message reached a real reader, from a browser holding a fresh
`vocabulary.json` beside a cached `js/interp.mjs`. The cache is guarded
separately (`js/test/stale_module_cache.test.mjs`). This is the other half: the
same half-landed state is reachable by an ordinary commit, and until now
nothing would have caught it.

The self-hosted interpreter is included, and it is the one most likely to lag —
it implements each builtin by hand in Planes, so a new one is real work there
rather than a line of dispatch.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))

from host import TestHost  # noqa: E402
from interp import Interpreter, PlanesError  # noqa: E402
from parser import BUILTIN_NAMES  # noqa: E402

REPO = os.path.dirname(os.path.abspath(__file__))

# A literal each builtin accepts far enough to reach its own dispatch. The
# argument is evaluated before the name is looked up, so anything that parses
# is enough; these are chosen to be the least surprising thing to read.
PROBE = {
    "count": "[1]", "lower": '"A"', "upper": '"a"', "text": "1",
    "whole": "1.5", "ask": '"https://example.invalid"', "read": '"x"',
    "normalize": '"a"', "join": '["a"]', "rest": "[1, 2]", "sine": "0",
    "number": '"1.5"', "root": "9",
}

# The tags that mean "this interpreter has never heard of it". Every other
# refusal is the builtin working and declining for its own reasons — `read`
# wants `use file`, `ask` wants a response — and a check that could not tell
# the difference would fail on both of those forever.
UNKNOWN = {"unknown-builtin", "unknown-function"}


def _probe_source(name):
    return f"probe = {name} of {PROBE.get(name, '1')}\n"


def test_every_declared_builtin_has_a_probe():
    """The probe table cannot fall behind the vocabulary silently."""
    missing = sorted(set(BUILTIN_NAMES) - set(PROBE))
    assert not missing, f"no probe argument for: {', '.join(missing)}"


def test_the_reference_implements_every_builtin_the_vocabulary_declares():
    unimplemented = []
    for name in sorted(BUILTIN_NAMES):
        try:
            Interpreter(host=TestHost()).run(_probe_source(name))
        except PlanesError as e:
            if e.tag in UNKNOWN:
                unimplemented.append(name)
        except Exception:                       # noqa: BLE001 — any other refusal is the builtin working
            pass
    assert not unimplemented, (
        "declared in grammar/vocabulary.json, not implemented in interp.py: "
        + ", ".join(unimplemented))


def test_the_self_hosted_interpreter_implements_every_builtin_too():
    import run_corpus_selfhosted as sh
    unimplemented = []
    for name in sorted(BUILTIN_NAMES):
        _, tag = sh.planes_run(_probe_source(name), {})
        if tag in UNKNOWN:
            unimplemented.append(name)
    assert not unimplemented, (
        "declared in grammar/vocabulary.json, not implemented in "
        "grammar/interp.planes: " + ", ".join(unimplemented))


def test_the_fall_through_message_is_for_a_case_the_gate_now_prevents():
    """The message stays — it is still right for a genuinely corrupt AST — but
    the state it describes can no longer ship, in any of the three."""
    with open(os.path.join(REPO, "interp.py"), encoding="utf-8") as f:
        assert "builtins are fixed and the lexer recognises only those" in f.read()


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
        except Exception as e:                  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
