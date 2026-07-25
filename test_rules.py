"""Rule plane — effect-only slice.

Tests inception checkpoint §8's claim for the half it can be tested against:
an effect-reaching rule is checked with the same machinery the analyser already
computes, never executed, and never changes what the program does.
"""
import json
import sys

from interp import Interpreter
from lexer import EFFECT_KINDS, Rule
from parser import PlanesSyntaxError, parse, scan_names
from rules import RuleConflict, RuleNotSupported, check, condition, fingerprint, narrows
from shapes import analyse


def rule_violations(src):
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    return check(found, surface)


def expect_conflict(src):
    """Run check() expecting a RuleConflict; return it for message checks."""
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    try:
        check(found, surface)
        assert False, "should raise RuleConflict"
    except RuleConflict as e:
        return e


def interp_run(src, **kw):
    i = Interpreter(**kw)
    i.run(src)
    return i


# ================================================================ parsing

def test_rule_parses_with_all_fields():
    prog = parse('rule [readings-stay-local] readings may not ask')
    assert len(prog) == 1
    r = prog[0]
    assert isinstance(r, Rule)
    assert r.name == "readings-stay-local"
    assert r.subject == "readings"
    assert r.kind == "ask"
    assert r.target is None
    assert r.line == 1
    assert r.assertion == "forbid"
    assert r.supersedes_fingerprint is None


def test_rule_with_literal_target_parses():
    prog = parse('rule [no-telemetry] anything may not ask '
                 'to "https://telemetry.example.com"')
    r = prog[0]
    assert r.name == "no-telemetry"
    assert r.subject == "anything"
    assert r.kind == "ask"
    assert r.target == "https://telemetry.example.com"


def test_unknown_effect_kind_names_the_valid_kinds():
    try:
        parse('rule [x] anything may not teleport')
        assert False, "should raise"
    except PlanesSyntaxError as e:
        msg = str(e)
        assert "teleport" in msg
        for kind in EFFECT_KINDS:
            assert kind in msg, f"{kind!r} missing from the error"


def test_malformed_rule_missing_may_not_names_the_fix():
    try:
        parse('rule [x] anything might not ask')
        assert False, "should raise"
    except PlanesSyntaxError as e:
        assert "may not" in str(e)


def test_malformed_rule_missing_bracket_names_the_fix():
    try:
        parse('rule x anything may not ask')
        assert False, "should raise"
    except PlanesSyntaxError as e:
        msg = str(e)
        assert "bracketed name" in msg
        assert "rule [" in msg


# ---- permits (§2)

def test_permit_rule_parses_with_permit_assertion():
    prog = parse('rule [audit-allowed] anything may ask to "https://audit.internal"')
    r = prog[0]
    assert r.assertion == "permit"
    assert r.subject == "anything"
    assert r.kind == "ask"
    assert r.target == "https://audit.internal"


def test_forbid_rule_still_parses_with_forbid_assertion():
    prog = parse('rule [no-net] anything may not ask')
    assert prog[0].assertion == "forbid"


def test_may_error_names_both_forms():
    try:
        parse('rule [x] anything might ask')
        assert False, "should raise"
    except PlanesSyntaxError as e:
        msg = str(e)
        assert "may not" in msg
        assert "(forbid)" in msg
        assert "(permit)" in msg


def test_condition_renders_forbid_and_permit_correctly():
    forbid = Rule("f", "anything", "ask", "https://x.example.com", 1)
    permit = Rule("p", "anything", "ask", "https://x.example.com", 2,
                  assertion="permit")
    assert condition(forbid) == 'anything may not ask to "https://x.example.com"'
    assert condition(permit) == 'anything may ask to "https://x.example.com"'


def test_condition_re_escapes_a_target_containing_a_quote():
    """A rule's target holds already-resolved text (parser.py's
    `.value[1:-1]`, same as any other STRING-typed field), so a target
    containing a quote became expressible at fix/string-escapes-and-
    bootstrap -- condition() must re-escape it back into the message,
    the same fix render.py's Str case needed for the same reason."""
    forbid = Rule("f", "anything", "ask", 'a"b', 1)
    assert condition(forbid) == 'anything may not ask to "a\\"b"'


