"""E1 -- the published effect-surface format, checked rather than just written.

`docs/surface-format-v2.md` is the specification five downstream projects
copy by hand (Undertow, Cutter, Omniglot, Koncord's `HostEffect`, 5xFive),
and `grammar/protocols/surface-v2.json` is its JSON Schema. This file is what
keeps the three from drifting apart:

  1. every one of the three hosts' `shapes_cli --json [--rules]` output, over
     a spread of real programs, validates against the schema;
  2. the schema's effect-kind enums agree with `grammar/vocabulary.json`
     (the closed eight-kind vocabulary, plus the `"unknown"` sentinel where
     it is actually allowed to appear -- never inside a rule, since the
     parser only ever accepts one of the eight there);
  3. the doc's own kind table (section 3) has not drifted from the same
     generated vocabulary.

B1 (Sprint B) bumped the format from 1 to 2 (`send` joined the vocabulary,
`ask` narrowed to fetch-only) and moved this suite from v1 to v2. Format 1's
doc and schema stay in the repo, frozen, as the `sprint-a-2026-09` tag's
record -- this file no longer checks them.

No JSON Schema library is a project dependency (`import jsonschema` succeeds
against the system `python3` on this machine but not against `.venv`, so
relying on it would be an unlisted, environment-dependent dependency) --
`validate()` below is a small validator for exactly the subset the schema
uses: `type`, `properties`, `required`, `additionalProperties`, `items`,
`enum`, `const`, and `anyOf` for nullability. The schema is deliberately
written to stay inside that subset (no `$ref`, no `oneOf`).

Program coverage: every one of the 51 `corpus/*.planes` programs, through
plain `--json`, on all three hosts -- runtime is a few seconds per host, so
this is the full corpus, not a sample (see `_timed` below if that changes).
A second, smaller spread -- `annotated.planes`, all of `demo/rules/`, all of
`demo/mcp/`, and the two corpus programs that carry a `rule` block
(`allowed-hosts.planes`, `audit-log.planes`) -- is run both with and without
`--rules`, on all three hosts, and additionally checked for byte-identical
agreement across the three (the schema alone cannot catch two hosts
agreeing with each other while both drifting from the spec).
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

import swift_host

NODE = shutil.which("node")
SWIFT = swift_host.SWIFT
REPO = os.path.dirname(os.path.abspath(__file__))

SCHEMA_PATH = os.path.join(REPO, "grammar", "protocols", "surface-v2.json")
VOCAB_PATH = os.path.join(REPO, "grammar", "vocabulary.json")
DOC_PATH = os.path.join(REPO, "docs", "surface-format-v2.md")


# ================================================================ the validator
#
# type, properties, required, additionalProperties, items, enum, const,
# anyOf/oneOf -- nothing else. Returns a list of error strings; empty means
# valid. `anyOf`/`oneOf`/`enum`/`const` short-circuit the rest of the schema
# at that node (JSON Schema itself allows combining them with `type`, but
# this document's schema never does, so there is nothing lost by keeping the
# validator this simple).

def _type_ok(instance, type_name):
    if type_name == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if type_name == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if type_name == "boolean":
        return isinstance(instance, bool)
    if type_name == "null":
        return instance is None
    if type_name == "string":
        return isinstance(instance, str)
    if type_name == "array":
        return isinstance(instance, list)
    if type_name == "object":
        return isinstance(instance, dict)
    raise ValueError(f"unsupported schema type {type_name!r}")


def _same_json_value(a, b):
    """Equality that does not let Python's `True == 1` blur enum/const checks."""
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def validate(instance, schema, path="$"):
    if "const" in schema:
        if not _same_json_value(instance, schema["const"]):
            return [f"{path}: expected const {schema['const']!r}, got {instance!r}"]
        return []

    if "enum" in schema:
        if not any(_same_json_value(instance, v) for v in schema["enum"]):
            return [f"{path}: {instance!r} is not in enum {schema['enum']!r}"]
        return []

    if "anyOf" in schema:
        attempts = []
        for sub in schema["anyOf"]:
            errs = validate(instance, sub, path)
            if not errs:
                return []
            attempts.append(errs)
        return [f"{path}: matched none of {len(schema['anyOf'])} anyOf branches: {attempts!r}"]

    if "oneOf" in schema:
        attempts = [validate(instance, sub, path) for sub in schema["oneOf"]]
        passing = [e for e in attempts if not e]
        if len(passing) != 1:
            return [f"{path}: expected exactly one oneOf match, got {len(passing)}: {attempts!r}"]
        return []

    errors = []
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(instance, t) for t in types):
            return [f"{path}: expected type {schema['type']!r}, "
                    f"got {type(instance).__name__} ({instance!r})"]

    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in instance:
                errors.extend(validate(instance[key], sub, f"{path}.{key}"))
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required property {req!r}")
        if schema.get("additionalProperties") is False:
            extra = sorted(set(instance) - set(props))
            if extra:
                errors.append(f"{path}: additional properties not allowed: {extra}")

    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            errors.extend(validate(item, schema["items"], f"{path}[{i}]"))

    return errors


