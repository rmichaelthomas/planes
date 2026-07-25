"""Agreement test: lexer.py vs. grammar/lexer.planes (Route B stage one).

grammar/lexer.planes is a lexer for Planes, written in Planes, checked by
agreement with lexer.py's own tokenize() -- lexer.py's output is the
specification (fix/text-iteration-and-the-lexer's Phase 6).

PROBE_LEXER.md's original build found string-walking MISSING and stopped.
This branch closed that gap (for each over a string, PROBE_LEXER.md
Phase 1), but a *second*, independent gap surfaced while writing the
lexer itself: there is no way to write a Planes string literal containing
a double quote (grammar/vocabulary.json's STRING pattern has no escape
sequences), and no builtin converts a code point to or from its numeric
value -- so lexer.planes has no way to test "is this character a quote"
and cannot tokenize STRING. Documented at length in grammar/lexer.planes
itself, at the point the gap is hit.

That gap has one precise, checkable consequence: the two token streams
must agree on every token up to the first STRING literal a file
contains, and disagree from there (a quoted string's contents come out
as whatever they tokenize into on their own terms -- names, numbers,
operators -- instead of one STRING token). That is exactly what these
tests assert, file by file, rather than asserting blanket equality and
leaving 27 of 29 corpus files failing for a reason already understood
and written down.

lexer-in-planes-verification.md carries the full per-file table this
file's assertions are drawn from.
"""
import glob
import sys

import lexer as pylexer
from interp import Deriv, Interpreter, Traced

ROOT_CORPUS = ["annotated.planes", "foreign.planes", "gate.planes", "hn.planes",
              "money.planes", "names.planes", "ordinary.planes", "pypi.planes"]
DEMO_CORPUS = sorted(f for f in glob.glob("demo/**/*.planes", recursive=True)
                     if "cycle" not in f)
CORPUS = ROOT_CORPUS + DEMO_CORPUS

# The two files with no string literal at all -- established once, here,
# by scanning the real corpus, not asserted as a hardcoded belief.
NO_STRING_FILES = [f for f in CORPUS if '"' not in open(f).read()]
STRING_FILES = [f for f in CORPUS if f not in NO_STRING_FILES]

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

def test_corpus_is_the_29_files_report_grammar_amber_counts():
    assert len(CORPUS) == 29, f"expected 29 corpus files, found {len(CORPUS)}"


def test_exactly_two_corpus_files_have_no_string_literal():
    # Established, not assumed: demo/pkgs/fetcher.planes and mathlib.planes
    # are the only corpus files that never reach for a string.
    assert NO_STRING_FILES == ["demo/pkgs/fetcher.planes", "demo/pkgs/mathlib.planes"], \
        NO_STRING_FILES


# ================================================================ agreement

def test_files_with_no_string_literal_match_lexer_py_exactly():
    for fpath in NO_STRING_FILES:
        src = open(fpath).read()
        want = python_tokenize(src)
        got = planes_tokenize(src)
        assert got == want, f"{fpath}: expected an exact match, first " \
                            f"divergence at {first_divergence(got, want)}"


def test_string_bearing_files_agree_up_to_their_first_string_literal():
    for fpath in STRING_FILES:
        src = open(fpath).read()
        want = python_tokenize(src)
        got = planes_tokenize(src)
        idx = first_divergence(got, want)
        assert idx < len(want), \
            f"{fpath}: planes stream never diverges from a shorter-or-equal " \
            f"python stream -- expected a STRING literal to cause one"
        assert want[idx][0] == "STRING", \
            f"{fpath}: unexpected divergence at token {idx} -- " \
            f"got {got[idx] if idx < len(got) else None!r}, want {want[idx]!r}"
        assert got[:idx] == want[:idx], \
            f"{fpath}: streams differ before the first STRING literal " \
            f"(at token {idx}), which should be impossible if " \
            f"first_divergence found idx correctly"


# ================================================================ self-tokenization (Phase 7)

def test_lexer_planes_tokenizes_itself_up_to_its_own_first_string_literal():
    src = open("grammar/lexer.planes").read()
    want = python_tokenize(src)
    got = planes_tokenize(src)
    idx = first_divergence(got, want)
    assert idx < len(want), "expected lexer.planes's own STRING literals to diverge"
    assert want[idx][0] == "STRING", \
        f"unexpected self-tokenization divergence at token {idx}: " \
        f"got {got[idx] if idx < len(got) else None!r}, want {want[idx]!r}"
    assert got[:idx] == want[:idx]


def test_lexer_planes_tokenizes_vocabulary_planes_up_to_first_string_literal():
    src = open("grammar/vocabulary.planes").read()
    want = python_tokenize(src)
    got = planes_tokenize(src)
    idx = first_divergence(got, want)
    assert idx < len(want), "expected vocabulary.planes's own STRING literal(s) to diverge"
    assert want[idx][0] == "STRING", \
        f"unexpected self-tokenization divergence at token {idx}: " \
        f"got {got[idx] if idx < len(got) else None!r}, want {want[idx]!r}"
    assert got[:idx] == want[:idx]


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
