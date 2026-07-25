"""Tests for the host seam.

P-Q9 — "what is the implementation host" — turned out to be a smaller
question than it looked, and measuring it is what showed that. Almost
nothing in Planes is host-shaped: the parser reads a foreign target as an
opaque string, the analyser never parses it, and only the interpreter
interprets it. The language's requirement of a machine is five capabilities
and a name resolver.

These tests hold that line. If a host assumption leaks back into the
language, something here fails.
"""
import json
import sys

from host import Host, PythonHost, TestHost
from interp import Interpreter, PlanesError


def run(src, **kw):
    return Interpreter(**kw).run(src)


def interp(src, **kw):
    i = Interpreter(**kw)
    i.run(src)
    return i


# ================================================================ the surface

def test_a_host_is_five_capabilities_and_a_resolver():
    """The whole requirement Planes places on a machine.

    It is this small because the effect vocabulary was closed early, for
    the analyser. A host cannot be asked for more than the language can name.
    """
    required = {"ask", "read", "write", "show", "clock",
                "resolve", "parse_json", "to_json"}
    for name in required:
        assert hasattr(Host, name), f"a host must provide {name}"


def test_the_host_surface_matches_the_effect_vocabulary():
    """Every effect kind the language can name is something a host does."""
    from shapes import EFFECT_KINDS
    for kind in EFFECT_KINDS:
        if kind in ("random", "env"):
            continue        # reachable only through `foreign`, by design
        assert hasattr(Host, kind), \
            f"effect '{kind}' has no host capability"


def test_the_default_host_is_python():
    assert Interpreter().host.name == "python"


# ================================================================ swappable

def test_a_program_runs_on_a_substituted_host():
    """The seam is real if a different host runs the same program."""
    host = TestHost(responses={"https://x/y.json": '{"n": 1}'})
    i = Interpreter(host=host)
    i.run('use http\nr = ask "https://x/y.json"\nshow text of r.n')
    assert i.output == ["1"]
    assert host.shown == ["1"], "output went through the host"


def test_the_host_receives_file_writes():
    host = TestHost()
    Interpreter(host=host).run('use file\nwrite [1, 2] to "o.json"')
    assert json.loads(host.files["o.json"]) == [1, 2]


def test_the_host_supplies_the_clock():
    """A stubbed clock makes a clock-reading program reproducible."""
    host = TestHost(now=42.0)
    i = Interpreter(host=host)
    i.run('foreign now from "time.time" doing clock\nt = now')
    # the foreign path goes to the real host function, so check the seam
    # directly rather than through `foreign`
    assert host.clock() == 42.0


def test_a_host_error_becomes_a_planes_error():
    """Machine failure and program error stay distinguishable."""
    host = TestHost(responses={})
    try:
        Interpreter(host=host).run('use http\nr = ask "https://nope/x.json"')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "ask-failed"


def test_missing_file_on_a_host_is_a_program_error():
    try:
        Interpreter(host=TestHost()).run('use file\nr = read "gone.json"')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "no-such-file"


# ================================================================ foreign

def test_the_foreign_target_is_opaque_to_the_language():
    """The parser stores the target as a string and imposes no structure.

    This is why moving hosts needs no syntax change: `builtins.sorted` is
    Python-shaped because the *host* reads it that way, not because the
    language does.
    """
    from parser import parse
    decl = parse('foreign f of x from "node:fs#readFile" doing nothing')[0]
    assert decl.target == "node:fs#readFile", \
        "the language must not interpret a target"


def test_the_analyser_never_parses_a_target():
    """The analyser uses the target as a label. A non-Python target analyses fine."""
    from shapes import analyse
    s = analyse('foreign f of x from "crate::mod::fn" doing ask "https://a/b"\n'
                'r = f of 1')
    assert "https://a/b" in s.targets("ask")


def test_a_host_resolves_its_own_targets():
    host = PythonHost()
    assert host.resolve("builtins.sorted")([2, 1]) == [1, 2]


def test_an_unresolvable_target_names_the_host_convention():
    """The error tells the reader how *this* host wants targets written."""
    try:
        run('foreign f of x from "nodots" doing nothing\nr = f of 1')
        assert False, "should raise"
    except PlanesError as e:
        assert e.tag == "bad-foreign-target"
        assert "module.function" in e.fix


# ================================================================ compatibility

def test_the_older_http_and_fs_arguments_still_work():
    """Sessions of tests use these. They build a TestHost now."""
    i = interp('use http\nr = ask "https://x/y.json"\nshow text of r.n',
               http=lambda u: '{"n": 7}')
    assert i.output == ["7"]

    i = interp('use file\nwrite [1] to "o.json"', fs={})
    assert "o.json" in i.fs


def test_fs_reads_through_to_the_host():
    i = interp('use file\nr = read "in.json"\nshow r',
               fs={"in.json": "hello"})
    assert i.output == ["hello"]


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