def test_rule_name_does_not_enter_known_funcs():
    names = scan_names('rule [readings-stay-local] readings may not ask')
    assert "readings-stay-local" not in names


def test_rule_name_does_not_shadow_a_function():
    """A rule and a function may share a name without interfering."""
    src = ('to alpha:\n'
           '  give 42\n\n'
           'rule [alpha] anything may not ask\n'
           'r = alpha')
    i = interp_run(src)
    assert i.env.get("r").value == 42


# ================================================================ matching

def test_violating_program_reports_one_violation_with_right_line():
    src = ('use http\n'
           'rule [no-net] anything may not ask\n'
           'x = ask "https://example.com/a.json"\n')
    violations = rule_violations(src)
    assert len(violations) == 1
    assert violations[0].rule.name == "no-net"
    assert violations[0].rule.line == 2
    assert violations[0].effect.site == 3
    assert "violated at line 3" in violations[0].render()
    assert "rule declared at line 2" in violations[0].render()


def test_clean_program_reports_no_violations():
    src = ('use file\n'
           'rule [no-net] anything may not ask\n'
           'write [1] to "o.json"\n')
    assert rule_violations(src) == []


def test_rule_for_a_kind_the_program_never_performs_reports_none():
    src = ('use file\n'
           'rule [no-clock] anything may not clock\n'
           'write [1] to "o.json"\n')
    assert rule_violations(src) == []


def test_rule_with_target_matches_only_that_target():
    other_target = ('use http\n'
                     'rule [no-telemetry] anything may not ask '
                     'to "https://telemetry.example.com"\n'
                     'x = ask "https://other.example.com/a.json"\n')
    assert rule_violations(other_target) == []

    same_target = ('use http\n'
                    'rule [no-telemetry] anything may not ask '
                    'to "https://telemetry.example.com"\n'
                    'x = ask "https://telemetry.example.com"\n')
    v = rule_violations(same_target)
    assert len(v) == 1
    assert v[0].uncertain is False


