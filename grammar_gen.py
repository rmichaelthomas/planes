#!/usr/bin/env python3
"""grammar_gen.py — generates grammar/rules.json and grammar/errors.json
from the actual source (ruling D1: generated, not hand-authored).

Run from the repo root, same conventions as audit_locked_vs_built.py:
openable pointers, honest output, an exit code usable as a CI gate.

  python3 grammar_gen.py            regenerate both files
  python3 grammar_gen.py --check    regenerate into memory, diff against
                                     the committed files, print the diff,
                                     exit non-zero on any difference

Never touches grammar/vocabulary.json. That file is source-of-truth
(ruling D2), hand-edited, and read here like any other input — this
script only ever regenerates rules.json and errors.json, which are pure
projections of the real source (grammar/README.md).
"""
import ast
import difflib
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(REPO, "grammar", "rules.json")
ERRORS_PATH = os.path.join(REPO, "grammar", "errors.json")
PARSER_PATH = os.path.join(REPO, "parser.py")

TARGET_EXCEPTIONS = ("PlanesError", "PlanesSyntaxError", "PlanesAmbiguity",
                     "RuleConflict", "RuleNotSupported")

# rules.py's Violation.render and _render_vacuous build messages by
# assembling several f-strings across branches rather than constructing one
# of TARGET_EXCEPTIONS — D.2 asks for these as "assembled" entries by name,
# since deriving a generic "this function assembles a message" detector
# from arbitrary code is not what a form inventory can honestly claim to do
# (the same honesty D.3 states outright for rules.json).
ASSEMBLED_MESSAGE_SITES = [("rules.py", "render"), ("rules.py", "_render_vacuous")]


def repo_py_files():
    """Every .py file in the repo root, in a stable order."""
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(REPO, "*.py")))


# ================================================================ D.2: grammar/errors.json

