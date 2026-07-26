"""S6, Phase 1 — reproduce the composition defect (render produces
source that does not reparse), on the Python side, before any fix.

The analyser port (S5) found that render.py renders a multi-argument call used
as a record-field value in a form it cannot reparse — the call's argument-list
commas collide with the record's field separators. A.0 requires reproducing it
as a test and confirming the mechanism before changing code.

Confirmed, and BROADER than the single instance the report described (this is
what A.3's composition coverage exists to surface):

  * the greedy tail is not only a call's `of` argument list — a RecordUpdate's
    `with` field list is greedy the same way (`base with a: 1, b: 2` extends on a
    following `name: expr`);
  * even a ONE-argument call breaks, because `name of (a), k2` reads `k2` as a
    second bare-primary argument;
  * it occurs in record-field-value AND list-element positions;
  * TWO corpus files fail the render round-trip, not one: grammar/interp.planes
    (the reported site) and grammar/parser.planes.

Phase 1 pins the bug as it is TODAY (these tests assert the broken behaviour, so
the suite stays green — invariant 7). Phase 2 flips each assertion to the fixed
behaviour and lands the fix.
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


def test_reproduction_call_in_record_currently_fails_to_reparse():
    """PINS THE BUG (Phase 1). render strips the source's protective parens and
    emits `{ k: f of (a), (b), k2: 9 }`, whose commas collide with the record
    separators. Phase 2 flips this to assert a clean round-trip."""
    prog = parse(REPRO_CALL_IN_RECORD)
    rendered = render(prog)
    assert "k: f of (a), (b), k2:" in rendered, rendered
    # currently does NOT reparse — the defect
    try:
        parse(rendered)
        reparsed = True
    except PlanesSyntaxError:
        reparsed = False
    assert reparsed is False, "expected the known reparse failure (Phase 1)"


def test_the_two_corpus_files_that_fail_the_render_round_trip():
    """A.0: confirm the footprint. Exactly interp.planes and parser.planes fail
    render round-trip today. Phase 2 makes both round-trip."""
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
    assert broken == ["grammar/interp.planes", "grammar/parser.planes"], broken


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