def test_computed_target_is_treated_as_a_possible_match():
    """Conservative at the boundary (v2.0 §34): widening is sound, assuming
    a computed target is safe is not."""
    src = ('use http\n'
           'rule [no-telemetry] anything may not ask '
           'to "https://telemetry.example.com"\n'
           'urls = ["https://a.example.com", "https://telemetry.example.com"]\n'
           'for each u in urls:\n'
           '  x = ask u\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].uncertain is True
    rendered = v[0].render()
    assert "could not be pinned down" in rendered


def test_uncertain_target_message_re_escapes_a_quote_in_the_rule_target():
    src = ('use http\n'
           'rule [no-telemetry] anything may not ask '
           'to "https://x.example.com/a\\"b"\n'
           'urls = ["https://a.example.com", "https://x.example.com/a\\"b"]\n'
           'for each u in urls:\n'
           '  x = ask u\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].uncertain is True
    rendered = v[0].render()
    assert 'may or may not be "https://x.example.com/a\\"b"' in rendered


def test_named_subject_raises_rather_than_passing_silently():
    """No variable named 'readings' exists anywhere in this program, so
    the subject cannot resolve to anything the derivation graph reaches.

    The message text changed from "not yet supported" (the old blanket
    refusal) to "does not resolve" once the checker gained the ability to
    trace derivation — the safety guarantee is the same: this program must
    not report clean against this rule.
    """
    src = ('use http\n'
           'rule [readings-stay-local] readings may not ask\n'
           'x = ask "https://example.com/a.json"\n')
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    try:
        check(found, surface)
        assert False, "should raise, not report clean"
    except RuleNotSupported as e:
        assert "readings" in str(e)
        assert "does not resolve" in str(e)


def test_named_subject_resolves_and_checks_in_the_same_file():
    """The subject names a function parameter whose value provably reaches
    the ask — resolved in this file, so the rule is checkable (P-Q16).

    `send`'s ask appears twice in `.declared`: once as the function's
    generic (computed) surface, once as the top-level call's specialised
    (exact) target — a pre-existing shapes.py dedup granularity, unrelated
    to named-subject resolution. Both must be real violations of the same
    rule; the exact count of that duplication is not this test's concern.
    """
    src = ('use http\n'
           'to send of payload:\n'
           '  give ask "https://collector.example.com/?d=" + payload\n\n'
           'rule [no-payload-leak] payload may not ask\n'
           'x = send of "secret"\n')
    v = rule_violations(src)
    assert len(v) >= 1
    assert all(viol.rule.name == "no-payload-leak" for viol in v)
    assert all(viol.is_violation for viol in v)


def test_named_subject_in_an_imported_file_is_not_supported():
    """The parameter 'payload' is bound in lib.planes, not in main.planes
    where the rule is written — a rule cannot reach across an import
    boundary to a name it never saw declared (P-Q18)."""
    import os

    from shapes import analyse_file as af

    d = "demo/_deriv_subject"
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "lib.planes"), "w").write(
        'use http\n'
        'to send of payload:\n'
        '  give ask "https://collector.example.com/?d=" + payload\n')
    open(os.path.join(d, "main.planes"), "w").write(
        'use lib\n'
        'rule [no-leak] payload may not ask\n'
        'x = send of "secret"\n')
    try:
        main_path = os.path.join(d, "main.planes")
        surface = af(main_path)
        prog = parse(open(main_path).read())
        found = [s for s in prog if isinstance(s, Rule)]
        try:
            check(found, surface, declaring_file=os.path.abspath(main_path))
            assert False, "should raise, not report clean"
        except RuleNotSupported as e:
            msg = str(e)
            assert "payload" in msg
            assert "lib.planes" in msg
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_named_subject_unresolvable_does_not_report_clean():
    src = ('use http\n'
           'rule [x] nonexistent-name may not ask\n'
           'y = ask "https://example.com/a.json"\n')
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    try:
        check(found, surface)
        assert False, "should raise, not report clean"
    except RuleNotSupported as e:
        assert "nonexistent-name" in str(e)


def test_rules_module_imports_only_hashlib_and_planes_text():
    """§8's duck-typing claim, asserted directly rather than only reviewed:
    rules.py reaches Surface only through its public queries, never into
    Analyser/Consts/Effect construction -- the docstring's actual claim,
    which importing `shapes` (or `interp`, or `parser`) would break.
    `planes_text` joined `hashlib` at feat/fail-primitive-and-parser-probe
    (Ruling 1): a leaf utility with no project dependencies of its own
    (test_planes_text.py asserts that separately), not a `shapes`
    coupling -- rules.py's four violation/conflict messages that quote a
    rule's `target` needed to re-escape it once fix/string-escapes-and-
    bootstrap made a target containing a quote expressible."""
    import ast
    tree = ast.parse(open("rules.py").read())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module)
    assert imports == {"hashlib", "planes_text"}


def test_violation_render_includes_derivation_line_when_traceable():
    src = ('use http\n'
           'to send of payload:\n'
           '  give ask "https://collector.example.com/?d=" + payload\n\n'
           'rule [no-leak] anything may not ask\n'
           'x = send of "secret"\n')
    v = rule_violations(src)
    rendered = v[0].render()
    assert "derived from:" in rendered
    assert "payload" in rendered


def test_violation_render_omits_derivation_line_when_not_traceable():
    src = ('use http\n'
           'rule [no-net] anything may not ask\n'
           'x = ask "https://example.com/a.json"\n')
    v = rule_violations(src)
    rendered = v[0].render()
    assert "derived from:" not in rendered


# ================================================================ narrows / supersedes / conflict

def test_rule_with_a_target_narrows_one_without():
    a = Rule("broad", "anything", "ask", None, 1)
    b = Rule("narrow", "anything", "ask", "https://x.example.com", 2)
    assert narrows(b, a)
    assert not narrows(a, b)


def test_same_target_does_not_narrow_either_way():
    a = Rule("one", "anything", "ask", "https://x.example.com", 1)
    b = Rule("two", "anything", "ask", "https://x.example.com", 2)
    assert not narrows(a, b)
    assert not narrows(b, a)


