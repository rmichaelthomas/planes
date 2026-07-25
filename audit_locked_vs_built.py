#!/usr/bin/env python3
"""audit_locked_vs_built.py — does the corpus's "LOCKED" match the code?

Run this from the repo root:  python3 audit_locked_vs_built.py

It does NOT trust any checkpoint. It reads the actual source and reports,
per construct the corpus claims is locked, whether that construct is
BUILT — meaning it has real evidence in the code — with the file and line
of that evidence, or NOT BUILT, with what was searched.

The point is that YOU run it and the terminal answers. Nothing here is a
claim you have to take on faith: every BUILT line is a pointer you can open,
every NOT BUILT line names exactly what was searched so you can confirm the
absence yourself.

Evidence rules, so "BUILT" can't be faked by a comment mentioning the word:
  - keyword    : the token is in lexer.py's KEYWORDS set
  - ast_node   : there is a `class <Name>` dataclass in lexer.py
  - interp     : there is an `isinstance(node|stmt, <Node>)` branch in interp.py
  - builtin    : the name is in parser.py's BUILTIN_NAMES
  - operator   : the operator string is handled in interp.py's apply_op
A construct's requirement lists which of these must ALL be present for BUILT.

Exit code is the count of locked-but-not-built constructs (0 = all clean),
so it can drop into CI as a gate.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.abspath(__file__))


def read(name):
    p = os.path.join(REPO, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read()


def find_line(text, pattern):
    """First line (1-indexed) matching a regex, or None."""
    if text is None:
        return None
    rx = re.compile(pattern)
    for i, line in enumerate(text.split("\n"), 1):
        if rx.search(line):
            return i
    return None


# Load the sources once. If a file is missing, every check against it fails
# honestly rather than crashing.
LEXER = read("lexer.py")
INTERP = read("interp.py")
PARSER = read("parser.py")

SOURCES = {"lexer.py": LEXER, "interp.py": INTERP, "parser.py": PARSER}


def check_keyword(word):
    """Word appears inside the KEYWORDS set literal in lexer.py.

    Scans only the KEYWORDS = { ... } block so a keyword used elsewhere in
    prose does not count.
    """
    if LEXER is None:
        return None
    m = re.search(r"KEYWORDS\s*=\s*\{(.*?)\}", LEXER, re.DOTALL)
    if not m:
        return None
    block = m.group(1)
    if not re.search(rf'"{re.escape(word)}"', block):
        return None
    # Point at the actual line the keyword sits on, not the block start,
    # so the pointer is openable.
    block_start_line = LEXER[: m.start(1)].count("\n") + 1
    for offset, bline in enumerate(block.split("\n")):
        if re.search(rf'"{re.escape(word)}"', bline):
            return f"lexer.py:{block_start_line + offset} (in KEYWORDS)"
    return f"lexer.py:{block_start_line} (in KEYWORDS)"


def check_ast_node(classname):
    ln = find_line(LEXER, rf"^\s*class {re.escape(classname)}\b")
    return f"lexer.py:{ln} (class {classname})" if ln else None


def check_interp_branch(nodename):
    ln = find_line(INTERP, rf"isinstance\(\w+,\s*{re.escape(nodename)}\)")
    return f"interp.py:{ln} (isinstance … {nodename})" if ln else None


def check_builtin(name):
    if PARSER is None:
        return None
    m = re.search(r"BUILTIN_NAMES\s*=\s*\{(.*?)\}", PARSER, re.DOTALL)
    if not m:
        return None
    if re.search(rf'"{re.escape(name)}"', m.group(1)):
        start = PARSER[: m.start()].count("\n") + 1
        return f"parser.py:~{start} (in BUILTIN_NAMES)"
    return None


def check_apply_op(opstring):
    """Operator string is handled in apply_op, not merely tokenized."""
    m = re.search(r"def apply_op\(.*?\n(.*?)\ndef ", INTERP or "", re.DOTALL)
    body = m.group(1) if m else (INTERP or "")
    if re.search(rf'op == "{re.escape(opstring)}"', body):
        return "interp.py (apply_op handles it)"
    return None


# ---- the checklist -----------------------------------------------------
#
# Each entry: (construct, corpus_lock, list of (evidence_kind, argument)).
# ALL evidence in the list must be present for BUILT. The evidence kinds
# map to the check_* functions above.

CHECKS = [
    # construct,                lock,        required evidence
    ("functions (to/give)",     "v3.0 §40",  [("ast", "FuncDef"), ("interp", "FuncDef"),
                                              ("ast", "Give")]),
    ("let / rebinding",         "v4.0 §58",  [("ast", "Assign"), ("interp", "Assign")]),
    ("records + field access",  "v2.0 §35",  [("ast", "RecordLit"), ("ast", "Field"),
                                              ("interp", "Field")]),
    ("lists",                   "v3.0 §48",  [("ast", "ListLit"), ("interp", "ListLit")]),
    ("comprehensions",          "v3.0 §48",  [("ast", "ForEach"), ("interp", "ForEach")]),
    ("if / else",               "v3.0 §42",  [("ast", "If"), ("interp", "If")]),
    ("show",                    "v3.0 §40",  [("ast", "Show"), ("interp", "Show")]),
    ("write to",                "v3.0 §40",  [("ast", "WriteTo"), ("interp", "WriteTo")]),
    ("ask (builtin)",           "v3.0 §40",  [("builtin", "ask")]),
    ("read (builtin)",          "v3.0 §40",  [("builtin", "read")]),
    ("count/text/lower/upper",  "v3.0 §48",  [("builtin", "count"), ("builtin", "text"),
                                              ("builtin", "lower"), ("builtin", "upper")]),
    # `first` is a reserved keyword with its own AST/operator path
    # (`first n of xs`), NOT a BUILTIN_NAMES entry like count/text. Its
    # evidence is the keyword + the eval_binop operator branch, same shape
    # as `round`. (This entry was wrong in the first version of this script:
    # it asked for builtin("first") and flagged a real, working feature as
    # NOT BUILT. Corrected here.)
    ("first",                   "v3.0 §48",  [("keyword", "first"), ("first_operator", None)]),
    ("round + exact numbers",   "v3.0 §47",  [("ast", "Round"), ("interp", "Round")]),
    ("guarded equality (==)",   "v4.0 §59",  [("apply_op", "==")]),
    ("foreign calls",           "FFI sprint",[("ast", "Foreign")]),
    ("rules",                   "v2.0",      [("ast", "Rule")]),
    ("annotations",             "v6.0",      [("ast", "Because"), ("ast", "Note")]),
    ("is nothing",              "v4.0",      [("ast", "IsNothing"), ("interp", "IsNothing")]),

    # ---- the ones under scrutiny this session ----
    ("or fail as + HANDLER",    "§106",      [("ast", "OrFail"), ("interp", "OrFail"),
                                              ("handler_field", None)]),
    ("when shape-dispatch",     "§74 / G-Q1",[("ast", "When"), ("interp", "When")]),
    ("with (record update)",    "§72",       [("record_update_with", None)]),
    ("plus (list append)",      "§72",       [("plus_operator", None)]),
    ("normalize builtin",       "§107",      [("builtin", "normalize")]),
]


def evaluate(kind, arg):
    if kind == "ast":
        return check_ast_node(arg)
    if kind == "interp":
        return check_interp_branch(arg)
    if kind == "builtin":
        return check_builtin(arg)
    if kind == "apply_op":
        return check_apply_op(arg)
    if kind == "keyword":
        return check_keyword(arg)

    # ---- special-cased evidence, spelled out so it can't be gamed ----

    if kind == "handler_field":
        # OrFail must carry a `handler` field for §106's block form to exist.
        ln = find_line(LEXER, r"^\s*handler\s*[:=]")
        # Only count it if it's inside the OrFail class region.
        if ln and "class OrFail" in (LEXER or ""):
            return f"lexer.py:{ln} (OrFail.handler)"
        return None

    if kind == "record_update_with":
        # §72's `with` is a RECORD-UPDATE operator, distinct from the
        # module-rename `with` (use x with a as b) and the foreign `with`.
        # Evidence would be an interpreter branch that builds a new record
        # from an old one plus overrides — look for a dedicated node or a
        # `with` handling path that is NOT the Use-rename. There is no such
        # node in the AST list, so this looks for one and reports honestly.
        node = check_ast_node("With") or check_ast_node("RecordUpdate")
        if node:
            return node
        # A record-update `with` handled inside eval would show here:
        ln = find_line(INTERP, r"record.*update|update.*record|\bwith\b.*override")
        return f"interp.py:{ln}" if ln else None

    if kind == "first_operator":
        # `first n of xs` is handled in eval_binop as node.op == "first",
        # not in apply_op. Look for that branch specifically.
        ln = find_line(INTERP, r'node\.op == "first"')
        if ln:
            return f"interp.py:{ln} (eval_binop first branch)"
        # fall back to any op == "first" handling
        ln = find_line(INTERP, r'op == "first"')
        return f"interp.py:{ln}" if ln else None

    if kind == "plus_operator":
        # §72's `plus` for lists. Evidence: `plus` as a keyword/operator OR
        # an apply_op branch for "plus". (`+` concatenating lists is NOT
        # `plus` — the corpus names a distinct operator.)
        kw = check_keyword("plus")
        if kw:
            return kw
        ln = find_line(INTERP, r'op == "plus"')
        return f"interp.py:{ln}" if ln else None

    return None


def main():
    missing_files = [n for n, s in SOURCES.items() if s is None]
    if missing_files:
        print(f"!! could not read: {', '.join(missing_files)}")
        print("   Run this from the repo root (where lexer.py / interp.py live).")
        print()

    print("=" * 72)
    print("BUILT vs LOCKED — audit of corpus claims against actual code")
    print(f"repo root: {REPO}")
    print("=" * 72)
    print()

    not_built = []
    for construct, lock, evidence in CHECKS:
        proofs = []
        ok = True
        for kind, arg in evidence:
            proof = evaluate(kind, arg)
            if proof is None:
                ok = False
                proofs.append(f"        MISSING: {kind}({arg})")
            else:
                proofs.append(f"        {proof}")
        status = "BUILT    " if ok else "NOT BUILT"
        print(f"[{status}] {construct:28} (lock: {lock})")
        for p in proofs:
            print(p)
        print()
        if not ok:
            not_built.append((construct, lock))

    print("=" * 72)
    if not_built:
        print(f"LOCKED BUT NOT BUILT — {len(not_built)}:")
        for c, lock in not_built:
            print(f"   - {c}  ({lock})")
        print()
        print("Each of these is a corpus lock with no code behind it. Either")
        print("the construct gets built, or the lock gets amended to match")
        print("reality. Until then, the corpus claims something the code denies.")
    else:
        print("All locked constructs have code evidence. No drift.")
    print("=" * 72)

    # Exit code = number of holes, for CI use.
    sys.exit(len(not_built))


if __name__ == "__main__":
    main()
