#!/usr/bin/env python3
"""S3d (build 3), Phase 5 — the effect surface of grammar/interp.planes.

A.3 is a prediction made before interp.planes existed: a Planes interpreter's
static effect surface is *every kind it has a reason to claim, always*,
because an interpreter performs whatever effects the program it runs
performs. This script is the first chance to check it against the real
artifact. It runs the static analyser (shapes.py) on grammar/interp.planes
and reports:

  1. the surface exactly -- which kinds, and whether it is all of them;
  2. whether the analyser stays total over the interpreter (no crash, a Surface
     out);
  3. origins_of behaviour across the interpreter's effects.

A refutation would be the more valuable result (A.3); this reports what the
analyser actually says, not what the prediction hoped.

`send` (B1, Sprint B) is excepted by name, the same way core_check.py's own
confirmation of this prediction excepts it: nothing in interp.planes's own
graph carries the program's data out, so it never has occasion to claim one.

Run:  .venv/bin/python3 scripts/measure_effect_surface.py
"""
import sys

sys.path.insert(0, ".")
from lexer import EFFECT_KINDS  # noqa: E402
from shapes import analyse_file  # noqa: E402

ALL_KINDS = set(EFFECT_KINDS)  # ask clock env random read send show write
EXPECTED_KINDS = ALL_KINDS - {"send"}
TARGET = "grammar/interp.planes"


def main():
    print(f"# effect surface of {TARGET} (Phase 5, A.3 under test)")
    print(f"# the {len(ALL_KINDS)} kinds: {sorted(ALL_KINDS)}")
    print(f"# expected here (send excepted by design): {sorted(EXPECTED_KINDS)}")
    print()

    # (2) totality: the analyser must not crash on the interpreter.
    total = True
    surface = None
    try:
        surface = analyse_file(TARGET, follow=True)
    except Exception as e:  # noqa: BLE001
        total = False
        print(f"ANALYSER NOT TOTAL: {type(e).__name__}: {e}")

    if surface is None:
        print("no surface produced")
        sys.exit(1)

    # (1) the surface, exactly.
    effects = surface.declared
    by_kind = {}
    for eff in effects:
        by_kind.setdefault(eff.kind, []).append(eff)

    kinds = set(by_kind)
    print("SURFACE (kind -> boundary : targets):")
    for kind in sorted(kinds):
        es = by_kind[kind]
        boundary = es[0].boundary
        targets = ", ".join(
            (e.target if not e.computed else "{computed}") for e in es)
        print(f"  {kind:8} {boundary:8} : {targets}")
    print()

    missing = EXPECTED_KINDS - kinds
    extra = kinds - EXPECTED_KINDS
    print(f"KINDS PRESENT : {sorted(kinds)}")
    print(f"ALL EXPECTED? : {kinds >= EXPECTED_KINDS}  "
          f"(missing: {sorted(missing) or 'none'}, "
          f"unexpected: {sorted(extra) or 'none'})")
    print(f"ANALYSER TOTAL: {total}")
    print()

    # (3) origins_of across the interpreter.
    print("ORIGINS_OF (per effect, static derivation walk):")
    for kind in sorted(kinds):
        for eff in by_kind[kind]:
            origins = surface.origins_of(eff)
            names = [lbl for (lbl, _f) in origins]
            shown = names if names else "(none — target is a literal/host name)"
            print(f"  {kind:8} target={eff.target!r:24} origins={shown}")
    print()

    verdict = "HELD" if kinds >= EXPECTED_KINDS else "REFUTED"
    print(f"A.3 PREDICTION: {verdict}")
    print(f"  the static effect surface of {TARGET} is "
          f"{'every kind expected' if kinds >= EXPECTED_KINDS else 'NOT every kind expected'}, "
          f"{'as predicted' if kinds >= EXPECTED_KINDS else 'against the prediction'}.")

    # exit non-zero only if the analyser was not total (a real failure); a
    # refutation of the prediction is a valid, reportable outcome, not an error.
    sys.exit(0 if total else 1)


if __name__ == "__main__":
    main()
