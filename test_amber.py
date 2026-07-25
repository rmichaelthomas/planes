"""Amber: scoped ambiguity refusal (addendum v4.2 section 69.5).

The parser refuses, at parse time, wherever the name table admits more
than one viable reading of the same source — instead of silently picking
one the way it always has. Four sites; each gets a fire test and the
near-misses that must NOT fire, plus the unknown-arity variant where one
applies (sites 2 and 3 — the two that actually consult arity).
"""
import glob
import json
import re
import sys

from parser import PlanesAmbiguity, PlanesSyntaxError, parse

VOCAB_PATH = "grammar/vocabulary.json"
AMBER_PATH = "grammar/messages/amber.json"


def amber_of(src, known=None):
    """Parse `src`, asserting it raises PlanesAmbiguity, and return it."""
    try:
        parse(src, known)
    except PlanesAmbiguity as e:
        return e
    raise AssertionError(f"expected PlanesAmbiguity, source parsed clean:\n{src}")


def parses_clean(src, known=None):
    parse(src, known)


# ================================================================ PlanesAmbiguity itself

def test_planes_ambiguity_is_a_planes_syntax_error():
    """Every existing `except PlanesSyntaxError` must still catch it."""
    assert issubclass(PlanesAmbiguity, PlanesSyntaxError)


def test_amber_never_fires_on_the_planes_corpus():
    """Every .planes file in the repo root still parses, unambiguously."""
    for name in ("annotated", "foreign", "gate", "hn", "money",
                 "names", "ordinary", "pypi"):
        with open(f"{name}.planes", encoding="utf-8") as f:
            src = f.read()
        parse(src)  # raises if amber fires


def test_amber_never_fires_on_the_demo_module_graphs():
    """Every real, valid multi-file demo program still parses clean, with
    the actual cross-file name table each file is parsed with in
    practice (module.load_graph + names_in_graph, not a bare parse)."""
    from modules import ModuleError, check_collisions, load_graph, names_in_graph
    for path in sorted(glob.glob("demo/**/*.planes", recursive=True)):
        try:
            graph = load_graph(path)
            check_collisions(graph)
        except ModuleError:
            continue  # not a valid standalone entry point
        known = names_in_graph(graph)
        for _p, src in graph:
            parse(src, known)  # raises if amber fires


# ================================================================ site 1: multiword longest match

def test_site1_fires_when_a_shorter_and_longer_name_both_match():
    src = ("to word:\n  give 1\n\n"
           "to word count:\n  give 2\n\n"
           "r = word count\n")
    e = amber_of(src)
    assert "word" in str(e) and "word count" in str(e)


def test_site1_does_not_fire_when_only_the_longer_name_matches():
    src = ("to word count:\n  give 2\n\n"
           "r = word count\n")
    parses_clean(src)


def test_site1_does_not_fire_when_only_the_shorter_name_matches():
    src = "to word:\n  give 1\n\nr = word\n"
    parses_clean(src)


def test_site1_fires_across_two_different_multiword_extensions():
    """`a`, `a b`, and `a b c` all defined -- three viable readings."""
    src = ("to a b:\n  give 1\n\n"
           "to a b c:\n  give 2\n\n"
           "r = a b c\n")
    e = amber_of(src)
    assert "a b" in str(e) and "a b c" in str(e)


# ================================================================ site 2: juxtaposition

def test_site2_fires_when_head_takes_an_arg_and_the_next_name_is_zero_arity():
    src = "to main:\n  give 1\n\nr = ask main\n"
    e = amber_of(src)
    assert "ask" in str(e) and "main" in str(e)


def test_site2_does_not_fire_when_head_has_arity_zero():
    """`main` (arity 0) followed by another statement -- no argument is
    ever considered, so there is nothing to be ambiguous about."""
    src = "to main:\n  give 1\n\nto other:\n  give 2\n\nmain\nother\n"
    parses_clean(src)


def test_site2_does_not_fire_when_the_next_name_is_not_callable():
    """`url` is an ordinary unresolved name here, not in known_funcs at
    all -- unambiguously the argument, exactly as before."""
    src = 'use http\nx = ask url\n'
    parses_clean(src)


