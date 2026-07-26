"""S4, Phase 1 — the JS host seam, checked against host.py.

js/host.mjs is the JavaScript counterpart of host.py: the seven-method Host
interface and a NodeHost backend. This test pins each of the seven methods
directly against host.py's PythonHost behaviour for the same inputs — before
any of the rest of the port exists to lean on it (A.4: report whether eight was
the right number before the rest of the port makes it convenient to say yes).

It shells out to `node js/cli.mjs host <op>` and compares. Node's availability
is a §0 baseline fact for this build; if node is missing every test skips with a
clear message rather than failing spuriously.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from host import Host, PythonHost

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))

# The seven methods host.py requires (test_host.py's own list). random and env
# are foreign-only, so they are not host methods — the surface is exactly these.
# Seven since C4: `to_json` was declared and never called, and removing a dead
# method is not a substitution — see REPORT_FAST_FOLLOW.md's call-site table.
REQUIRED = ["ask", "read", "write", "show", "clock", "resolve",
            "parse_json"]


def _probe(backend, *args):
    r = subprocess.run(
        [NODE, "js/cli.mjs", backend, *args],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed ({r.returncode}): {r.stderr}")
    return r.stdout


def _node(*args):
    return _probe("host", *args)


def _skip_if_no_node():
    if NODE is None:
        print("  SKIP  node not on PATH")
        return True
    return False


# ================================================================ the surface is seven

def test_the_js_host_names_exactly_the_seven_methods():
    """The JS Host exposes the same seven methods as host.py's abstract Host —
    ask, read, write, show, clock, resolve, and reading JSON. `record` is
    optional on both and is not one of the seven.

    It was eight until C4 counted callers instead of declarations. Both
    implementations dropped `toJson` together: the seam is two implementations
    or it is not a seam."""
    present = json.loads(_node("methods"))
    # camelCase on the JS side, snake_case on the Python side; same seven.
    assert present == ["ask", "read", "write", "show", "clock",
                       "resolve", "parseJson"], present
    # The Python abstract Host has each of the seven too (test_host.py's line).
    for name in REQUIRED:
        assert hasattr(Host, name), name
    assert len(present) == len(REQUIRED) == 7
    assert "toJson" not in present


# ================================================================ the JSON boundary

def test_json_serialisation_is_byte_identical_to_python_json_dumps_indent_2():
    """A.4: it must be byte-identical to interp.py's, or a written file
    diverges (failure mode 1's sibling — the write effect's payload).

    C4 moved this off `host.toJson`, which nothing called, and onto
    `pyJsonDumps` — the serialiser `js/interp.mjs`'s module-level `toJson`
    actually hands its unwrapped value to on the write path. The assertion is
    unchanged; it now checks the code that runs. The Python side stays
    `json.dumps(v, indent=2)` written out, because that is exactly what
    `interp.py`'s own module-level `to_json` ends with."""
    cases = [
        [1, 2],
        {"a": 1, "b": [2, 3], "c": "hi"},
        [],
        {},
        "plain",
        {"nested": {"deep": [1, {"x": True, "y": None}]}},
        [1.5, -2.25, 0],
    ]
    for value in cases:
        got = _probe("json-dumps", json.dumps(value))
        want = json.dumps(value, indent=2)
        assert got == want, f"{value!r}\n got={got!r}\nwant={want!r}"


def test_json_serialisation_escapes_non_ascii_like_ensure_ascii():
    """json.dumps escapes non-ASCII (ensure_ascii=True); JSON.stringify does
    not. The JS side must match — a BMP char to \\uXXXX, an astral char to a
    surrogate pair — or a written file with any non-ASCII text diverges."""
    for value in ["café", "naïve", "😀", "a😀b", "Ω≈ç"]:
        got = _probe("json-dumps", json.dumps(value))
        want = json.dumps(value, indent=2)
        assert got == want, f"{value!r}\n got={got!r}\nwant={want!r}"


def test_parse_json_round_trips_like_python():
    py = PythonHost()
    for text in ['{"n": 1}', '[1, 2, 3]', '"s"', 'true', 'null',
                 '{"a": [1, {"b": 2}]}']:
        got = json.loads(_node("parse_json", text))
        want = py.parse_json(text)
        assert got == want, f"{text!r}: got={got!r} want={want!r}"


# ================================================================ foreign resolution

