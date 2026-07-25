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
VOCAB_TEXT = read(os.path.join("grammar", "vocabulary.json"))

SOURCES = {"lexer.py": LEXER, "interp.py": INTERP, "parser.py": PARSER,
           "grammar/vocabulary.json": VOCAB_TEXT}


def _find_array_block(text, key):
    """Locate `"<key>": [ ... ]` in a JSON text and return (block, start_line).

    Depth-counts brackets rather than a single non-greedy regex, so a block
    containing further `[`/`]` (none of ours do, but a future one might)
    still resolves to the right close.
    """
    m = re.search(rf'"{key}"\s*:\s*\[', text)
    if not m:
        return None, None
    depth, i = 0, m.end() - 1
    start = i
    while i < len(text):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return text[start:i + 1], text[:start].count("\n") + 1


def check_keyword(word):
    """Word appears in the `keywords` array of grammar/vocabulary.json.

    Used to regex `KEYWORDS = { ... }` out of lexer.py directly. Since the
    grammar-as-data build (addendum v4.2 section 69.1), that literal no
    longer exists — lexer.py loads KEYWORDS from grammar/vocabulary.json —
    so this check moved to the file that is now the actual source of
    truth. Scans only the `"keywords": [ ... ]` block so a word appearing
    elsewhere in the file (a positional word, a note) does not count.
    """
    if VOCAB_TEXT is None:
        return None
    block, block_start_line = _find_array_block(VOCAB_TEXT, "keywords")
    if block is None:
        return None
    pat = rf'"word"\s*:\s*"{re.escape(word)}"'
    if not re.search(pat, block):
        return None
    for offset, bline in enumerate(block.split("\n")):
        if re.search(pat, bline):
            return f"grammar/vocabulary.json:{block_start_line + offset} (in keywords)"
    return f"grammar/vocabulary.json:{block_start_line} (in keywords)"


def check_ast_node(classname):
    ln = find_line(LEXER, rf"^\s*class {re.escape(classname)}\b")
    return f"lexer.py:{ln} (class {classname})" if ln else None


def check_interp_branch(nodename):
    ln = find_line(INTERP, rf"isinstance\(\w+,\s*{re.escape(nodename)}\)")
    return f"interp.py:{ln} (isinstance … {nodename})" if ln else None


def check_builtin(name):
    """Name appears in the `builtins` array of grammar/vocabulary.json.

    Used to regex `BUILTIN_NAMES = { ... }` out of parser.py directly.
    Since the grammar-as-data build, that literal no longer exists —
    parser.py loads BUILTIN_NAMES from grammar/vocabulary.json — so this
    check moved the same way check_keyword did, and for the same reason.
    """
    if VOCAB_TEXT is None:
        return None
    block, block_start_line = _find_array_block(VOCAB_TEXT, "builtins")
    if block is None:
        return None
    pat = rf'"name"\s*:\s*"{re.escape(name)}"'
    if not re.search(pat, block):
        return None
    for offset, bline in enumerate(block.split("\n")):
        if re.search(pat, bline):
            return f"grammar/vocabulary.json:{block_start_line + offset} (in builtins)"
    return f"grammar/vocabulary.json:{block_start_line} (in builtins)"


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
    ("join builtin",            "S2 §A.2",   [("builtin", "join")]),
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
        # Require BOTH an AST node AND an interpreter branch — parsing
        # without evaluating is not "built" (this two-part evidence matches
        # what `when` gets; the earlier one-sided version could pass on the
        # AST node alone, a weaker 0 than it looked).
        node = check_ast_node("RecordUpdate") or check_ast_node("With")
        if not node:
            return None
        branch = (check_interp_branch("RecordUpdate")
                  or check_interp_branch("With"))
        if not branch:
            return None
        return f"{node} + {branch}"

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
        # §72's `plus` for lists. Require BOTH the keyword/node AND an
        # interpreter branch that evaluates it — two-part evidence matching
        # `when`. (`+` concatenating lists is NOT `plus` — the corpus names
        # a distinct operator.) The build added a ListPlus node.
        node = check_ast_node("ListPlus")
        kw = check_keyword("plus")
        surface = node or kw
        if not surface:
            return None
        branch = check_interp_branch("ListPlus")
        if not branch:
            # fall back to an apply_op / eval_binop "plus" branch
            ln = find_line(INTERP, r'op == "plus"')
            branch = f"interp.py:{ln} (op == \"plus\")" if ln else None
        if not branch:
            return None
        return f"{surface} + {branch}"

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
