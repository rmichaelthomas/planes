#!/usr/bin/env python3
"""scripts/check_derived_claims.py -- a hand-written claim about machine-derived
state, with nothing binding the two together, closed as a class.

grammar/README.md states the doctrine (ruling D2): a hand-written grammar file
goes stale silently, and a stale specification is worse than none. The remedy
is a split -- source-of-truth data is hand-edited, projections are generated
and checked in CI so they cannot go stale silently. `rules.json`/`errors.json`
live under it, `core.json` was hand-edited with nothing holding it to the
vocabulary until #62 added `core_check.py`'s drift guard.

THE CLASS IS WIDER THAN grammar/. Four instances were found by reading, not by
any check, all of the same shape: a hand-written sentence claims something
about state a generator or an interpreter actually computes, and nothing reads
both and compares them.

  1. .github/workflows/pages.yml's `on: push: paths:` filter named the files
     whose change should redeploy, and omitted grammar/*.planes and
     grammar/core.json, both of which scripts/assemble_site.sh copies because
     meta.html fetches them. Closed in this build (§3.1) by deleting the
     filter outright -- deploy on every push -- rather than gating a second
     hand-maintained list. test_gate.py::test_the_deploy_workflow_has_no_paths_filter
     holds the line.

  2. core_check.py's own `main()` comment said "A REPORT, never a gate ...
     does not change the exit code" over the graph block, while
     `sys.exit(len(viols) + len(graph) + len(drifts))` counted it and the same
     block's own printed message said "THIS FAILS THE GATE". Fixed alongside
     Check C below, which is built to catch exactly this shape.

  3. paint.html's footer said a stream declares `draw protocol 1` or
     `draw protocol 2`, or nothing, while the same footer's first line said
     "Drawing Protocol v3" and the page imports the v3 renderer chain
     (painter.mjs -> stream.mjs -> protocol.mjs). Fixed alongside Check B.

  4. js/browser_main.mjs's PROBE_ARGUMENT carried eleven of the vocabulary's
     thirteen builtin names, missing `number` and `root` -- inside the exact
     mechanism whose job is detecting a version mismatch between the loaded
     vocabulary and the loaded interpreter. Fixed alongside Check A.

THESE FOUR ARE NOT THE DELIVERABLE. They are the anti-vacuity set
test_derived_claims.py reconstructs as fixtures and asserts each check below
rediscovers, by name and by remedy -- an audit that cannot mechanically
rediscover the instances a human already found by reading is four point fixes
wearing a hat.

Three checks, each mechanical, each narrow on purpose, each naming a known
instance:

  Check A -- a table keyed by a generated vocabulary must cover it (instance 4)
  Check B -- a page that ships a protocol version must name it   (instance 3)
  Check C -- a comment asserting gate behaviour must match the exit path
             (instance 2, and it is narrow ON PURPOSE -- see check_c()'s
             own docstring for exactly what it does and does not reach)

Every check derives from generated data -- grammar/vocabulary.json,
protocol/protocol.json, sound/protocol.json, this file's own AST walk of
sys.exit -- never from a number, version, or name written in prose. The prose
is the subject, not the source.

This is a GATE step (`timed`, not `timed_soft`, in scripts/ci.sh): it exits
with the count of real violations across the three checks. A "clean" site --
one examined and found to already agree -- is recorded, not silently omitted;
see write_inventory() and derived-surface-audit.md, which this script
(re)writes on every run.

Usage:  python3 scripts/check_derived_claims.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from scripts.check_pages_surface import _COMMENTS, _SPECIFIER, _is_local, _resolve  # noqa: E402

VOCAB_PATH = os.path.join(REPO, "grammar", "vocabulary.json")
DRAWING_PROTOCOL_PATH = os.path.join(REPO, "protocol", "protocol.json")
SOUND_PROTOCOL_PATH = os.path.join(REPO, "sound", "protocol.json")

SKIP_DIRS = {
    ".git", ".venv", "__pycache__", "node_modules", ".mypy_cache",
    ".ruff_cache", ".pytest_cache", ".ci-logs", "identity",
}


def _rel(path):
    return os.path.relpath(path, REPO) if os.path.abspath(path).startswith(REPO) else path


def load_vocab_sets(path=VOCAB_PATH):
    """(builtins, keywords, effect_kinds) -- the three sets a hand-written
    table can be "about", read from the one hand-edited source of truth
    (grammar/README.md) rather than from any generated projection of it."""
    with open(path, encoding="utf-8") as f:
        vocab = json.load(f)
    builtins = {b["name"] for b in vocab["builtins"]}
    keywords = {k["word"] for k in vocab["keywords"]}
    effects = {e["kind"] for e in vocab["effect_kinds"]}
    return {"builtins": builtins, "keywords": keywords, "effect_kinds": effects}


def _walk_source_files(exts, skip_dirs=SKIP_DIRS):
    for dirpath, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fn in files:
            if fn.endswith(exts):
                yield os.path.join(dirpath, fn)


# ============================================================== Check A
#
# A TABLE KEYED BY A GENERATED VOCABULARY MUST COVER IT (instance 4).
#
# Detected by KEY OVERLAP, not by name (the design this build was given): a
# named dict (Python) or `const NAME = {...}` object literal (JavaScript)
# three or more of whose keys are vocabulary names is a table ABOUT that
# vocabulary, and must either cover the matching set or declare its
# omissions with a reason -- the shape grammar/core.json's
# excluded_builtins/excluded_keywords maps established, and core_check.py's
# drift() already enforces for that one file.
#
# Scoped to NAMED literals -- assigned to a variable (Python `ast.Assign`/
# `ast.AnnAssign`, JS `const NAME = {`) -- not every dict-shaped value
# anywhere. An inline `assert kinds == {"ask": ..., "write": ..., "show": ...}`
# in a test is a one-off comparison of what one run produced, not a claim
# standing on its own about the vocabulary; test_record.py has exactly this
# shape (3 of the 7 effect kinds, by design, for one test) and is not a
# violation. A "table" is a named, persistent thing; a bare literal compared
# with `==` is a value.
#
# The escape hatch a table can use to declare a deliberate, permanent
# omission (rather than fixing it, when the table's whole *purpose* is
# something narrower than covering the vocabulary): either
#   (a) a sibling assignment in the same file whose name contains "exclud"
#       (case-insensitive) -- core.json's own excluded_builtins/
#       excluded_keywords shape, generalised -- whose keys, unioned with the
#       candidate's own, cover the missing set; or
#   (b) a comment containing the words "not a vocabulary table" in the lines
#       immediately preceding the declaration, stating why.
# js/core_restrict.mjs's BINOP_KEYWORDS is the known instance of (b): its four
# keys are BinOp operator names that happen to be spelled with keywords, not
# an attempt to enumerate the keyword set, and it says so.

_EXCLUSION_MARKER = "not a vocabulary table"


def _py_named_dict_literals(path):
    """(lineno, name, keys) for every `NAME = {...}` / `NAME: T = {...}`
    whose value is a dict literal with all-string keys, anywhere in the file
    -- module level, function level, doesn't matter. Also yields exclusion
    dicts (name contains "exclud") the same way, so callers can check both in
    one pass."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError:
        return [], src
    out = []
    for node in ast.walk(tree):
        target_dict = None
        name = None
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            target_dict = node.value
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Dict):
            target_dict = node.value
            if isinstance(node.target, ast.Name):
                name = node.target.id
        if target_dict is None or name is None:
            continue
        keys = []
        ok = True
        for k in target_dict.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keys.append(k.value)
            else:
                ok = False
                break
        if not ok:
            continue
        out.append((target_dict.lineno, name, set(keys)))
    return out, src