def test_resolve_matches_python_for_the_targets_the_corpus_names():
    """host.resolve is the one non-effect method interp.planes cannot stand in
    for (REPORT §Route B). The JS host resolves the targets the corpus actually
    uses — builtins.sorted/max/min — to the same results as PythonHost."""
    py = PythonHost()
    assert json.loads(_node("resolve", "builtins.sorted", "[[2,1,3]]")) \
        == py.resolve("builtins.sorted")([2, 1, 3]) == [1, 2, 3]
    assert json.loads(_node("resolve", "builtins.max", "[[2,1,3]]")) \
        == py.resolve("builtins.max")([2, 1, 3]) == 3
    assert json.loads(_node("resolve", "builtins.min", "[[2,1,3]]")) \
        == py.resolve("builtins.min")([2, 1, 3]) == 1


def test_resolve_sorts_strings_by_code_point_like_python():
    py = PythonHost()
    got = json.loads(_node("resolve", "builtins.sorted", '[["b","a","c"]]'))
    assert got == py.resolve("builtins.sorted")(["b", "a", "c"]) == ["a", "b", "c"]


def test_the_ambient_targets_resolve():
    """clock / random / env are foreign-only, reached through the ambient
    targets time.time / random.random / os.getcwd. The JS host resolves each."""
    t = float(json.loads(_node("resolve", "time.time", "[]")))
    assert t > 1_000_000_000        # a plausible epoch second
    r = float(json.loads(_node("resolve", "random.random", "[]")))
    assert 0.0 <= r < 1.0
    cwd = json.loads(_node("resolve", "os.getcwd", "[]"))
    assert isinstance(cwd, str) and len(cwd) > 0


def test_a_bad_foreign_target_raises_a_host_error_naming_the_convention():
    """PythonHost raises HostError('bad target') on a target with no dot; the
    JS host does the same, and its target hint names its own convention."""
    got = _node("resolve_bad", "nodots")
    assert got.startswith("HOSTERROR:"), got
    assert "bad target" in got


# ================================================================ filesystem

def test_write_then_read_round_trips_on_the_node_host():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "o.txt")
        assert _node("write", p, "hello\nworld") == "ok"
        assert _node("read", p) == "hello\nworld"
        # and Python's PythonHost reads the same bytes the JS host wrote.
        assert PythonHost().read(p) == "hello\nworld"


def test_python_writes_and_the_node_host_reads_the_same_bytes():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "in.txt")
        PythonHost().write(p, "from-python\n")
        assert _node("read", p) == "from-python\n"


def test_reading_a_missing_file_is_a_host_error_on_both():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "gone.txt")
        got = _node("read", p)
        assert got.startswith("HOSTERROR:"), got
        assert "no such file" in got
        # PythonHost's read raises too (its HostError surfaces as no-such-file
        # at the interp layer — Phase 5).
        try:
            PythonHost().read(p)
            assert False, "python read should raise"
        except (FileNotFoundError, OSError):
            pass


# ================================================================ clock, record

def test_the_clock_returns_a_plausible_epoch_second():
    t = float(_node("clock"))
    assert t > 1_000_000_000
    # PythonHost.clock() is time.time(); both are seconds since the epoch.
    assert abs(t - PythonHost().clock()) < 60


def test_record_is_an_optional_no_op_on_the_node_host():
    """host.py's record has a no-op default; the JS host matches — record must
    not throw, and it is not one of the eight required methods."""
    assert _node("record") == "ok"
    assert "record" not in REQUIRED


# ============================================= A.4: the browser backend, the same interface

def test_the_browser_backend_names_the_same_seven_methods():
    assert json.loads(_probe("host-browser", "methods")) == json.loads(_node("methods"))


def test_the_browser_backend_shares_the_json_boundary_and_resolver():
    """A.4: one interface, two implementations. The browser VFS host and the
    Node host read the same JSON and resolve the same targets — the JSON
    boundary is byte-identical to interp.py's on both.

    C4: the *writing* half of that boundary was `host.toJson`, which nothing
    called; the serialiser both hosts really share is `pyJsonDumps`, checked
    above and independent of which host is installed. What is left here is the
    half a host genuinely supplies — reading."""
    py = PythonHost()
    for value in [[1, 2], {"a": 1, "b": [2, 3]}, "café", "😀"]:
        js_value = json.dumps(value)
        assert json.loads(_probe("host-browser", "parse_json", js_value)) == \
            json.loads(_node("parse_json", js_value)) == py.parse_json(js_value)
    assert json.loads(_probe("host-browser", "resolve", "builtins.sorted", "[[3,1,2]]")) \
        == [1, 2, 3]
    got = _probe("host-browser", "resolve_bad", "nodots")
    assert got.startswith("HOSTERROR:") and "bad target" in got
    assert _probe("host-browser", "record") == "ok"    # optional no-op on both


if __name__ == "__main__":
    if _skip_if_no_node():
        sys.exit(0)
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
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