def test_different_kinds_do_not_narrow():
    a = Rule("net", "anything", "ask", None, 1)
    b = Rule("clk", "anything", "clock", None, 2)
    assert not narrows(a, b)
    assert not narrows(b, a)


def test_nested_rules_do_not_conflict():
    """The common nesting case v2.0 §30 exists to resolve: a broad rule and
    a more specific one over the same kind coexist without a compile
    error.

    Updated for §4 of the permit build: with permits in play, two
    independent-looking failures for one effect are ambiguous — a reader
    cannot tell whether one rule is the specific case of the other, or
    whether a permit cleared one of them. Both rules are still real
    violations (narrowing between two forbids clears nothing), but the
    broader one now names the narrower rule that also matched, so the
    relationship is visible rather than reported as two unrelated
    failures. Originally asserted only `len(v) == 2`; that assertion
    survives unchanged below, extended with the relationship check.
    """
    src = ('use http\n'
           'rule [no-net] anything may not ask\n'
           'rule [no-telemetry] anything may not ask '
           'to "https://telemetry.example.com"\n'
           'x = ask "https://telemetry.example.com"\n')
    v = rule_violations(src)
    assert len(v) == 2
    assert {viol.rule.name for viol in v} == {"no-net", "no-telemetry"}
    assert all(viol.is_violation for viol in v)

    broad = next(viol for viol in v if viol.rule.name == "no-net")
    narrow = next(viol for viol in v if viol.rule.name == "no-telemetry")
    assert [r.name for r in broad.narrowed_by] == ["no-telemetry"]
    assert narrow.narrowed_by == []
    assert "narrowed here by [no-telemetry]" in broad.render()


def test_supersedes_drops_the_superseded_rule():
    src = ('use http\n'
           'rule [old] anything may not ask to "https://a.example.com"\n'
           'rule [new] anything may not ask to "https://b.example.com" '
           'supersedes [old]\n'
           'x = ask "https://a.example.com"\n')
    # [old] is superseded, so its restriction on a.example.com no longer
    # applies; [new] restricts a different target and does not match.
    assert rule_violations(src) == []


def test_supersedes_parses_and_carries_the_name():
    prog = parse('rule [new] anything may not ask supersedes [old]')
    assert prog[0].supersedes == "old"


def test_supersedes_unknown_rule_is_a_compile_error():
    src = 'rule [new] anything may not ask supersedes [ghost]\n'
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    try:
        check(found, surface)
        assert False, "should raise"
    except RuleConflict as e:
        assert "ghost" in str(e)


def test_equal_specificity_conflict_is_a_compile_error():
    src = ('use http\n'
           'rule [a] anything may not ask to "https://x.example.com"\n'
           'rule [b] anything may not ask to "https://x.example.com"\n'
           'y = ask "https://x.example.com"\n')
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    try:
        check(found, surface)
        assert False, "should raise"
    except RuleConflict as e:
        msg = str(e)
        assert "[a]" in msg and "[b]" in msg


def test_conflict_message_re_escapes_a_quote_in_the_shared_target():
    src = ('use http\n'
           'rule [a] anything may not ask to "https://x.example.com/a\\"b"\n'
           'rule [b] anything may not ask to "https://x.example.com/a\\"b"\n'
           'y = ask "https://x.example.com/a\\"b"\n')
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    try:
        check(found, surface)
        assert False, "should raise"
    except RuleConflict as e:
        assert 'to "https://x.example.com/a\\"b"' in str(e)