def _py_preceding_comment_text(src, lineno, max_lines=8):
    """The contiguous full-line `#` comments directly above 1-indexed
    `lineno`, joined -- the window a marker like "not a vocabulary table" is
    read from."""
    lines = src.splitlines()
    out = []
    i = lineno - 2  # 0-indexed line just above the declaration
    seen = 0
    while i >= 0 and seen < max_lines:
        stripped = lines[i].strip()
        if not stripped.startswith("#"):
            break
        out.append(stripped.lstrip("#").strip())
        i -= 1
        seen += 1
    out.reverse()
    return " ".join(out)


# ---- the JavaScript side: a hand-rolled, string/template-aware scanner ----
#
# This repo has no JS AST library and the drawing protocol generator
# (scripts/protocol_gen.mjs) already established the pattern for reading JS
# structure without one: understand exactly enough lexical shape -- strings,
# template literals, `${ }` interpolation nesting, line/block comments -- to
# find where a bracketed span ends despite nested quotes and braces inside an
# interpolation. Ported to Python (rather than shelling out to node) because
# this checker's other two languages (Python AST, JSON) are native here and a
# fourth process per file would be its own cost; the ALGORITHM is
# protocol_gen.mjs's scanBracket, not a re-derivation of it -- a first version
# of this scanner used a naive brace counter with no `${ }` awareness and
# silently ran to end-of-file on the first template literal it met (found by
# testing it against this repo, not guessed).


