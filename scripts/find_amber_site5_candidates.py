#!/usr/bin/env python3
"""Detection-only pass for the fifth amber site (Ruling 3, fix/recursion-
leak-and-fifth-amber-site).

`of` binds its argument to a single `parse_unary()` primary — tighter than
every binary operator (`+ - * / < > <= >= == != and or plus in`), all of
which live above it in the precedence chain (parser.py parse_comparison /
parse_plus / parse_additive / parse_multiplicative). So `f of x - 1` always
parses as `(f of x) - 1`, never `f of (x - 1)`, even though a reader who
does not already know `of`'s precedence could plausibly expect the second
reading. This is exactly amber's own complaint at its other four sites:
two readings are possible, and nothing in the surface syntax says which.

This script finds every place in the corpus where that shape occurs —
`NAME of <bare-primary>` immediately followed by a binary operator token —
using the real tokenizer (lexer.tokenize), not a text regex, so it agrees
with the parser's own token stream. It changes nothing; it only reports.
Phase 2b reads AMBER_SITE5_BLAST_RADIUS.md, the file this script writes,
and decides from the measurement whether to land the fifth site.

"Bare primary" here means the argument is a single NUMBER literal, or a
single NAME that does not itself continue into a nested call (a following
OF, a following "(", or a following NAME that could extend a multi-word
name) — i.e., precisely the shape parse_unary() would resolve to one token
before the operator ambiguity could apply.
"""
import glob
import sys

sys.path.insert(0, ".")
from lexer import tokenize  # noqa: E402

BINOP_STARTS = {"+", "-", "*", "/", "<", ">", "<=", ">=", "==", "!="}
BINOP_KEYWORDS = {"AND", "OR", "PLUS", "IN"}


def find_planes_files():
    files = set()
    files.update(glob.glob("*.planes"))
    files.update(glob.glob("demo/**/*.planes", recursive=True))
    files.update(glob.glob("grammar/**/*.planes", recursive=True))
    files.update(glob.glob("probe/**/*.planes", recursive=True))
    return sorted(files)


def is_binop_start(tok):
    if tok.kind == "OP" and tok.value in BINOP_STARTS:
        return True
    if tok.kind in BINOP_KEYWORDS:
        return True
    return False


def find_candidates(path):
    src = open(path, encoding="utf-8").read()
    try:
        toks = tokenize(src)
    except Exception as e:  # noqa: BLE001 -- a malformed probe fixture is not this pass's concern
        print(f"  (skipped {path}: tokenize failed: {e})", file=sys.stderr)
        return []

    hits = []
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        if t.kind == "NAME" and i + 1 < n and toks[i + 1].kind == "OF":
            arg_idx = i + 2
            if arg_idx >= n:
                i += 1
                continue
            arg = toks[arg_idx]
            after_idx = None
            if arg.kind == "NUMBER":
                after_idx = arg_idx + 1
            elif arg.kind == "NAME":
                nxt = toks[arg_idx + 1] if arg_idx + 1 < n else None
                # A following OF/(/NAME means the argument keeps extending
                # into a nested call or multi-word name -- not bare.
                if nxt is not None and (nxt.kind == "OF"
                                        or (nxt.kind == "OP" and nxt.value == "(")
                                        or nxt.kind == "NAME"):
                    after_idx = None
                else:
                    after_idx = arg_idx + 1
            if after_idx is not None and after_idx < n and is_binop_start(toks[after_idx]):
                op_tok = toks[after_idx]
                hits.append((t.line, t.value, arg.value, op_tok.value or op_tok.kind))
            i = arg_idx
            continue
        i += 1
    return hits


def line_text(path, line):
    lines = open(path, encoding="utf-8").read().splitlines()
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()
    return ""


def main():
    total = 0
    for path in find_planes_files():
        hits = find_candidates(path)
        for line, name, arg, op in hits:
            total += 1
            print(f"{path}:{line}: `{name} of {arg} {op} ...`  |  {line_text(path, line)}")
    print(f"\n{total} candidate site(s) found.", file=sys.stderr)


if __name__ == "__main__":
    main()
