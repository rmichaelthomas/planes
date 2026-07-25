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
from parser import Parser, parse, prescan_funcs, scan_names, tokenize

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
    assert len(doc["builtins"]) == 9
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


# ================================================================ arity in the name table (Phase B)

def test_prescan_funcs_returns_arity_from_the_of_clause():
    src = ("to fetch stories of source, limit:\n  give 1\n\n"
           "to main:\n  give 1\n")
    names = prescan_funcs(tokenize(src))
    assert names == {"fetch stories": 2, "main": 0}


def test_prescan_funcs_returns_arity_for_a_foreign_declaration():
    names = prescan_funcs(tokenize('foreign sort of xs from "builtins.sorted"'))
    assert names == {"sort": 1}


def test_parse_known_accepts_a_bare_set_with_unknown_arity():
    parse("r = 1", known={"foo bar"})
    assert Parser.known_funcs["foo bar"] is None


def test_parse_known_accepts_a_mapping_and_keeps_its_arity():
    parse("r = 1", known={"foo bar": 2})
    assert Parser.known_funcs["foo bar"] == 2


def test_local_definition_overrides_a_builtin_arity_in_known_funcs():
    """A local zero-arg redefinition of a builtin must be visible as arity
    0 to the parser, not the builtin's arity 1 -- shadowing (test_names.py)
    has to hold for parsing decisions, not just at call time."""
    parse("to count:\n  give 7\n\nr = count")
    assert Parser.known_funcs["count"] == 0


def test_every_builtin_has_arity_one_in_the_vocabulary():
    doc = load_vocab_doc()
    for b in doc["builtins"]:
        assert b["arity"] == 1, f"{b['name']!r} has arity {b['arity']}, expected 1"


def test_scan_names_is_still_dict_membership_compatible():
    names = scan_names('rule [readings-stay-local] readings may not ask')
    assert "readings-stay-local" not in names


# ================================================================ read_multiword_name (defect fix)

def test_read_name_until_is_gone():
    assert not hasattr(Parser, "read_name_until")
    assert hasattr(Parser, "read_multiword_name")


def test_use_rename_clause_still_reads_multiword_names_both_sides():
    from lexer import Use
    prog = parse("use cache with load record as load cached")
    assert prog == [Use("cache", (("load record", "load cached"),))]


def test_read_multiword_name_consumes_every_consecutive_name_token():
    """Pins the mechanism the old docstring implied but the code never
    implemented: it does not look for a specific stop word, it just reads
    NAME tokens until a non-NAME. A reserved word ends it even if that
    word was never named as a 'stop' anywhere."""
    p = Parser(tokenize("alpha beta gamma if"))
    assert p.read_multiword_name() == "alpha beta gamma"
    assert p.at("IF")


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


# ================================================================ escape-table drift guard

def test_committed_string_note_mentions_every_planes_text_escape():
    """The real, committed vocabulary.json against the real, committed
    planes_text.py -- the actual invariant grammar_gen.py's
    check_escape_table_matches_vocabulary_note() enforces at every run."""
    import grammar_gen
    doc = load_vocab_doc()
    note = next(tc["note"] for tc in doc["token_classes"] if tc["name"] == "STRING")
    assert grammar_gen._missing_escapes_in_note(note) == []


def test_missing_escapes_in_note_names_what_is_missing():
    import grammar_gen
    note_missing_tab = 'recognizes \\" \\\\ \\n only'
    assert grammar_gen._missing_escapes_in_note(note_missing_tab) == ["t"]


def test_missing_escapes_in_note_finds_nothing_when_all_four_present():
    import grammar_gen
    note_complete = 'recognizes \\" \\\\ \\n \\t, no others'
    assert grammar_gen._missing_escapes_in_note(note_complete) == []


def test_check_escape_table_exits_nonzero_when_the_note_is_missing_one():
    """The full check() function, against a deliberately broken copy of
    the real vocabulary.json -- not the real file, so this cannot leave
    the working tree dirty or race a concurrent test run."""
    import json
    import os
    import tempfile

    import grammar_gen

    doc = load_vocab_doc()
    for tc in doc["token_classes"]:
        if tc["name"] == "STRING":
            assert "\\t" in tc["note"]
            tc["note"] = tc["note"].replace("\\t", "")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(doc, f)
        broken_path = f.name

    original_path = grammar_gen.VOCAB_JSON_PATH
    grammar_gen.VOCAB_JSON_PATH = broken_path
    try:
        grammar_gen.check_escape_table_matches_vocabulary_note()
        assert False, "should have called sys.exit"
    except SystemExit as e:
        assert e.code != 0
    finally:
        grammar_gen.VOCAB_JSON_PATH = original_path
        os.unlink(broken_path)


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