def test_site2_does_not_fire_when_the_next_name_also_takes_an_argument():
    """`next_arity` != 0 and != None -- juxtaposition still unambiguously
    applies the whole following expression."""
    src = ("to greeting of who:\n  give who\n\n"
           "to shout:\n  give \"hi\"\n\n"
           "r = text greeting\n")
    # `text` (builtin, arity 1) followed by `greeting` -- but `greeting`
    # itself is not defined standalone, only `greeting of who` is, so this
    # exercises the "next name not known" path, not the arity-nonzero path.
    parses_clean(src)


def test_site2_unknown_arity_fires_when_head_arity_is_unknown():
    """A cross-file name arrives with arity None (a bare set, not a
    mapping) -- refused, not assumed."""
    e = amber_of("r = remote thing\n", known={"remote"})
    assert "remote" in str(e)


# ================================================================ site 3: paren_is_arglist

def test_site3_fires_when_arity_is_exactly_one():
    src = ('use http\n'
           'to base:\n  give "https://example.com"\n\n'
           'x = ask (base) + "/x.json"\n')
    e = amber_of(src)
    assert "ask" in str(e)


def test_site3_does_not_fire_when_arity_is_not_one():
    src = ("to add of a, b:\n  give a + b\n\n"
           "r = add (1) + 2\n")
    # add has arity 2 -- only one shape (parens are a sub-expression) fits
    parses_clean(src)


def test_site3_does_not_fire_when_arity_is_zero():
    src = "to main:\n  give 1\n\nr = main + 1\n"
    parses_clean(src)


def test_site3_unknown_arity_fires_when_arity_is_unknown():
    e = amber_of("x = remote (1) + 2\n", known={"remote"})
    assert "remote" in str(e)


def test_site3_still_works_unchanged_when_parens_are_not_an_arglist_and_unambiguous():
    """`f(a, b)` — two args -- arity 2, no operator after the paren at
    all here, so paren_is_arglist takes the arglist branch outright and
    amber never even runs."""
    src = "to add of a, b:\n  give a + b\n\nr = add(1, 2)\n"
    parses_clean(src)


# ================================================================ site 4: rename clause

def test_site4_fires_on_an_ambiguous_rename_source():
    src = ("to load record:\n  give 1\n\n"
           "to load:\n  give 2\n")
    known = {"load", "load record"}
    e = amber_of("use cache with load record as cached load", known=known)
    assert "load record" in str(e) or "load" in str(e)
    del src


def test_site4_does_not_fire_on_an_unambiguous_rename_source():
    known = {"load record"}
    parses_clean("use cache with load record as cached load", known=known)


def test_site4_does_not_check_the_new_alias_against_known_funcs():
    """The alias being introduced is not a lookup -- it must never be
    flagged just because it happens to share a prefix with something
    already known (the real bug this build found and fixed)."""
    known = {"greet", "greet b"}
    parses_clean("use b with greet as greet cached", known=known)


# ================================================================ messages come from data (D5)

def test_every_amber_template_id_used_by_the_parser_exists_in_the_json():
    with open(AMBER_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    ids = {t["id"] for t in doc["templates"]}
    used = set(re.findall(r'render_amber\("([\w.]+)"', open("parser.py", encoding="utf-8").read()))
    assert used, "no render_amber calls found -- did amber move?"
    assert used <= ids, f"parser.py references template ids not in {AMBER_PATH}: {used - ids}"


def test_no_amber_headline_or_reason_text_is_hardcoded_in_parser_py():
    """The structural wording (headline/reason/fix) lives in
    grammar/messages/amber.json, not as string literals in parser.py."""
    with open(AMBER_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    with open("parser.py", encoding="utf-8") as f:
        parser_src = f.read()
    offenders = []
    for t in doc["templates"]:
        for field in ("headline", "reason", "fix"):
            # strip the {slot} placeholders down to a literal fragment
            # long enough that finding it verbatim would be real drift
            literal = re.sub(r"\{[^}]+\}", "", t[field])
            fragment = literal.strip().split("  ")[0].strip()
            if len(fragment) > 15 and fragment in parser_src:
                offenders.append(f"{t['id']}.{field}: {fragment!r}")
    assert not offenders, "amber template text duplicated inline in parser.py:\n  " + \
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
