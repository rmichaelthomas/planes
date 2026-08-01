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
    assert len(doc["builtins"]) == 13
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


def test_value_properties_section_records_exactness_descriptively():
    """value_properties follows positional_words's precedent exactly:
    hand-edited, descriptive-only, no loader consults it -- it exists
    because no other table in the repository records that every value
    carries an exact/approximate property (test_exactness.py exercises
    the property itself; this only holds the data-file record of its
    rules legible)."""
    doc = load_vocab_doc()
    assert "value_properties_note" in doc
    assert len(doc["value_properties"]) == 1
    exactness = doc["value_properties"][0]
    assert exactness["property"] == "exactness"
    assert exactness["values"] == ["exact", "approximate"]
    assert exactness["default"] == "exact"
    # Both operations that introduce approximation, and they do not do it the
    # same way -- `sine` at every argument, `root` only at some. The list held
    # only `sine` for two builds after `root` shipped.
    assert set(exactness["introduced_by"]) == {"sine", "root"}
    rule_names = {r["rule"] for r in exactness["rules"]}
    assert rule_names == {
        "entry", "named-precision-reduction-stays-exact", "propagation",
        "comparison", "static-derivability", "approximation-is-per-argument",
    }


def test_no_loader_reads_value_properties():
    """Descriptive only, like positional_words -- lexer.py and parser.py
    load grammar/vocabulary.json but must never branch on this section."""
    for module_path in ("lexer.py", "parser.py"):
        with open(module_path, encoding="utf-8") as f:
            assert "value_properties" not in f.read()


def test_binding_semantics_section_matches_the_language():
    """binding_semantics follows value_properties's and positional_words's
    precedent exactly: hand-edited, descriptive-only, no loader consults it --
    it exists because nothing else in the repository records, as data, what
    `let` does differently from bare assignment (V-Q5, reports/REPORT_VALUES.md).
    test_values.py's test_summing_a_list_in_a_loop_produces_the_sum and
    test_let_inside_a_loop_shadows_and_does_not_escape are the behaviour this
    section describes; this only holds the data-file record legible."""
    doc = load_vocab_doc()
    assert "binding_semantics_note" in doc
    assert len(doc["binding_semantics"]) == 2
    forms = {e["form"]: e for e in doc["binding_semantics"]}
    assert set(forms) == {"NAME = expression", "let NAME = expression"}
    assert forms["NAME = expression"]["binds"] == "rebinding"
    let_entry = forms["let NAME = expression"]
    assert let_entry["binds"] == "local"
    assert "hazard" in let_entry
    assert "discards it at the end of the iteration" in let_entry["hazard"]
    # The discarded-write build: this exact shape is no longer silent, and
    # the JSON must say so -- test_values.py's
    # test_let_accumulator_hazard_is_now_refused_a_q9 is the behaviour.
    assert "discarded-write" in let_entry["hazard"]
    assert "refused" in let_entry["hazard"]


def test_no_loader_reads_binding_semantics():
    """Descriptive only -- lexer.py and parser.py load
    grammar/vocabulary.json but must never branch on this section."""
    for module_path in ("lexer.py", "parser.py"):
        with open(module_path, encoding="utf-8") as f:
            assert "binding_semantics" not in f.read()


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


# ================================================================ the precedence ladder
#
# rules.json records `calls` per form but never named the one structure an
# agent most needs and cannot get from an unordered call graph: the binding
# order. It is derived from `calls`, never written down -- so these tests
# re-derive it independently rather than comparing it to a literal list, and
# then check the derivation against how the parser actually binds.

RULES_PATH = "grammar/rules.json"


def load_rules_doc():
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_the_ladder_is_the_calls_chain_walked_from_the_start():
    """Re-derived here from rules.json's own `calls` data, by the rule the
    section states: follow the single expression-level successor until a form
    has anything but one. Nothing in this test names a form."""
    doc = load_rules_doc()
    ladder = doc["precedence"]
    by_method = {f["parser_method"]: f for f in doc["forms"]}

    method = ladder["start"]
    walked = [by_method[method]["form"]]
    seen = {method}
    while True:
        successors = [c for c in by_method[method]["calls"] if c in by_method]
        if len(successors) != 1 or successors[0] in seen:
            break
        method = successors[0]
        seen.add(method)
        walked.append(by_method[method]["form"])

    assert ladder["loosest_first"] == walked
    assert len(walked) > 1


def test_every_level_is_a_real_parser_method():
    doc = load_rules_doc()
    for form in doc["precedence"]["loosest_first"]:
        assert hasattr(Parser, f"parse_{form}"), form


