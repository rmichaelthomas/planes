"""Grammar as data (addendum v4.2 section 69.1).

grammar/vocabulary.json is the single source of truth for the language's
vocabulary -- KEYWORDS, BUILTIN_NAMES, EFFECT_KINDS, and
Parser.FIELD_NAME_KINDS all load from it. These tests hold two things:
that the load actually happened (no table silently reverted to a literal),
and that a missing or corrupt vocabulary file fails loudly rather than
guessing.
"""
import glob
import json
import re
import subprocess
import sys

import lexer
import parser as parser_mod

VOCAB_PATH = "grammar/vocabulary.json"


def load_vocab_doc():
    with open(VOCAB_PATH, encoding="utf-8") as f:
        return json.load(f)


# ================================================================ structure

def test_vocabulary_file_has_all_required_sections():
    doc = load_vocab_doc()
    for key in ("token_classes", "keywords", "builtins", "effect_kinds",
                "field_name_token_kinds"):
        assert key in doc, f"grammar/vocabulary.json is missing '{key}'"


def test_counts_match_what_the_repo_actually_has():
    doc = load_vocab_doc()
    assert len(doc["token_classes"]) == 7
    assert len(doc["keywords"]) == 32
    assert len(doc["builtins"]) == 8
    assert len(doc["effect_kinds"]) == 7
    assert len(doc["field_name_token_kinds"]) == 14


def test_token_spec_order_is_preserved_and_load_bearing():
    """FINGERPRINT must precede NUMBER; OP must follow NAME (failure mode
    10) -- a shuffled JSON array would silently mistokenize fingerprints
    and names, so this is asserted directly against both the JSON and the
    lexer's actual TOKEN_SPEC."""
    doc = load_vocab_doc()
    names = [t["name"] for t in doc["token_classes"]]
    assert names.index("FINGERPRINT") < names.index("NUMBER")
    assert names.index("OP") > names.index("NAME")
    assert [n for n, _ in lexer.TOKEN_SPEC] == names


def test_lexer_and_parser_tables_round_trip_the_json():
    doc = load_vocab_doc()
    assert lexer.KEYWORDS == {e["word"] for e in doc["keywords"]}
    assert lexer.EFFECT_KINDS == {e["kind"]: e["boundary"] for e in doc["effect_kinds"]}
    assert parser_mod.BUILTIN_NAMES == {b["name"] for b in doc["builtins"]}
    assert parser_mod.Parser.FIELD_NAME_KINDS == tuple(doc["field_name_token_kinds"])


def test_positional_words_are_not_in_keywords():
    """The six words kept out of KEYWORDS to protect the reserved-word
    ceiling (test_names.py) must actually be absent from it -- this is
    the fact grammar/vocabulary.json exists to make legible."""
    doc = load_vocab_doc()
    keyword_words = {e["word"] for e in doc["keywords"]}
    for entry in doc["positional_words"]:
        assert entry["word"] not in keyword_words, \
            f"{entry['word']!r} is both a positional word and a keyword"
        assert entry["reserved"] is False


# ================================================================ refuse, don't guess

def _run_with_vocab_missing(code):
    """Run `code` in a subprocess with grammar/vocabulary.json moved aside,
    so the in-process import cache is never disturbed."""
    import os
    moved = VOCAB_PATH + ".moved-for-test"
    os.rename(VOCAB_PATH, moved)
    try:
        return subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True)
    finally:
        os.rename(moved, VOCAB_PATH)


def test_missing_vocabulary_file_fails_loudly_not_silently():
    result = _run_with_vocab_missing("import lexer")
    assert result.returncode != 0
    assert "grammar-data-missing" in result.stderr
    assert "KeyError" not in result.stderr


def test_missing_vocabulary_file_fails_the_same_way_through_parser():
    result = _run_with_vocab_missing("import parser")
    assert result.returncode != 0
    assert "grammar-data-missing" in result.stderr


def test_corrupt_json_fails_loudly():
    import os
    with open(VOCAB_PATH, encoding="utf-8") as f:
        original = f.read()
    try:
        with open(VOCAB_PATH, "w", encoding="utf-8") as f:
            f.write("{ not valid json")
        result = subprocess.run([sys.executable, "-c", "import lexer"],
                                capture_output=True, text=True)
        assert result.returncode != 0
        assert "grammar-data-missing" in result.stderr
    finally:
        with open(VOCAB_PATH, "w", encoding="utf-8") as f:
            f.write(original)
    del os


def test_wrong_format_version_fails_loudly():
    import os
    with open(VOCAB_PATH, encoding="utf-8") as f:
        original = f.read()
    try:
        doc = json.loads(original)
        doc["format"] = 999
        with open(VOCAB_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        result = subprocess.run([sys.executable, "-c", "import lexer"],
                                capture_output=True, text=True)
        assert result.returncode != 0
        assert "grammar-data-missing" in result.stderr
        assert "999" in result.stderr
    finally:
        with open(VOCAB_PATH, "w", encoding="utf-8") as f:
            f.write(original)
    del os


# ================================================================ anti-drift
#
# Same style as test_planes.py's test_no_capital_shapes_in_source_or_readme
# and test_shapes.py's test_no_governance_vocabulary: a literal reappearing
# is drift, caught by grepping the actual source rather than trusting that
# nobody adds one back.

def test_no_hardcoded_vocabulary_literal_survives_anywhere():
    """One definition per table (consistency invariant 1). Each pattern
    below matches only a hand-written literal, never the legitimate
    `{e["word"] for e in _VOCAB[...]}`-style load, which starts with `{e`
    or `{b`, not `{"`."""
    offenders = []
    banned = [
        (r'KEYWORDS\s*=\s*\{\s*"', "a KEYWORDS set literal"),
        (r'BUILTIN_NAMES\s*=\s*\{\s*"', "a BUILTIN_NAMES set literal"),
        (r'EFFECT_KINDS\s*=\s*\{\s*"', "an EFFECT_KINDS dict literal"),
        (r'FIELD_NAME_KINDS\s*=\s*\(\s*"', "a FIELD_NAME_KINDS tuple literal"),
        (r'"SHOW",\s*"WRITE",\s*"FIRST"', "a re-duplicated field-name-kinds tuple"),
    ]
    for path in glob.glob("*.py"):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for pattern, label in banned:
            if re.search(pattern, text):
                offenders.append(f"{path}: {label}")
    assert not offenders, "hardcoded vocabulary literal(s) found:\n  " + \
                          "\n  ".join(offenders)


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
