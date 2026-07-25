"""Agreement test: lexer.py vs. grammar/lexer.planes (Route B stage one).

grammar/lexer.planes is a lexer for Planes, written in Planes, checked by
agreement with lexer.py's own tokenize() -- lexer.py's output is the
specification (fix/text-iteration-and-the-lexer's Phase 6).

PROBE_LEXER.md's original build found string-walking MISSING and stopped.
That branch closed it (for each over a string, PROBE_LEXER.md Phase 1),
but a *second*, independent gap surfaced while writing the lexer itself:
there was no way to write a Planes string literal containing a double
quote (grammar/vocabulary.json's STRING pattern had no escape sequences),
so lexer.planes had no way to test "is this character a quote" and could
not tokenize STRING -- every corpus file that reached for a string
diverged from lexer.py's stream at exactly that token, and nowhere else.

fix/string-escapes-and-bootstrap closes that gap: STRING literals admit
four escapes (\\" \\\\ \\n \\t), one of which -- \\" -- is precisely the
value lexer.planes needed and never had. grammar/lexer.planes's STRING
section (added there, not routed around) now tokenizes every corpus
file's *entire* stream identically to lexer.py, not just up to the first
STRING literal. These tests assert exactly that: full equality, file by
file, including lexer.planes's own source and grammar/vocabulary.planes
(the bootstrap assertion -- a lexer for Planes, written in Planes,
correctly tokenizing itself).

lexer-in-planes-verification.md carries the full per-file table these
assertions are drawn from.

A third, narrower gap remained even after full agreement: lexer.planes
could tokenize well-formed input identically to lexer.py, but had no
way to *raise* on malformed input the way lexer.py raises
PlanesSyntaxError, since no `to` function could manufacture a failure
from ordinary code. feat/fail-primitive-and-parser-probe's `fail
<message> as <tag>` closes that one too, at the exact site
grammar/lexer.planes's STRING section documented it in place -- the
malformed-input tests below check the message text itself agrees, not
only that both sides raise.
"""
import glob
import sys

import lexer as pylexer
from interp import Deriv, Interpreter, PlanesError, Traced

ROOT_CORPUS = ["annotated.planes", "foreign.planes", "gate.planes", "hn.planes",
              "money.planes", "names.planes", "ordinary.planes", "pypi.planes"]
DEMO_CORPUS = sorted(f for f in glob.glob("demo/**/*.planes", recursive=True)
                     if "cycle" not in f)
CORPUS = ROOT_CORPUS + DEMO_CORPUS

# The two files with no string literal at all -- established once, here,
# by scanning the real corpus, not asserted as a hardcoded belief. Kept
# as a standalone sanity check on corpus composition even though full
# agreement no longer needs to special-case them.
NO_STRING_FILES = [f for f in CORPUS if '"' not in open(f).read()]

_interp = Interpreter()
_interp.run_file("grammar/lexer.planes")


def _traced(v):
    return Traced(v, Deriv("literal", repr(v), v, []))


def planes_tokenize(src):
    result = _interp.call("tokenize", [_traced(src)], _interp.env)
    return [(t["kind"], t["text"], t["line"]) for t in result.value]


def python_tokenize(src):
    return [(t.kind, t.value, t.line) for t in pylexer.tokenize(src)]


def first_divergence(got, want):
    """Index of the first position where the streams differ, or the
    length of the shorter stream if one is a strict prefix of the
    other."""
    n = min(len(got), len(want))
    for i in range(n):
        if got[i] != want[i]:
            return i
    return n


# ================================================================ sanity: the corpus split itself

def test_corpus_is_the_30_files_report_grammar_amber_counts():
    """29 at REPORT_GRAMMAR_AMBER.md §4; 30 since demo/association.planes
    entered the corpus (fix/recursion-leak-and-fifth-amber-site Phase 3,
    P-Q15's corpus half)."""
    assert len(CORPUS) == 30, f"expected 30 corpus files, found {len(CORPUS)}"


def test_exactly_two_corpus_files_have_no_string_literal():
    # Established, not assumed: demo/pkgs/fetcher.planes and mathlib.planes
    # are the only corpus files that never reach for a string.
    assert NO_STRING_FILES == ["demo/pkgs/fetcher.planes", "demo/pkgs/mathlib.planes"], \
        NO_STRING_FILES


# ================================================================ agreement (full, not partial)

