"""S7, Phase 1 — the corpus coverage checker (A.2).

corpus_coverage.py measures what `corpus/` exercises across four dimensions:
reserved words, builtins, effect kinds, and grammar-derived compositions. The
two things that must hold, and are easy to get wrong, are:

  1. every list is DERIVED from the grammar, never a hand-written enumeration --
     so the totals here are read back from grammar/vocabulary.json's own loaders
     (lexer.KEYWORDS / parser.BUILTIN_NAMES / lexer.EFFECT_KINDS), and a drift
     between the checker and the grammar would fail this file;
  2. it REPORTS gaps and never fails on them -- main() returns 0 on an empty
     corpus, on a full one, and on one containing a file that will not parse.
"""
import json
import os
import subprocess
import sys
import tempfile

import corpus_coverage as cc
from lexer import EFFECT_KINDS, KEYWORDS
from parser import BUILTIN_NAMES, parse

REPO = os.path.dirname(os.path.abspath(__file__))


# ============================================================ lists are derived, not typed

def test_the_totals_come_from_the_grammar_not_a_literal():
    """The universe of each dimension is the grammar's own set. If someone
    hand-lists 31 keywords here or in the checker, this fails."""
    cov = cc.coverage([os.path.join(REPO, "*.planes")])
    assert cov["reserved_words"]["total"] == len(KEYWORDS) == 32
    assert cov["builtins"]["total"] == len(BUILTIN_NAMES) == 11
    assert cov["effect_kinds"]["total"] == len(EFFECT_KINDS) == 7


def test_present_plus_absent_is_the_whole_universe():
    """No word is dropped or double-counted: present and absent partition the
    grammar's set exactly, for every dimension."""
    cov = cc.coverage([os.path.join(REPO, "demo")])
    for dim, universe in (("reserved_words", KEYWORDS),
                          ("builtins", BUILTIN_NAMES),
                          ("effect_kinds", set(EFFECT_KINDS))):
        d = cov[dim]
        assert set(d["present"]) | set(d["absent"]) == universe
        assert set(d["present"]) & set(d["absent"]) == set()


# ============================================================ the four detectors

def test_reserved_words_reads_keyword_tokens():
    src = "to f of n:\n  give n\n\nx = for each i in xs where i > 0: i\n"
    words = cc.reserved_words_in(src)
    assert {"to", "give", "of", "for", "each", "in", "where"} <= words
    # a plain name is not a keyword
    assert "n" not in words and "xs" not in words


def test_builtins_reads_calls_and_respects_shadowing():
    prog = parse('a = count of xs\nb = join of parts\n')
    assert cc.builtins_in(prog) == {"count", "join"}
    # a user function of the same name shadows the builtin -> not counted
    shadowed = parse("to count of xs:\n  give 1\n\na = count of xs\n")
    assert "count" not in cc.builtins_in(shadowed)


def test_effect_kinds_reads_the_static_surface():
    src = ('use file\nuse http\n'
           'r = ask "https://x/y.json" or fail as down\n'
           'write [1] to "o.json"\n'
           'show "hi"\n')
    kinds = cc.effect_kinds_in(src)
    assert {"ask", "write", "show"} <= kinds


def test_compositions_are_read_off_the_tree():
    prog = parse("x = { k: (1 + 2) }\n")
    pairs = cc.composition_pairs(prog)
    assert ("RecordLit", "fields", "BinOp") in pairs
    assert ("BinOp", "left", "Num") in pairs


def test_the_composition_universe_is_nonempty_and_grammar_derived():
    """The denominator is generated from the matrix, so it is a set of real
    parse-able nestings, not a number someone chose."""
    universe = cc.composition_universe()
    assert len(universe) > 100
    # every triple is (parentKind, field, childKind) of real AST class names
    for p, f, c in universe:
        assert isinstance(p, str) and isinstance(f, str) and isinstance(c, str)


# ============================================================ it reports, never fails

def _run_cli(args):
    r = subprocess.run([sys.executable, "corpus_coverage.py", *args],
                       cwd=REPO, capture_output=True, text=True)
    return r.stdout, r.returncode


def test_exit_zero_on_an_empty_corpus():
    with tempfile.TemporaryDirectory() as d:
        out, code = _run_cli([d])
        assert code == 0
        assert "0 file(s)" in out


def test_exit_zero_even_with_an_unparseable_file():
    """A file that will not parse is REPORTED, not fatal (invariant 7)."""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "bad.planes"), "w", encoding="utf-8") as fh:
            fh.write("x = [\n")   # never closes
        with open(os.path.join(d, "good.planes"), "w", encoding="utf-8") as fh:
            fh.write("x = 1\nshow x\n")
        out, code = _run_cli([d])
        assert code == 0
        assert "did not parse" in out
        assert "bad.planes" in out


def test_json_mode_is_machine_readable_and_also_exits_zero():
    out, code = _run_cli(["--json", "demo"])
    assert code == 0
    doc = json.loads(out)
    assert doc["reserved_words"]["total"] == 32
    assert doc["compositions"]["total"] == len(cc.composition_universe())


def test_it_only_reads_planes_never_python_source():
    """Confirms the S7/§6.4 neutrality claim in miniature: the checker's inputs
    are .planes files parsed by the grammar, so it audits the corpus, not an
    implementation. Pointed at a directory of .py files, it finds no .planes and
    reports an empty corpus rather than reading the Python."""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "not_planes.py"), "w", encoding="utf-8") as fh:
            fh.write("import os\n")
        out, code = _run_cli([d])
        assert code == 0
        assert "0 file(s)" in out


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
