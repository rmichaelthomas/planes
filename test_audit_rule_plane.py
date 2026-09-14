"""H2 — the audit tool learns rule-plane relations; B3 flips two to BUILT.

`audit_locked_vs_built.py` used to check LANGUAGE constructs only: a keyword,
an AST node, an interpreter branch. It had no evidence category that could
see a RULE-PLANE relation (`supersedes`, `permit`, `contradicts`, a mandatory
fingerprint) at all — which is exactly why `until` and `contradicts` went
unflagged as locked-but-unchecked from checkpoint v5.0 to this sprint. This
file exercises the "RULE-PLANE RELATIONS" section directly against the
audit's own helpers and, end to end, against its printed output and exit
code.

The three things this pins:
  1. `supersedes` and `permit` really are BUILT — real pointers into
     parser.py/js/parser.mjs/swift/.../Parser.swift AND
     rules.py/js/rules.mjs/swift/.../Rules.swift, not a hard-coded True.
  2. B3 built `contradicts` and the mandatory-fingerprint requirement, so
     the audit now reports both BUILT, with real evidence, on the "normal"
     (CI-gating) allowance rather than the scheduled-B3 one H2 recorded —
     and `until` is WITHDRAWN, not a locked construct. A bare prose mention
     of a relation's name is never mistaken for the relation being handled:
     `contradicts` reads BUILT only because real parser/checker support
     exists, not because a comment names it.
  3. The audit's own evidence functions distinguish "the clause parses and
     resolves" from "a contradiction is actually reported": the dedicated
     `contradicts_reported` check looks for the Violation-shape field
     (`contradicts_rule`/`contradictsRule`) that only exists once the
     both-apply reporting path is built, not merely once the clause is
     validated at parse/resolve time.
"""
import os
import subprocess
import sys

import audit_locked_vs_built as audit

REPO = os.path.dirname(os.path.abspath(__file__))


def _run_cli():
    r = subprocess.run([sys.executable, "audit_locked_vs_built.py"],
                        cwd=REPO, capture_output=True, text=True)
    return r.stdout, r.returncode


# ============================================================ supersedes / permit are BUILT

def test_supersedes_has_real_three_way_parse_evidence():
    py, js, sw = audit.evaluate_rule_relation("rule_parse", "supersedes")
    assert py and py.startswith("parser.py:")
    assert js and js.startswith("js/parser.mjs:")
    assert sw and sw.startswith("swift/Sources/Planes/Parser.swift:")


def test_supersedes_has_real_three_way_checker_evidence():
    py, js, sw = audit.evaluate_rule_relation("rule_identifier", "supersedes")
    assert py and py.startswith("rules.py:")
    assert js and js.startswith("js/rules.mjs:")
    assert sw and sw.startswith("swift/Sources/Planes/Rules.swift:")


def test_permit_has_real_three_way_parse_evidence():
    py, js, sw = audit.evaluate_rule_relation("permit_parse", None)
    assert py and py.startswith("parser.py:")
    assert js and js.startswith("js/parser.mjs:")
    assert sw and sw.startswith("swift/Sources/Planes/Parser.swift:")


def test_permit_has_real_three_way_checker_evidence():
    py, js, sw = audit.evaluate_rule_relation("rule_identifier", "permit")
    assert py and py.startswith("rules.py:")
    assert js and js.startswith("js/rules.mjs:")
    assert sw and sw.startswith("swift/Sources/Planes/Rules.swift:")


def test_supersedes_and_permit_are_normal_not_scheduled():
    by_name = {c: ci for c, _, ci, _ in audit.RULE_RELATION_CHECKS}
    assert by_name["supersedes"] == "normal"
    assert by_name["permit"] == "normal"


# ============================================================ contradicts / fingerprint: now BUILT

def test_contradicts_has_real_three_way_parse_evidence():
    py, js, sw = audit.evaluate_rule_relation("rule_parse", "contradicts")
    assert py and py.startswith("parser.py:")
    assert js and js.startswith("js/parser.mjs:")
    assert sw and sw.startswith("swift/Sources/Planes/Parser.swift:")


def test_contradicts_has_real_three_way_checker_evidence():
    py, js, sw = audit.evaluate_rule_relation("rule_identifier", "contradicts")
    assert py and py.startswith("rules.py:")
    assert js and js.startswith("js/rules.mjs:")
    assert sw and sw.startswith("swift/Sources/Planes/Rules.swift:")