def _string_template(node):
    """From a string-producing AST node, a (template, slots) pair:
    `template` has each interpolation rendered as `{expr text}`, `slots`
    is the list of those expr texts in order. (None, []) if `node` is not
    a literal or an f-string this can read (e.g. a variable holding an
    already-built message, as PlanesAmbiguity's call sites do — those
    delegate to grammar/messages/amber.json instead)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, []
    if isinstance(node, ast.JoinedStr):
        parts, slots = [], []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            elif isinstance(v, ast.FormattedValue):
                expr_text = ast.unparse(v.value)
                slots.append(expr_text)
                parts.append("{" + expr_text + "}")
        return "".join(parts), slots
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        lt, ls = _string_template(node.left)
        rt, rs = _string_template(node.right)
        if lt is not None and rt is not None:
            return lt + rt, ls + rs
    return None, []


def _enclosing_function(tree, lineno):
    """Name of the innermost function/method containing source line
    `lineno`, or None at module level."""
    best = None
    best_span = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            if node.lineno <= lineno <= end:
                span = end - node.lineno
                if best_span is None or span < best_span:
                    best, best_span = node.name, span
    return best


def _call_args(node):
    """Positional args, plus keyword args by name, for a Call node."""
    return list(node.args), {kw.arg: kw.value for kw in node.keywords if kw.arg}


def _extract_error_entries(fname, tree, src_lines):
    entries = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id in TARGET_EXCEPTIONS):
            continue
        cls = node.func.id
        args, kwargs = _call_args(node)
        raised_in = _enclosing_function(tree, node.lineno)

        if cls == "PlanesError":
            tag_node = args[0] if len(args) > 0 else kwargs.get("tag")
            detail_node = args[1] if len(args) > 1 else kwargs.get("detail")
            fix_node = args[2] if len(args) > 2 else kwargs.get("fix")
            tag = tag_node.value if isinstance(tag_node, ast.Constant) else None
            template, slots = (None, []) if detail_node is None else _string_template(detail_node)
            fix, _ = (None, []) if fix_node is None else _string_template(fix_node)
        else:
            tag = None
            msg_node = args[0] if args else None
            template, slots = (None, []) if msg_node is None else _string_template(msg_node)
            fix = None

        id_tag = tag or f"{cls.lower()}-site"
        entry = {
            "id": f"{fname[:-3]}.{id_tag}",
            "class": cls,
            "tag": tag,
            "source": f"{fname}:{node.lineno}",
            "raised_in": raised_in,
            "template": template,
            "slots": slots,
        }
        if fix:
            entry["fix"] = fix
        if template is None:
            entry["assembled"] = False
            if cls == "PlanesAmbiguity":
                entry["note"] = "delegates to grammar/messages/amber.json"
            else:
                entry["note"] = "message is not a literal/f-string at the call site " \
                                "(built elsewhere)"
        entries.append(entry)

    # A tag (or the class-site fallback) is not unique on its own -- the
    # same tag legitimately raises from several call sites (interp.py's
    # "cannot-compare", four places). Disambiguate ids that collide by
    # appending a running count, in source order, rather than pretending
    # each id was already unique.
    counters = {}
    for e in entries:
        counters[e["id"]] = counters.get(e["id"], 0) + 1
    seen = {}
    for e in entries:
        base = e["id"]
        if counters[base] > 1:
            seen[base] = seen.get(base, 0) + 1
            e["id"] = f"{base}-{seen[base]}"
    return entries


def _branch_message(stmts):
    """Every string-literal/f-string a branch's statements build, in
    source order: a plain `x = "..."` (or `x = ["...", "..."]`)
    assignment, an `x.append("...")` call, or a direct `return "..."`.
    Skips a bare delegating return (`return self._other_method()`) --
    that is routing, not a message shape of its own."""
    pieces = []
    for stmt in stmts:
        value = None
        if isinstance(stmt, ast.Assign):
            value = stmt.value
        elif isinstance(stmt, ast.Return) and stmt.value is not None:
            value = stmt.value
        elif (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Attribute)
                and stmt.value.func.attr == "append" and stmt.value.args):
            value = stmt.value.args[0]
        if value is None:
            continue
        candidates = value.elts if isinstance(value, ast.List) else [value]
        for c in candidates:
            t, _s = _string_template(c)
            if t is not None:
                pieces.append(t)
    return "\n".join(pieces) if pieces else None


def _span(stmts):
    lines = [s.lineno for s in stmts] + [getattr(s, "end_lineno", s.lineno) for s in stmts]
    return min(lines), max(lines)


def _extract_branches(stmts):
    """(span_stmts, message) for each distinct message shape a method
    body can produce: every arm of a top-level if/elif/else chain, every
    top-level `if: return ...` early exit, and finally one "main" branch
    combining everything else (including a conditional `if: append(...)`
    with no `return`, since that still contributes to the one message
    the main path builds, just optionally)."""
    branches = []
    trailing = []
    for stmt in stmts:
        if isinstance(stmt, ast.If):
            chain = stmt
            arms = [chain.body]
            while len(chain.orelse) == 1 and isinstance(chain.orelse[0], ast.If):
                chain = chain.orelse[0]
                arms.append(chain.body)
            if chain.orelse:
                arms.append(chain.orelse)
            if len(arms) > 1:
                for arm in arms:
                    msg = _branch_message(arm)
                    if msg is not None:
                        branches.append((arm, msg))
                continue
            if any(isinstance(s, ast.Return) for s in stmt.body):
                msg = _branch_message(stmt.body)
                if msg is not None:
                    branches.append((stmt.body, msg))
            else:
                trailing.extend(stmt.body)
        else:
            trailing.append(stmt)
    main_msg = _branch_message(trailing)
    if main_msg is not None:
        branches.append((trailing, main_msg))
    return branches


def _extract_assembled_entries(fname, tree, src_lines, method_name):
    """One entry per distinct message-producing branch of a message-
    assembling method (D.2's "assembled": true case) -- rules.py's
    Violation.render and Violation._render_vacuous, the two sites D.2
    names because deriving "this function assembles a message"
    generically, for arbitrary code, is not what a form inventory can
    honestly claim (the same limit D.3 states for rules.json)."""
    entries = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == method_name):
            continue
        for i, (stmts, msg) in enumerate(_extract_branches(node.body), 1):
            start, end = _span(stmts)
            entries.append({
                "id": f"{fname[:-3]}.{method_name}.branch-{i}",
                "class": None,
                "tag": None,
                "source": f"{fname}:{start}-{end}" if end != start else f"{fname}:{start}",
                "raised_in": method_name,
                "template": msg,
                "slots": [],
                "assembled": True,
            })
    return entries


def generate_errors():
    entries = []
    for fname in repo_py_files():
        path = os.path.join(REPO, fname)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src, filename=fname)
        src_lines = src.split("\n")
        entries.extend(_extract_error_entries(fname, tree, src_lines))
        for site_file, method in ASSEMBLED_MESSAGE_SITES:
            if fname == site_file:
                entries.extend(_extract_assembled_entries(fname, tree, src_lines, method))

    tags = {}
    for e in entries:
        key = e["tag"] or e["id"]
        tags.setdefault(key, []).append(e["source"])

    return {
        "format": 1,
        "generated_by": "grammar_gen.py",
        "count": len(entries),
        "entries": entries,
        "tags": tags,
    }


# ================================================================ D.3: grammar/rules.json

def _parser_method_docstring_surface(node):
    """The method's own first paragraph (up to the first blank line),
    joined onto one line -- most of these docstrings state the surface
    form across two or three wrapped lines before the blank line that
    starts the rationale. Taking only the literal first source line would
    truncate mid-phrase for several of them (e.g. parse_when)."""
    doc = ast.get_docstring(node)
    if not doc:
        return None
    doc = doc.strip()
    paragraph = doc.split("\n\n", 1)[0]
    joined = " ".join(line.strip() for line in paragraph.split("\n")).strip()
    return joined or None


def _calls_within(node):
    """Names of parse_*/read_*/check_*/paren_is_arglist methods called
    (via self.X(...)) anywhere in `node`'s body — the sub-forms this
    production uses."""
    out = []
    for n in ast.walk(node):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"):
            name = n.func.attr
            if name.startswith(("parse_", "read_", "check_")) or name == "paren_is_arglist":
                if name not in out:
                    out.append(name)
    return out


def _opens_with_tokens(node):
    """Token kinds this parse_* method's own body tests for at its start
    (`self.at("X")` / `self.accept("X")` / `t.kind == "X"`), best-effort —
    the form inventory D.3 asks for, not a formal FIRST-set derivation."""
    out = []
    for n in ast.walk(node):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr in ("at", "accept", "expect")
                and n.args and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)):
            kind = n.args[0].value
            if kind.isupper() and kind not in out:
                out.append(kind)
    return out


def _produces_node_type(node):
    """The AST node type constructed on the method's own `return`
    statements, when it is a single, direct `return SomeNode(...)` shape —
    best-effort; a method with several possible return shapes (or one
    that returns a sub-call's result) reports what it can and no more."""
    types = []
    for n in ast.walk(node):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Call) \
                and isinstance(n.value.func, ast.Name):
            name = n.value.func.id
            if name[:1].isupper() and name not in types:
                types.append(name)
    return types


def generate_rules():
    with open(PARSER_PATH, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src, filename="parser.py")

    forms = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not (node.name.startswith("parse_") or node.name == "paren_is_arglist"):
            continue
        produces = _produces_node_type(node)
        forms.append({
            "form": node.name.removeprefix("parse_") or node.name,
            "parser_method": node.name,
            "opens_with": _opens_with_tokens(node),
            "produces": produces[0] if len(produces) == 1 else produces,
            "calls": [c for c in _calls_within(node) if c != node.name],
            "source": f"parser.py:{node.lineno}",
            "surface": _parser_method_docstring_surface(node),
        })

    forms.sort(key=lambda f: f["source"])
    return {
        "format": 1,
        "generated_by": "grammar_gen.py",
        "note": "A form inventory, not a formal grammar (D.3) -- deriving a "
                "true BNF from recursive-descent code is not mechanical.",
        "count": len(forms),
        "forms": forms,
    }


# ================================================================ CLI

def _write(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=False)
        f.write("\n")


def _read_existing(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def main():
    check = "--check" in sys.argv
    rules_doc = generate_rules()
    errors_doc = generate_errors()

    rules_text = json.dumps(rules_doc, indent=2) + "\n"
    errors_text = json.dumps(errors_doc, indent=2) + "\n"

    if not check:
        _write(RULES_PATH, rules_doc)
        _write(ERRORS_PATH, errors_doc)
        print(f"wrote {RULES_PATH} ({rules_doc['count']} forms)")
        print(f"wrote {ERRORS_PATH} ({errors_doc['count']} entries, "
              f"{len(errors_doc['tags'])} distinct tags)")
        return 0

    diffs = 0
    for path, generated, label in ((RULES_PATH, rules_text, "grammar/rules.json"),
                                    (ERRORS_PATH, errors_text, "grammar/errors.json")):
        existing = _read_existing(path)
        if existing == generated:
            print(f"{label}: up to date")
            continue
        diffs += 1
        print(f"{label}: OUT OF DATE — regenerate with python3 grammar_gen.py")
        existing_lines = (existing or "").splitlines(keepends=True)
        generated_lines = generated.splitlines(keepends=True)
        diff = difflib.unified_diff(existing_lines, generated_lines,
                                    fromfile=f"{label} (committed)",
                                    tofile=f"{label} (generated)")
        sys.stdout.writelines(diff)
    if diffs:
        print(f"\n{diffs} file(s) out of date.")
    return diffs


if __name__ == "__main__":
    sys.exit(main())