def test_every_corpus_file_matches_lexer_py_exactly():
    """30 PASS, 0 PARTIAL: every corpus file's token stream is now
    byte-identical between lexer.planes and lexer.py, string-bearing or
    not -- the STRING gap that used to cut every string-bearing file's
    agreement short is closed."""
    for fpath in CORPUS:
        src = open(fpath).read()
        want = python_tokenize(src)
        got = planes_tokenize(src)
        idx = first_divergence(got, want)
        assert got == want, f"{fpath}: expected a byte-identical token " \
                            f"stream, first divergence at {idx}"


# ================================================================ self-tokenization (bootstrap)

def test_lexer_planes_tokenizes_itself_exactly():
    """The first closed bootstrap assertion in this domain's history:
    grammar/lexer.planes -- a lexer for Planes, written in Planes --
    tokenizes its own source to the exact same stream lexer.py produces,
    with no divergence anywhere, including the STRING literals its own
    doc comments and pending-state records use throughout."""
    src = open("grammar/lexer.planes").read()
    want = python_tokenize(src)
    got = planes_tokenize(src)
    assert got == want, f"expected byte-identical self-tokenization, " \
                        f"first divergence at {first_divergence(got, want)}"


def test_lexer_planes_tokenizes_vocabulary_planes_exactly():
    src = open("grammar/vocabulary.planes").read()
    want = python_tokenize(src)
    got = planes_tokenize(src)
    assert got == want, f"expected byte-identical self-tokenization, " \
                        f"first divergence at {first_divergence(got, want)}"


# ================================================================ malformed input (fail primitive)
#
# lexer.planes's STRING section documented, in place, the one thing it
# could not do: raise its own error on malformed input the way lexer.py
# raises PlanesSyntaxError, because no `to` function could manufacture a
# failure. `fail <message> as <tag>` closes that gap, at the exact site
# that reported it -- these tests check the two implementations now
# agree on the message text itself, not just on well-formed input.
# lexer.planes raises PlanesError (a Planes program's only failure
# primitive); lexer.py raises PlanesSyntaxError (a host-language parse
# error) -- the two can never share an exception type, so what agreeing
# means here is the message text lexer.planes builds via `fail` equals
# the message text `str()` of lexer.py's exception.

def test_unrecognized_escape_messages_agree():
    src = 'x = "a\\zb"'
    try:
        pylexer.tokenize(src)
        assert False, "lexer.py should have raised"
    except pylexer.PlanesSyntaxError as e:
        py_msg = str(e)

    try:
        planes_tokenize(src)
        assert False, "lexer.planes should have raised"
    except PlanesError as e:
        assert e.detail == py_msg, f"planes: {e.detail!r}\npython: {py_msg!r}"


def test_unterminated_string_messages_agree_trailing_backslash():
    """The backslash consumed what looked like the closing quote --
    both implementations correctly blame the backslash."""
    src = 'x = "a\\"'
    try:
        pylexer.tokenize(src)
        assert False, "lexer.py should have raised"
    except pylexer.PlanesSyntaxError as e:
        py_msg = str(e)

    try:
        planes_tokenize(src)
        assert False, "lexer.planes should have raised"
    except PlanesError as e:
        assert e.detail == py_msg, f"planes: {e.detail!r}\npython: {py_msg!r}"


def test_unterminated_string_messages_agree_no_backslash_at_all():
    """A plain forgotten closing quote, no backslash anywhere on the
    line. Found during this build's own gate self-check (self-run, not
    deferred): the message used to say "a backslash right before the
    closing quote" even here, inventing one that never occurred --
    lexer.py distinguishes the two cases now (stripped[pos:].endswith
    ('"') -- an odd backslash count precedes a trailing quote only if
    one is actually there), and lexer.planes mirrors the distinction via
    ends-in-escaped-quote, a flag only ever true right after resolving
    \\" (the one path a literal quote can enter `text` by, since a raw
    `"` closes the token immediately rather than joining it)."""
    src = 'x = "abc'
    try:
        pylexer.tokenize(src)
        assert False, "lexer.py should have raised"
    except pylexer.PlanesSyntaxError as e:
        py_msg = str(e)
    assert "backslash" not in py_msg, \
        f"no backslash occurred in the source; message must not blame one: {py_msg!r}"

    try:
        planes_tokenize(src)
        assert False, "lexer.planes should have raised"
    except PlanesError as e:
        assert e.detail == py_msg, f"planes: {e.detail!r}\npython: {py_msg!r}"


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
