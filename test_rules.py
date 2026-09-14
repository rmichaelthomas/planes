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
from shapes import Effect, analyse


def rule_violations(src):
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    return check(found, surface)


def lit(target):
    """A literal (non-computed) `ask` effect naming `target` — enough of
    an `Effect` for `_target_matches`/`narrows`, which read only `.kind`
    (unused here), `.target` and `.computed`."""
    return Effect("ask", "network", target, computed=False)


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


def test_a_computed_target_with_an_incompatible_known_prefix_is_a_certain_non_match():
    """v37.0 §513: a computed target is not an unknown one. Its known chunks
    are facts, and a host they rule out is not a possible match."""
    src = ('use http\n'
           'rule [no-telemetry] anything may not ask '
           'to "https://telemetry.example.com/collect"\n'
           'to lookup of name:\n'
           '  give ask "https://registry.example.com/v1/packages/" + name\n\n'
           'x = for each n in ["a"]: lookup of n\n')
    assert rule_violations(src) == []


def test_a_computed_target_that_could_still_be_the_rule_target_stays_possible():
    src = ('use http\n'
           'rule [no-requests] anything may not ask '
           'to "https://registry.example.com/v1/packages/requests"\n'
           'to lookup of name:\n'
           '  give ask "https://registry.example.com/v1/packages/" + name\n\n'
           'x = for each n in ["a"]: lookup of n\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].uncertain is True


def test_pattern_exclusion_anchors_both_ends_and_orders_the_middle():
    """The pre-B2 exact-match anchoring algorithm, unchanged: still what
    governs a rule target that isn't URL-shaped (B2 leaves those on
    exact matching)."""
    from rules import _pattern_excludes
    assert _pattern_excludes("https://a/x", "{...}") is False
    assert _pattern_excludes("aXbYc", "a{...}b{...}c") is False
    assert _pattern_excludes("acb", "a{...}b{...}c") is True
    # a hole may be empty, and a chunk may not overlap its neighbour
    assert _pattern_excludes("ab", "a{...}b") is False
    assert _pattern_excludes("a", "a{...}a") is True


def test_pattern_exclusion_still_anchors_the_scheme_for_a_url_rule_target():
    """A URL-shaped rule target's scheme is known before any hole, so a
    mismatch there is still provable under B2's host/path covering."""
    from rules import _pattern_excludes
    assert _pattern_excludes("https://a/x.json", "http://{...}") is True


def test_b2_covering_makes_a_pre_b2_exclusion_uncertain():
    """B2 (Sprint B) re-proves #104's guard for covering, not equality —
    strictly weaker. Pre-B2, a rule target was matched by exact string
    equality, so a pattern whose trailing chunk couldn't be the literal
    target's own suffix was excluded. Under B2, `_url_pattern_excludes`
    only reasons from the certain text before the first hole (B2's
    documented, sound simplification); it does not see the trailing
    ".xml" chunk at all, so it correctly stays uncertain here — and
    rightly so: `n = "x.json/report"` produces
    "https://a/x.json/report.xml", whose path "/x.json/report.xml" IS
    covered by rule path "/x.json" (the "/" boundary right after it).
    v37.0 pinned the opposite answer for this exact pair when rule
    targets matched by equality alone; B2 supersedes it.
    """
    from rules import _pattern_excludes
    assert _pattern_excludes("https://a/x.json", "https://{...}.xml") is False


def test_a_foreign_with_no_stated_destination_is_never_excluded():
    """Its target names the host function, not where the request goes, so
    the text differing from the rule's target proves nothing."""
    from rules import _pattern_excludes
    assert _pattern_excludes("https://t.example.com", "m.post (destination not stated)") is False
    assert _pattern_excludes("https://t.example.com", "m.{...} (destination not stated)") is False
    src = ('rule [no-telemetry] anything may not ask to "https://t.example.com"\n'
           'foreign post of x from "m.post" doing ask\n'
           'r = post of 1\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].uncertain is True


def test_a_forbid_rule_fires_on_its_real_target_beside_an_excluded_one():
    src = ('use http\n'
           'rule [no-telemetry] anything may not ask '
           'to "https://telemetry.example.com/collect"\n'
           'to lookup of name:\n'
           '  give ask "https://registry.example.com/v1/packages/" + name\n\n'
           'x = for each n in ["a"]: lookup of n\n'
           'y = ask "https://telemetry.example.com/collect"\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].uncertain is False
    assert v[0].effect.target == "https://telemetry.example.com/collect"


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


# ================================================================ B2: URL covers matching

def test_b2_rule_path_covers_itself_and_beneath_it_but_not_a_longer_word():
    """`/ingest` covers `/ingest` and `/ingest/v2`, but not `/ingestion`."""
    from rules import _target_matches
    rule = Rule("r", "anything", "ask", "https://x/ingest", 1)

    assert _target_matches(rule, lit("https://x/ingest")) == (True, False)
    assert _target_matches(rule, lit("https://x/ingest/v2")) == (True, False)
    assert _target_matches(rule, lit("https://x/ingestion")) == (False, False)


def test_b2_empty_or_slash_path_covers_every_path_on_the_host():
    from rules import _target_matches

    for rule_target in ("https://x", "https://x/"):
        rule = Rule("r", "anything", "ask", rule_target, 1)
        assert _target_matches(rule, lit("https://x"))[0] is True
        assert _target_matches(rule, lit("https://x/"))[0] is True
        assert _target_matches(rule, lit("https://x/anything/at/all"))[0] is True


def test_b2_trailing_slash_covers_beneath_but_not_the_bare_path():
    """`/ingest/` covers `/ingest/` and everything under it, but not the
    bare `/ingest` (which lacks the trailing slash)."""
    from rules import _target_matches
    rule = Rule("r", "anything", "ask", "https://x/ingest/", 1)

    assert _target_matches(rule, lit("https://x/ingest/"))[0] is True
    assert _target_matches(rule, lit("https://x/ingest/v2"))[0] is True
    assert _target_matches(rule, lit("https://x/ingest"))[0] is False


def test_b2_a_different_host_or_a_subdomain_is_never_covered():
    from rules import _target_matches

    tracker = Rule("r", "anything", "ask", "https://tracker.example", 1)
    assert _target_matches(tracker, lit("https://tracker.example.evil.com"))[0] is False

    host_rule = Rule("r2", "anything", "ask", "https://x.com", 1)
    assert _target_matches(host_rule, lit("https://api.x.com"))[0] is False


def test_b2_scheme_and_host_are_case_insensitive_but_path_is_not():
    from rules import _target_matches

    rule = Rule("r", "anything", "ask", "https://X.example/Ingest", 1)
    assert _target_matches(rule, lit("HTTPS://x.EXAMPLE/Ingest"))[0] is True
    assert _target_matches(rule, lit("https://x.example/ingest"))[0] is False


def test_b2_case_insensitivity_is_ascii_only_not_full_unicode():
    """DNS case-insensitivity is ASCII-only, so scheme/host comparison
    folds only A-Z to a-z (`_ascii_lower`), never a full Unicode
    `.lower()`. A capital-Sigma host compares exactly against BOTH
    plausible Unicode lowerings of it -- a final-sigma reading (some
    case-folding rules turn a word-final capital Sigma into U+03C2) and a
    plain-sigma reading (others give U+03C3) -- because non-ASCII
    characters are left exactly as written, not covered by either. A
    full Unicode lower would (in general, and does on at least one
    engine/version pairing) pick one of the two readings, matching one
    host and not the other, and there is no guarantee two hosts' Unicode
    tables would even agree on which -- exactly the byte-for-byte
    agreement this avoids depending on. js/rules.mjs's and Rules.swift's
    identically-named `asciiLower` must give the same answers.
    """
    from rules import _ascii_lower, _target_matches

    # ASCII is folded...
    assert _ascii_lower("AbC-123") == "abc-123"
    # ...and non-ASCII passes through untouched, whatever its case.
    assert _ascii_lower("ΑΣ") == "ΑΣ"

    rule = Rule("r", "anything", "ask", "https://ΑΣ.example", 1)
    final_sigma = lit("https://ας.example")   # a lower(), final sigma
    plain_sigma = lit("https://ασ.example")   # a lower(), plain sigma
    assert _target_matches(rule, final_sigma)[0] is False
    assert _target_matches(rule, plain_sigma)[0] is False
    # The exact same (unfolded) host still matches.
    assert _target_matches(rule, lit("https://ΑΣ.example"))[0] is True


def test_b2_no_default_port_folding():
    """`https://x` and `https://x:443` differ — port is part of the host
    and compared exactly as written, with no default-port normalisation."""
    from rules import _target_matches

    rule = Rule("r", "anything", "ask", "https://x", 1)
    assert _target_matches(rule, lit("https://x:443"))[0] is False
    assert _target_matches(rule, lit("https://x"))[0] is True


def test_b2_effect_query_and_fragment_are_ignored():
    from rules import _target_matches

    rule = Rule("r", "anything", "ask", "https://x/ingest", 1)
    assert _target_matches(rule, lit("https://x/ingest?pkg=requests"))[0] is True
    assert _target_matches(rule, lit("https://x/ingest#frag"))[0] is True
    assert _target_matches(rule, lit("https://x/ingest/v2?pkg=requests#f"))[0] is True


def test_b2_a_rule_target_with_a_query_or_fragment_is_refused():
    src = 'rule [bad] anything may not ask to "https://x/ingest?pkg=1"\n'
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    try:
        check(found, surface)
        assert False, "should raise"
    except RuleConflict as e:
        msg = str(e)
        assert "bad" in msg
        assert "query string or fragment" in msg
        assert "drop everything" in msg


def test_b2_a_rule_target_with_a_fragment_is_refused_identically():
    src = 'rule [bad] anything may not ask to "https://x/ingest#frag"\n'
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    try:
        check(found, surface)
        assert False, "should raise"
    except RuleConflict as e:
        assert "query string or fragment" in str(e)


def test_b2_a_non_url_target_keeps_exact_matching():
    """A rule target that isn't URL-shaped (a file path here) keeps
    exact-string matching, unchanged by B2."""
    from rules import _target_matches

    rule = Rule("r", "anything", "write", "refunds.json", 1)
    assert _target_matches(rule, lit("refunds.json"))[0] is True
    assert _target_matches(rule, lit("refunds.json.bak"))[0] is False


def test_b2_end_to_end_permit_narrows_a_broad_forbid_by_path():
    """Straight from the spec: a broad forbid on a bare host, narrowed by
    a permit scoped to one subtree under it — the subtree is permitted,
    everything else under the host stays forbidden."""
    from rules import fingerprint
    deny_src = 'rule [deny] anything may not ask to "https://x"\n'
    deny_rule = parse(deny_src)[0]
    fp = fingerprint(deny_rule)
    src = (f'use http\n{deny_src}'
          f'rule [ok] anything may ask to "https://x/public" '
          f'supersedes [deny] @{fp}\n'
          f'a = ask "https://x/public/a"\n'
          f'b = ask "https://x/private"\n')
    v = rule_violations(src)
    by_target = {viol.effect.target: viol for viol in v}
    assert by_target["https://x/public/a"].is_violation is False
    assert by_target["https://x/private"].is_violation is True


# ---- B2: computed-target exclusion re-proven for covering (not equality)

def test_b2_pattern_hole_right_after_the_rule_path_stays_uncertain():
    """`https://x/ingest{...}` vs rule `https://x/ingest`: not excluded,
    since the hole may produce "" (equal) or "/v2" (covered)."""
    from rules import _pattern_excludes
    assert _pattern_excludes("https://x/ingest", "https://x/ingest{...}") is False


def test_b2_pattern_with_a_longer_word_before_the_hole_is_excluded():
    """`https://x/ingestion/{...}` vs rule `https://x/ingest`: excluded —
    the known text already breaks the "/" boundary ("ingestion" continues
    past "ingest" with "i", not "/")."""
    from rules import _pattern_excludes
    assert _pattern_excludes("https://x/ingest", "https://x/ingestion/{...}") is True


def test_b2_pattern_with_an_unresolved_host_stays_uncertain():
    """`https://{...}/ingest` vs rule `https://x/ingest`: not excluded —
    the hole may still resolve the host to "x"."""
    from rules import _pattern_excludes
    assert _pattern_excludes("https://x/ingest", "https://{...}/ingest") is False


def test_b2_pattern_whose_known_host_prefix_cannot_match_is_excluded():
    """`https://api.{...}/` vs rule `https://x/`: excluded — whatever the
    hole produces, the host will start with "api.", which "x" can never
    equal."""
    from rules import _pattern_excludes
    assert _pattern_excludes("https://x/", "https://api.{...}/") is True


def test_b2_pattern_whose_known_path_is_a_short_prefix_stays_uncertain():
    """`https://x/{...}` vs rule `https://x/a`: not excluded — the hole
    may produce "a"."""
    from rules import _pattern_excludes
    assert _pattern_excludes("https://x/a", "https://x/{...}") is False


def test_b2_a_hole_less_computed_target_excludes_nothing():
    """#104's guard, restated: a computed target with no hole at all
    (nothing left to reason about) is never excluded."""
    from rules import _pattern_excludes
    assert _pattern_excludes("https://x/ingest", "https://x/other") is False


def test_b2_a_scheme_or_host_that_is_fully_literal_and_different_is_excluded():
    from rules import _pattern_excludes
    # scheme fully literal and different
    assert _pattern_excludes("https://x/a", "http://x/{...}") is True
    # host fully literal (terminated by "/") and different
    assert _pattern_excludes("https://x/a", "https://y/{...}") is True


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


def test_b2_a_url_path_narrows_a_broader_one_on_the_same_host():
    """`narrows` re-proven for host/path covering (B2): a target strictly
    inside another's covered set narrows it, even though neither target
    is `None`."""
    broad = Rule("broad", "anything", "ask", "https://x", 1)
    narrow = Rule("narrow", "anything", "ask", "https://x/public", 2)
    assert narrows(narrow, broad)
    assert not narrows(broad, narrow)


def test_b2_trailing_slash_path_narrows_the_bare_host_the_same_way():
    broad = Rule("broad", "anything", "ask", "https://x/", 1)
    narrow = Rule("narrow", "anything", "ask", "https://x/ingest", 2)
    assert narrows(narrow, broad)
    assert not narrows(broad, narrow)


def test_b2_disjoint_paths_on_the_same_host_do_not_narrow_either_way():
    """Two path prefixes that neither contain the other (B2's "laminar,
    never partial" covering) are simply unrelated, not a narrowing."""
    a = Rule("a", "anything", "ask", "https://x/alpha", 1)
    b = Rule("b", "anything", "ask", "https://x/beta", 2)
    assert not narrows(a, b)
    assert not narrows(b, a)


def test_b2_different_spellings_of_the_same_scope_do_not_narrow_either_way():
    """`"https://x"` and `"https://x/"` are two spellings of "every path
    on x" — the same scope, so neither narrows the other (B2's
    `_same_scope`, not `==`)."""
    a = Rule("a", "anything", "ask", "https://x", 1)
    b = Rule("b", "anything", "ask", "https://x/", 2)
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
    old_src = 'rule [old] anything may not ask to "https://a.example.com"'
    fp = fingerprint(parse(old_src)[0])
    src = (f'use http\n{old_src}\n'
          f'rule [new] anything may not ask to "https://b.example.com" '
          f'supersedes [old] @{fp}\n'
          f'x = ask "https://a.example.com"\n')
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
    a_src = 'rule [a] anything may not ask to "https://x.example.com"'
    fp = fingerprint(parse(a_src)[0])
    src = (f'use http\n{a_src}\n'
          f'rule [b] anything may not ask to "https://x.example.com" '
          f'supersedes [a] @{fp}\n'
          f'y = ask "https://x.example.com"\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].rule.name == "b"


def test_b2_two_spellings_of_the_same_scope_still_conflict():
    """`"https://x"` and `"https://x/"` mean the same covered set (every
    path on x) — B2's `_same_scope` in place of `==` still calls this
    equally specific, the same as if the strings were identical."""
    src = ('use http\n'
           'rule [a] anything may not ask to "https://x"\n'
           'rule [b] anything may not ask to "https://x/"\n'
           'y = ask "https://x"\n')
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    try:
        check(found, surface)
        assert False, "should raise"
    except RuleConflict as e:
        assert "[a]" in str(e) and "[b]" in str(e)


def test_b2_a_narrower_permit_under_a_forbid_is_a_narrowing_not_a_conflict():
    """A permit strictly inside a forbid's covered set clears that
    subtree without raising — narrowing, not a collision (B2)."""
    src = ('use http\n'
           'rule [deny] anything may not ask to "https://x"\n'
           'rule [ok] anything may ask to "https://x/public"\n'
           'a = ask "https://x/public/report"\n'
           'b = ask "https://x/private"\n')
    v = rule_violations(src)
    by_target = {viol.effect.target: viol for viol in v}
    assert by_target["https://x/public/report"].is_violation is False
    assert by_target["https://x/private"].is_violation is True


# ================================================================ exception resolution (§3)

def test_permit_that_supersedes_a_forbid_clears_it():
    deny_src = 'rule [no-external-sends] anything may not ask'
    fp = fingerprint(parse(deny_src)[0])
    src = (f'use http\n{deny_src}\n'
          f'rule [audit-allowed] anything may ask to '
          f'"https://audit.internal" supersedes [no-external-sends] @{fp}\n'
          f'x = ask "https://audit.internal"\n')
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
    a_src = 'rule [a] anything may not ask to "https://x.example.com"'
    fp = fingerprint(parse(a_src)[0])
    src = (f'use http\n{a_src}\n'
          f'rule [b] anything may ask to "https://x.example.com" '
          f'supersedes [a] @{fp}\n'
          f'y = ask "https://x.example.com"\n')
    v = rule_violations(src)
    assert len(v) == 1
    assert v[0].is_violation is False
    assert v[0].cleared_by.name == "b"


# ================================================================ reporting (§4)

def test_cleared_violation_renders_the_excepted_by_line():
    deny_src = 'rule [no-external-sends] anything may not ask'
    fp = fingerprint(parse(deny_src)[0])
    src = (f'use http\n{deny_src}\n'
          f'rule [audit-allowed] anything may ask to '
          f'"https://audit.internal" supersedes [no-external-sends] @{fp}\n'
          f'x = ask "https://audit.internal"\n')
    v = rule_violations(src)
    rendered = v[0].render()
    assert rendered.startswith("[no-external-sends] would have been "
                               "violated at line 4")
    assert "excepted by [audit-allowed] (line 3)" in rendered


def test_cleared_violations_do_not_count_toward_a_pass_fail_result():
    deny_src = 'rule [no-external-sends] anything may not ask'
    fp = fingerprint(parse(deny_src)[0])
    src = (f'use http\n{deny_src}\n'
          f'rule [audit-allowed] anything may ask to '
          f'"https://audit.internal" supersedes [no-external-sends] @{fp}\n'
          f'x = ask "https://audit.internal"\n')
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


def test_absent_fingerprint_is_refused():
    """B3 (Track 0 #3): a supersedes clause naming no fingerprint at all is
    refused, not treated as an unverified-but-legal override — the parser
    cannot know the other rule's fingerprint, so this is enforced here,
    where supersedes resolves, with the same error class the mismatch
    check below uses. The message names the fix: the exact fingerprint to
    add."""
    old_src = 'rule [old] anything may not ask to "https://x.example.com"'
    fp = fingerprint(parse(old_src)[0])
    src = (f'use http\n{old_src}\n'
          f'rule [new] anything may ask to "https://x.example.com" '
          f'supersedes [old]\n'
          f'y = ask "https://x.example.com"\n')
    e = expect_conflict(src)
    msg = str(e)
    assert "[new]" in msg and "[old]" in msg
    assert "supersedes [old] (line 2) without its fingerprint" in msg
    assert f"write supersedes [old] @{fp}" in msg


# ================================================================ contradicts (B3, Track 0 #5)

def test_contradicts_parses_and_carries_the_name():
    prog = parse('rule [a] anything may not ask contradicts [b]')
    assert prog[0].contradicts == "b"
    assert prog[0].supersedes is None


def test_contradicts_follows_supersedes_in_fixed_order():
    """supersedes first, then contradicts -- both on one rule."""
    fp = fingerprint(parse('rule [old] anything may not write')[0])
    prog = parse(f'rule [new] anything may ask supersedes [old] @{fp} '
                f'contradicts [other]')
    r = prog[0]
    assert r.supersedes == "old"
    assert r.supersedes_fingerprint == fp
    assert r.contradicts == "other"


def test_contradicts_before_supersedes_is_refused():
    """The reverse order is not accepted -- contradicts is read only after
    supersedes, so a contradicts clause first leaves supersedes as trailing
    text the grammar does not expect."""
    try:
        parse('rule [new] anything may ask contradicts [other] '
             'supersedes [old] @abcdef')
        assert False, "should raise"
    except PlanesSyntaxError:
        pass


def test_contradicts_missing_bracket_names_the_fix():
    try:
        parse('rule [a] anything may not ask contradicts b')
        assert False, "should raise"
    except PlanesSyntaxError as e:
        msg = str(e)
        assert "contradicts" in msg and "bracketed rule" in msg
        assert "contradicts [other-rule-name]" in msg


def test_contradicts_missing_name_names_the_fix():
    try:
        parse('rule [a] anything may not ask contradicts [')
        assert False, "should raise"
    except PlanesSyntaxError as e:
        msg = str(e)
        assert "contradicts" in msg and "bracketed rule" in msg


def test_contradicts_unknown_rule_is_a_compile_error():
    src = 'rule [a] anything may not ask contradicts [ghost]\n'
    e = expect_conflict(src)
    msg = str(e)
    assert "[a]" in msg and "[ghost]" in msg
    assert "which is not a rule in this file" in msg
    assert "remove the contradicts clause" in msg


def test_contradicts_itself_is_a_compile_error():
    src = 'rule [a] anything may not ask contradicts [a]\n'
    e = expect_conflict(src)
    msg = str(e)
    assert "contradicts itself" in msg
    assert "contradicts should name a different rule" in msg


def test_contradicts_declared_from_both_sides_is_a_compile_error():
    """Same pair, declared twice: A contradicts B and B contradicts A. The
    second one encountered is refused, naming the first."""
    src = ('rule [a] anything may not ask contradicts [b]\n'
           'rule [b] anything may not write contradicts [a]\n')
    e = expect_conflict(src)
    msg = str(e)
    assert "[b]" in msg and "[a]" in msg
    assert "already contradicts" in msg
    assert "only needs declaring once" in msg


def test_contradicts_has_no_fingerprint_field_to_go_stale():
    """Unlike supersedes, contradicts declares an incompatibility with the
    OTHER rule itself, not a claim about its current text -- so editing the
    named rule's condition never invalidates the declaration, and there is
    no fingerprint mismatch to raise."""
    src = ('rule [a] anything may not ask to "https://x.example.com"\n'
           'rule [b] anything may not write contradicts [a]\n')
    prog = parse(src)
    b = next(r for r in prog if r.name == "b")
    assert b.contradicts == "a"
    # Editing [a]'s target does not change [b]'s declaration at all --
    # there is nothing on the clause that could go stale.
    src2 = ('rule [a] anything may not ask to "https://changed.example.com"\n'
            'rule [b] anything may not write contradicts [a]\n')
    found = [s for s in parse(src2) if isinstance(s, Rule)]
    surface = analyse(src2)
    check(found, surface)  # does not raise


def test_a_pair_that_both_apply_is_reported_as_a_contradiction():
    """A rule *applies* when its condition matches at least one effect --
    a forbid rule violated, or a permit rule matched. When both rules of a
    declared pair apply, the checker reports the contradiction, naming the
    DECLARING rule's `because` (the rule that wrote the `contradicts`
    clause) -- never the named rule's, since the declaration belongs to
    whichever rule wrote it."""
    src = ('use http\nuse file\n'
           'rule [no-writes] anything may not write\n'
           'rule [no-sends] anything may not ask contradicts [no-writes]\n'
           '  because "writes are audited separately"\n'
           'write 1 to "out.txt"\n'
           'x = ask "https://x.example.com"\n')
    v = rule_violations(src)
    contradictions = [r for r in v if r.contradicts_rule is not None]
    assert len(contradictions) == 1
    c = contradictions[0]
    assert c.is_violation is True
    assert c.rule.name == "no-sends"
    assert c.contradicts_rule.name == "no-writes"
    assert c.effect.target == "https://x.example.com"
    assert c.contradicts_effect.target == "out.txt"
    rendered = c.render()
    assert rendered.startswith(
        "[no-sends] contradicts [no-writes]: both apply to this program")
    assert "[no-sends] at line 7 (ask https://x.example.com)" in rendered
    assert "[no-writes] at line 6 (write out.txt)" in rendered
    assert '[no-sends] because "writes are audited separately"' in rendered


def test_a_pair_where_one_is_vacuous_is_not_reported():
    """[no-writes] never matches -- the program performs no write -- so it
    does not apply, and the declared contradiction never fires even though
    [no-sends] does apply."""
    src = ('use http\n'
           'rule [no-writes] anything may not write\n'
           'rule [no-sends] anything may not ask contradicts [no-writes]\n'
           'x = ask "https://x.example.com"\n')
    v = rule_violations(src)
    assert not any(r.contradicts_rule is not None for r in v)
    assert len(v) == 1
    assert v[0].rule.name == "no-sends"
    assert v[0].is_violation is True


def test_a_contradiction_involving_a_permit_rule():
    """contradicts may be declared on, or point at, a permit rule -- a
    permit that clears one forbid can still be declared incompatible with
    a completely unrelated forbid rule."""
    deny_fp = fingerprint(parse('rule [no-sends] anything may not ask')[0])
    src = (f'use http\nuse file\n'
          f'rule [no-sends] anything may not ask\n'
          f'rule [audit-allowed] anything may ask to '
          f'"https://audit.internal" supersedes [no-sends] @{deny_fp}\n'
          f'rule [no-writes] anything may not write '
          f'contradicts [audit-allowed]\n'
          f'x = ask "https://audit.internal"\n'
          f'write 1 to "out.txt"\n')
    v = rule_violations(src)
    contradictions = [r for r in v if r.contradicts_rule is not None]
    assert len(contradictions) == 1
    c = contradictions[0]
    assert c.rule.name == "no-writes"
    assert c.contradicts_rule.name == "audit-allowed"
    assert c.contradicts_rule.assertion == "permit"
    assert c.is_violation is True
    # the permit's own match is still cleared -- contradicts changes no
    # rule's outcome, only adds a new reported fact
    cleared = next(r for r in v if r.rule.name == "no-sends")
    assert cleared.is_violation is False
    assert cleared.cleared_by.name == "audit-allowed"


def test_contradiction_as_json_names_both_rules_and_effects():
    src = ('use http\nuse file\n'
           'rule [no-writes] anything may not write\n'
           'rule [no-sends] anything may not ask contradicts [no-writes]\n'
           'write 1 to "out.txt"\n'
           'x = ask "https://x.example.com"\n')
    v = rule_violations(src)
    c = next(r for r in v if r.contradicts_rule is not None)
    doc = c.as_json()
    assert doc["is_violation"] is True
    assert doc["vacuous"] is False
    assert doc["cleared_by"] is None
    assert doc["message"] == c.render()
    assert doc["contradiction"] == {
        "rule": "no-sends",
        "effect": {"kind": "ask", "boundary": "network",
                   "target": "https://x.example.com", "line": 6},
        "with_rule": "no-writes",
        "with_effect": {"kind": "write", "boundary": "file",
                        "target": "out.txt", "line": 5},
    }


def test_non_contradiction_violation_as_json_has_a_null_contradiction():
    src = ('use http\nrule [no-net] anything may not ask\n'
           'x = ask "https://example.com/a.json"\n')
    v = rule_violations(src)[0]
    assert v.as_json()["contradiction"] is None


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
    possible match by `_target_matches` (v2.0 §34) unless its known chunks
    exclude the rule's target (v37.0 §513). Kept plain so the case this
    test isolates does not depend on that exclusion.
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


# ================================================================ H1: --json --rules

def test_violation_as_json_reports_every_structured_field():
    src = ('use http\n'
           'rule [no-net] anything may not ask\n'
           'x = ask "https://example.com/a.json"\n')
    v = rule_violations(src)[0]
    doc = v.as_json()
    assert doc["rule"] == "no-net"
    assert doc["rule_line"] == 2
    assert doc["assertion"] == "forbid"
    assert doc["kind"] == "ask"
    assert doc["target"] is None
    assert doc["condition"] == condition(v.rule)
    assert doc["because"] is None
    assert doc["is_violation"] is True
    assert doc["vacuous"] is False
    assert doc["vacuous_situation"] is None
    assert doc["uncertain"] is False
    assert doc["effect"] == {"kind": "ask", "boundary": "network",
                             "target": "https://example.com/a.json", "line": 3}
    assert doc["cleared_by"] is None
    assert doc["narrowed_by"] == []
    assert doc["origins"] == []
    assert doc["message"] == v.render()


def test_violation_as_json_reports_because():
    src = ('use http\n'
           'rule [no-net] anything may not ask\n'
           '  because "default deny"\n'
           'x = ask "https://example.com/a.json"\n')
    v = rule_violations(src)[0]
    assert v.as_json()["because"] == "default deny"


def test_violation_as_json_reports_a_permit_exception_as_cleared_by():
    deny_src = 'rule [no-external-sends] anything may not ask'
    fp = fingerprint(parse(deny_src)[0])
    src = (f'use http\n{deny_src}\n'
          f'rule [audit-allowed] anything may ask to "https://audit.internal" '
          f'supersedes [no-external-sends] @{fp}\n'
          f'x = ask "https://audit.internal"\n')
    v = rule_violations(src)[0]
    doc = v.as_json()
    assert doc["is_violation"] is False
    assert doc["vacuous"] is False
    assert doc["cleared_by"] == {"rule": "audit-allowed", "line": 3}
    assert doc["message"] == v.render()


def test_violation_as_json_reports_narrowed_by():
    src = ('use http\n'
           'rule [no-net] anything may not ask\n'
           'rule [no-telemetry] anything may not ask '
           'to "https://telemetry.example.com"\n'
           'x = ask "https://telemetry.example.com"\n')
    wide = next(v for v in rule_violations(src) if v.rule.name == "no-net")
    assert wide.as_json()["narrowed_by"] == [{"rule": "no-telemetry", "line": 3}]


def test_violation_as_json_reports_a_vacuous_situation():
    src = ('use file\n'
           'let secret = "value"\n'
           'show secret\n'
           'rule [no-secret-uploads] secret may not ask\n')
    v = rule_violations(src)[0]
    doc = v.as_json()
    assert doc["vacuous"] is True
    assert doc["vacuous_situation"] == 1
    assert doc["is_violation"] is False
    assert doc["effect"] is None
    assert doc["message"] == v.render()


def test_violation_as_json_dedupes_origins_like_render_does():
    src = ('use http\n'
           'to send of payload:\n'
           '  give ask "https://collector.example.com/?d=" + payload\n\n'
           'rule [no-leak] anything may not ask\n'
           'x = send of "secret"\n')
    v = rule_violations(src)[0]
    doc = v.as_json()
    rendered = v.render()
    if doc["origins"]:
        parts = sorted({f"{o['name']} ({o['file']})" if o["file"] else o["name"]
                       for o in doc["origins"]})
        assert f"derived from: {', '.join(parts)}" in rendered
    else:
        assert "derived from" not in rendered


def test_as_json_omits_the_rules_field_by_default():
    """Adding fields must never touch the ones that shipped before H1."""
    from shapes import analyse_file
    from shapes_cli import as_json

    doc = as_json(analyse_file("demo/rules/violation.planes"),
                  "demo/rules/violation.planes")
    assert "rules" not in doc


def test_as_json_with_rules_matches_shapes_cli_rules_json():
    from shapes import analyse_file
    from shapes_cli import as_json, rules_json

    path = "demo/rules/violation.planes"
    src = open(path, encoding="utf-8").read()
    found = [s for s in parse(src) if isinstance(s, Rule)]
    surface = analyse_file(path)
    import os as _os
    results = check(found, surface, declaring_file=_os.path.abspath(path))
    rdoc = rules_json(found, results)
    doc = as_json(surface, path, rules=rdoc)
    assert doc["rules"] == rdoc
    assert doc["rules"]["checked"] == 1
    assert len(doc["rules"]["violations"]) == 1
    assert doc["rules"]["violations"][0]["is_violation"] is True


def test_cli_json_rules_exit_code_matches_bare_rules():
    """The exit code the --json --rules branch returns must be identical to
    --rules alone (H1's requirement) — checked here across all three
    outcomes the demo/rules corpus already carries: clean, a real
    violation, and a permit exception."""
    import subprocess
    cases = [
        ("demo/rules/clean.planes", 0),
        ("demo/rules/violation.planes", 1),
        ("demo/rules/exception.planes", 0),
    ]
    for path, expected_exit in cases:
        text_only = subprocess.run(
            ["python3", "shapes_cli.py", path, "--rules"],
            capture_output=True, text=True)
        with_json = subprocess.run(
            ["python3", "shapes_cli.py", path, "--json", "--rules"],
            capture_output=True, text=True)
        assert text_only.returncode == expected_exit, path
        assert with_json.returncode == expected_exit, path
        doc = json.loads(with_json.stdout)
        assert "rules" in doc, path


def test_cli_json_rules_reports_checked_zero_with_no_rules_in_the_file():
    """A --json --rules consumer must not be handed the "no rules found"
    sentence in place of a document — an absent --json falls back to text,
    but --json always gets JSON, even with nothing to report."""
    import os
    import shutil
    import subprocess
    import tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "m.planes")
    open(p, "w").write('use file\nwrite [1] to "o.json"\n')
    try:
        result = subprocess.run(
            ["python3", "shapes_cli.py", p, "--json", "--rules"],
            capture_output=True, text=True)
        assert result.returncode == 0
        doc = json.loads(result.stdout)
        assert doc["rules"] == {"checked": 0, "resolved_subjects": [], "violations": []}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_fingerprints_ignores_json_exactly_as_before():
    """--fingerprints takes priority over --rules (pre-existing behaviour);
    H1 must not change that when --json is also present."""
    import subprocess
    result = subprocess.run(
        ["python3", "shapes_cli.py", "demo/rules/exception.planes",
         "--fingerprints", "--json"],
        capture_output=True, text=True)
    assert result.returncode == 0
    assert not result.stdout.strip().startswith("{")
    assert "@" in result.stdout


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