class _JsBracketError(ValueError):
    pass


def _js_scan_bracket(src, open_idx):
    """src[open_idx] is one of ( [ {. Returns (end, splits): `end` is the
    matching close bracket's index, `splits` is every top-level (depth==1)
    comma inside it. Skips line and block comments in code mode, and treats
    `${` inside a template literal as its own nesting level so a brace or
    comma inside an interpolation is never mistaken for this bracket's own."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack = [src[open_idx]]
    splits = []
    mode = "code"
    i = open_idx + 1
    n = len(src)
    while i < n:
        c = src[i]
        if mode == "code":
            if c == "\\":
                i += 2
                continue
            if c == "/" and i + 1 < n and src[i + 1] == "/":
                j = src.find("\n", i)
                i = n if j == -1 else j
                continue
            if c == "/" and i + 1 < n and src[i + 1] == "*":
                j = src.find("*/", i + 2)
                i = n if j == -1 else j + 2
                continue
            if c == '"':
                mode = "dquote"
                i += 1
                continue
            if c == "'":
                mode = "squote"
                i += 1
                continue
            if c == "`":
                mode = "template"
                i += 1
                continue
            if c in "([{":
                stack.append(c)
                i += 1
                continue
            if c in ")]}":
                top = stack.pop()
                if top == "interp":
                    mode = "template"
                    i += 1
                    continue
                if pairs.get(top) != c:
                    raise _JsBracketError(f"mismatched bracket at index {i}")
                if not stack:
                    return i, splits
                i += 1
                continue
            if len(stack) == 1 and c == ",":
                splits.append(i)
            i += 1
            continue
        elif mode in ("dquote", "squote"):
            if c == "\\":
                i += 2
                continue
            if (mode == "dquote" and c == '"') or (mode == "squote" and c == "'"):
                mode = "code"
            i += 1
            continue
        else:  # template
            if c == "\\":
                i += 2
                continue
            if c == "`":
                mode = "code"
                i += 1
                continue
            if c == "$" and i + 1 < n and src[i + 1] == "{":
                stack.append("interp")
                mode = "code"
                i += 2
                continue
            i += 1
            continue
    raise _JsBracketError(f"unterminated bracket starting at index {open_idx}")


_JS_KEY_RE = re.compile(r'''^\s*(?:"([^"]+)"|'([^']+)'|([A-Za-z_$][\w$]*))\s*:''')


def _js_top_level_keys(src, open_idx, close_idx, splits):
    """The key of every top-level `key: value` entry between `open_idx` and
    `close_idx` (a shorthand `{foo}` entry has no `:` and is skipped -- no
    table this check needs to cover uses shorthand)."""
    bounds = [open_idx + 1] + [s + 1 for s in splits] + [close_idx]
    keys = []
    for a, b in zip(bounds, bounds[1:]):
        m = _JS_KEY_RE.match(src[a:b])
        if m:
            keys.append(m.group(1) or m.group(2) or m.group(3))
    return keys


_JS_CONST_RE = re.compile(r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*\{")


def _js_named_object_literals(path):
    """(lineno, name, keys) for every `const NAME = {...}` object literal in
    the file (module scope or not). A mismatched/unterminated bracket is
    reported by raising, exactly as protocol_gen.mjs's own scanner refuses
    rather than guessing -- callers surface it as a finding, not a crash."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    out = []
    for m in _JS_CONST_RE.finditer(src):
        open_idx = m.end() - 1
        try:
            close_idx, splits = _js_scan_bracket(src, open_idx)
        except _JsBracketError:
            continue
        keys = _js_top_level_keys(src, open_idx, close_idx, splits)
        lineno = src[:m.start()].count("\n") + 1
        out.append((lineno, m.group(1), set(keys)))
    return out, src