def _load_schema():
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _load_vocab_effect_kinds():
    with open(VOCAB_PATH, encoding="utf-8") as fh:
        return json.load(fh)["effect_kinds"]


def _doc_kind_table():
    """Parse docs/surface-format-v2.md section 3's table into
    {kind: (boundary, meaning)}. A hand-maintained doc table is exactly the
    hazard scripts/check_derived_claims.py names -- a sentence that claims
    something about generated state with nothing holding the two together
    -- so this reads the doc's own text rather than trusting it."""
    text = open(DOC_PATH, encoding="utf-8").read()
    start = text.index("## 3. The effect-kind vocabulary")
    end = text.index("### 3.1", start)
    rows = {}
    row_re = re.compile(r"^\|\s*`([a-z]+)`\s*\|\s*`([a-z]+)`\s*\|\s*(.+?)\s*\|\s*$")
    for line in text[start:end].splitlines():
        m = row_re.match(line)
        if m:
            kind, boundary, meaning = m.groups()
            rows[kind] = (boundary, meaning)
    return rows


# ================================================================ running the hosts

def _python_json(path, rules=False):
    args = [sys.executable, "shapes_cli.py", path, "--json"]
    if rules:
        args.append("--rules")
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    return json.loads(r.stdout)


def _js_json(path, rules=False):
    args = [NODE, "js/cli.mjs", "shapes", path]
    if rules:
        args.append("--rules")
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, (path, rules, r.stdout, r.stderr)
    return json.loads(r.stdout)


