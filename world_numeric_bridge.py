"""world_numeric_bridge.py — Horizon Phase 0 Build 4: the numeric bridge (spec §9.4).

Last Phase 0 build. Builds 1-3 carried semantic positions, gains, and
normalized values across the `to_host`/`from_foreign` boundary as exact
Planes-boundary numbers with no unit quantization — `world-v1.json` said so
explicitly. This module defines the discipline `world-v1.json`'s
`coordinates.numericBridge` now names: a declared fixed-point unit convention
layered on the EXISTING boundary seam, not a new numeric mechanism.

A "unit" here is a `(unit-name, places)` pair — `places` decimal places of
fixed-point precision, declared per field in `grammar/protocols/world-v1.json`
(`situation.x`/`situation.y` carry `unit: "world-position"`, `places: 3`).
Quantizing to `places` decimal places is exactly what `Number.round_to`
already does; this module does not invent a second rounding rule, only the
convention for WHEN and WHY it runs at a boundary crossing, and the marking
discipline that keeps a lossy crossing visible.

Two functions carry the whole discipline:

  `quantize_outcome(value, places)`   the REACHABLE arithmetic: round via
                                       round_to, report whether it was lossy.
                                       Ordinary Planes (four operators,
                                       `round ... to N places`, `==`) can
                                       compute this — see
                                       grammar/world_numeric_bridge.planes,
                                       the self-hosted mirror of this half.

  `quantize(value, unit, places)`     the FULL discipline: `quantize_outcome`
                                       plus attaching a named `Approximation`
                                       to a lossy crossing (the same
                                       mechanism `sine`/`root` use). NOT
                                       reachable from `.planes` source — a
                                       program cannot construct an
                                       Approximation itself, only trigger one
                                       via a host-implemented builtin. See
                                       grammar/world_numeric_bridge.planes's
                                       own docstring for why this half is
                                       Python+JS only, by design.

`to_host_quantized`/`from_host_quantized` wrap `quantize` around the existing
`to_host`/`from_foreign` for the two crossing directions; `is_deterministic`
states the §9.4 rule that two runs are compared on the semantic canonical
form, never on host-rendered floats.

No new numeric type. `Number`, `Approximation`, `MAX_DENOMINATOR`, and
`round_to` are read here, never modified — the fixed-point unit is boundary
metadata (`grammar/protocols/world-v1.json`'s field declarations), and a
quantized position is still an ordinary exact Planes `Number` inside the
language.
"""
from interp import from_foreign, to_host
from planes_num import Approximation
from world_delta import semantic_hash
from world_ir import RECORDS


def declared_unit(facet, field_name):
    """(unit, places) declared for `facet.field_name` in world-v1.json's own
    field spec (Phase 1's boundary metadata), or `None` when the field
    carries no declared unit and crosses via `to_host` exactly as Builds 1-3
    already do, unquantized.

    Raises `KeyError` if `facet.field_name` names no world-v1 field at all —
    a caller error (an unknown facet/field pair), distinct from "a known
    field with no declared unit"."""
    for field in RECORDS[facet]["fields"]:
        if field["name"] == field_name:
            if "unit" in field and "places" in field:
                return field["unit"], field["places"]
            return None
    raise KeyError(f"{facet}.{field_name} is not a world-v1 field")


def quantize_outcome(value, places):
    """Round `value` to `places` decimal places via the existing
    `Number.round_to`, and report whether that changed the value. This is
    the REACHABLE half of the bridge — every implementation, including the
    self-hosted `grammar/world_numeric_bridge.planes`, computes exactly this
    from `round_to` + `==`. Returns `(rounded, lossy)`."""
    rounded = value.round_to(places)
    return rounded, rounded.q != value.q


def _quantization_approximation(unit, places):
    """Same shape as `planes_num.SINE_APPROXIMATION`/`ROOT_APPROXIMATION`:
    an `Approximation` naming exactly what happened and at what precision,
    so `why` on a quantized value reports the truth rather than a silent
    rounding."""
    return Approximation(
        "quantize",
        f"fixed-point boundary quantization to unit '{unit}' at {places} "
        f"decimal place(s), rounded half away from zero via round_to "
        f"(numeric bridge, spec §9.4)")


def quantize(value, unit, places):
    """The bridge's one quantization rule (§9.4 requirements 1-2 both run
    through this). Rounds `value` to `places` decimal places via
    `quantize_outcome` — the same named, visible rounding a program's own
    `round ... to N places` uses, not a second rule — and marks the result
    `approx`, naming the quantization as provenance, exactly when rounding
    actually changed the value's rational.

    A value already exact at its declared scale crosses unmarked. A value
    that was already approximate before this call (e.g. the result of
    `sine`) crosses with its EXISTING marker intact — that marker already
    discloses the non-exactness, so quantizing it further attaches no
    second one."""
    rounded, lossy = quantize_outcome(value, places)
    if not lossy or value.approx is not None:
        return rounded
    return rounded.with_approx(_quantization_approximation(unit, places))


def to_host_quantized(value, unit, places):
    """Outbound (§9.4 requirement 1): quantize, then cross through the
    existing `to_host`, unchanged. Returns `(native, quantized)` — the
    host-native int/float a physics/GPU host would receive, AND the
    quantized Planes `Number` itself, for a caller that needs to hold onto
    the quantized value rather than discard it once it crosses."""
    quantized = quantize(value, unit, places)
    return to_host(quantized), quantized


def from_host_quantized(raw, unit, places):
    """Inbound (§9.4 requirement 2): read `raw` (an int/float arriving from
    a host) back as an exact rational via the existing `from_foreign`, then
    pin it to its declared scale before it is usable as a Planes value —
    the exact-rational core is never handed a raw float claiming an
    exactness it does not have."""
    return quantize(from_foreign(raw), unit, places)


def is_deterministic(envelope_a, envelope_b):
    """§9.4 requirement 3: two runs are compared for determinism on the
    semantic canonical form, never on host-rendered floats. Reuses
    `world_delta.semantic_hash` — the same SHA-256-over-canonical-outcome-
    string Build 3's delta/event log already hash-chains on — so this build
    states no new comparison primitive, only the rule that this is the one
    to use for it."""
    return semantic_hash(envelope_a) == semantic_hash(envelope_b)


def canonical_quantize_outcome_string(value, places):
    """The cross-implementation comparison form
    `test_world_numeric_bridge_conformance.py` checks byte-for-byte against
    `js/world_numeric_bridge.mjs`'s `canonicalQuantizeOutcomeString` and
    `grammar/world_numeric_bridge.planes`'s own rendering — the same
    hand-built, fixed-order text-form discipline `world_ir.py`'s
    `canonical_outcome_string` established."""
    rounded, lossy = quantize_outcome(value, places)
    return (f"quantize-outcome: value={value.text()} places={places} "
            f"quantized={rounded.text()} lossy={'true' if lossy else 'false'}")


if __name__ == "__main__":
    import json
    import sys

    from planes_num import Number

    payload = json.load(sys.stdin)
    sys.stdout.write(canonical_quantize_outcome_string(
        Number.parse(payload["value"]), payload["places"]))