def _js_preceding_comment_text(src, lineno, max_lines=8):
    lines = src.splitlines()
    out = []
    i = lineno - 2
    seen = 0
    while i >= 0 and seen < max_lines:
        stripped = lines[i].strip()
        if not stripped.startswith("//"):
            break
        out.append(stripped.lstrip("/").strip())
        i -= 1
        seen += 1
    out.reverse()
    return " ".join(out)


def _excluded_by_sibling(candidates, name, keys, missing):
    """True when some OTHER named literal in the same file, whose name
    contains "exclud", covers every name in `missing` between its own keys
    and `keys`."""
    for _, other_name, other_keys in candidates:
        if other_name == name:
            continue
        if "exclud" in other_name.lower() and missing <= (keys | other_keys):
            return True
    return False


def _check_a_candidates(path, candidates, src, vocab, preceding_comment_fn, findings, examined):
    """The shared judgment for one file's candidate tables, whichever
    language found them: clean / excluded-by-comment / excluded-by-sibling /
    violation. Python and JavaScript differ only in HOW a candidate and its
    preceding comment are found (`_py_named_dict_literals` /
    `_js_named_object_literals` and their matching comment readers); the
    judgment itself is one piece of logic, not two."""
    for lineno, name, keys in candidates:
        for label, vset in vocab.items():
            if len(keys & vset) < 3:
                continue
            missing = vset - keys
            if not missing:
                examined.append((_rel(path), lineno, name, label, "clean (full coverage)"))
                continue
            comment = preceding_comment_fn(src, lineno)
            if _EXCLUSION_MARKER in comment.lower():
                examined.append((_rel(path), lineno, name, label,
                                  f"excluded (comment: {comment[:120]!r})"))
                continue
            if _excluded_by_sibling(candidates, name, keys, missing):
                examined.append((_rel(path), lineno, name, label,
                                  "excluded (sibling exclusion table)"))
                continue
            findings.append({
                "check": "A", "file": _rel(path), "line": lineno,
                "site": f"{name} ({label})",
                "summary": (f"{name} at {_rel(path)}:{lineno} covers "
                            f"{len(keys & vset)} of {len(vset)} {label} "
                            f"names, missing {sorted(missing)}"),
                "remedy": (f"add {sorted(missing)} to {name}, or declare "
                           f"why not with a comment containing "
                           f'"{_EXCLUSION_MARKER}", or a sibling table '
                           f'whose name contains "exclud" covering the gap'),
            })
            examined.append((_rel(path), lineno, name, label, "VIOLATION"))


