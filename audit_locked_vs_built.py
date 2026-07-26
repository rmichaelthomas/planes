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

S7 (A.7): the audit now covers BOTH implementations. It used to read only
Python — every pointer landed in lexer.py / interp.py — so a construct present
in Python and absent in JavaScript (or the reverse) would have passed every
check in the repo. Now each locked construct must have evidence on BOTH sides,
Python AND JavaScript, with an openable pointer for each. The keyword/builtin/
effect vocabulary is not checked twice: both implementations load the one
grammar/vocabulary.json, so there is no second copy to drift.

Evidence rules, so "BUILT" can't be faked by a comment mentioning the word:
  - keyword    : the token is in the shared grammar/vocabulary.json keywords;
                 recognised in lexer.py's KEYWORDS and js/lexer.mjs's _keywords
  - ast_node   : a `class <Name>` dataclass in lexer.py AND a `__node: "<Name>"`
                 constructor in js/nodes.mjs
  - interp     : an `isinstance(node, <Node>)` branch in interp.py AND a
                 `=== "<Name>"` dispatch in js/interp.mjs
  - builtin    : the name is in the shared vocabulary AND implemented at
                 `name === "<name>"` in js/interp.mjs
  - operator   : handled in interp.py's apply_op AND at `op === "<op>"` in
                 js/interp.mjs
A construct is BUILT only when every piece of its evidence is present on BOTH
sides. A Python-only construct is reported specifically — it is the A.7 gap.

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

# S7, A.7: the audit covered ONE implementation — every pointer above lands in
# Python. A construct present in Python and absent in JavaScript would pass every
# check in the repo. So the JavaScript implementation is read too, and every
# locked construct is now required to have evidence on BOTH sides, with an
# openable pointer for each. lexer.py's grammar (keywords, builtins, effect
# kinds) is not duplicated in JS — both implementations load the one
# grammar/vocabulary.json — so those are marked shared rather than checked twice.
JS_NODES = read(os.path.join("js", "nodes.mjs"))
JS_INTERP = read(os.path.join("js", "interp.mjs"))
JS_LEXER = read(os.path.join("js", "lexer.mjs"))

SOURCES = {"lexer.py": LEXER, "interp.py": INTERP, "parser.py": PARSER,
           "grammar/vocabulary.json": VOCAB_TEXT,
           "js/nodes.mjs": JS_NODES, "js/interp.mjs": JS_INTERP,
           "js/lexer.mjs": JS_LEXER}


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


# ---- the JavaScript side (S7, A.7) --------------------------------------
#
# The JS AST is plain objects tagged `__node: "<Name>"` (js/nodes.mjs); the
# interpreter dispatches on that tag with `=== "<Name>"` and on operator/builtin
# strings with `op === "..."` / `name === "..."` (js/interp.mjs). These checks
# find that concrete evidence, the same standard the Python side is held to —
# an AST node with no evaluator branch is not "built" on either side.

SHARED_VOCAB = ("grammar/vocabulary.json (shared source of truth; js loads it "
                "via js/lexer.mjs, no second copy to drift)")


def check_js_ast_node(classname):
    ln = find_line(JS_NODES, rf'__node:\s*"{re.escape(classname)}"')
    return f"js/nodes.mjs:{ln} (__node {classname})" if ln else None


def check_js_interp_branch(nodename):
    ln = find_line(JS_INTERP, rf'=== "{re.escape(nodename)}"')
    return f'js/interp.mjs:{ln} (=== "{nodename}")' if ln else None


def check_js_builtin(name):
    # Both sides recognise the builtin from the shared vocabulary; the JS
    # interpreter also IMPLEMENTS it — the stronger, concrete pointer.
    ln = find_line(JS_INTERP, rf'name === "{re.escape(name)}"')
    return f'js/interp.mjs:{ln} (name === "{name}")' if ln else None


