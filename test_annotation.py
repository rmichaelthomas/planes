"""Annotation plane tests.

The inertness test (`test_inertness_*`) is the guarantee, not one test
among many (unbound v1.0 §4 item 3, §218): nothing in this tier can change
what a program does. It is enforced here by construction — strip every
annotation, run both versions, and require the show-output, effect log,
and effect surface to come back identical — not by trusting that `because`
and `note` were written to be inert.

Inertness governs effects, not inspection (docs/annotation-scope.md): `why`
may display a `because` on request, and that display is allowed to differ
between the annotated and stripped runs. `show`, `write`, `ask`, and `read`
may not — those are what a program *does*, and comparing `i.effects`
(which records exactly those, never `why`) is what actually enforces that.
"""
import glob
import json
import sys

from interp import Interpreter, PlanesError
from lexer import Assign, Because, ForEach, FuncDef, If, Note, Rule
from parser import PlanesSyntaxError, parse
from render import ast_equal, render, strip_annotations
from shapes import analyse

# ================================================================ fixtures

# hn.planes and pypi.planes are the only two of the repo's top-level
# programs that touch the network; demo/rules/exception.planes (added below)
# is the one demo/ fixture that can run standalone with just a stub. All
# three need one (test_coverage.py's own rule: no test may touch the real
# world).
STORIES = {
    1: {"title": "Rust 2.0 released",       "score": 450},
    2: {"title": "Why Go is fine",          "score": 300},
    3: {"title": "Rewriting grep in Rust",  "score": 210},
    4: {"title": "A rust postmortem",       "score": 150},
}


def stub_http(url):
    if "topstories" in url:
        return json.dumps(list(STORIES.keys()))
    if "pypi.org" in url:
        name = url.split("/pypi/")[1].split("/json")[0]
        return json.dumps({"info": {
            "name": name,
            "summary": f"{name} does something useful and interesting"}})
    if "audit.internal" in url:
        return "ok"
    sid = int(url.split("/item/")[1].split(".json")[0])
    return json.dumps(STORIES[sid])


FIXTURE_KWARGS = {
    "hn.planes": {"http": stub_http},
    "pypi.planes": {"http": stub_http},
    "demo/rules/exception.planes": {"http": stub_http},
}

# The repo's top-level *.planes files run standalone via
# Interpreter().run(open(path).read()). demo/rules/exception.planes is the
# one fixture under demo/ that can too -- it needs only an http stub, no
# cross-file `known` names. Every other file under demo/ either needs the
# `known`/rename map modules.py's run_file() supplies (demo/app/net.planes
# will not even parse alone) or a stub this file has no generic way to
# construct (a named CSV, a specific ask URL only the test that owns it
# provides) -- confirmed against main before this build. Those still get
# the structural strip-is-a-no-op check further down; every .planes file in
# the repo does.
STANDALONE_PLANES_FILES = sorted(glob.glob("*.planes")) + [
    "demo/rules/exception.planes"]

NOT_STANDALONE_PARSEABLE = {"demo/app/net.planes"}


def all_planes_files():
    paths = sorted(glob.glob("*.planes")) + \
        sorted(glob.glob("demo/**/*.planes", recursive=True))
    return [p for p in paths if p not in NOT_STANDALONE_PARSEABLE]


# ================================================================ has this program been annotated?

def has_annotations(prog):
    """Does this program carry a Note, or a Because on any Assign/Rule,
    anywhere -- including nested inside a FuncDef, If, or ForEach body?"""
    return bool(annotation_nesting_kinds(prog, top_level_counts=True))


def annotation_nesting_kinds(stmts, top_level_counts=False, _in=None):
    """Which contexts (None for top-level, or 'FuncDef'/'If'/'ForEach')
    carry a nested annotation in this statement list, checked recursively.

    Used two ways: `has_annotations` just asks whether the result set is
    non-empty; the nesting-coverage test asks exactly which of FuncDef/
    If/ForEach are represented in it, across the whole repo.
    """
    found = set()
    for s in stmts:
        annotated = isinstance(s, Note) or (
            isinstance(s, (Assign, Rule)) and s.annotation is not None)
        if annotated and (top_level_counts or _in is not None):
            found.add(_in)
        if isinstance(s, FuncDef):
            found |= annotation_nesting_kinds(s.body, top_level_counts, "FuncDef")
        elif isinstance(s, If):
            found |= annotation_nesting_kinds(s.then, top_level_counts, "If")
            found |= annotation_nesting_kinds(s.els, top_level_counts, "If")
        elif isinstance(s, ForEach):
            found |= annotation_nesting_kinds(s.body, top_level_counts, "ForEach")
    return found