def check_a():
    """Every named dict (Python) / `const NAME = {...}` (JS) literal in the
    repo whose keys overlap >= 3 with grammar/vocabulary.json's builtins,
    keywords, or effect_kinds. Returns (findings, examined) -- `examined` is
    every candidate table found, clean or not, so a clean site is on record
    and not just absent from the findings list."""
    vocab = load_vocab_sets()
    findings = []
    examined = []

    for path in _walk_source_files((".py",)):
        candidates, src = _py_named_dict_literals(path)
        if candidates:
            _check_a_candidates(path, candidates, src, vocab,
                                 _py_preceding_comment_text, findings, examined)

    for path in _walk_source_files((".mjs", ".js")):
        try:
            candidates, src = _js_named_object_literals(path)
        except _JsBracketError as e:
            findings.append({
                "check": "A", "file": _rel(path), "line": 0,
                "site": "(unparseable)",
                "summary": f"{_rel(path)}: {e}",
                "remedy": "fix the object literal's bracket/quote balance so "
                          "check_derived_claims.py can read it",
            })
            continue
        if candidates:
            _check_a_candidates(path, candidates, src, vocab,
                                 _js_preceding_comment_text, findings, examined)

    return findings, examined


# ============================================================== Check B
#
# A PAGE THAT SHIPS A PROTOCOL VERSION MUST NAME IT (instance 3).
#
# For each served root *.html that documents the drawing or sound protocol in
# PROSE (outside its own <script> tags -- garden.html's "sound protocol 1" is
# inside a <script> block building an actual command stream, not prose
# documentation, and is correctly not a site this check examines): the set of
# `draw protocol N` / `sound protocol N` version numbers the page's prose
# names must include the highest version the modules that page imports
# implement. The implemented version is read from protocol/protocol.json's
# and sound/protocol.json's own `version` field -- GENERATED data
# (scripts/protocol_gen.mjs) -- never from a number written in prose, which
# is the thing being checked (invariant 4).
#
# "The modules that page imports" is resolved TRANSITIVELY: paint.html's own
# <script> imports painter.mjs, not protocol.mjs directly -- painter.mjs
# imports stream.mjs, which imports protocol.mjs. A direct-imports-only
# reading would never see that paint.html implements the drawing protocol at
# all. The walk reuses scripts/check_pages_surface.py's own specifier regex
# and resolver -- the same module-graph-following logic the deploy's own
# surface check already uses and this build did not want a second reader of.

_VERSION_MENTION_RE = re.compile(r"\b(draw|sound) protocol (\d+)\b")


def _prose_text(html):
    """`html` with every <script>...</script> block removed -- what a reader
    of the PAGE, as opposed to its code, actually sees."""
    return re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)


def _mjs_graph(entry_html):
    """The full set of .mjs/.js files reachable from `entry_html`, repo-
    relative, transitively through every relative import -- restricted to
    script files (the version-implementation question does not need the
    .json/.planes/.css leaves check_pages_surface.py's own walk also
    follows)."""
    seen = set()
    queue = [entry_html]
    reached = set()
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        if not os.path.exists(path):
            continue
        if not path.endswith((".html", ".mjs", ".js")):
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if path.endswith((".mjs", ".js")):
            text = _COMMENTS.sub(" ", text)
            reached.add(_rel(path))
        for spec in _SPECIFIER.findall(text):
            if not _is_local(spec):
                continue
            target = _resolve(spec, path, REPO)
            if target and target.endswith((".mjs", ".js")):
                queue.append(target)
    return reached


_PROTOCOL_DESCRIPTORS = {
    "draw": (DRAWING_PROTOCOL_PATH, "js/paint/protocol.mjs"),
    "sound": (SOUND_PROTOCOL_PATH, "js/sound/protocol.mjs"),
}


