"""The unearned-assertion guard (P-Q20/P-Q21/P-Q22/P-Q23).

An unearned assertion is output that claims work occurred where the claim
is not derived from the work (see REPORT_AUDIT.md §1 for the full class
definition). Three layers, because the class has two forms and a registry
alone catches only one:

- 4.1 A registry of every claim-bearing string that reaches `print()` in
  `planes.py`/`shapes_cli.py` — the *lexical* form. A new summary line
  that reads like a claim (matches a claim-verb) and is not registered
  here fails the build. Stating the dependency in the registry value is
  the point, not decoration.
- 4.2 Behavioral tests that exercise the *structural* form — a claim made
  by control flow, where no string is wrong but the path reaching the
  output didn't do the work the output implies. A registry cannot see
  control flow; these can.
- 4.3 Subprocess-level CLI coverage. Before this build, this repository had
  exactly two end-to-end CLI tests, both added by the previous build — the
  untested output layer is the finding this whole build responds to
  (REPORT_AUDIT.md §0).
"""
import ast
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile

import planes as planes_mod
from lexer import Rule
from parser import parse
from rules import RuleNotSupported, RuleResults, check
from shapes import analyse

# ================================================================ 4.1 registry

# Any word here appearing (case-insensitively) in a string reaching print()
# forces that string to be registered below. Biased hard toward
# over-matching per the build prompt: a false positive costs one registry
# line, a false negative ships the defect.
CLAIM_VERBS = ("no ", "nothing", "none", "checked", "resolved", "match",
               "clean", "pure", "complete", "unchanged", "incomplete")

# Every user-facing string (in planes.py or shapes_cli.py) that reaches
# print() and matches a claim-verb, with what the claim rests on. A new
# summary line that matches a claim-verb and isn't added here fails
# test_every_claim_verb_string_is_registered.
CLAIM_SITES = {
    "no such file: {}": (
        "earned — os.path.exists(path) was just checked False immediately "
        "above, in the same branch, in both planes.py and shapes_cli.py"),

    "  (nothing — this run performed no effects; run `shapes_cli.py "
    "<file>` for what the program can do on any run)": (
        "fixed (audit item 1, P-Q22): scoped to 'this run' — i.effects is "
        "the runtime log, the run's own record, not a property of the "
        "program — and names shapes_cli.py for the static question it "
        "cannot answer. Previously: '(none — this program touches "
        "nothing outside itself)', a static claim from a single run's "
        "log; false whenever an effect sits in a branch that run didn't "
        "take."),

    "no .planes files found": (
        "earned — `paths` is the glob result computed immediately above; "
        "empty means the glob found nothing, which is exactly the claim"),

    "nothing touches {} among the files searched{}": (
        "fixed (audit sweep finding, same class as items 1-3): a file "
        "that failed to parse was silently `continue`d out of the search "
        "with no signal, so 'nothing touches X' could be printed while an "
        "unparseable file's real answer was never checked. Now reports "
        "each skipped file to stderr (matching --index's handling of the "
        "identical failure) and the claim is qualified with a skip count "
        "when any file was skipped."),

    "no rules found in {}": (
        "fixed (audit item 3): reworded from 'no rules in <file>' — "
        "`found` comes from a second, independent parse of the file, "
        "separate from the one that produced `surface`. 'found in' scopes "
        "the claim to what this parse actually saw, rather than implying "
        "agreement with the other parse that was never checked."),

    "{} {} checked, no violations": (
        "'checked' is earned — `found` is the exact list passed into "
        "check_rules(), same object, same call, so the count is a "
        "statement about what was just checked, not a separate guess. "
        "The 'named subjects resolved' text built into this same "
        "`summary` variable when a named subject was involved (audit "
        "item 2, P-Q20) is now read back from "
        "RuleResults.resolved_subjects — populated inside check() only "
        "after _resolve_subject returns without raising — rather than "
        "re-derived here from `found` and assumed to agree with what "
        "check() actually did."),

    "  {} pure": (
        "earned — printed once per function in surface.functions "
        "exactly when that function's own effect list is empty, read "
        "directly off the computed surface"),

    "module declarations match the effect surface": (
        "earned — fires only when declared_but_unused() and "
        "used_but_undeclared(), both computed from the same `surface` "
        "in this same invocation, are both empty"),
}


