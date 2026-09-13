"""The JavaScript embedding's grammar data, held to the files it was copied
from.

js/embedded_grammar_data.mjs carries grammar/vocabulary.json,
grammar/messages/amber.json and grammar/core.json verbatim, so js/embed.mjs
(E2) can load the grammar synchronously with no `fs` read and no `fetch` — the
same problem scripts/swift_grammar_gen.py solves for the Swift host, by the
same route. A copy goes stale silently, so it is a generated projection, like
grammar/rules.json and Swift's own embedding: scripts/js_grammar_gen.py writes
it, and `--check` regenerates it in memory and fails on any difference. This
suite runs that check, so editing a grammar file without regenerating fails
the suites. It needs no Node; js/test/embedded_grammar_data.test.mjs is the
Node-side counterpart, loading the generated module for real and comparing it
to a fresh `fs` read.
"""
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile

from scripts import js_grammar_gen as gen

REPO = os.path.dirname(os.path.abspath(__file__))


def test_the_embedded_grammar_is_up_to_date():
    r = subprocess.run([sys.executable, "scripts/js_grammar_gen.py", "--check"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "up to date" in r.stdout, r.stdout


def test_check_fails_on_a_stale_copy():
    """The gate has teeth: a committed file that differs from what the generator
    produces is reported and exits non-zero."""
    stale = gen.generate().replace(
        'export const core', 'export const staleCore', 1)
    assert stale != gen.generate()
    saved = gen.OUT_PATH
    with tempfile.TemporaryDirectory() as d:
        gen.OUT_PATH = os.path.join(d, "embedded_grammar_data.mjs")
        try:
            with open(gen.OUT_PATH, "w", encoding="utf-8", newline="") as f:
                f.write(stale)
            argv, sys.argv = sys.argv, ["js_grammar_gen.py", "--check"]
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    assert gen.main() == 1
                assert "OUT OF DATE" in out.getvalue(), out.getvalue()
            finally:
                sys.argv = argv
        finally:
            gen.OUT_PATH = saved


def test_it_embeds_every_file_the_javascript_loader_reads():
    """js/loader_node.mjs's loadGrammar() is the list of grammar files a host
    needs; the generated embedding carries the same list."""
    with open(os.path.join(REPO, "js", "loader_node.mjs"), encoding="utf-8") as f:
        loader = f.read()
    read = sorted(p for p in re.findall(r'readJson\("\.\./(grammar/[^"]+)"\)', loader))
    assert read, "found no readJson calls in js/loader_node.mjs"
    assert sorted(rel for _, rel in gen.SOURCES) == read


def _unescape_template_literal(body):
    """The inverse of `_template_literal`'s three-pass escaping, applied as a
    single left-to-right scan the way a JS engine's own tokenizer reads
    escapes -- `\\\\` -> `\\`, `` \\` `` -> `` ` ``, `\\$` -> `$` (the
    trailing `{` is never consumed by the escape, so it stays a literal
    character right after -- which is exactly why escaping only the `$` is
    enough to stop `${` from starting a substitution)."""
    out = []
    i = 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body) and body[i + 1] in ("\\", "`", "$"):
            out.append(body[i + 1])
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def test_each_embedded_literal_holds_its_file_verbatim():
    """The template literal's escaping round-trips exactly -- checked here
    against the real files, including grammar/vocabulary.json's and
    grammar/messages/amber.json's backtick-containing notes."""
    for name, rel in gen.SOURCES:
        with open(os.path.join(REPO, rel), encoding="utf-8", newline="") as f:
            text = f.read()
        assert "`" in text, f"{rel} no longer exercises the backtick-escaping path"
        lit = gen._template_literal(rel, text)
        assert lit.startswith("`") and lit.endswith("`"), rel
        assert _unescape_template_literal(lit[1:-1]) == text, rel


def test_check_refuses_a_carriage_return_or_stray_control_character():
    """Refuse, don't guess: a template literal normalises CRLF to LF, and a
    stray control character has no place in grammar data, so both stop the
    generator rather than being embedded wrong silently."""
    for bad in ("line one\r\nline two\n", "bad\x07byte\n"):
        try:
            gen._template_literal("fake.json", bad)
        except gen.EmbedError:
            continue
        raise AssertionError(f"expected EmbedError for {bad!r}")


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
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