def test_the_ladder_says_what_it_is_not():
    """The same honesty rules.json's own note keeps about not being a BNF."""
    note = load_rules_doc()["precedence"]["note"]
    assert "not a grammar" in note
    assert "statement forms" in note
    assert load_rules_doc()["precedence"]["derived_from"] == "calls"


# One expression per adjacent pair in the ladder, and the shape it must have:
# the tighter level nested inside the looser one. This is the check that ties
# the derived order to the parser rather than to itself.
LADDER_BEHAVIOUR = [
    ("or", "and", "a or b and c", "(Var or (Var and Var))"),
    ("and", "not", "a and not b", "(Var and (not Var))"),
    ("not", "comparison", "not a == b", "(not (Var == Var))"),
    ("comparison", "plus", "a == [1] plus 2", "(Var == ([..] plus Num))"),
    ("plus", "additive", "[1] plus 2 + 3", "([..] plus (Num + Num))"),
    ("additive", "multiplicative", "1 + 2 * 3", "(Num + (Num * Num))"),
]


def _shape(n):
    t = type(n).__name__
    if t == "BinOp":
        return f"({_shape(n.left)} {n.op} {_shape(n.right)})"
    if t == "Not":
        return f"(not {_shape(n.expr)})"
    if t == "ListPlus":
        return f"({_shape(n.base)} plus {_shape(n.item)})"
    if t == "ListLit":
        return "[..]"
    return t          # `Num` for a literal, `Var` for a name


def test_the_derived_order_is_the_order_the_parser_binds_in():
    doc = load_rules_doc()
    order = doc["precedence"]["loosest_first"]
    for looser, tighter, src, expected in LADDER_BEHAVIOUR:
        assert order.index(looser) < order.index(tighter), \
            f"{looser} should be looser than {tighter} in {order}"
        got = _shape(parse(f"x = {src}\n")[0].expr)
        assert got == expected, f"{src} parsed as {got}, expected {expected}"


def test_every_adjacent_pair_in_the_ladder_that_can_be_shown_is_shown():
    """The behaviour table above covers every adjacent pair down to the last
    one two infix operators can express. Below `multiplicative` the levels are
    unary, postfix and primary, which bind by position rather than by an
    operator with something to its left, so there is no two-operator sentence
    to write for them."""
    order = load_rules_doc()["precedence"]["loosest_first"]
    covered = {(a, b) for a, b, _, _ in LADDER_BEHAVIOUR}
    infix = order[:order.index("multiplicative") + 1]
    for a, b in zip(infix, infix[1:]):
        assert (a, b) in covered, f"no behavioural check for {a} -> {b}"


def test_a_branching_chain_emits_no_ladder_rather_than_a_guess():
    """A parser change that branches the ladder must show up as an ABSENT
    section, not a wrong one -- a guessed ladder is the hand-written grammar
    ruling D2 declined, arrived at by a different route."""
    import grammar_gen

    forms = [
        {"parser_method": "parse_or", "form": "or",
         "calls": ["parse_and", "parse_comparison"]},
        {"parser_method": "parse_and", "form": "and", "calls": []},
        {"parser_method": "parse_comparison", "form": "comparison",
         "calls": []},
    ]
    levels, why = grammar_gen._precedence_ladder(forms)
    assert levels is None
    assert "does not have exactly one" in why


def test_a_cycle_emits_no_ladder():
    import grammar_gen

    forms = [
        {"parser_method": "parse_or", "form": "or", "calls": ["parse_and"]},
        {"parser_method": "parse_and", "form": "and", "calls": ["parse_or"]},
    ]
    levels, why = grammar_gen._precedence_ladder(forms)
    assert levels is None
    assert "revisits" in why


def test_a_missing_start_emits_no_ladder():
    import grammar_gen

    levels, why = grammar_gen._precedence_ladder(
        [{"parser_method": "parse_statement", "form": "statement",
          "calls": []}])
    assert levels is None
    assert "is not among the parser's forms" in why


def test_the_absent_ladder_says_so_in_the_generated_note():
    """rules.json's own note carries the reason, so a reader of the artifact
    learns the section is missing on purpose."""
    import grammar_gen

    doc = grammar_gen.generate_rules()
    assert "precedence" in doc
    assert "No `precedence` section is emitted" not in doc["note"]

    real = grammar_gen._precedence_ladder
    grammar_gen._precedence_ladder = lambda forms: (None, "the chain branches")
    try:
        broken = grammar_gen.generate_rules()
    finally:
        grammar_gen._precedence_ladder = real
    assert "precedence" not in broken
    assert "No `precedence` section is emitted: the chain branches." \
        in broken["note"]
    # The inventory itself is untouched either way.
    assert broken["count"] == doc["count"]
    assert broken["forms"] == doc["forms"]


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
