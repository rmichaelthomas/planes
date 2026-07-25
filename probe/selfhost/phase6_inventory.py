#!/usr/bin/env python3
"""Phase 6 (PROBE_SELFHOST.md) — mechanical inventory of the core surface.

The two largest Planes programs in existence are grammar/lexer.planes (564
lines) and grammar/parser.planes (1118 lines). Whatever they actually use,
across ~1682 lines of real Planes, is the first evidence of what is core;
whatever the full 32/8/7 surface offers that they never touch is the first
evidence of what is not.

This does not eyeball the files. It tokenizes them with the language's own
lexer (lexer.tokenize) and tallies, per file and combined: every one of the
32 keywords (a keyword tokenizes to its own uppercased token kind), every one
of the 8 builtins (a NAME token whose value is a builtin), and every one of
the 7 effect kinds (a NAME token whose value is an effect kind — appearing in
a `foreign ... doing` clause or as the ask/read builtins). It also counts the
two bracket constructs that carry no keyword: record literals `{` and list
literals `[`.

Nothing is changed. This is a read-only census.
"""
import json
import sys

sys.path.insert(0, ".")
from lexer import tokenize  # noqa: E402

VOCAB = json.load(open("grammar/vocabulary.json"))
KEYWORDS = [k["word"] for k in VOCAB["keywords"]]
BUILTINS = [b["name"] for b in VOCAB["builtins"]]
EFFECT_KINDS = [e["kind"] for e in VOCAB["effect_kinds"]]
# Positional words (§ vocabulary.json positional_words) — grammar read at one
# site each, deliberately NOT in the 32. An inventory that ignored them would
# miss `may`, `is`, `because`, `supersedes`, `note`, `derives-from`.
POSITIONAL = ["may", "is", "because", "supersedes", "note", "derives-from"]

FILES = ["grammar/lexer.planes", "grammar/parser.planes"]


def census(path):
    toks = tokenize(open(path).read())
    kw = {w: 0 for w in KEYWORDS}
    bi = {w: 0 for w in BUILTINS}
    ek = {w: 0 for w in EFFECT_KINDS}
    pos = {w: 0 for w in POSITIONAL}
    braces = brackets = 0
    for t in toks:
        # a keyword tokenizes to KIND == word.upper(), value == word
        if t.value in kw and t.kind == t.value.upper():
            kw[t.value] += 1
        if t.kind == "NAME" and t.value in bi:
            bi[t.value] += 1
        if t.kind == "NAME" and t.value in ek:
            ek[t.value] += 1
        if t.kind == "NAME" and t.value in pos:
            pos[t.value] += 1
        if t.kind == "OP" and t.value == "{":
            braces += 1
        if t.kind == "OP" and t.value == "[":
            brackets += 1
    return kw, bi, ek, pos, braces, brackets


def merge(dicts):
    out = {}
    for d in dicts:
        for k, v in d.items():
            out[k] = out.get(k, 0) + v
    return out


def main():
    per_file = {p: census(p) for p in FILES}

    kw_all = merge([per_file[p][0] for p in FILES])
    bi_all = merge([per_file[p][1] for p in FILES])
    ek_all = merge([per_file[p][2] for p in FILES])
    pos_all = merge([per_file[p][3] for p in FILES])
    braces_all = sum(per_file[p][4] for p in FILES)
    brackets_all = sum(per_file[p][5] for p in FILES)

    print("# Phase 6 — inventory of grammar/lexer.planes + grammar/parser.planes")
    print("# tokenized with lexer.tokenize; counts are token occurrences\n")

    print("## KEYWORDS (32) — combined usage across both files")
    used = [(w, kw_all[w]) for w in KEYWORDS if kw_all[w] > 0]
    unused = [w for w in KEYWORDS if kw_all[w] == 0]
    for w, c in sorted(used, key=lambda x: -x[1]):
        print(f"  {c:>5}  {w}")
    print(f"\n  UNUSED keywords ({len(unused)}): {unused}\n")

    print("## BUILTINS (8) — combined usage")
    for w in BUILTINS:
        flag = "" if bi_all[w] else "   <-- UNUSED"
        print(f"  {bi_all[w]:>5}  {w}{flag}")
    print()

    print("## EFFECT KINDS (7) — combined usage (foreign doing-clauses / ask,read)")
    for w in EFFECT_KINDS:
        flag = "" if ek_all[w] else "   <-- UNUSED"
        print(f"  {ek_all[w]:>5}  {w}{flag}")
    print()

    print("## POSITIONAL WORDS (6, outside the 32) — combined usage")
    for w in POSITIONAL:
        flag = "" if pos_all[w] else "   <-- UNUSED"
        print(f"  {pos_all[w]:>5}  {w}{flag}")
    print()

    print("## BRACKET CONSTRUCTS (no keyword)")
    print(f"  {braces_all:>5}  record/when-pattern literals  {{ ... }}")
    print(f"  {brackets_all:>5}  list literals                 [ ... ]")
    print()

    print("## per-file keyword usage (for cross-checking)")
    for p in FILES:
        kw = per_file[p][0]
        u = sorted([(w, kw[w]) for w in KEYWORDS if kw[w] > 0], key=lambda x: -x[1])
        print(f"  {p}: {[w for w, _ in u]}")


if __name__ == "__main__":
    main()
