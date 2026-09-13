"""S4, Phase 3 — the JS lexer, checked against lexer.py.

js/lexer.mjs is a port of lexer.py's tokenize(). This test tokenizes every
.planes file in the repo with both implementations and compares the token
streams — the same check test_lexer_in_planes.py performs for the Planes lexer,
reusing its canonical form: a list of (kind, value, line) per token (A.3, reuse
the existing form, do not invent a fourth).

Target: 100% agreement. Per-file results are reported for anything short of it.
Included is grammar/lexer.mjs tokenizing grammar/lexer.planes — the Planes lexer
source, string escapes and all — against lexer.py.

The last section drives the places Python's `re` and `str` are Unicode-aware
and JavaScript's are not — `\\d`, `.`, `str.strip()`, code-point positions —
over every character Python counts as a digit or as whitespace, the same cases
test_swift_lexer.py drives through the Swift lexer. The corpus is ASCII, so the
corpus agreement above could never have seen them.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata

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


# ============================================== Unicode: Python's semantics, not JavaScript's

def _py_result(src):
    try:
        return [[t.kind, t.value, t.line] for t in pylexer.tokenize(src)]
    except pylexer.PlanesSyntaxError as e:
        return {"error": "PlanesSyntaxError", "message": str(e)}


def _agree_src(src):
    """The source is written byte-for-byte (no newline translation) and handed
    to lexer.py as the same string, so both lex exactly the same code points."""
    want = _py_result(src)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "m.planes")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(src)
        r = subprocess.run(
            [NODE, "js/cli.mjs", "tokens", p],
            cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed: {r.stderr}")
    got = json.loads(r.stdout)
    if isinstance(want, list) and isinstance(got, list):
        assert want == got, f"first divergence {first_divergence(want, got)}"
    else:
        assert want == got, f"js={got!r}\npy={want!r}"


def test_every_python_digit_is_a_number_and_nothing_else_is():
    """`\\d` in a Python str pattern is Unicode category Nd, at Python's
    Unicode version; in a JavaScript pattern it is 0-9. js/planes_text.mjs
    carries Python's set as a table, because `\\p{Nd}` is the JavaScript
    engine's Unicode version (Node 22 is a version ahead, and adds
    U+11DE0...U+11DE9) — those are driven here too, and must not lex as NUMBER."""
    digits = [chr(c) for c in range(0x110000) if unicodedata.category(chr(c)) == "Nd"]
    lines = [f"x = {d}{d}.{d} {d}. .{d} a{d}" for d in digits]
    lines += [f"y = {chr(c)}" for c in range(0x11DE0, 0x11DEA)]
    lines += ["z = ²³ ½ Ⅻ ①"]                        # numeric, but not Nd
    lines += ["w = ٣", "v = ١٢.٥ + 𝟙"]
    try:
        _agree_src("\n".join(lines) + "\n")
    except AssertionError as e:
        raise AssertionError(
            f"{e}\n(js/planes_text.mjs's digit table is Python 3.14's, Unicode "
            f"16.0; this Python is Unicode {unicodedata.unidata_version})") from None


def test_python_whitespace_is_what_strip_and_indentation_count():
    """str.strip() and str.lstrip() strip Python's isspace set — not
    JavaScript's trim(), which lacks U+001C...U+001F and U+0085 and adds
    U+FEFF. Each such character is used as indentation, as trailing space, as a
    whole line, and inside a line (where only space and tab are WS, and
    anything else is a skipped stray character)."""
    spaces = [chr(c) for c in range(0x110000) if chr(c).isspace() and c != 0x0A]
    near = ["\u180e", "\u200b", "\ufeff", "\u2060"]  # whitespace-like, not isspace
    lines = []
    for w in spaces + near:
        lines += ["a", f"{w}b{w}= 1{w}", f"{w}{w}c{w}+{w}2", f"{w}", "d"]
    try:
        _agree_src("\n".join(lines))
    except AssertionError as e:
        raise AssertionError(
            f"{e}\n(js/planes_text.mjs's whitespace set is Python 3.14's, Unicode "
            f"16.0; this Python is Unicode {unicodedata.unidata_version})") from None


def test_a_file_separator_indents_a_block():
    """The reported case: U+001C is indentation to Python, so `\\x1cy = 2`
    opens a block (BEGIN, then END) where trim() saw none."""
    _agree_src("x = 1\n\x1cy = 2\nz = 3\n")


def test_non_ascii_text_lexes_by_code_point():
    """Stray characters are skipped one code point at a time — an astral
    character is one position, never two UTF-16 units — and a combining mark
    after a quote is its own code point."""
    _agree_src("\n".join([
        'café = "naïve 👨‍👩‍👧 𝕏"',
        "é1 = x́y",
        'show "a"́ + "é"',
        "名前 = 1",
        'x = "\\"😀\\\\" # 😀 comment',
        "  y = 🙂-z - a-b-",
        "𝟘𝟙 = 😀𝟚😀.😀𝟛",
        "",
    ]))


def test_fingerprints_and_operators_at_their_edges():
    _agree_src("\n".join([
        "supersedes [r] @3f9c2d",
        "a @3f9c2 b @3f9c2d7 @ABCDEF @ghijkl @",
        "x = @３f9c2d",
        "a->b==c!=d<=e>=f<g>h(i)j.k,l;m:n[o]p{q}r+s-t*u/v=w",
        "1.5.2 3. .4 007",
        "",
    ]))


def test_line_endings_and_a_byte_order_mark():
    """Only "\\n" separates lines (src.split("\\n")); a carriage return is
    stripped whitespace at a line's edge and a stray character inside it. A
    leading byte-order mark is kept, as Python's utf-8 codec keeps it, and is
    not whitespace to str.strip() — so it opens no block, and a line holding
    only it and a comment still ends in EOL."""
    _agree_src("x = 1\r\n  y = 2\r\nz\r= 3\r")
    _agree_src("\ufeffx = 1\n")
    _agree_src("\ufeff  x = 1\n  y = 2\n")
    _agree_src("\ufeff# a comment\nx = 1\n")
    _agree_src(" x = 1 \n\x0c  y\x0b= 2\n")


def test_a_backslash_pairs_with_any_code_point_but_a_newline():
    """STRING's `\\.` is Python's `.`: every code point but "\\n". A
    JavaScript `.` also refuses "\\r", U+2028 and U+2029, which turned an
    unrecognized-escape error into an unterminated-string one."""
    for c in ["\r", "\u2028", "\u2029", "\x85", "😀"]:
        _agree_src(f'x = "a\\{c}b"\n')
        _agree_src(f'x = "a\\{c}"\n')


def test_malformed_strings_with_non_ascii_content_agree():
    _agree_src('x = "😀\\😀"')
    _agree_src('x = "é\\"')
    _agree_src('x = "naïve')


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