# ================================================================ the guarantee

def run_and_capture(src, **kw):
    kw.setdefault("fs", {})
    i = Interpreter(**kw)
    full_output = i.run(src)
    surface = analyse(src)
    show_output = [e[1] for e in i.effects if e[0] == "show"]
    return show_output, list(i.effects), [str(e) for e in surface.declared], full_output


def assert_inert(src, **kw):
    """Strip every annotation; the program must perform exactly the same
    effects. show-output, the effect log, and the effect surface must be
    identical -- `why`'s output is not compared here (see the module
    docstring and docs/annotation-scope.md) and is returned so a caller
    that wants to inspect it can.

    Stripping goes through the renderer (render.py's `strip_annotations` +
    `render`), not a regex over `because "..."` / `note:` text: a
    mechanical AST transform can't be fooled by a quoted string that
    happens to contain the word `because`, and reusing the renderer here
    is itself a live check on the renderer's own correctness.
    """
    prog = parse(src)
    stripped_src = render(strip_annotations(prog))
    a_show, a_eff, a_surf, a_full = run_and_capture(src, **kw)
    b_show, b_eff, b_surf, b_full = run_and_capture(stripped_src, **kw)
    assert a_show == b_show, (
        f"show-output differs after stripping annotations:\n"
        f"  with:    {a_show}\n  without: {b_show}")
    assert a_eff == b_eff, (
        f"effect log differs after stripping annotations:\n"
        f"  with:    {a_eff}\n  without: {b_eff}")
    assert a_surf == b_surf, (
        f"effect surface differs after stripping annotations:\n"
        f"  with:    {a_surf}\n  without: {b_surf}")
    return a_full, b_full


def test_inertness_on_the_annotated_demo():
    assert_inert(open("annotated.planes").read())


def test_inertness_across_every_standalone_planes_file():
    """Every standalone program in the repo, annotated or not. The ones
    without annotations trivially pass (stripping is a no-op) and double
    as a regression net for the renderer across the corpus's real syntax
    variety; the annotated ones (§F below) are where the guarantee is
    actually exercised."""
    for path in STANDALONE_PLANES_FILES:
        if path == "annotated.planes":
            continue
        src = open(path).read()
        kw = FIXTURE_KWARGS.get(path, {})
        assert_inert(src, **kw)


def test_inertness_sample_covers_more_than_one_file():
    """The guarantee must not rest on a single purpose-built demo."""
    annotated = [p for p in all_planes_files()
                 if has_annotations(parse(open(p).read()))]
    assert len(annotated) >= 4, annotated


def test_nesting_is_exercised_in_funcdef_if_and_foreach():
    """render.strip_annotations recurses through FuncDef, If, and
    ForEach bodies -- each must actually be exercised by a real
    annotation somewhere in the repo, not just claimed."""
    found = set()
    for path in all_planes_files():
        found |= annotation_nesting_kinds(parse(open(path).read()))
    assert found >= {"FuncDef", "If", "ForEach"}, found


def test_strip_is_structurally_a_no_op_on_unannotated_programs():
    """A second, execution-free angle on the same guarantee: for a program
    with no `because`/`note`, strip_annotations() must return something
    structurally identical to the parse it started from -- covers the
    multi-file fixtures under demo/ that are not meant to run standalone
    (a `known` name table or a stub this file has no generic way to
    construct), where the run-based check above cannot reach. Any file
    that DOES have annotations is skipped here on purpose -- stripping it
    is supposed to change the AST; that direction is what the run-based
    tests above prove instead."""
    for path in all_planes_files():
        prog = parse(open(path).read())
        if has_annotations(prog):
            continue
        stripped = strip_annotations(prog)
        assert len(prog) == len(stripped), path
        assert all(ast_equal(a, b) for a, b in zip(prog, stripped)), path


def test_why_on_an_annotated_binding_does_not_break_inertness():
    """The case the prior build scoped out of the demo rather than
    resolving: why may display a because, and that is inspection, not
    effect (docs/annotation-scope.md). show-output/effects/surface hold
    identical; why's own output is allowed -- and here shown -- to
    differ, which is the boundary working, not a gap."""
    src = 'cap = 200 because "board policy"\nshow text of cap\nwhy cap\n'
    a_full, b_full = assert_inert(src)
    assert a_full != b_full
    assert 'because "board policy"' in a_full[1]
    assert "because" not in b_full[1]


# ================================================================ non-execution