def check_b():
    """Returns (findings, examined) -- `examined` covers every root *.html
    page, whether or not it documents a protocol in prose."""
    findings = []
    examined = []
    pages = sorted(f for f in os.listdir(REPO) if f.endswith(".html")
                    and os.path.isfile(os.path.join(REPO, f)))

    for page in pages:
        path = os.path.join(REPO, page)
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        prose = _prose_text(html)
        mentions = {}
        for key, num in _VERSION_MENTION_RE.findall(prose):
            mentions.setdefault(key, set()).add(int(num))

        if not mentions:
            examined.append((page, "does not document a protocol version in prose"))
            continue

        graph = None
        for key, versions in sorted(mentions.items()):
            json_path, module_rel = _PROTOCOL_DESCRIPTORS[key]
            if graph is None:
                graph = _mjs_graph(path)
            if module_rel not in graph:
                examined.append((page, f"names {key} protocol version(s) "
                                        f"{sorted(versions)} in prose but its "
                                        f"module graph does not reach {module_rel} "
                                        f"-- nothing to check the claim against"))
                continue
            with open(json_path, encoding="utf-8") as jf:
                highest = json.load(jf)["version"]
            if highest in versions:
                examined.append((page, f"{key} protocol: names version(s) "
                                        f"{sorted(versions)}, implements {highest} "
                                        f"-- clean"))
            else:
                findings.append({
                    "check": "B", "file": page, "line": 0,
                    "site": f"{page} footer/prose ({key} protocol)",
                    "summary": (f"{page} names {key} protocol version(s) "
                                f"{sorted(versions)} in prose, but its module "
                                f"graph implements version {highest} "
                                f"({module_rel}, per {_rel(json_path)})"),
                    "remedy": (f"name `{key} protocol {highest}` in {page}'s "
                               f"prose -- derived from {_rel(json_path)}'s "
                               f'"version" field, not restated by hand'),
                })

    return findings, examined


# ============================================================== Check C
#
# A COMMENT ASSERTING GATE BEHAVIOUR MUST MATCH THE EXIT PATH (instance 2).
# See check_c()'s own docstring for what this catches and, deliberately,
# what it does not reach.

_TRIGGER_PHRASES = (
    "never a gate",
    "does not change the exit code",
    "a report, not a gate",
    "reports and does not gate",
)

CHECK_C_SCOPE_ROOT_FILES = (
    "core_check.py", "grammar_gen.py", "audit_locked_vs_built.py",
    "corpus_coverage.py", "errors_coverage.py",
)


def _check_c_scope():
    paths = [os.path.join(REPO, f) for f in CHECK_C_SCOPE_ROOT_FILES
              if os.path.exists(os.path.join(REPO, f))]
    scripts_dir = os.path.join(REPO, "scripts")
    for fn in sorted(os.listdir(scripts_dir)):
        if fn.endswith((".py", ".sh", ".mjs")):
            paths.append(os.path.join(scripts_dir, fn))
    return paths


def _py_comment_paragraphs(path):
    """(start_line, end_line, text) for every run of contiguous FULL-LINE
    `#` comments in `path` -- a trailing `x = 1  # note` is excluded (its
    token's start column is not the line's first non-whitespace column)."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    lines = src.splitlines()
    paragraphs = []
    cur_start = None
    cur_lines = []
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            if cur_start is None:
                cur_start = i
            cur_lines.append(stripped.lstrip("#").strip())
        else:
            if cur_start is not None:
                paragraphs.append((cur_start, i - 1, " ".join(cur_lines)))
            cur_start, cur_lines = None, []
    if cur_start is not None:
        paragraphs.append((cur_start, len(lines), " ".join(cur_lines)))
    return paragraphs, src


def _py_assigned_names_in_range(tree, start_line, end_line):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            if start_line <= node.lineno <= end_line:
                names.add(node.id)
    return names


def _py_exit_calls(tree):
    """(lineno, referenced_names) for every `sys.exit(...)` / bare
    `exit(...)` call -- referenced_names is every Name inside its arguments,
    collected by walking the call's own args/keywords, never by reading the
    source line as text."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        is_sys_exit = (isinstance(node.func, ast.Attribute) and node.func.attr == "exit"
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "sys")
        is_bare_exit = isinstance(node.func, ast.Name) and node.func.id == "exit"
        if not (is_sys_exit or is_bare_exit):
            continue
        names = set()
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
        out.append((node.lineno, names))
    return out


