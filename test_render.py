"""Canonical renderer tests: round-trip, and the generated rule marker."""
import glob
import sys

from lexer import Rule
from parser import PlanesSyntaxError, parse
from render import ast_equal, compute_markers, render
from shapes import analyse

# demo/app/net.planes needs the cross-file `known` name table modules.py's
# run_file() supplies -- it does not parse standalone even on main, before
# this build (test_annotation.py's NEEDS_MULTI_FILE_CONTEXT reasoning
# applies here identically).
NOT_STANDALONE_PARSEABLE = {"demo/app/net.planes"}


def every_planes_file():
    # S7: the canonical corpus joins render's round-trip set, and so do the two
    # self-hosted grammar files this function's own name always implied but
    # excluded — grammar/interp.planes and grammar/parser.planes, the repo's two
    # largest programs, whose exclusion from a round-trip set is exactly how #24's
    # forty defects hid. render round-trips all of them since #24/S6.
    paths = sorted(glob.glob("*.planes")) + \
        sorted(glob.glob("demo/**/*.planes", recursive=True)) + \
        sorted(glob.glob("grammar/*.planes")) + \
        sorted(glob.glob("corpus/**/*.planes", recursive=True))
    return [p for p in paths if p not in NOT_STANDALONE_PARSEABLE]


# ================================================================ round-trip

def test_round_trip_every_planes_file_in_the_repo():
    """render(parse(src)) must parse to an AST equal to parse(src) --
    equal under ast_equal(), which ignores `line` (canonical reformatting
    legitimately moves source position; see render.py's module docstring
    for why that is the honest bar, not accidental line-number agreement)."""
    failures = []
    for path in every_planes_file():
        src = open(path).read()
        try:
            prog = parse(src)
        except PlanesSyntaxError as e:
            failures.append(f"{path}: does not even parse on its own: {e}")
            continue
        out = render(prog)
        try:
            prog2 = parse(out)
        except PlanesSyntaxError as e:
            failures.append(f"{path}: rendered output failed to reparse: {e}")
            continue
        if len(prog) != len(prog2) or not all(
                ast_equal(a, b) for a, b in zip(prog, prog2)):
            failures.append(f"{path}: reparsed AST is not equal")
    assert not failures, "\n  ".join([""] + failures)


def test_round_trip_on_the_most_deeply_nested_program():
    """Failure mode 7: the lexer is indentation-sensitive, so round-trip
    is checked explicitly on the program with the deepest nested-block
    structure in the repo -- pypi.planes (to -> for each -> for each
    where, with or-fail wrapping both a call and a write)."""
    src = open("pypi.planes").read()
    prog = parse(src)
    prog2 = parse(render(prog))
    assert len(prog) == len(prog2)
    assert all(ast_equal(a, b) for a, b in zip(prog, prog2))


def test_render_output_is_not_byte_identical_to_source():
    """Canonical, not literal (§3.1): the renderer is not required to
    reproduce the original formatting, only to round-trip."""
    src = open("gate.planes").read()
    out = render(parse(src))
    assert out != src


def test_a_program_with_annotations_round_trips():
    prog = parse(open("annotated.planes").read())
    prog2 = parse(render(prog))
    assert len(prog) == len(prog2)
    assert all(ast_equal(a, b) for a, b in zip(prog, prog2))


# ================================================================ round-trip with escapes
#
# None of the four escapes could occur in any string before this build
# (ESCAPE_AUDIT.md), so nothing exercised render.py's re-quoting until
# now -- render_expr's Str case, and every other site that prints a
# string-typed AST field back as a quoted literal (Because.text, Rule
# and Foreign's `target`, a Note entry's `from`), shared the same gap:
# each field holds already-resolved text (parser.py's `.value[1:-1]`),
# so printing it back inside bare quotes either reparses to a different
# value or, for an escaped quote, does not reparse at all.

def _round_trips(src):
    prog = parse(src)
    out = render(prog)
    prog2 = parse(out)
    return len(prog) == len(prog2) and all(ast_equal(a, b) for a, b in zip(prog, prog2))


def test_string_literal_with_escaped_quote_round_trips():
    assert _round_trips(r'x = "a\"b"' + "\n")


def test_string_literal_with_each_escape_round_trips():
    for body in (r'a\"b', r"a\\b", r"a\nb", r"a\tb"):
        assert _round_trips(f'x = "{body}"\n'), body


def test_because_annotation_with_escaped_quote_round_trips():
    assert _round_trips('x = 1 because "a\\"b"\n')