def test_a_note_block_runs_clean():
    """The normal path: run(), run_file(), and exec_block() all skip a
    Note before ever calling exec_stmt on it -- a program using `note:`
    runs exactly as it would without one, the same as `because`."""
    src = 'note:\n  from "policy"\n  derives-from [some-rule]\nshow "hi"\n'
    assert Interpreter(fs={}).run(src) == ["hi"]


def test_note_reaching_exec_stmt_directly_raises():
    """The defensive half of that guarantee: exec_stmt itself refuses a
    Note if some call site ever bypasses the filter (§4.1.4) -- reached
    here by calling exec_stmt directly, since the normal entry points
    (run/run_file/exec_block) never pass one through."""
    prog = parse('note:\n  from "policy"\n  derives-from [some-rule]\n')
    i = Interpreter(fs={})
    try:
        i.exec_stmt(prog[0], i.env)
        assert False, "Note reached exec_stmt and did not raise"
    except PlanesError as e:
        assert e.tag == "annotation-executed", e.tag


def test_because_has_no_eval_case():
    """A `Because` reaching eval() falls through to the pre-existing
    cannot-evaluate error -- there is no dedicated case for it at all."""
    from interp import Interpreter as I
    i = I(fs={})
    try:
        i.eval(Because("a reason"), i.env)
        assert False, "Because was evaluated and did not raise"
    except PlanesError as e:
        assert e.tag == "cannot-evaluate"


def test_because_never_enters_the_derivation_graph():
    """`why` may display the text; the Deriv graph and origins() must
    never see it (§4.1.5)."""
    from interp import origins
    src = 'cap = 200 because "board policy"\nresult = cap + 1\n'
    i = Interpreter(fs={})
    i.run(src)
    traced = i.env.get("result")
    assert origins(traced) == []
    # And the annotation genuinely is display-only: the node kinds present
    # in the graph are exactly the ones an unannotated program would have.
    def kinds(n):
        yield n.kind
        for inp in n.inputs:
            yield from kinds(inp)
    assert "because" not in set(kinds(traced.node))


def test_why_displays_because_text():
    src = 'cap = 200 because "board policy, ratified March"\nwhy cap\n'
    out = Interpreter(fs={}).run(src)
    assert 'because "board policy, ratified March"' in out[0]


def test_why_omits_because_when_none_given():
    src = 'cap = 200\nwhy cap\n'
    out = Interpreter(fs={}).run(src)
    assert "because" not in out[0]


def test_stale_because_does_not_survive_reassignment():
    """A because attached to one binding must not leak onto a later,
    unannotated rebinding of the same name."""
    src = 'x = 5 because "first reason"\nx = 6\nwhy x\n'
    out = Interpreter(fs={}).run(src)
    assert "because" not in out[0]


# ================================================================ parsing

def test_because_trailing_on_assign():
    prog = parse('cap = 200 because "board policy"\n')
    assert prog[0].annotation.text == "board policy"


def test_because_wrapped_on_rule():
    prog = parse(
        'rule [refund-cap] anything may not write to "refunds.json"\n'
        '  because "finance owns this file"\n')
    assert prog[0].annotation.text == "finance owns this file"


def test_because_needs_a_quoted_reason():
    try:
        parse('x = 5 because 200\n')
        assert False, "expected a syntax error"
    except PlanesSyntaxError as e:
        assert "needs a quoted reason" in str(e)
        assert "try:" in str(e)


def test_note_parses_from_and_derives_from():
    prog = parse(
        'note:\n'
        '  from "GDPR Article 17"\n'
        '  derives-from [refund-cap]\n')
    assert isinstance(prog[0], Note)
    assert prog[0].entries == [
        ("from", "GDPR Article 17"),
        ("derives-from", "refund-cap"),
    ]


def test_note_derives_from_needs_a_bracketed_name():
    try:
        parse('note:\n  derives-from refund-cap\n')
        assert False, "expected a syntax error"
    except PlanesSyntaxError as e:
        assert "bracketed rule name" in str(e)


def test_because_and_note_still_work_as_ordinary_names():
    """Positional recognition, not reservation: the ceiling stays at 30."""
    out = Interpreter(fs={}).run(
        'because = 5\nnote = because + 1\nshow note\n')
    assert out == ["6"]
    out2 = Interpreter(fs={}).run(
        'to note of x:\n  give x + 1\n\nshow note of 5\n')
    assert out2 == ["6"]


def test_reserved_word_ceiling_unchanged():
    from lexer import KEYWORDS
    assert "because" not in KEYWORDS
    assert "note" not in KEYWORDS
    assert len(KEYWORDS) == 30


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
