"""test_world_emission.py — Horizon Phase 0 Build 2, Phase 1.

Covers the build prompt's §3 acceptance: a program emitting the three
critical facets round-trips emit -> parse -> accept, and an existing
corpus program's text output and effect log match a pre-build capture
byte-for-byte (§N+3.2's text/effect byte-identity proof).
"""
import copy
import sys

import world_ir as w
from host import TestHost
from interp import Interpreter

DEMO = "world_runtime_demo.planes"

# The pre-build capture (§N+3.2): benchmarks/world_shape.planes run against
# interp.py BEFORE this build's Show-case changes (git stash to main HEAD
# 5d55661, run, git stash pop — see reports/REPORT_WORLD_RUNTIME.md for the
# exact commands). Neither list has changed by one character since.
PRE_BUILD_OUTPUT = [
    "FINAL-TICK=31", "SUBJECT-COUNT=64", "EVENTS-LENGTH=32",
    "FACET-FIELD-COUNT=4", "SUBJECT-FIELD-COUNT=7", "WORLD-FIELD-COUNT=3",
]
PRE_BUILD_EFFECTS = [("show", t) for t in PRE_BUILD_OUTPUT]


def test_an_existing_corpus_program_shows_no_world_content_and_emits_nothing():
    """The gate must not fire for a program with no world content — none of
    world_shape.planes's `show`n values is a top-level record carrying a
    `version` field (the `version` fields in its subject records are
    nested inside `identity`, never at a shown value's own top level)."""
    itp = Interpreter(host=TestHost())
    itp.run_file("benchmarks/world_shape.planes")
    assert itp.output == PRE_BUILD_OUTPUT
    assert itp.effects == PRE_BUILD_EFFECTS
    assert itp.world_envelopes == []


def test_demo_world_program_emits_exactly_one_world_envelope():
    itp = Interpreter(host=TestHost())
    itp.run_file(DEMO)
    assert len(itp.world_envelopes) == 1


def test_the_emitted_envelope_parses_clean_through_build_1s_own_parser():
    """The round-trip proof: emission and Build 1's validator are two
    halves of one contract, so the SAME call `_maybe_emit_world_envelope`
    already made is re-run here independently, over the RAW form the
    interpreter actually emitted."""
    itp = Interpreter(host=TestHost())
    itp.run_file(DEMO)
    emission = itp.world_envelopes[0]
    normalized, warnings = w.parse_world_envelope(copy.deepcopy(emission.raw))
    assert warnings == []
    assert normalized == emission.normalized


def test_the_emitted_envelope_normalizes_to_the_expected_canonical_form():
    itp = Interpreter(host=TestHost())
    itp.run_file(DEMO)
    emission = itp.world_envelopes[0]
    outcome = w.canonical_outcome_string(emission.raw)
    assert outcome.startswith("world-ir-outcome: accept")
    assert "identity.id: wayfinder-1" in outcome
    assert "situation.x: 0" in outcome
    assert "lineage.corpusSource: ala-eriri" in outcome


def test_the_three_critical_facets_are_present_and_normalized():
    itp = Interpreter(host=TestHost())
    itp.run_file(DEMO)
    normalized = itp.world_envelopes[0].normalized
    assert set(w.FACET_ORDER) & set(normalized) >= {"identity", "situation", "lineage"}
    assert normalized["identity"]["id"] == "wayfinder-1"
    assert normalized["situation"]["x"] == 0
    assert normalized["lineage"]["corpusSource"] == "ala-eriri"


def test_emission_never_touches_output_effects_or_trace_length():
    """§N+1 invariant 2: emission rides beside show, never instead of it.
    `output`/`trace` stay the exact length a `show`-only run always had —
    one entry per show, whether or not that show also emitted a world
    envelope."""
    itp = Interpreter(host=TestHost())
    itp.run_file(DEMO)
    assert len(itp.output) == 1
    assert len(itp.trace) == 1
    assert itp.effects == [("show", "{record}")]


def test_a_shown_record_with_no_version_field_emits_nothing():
    itp = Interpreter(host=TestHost())
    itp.run("""
let x = {
  identity: {
    id: "a", kind: "b", subkind: "c", displayName: "d", status: "e", schemaVersion: 1
  }
}
show x
""")
    assert itp.world_envelopes == []
    assert itp.output == ["{record}"]


def test_a_shown_record_with_version_but_no_critical_facet_emits_nothing():
    itp = Interpreter(host=TestHost())
    itp.run("""
let x = { version: 1, note: "not world content" }
show x
""")
    assert itp.world_envelopes == []


def test_a_malformed_world_content_attempt_refuses_rather_than_silently_dropping():
    """Once the gate fires (version + a critical facet present), a
    malformed envelope is refused loudly, not swallowed — the same
    anti-obfuscation choice `world_ir.py` itself makes for a malformed
    critical record."""
    itp = Interpreter(host=TestHost())
    try:
        itp.run("""
let x = { version: 1, identity: { this: "is not a valid identity record" } }
show x
""")
        assert False, "expected a WorldIRError"
    except w.WorldIRError as e:
        assert e.tag == "malformed-critical-record"
    # The ordinary show already ran before the refusal (§N+1 invariant 2):
    # ordinary effect logging happens BEFORE the emission attempt.
    assert itp.output == ["{record}"]
    assert itp.effects == [("show", "{record}")]


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
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
