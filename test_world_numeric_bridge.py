"""test_world_numeric_bridge.py — Horizon Phase 0 Build 4, last Phase 0 build.

Covers the build prompt's §4/§5 acceptance: quantization correctness (via
the existing `round_to`), exactness preserved on the inbound crossing,
`approx` marking on lossy crossings only, an exact crossing staying exact,
and the §9.4 determinism-on-semantic-hashes rule.
`test_world_numeric_bridge_conformance.py` is the byte-identical-across-
Python/JS/.planes half of this gate; this file is Python-only correctness.
"""
import copy
import sys

import world_delta as wd
import world_ir as w
import world_numeric_bridge as b
from planes_num import Number

VALID_ENVELOPE = {
    "version": 1,
    "identity": {
        "id": "subject-1", "kind": "vehicle", "subkind": "hydrofoil",
        "displayName": "Reso", "status": "canonical", "schemaVersion": 1,
    },
    "situation": {
        "containingPlace": "landing-1", "space": "world", "x": 10, "y": -5,
        "state": "docked", "occupancy": 0, "anchorId": "anchor-1",
        "chunkActive": True, "physicsRef": "phys-1", "audioRef": "audio-1",
    },
    "lineage": {
        "corpusSource": "ala-eriri", "culturalStatus": "canonical",
        "author": "studio", "origin": "system", "because": "canonical corpus asset",
        "agreementFingerprint": "fp-1", "permittedTransformations": "remix",
        "publishingRestriction": "none", "systemBoundary": "immutable",
    },
}


def _valid():
    return copy.deepcopy(VALID_ENVELOPE)


# ============================================================= declared_unit

def test_declared_unit_finds_situation_x_and_y():
    assert b.declared_unit("situation", "x") == ("world-position", 3)
    assert b.declared_unit("situation", "y") == ("world-position", 3)


def test_declared_unit_is_none_for_a_field_with_no_declared_unit():
    # occupancy is an `integer` field — never carries a unit (§9.4 convention).
    assert b.declared_unit("situation", "occupancy") is None


def test_declared_unit_raises_for_an_unknown_field():
    try:
        b.declared_unit("situation", "not-a-real-field")
        assert False, "expected KeyError"
    except KeyError:
        pass


# ================================================================ quantize_outcome

def test_quantize_outcome_correctness():
    cases = [
        # (value text, places) -> (expected quantized text, expected lossy)
        (("1.2341", 3), ("1.234", True)),
        (("1.2349", 3), ("1.235", True)),
        (("1.500", 3), ("1.5", False)),
        (("7", 3), ("7", False)),
        (("-1.2349", 3), ("-1.235", True)),
        (("2.6", 0), ("3", True)),
        (("0.5", 0), ("1", True)),
        (("-0.5", 0), ("-1", True)),
    ]
    for (value_text, places), (expected_text, expected_lossy) in cases:
        rounded, lossy = b.quantize_outcome(Number.parse(value_text), places)
        assert rounded.text() == expected_text, (value_text, places, rounded.text())
        assert lossy is expected_lossy, (value_text, places, lossy)


def test_quantize_outcome_reuses_round_to_exactly():
    """§N+3.2's "round_to reuse" proof: a hand-rounded value and the
    bridge's own quantized value agree — not a second rounding rule."""
    for value_text, places in [("1.2349", 3), ("-7.777", 2), ("100", 4), ("0.0005", 3)]:
        value = Number.parse(value_text)
        rounded, _lossy = b.quantize_outcome(value, places)
        hand_rounded = value.round_to(places)
        assert rounded.q == hand_rounded.q


# ========================================================================= quantize

def test_exact_crossing_stays_exact():
    v = Number.parse("1.500")
    q = b.quantize(v, "world-position", 3)
    assert q.is_exact
    assert q.approx is None
    assert q.q == v.q


def test_lossy_crossing_is_marked_with_a_named_approximation():
    v = Number.parse("1.4995")
    q = b.quantize(v, "world-position", 3)
    assert not q.is_exact
    assert q.approx is not None
    assert q.approx.op == "quantize"
    assert "world-position" in q.approx.detail
    assert "3" in q.approx.detail
    assert q.text() == "1.5"


def test_already_approximate_value_keeps_its_own_marker():
    """A value that was already approximate before quantization (e.g. the
    result of `sine`) is not relabelled as a quantization artifact — its
    existing marker already discloses the non-exactness."""
    from planes_num import sine_degrees

    approximate = sine_degrees(Number.parse("30"))
    assert approximate.approx is not None and approximate.approx.op == "sine"
    q = b.quantize(approximate, "world-position", 3)
    assert q.approx is approximate.approx