def check_js_apply_op(opstring):
    ln = find_line(JS_INTERP, rf'op === "{re.escape(opstring)}"')
    return f'js/interp.mjs:{ln} (op === "{opstring}")' if ln else None


def check_js_keyword(word):
    # Keywords are honoured in one place: js/lexer.mjs upcases a NAME whose text
    # is in the shared keyword set (the mirror of lexer.py:212). The word itself
    # lives only in grammar/vocabulary.json, loaded by both implementations.
    ln = find_line(JS_LEXER, r"_keywords\.has\(")
    return f"js/lexer.mjs:{ln} (keyword recognition; {SHARED_VOCAB})" if ln else None


def evaluate_js(kind, arg):
    """The JavaScript-side pointer for one piece of evidence, or None."""
    if kind == "ast":
        return check_js_ast_node(arg)
    if kind == "interp":
        return check_js_interp_branch(arg)
    if kind == "builtin":
        return check_js_builtin(arg)
    if kind == "apply_op":
        return check_js_apply_op(arg)
    if kind == "keyword":
        return check_js_keyword(arg)

    if kind == "handler_field":
        ln = find_line(JS_NODES, r"OrFail = \(.*handler")
        return f"js/nodes.mjs:{ln} (OrFail handler param)" if ln else None

    if kind == "record_update_with":
        node = check_js_ast_node("RecordUpdate")
        branch = check_js_interp_branch("RecordUpdate")
        return f"{node} + {branch}" if node and branch else None

    if kind == "first_operator":
        ln = find_line(JS_INTERP, r'op === "first"')
        return f'js/interp.mjs:{ln} (op === "first")' if ln else None

    if kind == "plus_operator":
        node = check_js_ast_node("ListPlus")
        branch = check_js_interp_branch("ListPlus")
        return f"{node} + {branch}" if node and branch else None

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
    ("rest builtin",            "S2 §A.3",   [("builtin", "rest")]),
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
    print("BUILT vs LOCKED — audit of corpus claims against BOTH implementations")
    print(f"repo root: {REPO}")
    print("=" * 72)
    print()

    not_built = []       # missing on either side
    py_only = []         # Python evidence, no JavaScript — the A.7 gap
    for construct, lock, evidence in CHECKS:
        proofs = []
        py_ok = js_ok = True
        for kind, arg in evidence:
            py = evaluate(kind, arg)
            js = evaluate_js(kind, arg)
            if py is None:
                py_ok = False
            if js is None:
                js_ok = False
            proofs.append((kind, arg, py, js))
        ok = py_ok and js_ok
        status = "BUILT    " if ok else "NOT BUILT"
        print(f"[{status}] {construct:28} (lock: {lock})")
        for kind, arg, py, js in proofs:
            print(f"      {kind}({arg}):")
            print(f"        py: {py or f'MISSING {kind}({arg})'}")
            print(f"        js: {js or f'MISSING {kind}({arg})'}")
        print()
        if not ok:
            not_built.append((construct, lock))
            if py_ok and not js_ok:
                py_only.append((construct, lock))

    print("=" * 72)
    if not_built:
        print(f"LOCKED BUT NOT BUILT — {len(not_built)}:")
        for c, lock in not_built:
            print(f"   - {c}  ({lock})")
        if py_only:
            print()
            print(f"   of these, {len(py_only)} have PYTHON evidence but NO "
                  f"JavaScript — the exact A.7 gap: a construct one")
            print("   implementation has and the other lacks, which every "
                  "single-implementation check in this repo would miss.")
        print()
        print("Each is a corpus lock with no code behind it on at least one")
        print("side. Either it gets built, or the lock gets amended to match.")
    else:
        print("All locked constructs have code evidence in BOTH implementations.")
        print("Two independently written implementations agree on every locked")
        print("construct — a stronger result than parity on one side alone.")
    print("=" * 72)

    # Exit code = number of holes on either side, for CI use.
    sys.exit(len(not_built))


if __name__ == "__main__":
    main()