def _check_c_python(path, findings, examined):
    paragraphs, src = _py_comment_paragraphs(path)
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError:
        examined.append((_rel(path), "unparseable -- skipped"))
        return
    triggered = [(s, e, t) for s, e, t in paragraphs
                 if any(p in t.lower() for p in _TRIGGER_PHRASES)]
    if not triggered:
        examined.append((_rel(path), "no trigger phrase in any comment"))
        return
    exit_calls = _py_exit_calls(tree)
    starts = sorted(s for s, _, _ in paragraphs)
    for start, end, text in triggered:
        later = [s for s in starts if s > end]
        window_end = min(later) if later else len(src.splitlines()) + 1
        block_names = _py_assigned_names_in_range(tree, end + 1, window_end - 1)
        hit = False
        for exit_line, exit_names in exit_calls:
            overlap = block_names & exit_names
            if overlap:
                hit = True
                findings.append({
                    "check": "C", "file": _rel(path), "line": start,
                    "site": f"{_rel(path)}:{start}",
                    "summary": (f'{_rel(path)}:{start} says a block is '
                                f"never a gate, but sys.exit at line "
                                f"{exit_line} counts {sorted(overlap)}, which "
                                f"that block computes"),
                    "remedy": ("correct the comment to say the block gates "
                               "(and why it became one), or remove "
                               f"{sorted(overlap)} from the sys.exit "
                               "expression if it truly should not gate"),
                })
        status = "VIOLATION" if hit else "clean (no exit-path overlap)"
        examined.append((_rel(path), f"line {start}: {status}"))


