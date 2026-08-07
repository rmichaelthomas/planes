"""world_ir.py — the Python World IR (world-v1) parser/validator.

Horizon Phase 0 Build 1. Reads `grammar/protocols/world-v1.json` and validates
a world envelope (a dict of records, in Python's native value form) against
it: version first, then each of the seven §8 facets in a fixed order, then a
pass over any envelope key the protocol does not name.

Refusal follows the same voice as `interp.py`'s `records_from_json` — an
unrecognized protocol version refuses the whole envelope before any record is
checked, and every raise names a tag, a detail, and a fix. There is no
coercion at the type boundary: a field whose value fails its declared type
refuses, exactly as `+` does not coerce and `require_text` does not either.

This module adds no builtin, no effect, and no value kind — it is a validator
over the existing value model, not a change to it.
"""
import json
import os

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_PROTOCOL_PATH = os.path.join(_REPO_ROOT, "grammar", "protocols", "world-v1.json")

with open(_PROTOCOL_PATH, encoding="utf-8") as _f:
    PROTOCOL = json.load(_f)

SUPPORTED_VERSION = PROTOCOL["version"]
RECORDS = PROTOCOL["records"]

# Fixed enumeration order — spec §8.1-8.7, and the order every implementation
# (Python, JS, self-hosted Planes) walks the seven facets in. The conformance
# gate's byte-identical comparison depends on this order being the same
# everywhere, so it is a plain tuple, not derived from dict iteration order.
FACET_ORDER = (
    "identity", "situation", "relation", "behavior",
    "expression", "affordance", "lineage",
)
FIELD_ORDER = {facet: tuple(f["name"] for f in RECORDS[facet]["fields"]) for facet in FACET_ORDER}


class WorldIRError(Exception):
    """A refusal naming the world-v1 rule it broke — `tag`, `detail`, `fix`,
    the same three-part shape `interp.py`'s `PlanesError` carries, kept as a
    standalone class so this module has no import dependency on the language
    implementation it validates data for."""

    def __init__(self, tag, detail, fix):
        self.tag = tag
        self.detail = detail
        self.fix = fix
        super().__init__(f"{tag}: {detail}")


def _type_ok(value, type_name):
    """No coercion: a value either already matches `type_name` or it does
    not. `bool` is checked before the numeric types because Python's `bool`
    is a subclass of `int` — an unguarded numeric check would silently
    accept `true`/`false` as `integer`."""
    if type_name == "boolean":
        return isinstance(value, bool)
    if isinstance(value, bool):
        return False
    if type_name in ("identifier", "semantic-id", "source-map-path"):
        return isinstance(value, str) and len(value) > 0
    if type_name == "text":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, (int, float)) and float(value).is_integer()
    if type_name == "number":
        return isinstance(value, (int, float))
    if type_name == "normalized-number":
        return isinstance(value, (int, float)) and 0 <= value <= 1
    raise WorldIRError(
        "unknown-field-type",
        f"world-v1.json declares field type {type_name!r}, which this parser does not know",
        "add a case for the new type to _type_ok in world_ir.py, in the same commit "
        "that adds it to world-v1.json")


def _validate_record(facet, record_value):
    """Returns (normalized_fields, None) or (None, reason).

    Presence is checked all at once, not field by field: a record either
    carries every field the facet declares or it does not, matching the
    self-hosted Planes implementation's `when r is { f1, f2, ... }:` —
    a single shape match, not a sequence of per-field presence tests (`when`
    cannot test a field whose name is itself a runtime value). Once presence
    holds, type failures are reported by field, in the facet's declared
    order, so every implementation names the same field first."""
    if not isinstance(record_value, dict):
        return None, "the record is not a record of fields"
    field_specs = RECORDS[facet]["fields"]
    if not all(f["name"] in record_value for f in field_specs):
        return None, "the record is missing one or more required fields"
    normalized = {}
    for field in field_specs:
        name, type_name = field["name"], field["type"]
        value = record_value[name]
        if not _type_ok(value, type_name):
            return None, f"field '{name}' fails its declared type '{type_name}'"
        normalized[name] = value
    return normalized, None