def _resolve_string(node, assigns):
    """Best-effort literal text an AST node evaluates to.

    Handles string/f-string literals directly, and a bare Name reference
    to a variable this same function-scoped scan has already resolved —
    enough to follow `summary = f"..."; summary += f"..."; print(summary)`
    without a real data-flow analysis. A FormattedValue whose inner
    expression cannot be resolved becomes "{}", so the surrounding literal
    text stays searchable for claim-verbs even when a value is opaque.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            elif isinstance(v, ast.FormattedValue):
                inner = _resolve_string(v.value, assigns)
                parts.append(inner if inner is not None else "{}")
        return "".join(parts)
    if isinstance(node, ast.Name) and node.id in assigns:
        return assigns[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        l = _resolve_string(node.left, assigns)
        r = _resolve_string(node.right, assigns)
        if l is not None and r is not None:
            return l + r
    return None


def _scan_block(stmts, assigns, hits):
    """Walk a statement list in order, tracking simple string variables.

    Composite statements (if/for/while/try/with) recurse with a COPY of
    the current bindings, so a mutation inside a branch does not leak to
    statements after it — deliberately conservative (may under-resolve a
    variable mutated only inside a branch that precedes the print as a
    sibling, not an ancestor) rather than over-claim a binding that may
    not hold. Composite statements are not also re-scanned as a whole via
    ast.walk, to avoid double-counting the print() calls inside them.
    """
    for stmt in stmts:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)):
            val = _resolve_string(stmt.value, assigns)
            if val is not None:
                assigns[stmt.targets[0].id] = val
        elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
            val = _resolve_string(stmt.value, assigns)
            if val is not None and stmt.target.id in assigns:
                assigns[stmt.target.id] = assigns[stmt.target.id] + val

        if isinstance(stmt, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            for attr in ("body", "orelse", "finalbody"):
                sub = getattr(stmt, attr, None)
                if sub:
                    _scan_block(sub, dict(assigns), hits)
            continue

        for node in ast.walk(stmt):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "print" and node.args):
                text = _resolve_string(node.args[0], assigns)
                if text is not None:
                    hits.append(text)


def print_reaching_strings(path):
    """Every string print() is ever called with in this file, best-effort
    resolved through same-function variable assignment, per function."""
    tree = ast.parse(open(path).read(), filename=path)
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            _scan_block(node.body, {}, hits)
    return hits


def claim_bearing_strings(path):
    seen, out = set(), []
    for text in print_reaching_strings(path):
        if text in seen:
            continue
        seen.add(text)
        if any(v in text.lower() for v in CLAIM_VERBS):
            out.append(text)
    return out


def test_every_claim_verb_string_is_registered():
    unregistered = []
    found = set()
    for path in ("planes.py", "shapes_cli.py"):
        for text in claim_bearing_strings(path):
            found.add(text)
            if text not in CLAIM_SITES:
                unregistered.append((path, text))
    assert not unregistered, (
        f"unregistered claim-bearing strings (add each to CLAIM_SITES "
        f"with what it rests on): {unregistered}")
    # Every registered site found is genuinely a claim in this scanner's
    # design (it only resolves text that actually reaches a print() call,
    # via literal concatenation or same-function variable tracking) — zero
    # false positives, reported rather than assumed. A whole-file literal
    # scan tried first caught JSON schema keys ("pure", "complete") and
    # both module docstrings as spurious claim-verb matches; restricting
    # to print-reaching text (with simple variable resolution, needed to
    # not silently miss item 2's readback, which lives in a variable built
    # across two statements before the print) eliminated all of them.
    # "no such file: {}" is the one string both files share, so the set of
    # distinct texts found (not a per-file occurrence count) is what's
    # compared against the registry.
    assert found == set(CLAIM_SITES), (
        f"found {sorted(found)}, registered {sorted(CLAIM_SITES)} — a "
        f"stale registry entry needs to be reconciled")


def test_registry_catches_a_reintroduced_item_1_regression():
    """A false negative here ships the defect back. Prove the registry
    would actually catch item 1 if it reappeared, by asserting the
    claim-verb match fires on the exact old (unearned) wording."""
    old_wording = "(none — this program touches nothing outside itself)"
    assert any(v in old_wording.lower() for v in CLAIM_VERBS)
    assert old_wording not in CLAIM_SITES


# ================================================================ 4.2 behavioral

def _write(src):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "m.planes")
    open(p, "w").write(src)
    return d, p


def _run_planes_main(args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = planes_mod.main(["planes.py"] + args)
    return code, out.getvalue()


def test_untaken_branch_effect_makes_no_claim_the_program_touches_nothing():
    """The structural regression test for item 1/P-Q22: an effect sits in
    a branch this run does not take. --effects must not print any
    variant of 'this program touches nothing' — the claim item 1 removed
    must not come back under different wording either, so this asserts
    on absence of the CLAIM (a program-level 'touches nothing'
    statement), not on exact text."""
    src = ('use http\n'
           'x = 1\n'
           'if x > 100:\n'
           '  y = ask "https://example.com/a.json"\n'
           'show "small"\n')
    d, p = _write(src)
    try:
        code, text = _run_planes_main([p, "--effects"])
        assert code == 0
        assert "touches nothing" not in text
        assert "program touches" not in text
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_resolved_subjects_tracks_resolution_not_input():
    """check().resolved_subjects reflects what _resolve_subject actually
    passed, not a guess re-derived from the rule list handed in."""
    anything_src = 'use http\nrule [no-net] anything may not ask\nshow "hi"\n'
    prog = parse(anything_src)
    found = [s for s in prog if isinstance(s, Rule)]
    results = check(found, analyse(anything_src))
    assert results.resolved_subjects == [], \
        "'anything' must never appear in resolved_subjects"

    named_src = ('use http\n'
                'to send of payload:\n'
                '  give ask "https://collector.example.com/?d=" + payload\n\n'
                'rule [no-leak] payload may not ask\n'
                'x = send of "secret"\n')
    prog2 = parse(named_src)
    found2 = [s for s in prog2 if isinstance(s, Rule)]
    results2 = check(found2, analyse(named_src))
    assert results2.resolved_subjects == ["payload"]

    failing_src = ('use http\n'
                  'rule [x] nonexistent-name may not ask\n'
                  'y = ask "https://example.com/a.json"\n')
    prog3 = parse(failing_src)
    found3 = [s for s in prog3 if isinstance(s, Rule)]
    try:
        check(found3, analyse(failing_src))
        assert False, "an unresolvable subject must raise, not appear"
    except RuleNotSupported:
        pass


def test_rule_results_satisfies_the_list_contract():
    r = RuleResults([1, 2, 3], resolved_subjects=["a", "b"])
    assert list(r) == [1, 2, 3]
    assert len(r) == 3
    assert r[0] == 1 and r[-1] == 3
    assert any(x == 2 for x in r)
    assert r.resolved_subjects == ["a", "b"]

    empty = RuleResults()
    assert not empty
    assert len(empty) == 0
    assert empty.resolved_subjects == []
    assert list(empty) == []


def test_exit_code_0_from_rules_is_never_silent():
    """The structural guard proper: a 0 exit from --rules must be
    accompanied by output naming what was checked. A silent 0 is exactly
    how P-Q19 hid before it was fixed."""
    src = 'use file\nrule [no-net] anything may not ask\nshow "hi"\n'
    d, p = _write(src)
    try:
        result = subprocess.run(
            [sys.executable, "shapes_cli.py", p, "--rules"],
            capture_output=True, text=True)
        assert result.returncode == 0
        assert result.stdout.strip() != ""
        assert "checked" in result.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ================================================================ 4.3 CLI coverage

def run_cli(script, *args):
    result = subprocess.run([sys.executable, script] + list(args),
                            capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def test_cli_rules_clean():
    src = 'use file\nrule [no-net] anything may not ask\nshow "hi"\n'
    d, p = _write(src)
    try:
        code, out, _ = run_cli("shapes_cli.py", p, "--rules")
        assert code == 0
        assert "checked" in out and "no violations" in out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_rules_violation():
    src = ('use http\n'
           'rule [no-net] anything may not ask\n'
           'x = ask "https://a.example.com"\n')
    d, p = _write(src)
    try:
        code, out, _ = run_cli("shapes_cli.py", p, "--rules")
        assert code == 1
        assert "violated" in out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_rules_vacuous():
    src = ('use http\n'
           'use file\n\n'
           'let endpoint = "https://api.example.com/data"\n'
           'let readings = read of "sensor.txt"\n\n'
           'show readings\n'
           'ask endpoint\n\n'
           'rule [no-reading-uploads] readings may not ask\n')
    d, p = _write(src)
    try:
        code, out, _ = run_cli("shapes_cli.py", p, "--rules")
        assert code == 2
        assert "checked nothing" in out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_rules_no_rules_found():
    src = 'x = 5\n'
    d, p = _write(src)
    try:
        code, out, _ = run_cli("shapes_cli.py", p, "--rules")
        assert code == 0
        assert "no rules found in" in out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_effects_empty():
    src = 'x = 5\ny = x + 1\n'
    d, p = _write(src)
    try:
        code, out = _run_planes_main([p, "--effects"])
        assert code == 0
        assert "nothing" in out
        assert "shapes_cli.py" in out
        assert "touches nothing" not in out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_effects_nonempty():
    """A file effect, not network — planes.py's default host performs a
    real ask/write, and this test must not depend on network access."""
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "m.planes")
        open(p, "w").write('use file\nwrite [1] to "out.json"\n')
        cwd = os.getcwd()
        os.chdir(d)
        try:
            code, out = _run_planes_main([p, "--effects"])
        finally:
            os.chdir(cwd)
        assert code == 0
        assert "write" in out
        assert "out.json" in out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_check_match():
    src = 'use http\nx = ask "https://example.com/a.json"\n'
    d, p = _write(src)
    try:
        code, out, _ = run_cli("shapes_cli.py", p, "--check")
        assert code == 0
        assert "match" in out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_check_mismatch():
    src = 'x = ask "https://example.com/a.json"\n'
    d, p = _write(src)
    try:
        code, out, _ = run_cli("shapes_cli.py", p, "--check")
        assert code == 1
        assert "without `use" in out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_diff_no_change():
    src = 'use file\nwrite [1] to "out.json"\n'
    d, p = _write(src)
    try:
        code, out, _ = run_cli("shapes_cli.py", "--diff", p, p)
        assert code == 0
        assert "no change" in out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_diff_significant_change():
    d = tempfile.mkdtemp()
    try:
        p1 = os.path.join(d, "before.planes")
        p2 = os.path.join(d, "after.planes")
        open(p1, "w").write('to helper of n:\n  give n + 1\n')
        open(p2, "w").write(
            'use http\nto helper of n:\n  give ask "https://x.example.com"\n')
        code, out, _ = run_cli("shapes_cli.py", "--diff", p1, p2)
        assert code == 1
        assert "NEW BOUNDARIES" in out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_derivation_stats_with_derivations():
    code, out, _ = run_cli("shapes_cli.py", "hn.planes", "--derivation-stats")
    assert code == 0
    assert "derivation stats" in out
    assert "effects with a derivation: 0" not in out


def test_cli_derivation_stats_without_derivations():
    src = 'x = 5\n'
    d, p = _write(src)
    try:
        code, out, _ = run_cli("shapes_cli.py", p, "--derivation-stats")
        assert code == 0
        assert "effects with a derivation: 0" in out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_bare_invocation_shapes():
    code, out, _ = run_cli("shapes_cli.py")
    assert code == 2
    assert "shapes_cli.py" in out


def test_cli_bare_invocation_planes():
    code, out, _ = run_cli("planes.py")
    assert code == 2
    assert "planes.py" in out


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
