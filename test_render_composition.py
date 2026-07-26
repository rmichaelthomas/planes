"""S6, Phase 2 — the composition defect, fixed (render round-trips the corpus).

Phase 1 pinned the defect the analyser port (S5) found: render produces source
that does not reparse. Reproducing it confirmed the mechanism AND that it was a
CLASS, not one instance — four distinct render round-trip defects, all masked
because the only files exercising them (grammar/interp.planes, parser.planes)
sat outside render.py's own round-trip corpus (*.planes + demo/**):

  1. a greedy comma tail -- a call's `of` argument list, or a RecordUpdate's
     `with` field list -- in a record-field-value or list-element position;
  2. the `first N of L` operator, whose bare Var count is swallowed as the call
     `k of parts` and whose sub-unary list is split by precedence;
  3. a `X.name` field access whose base has a greedy tail: `(call).kind` bare
     binds `.kind` to the call's last argument;
  4. an `or fail as tag:` HANDLER block, dropped entirely by render_orfail.

Phase 2 fixes all four in render.py (and mirrors them in render.mjs), by
parenthesisation and by rendering the handler block -- no grammar change. This
file flips the Phase 1 assertions to the fixed behaviour; the composition
generator that proves the class is closed is Phase 3.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

from parser import PlanesSyntaxError, parse
from render import ast_equal, render

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))


def _round_trips(src):
    prog = parse(src)
    try:
        prog2 = parse(render(prog))
    except PlanesSyntaxError:
        return False
    return len(prog) == len(prog2) and all(
        ast_equal(a, b) for a, b in zip(prog, prog2))


# The minimal reproduction: a two-field record whose first field's value is a
# multi-argument call. This is grammar/interp.planes:1152's shape, distilled.
REPRO_CALL_IN_RECORD = (
    "to f of a, b:\n  give a\n\n"
    "x = { k: (f of a, b), k2: 9 }\n"
)


def test_call_in_record_round_trips():
    """FLIPPED from Phase 1. render now wraps the greedy call, emitting
    `{ k: (f of (a), (b)), k2: 9 }`, which reparses to the same AST."""
    rendered = render(parse(REPRO_CALL_IN_RECORD))
    assert "k: (f of (a), (b)), k2:" in rendered, rendered
    assert _round_trips(REPRO_CALL_IN_RECORD)


def test_every_corpus_file_now_round_trips():
    """FLIPPED from Phase 1. No standalone-parseable file fails the render
    round-trip any more -- interp.planes and parser.planes included, which never
    round-tripped before this build."""
    paths = sorted(glob.glob("*.planes")) + \
        sorted(glob.glob("demo/**/*.planes", recursive=True)) + \
        sorted(glob.glob("grammar/*.planes"))
    paths = [p for p in paths if p != "demo/app/net.planes"]
    broken = []
    for p in paths:
        try:
            parse(open(p, encoding="utf-8").read())
        except PlanesSyntaxError:
            continue
        if not _round_trips(open(p, encoding="utf-8").read()):
            broken.append(p)
    assert broken == [], broken


def test_each_of_the_four_defect_shapes_round_trips():
    """One distilled case per defect (Phase 2), all fixed."""
    prelude = "to f of a, b:\n  give a\n\nto g of a:\n  give a\n\n"
    cases = [
        # 1. greedy call in a record field, and a RecordUpdate in a record field
        'x = { k: (f of a, b), k2: 9 }\n',
        'x = { k: (p with a: 1, b: 2), k2: 9 }\n',
        # 1b. greedy call in a list element
        'x = [(f of a, b), 9]\n',
        # 2. the first operator with a bare Var count and a sub-unary list
        'x = first (k) of parts\n',
        'x = first (k) of (parts plus [1])\n',
        # 3. a field access on a call result
        'x = (g of a).kind\n',
        # 4. an or-fail handler block
        'x = (f of a, b) or fail as e:\n  give g of e\n',
    ]
    for src in cases:
        assert _round_trips(prelude + src), src


# ================================================================ Phase 3: composition coverage
#
# A.3: per-node-kind exhaustiveness cannot reach a bug living in a valid
# composition of two handled kinds (this build found four such bugs). This
# generator nests every expression kind inside every kind that can contain an
# expression, deterministically, and checks render->reparse->ast_equal -- on
# both implementations and cross-implementation (the byte-identical render plus a
# both-sides round-trip is exactly the cross-implementation round-trip: Python
# render == JS render, and each reparses to the same AST it was rendered from).
#
# Reachability: each case is built as SOURCE and parsed first, so only ASTs the
# parser can actually produce are tested; a composition the grammar rejects is
# skipped, not counted. The matrix is derived from the grammar -- INNER lists
# every kind render_expr emits; CONTAINER lists every position a grammar
# production reads a sub-expression.

# A prelude of the functions the cases call, so a bare `f of a, b` is read as a
# call. Prepended to every case; it round-trips trivially.
_PRELUDE = (
    "to f of a, b:\n  give a\n\n"
    "to g of a:\n  give a\n\n"
    "to cc of a, b:\n  give a\n\n"
)

# INNER: kind -> a source fragment that parses to that kind, parenthesised where
# a bare form would not embed. Every expression kind render_expr handles.
_INNER = {
    "Num": "1",
    "Str": '"s"',
    "Bool": "true",
    "Nothing": "nothing",
    "Var": "z",
    "ListLit": "[1, 2]",
    "RecordLit": "{ a: 1 }",
    "RecordUpdate": "(p with a: 1, b: 2)",
    "ListPlus": "(xs plus 1)",
    "BinOpAdd": "(1 + 2)",
    "BinOpCmp": "(z > 0)",
    "First": "(first (k) of parts)",
    "Not": "(not z)",
    "IsNothing": "(z is nothing)",
    "Field": "z.fld",
    "Call2": "(f of a, b)",
    "Call1": "(g of a)",
    "Round": "(round v to 2 places)",
    "ForEach": "(for each i in xs: i)",
    "OrFail": "(g of a or fail as e)",
}

# CONTAINER: name -> a source template with the marker HOLE where the inner goes.
# Every grammar position that reads a sub-expression.
_CONTAINER = {
    "record-field-first": "x = { k: HOLE, k2: 9 }\n",
    "record-field-last": "x = { k1: 9, k: HOLE }\n",
    "record-field-only": "x = { k: HOLE }\n",
    "recordupdate-field-first": "x = p with k: HOLE, k2: 9\n",
    "recordupdate-field-last": "x = p with k1: 9, k: HOLE\n",
    "list-first": "x = [HOLE, 9]\n",
    "list-last": "x = [9, HOLE]\n",
    "list-only": "x = [HOLE]\n",
    "call-arg-first": "x = cc of (HOLE), (9)\n",
    "call-arg-last": "x = cc of (9), (HOLE)\n",
    "field-base": "x = (HOLE).fld\n",
    "binop-left": "x = HOLE + 1\n",
    "binop-right": "x = 1 + HOLE\n",
    "not-operand": "x = not HOLE\n",
    "isnothing-operand": "x = HOLE is nothing\n",
    "round-value": "x = round HOLE to 2 places\n",
    "round-places": "x = round v to HOLE places\n",
    "listplus-base": "x = HOLE plus 1\n",
    "listplus-item": "x = xs plus HOLE\n",
    "assign-rhs": "x = HOLE\n",
    "give": "to fn:\n  give HOLE\n",
    "show": "show HOLE\n",
    "if-cond": "if HOLE:\n  show 1\n",
    "foreach-source": "x = for each i in HOLE: i\n",
    "foreach-where": "x = for each i in xs where HOLE: i\n",
    "foreach-body": "x = for each i in xs: HOLE\n",
    "when-subject": "when HOLE is { a: 1 }:\n  show 1\n",
    "when-match": "when r is { a: HOLE }:\n  show 1\n",
    "writeto-value": 'write HOLE to "f"\n',
    "writeto-dest": 'write [1] to HOLE\n',
    "orfail-expr": "x = HOLE or fail as e\n",
    "first-count": "x = first (HOLE) of parts\n",
    "first-list": "x = first (k) of (HOLE)\n",
    "fail-message": "fail HOLE as t\n",
}


def _composition_sources():
    """Every (container, inner) pair as a source string, deterministically
    ordered. Returns a list of (label, source)."""
    out = []
    for cname in sorted(_CONTAINER):
        for iname in sorted(_INNER):
            src = _PRELUDE + _CONTAINER[cname].replace("HOLE", _INNER[iname])
            out.append((f"{cname} <- {iname}", src))
    return out


def _js_render_batch(sources):
    r = subprocess.run(
        [NODE, "js/cli.mjs", "render-batch", json.dumps(sources)],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node render-batch failed: {r.stderr}")
    return json.loads(r.stdout)


def test_composition_round_trip_matrix():
    """The phase that addresses the class. Every expression kind nested in every
    container, render->reparse->ast_equal, on both implementations and
    cross-implementation. Reports coverage; asserts no case fails."""
    cases = _composition_sources()
    sources = [src for _, src in cases]

    # Python side: parse (reachability), then render->reparse->ast_equal.
    py = []
    for _label, src in cases:
        try:
            prog = parse(src)
        except PlanesSyntaxError:
            py.append({"parsed": False})
            continue
        try:
            prog2 = parse(render(prog))
            ok = len(prog) == len(prog2) and all(
                ast_equal(a, b) for a, b in zip(prog, prog2))
        except PlanesSyntaxError:
            ok = False
        py.append({"parsed": True, "rendered": render(prog), "ok": ok})

    # JS side + cross-implementation, in one batch call.
    js = _js_render_batch(sources)
    assert len(js) == len(py) == len(cases)

    total = len(cases)
    covered = sum(1 for r in py if r["parsed"])
    failures = []
    for (label, _src), p, j in zip(cases, py, js):
        if not p["parsed"]:
            # Both implementations must agree the grammar rejects it.
            if j["parsed"]:
                failures.append(f"{label}: py rejected, js parsed")
            continue
        if not j["parsed"]:
            failures.append(f"{label}: py parsed, js rejected")
            continue
        if not p["ok"]:
            failures.append(f"{label}: PY round-trip FAILED\n    {p['rendered'].strip()}")
        if not j["ok"]:
            failures.append(f"{label}: JS round-trip FAILED\n    {j['rendered'].strip()}")
        if p["rendered"] != j["rendered"]:
            failures.append(
                f"{label}: render DIVERGES\n    py={p['rendered'].strip()}\n"
                f"    js={j['rendered'].strip()}")

    print(f"    [composition coverage: {total} pairs, {covered} reachable "
          f"(parsed on both), {len(failures)} failures]")
    assert not failures, ("composition round-trip failures:\n"
                          + "\n".join(failures))


if __name__ == "__main__":
    fails = []
    tests = [(k, f) for k, f in sorted(globals().items())
             if k.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            fails.append(name)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
