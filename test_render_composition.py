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
import sys

from parser import PlanesSyntaxError, parse
from render import ast_equal, render


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
