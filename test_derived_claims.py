"""test_derived_claims.py -- the audit must find its own seeds (§5).

scripts/check_derived_claims.py closes a class: a hand-written claim about
machine-derived state, with nothing binding the two together. Four instances
of the class were found by reading this repository, not by any check -- and
"found by reading" is exactly the failure mode an automated sweep exists to
retire. An audit that cannot mechanically rediscover the instances a human
already found is four point fixes wearing a hat (§1's own words for the risk).

This file reconstructs each of the four known instances AS IT STOOD ON `main`
AT 976c3ab -- this build's own base commit -- via `git show`, not by hand-
retyping an approximation that could itself drift from the real historical
defect. Each seed is dropped into the real repository tree at a location the
corresponding check already walks (never a special-cased test path), the
check is run for real, and removed in a `finally` -- the same fixture
discipline test_gate.py's own PROBE_SUITE/PROBE_MJS already established for
this repository's suites.

Four seeds, eight assertions (§5): each instance is detected as it stood at
976c3ab, and its correction (the CURRENT, fixed file) passes clean. Plus the
narrower assertions §N+3.2 lists by letter: C (Check A's overlap threshold),
D (Check C's docstring states its own limits), E (the sweep is a hard gate
step), and F (a deliberate break of C/D/E's own assertions, confirming each
one discriminates rather than passing unconditionally).
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

import test_gate  # noqa: E402
from scripts import check_derived_claims as cdc  # noqa: E402

BASE_SHA = "976c3ab"


def _original(rel_path):
    """Byte-for-byte content of `rel_path` as it stood on `main` at
    BASE_SHA -- this build's own base commit, permanently reachable in this
    repository's history -- via `git show`."""
    r = subprocess.run(["git", "show", f"{BASE_SHA}:{rel_path}"], cwd=REPO,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"git show {BASE_SHA}:{rel_path} failed: {r.stderr}"
    return r.stdout


def _current(rel_path):
    with open(os.path.join(REPO, rel_path), encoding="utf-8") as fh:
        return fh.read()


def _drop_fixture(rel_path, content):
    path = os.path.join(REPO, rel_path)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def _remove_fixture(rel_path):
    path = os.path.join(REPO, rel_path)
    if os.path.exists(path):
        os.remove(path)


# ================================================================ instance 1
#
# .github/workflows/pages.yml's `on: push: paths:` filter, omitting
# grammar/*.planes and grammar/core.json. Not one of Checks A/B/C (it is a
# workflow trigger, not a vocabulary table, a protocol claim, or a gate
# comment) -- test_gate.py::test_the_deploy_workflow_has_no_paths_filter
# holds the line, built on workflow_has_paths_filter(), extracted so this
# file can call the SAME logic against a reconstructed fixture rather than a
# second hand-copy of the substring check.


def test_instance_1_seed_paths_filter_is_detected():
    original = _original(".github/workflows/pages.yml")
    assert test_gate.workflow_has_paths_filter(original), (
        "the pre-fix pages.yml at 976c3ab has no `paths:` filter -- either "
        "the fixture is wrong or workflow_has_paths_filter() is")


def test_instance_1_correction_passes():
    current = _current(".github/workflows/pages.yml")
    assert not test_gate.workflow_has_paths_filter(current), (
        "the CURRENT pages.yml still has a `paths:` filter -- instance 1 is "
        "not actually fixed")


# ================================================================ instance 2
#
# core_check.py's own main() comment: "A REPORT, never a gate ... does not
# change the exit code" over the graph block, while sys.exit counted it.
# Check C's job. The fixture is the WHOLE original core_check.py, dropped at
# a path scripts/*.py's own glob already walks -- not a hand-trimmed excerpt,
# so the line numbers Check C reports (296, 394) are the real historical
# ones and this test is also a check that nothing about core_check.py's own
# shape has silently drifted since.

INSTANCE_2_FIXTURE = "scripts/_gate_probe_core_check.py"


def test_instance_2_seed_never_a_gate_comment_is_detected():
    try:
        _drop_fixture(INSTANCE_2_FIXTURE, _original("core_check.py"))
        findings, examined = cdc.check_c()
        hits = [f for f in findings if f["file"] == INSTANCE_2_FIXTURE]
        assert hits, f"Check C did not flag {INSTANCE_2_FIXTURE}: {examined}"
        assert hits[0]["line"] == 296, hits[0]
        assert "graph" in hits[0]["summary"], hits[0]
    finally:
        _remove_fixture(INSTANCE_2_FIXTURE)


def test_instance_2_correction_passes():
    try:
        _drop_fixture(INSTANCE_2_FIXTURE, _current("core_check.py"))
        findings, _examined = cdc.check_c()
        hits = [f for f in findings if f["file"] == INSTANCE_2_FIXTURE]
        assert not hits, hits
    finally:
        _remove_fixture(INSTANCE_2_FIXTURE)


# ================================================================ instance 3
#
# paint.html's footer named `draw protocol 1`/`draw protocol 2` while the
# page's own module graph implements version 3. Check B's job. The fixture
# has to sit at the REPO ROOT -- check_b() enumerates `os.listdir(REPO)` for
# `*.html` exactly as the deploy's own page list does, and the fixture's
# relative imports (`./js/browser_main.mjs`, ...) only resolve correctly
# from that location.

INSTANCE_3_FIXTURE = "_gate_probe_paint.html"


def test_instance_3_seed_footer_version_is_detected():
    try:
        _drop_fixture(INSTANCE_3_FIXTURE, _original("paint.html"))
        findings, examined = cdc.check_b()
        hits = [f for f in findings if f["file"] == INSTANCE_3_FIXTURE]
        assert hits, f"Check B did not flag {INSTANCE_3_FIXTURE}: {examined}"
        assert "3" in hits[0]["summary"], hits[0]
        assert "[1, 2]" in hits[0]["summary"], hits[0]
    finally:
        _remove_fixture(INSTANCE_3_FIXTURE)


def test_instance_3_correction_passes():
    try:
        _drop_fixture(INSTANCE_3_FIXTURE, _current("paint.html"))
        findings, _examined = cdc.check_b()
        hits = [f for f in findings if f["file"] == INSTANCE_3_FIXTURE]
        assert not hits, hits
    finally:
        _remove_fixture(INSTANCE_3_FIXTURE)


# ================================================================ instance 4
#
# js/browser_main.mjs's PROBE_ARGUMENT: eleven of thirteen builtin names,
# missing `number` and `root`. Check A's job. The fixture sits under js/ so
# Check A's repo-wide walk picks it up with no special-casing.

INSTANCE_4_FIXTURE = "js/_gate_probe_browser_main.mjs"


def test_instance_4_seed_probe_argument_is_detected():
    try:
        _drop_fixture(INSTANCE_4_FIXTURE, _original("js/browser_main.mjs"))
        findings, examined = cdc.check_a()
        hits = [f for f in findings
                if f["file"] == INSTANCE_4_FIXTURE and "PROBE_ARGUMENT" in f["site"]]
        assert hits, f"Check A did not flag {INSTANCE_4_FIXTURE}: {examined}"
        assert "number" in hits[0]["summary"] and "root" in hits[0]["summary"], hits[0]
    finally:
        _remove_fixture(INSTANCE_4_FIXTURE)


def test_instance_4_correction_passes():
    try:
        _drop_fixture(INSTANCE_4_FIXTURE, _current("js/browser_main.mjs"))
        findings, _examined = cdc.check_a()
        hits = [f for f in findings if f["file"] == INSTANCE_4_FIXTURE]
        assert not hits, hits
    finally:
        _remove_fixture(INSTANCE_4_FIXTURE)


# ============================================== C: Check A's overlap threshold
#
# The design this build was given (§4.1): three or more overlapping keys is
# a table about the vocabulary; two is not. Exercised directly rather than
# trusted, since the number 3 appears nowhere else to check it against.

THRESHOLD_FIXTURE = "js/_gate_probe_threshold.mjs"


def test_check_a_threshold_two_keys_is_not_a_table_three_is():
    try:
        _drop_fixture(THRESHOLD_FIXTURE, "const TWO = { count: 1, lower: 2 };\n")
        findings, _ = cdc.check_a()
        assert not any(f["file"] == THRESHOLD_FIXTURE for f in findings), (
            "a 2-key overlap was treated as a vocabulary table")

        _drop_fixture(THRESHOLD_FIXTURE,
                      "const THREE = { count: 1, lower: 2, upper: 3 };\n")
        findings, _ = cdc.check_a()
        assert any(f["file"] == THRESHOLD_FIXTURE for f in findings), (
            "a 3-key overlap was NOT treated as a vocabulary table")
    finally:
        _remove_fixture(THRESHOLD_FIXTURE)


# ========================================== D: Check C's docstring states limits


def _docstring_states_limits(doc):
    """Pure, so it can be tested both on the real docstring and on a
    deliberately broken one (F)."""
    if not doc or not doc.strip():
        return False
    return "converse" in doc.lower()


def test_check_c_docstring_states_its_limits_and_the_converse():
    assert _docstring_states_limits(cdc.check_c.__doc__), (
        "check_c()'s docstring is empty or does not name the converse case "
        "it does not reach (§4.3)")


def test_check_c_docstring_check_rejects_an_empty_or_silent_docstring():
    """F, for D: confirm _docstring_states_limits() actually discriminates --
    an assertion that would pass on anything is not an assertion."""
    assert not _docstring_states_limits(None)
    assert not _docstring_states_limits("   ")
    assert not _docstring_states_limits("this check reads every comment in the repo")


# ================================================== E: the sweep is a hard step


def _ci_sh_text():
    with open(os.path.join(REPO, "scripts", "ci.sh"), encoding="utf-8") as fh:
        return fh.read()


def _is_hard_step(ci_text, script_name):
    lines = ci_text.splitlines()
    hard = [ln for ln in lines
            if script_name in ln and ln.strip().startswith("timed ")]
    soft = [ln for ln in lines
            if script_name in ln and ln.strip().startswith("timed_soft ")]
    return bool(hard) and not soft


def test_check_derived_claims_is_a_hard_step_in_ci_sh():
    assert _is_hard_step(_ci_sh_text(), "check_derived_claims.py"), (
        "scripts/check_derived_claims.py is not run as a `timed` (hard) "
        "step in scripts/ci.sh (invariant 5)")


def test_the_hard_step_check_rejects_a_soft_step():
    """F, for E: a crafted ci.sh using timed_soft for this step must be
    reported as NOT hard -- proving the assertion above discriminates."""
    soft_text = "timed_soft check_derived_claims python3 scripts/check_derived_claims.py\n"
    assert not _is_hard_step(soft_text, "check_derived_claims.py")
    hard_text = "timed check_derived_claims python3 scripts/check_derived_claims.py\n"
    assert _is_hard_step(hard_text, "check_derived_claims.py")


# ================================================================ E: coverage
#
# The gate wiring itself, run for real rather than only read as text --
# mirrors test_gate.py's own test_every_js_test_file_that_exists_is_one_the_gate_runs.


def test_check_derived_claims_runs_clean_on_the_real_repository():
    """The other tests in this file plant and remove fixtures; this one
    confirms that after every `finally` has run, the repository check_a() /
    check_b() / check_c() actually see is clean -- the four known instances
    are fixed, and nothing else new needs a decision (§4.4)."""
    findings_a, _ = cdc.check_a()
    findings_b, _ = cdc.check_b()
    findings_c, _ = cdc.check_c()
    assert not findings_a, findings_a
    assert not findings_b, findings_b
    assert not findings_c, findings_c


if __name__ == "__main__":
    import types
    fails = []
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and isinstance(f, types.FunctionType)]
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
