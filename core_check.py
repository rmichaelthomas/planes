#!/usr/bin/env python3
"""core_check.py — does grammar/interp.planes stay inside the declared core?

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

Exit code is the count of violations (0 = conforms), so it drops into CI as a
gate. It also reports the two confirmations A.4 asks for -- whether `with` is
used, and whether all seven effect kinds are used -- and the core's real size
against the full 32/10/7 surface, which is the port surface for a second host.

Usage:  python3 core_check.py [file]     (default grammar/interp.planes)
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

from lexer import EFFECT_KINDS, KEYWORDS, tokenize  # noqa: E402
from parser import BUILTIN_NAMES  # noqa: E402
from shapes import analyse_file  # noqa: E402

CORE_PATH = os.path.join(REPO, "grammar", "core.json")
DEFAULT_TARGET = os.path.join("grammar", "interp.planes")


def load_core():
    with open(CORE_PATH, encoding="utf-8") as f:
        core = json.load(f)
    return set(core["keywords"]), set(core["builtins"]), core


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


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET
    core_keywords, core_builtins, core = load_core()

    print(f"core_check: {target} against grammar/core.json")
    print("=" * 72)

    viols = violations(target, core_keywords, core_builtins)
    if viols:
        print(f"\n{len(viols)} construct(s) OUTSIDE the declared core:\n")
        for line, cat, val in viols:
            print(f"  {target}:{line}  uses non-core {cat} '{val}'")
    else:
        print("\ninterp.planes conforms: no keyword or builtin outside the "
              "declared core.")

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

    sys.exit(len(viols))


def _toks(path):
    with open(path, encoding="utf-8") as f:
        return list(tokenize(f.read()))


if __name__ == "__main__":
    main()