def parse_world_envelope(envelope):
    """Validate `envelope` against world-v1.

    Returns `(normalized, warnings)` on success — `normalized` is a dict
    keyed by `"version"` plus every facet present in the envelope;
    `warnings` is a sorted list of `"unknown-optional-record:<name>"`
    strings, one per envelope key the protocol does not name.

    Raises `WorldIRError` on refusal: an unsupported protocol version
    refuses the whole envelope before any record is checked; a missing or
    malformed critical record, or a malformed known-optional record, stops
    the parse. An unknown record never refuses — it warns and is dropped.
    """
    if not isinstance(envelope, dict):
        raise WorldIRError(
            "malformed-world-envelope",
            "the world envelope is not a record of fields",
            "provide the envelope as a record whose fields are 'version' plus "
            "the world-v1 facet names")

    version = envelope.get("version")
    # `isinstance(version, bool)` is checked before the equality, not folded
    # into it: Python's `bool` is a subtype of `int`, so `True == 1` is true
    # and an unguarded `!=` would silently accept `true` as version 1 — the
    # same coercion `_type_ok`'s boolean-before-numeric ordering guards
    # against for facet fields.
    if isinstance(version, bool) or version != SUPPORTED_VERSION:
        raise WorldIRError(
            "unsupported-world-protocol-version",
            f"world envelope declares protocol version {json.dumps(version)}, "
            f"which is not {SUPPORTED_VERSION}",
            "regenerate the envelope with a world-v1 protocol matching this parser's version — "
            "if the envelope is newer than what this parser reads, upgrade the parser instead "
            "of regenerating the envelope")

    normalized = {"version": SUPPORTED_VERSION}
    for facet in FACET_ORDER:
        spec = RECORDS[facet]
        if facet not in envelope:
            if spec["critical"]:
                raise WorldIRError(
                    "missing-critical-record",
                    f"critical record '{facet}' is missing from the world envelope",
                    f"add the '{facet}' record — {facet} is a critical facet and the "
                    "envelope cannot be applied without it")
            continue
        fields, reason = _validate_record(facet, envelope[facet])
        if reason is not None:
            tag = "malformed-critical-record" if spec["critical"] else "malformed-optional-record"
            raise WorldIRError(
                tag,
                f"record '{facet}' is malformed: {reason}",
                f"correct '{facet}' so every field world-v1.json declares for it is present "
                "and matches its declared type")
        normalized[facet] = fields

    known_keys = set(FACET_ORDER) | {"version"}
    warnings = sorted(
        f"unknown-optional-record:{key}" for key in envelope if key not in known_keys)

    return normalized, warnings


def _format_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def canonical_outcome_string(envelope):
    """The cross-implementation comparison form `test_world_ir_conformance.py`
    checks byte-for-byte. Deliberately not JSON — a hand-built, fixed-order
    text form that Python, JS, and self-hosted Planes can each produce
    without needing a shared serializer, the same way the three interpreters'
    canonical-form agreement (README's 349-shape sweep) is text, not a
    structure compared by a fourth piece of code."""
    try:
        normalized, warnings = parse_world_envelope(envelope)
    except WorldIRError as e:
        return "\n".join([
            "world-ir-outcome: refuse",
            f"tag: {e.tag}",
            f"detail: {e.detail}",
            f"fix: {e.fix}",
        ])
    lines = [
        "world-ir-outcome: accept",
        f"version: {normalized['version']}",
        f"warnings: {','.join(warnings)}",
    ]
    for facet in FACET_ORDER:
        if facet not in normalized:
            continue
        for name in FIELD_ORDER[facet]:
            lines.append(f"{facet}.{name}: {_format_value(normalized[facet][name])}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    envelope_in = json.load(sys.stdin)
    sys.stdout.write(canonical_outcome_string(envelope_in))