def test_no_unmarked_lossy_crossing_across_many_values():
    """Invariant 2, swept over a deterministic spread of fractions (not
    `random`, so this test's own expectations do not depend on an RNG's
    cross-run stability): every crossing that changes the rational is
    marked; every crossing that does not is unmarked."""
    for n in range(-50, 51):
        for d in (1, 3, 7, 1000):
            v = Number(n) / Number(d)
            q = b.quantize(v, "world-position", 3)
            if q.q != v.q:
                assert q.approx is not None, (n, d, "lossy crossing left unmarked")
            else:
                assert q.approx is None, (n, d, "exact crossing marked anyway")


# ============================================================ outbound / inbound

def test_to_host_quantized_matches_to_host_of_the_quantized_value():
    from interp import to_host

    v = Number.parse("1.4995")
    native, quantized = b.to_host_quantized(v, "world-position", 3)
    assert native == to_host(quantized)
    assert native == 1.5


def test_from_host_quantized_pins_a_noisy_host_float_to_the_declared_scale():
    """Inbound (§9.4 requirement 2): a raw host float that does not sit
    exactly on the declared scale is quantized down to it, and the
    exact-rational core never sees the raw, un-pinned float as a value
    claiming full exactness."""
    noisy = 1.4999999999999998  # a plausible host float, not a clean 3-place decimal
    q = b.from_host_quantized(noisy, "world-position", 3)
    assert q.text() == "1.5"
    assert q.approx is not None
    assert q.approx.op == "quantize"


def test_from_host_quantized_exact_at_scale_stays_exact():
    q = b.from_host_quantized(1.5, "world-position", 3)
    assert q.is_exact
    assert q.text() == "1.5"


def test_from_host_quantized_integer_stays_exact():
    q = b.from_host_quantized(10, "world-position", 3)
    assert q.is_exact
    assert q.text() == "10"


# ==================================================================== determinism

def test_identical_semantic_hashes_are_deterministic_even_if_a_hypothetical_host_float_differs():
    """§9.4 requirement 3, stated as a test: comparison is on the semantic
    canonical form, never on host-rendered floats. `envelope_a`/`envelope_b`
    are semantically identical world-v1 envelopes; a simulated "host
    render" artifact attached OUTSIDE each envelope (never part of the
    world-v1 canonical form at all, exactly because a host renderer's own
    output is not semantic state) differs between them, and that difference
    is irrelevant to the determinism verdict."""
    envelope_a = _valid()
    envelope_b = _valid()
    simulated_host_render_a = {"hostRenderedX": 10.000000001}  # platform float noise
    simulated_host_render_b = {"hostRenderedX": 10.000000002}  # a different platform's noise
    assert simulated_host_render_a != simulated_host_render_b

    assert b.is_deterministic(envelope_a, envelope_b)
    assert wd.semantic_hash(envelope_a) == wd.semantic_hash(envelope_b)


def test_a_genuine_semantic_divergence_is_caught_by_the_hash():
    envelope_a = _valid()
    envelope_b = _valid()
    envelope_b["situation"]["x"] = 999

    assert not b.is_deterministic(envelope_a, envelope_b)
    assert wd.semantic_hash(envelope_a) != wd.semantic_hash(envelope_b)


def test_determinism_check_is_the_normalized_envelopes_canonical_form():
    """Confirms `is_deterministic` is exactly `world_ir.canonical_outcome_string`
    agreement under a hash, not a structural dict comparison — two envelopes
    that normalize to the identical canonical string hash identically even
    if their raw (pre-normalization) dict key order differs."""
    envelope_a = _valid()
    envelope_b = {
        "lineage": envelope_a["lineage"],
        "situation": envelope_a["situation"],
        "identity": envelope_a["identity"],
        "version": envelope_a["version"],
    }
    normalized_a, _ = w.parse_world_envelope(envelope_a)
    normalized_b, _ = w.parse_world_envelope(envelope_b)
    assert w.canonical_outcome_string(normalized_a) == w.canonical_outcome_string(normalized_b)
    assert b.is_deterministic(envelope_a, envelope_b)


# =========================================================== parser stays green

def test_world_v1_json_declared_units_validate_through_build_1s_parser():
    """Phase 1 acceptance: world-v1.json's new `unit`/`places` field
    metadata is inert to the parser — a valid envelope built against the
    CURRENT protocol still normalizes cleanly, and the new keys never leak
    into a normalized record's own field values."""
    normalized, warnings = w.parse_world_envelope(_valid())
    assert warnings == []
    assert normalized["situation"]["x"] == 10
    assert normalized["situation"]["y"] == -5
    assert "unit" not in normalized["situation"]
    assert "places" not in normalized["situation"]


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