def _swift_json(path, rules=False):
    args = ["shapes", path]
    if rules:
        args.append("--rules")
    r = subprocess.run(swift_host.command(*args), cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, (path, rules, r.stdout, r.stderr)
    return json.loads(r.stdout)


def _relglob(pattern):
    return sorted(os.path.relpath(p, REPO) for p in glob.glob(os.path.join(REPO, pattern)))


CORPUS = _relglob("corpus/*.planes")

# A smaller spread that actually carries `rule` statements, run both with and
# without --rules, on all three hosts, with a cross-host equality check --
# the schema alone cannot catch two hosts silently agreeing on the wrong
# thing.
RULE_FILES = [
    "annotated.planes",
    "demo/rules/clean.planes",
    "demo/rules/violation.planes",
    "demo/rules/exception.planes",
    "demo/mcp/v1.planes",
    "demo/mcp/v2.planes",
    "corpus/allowed-hosts.planes",
    "corpus/audit-log.planes",
]


# ================================================================ 1. output validates

def test_python_json_validates_across_the_corpus():
    assert len(CORPUS) >= 40, CORPUS  # the 51-program corpus, not a stray handful
    schema = _load_schema()
    failures = []
    for path in CORPUS:
        doc = _python_json(path)
        errs = validate(doc, schema)
        if errs:
            failures.append((path, errs))
    assert not failures, failures


def test_js_json_validates_across_the_corpus():
    if NODE is None:
        return
    schema = _load_schema()
    failures = []
    for path in CORPUS:
        doc = _js_json(path)
        errs = validate(doc, schema)
        if errs:
            failures.append((path, errs))
    assert not failures, failures


def test_swift_json_validates_across_the_corpus():
    if SWIFT is None:
        return
    schema = _load_schema()
    failures = []
    for path in CORPUS:
        doc = _swift_json(path)
        errs = validate(doc, schema)
        if errs:
            failures.append((path, errs))
    assert not failures, failures


def test_rules_field_validates_and_agrees_across_hosts():
    schema = _load_schema()
    failures = []
    for path in RULE_FILES:
        for rules in (False, True):
            py = _python_json(path, rules=rules)
            errs = validate(py, schema)
            if errs:
                failures.append((path, rules, "python", errs))
            assert ("rules" in py) == rules, (path, rules, sorted(py))

            if NODE is not None:
                js = _js_json(path, rules=rules)
                errs = validate(js, schema)
                if errs:
                    failures.append((path, rules, "js", errs))
                if js != py:
                    failures.append((path, rules, "js != python"))

            if SWIFT is not None:
                sw = _swift_json(path, rules=rules)
                errs = validate(sw, schema)
                if errs:
                    failures.append((path, rules, "swift", errs))
                if sw != py:
                    failures.append((path, rules, "swift != python"))
    assert not failures, failures


# ================================================================ 2. schema vs vocabulary.json

def test_schema_surface_kind_enum_matches_vocabulary_plus_unknown():
    """kinds / effects[].kind / runs_on_load[].kind / effects_undeclared[].kind
    all admit the eight vocabulary kinds plus the `"unknown"` sentinel
    (docs/surface-format-v2.md section 3.1) -- never a ninth real kind."""
    vocab_kinds = sorted(e["kind"] for e in _load_vocab_effect_kinds())
    expected = sorted(vocab_kinds + ["unknown"])
    schema = _load_schema()
    props = schema["properties"]
    checked = [
        props["kinds"]["items"]["enum"],
        props["effects"]["items"]["properties"]["kind"]["enum"],
        props["runs_on_load"]["items"]["properties"]["kind"]["enum"],
        props["effects_undeclared"]["items"]["properties"]["kind"]["enum"],
    ]
    for enum in checked:
        assert sorted(enum) == expected, (sorted(enum), expected)


def test_schema_rule_kind_enum_is_vocabulary_only():
    """A rule's own kind, and the kind of the effect it matched, are always
    one of the eight vocabulary kinds -- the parser rejects any other word
    in a rule's kind position, so `"unknown"` can never appear there."""
    vocab_kinds = sorted(e["kind"] for e in _load_vocab_effect_kinds())
    schema = _load_schema()
    violation = schema["properties"]["rules"]["properties"]["violations"]["items"]
    assert sorted(violation["properties"]["kind"]["enum"]) == vocab_kinds
    effect_obj = violation["properties"]["effect"]["anyOf"][0]
    assert sorted(effect_obj["properties"]["kind"]["enum"]) == vocab_kinds


def test_schema_boundary_enum_matches_vocabulary_plus_foreign():
    """boundaries / effects[].boundary / runs_on_load[].boundary admit the
    four vocabulary boundaries plus `"foreign"` (paired only with
    `"unknown"`); a rule's matched effect never carries `"foreign"`."""
    vocab_boundaries = sorted({e["boundary"] for e in _load_vocab_effect_kinds()})
    expected = sorted(vocab_boundaries + ["foreign"])
    schema = _load_schema()
    props = schema["properties"]
    assert sorted(props["boundaries"]["items"]["enum"]) == expected
    assert sorted(props["effects"]["items"]["properties"]["boundary"]["enum"]) == expected
    assert sorted(props["runs_on_load"]["items"]["properties"]["boundary"]["enum"]) == expected
    violation = props["rules"]["properties"]["violations"]["items"]
    effect_obj = violation["properties"]["effect"]["anyOf"][0]
    assert sorted(effect_obj["properties"]["boundary"]["enum"]) == vocab_boundaries


# ================================================================ 3. doc table vs vocabulary.json

def test_doc_kind_table_matches_vocabulary_json():
    vocab = {e["kind"]: (e["boundary"], e["note"]) for e in _load_vocab_effect_kinds()}
    doc_rows = _doc_kind_table()
    assert doc_rows, "could not find any rows in the doc's kind table -- parser or doc drifted"
    assert set(doc_rows) == set(vocab), (sorted(doc_rows), sorted(vocab))
    mismatches = []
    for kind, (boundary, meaning) in doc_rows.items():
        v_boundary, v_note = vocab[kind]
        if boundary != v_boundary:
            mismatches.append((kind, "boundary", boundary, v_boundary))
        # An empty vocabulary.json note (read/write/show) leaves the doc free
        # to supply its own plain-English meaning; a non-empty note is the
        # generated fact, and the doc must say exactly that.
        if v_note and meaning != v_note:
            mismatches.append((kind, "meaning", meaning, v_note))
    assert not mismatches, mismatches


if __name__ == "__main__":
    fails = []
    tests = [(k, f) for k, f in sorted(globals().items()) if k.startswith("test_")]
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
    if NODE is None:
        print("  (node not on PATH -- JS checks skipped)")
    if SWIFT is None:
        print("  (swift not on PATH -- Swift checks skipped)")
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