def test_contradicts_has_real_three_way_reported_evidence():
    """The stronger check (B3): a contradiction is actually a reported
    Violation shape, not merely a validated clause."""
    py, js, sw = audit.evaluate_rule_relation("contradicts_reported", None)
    assert py and py.startswith("rules.py:")
    assert js and js.startswith("js/rules.mjs:")
    assert sw and sw.startswith("swift/Sources/Planes/Rules.swift:")


def test_contradicts_is_normal_not_scheduled():
    entry = next(e for e in audit.RULE_RELATION_CHECKS if e[0] == "contradicts")
    _, _, ci_status, _ = entry
    assert ci_status == "normal"


def test_mandatory_fingerprint_has_real_three_way_evidence():
    py, js, sw = audit.evaluate_rule_relation("mandatory_fingerprint", None)
    assert py and py.startswith("rules.py:")
    assert js and js.startswith("js/rules.mjs:")
    assert sw and sw.startswith("swift/Sources/Planes/Rules.swift:")


def test_mandatory_fingerprint_is_normal_not_scheduled():
    entry = next(e for e in audit.RULE_RELATION_CHECKS
                 if e[0] == "supersedes: mandatory fingerprint")
    assert entry[2] == "normal"


def test_contradicts_reported_is_absent_before_the_field_exists():
    """The regression this stronger check exists to catch: resolution
    validation alone (a rule referencing `r.contradicts` to check for an
    unknown name or self-reference) must not read as BUILT -- only the
    Violation-shape field the both-apply reporting path adds does."""
    resolution_only = (
        "def _resolve_active(rules):\n"
        "    for r in rules:\n"
        "        if r.contradicts == r.name:\n"
        "            raise RuleConflict('contradicts itself')\n")
    assert audit.check_contradicts_reported_py(resolution_only) is None


def test_contradicts_reported_is_present_once_the_field_exists():
    real = (
        "results.append(Violation(r, effect, contradicts_rule=other,\n"
        "                         contradicts_effect=other_effect))\n")
    assert audit.check_contradicts_reported_py(real) is not None


# ============================================================ until: withdrawn, not locked

def test_until_is_not_a_locked_construct():
    names = [c for c, _, _, _ in audit.RULE_RELATION_CHECKS]
    assert "until" not in names


def test_until_is_listed_as_withdrawn_with_its_citation():
    withdrawn = dict(audit.WITHDRAWN_RELATIONS)
    assert "until" in withdrawn
    citation = withdrawn["until"]
    assert "withdrawn" in citation.lower()
    assert "2026-09-13" in citation
    assert "§76" in citation


# ============================================================ a name in prose is not evidence

def test_a_docstring_mention_is_not_checker_evidence():
    """The regression H2 exists to prevent: `contradicts` merely being
    named in commentary must not read as the relation being handled."""
    py_prose = '"""This module will eventually support contradicts.\n"""\n'
    assert audit.check_rule_identifier("contradicts", py_prose) is None
    js_prose = "// TODO: support contradicts someday\n"
    assert audit.check_rule_identifier("contradicts", js_prose) is None


def test_a_docstring_mention_is_not_parse_evidence():
    prose = '"""a rule may eventually contradicts another"""\n'
    assert audit.check_rule_parse("contradicts", prose) is None


def test_real_code_shape_is_checker_evidence():
    """The converse of the two tests above: once `contradicts` names a real
    identifier in code, the same helper finds it -- proving BUILT can only
    follow real B3 support, not a documentation edit."""
    py_code = "def _check_contradicts(active):\n    return active\n"
    assert audit.check_rule_identifier("contradicts", py_code) is not None


def test_real_parse_shape_is_parse_evidence():
    real = 'if self.at("NAME", "contradicts"):\n    pass\n'
    assert audit.check_rule_parse("contradicts", real) is not None


# ============================================================ end to end

def test_cli_exits_zero_with_every_relation_built_and_until_withdrawn():
    """B3 built both relations H2 had scheduled: nothing is left on the
    scheduled allowance, and the audit still passes clean."""
    out, code = _run_cli()
    assert code == 0, out
    assert "[BUILT    ] supersedes" in out
    assert "[BUILT    ] permit" in out
    assert "[BUILT    ] contradicts" in out
    assert "[BUILT    ] supersedes: mandatory fingerprint" in out
    assert "[WITHDRAWN] until" in out


def test_cli_reports_no_scheduled_gaps_left():
    """With both former scheduled-B3 relations now built, the "DECIDED, NOT
    YET BUILT" section has nothing to name -- the audit's own "every
    relation has real evidence" message prints instead."""
    out, code = _run_cli()
    assert code == 0, out
    assert "DECIDED, NOT YET BUILT" not in out
    assert "sprint item B3" not in out
    assert ("Every rule-plane relation that isn't scheduled or withdrawn has"
            in out)


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
