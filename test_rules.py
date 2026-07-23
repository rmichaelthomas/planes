"""Rule plane — effect-only slice.

Tests inception checkpoint §8's claim for the half it can be tested against:
an effect-reaching rule is checked with the same machinery Shapes already
computes, never executed, and never changes what the program does.
"""
import json
import sys

from lexer import Rule, EFFECT_KINDS
from parser import parse, scan_names, PlanesSyntaxError
from shapes import analyse
from rules import check, narrows, RuleNotSupported, RuleConflict
from interp import Interpreter


def rule_violations(src):
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    return check(found, surface)


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


def test_named_subject_raises_rather_than_passing_silently():
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
        assert "not yet supported" in str(e)


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
    error."""
    src = ('use http\n'
           'rule [no-net] anything may not ask\n'
           'rule [no-telemetry] anything may not ask '
           'to "https://telemetry.example.com"\n'
           'x = ask "https://telemetry.example.com"\n')
    v = rule_violations(src)
    # Both rules are equally violated by the same effect; that is not a
    # conflict, since [no-telemetry] narrows [no-net].
    assert len(v) == 2
    assert {viol.rule.name for viol in v} == {"no-net", "no-telemetry"}


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
