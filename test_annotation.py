"""Annotation plane tests.

The inertness test (`test_inertness_*`) is the guarantee, not one test
among many (unbound v1.0 §4 item 3, §218): nothing in this tier can change
what a program does. It is enforced here by construction — strip every
annotation, run both versions, and require output, effect log, and effect
surface to come back byte-identical — not by trusting that `because` and
`note` were written to be inert.
"""
import glob
import json
import sys

from interp import Interpreter, PlanesError
from lexer import Because, Note
from parser import PlanesSyntaxError, parse
from render import ast_equal, render, strip_annotations
from shapes import analyse

# ================================================================ fixtures

# hn.planes and pypi.planes are the only two of the repo's standalone
# programs that touch the network; both need a stub (test_coverage.py's own
# rule: no test may touch the real world).
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
    sid = int(url.split("/item/")[1].split(".json")[0])
    return json.dumps(STORIES[sid])


FIXTURE_KWARGS = {
    "hn.planes": {"http": stub_http},
    "pypi.planes": {"http": stub_http},
}

# The repo's top-level *.planes files are the ones actually meant to run
# standalone via Interpreter().run(open(path).read()) -- confirmed against
# main, before this build, that every file under demo/ either needs the
# cross-file `known` names and rename map modules.py's run_file() supplies
# (demo/app/net.planes will not even parse alone), or a specific stub
# (a named CSV, a specific ask URL) only the test that owns it provides.
# None of those fixtures carry an annotation, so the run-based three-way
# proof below is scoped to the files that can honestly attempt it; every
# .planes file in the repo, including demo/, still gets the structural
# strip-is-a-no-op check further down.
STANDALONE_PLANES_FILES = sorted(glob.glob("*.planes"))


def all_planes_files():
    return sorted(glob.glob("*.planes")) + \
        sorted(glob.glob("demo/**/*.planes", recursive=True))


# ================================================================ the guarantee

def run_and_capture(src, **kw):
    kw.setdefault("fs", {})
    i = Interpreter(**kw)
    output = i.run(src)
    surface = analyse(src)
    return list(output), list(i.effects), [str(e) for e in surface.declared]


def assert_inert(src, **kw):
    """Strip every annotation; the program must do exactly the same thing.

    Stripping goes through the renderer (render.py's `strip_annotations` +
    `render`), not a regex over `because "..."` / `note:` text: a
    mechanical AST transform can't be fooled by a quoted string that
    happens to contain the word `because`, and reusing the renderer here
    is itself a live check on the renderer's own correctness.
    """
    prog = parse(src)
    stripped_src = render(strip_annotations(prog))
    a_out, a_eff, a_surf = run_and_capture(src, **kw)
    b_out, b_eff, b_surf = run_and_capture(stripped_src, **kw)
    assert a_out == b_out, (
        f"output differs after stripping annotations:\n"
        f"  with:    {a_out}\n  without: {b_out}")
    assert a_eff == b_eff, (
        f"effect log differs after stripping annotations:\n"
        f"  with:    {a_eff}\n  without: {b_eff}")
    assert a_surf == b_surf, (
        f"effect surface differs after stripping annotations:\n"
        f"  with:    {a_surf}\n  without: {b_surf}")


def test_inertness_on_the_annotated_demo():
    """The one file in the repo that actually carries annotations to
    strip -- the full three-way run-based proof."""
    assert_inert(open("annotated.planes").read())


def test_inertness_across_every_standalone_planes_file():
    """Every other standalone program in the repo has no annotations to
    begin with, so stripping is a no-op and the three-way comparison
    holds trivially -- still run for real, not assumed, and it also
    doubles as a regression net for the renderer across the corpus's
    real syntax variety (nested for-each/where, multi-word calls,
    foreign declarations, or-fail, records)."""
    for path in STANDALONE_PLANES_FILES:
        if path == "annotated.planes":
            continue
        src = open(path).read()
        kw = FIXTURE_KWARGS.get(path, {})
        assert_inert(src, **kw)


def test_strip_is_structurally_a_no_op_on_unannotated_programs():
    """A second, execution-free angle on the same guarantee: for a program
    with no `because`/`note` to begin with, strip_annotations() must
    return something structurally identical to the parse it started
    from -- covers the multi-file fixtures under demo/ that are not
    meant to run standalone (they are `use`d by a sibling file, not
    executed directly, some needing a `known` name table or a stub this
    file has no way to construct generically), where the run-based check
    above cannot reach. annotated.planes is excluded here on purpose --
    it is the one file in the repo that IS annotated, so stripping it is
    supposed to change the AST; that direction is what
    test_inertness_on_the_annotated_demo proves instead."""
    for path in all_planes_files():
        if path in ("annotated.planes", "demo/app/net.planes"):
            continue
        prog = parse(open(path).read())
        stripped = strip_annotations(prog)
        assert len(prog) == len(stripped), path
        assert all(ast_equal(a, b) for a, b in zip(prog, stripped)), path


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
