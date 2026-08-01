#!/usr/bin/env python3
"""core_check.py — does grammar/interp.planes stay inside the declared core,
and does grammar/core.json still describe the language it claims to?

Run from the repo root:  python3 core_check.py

The obligation, open since the core subset was declared (checkpoint v10.0
§127, CORE_SUBSET.md): the core -- the subset a second host must implement to
run interp.planes -- was to be declared before interp.planes was written,
mechanically checkable, and derived from evidence. The first two held; this is
the third. interp.planes now exists, so the checker can finally run against the
thing it was written for.

Modelled on audit_locked_vs_built.py, inverted: that confirms every LOCKED
construct has code evidence; this confirms interp.planes uses NOTHING outside
the declared core. It reuses the language's own lexer.tokenize (so the checker
and the language never disagree about what a token is), reads the core from a
single JSON source of truth (grammar/core.json), and fails closed.

  - a keyword token whose value is not in core.keywords  -> violation
  - a NAME token that is a builtin not in core.builtins   -> violation
  - effect kinds are NEVER flagged: all seven are core (an interpreter
    performs whatever it interprets; Phase 5's shapes surface confirms it)

THE SECOND CHECK, AND WHY IT IS HERE. grammar/README.md splits grammar/ into
generated files, which `grammar_gen.py --check` gates, and hand-edited ones,
which nothing gated. core.json is hand-edited, and it drifted exactly as that
split predicts: it declared "11 of 12" builtins after the thirteenth was added,
and left `root` in neither its core list nor its `excluded_builtins` map, so a
builtin was outside the core with no recorded reason and nothing said so. This
file already computed both numbers and printed them side by side without ever
comparing them. Now it compares them:

  - a name in core.keywords / core.builtins the vocabulary no longer has
  - a keyword or builtin the vocabulary has that is neither core nor excluded
  - a name declared both core and excluded
  - a `size` string whose integers disagree with the real counts

The guard is here rather than in grammar_gen.py because grammar_gen.py never
reads or writes core.json, and grammar/README.md says so; putting it there
would falsify a documented property of the split. Reported in its own block:
"interp.planes uses something it may not" and "core.json describes a language
that is not this one" are different failures.

Exit code is the count of violations plus the count of drift findings (0 =
both clean), so it drops into CI as a gate. It also reports the two
confirmations A.4 asks for -- whether `with` is used, and whether all seven
effect kinds are used -- and the core's real size against the full 32/13/7
surface, which is the port surface for a second host.

Usage:  python3 core_check.py [file] [--core PATH]
        (defaults: grammar/interp.planes, grammar/core.json)
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

from lexer import EFFECT_KINDS, KEYWORDS, tokenize  # noqa: E402
from parser import BUILTIN_NAMES  # noqa: E402
from shapes import analyse_file  # noqa: E402

CORE_PATH = os.path.join(REPO, "grammar", "core.json")
DEFAULT_TARGET = os.path.join("grammar", "interp.planes")


def load_core(path=CORE_PATH):
    with open(path, encoding="utf-8") as f:
        core = json.load(f)
    return set(core["keywords"]), set(core["builtins"]), core


# ================================================================ the drift guard
#
# Pure over its inputs -- it takes the core document and the two vocabulary
# sets rather than reading either from disk, so a crafted core.json is a dict
# in a test and not a fixture on a path. The same shape as grammar_gen.py's
# `_missing_escapes_in_note`, and for the same reason.

def _declared_size(core, key):
    """The two integers in a `size` string like "11 of 13 -- ...", or None
    when it does not carry that shape. The prose after them is deliberately
    not parsed: the numbers are the claim, the prose is the reason."""
    text = core.get("size", {}).get(key)
    if not isinstance(text, str):
        return None
    m = re.match(r"\s*(\d+)\s+of\s+(\d+)", text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def drift(core, keywords, builtins, effect_kinds):
    """(finding, remedy) for every way grammar/core.json disagrees with the
    language's actual vocabulary. Empty when the two describe the same
    language."""
    out = []
    core_kw = set(core.get("keywords", []))
    core_bi = set(core.get("builtins", []))
    excl_kw = dict(core.get("excluded_keywords", {}))
    excl_bi = dict(core.get("excluded_builtins", {}))
    kw, bi = set(keywords), set(builtins)

    for label, declared, real, field in (
            ("keyword", core_kw, kw, '"keywords"'),
            ("builtin", core_bi, bi, '"builtins"'),
            ("keyword", set(excl_kw), kw, '"excluded_keywords"'),
            ("builtin", set(excl_bi), bi, '"excluded_builtins"')):
        for name in sorted(declared - real):
            out.append((
                f"{field} names {label} '{name}', which the vocabulary does "
                f"not have",
                f"remove it from grammar/core.json's {field}, or add it back "
                f"to grammar/vocabulary.json"))

    # The check that catches `root`: a builtin that is neither core nor
    # explained. A new one cannot pass silently.
    for label, real, declared, excluded, a, b in (
            ("keyword", kw, core_kw, set(excl_kw),
             '"keywords"', '"excluded_keywords"'),
            ("builtin", bi, core_bi, set(excl_bi),
             '"builtins"', '"excluded_builtins"')):
        for name in sorted(real - declared - excluded):
            out.append((
                f"{label} '{name}' is in neither {a} nor {b}",
                f"add it to grammar/core.json's {a} if grammar/interp.planes "
                f"uses it, or to {b} with the reason it does not"))
        for name in sorted(declared & excluded):
            out.append((
                f"{label} '{name}' is in both {a} and {b}",
                "delete it from one of them in grammar/core.json -- a "
                "construct is core or it is excluded, not both"))

    # `violations` never flags an effect kind, and this flag is the whole of
    # its licence to do that. If it is ever turned off, the checker is quietly
    # not checking a third of the surface.
    if core.get("effect_kinds_all_core") is not True:
        out.append((
            '"effect_kinds_all_core" is not true',
            "core_check.py never flags an effect kind on the strength of "
            "this flag -- set it true in grammar/core.json, or the effect "
            "kinds need a core list of their own and a check that reads it"))

    for key, in_core, real in (("keywords", len(core_kw), len(kw)),
                               ("builtins", len(core_bi), len(bi)),
                               ("effect_kinds", len(effect_kinds),
                                len(effect_kinds))):
        pair = _declared_size(core, key)
        if pair is None:
            out.append((
                f'"size"."{key}" does not start with `N of M`',
                f"write grammar/core.json's size.{key} as "
                f"`{in_core} of {real}`, with any reasoning after it"))
            continue
        if pair != (in_core, real):
            out.append((
                f'"size"."{key}" says {pair[0]} of {pair[1]}; the real '
                f"numbers are {in_core} of {real}",
                f"correct grammar/core.json's size.{key}"))
    return out


def violations(path, core_keywords, core_builtins):
    """(line, category, value) for every token outside the declared core."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    out = []
    for t in tokenize(src):
        # A keyword the language reserves but the core excludes.
        if t.value in KEYWORDS and t.kind not in ("STRING", "NUMBER") \
                and t.value not in core_keywords:
            out.append((t.line, "keyword", t.value))
        # A builtin name outside the core builtin set. Effect-kind names are
        # not special-cased: ask/read are builtins (checked here as builtins),
        # and clock/random/env are foreign targets, never flagged.
        if t.kind == "NAME" and t.value in BUILTIN_NAMES \
                and t.value not in core_builtins:
            out.append((t.line, "builtin", t.value))
    return out