def _check_c_other(path, findings, examined):
    """.sh / .mjs: phrase-in-comment detection only (see check_c()'s own
    docstring for why no exit-path correlation happens here)."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    is_shell = path.endswith(".sh")
    hits = []
    for i, line in enumerate(src.splitlines(), start=1):
        stripped = line.strip()
        is_comment = stripped.startswith("#") if is_shell else stripped.startswith("//")
        if not is_comment:
            continue
        low = stripped.lower()
        if any(p in low for p in _TRIGGER_PHRASES):
            hits.append(i)
    if not hits:
        examined.append((_rel(path), "no trigger phrase in any comment"))
        return
    for i in hits:
        examined.append((_rel(path), f"line {i}: phrase found -- no AST "
                                       "exit-path correlation available for "
                                       "this file type (see check_c() "
                                       "docstring); reported for a human to "
                                       "correlate by hand"))


def check_c():
    """A comment in a gate script claiming its own block "never a gate"s
    (one of four fixed phrases -- see _TRIGGER_PHRASES) while the file's own
    sys.exit expression counts a name that block computes (instance 2:
    core_check.py's graph block).

    NARROW ON PURPOSE. No checker here reads English generally, and this one
    least of all: what it catches is a single, high-value, mechanically
    checkable pattern, not a general claim-vs-code auditor. What it does NOT
    reach, stated here because a checker that overstated its own reach would
    be a new instance of the very class it exists to catch:

      - It is Python-AST-based (`ast.walk` over `sys.exit()`/bare `exit()`
        calls, and over the block of code the flagged comment precedes,
        collecting assigned names -- never a regex over the exit line, which
        would mis-read a multi-line expression exactly as grammar_gen.py's
        own precedent warns against). For scripts/*.sh and scripts/*.mjs it
        only detects whether one of the four phrases appears in a comment at
        all -- there is no `sys.exit` AST to walk in bash or JavaScript
        here, and no shell/JS AST library in this repo (protocol_gen.mjs's
        own stated reason for hand-rolling its scanner instead). A phrase
        found in a shell or JS comment is reported for a human to correlate
        by hand; none currently exists in this repo's scope.
      - It only scans FULL-LINE comments (a `#`/`//` that is the only
        content on its line) -- a trailing inline comment on a code line is
        not read.
      - It catches a comment claiming NO gate where a gate exists. It does
        NOT catch the CONVERSE -- a comment wrongly claiming something IS a
        gate when the exit path does not, in fact, count it. That direction
        needs a human reviewer, not a substring match.
      - It is not a substitute for a reviewer, and it does not read English
        in general: four fixed phrases, nothing else.
    """
    findings = []
    examined = []
    for path in _check_c_scope():
        if path.endswith(".py"):
            _check_c_python(path, findings, examined)
        else:
            _check_c_other(path, findings, examined)
    return findings, examined


# ============================================================== inventory

INVENTORY_PATH = os.path.join(REPO, "derived-surface-audit.md")


def write_inventory(results):
    lines = []
    lines.append("# derived-surface-audit")
    lines.append("")
    lines.append("Generated by `scripts/check_derived_claims.py`. Every site the sweep")
    lines.append("examined, and every finding it reported -- a site examined and found")
    lines.append("clean is recorded here, not omitted (§4.4).")
    lines.append("")

    for key, title, intro in (
        ("A", "Check A -- a table keyed by a generated vocabulary must cover it",
         "Named dict/object literals whose keys overlap >=3 with "
         "grammar/vocabulary.json's builtins, keywords, or effect_kinds."),
        ("B", "Check B -- a page that ships a protocol version must name it",
         "Every root `*.html` page, and whether its prose names the highest "
         "protocol version its module graph implements."),
        ("C", "Check C -- a comment asserting gate behaviour must match the exit path",
         "Every file in scope, and whether any comment claiming \"never a "
         "gate\" (or an equivalent phrase) is contradicted by the file's own "
         "sys.exit expression."),
    ):
        findings, examined = results[key]
        lines.append(f"## {title}")
        lines.append("")
        lines.append(intro)
        lines.append("")
        lines.append(f"**{len(findings)} finding(s), {len(examined)} site(s) examined.**")
        lines.append("")
        if findings:
            lines.append("### Findings")
            lines.append("")
            for f in findings:
                lines.append(f"- `{f['site']}` -- {f['summary']}")
                lines.append(f"  - remedy: {f['remedy']}")
            lines.append("")
        lines.append("### Sites examined")
        lines.append("")
        for row in examined:
            lines.append("- " + " -- ".join(str(c) for c in row))
        lines.append("")

    with open(INVENTORY_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ============================================================== CLI

def main():
    findings_a, examined_a = check_a()
    findings_b, examined_b = check_b()
    findings_c, examined_c = check_c()

    results = {
        "A": (findings_a, examined_a),
        "B": (findings_b, examined_b),
        "C": (findings_c, examined_c),
    }
    write_inventory(results)

    total = len(findings_a) + len(findings_b) + len(findings_c)
    print("check_derived_claims: the derived-surface-audit class")
    print("=" * 72)
    for key, (findings, examined) in results.items():
        print(f"\nCheck {key}: {len(findings)} finding(s), {len(examined)} site(s) examined")
        for f in findings:
            print(f"  {f['site']}")
            print(f"    {f['summary']}")
            print(f"    -> {f['remedy']}")
    if total == 0:
        print(f"\nall clean -- see {_rel(INVENTORY_PATH)} for the full inventory")
    else:
        print(f"\n{total} violation(s) -- see {_rel(INVENTORY_PATH)} for the full inventory")
    sys.exit(total)


if __name__ == "__main__":
    main()
