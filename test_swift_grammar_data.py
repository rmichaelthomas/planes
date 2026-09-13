"""The Swift host's embedded grammar, held to the files it was copied from.

swift/Sources/Planes/Generated/GrammarData.swift carries grammar/vocabulary.json,
grammar/messages/amber.json and grammar/core.json verbatim, because the Swift
library has to run where this repo is not. A copy goes stale silently, so it is a
generated projection, like grammar/rules.json: scripts/swift_grammar_gen.py
writes it, and `--check` regenerates it in memory and fails on any difference.
This suite runs that check, so editing a grammar file without regenerating fails
the suites. It needs no Swift toolchain; the Swift side's own check (length and
hash, before parsing) is exercised by every test_swift_*.py that lexes.
"""
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile

from scripts import swift_grammar_gen as gen

REPO = os.path.dirname(os.path.abspath(__file__))


def test_the_embedded_grammar_is_up_to_date():
    r = subprocess.run([sys.executable, "scripts/swift_grammar_gen.py", "--check"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "up to date" in r.stdout, r.stdout


def test_check_fails_on_a_stale_copy():
    """The gate has teeth: a committed file that differs from what the generator
    produces is reported and exits non-zero."""
    stale = gen.generate().replace('"format": 1', '"format": 2', 1)
    saved = gen.OUT_PATH
    with tempfile.TemporaryDirectory() as d:
        gen.OUT_PATH = os.path.join(d, "GrammarData.swift")
        try:
            with open(gen.OUT_PATH, "w", encoding="utf-8", newline="") as f:
                f.write(stale)
            argv, sys.argv = sys.argv, ["swift_grammar_gen.py", "--check"]
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
    needs; the Swift embedding carries the same list."""
    with open(os.path.join(REPO, "js", "loader_node.mjs"), encoding="utf-8") as f:
        loader = f.read()
    read = sorted(p for p in re.findall(r'readJson\("\.\./(grammar/[^"]+)"\)', loader))
    assert read, "found no readJson calls in js/loader_node.mjs"
    assert sorted(rel for _, rel in gen.SOURCES) == read


def test_each_embedded_literal_holds_its_file_verbatim():
    """The raw literal's delimiter is chosen so no sequence in the file can end
    it or start an escape — checked here against the real files."""
    for _, rel in gen.SOURCES:
        with open(os.path.join(REPO, rel), encoding="utf-8", newline="") as f:
            text = f.read()
        lit = gen._literal(rel, text)
        hashes = lit[:lit.index('"')]
        body = lit[len(hashes) + 4:-(len(hashes) + 4)]
        assert body == text, rel
        assert '"' + hashes not in text and "\\" + hashes not in text, rel


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