def test_rule_target_with_escaped_quote_round_trips():
    assert _round_trips('rule [r] anything may not write to "a\\"b"\n')


def test_rendered_escaped_string_reparses_to_the_same_value():
    """Not just re-parseable -- the *value* survives the round trip,
    not merely well-formed source."""
    prog = parse(r'x = "a\"b"' + "\n")
    prog2 = parse(render(prog))
    assert prog2[0].expr.value == 'a"b'


# ================================================== exhaustive per-node-kind round-trip (A.5)
#
# render.py must have a real case for every AST node kind, checked by a
# round-trip per kind (parse -> render -> reparse -> ast_equal), and no
# safe fallback (an unhandled kind raises, naming it). Builtin is dead (the
# parser never builds it) and Because appears only as an annotation field,
# never a standalone node; both are exercised at their real sites below.

NODE_KIND_SNIPPETS = {
    "Num": "x = 42\n",
    "Str": 'x = "hi"\n',
    "Bool": "x = true\n",
    "Nothing": "x = nothing\n",
    "Var": "y = x\n",
    "ListLit": "x = [1, 2, 3]\n",
    "RecordLit": "x = { a: 1, b: 2 }\n",
    "RecordUpdate": "y = p with a: 1, b: 2\n",
    "ListPlus": "y = xs plus 1\n",
    "BinOp": "x = 1 + 2\n",
    "Not": "x = not true\n",
    "IsNothing": "x = y is nothing\n",
    "Field": "x = r.a.b\n",
    "Assign": "x = 1\n",
    "Because": 'x = 1 because "reason"\n',
    "Why": "why x\n",
    "Use": "use file\n",
    "FuncDef": "to f of n:\n  give n\n",
    "Call": "y = f of 1\n",
    "Give": "to f:\n  give 1\n",
    "Show": 'show "hi"\n',
    "ForEach": "y = for each p in xs where p > 0: p\n",
    "If": "if x:\n  show 1\nelse:\n  show 2\n",
    "When": "when r is { a: 1, b }:\n  show b\nelse:\n  show 0\n",
    "OrFail": "y = f of 1 or fail as e\n",
    "Fail": 'fail "boom" as oops\n',
    "Foreign": 'foreign sort of xs from "builtins.sorted" doing ask xs\n',
    "WriteTo": 'write [1] to "f.json"\n',
    "Round": "y = round x to 2 places\n",
    "Rule": 'rule [r] anything may not ask to "u" because "reason"\n',
    "Note": 'note:\n  from "src"\n  derives-from [rule-x]\n',
}


def _kinds_in(prog):
    """Every AST node class name in a parsed program, at any nesting depth,
    recursing through dataclass fields and list/tuple structure alike."""
    seen = set()

    def walk(v):
        if hasattr(v, "__dataclass_fields__"):
            seen.add(type(v).__name__)
            for f in v.__dataclass_fields__:
                walk(getattr(v, f))
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    for s in prog:
        walk(s)
    return seen


def test_every_ast_node_kind_has_a_round_trip():
    import dataclasses
    import inspect

    import lexer
    all_kinds = {
        n for n, o in vars(lexer).items()
        if inspect.isclass(o) and dataclasses.is_dataclass(o)
        and o.__module__ == "lexer" and n != "Token"}
    covered = set()
    for kind, src in NODE_KIND_SNIPPETS.items():
        prog = parse(src)
        kinds = _kinds_in(prog)
        assert kind in kinds, f"{kind}: snippet did not actually produce it (got {sorted(kinds)})"
        out = render(prog)
        prog2 = parse(out)
        assert len(prog) == len(prog2) and all(
            ast_equal(a, b) for a, b in zip(prog, prog2)), (
            f"{kind}: render round-trip failed\n--- rendered ---\n{out}")
        covered |= kinds
    covered.add("Builtin")   # dead node; test_builtin_render_raises covers it
    missing = all_kinds - covered
    assert not missing, f"AST node kinds with no round-trip coverage: {sorted(missing)}"


def test_record_update_round_trips_including_chains():
    """RecordUpdate (`with`) was absent from render.py entirely before this
    build (A.5). A chain nests left to right and must round-trip."""
    for src in ("y = p with a: 1\n",
                "y = p with a: 1, b: 2\n",
                "y = p with a: 1 with b: 2\n",
                "y = p with a: 1 + 2\n"):
        assert _round_trips(src), src