def first_line_of_keyword(path, word):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    for t in tokenize(src):
        if t.value == word and t.kind not in ("STRING", "NUMBER"):
            return t.line
    return None


def _parse_args(argv):
    """(target, core_path). `--core PATH` so the drift guard can be run
    end to end against a crafted core.json, not only unit-tested."""
    argv = list(argv)
    core_path = CORE_PATH
    if "--core" in argv:
        i = argv.index("--core")
        if i + 1 >= len(argv):
            print("core_check.py: --core needs a path to a core.json")
            sys.exit(1)
        core_path = argv[i + 1]
        del argv[i:i + 2]
    return (argv[0] if argv else DEFAULT_TARGET), core_path


def main():
    target, core_path = _parse_args(sys.argv[1:])
    core_keywords, core_builtins, core = load_core(core_path)

    shown = os.path.relpath(core_path, REPO) if core_path.startswith(REPO) \
        else core_path
    print(f"core_check: {target} against {shown}")
    print("=" * 72)

    viols = violations(target, core_keywords, core_builtins)
    if viols:
        print(f"\n{len(viols)} construct(s) OUTSIDE the declared core:\n")
        for line, cat, val in viols:
            print(f"  {target}:{line}  uses non-core {cat} '{val}'")
    else:
        print("\ninterp.planes conforms: no keyword or builtin outside the "
              "declared core.")

    # --- The drift block. Its own heading because it means something else:
    # not "the file under test uses too much" but "the declaration it is
    # measured against no longer describes this language".
    drifts = drift(core, KEYWORDS, BUILTIN_NAMES, EFFECT_KINDS)
    print()
    if drifts:
        print(f"{len(drifts)} DRIFT(S) between {shown} and the vocabulary "
              f"grammar/vocabulary.json declares:\n")
        for finding, remedy in drifts:
            print(f"  {finding}")
            print(f"      -> {remedy}")
        print("\n  core.json is hand-edited and the vocabulary is not, so "
              "this is a\n  human edit that was never made, not a "
              "regeneration that was missed.")
    else:
        print(f"{shown} agrees with the vocabulary: every core and excluded "
              "name\nexists, every keyword and builtin is one or the other, "
              "and the sizes\nmatch the real counts.")

    # --- A.4 confirmation 1: is `with` used? Confirm it, or it leaves the core.
    with_line = first_line_of_keyword(target, "with")
    print()
    if with_line is not None:
        print(f"CONFIRMED: `with` is used ({target}:{with_line}) -- it stays "
              "in the core, prediction discharged (CORE_SUBSET.md §4).")
    else:
        print("NOT CONFIRMED: `with` is unused -- it should leave the core "
              "(CORE_SUBSET.md §4's prediction was wrong).")

    # --- A.4 confirmation 2: are all seven effect kinds used? (Phase 5 corrob.)
    surface = analyse_file(target, follow=True)
    kinds = {e.kind for e in surface.declared}
    all_seven = set(EFFECT_KINDS)
    if kinds >= all_seven:
        print(f"CONFIRMED: all seven effect kinds are used {sorted(all_seven)} "
              "-- the core includes them all (CORE_SUBSET.md §2a).")
    else:
        print(f"NOT CONFIRMED: effect kinds used are {sorted(kinds)}, "
              f"missing {sorted(all_seven - kinds)}.")

    # --- A.4 item 4: the core's real size -- the port surface for a 2nd host.
    used_keywords = sorted(
        {t.value for t in _toks(target)
         if t.value in KEYWORDS and t.kind not in ("STRING", "NUMBER")})
    used_builtins = sorted(
        {t.value for t in _toks(target)
         if t.kind == "NAME" and t.value in BUILTIN_NAMES})
    print()
    print("CORE SIZE (the port surface a second host must implement):")
    print(f"  keywords    : {len(used_keywords)} of {len(KEYWORDS)}  "
          f"(excluded: {sorted(set(KEYWORDS) - set(used_keywords))})")
    print(f"  builtins    : {len(used_builtins)} of {len(BUILTIN_NAMES)}  "
          f"(excluded: {sorted(set(BUILTIN_NAMES) - set(used_builtins))})")
    print(f"  effect kinds: {len(kinds & all_seven)} of {len(all_seven)}")
    print(f"  declared core.json: {len(core_keywords)} keywords, "
          f"{len(core_builtins)} builtins, all 7 effect kinds")

    sys.exit(len(viols) + len(drifts))


def _toks(path):
    with open(path, encoding="utf-8") as f:
        return list(tokenize(f.read()))


if __name__ == "__main__":
    main()