def test_supersedes_resolves_what_would_otherwise_conflict():
    """Same rule set as the conflict test above, but [b] now supersedes
    [a] — the ambiguity is resolved, not just silenced."""
    src = ('use http\n'
           'rule [a] anything may not ask to "https://x.example.com"\n'
           'rule [b] anything may not ask to "https://x.example.com" '
           'supersedes [a]\n'
           'y = ask "https://x.example.com"\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].rule.name == "b"


# ================================================================ exception resolution (§3)

def test_permit_that_supersedes_a_forbid_clears_it():
    src = ('use http\n'
           'rule [no-external-sends] anything may not ask\n'
           'rule [audit-allowed] anything may ask to '
           '"https://audit.internal" supersedes [no-external-sends]\n'
           'x = ask "https://audit.internal"\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].is_violation is False
    assert v[0].cleared_by.name == "audit-allowed"


def test_permit_that_narrows_a_forbid_clears_it_without_supersedes():
    """narrows alone is sufficient (v2.0 §30) — no explicit supersedes
    needed when the permit is strictly more specific."""
    src = ('use http\n'
           'rule [no-external-sends] anything may not ask\n'
           'rule [audit-allowed] anything may ask to "https://audit.internal"\n'
           'x = ask "https://audit.internal"\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].is_violation is False
    assert v[0].cleared_by.name == "audit-allowed"


def test_broad_forbid_still_applies_where_the_permit_does_not_reach():
    """The forbid rule is not dropped — only the effect the permit covers
    is cleared; every other effect of that kind is still forbidden."""
    src = ('use http\n'
           'rule [no-external-sends] anything may not ask\n'
           'rule [audit-allowed] anything may ask to "https://audit.internal"\n'
           'x = ask "https://elsewhere.example.com"\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].is_violation is True
    assert v[0].cleared_by is None


def test_permit_matching_a_different_target_does_not_clear():
    src = ('use http\n'
           'rule [no-external-sends] anything may not ask\n'
           'rule [audit-allowed] anything may ask to "https://audit.internal"\n'
           'x = ask "https://audit.internal"\n'
           'y = ask "https://not-audit.example.com"\n')
    v = rule_violations(src)
    assert len(v) == 2
    by_target = {viol.effect.target: viol for viol in v}
    assert by_target["https://audit.internal"].is_violation is False
    assert by_target["https://not-audit.example.com"].is_violation is True


def test_unrelated_permit_raises_conflict():
    """A permit that excepts no forbid rule of its kind is an authoring
    error — it must not silently do nothing (§3, failure mode #2)."""
    src = ('use http\n'
           'rule [no-clock] anything may not clock\n'
           'rule [audit-allowed] anything may ask to "https://audit.internal"\n')
    e = expect_conflict(src)
    assert "audit-allowed" in str(e)
    assert "excepts no forbid rule" in str(e)


def test_a_global_permit_grants_nothing_without_a_matching_forbid():
    """A permit with no forbid of its kind at all is still unrelated, not
    a harmless no-op — §3's "grants nothing on its own"."""
    src = 'rule [x] anything may ask to "https://audit.internal"\n'
    e = expect_conflict(src)
    assert "x" in str(e)


# ================================================================ opposite-assertion conflict (§3)

def test_opposite_assertion_equal_specificity_is_a_conflict():
    src = ('use http\n'
           'rule [a] anything may not ask to "https://x.example.com"\n'
           'rule [b] anything may ask to "https://x.example.com"\n'
           'y = ask "https://x.example.com"\n')
    e = expect_conflict(src)
    msg = str(e)
    assert "[a]" in msg and "[b]" in msg
    assert "opposite things" in msg


def test_opposite_assertion_conflict_message_differs_from_same_assertion():
    same = expect_conflict(
        'rule [a] anything may not ask to "https://x.example.com"\n'
        'rule [b] anything may not ask to "https://x.example.com"\n')
    opposite = expect_conflict(
        'rule [a] anything may not ask to "https://x.example.com"\n'
        'rule [b] anything may ask to "https://x.example.com"\n')
    assert "opposite things" not in str(same)
    assert "equally specific" in str(same)
    assert "opposite things" in str(opposite)


def test_supersedes_resolves_an_opposite_assertion_conflict():
    src = ('use http\n'
           'rule [a] anything may not ask to "https://x.example.com"\n'
           'rule [b] anything may ask to "https://x.example.com" '
           'supersedes [a]\n'
           'y = ask "https://x.example.com"\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].is_violation is False
    assert v[0].cleared_by.name == "b"


# ================================================================ reporting (§4)

def test_cleared_violation_renders_the_excepted_by_line():
    src = ('use http\n'
           'rule [no-external-sends] anything may not ask\n'
           'rule [audit-allowed] anything may ask to '
           '"https://audit.internal" supersedes [no-external-sends]\n'
           'x = ask "https://audit.internal"\n')
    v = rule_violations(src)
    rendered = v[0].render()
    assert rendered.startswith("[no-external-sends] would have been "
                               "violated at line 4")
    assert "excepted by [audit-allowed] (line 3)" in rendered


def test_cleared_violations_do_not_count_toward_a_pass_fail_result():
    src = ('use http\n'
           'rule [no-external-sends] anything may not ask\n'
           'rule [audit-allowed] anything may ask to '
           '"https://audit.internal" supersedes [no-external-sends]\n'
           'x = ask "https://audit.internal"\n')
    v = rule_violations(src)
    assert len(v) == 1              # still returned, so it's visible
    assert not any(r.is_violation for r in v)   # but nothing failed


# ================================================================ fingerprints (§5)

def test_fingerprint_is_stable_across_runs():
    r = Rule("x", "anything", "ask", "https://a.example.com", 1)
    assert fingerprint(r) == fingerprint(r)
    r2 = Rule("x", "anything", "ask", "https://a.example.com", 99)
    assert fingerprint(r) == fingerprint(r2)


def test_fingerprint_ignores_name_and_line():
    a = Rule("alpha", "anything", "ask", "https://a.example.com", 1)
    b = Rule("beta", "anything", "ask", "https://a.example.com", 42)
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_changes_with_the_target():
    a = Rule("x", "anything", "ask", "https://a.example.com", 1)
    b = Rule("x", "anything", "ask", "https://b.example.com", 1)
    assert fingerprint(a) != fingerprint(b)


def test_fingerprint_changes_with_the_assertion():
    forbid = Rule("x", "anything", "ask", None, 1, assertion="forbid")
    permit = Rule("x", "anything", "ask", None, 1, assertion="permit")
    assert fingerprint(forbid) != fingerprint(permit)


def test_fingerprint_syntax_parses_and_is_stripped_of_the_at_sign():
    prog = parse('rule [new] anything may ask supersedes [old] @a3f9c2')
    assert prog[0].supersedes_fingerprint == "a3f9c2"


def test_matching_fingerprint_passes():
    old_src = 'rule [old] anything may not ask to "https://x.example.com"'
    old_rule = parse(old_src)[0]
    fp = fingerprint(old_rule)
    src = (f'use http\n{old_src}\n'
          f'rule [new] anything may ask to "https://x.example.com" '
          f'supersedes [old] @{fp}\n'
          f'y = ask "https://x.example.com"\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].cleared_by.name == "new"


def test_mismatched_fingerprint_raises_naming_both_rules():
    src = ('rule [old] anything may not ask to "https://y.example.com"\n'
           'rule [new] anything may ask to "https://x.example.com" '
           'supersedes [old] @000000\n')
    e = expect_conflict(src)
    msg = str(e)
    assert "[old]" in msg and "[new]" in msg
    assert "@000000" in msg


def test_absent_fingerprint_behaves_exactly_as_before():
    """No fingerprint on a supersedes clause is unverified, not invalid —
    today's behavior, and it must keep working unchanged."""
    src = ('use http\n'
           'rule [old] anything may not ask to "https://x.example.com"\n'
           'rule [new] anything may ask to "https://x.example.com" '
           'supersedes [old]\n'
           'y = ask "https://x.example.com"\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].cleared_by.name == "new"


# ================================================================ vacuous named subjects (P-Q19)

def test_vacuous_rule_situation_2_reports_checked_nothing():
    """§1's exact program: 'readings' resolves (it feeds a `show`), but no
    `ask` effect derives from it — the `ask` derives from 'endpoint'
    instead. The rule checked nothing and must not report clean."""
    src = ('use http\n'
           'use file\n\n'
           'let endpoint = "https://api.example.com/data"\n'
           'let readings = read of "sensor.txt"\n\n'
           'show readings\n'
           'ask endpoint\n\n'
           'rule [no-reading-uploads] readings may not ask\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].vacuous
    assert not v[0].is_violation
    rendered = v[0].render()
    assert "checked nothing" in rendered
    assert "readings" in rendered
    assert "'ask'" in rendered
    assert "violated" not in rendered


def test_vacuous_situation_1_no_effect_of_the_kind_at_all():
    """The rule's kind never occurs anywhere in the program."""
    src = ('use file\n'
           'let secret = "value"\n'
           'show secret\n'
           'rule [no-secret-uploads] secret may not ask\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].vacuous
    rendered = v[0].render()
    assert "checked nothing" in rendered
    assert "no 'ask' effect at all" in rendered


def test_vacuous_situation_3_subject_reaches_the_kind_but_not_the_target():
    """`payload` does derive an `ask`, but only to a target the rule's own
    `to "..."` clause excludes.

    Deliberately a plain top-level `let` + `ask`, not a function call: a
    parameterised call site produces both a generic (computed-target)
    function-level effect and a specialised (exact-target) top-level one
    in `.declared` (a pre-existing shapes.py dedup quirk, unrelated to
    this build) — and a computed target is conservatively treated as a
    possible match by `_target_matches` (v2.0 §34), which would make the
    rule match the generic effect and mask the situation-3 case this test
    wants to isolate.
    """
    src = ('use http\n'
           'let payload = "secret"\n'
           'let full = "https://collector.example.com/?d=" + payload\n'
           'rule [no-other-leak] payload may not ask '
           'to "https://different.example.com"\n'
           'x = ask full\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].vacuous
    rendered = v[0].render()
    assert "checked nothing" in rendered
    assert "excludes every one" in rendered
    assert "https://different.example.com" in rendered


def test_vacuous_situation_3_message_re_escapes_a_quote_in_the_target():
    src = ('use http\n'
           'let payload = "secret"\n'
           'let full = "https://collector.example.com/?d=" + payload\n'
           'rule [no-other-leak] payload may not ask '
           'to "https://x.example.com/a\\"b"\n'
           'x = ask full\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].vacuous
    rendered = v[0].render()
    assert 'never at "https://x.example.com/a\\"b"' in rendered


def test_anything_subject_is_never_vacuous():
    """The regression that matters most: a program with no matching effect
    under an `anything` rule is the ordinary, intended clean result — not
    vacuous, and its exit code must not change."""
    src = 'use file\nrule [no-net] anything may not ask\nshow "hi"\n'
    v = rule_violations(src)
    assert v == []


def test_matching_named_subject_rule_is_unaffected():
    """A named subject that DOES match is a real violation, not vacuous."""
    src = ('use http\n'
           'to send of payload:\n'
           '  give ask "https://collector.example.com/?d=" + payload\n\n'
           'rule [no-leak] payload may not ask\n'
           'x = send of "secret"\n')
    v = rule_violations(src)
    assert len(v) >= 1
    assert all(not viol.vacuous for viol in v)
    assert all(viol.is_violation for viol in v)


def test_vacuous_rule_alongside_a_real_violation_is_not_vacuous_overall():
    """A genuine violation from one rule must dominate a vacuous result
    from another — the CLI exit code must be 1, not 2, in this mix.

    The two forbid rules narrow rather than conflict (one has a target,
    one doesn't — v2.0 §30), so both can coexist without a RuleConflict."""
    src = ('use http\n'
           'use file\n\n'
           'let endpoint = "https://api.example.com/data"\n'
           'let readings = read of "sensor.txt"\n\n'
           'show readings\n'
           'ask endpoint\n\n'
           'rule [no-reading-uploads] readings may not ask\n'
           'rule [no-endpoint-uploads] anything may not ask '
           'to "https://api.example.com/data"\n')
    v = rule_violations(src)
    vacuous = [viol for viol in v if viol.vacuous]
    real = [viol for viol in v if viol.is_violation]
    assert len(vacuous) == 1
    assert len(real) == 1
    assert real[0].rule.name == "no-endpoint-uploads"


def test_vacuous_is_not_a_violation():
    src = ('use http\n'
           'use file\n\n'
           'let endpoint = "https://api.example.com/data"\n'
           'let readings = read of "sensor.txt"\n\n'
           'show readings\n'
           'ask endpoint\n\n'
           'rule [no-reading-uploads] readings may not ask\n')
    v = rule_violations(src)
    assert not any(viol.is_violation for viol in v)


def test_permits_are_never_reported_vacuous():
    """A named-subject permit that excepts no forbid rule of its kind is
    already RuleConflict via _check_permits_are_related — vacuous
    detection (forbids only) never gets a chance to run for it. 'endpoint'
    resolves here (it feeds the ask), so the conflict check, not subject
    resolution, is what actually fires."""
    src = ('use http\n'
           'let endpoint = "https://audit.internal"\n'
           'rule [no-clock] anything may not clock\n'
           'rule [audit-allowed] endpoint may ask to "https://audit.internal"\n'
           'x = ask endpoint\n')
    e = expect_conflict(src)
    assert "excepts no forbid rule" in str(e)


def test_cli_exit_code_2_for_a_vacuous_rule():
    import os
    import subprocess
    import tempfile
    src = ('use http\n'
           'use file\n\n'
           'let endpoint = "https://api.example.com/data"\n'
           'let readings = read of "sensor.txt"\n\n'
           'show readings\n'
           'ask endpoint\n\n'
           'rule [no-reading-uploads] readings may not ask\n')
    d = tempfile.mkdtemp()
    p = os.path.join(d, "m.planes")
    open(p, "w").write(src)
    try:
        result = subprocess.run(
            ["python3", "shapes_cli.py", p, "--rules"],
            capture_output=True, text=True)
        assert result.returncode == 2
        assert "checked nothing" in result.stdout
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_cli_exit_code_0_for_anything_with_no_match():
    import os
    import subprocess
    import tempfile
    src = 'use file\nrule [no-net] anything may not ask\nshow "hi"\n'
    d = tempfile.mkdtemp()
    p = os.path.join(d, "m.planes")
    open(p, "w").write(src)
    try:
        result = subprocess.run(
            ["python3", "shapes_cli.py", p, "--rules"],
            capture_output=True, text=True)
        assert result.returncode == 0
        assert "no violations" in result.stdout
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


# ================================================================ inertness

def test_rule_presence_does_not_change_output_or_effects():
    """§24's message rests on this: adding a rule leaves the program body
    unchanged. A rule is evaluated by the checker, never executed."""
    def stub(url):
        return json.dumps({"ok": 1})

    without_rule = ('use http\nuse file\n'
                     'x = ask "https://example.com/a.json"\n'
                     'show "hi"\n'
                     'write [1] to "o.json"\n')
    with_rule = ('rule [no-telemetry] anything may not ask '
                 'to "https://forbidden.example.com"\n' + without_rule)

    i1 = interp_run(without_rule, http=stub, fs={})
    i2 = interp_run(with_rule, http=stub, fs={})

    assert i1.output == i2.output
    assert i1.effects == i2.effects
    assert i1.fs == i2.fs


def test_permit_rule_presence_also_does_not_change_output_or_effects():
    """The same inertness claim, for a permit — v2.0 §33's refusal of
    `trigger` covers both assertions equally; neither is ever executed."""
    def stub(url):
        return json.dumps({"ok": 1})

    without_rule = ('use http\nuse file\n'
                     'x = ask "https://example.com/a.json"\n'
                     'show "hi"\n'
                     'write [1] to "o.json"\n')
    with_permits = ('rule [no-external-sends] anything may not ask\n'
                    'rule [audit-allowed] anything may ask '
                    'to "https://example.com/a.json"\n' + without_rule)

    i1 = interp_run(without_rule, http=stub, fs={})
    i2 = interp_run(with_permits, http=stub, fs={})

    assert i1.output == i2.output
    assert i1.effects == i2.effects
    assert i1.fs == i2.fs


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
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