def test_builtin_render_raises_named():
    """Builtin is unreachable by the parser; render_expr raises a named
    error rather than a silent fall-through (A.5, no safe fallback)."""
    import render as r
    from lexer import Builtin
    try:
        r.render_expr(Builtin("count", None))
        assert False, "expected a raise"
    except ValueError as e:
        assert "Builtin" in str(e), str(e)


def test_render_stmt_raises_on_a_node_it_cannot_render():
    """A node that is neither a known statement nor a renderable expression
    raises from render_stmt, naming the kind -- not routed silently through
    render_expr (A.5, failure mode 6)."""
    import render as r
    from lexer import Because
    try:
        r.render_stmt(Because("x", 1), "", {})
        assert False, "expected a raise"
    except ValueError as e:
        assert "Because" in str(e), str(e)


# ================================================================ the generated marker

RULE_SRC = (
    'rule [refund-cap] anything may not write to "refunds.json"\n'
    '\n'
    'use file\n'
    'results = { total: 1 }\n'
    'write results to "refunds.json"\n'
)


def test_marker_appears_at_the_governed_site():
    prog = parse(RULE_SRC)
    surface = analyse(RULE_SRC)
    found = [s for s in prog if isinstance(s, Rule)]
    out = render(prog, rules=found, surface=surface)
    lines = out.splitlines()
    idx = lines.index('~ [refund-cap] applies here')
    assert lines[idx + 1] == 'write results to "refunds.json"'


def test_marker_absent_without_rules():
    prog = parse(RULE_SRC)
    out = render(prog)
    assert "~" not in out
    assert "applies here" not in out


def test_changing_the_rule_set_changes_the_marker():
    prog = parse(RULE_SRC)
    surface = analyse(RULE_SRC)
    found = [s for s in prog if isinstance(s, Rule)]
    with_rule = render(prog, rules=found, surface=surface)
    without_rule = render(prog, rules=[], surface=surface)
    assert "~ [refund-cap] applies here" in with_rule
    assert "~ [refund-cap] applies here" not in without_rule


def test_cleared_match_still_shows_the_marker():
    """A permit clearing a forbid still means the forbid rule reached
    that site (unbound v2.0 §31) -- the marker says a rule reaches here,
    not that the reader should be worried."""
    src = (
        'rule [no-write] anything may not write to "a.json"\n'
        'rule [allow-a] anything may write to "a.json" supersedes [no-write]\n'
        '\n'
        'use file\n'
        'write [1] to "a.json"\n'
    )
    prog = parse(src)
    surface = analyse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    out = render(prog, rules=found, surface=surface)
    assert "~ [no-write] applies here" in out


def test_vacuous_rule_gets_no_marker():
    """A named-subject rule that resolves but matches nothing has no
    effect, and so no site to mark (P-Q19's vacuous shape): `cap`
    resolves (it is traceable as this write's target), but the program
    performs no `ask` effect at all -- situation 1."""
    src = (
        'cap = "a.json"\n'
        'rule [cap-guard] cap may not ask\n'
        '\n'
        'use file\n'
        'write [1] to cap\n'
    )
    prog = parse(src)
    surface = analyse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    out = render(prog, rules=found, surface=surface)
    assert "applies here" not in out


def test_no_marker_text_appears_in_any_source_file():
    """Invariant 2/6: the marker is output only. No .planes file in the
    repo may contain marker text -- if one did, it would mean either a
    marker leaked into a committed file, or a user's literal `~` line was
    mistaken for something meaningful."""
    for path in every_planes_file() + ["annotated.planes"]:
        src = open(path).read()
        assert "applies here" not in src, path
        assert "\n~ [" not in src, path


def test_marker_is_not_parsed_back_in():
    """A stray `~` line in source is not read as a marker -- the parser
    has no marker-recognition code path at all. Rendering the SAME
    program again with no rules must not reproduce a marker from a prior
    render: nothing carries it forward except a fresh rules.check()."""
    prog = parse(RULE_SRC)
    surface = analyse(RULE_SRC)
    found = [s for s in prog if isinstance(s, Rule)]
    render(prog, rules=found, surface=surface)   # a prior render, with markers
    unmarked_again = render(prog)                # re-rendered with no rules
    assert "~ [refund-cap] applies here" not in unmarked_again


def test_compute_markers_requires_a_surface():
    prog = parse(RULE_SRC)
    found = [s for s in prog if isinstance(s, Rule)]
    try:
        compute_markers(found, None)
        assert False, "expected an error"
    except ValueError as e:
        assert "surface" in str(e)


if __name__ == "__main__":
    fails = []
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            fails.append(name)
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
