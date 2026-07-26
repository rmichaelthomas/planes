"""S4, Phase 3 — the JS lexer, checked against lexer.py.

js/lexer.mjs is a port of lexer.py's tokenize(). This test tokenizes every
.planes file in the repo with both implementations and compares the token
streams — the same check test_lexer_in_planes.py performs for the Planes lexer,
reusing its canonical form: a list of (kind, value, line) per token (A.3, reuse
the existing form, do not invent a fourth).

Target: 100% agreement. Per-file results are reported for anything short of it.
Included is grammar/lexer.mjs tokenizing grammar/lexer.planes — the Planes lexer
source, string escapes and all — against lexer.py.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

import lexer as pylexer

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))


def all_planes_files():
    files = sorted(
        f for f in glob.glob("**/*.planes", recursive=True)
        if ".venv" not in f)
    return files


def py_tokens(path):
    src = open(path, encoding="utf-8").read()
    return [[t.kind, t.value, t.line] for t in pylexer.tokenize(src)]


def js_tokens(path):
    r = subprocess.run(
        [NODE, "js/cli.mjs", "tokens", path],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed on {path}: {r.stderr}")
    return json.loads(r.stdout)


def first_divergence(a, b):
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i, a[i], b[i]
    if len(a) != len(b):
        return n, a[n] if n < len(a) else None, b[n] if n < len(b) else None
    return None


# ================================================================ full corpus agreement

def test_every_planes_file_tokenizes_identically():
    files = all_planes_files()
    assert len(files) >= 40, f"expected the whole .planes corpus, found {len(files)}"
    mismatches = []
    for f in files:
        want = py_tokens(f)
        got = js_tokens(f)
        if want != got:
            d = first_divergence(want, got)
            mismatches.append(f"{f}: first divergence {d}")
    assert not mismatches, "per-file token divergences:\n" + "\n".join(mismatches)


def test_the_js_lexer_tokenizes_the_planes_lexer_source_identically():
    """The bootstrap-shaped case: grammar/lexer.planes — a lexer for Planes
    written in Planes, with STRING literals and escapes throughout — tokenizes
    identically between js/lexer.mjs and lexer.py."""
    f = "grammar/lexer.planes"
    assert py_tokens(f) == js_tokens(f)


def test_the_js_lexer_tokenizes_the_interpreter_source_identically():
    """grammar/interp.planes is the largest Planes program (~1400 lines)."""
    f = "grammar/interp.planes"
    assert py_tokens(f) == js_tokens(f)


# ================================================================ malformed input agreement

def _js_tokens_src(tmp, src):
    p = os.path.join(tmp, "m.planes")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(src)
    r = subprocess.run(
        [NODE, "js/cli.mjs", "tokens", p],
        cwd=REPO, capture_output=True, text=True)
    return json.loads(r.stdout)


def test_an_unrecognized_escape_is_a_syntax_error_with_the_same_message():
    import tempfile
    src = 'x = "a\\zb"'
    try:
        pylexer.tokenize(src)
        assert False, "lexer.py should raise"
    except pylexer.PlanesSyntaxError as e:
        py_msg = str(e)
    with tempfile.TemporaryDirectory() as d:
        got = _js_tokens_src(d, src)
    assert isinstance(got, dict) and got["error"] == "PlanesSyntaxError", got
    assert got["message"] == py_msg, f"js={got['message']!r}\npy={py_msg!r}"


def test_a_trailing_backslash_unterminated_string_message_agrees():
    import tempfile
    src = 'x = "a\\"'
    try:
        pylexer.tokenize(src)
        assert False, "lexer.py should raise"
    except pylexer.PlanesSyntaxError as e:
        py_msg = str(e)
    with tempfile.TemporaryDirectory() as d:
        got = _js_tokens_src(d, src)
    assert got["message"] == py_msg, f"js={got['message']!r}\npy={py_msg!r}"


def test_a_plain_unterminated_string_message_agrees():
    import tempfile
    src = 'x = "abc'
    try:
        pylexer.tokenize(src)
        assert False, "lexer.py should raise"
    except pylexer.PlanesSyntaxError as e:
        py_msg = str(e)
    assert "backslash" not in py_msg
    with tempfile.TemporaryDirectory() as d:
        got = _js_tokens_src(d, src)
    assert got["message"] == py_msg, f"js={got['message']!r}\npy={py_msg!r}"


if __name__ == "__main__":
    if NODE is None:
        print("  SKIP  node not on PATH")
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
