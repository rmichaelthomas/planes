#!/usr/bin/env python3
"""core_check.py — does grammar/interp.planes AND EVERY MODULE IT REACHES stay
inside the declared core, and does grammar/core.json still describe the language
it claims to?

Run from the repo root:  python3 core_check.py

The obligation, open since the core subset was declared (checkpoint v10.0 §127,
reports/CORE_SUBSET.md): the core -- the subset a second host must implement to
run interp.planes -- was to be declared before interp.planes was written,
mechanically checkable, and derived from evidence. The first two held; this is
the third. interp.planes now exists, so the checker can finally run against the
thing it was written for.

"AND EVERY MODULE IT REACHES" was not in that first sentence for three builds,
and its absence was the whole of a real defect: a second host runs the graph,
not the entry file, and this checked the entry file. See "the module graph"
below.

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

Exit code is the count of entry-file violations, plus module-graph violations,
plus drift findings (0 = all three clean), so it drops into CI as a gate. It
also reports the two confirmations A.4 asks for -- whether `with` is used, and
whether all seven effect kinds are used -- and the port surface's real size
against the full 32/13/7 vocabulary, measured over the GRAPH, with the entry
file's own smaller usage printed beside it and the difference named.

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


# ================================================================ the module graph
#
# WHY THIS IS HERE, AND WHY IT GATES.
#
# `violations` tokenizes ONE FILE. The declared core was derived from
# grammar/interp.planes alone, and interp.planes conforms -- but interp.planes is
# not what a second host runs. It opens `use parser`, `use json`, `use file` and
# `use http`, so the artifact is interp.planes PLUS ITS MODULE GRAPH:
# parser.planes, json.planes, and lexer.planes and vocabulary.planes beneath them.
# core.json's claim is about the graph; the check was about one file.
#
# The core-restricted JavaScript interpreter (js/core_restrict.mjs) ran
# interp.planes and its graph under a host implementing only the declared core,
# and refused at grammar/lexer.planes:89 on `when` -- a keyword core.json then
# EXCLUDED, on a reason true of interp.planes and false of the graph
# interp.planes needs. All sixteen of lexer.planes's `when` sites are reached at
# evaluation time on an ordinary corpus file; none was dead.
#
# The gap was one keyword and `when` has since joined the core, restoring what
# reports/CORE_SUBSET.md §1.1 had listed as core all along, with
# grammar/parser.planes's node dispatch as its justifying program -- a program
# that used `when` twenty-eight times when the derivation was written and zero
# times by the time the exclusion was. That is why this block was a report for
# exactly one build and is a gate now: the only two ways to green it were
# rewriting the module or widening the core, and until somebody chose, a checker
# had no business failing a build over a decision nobody had made. The choice is
# made. The graph is green. A construct reaching past the core from inside a
# module now fails the gate exactly as one in the entry file always has, which is
# what the port surface claiming to be a port surface requires.

def graph_of(path):
    """Every file `path` reaches through `use`, in dependency order, itself last.
    The same resolution `analyse_file(target, follow=True)` already uses for
    effect kinds -- one half of this file's job followed the graph and the other
    did not."""
    from modules import load_graph
    return [p for p, _ in load_graph(path)]


def modules_reached(path):
    """The graph minus the entry file: what `use` pulls in, repo-relative where
    it can be, so a reader sees `grammar/lexer.planes` and not a home
    directory."""
    out = []
    for p in graph_of(path):
        if os.path.abspath(p) == os.path.abspath(path):
            continue
        out.append(os.path.relpath(p, REPO)
                   if os.path.abspath(p).startswith(REPO) else p)
    return out


def graph_violations(path, core_keywords, core_builtins):
    """(file, line, category, value) for every token outside the declared core,
    across the modules `path` reaches rather than `path` alone. The entry file is
    excluded because `violations` already gates on it -- this adds the half of
    the artifact nothing was reading, it does not restate the half that was."""
    out = []
    for p in modules_reached(path):
        for line, cat, val in violations(p, core_keywords, core_builtins):
            out.append((p, line, cat, val))
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

    # --- The graph block. IT GATES (see graph_of above and #64's ruling): the
    # entry file's own violations gate as they always have, and a module it
    # reaches through `use` is named, counted, and added to sys.exit's count
    # below exactly the same way -- a construct reached from inside a module
    # is outside the port surface exactly as one in the entry file is.
    reached = modules_reached(target)
    graph = graph_violations(target, core_keywords, core_builtins)
    print()
    if graph:
        offenders = sorted({p for p, _, _, _ in graph})
        print(f"{len(graph)} construct(s) outside the declared core in "
              f"{len(offenders)} of the {len(reached)} module(s) {target} "
              f"reaches through `use`:\n")
        for p, line, cat, val in graph:
            print(f"  {p}:{line}  uses non-core {cat} '{val}'")
        clean = [p for p in reached if p not in offenders]
        if clean:
            print(f"\n  the other {len(clean)} conform: " + ", ".join(clean))
        print("\n  THIS FAILS THE GATE. core.json's claim is about the artifact "
              "a second host\n  runs, which is this graph and not the entry "
              "file alone, so a construct\n  reached from inside a module is "
              "outside the port surface exactly as one\n  in the entry file is. "
              "Either implement it and add it to core.json's\n  \"keywords\" / "
              "\"builtins\", or rewrite the module so it does not need it.")
    elif reached:
        print(f"all {len(reached)} module(s) {target} reaches through `use` "
              "conform too:\n  " + ", ".join(reached))
    else:
        print(f"{target} reaches no modules through `use`.")

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
              "in the core, prediction discharged (reports/CORE_SUBSET.md §4).")
    else:
        print("NOT CONFIRMED: `with` is unused -- it should leave the core "
              "(reports/CORE_SUBSET.md §4's prediction was wrong).")

    # --- A.4 confirmation 2: are all seven effect kinds used? (Phase 5 corrob.)
    surface = analyse_file(target, follow=True)
    kinds = {e.kind for e in surface.declared}
    all_seven = set(EFFECT_KINDS)
    if kinds >= all_seven:
        print(f"CONFIRMED: all seven effect kinds are used {sorted(all_seven)} "
              "-- the core includes them all (reports/CORE_SUBSET.md §2a).")
    else:
        print(f"NOT CONFIRMED: effect kinds used are {sorted(kinds)}, "
              f"missing {sorted(all_seven - kinds)}.")

    # --- A.4 item 4: the core's real size -- the port surface for a 2nd host.
    #
    # THIS BLOCK USED TO REPORT THE ENTRY FILE AND CALL IT THE PORT SURFACE.
    # It was the same number for three builds, because interp.planes happened to
    # use every keyword the core declared -- and being the same number is how
    # nobody noticed they were different questions. A second host runs the GRAPH,
    # so the graph's usage is the port surface and the entry file's is a
    # component of it. Both are printed, labelled, because when they diverge the
    # difference is the interesting part: today it is `when`, used by
    # grammar/lexer.planes and by nothing above it.
    entry_kw, entry_bi = _used(target)
    graph_kw, graph_bi = _used(target, *modules_reached(target))
    print()
    print("PORT SURFACE (what a second host must implement to run the GRAPH):")
    print(f"  keywords    : {len(graph_kw)} of {len(KEYWORDS)}  "
          f"(unused: {sorted(set(KEYWORDS) - graph_kw)})")
    print(f"  builtins    : {len(graph_bi)} of {len(BUILTIN_NAMES)}  "
          f"(unused: {sorted(set(BUILTIN_NAMES) - graph_bi)})")
    print(f"  effect kinds: {len(kinds & all_seven)} of {len(all_seven)}")
    print(f"  declared core.json: {len(core_keywords)} keywords, "
          f"{len(core_builtins)} builtins, all 7 effect kinds")
    print()
    print(f"  {target} ALONE uses {len(entry_kw)} keywords and "
          f"{len(entry_bi)} builtins.")
    only_graph = sorted(graph_kw - entry_kw)
    if only_graph:
        print(f"  {sorted(graph_kw - entry_kw)} reach the port surface through "
              f"a module and not through it —\n  which is the whole reason this "
              f"checker follows `use`.")

    sys.exit(len(viols) + len(graph) + len(drifts))


def _toks(path):
    with open(path, encoding="utf-8") as f:
        return list(tokenize(f.read()))


def _used(*paths):
    """(keywords, builtins) actually used across `paths`. Reads through the
    language's own lexer, so the checker and the language never disagree about
    what a token is."""
    kw, bi = set(), set()
    for p in paths:
        for t in _toks(p):
            if t.value in KEYWORDS and t.kind not in ("STRING", "NUMBER"):
                kw.add(t.value)
            if t.kind == "NAME" and t.value in BUILTIN_NAMES:
                bi.add(t.value)
    return kw, bi


if __name__ == "__main__":
    main()
