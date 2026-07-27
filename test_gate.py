"""The gate's own coverage — what it counts, what it refuses to run without,
and what it must not leave unrun.

Four builds in a row found the same failure: something that exists, passes, and
is never executed. `REPORT_HOST_BOUNDARY.md` §5 records the first; two Python
suites with no `__main__` runner were the second and third; the whole of
`js/test/` — 47 tests — was the fourth, found by accident at C4 while removing
a dead host method. C5 made a silent suite fail the gate rather than warn, and
made the JS half count what exists. C6 closes the fifth: the verification
scripts themselves, which nothing ran and one of which had gone stale.

Those mechanisms had no suite. They were asserted only by C5's own
verification script — which is to say, by exactly the category C6 retires. So
their assertions live here now, where the gate runs them.

This file tests `scripts/ci.sh`, `scripts/run_suites.py` and
`scripts/check_js_tests.py` by construction: it writes a runner-less suite file
and a stray `.mjs`, checks that the gate refuses each, and removes them in a
`finally`. It never edits a real suite.
"""
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.abspath(__file__))
CI_SH = os.path.join(REPO, "scripts", "ci.sh")

PROBE_SUITE = "test_zz_gate_silent_probe.py"
PROBE_MJS = ("js/test/_gate_probe_sub/stray.test.mjs", "js/_gate_stray.test.mjs")

SILENT_SUITE = '''"""test_gate.py probe — a suite file with no `__main__` runner.

Written by test_gate.py and removed by it in a `finally`. If this file is in
your working tree, that suite died between writing it and cleaning up.
"""


def test_this_runs_but_reports_nothing():
    assert True
'''

STRAY_MJS = 'import { test } from "node:test";\ntest("stray", () => {});\n'


def _py(*args, logdir=None):
    """A child process. `logdir` redirects `run_suites.py` away from the shared
    `.ci-logs`, which it clears on entry — without that, a nested run deletes
    the logs of the run this suite is running inside."""
    env = dict(os.environ)
    if logdir:
        env["PLANES_LOGDIR"] = logdir
    return subprocess.run([sys.executable, *args], cwd=REPO, env=env,
                          capture_output=True, text=True)


def _ci_text():
    with open(CI_SH, encoding="utf-8") as fh:
        return fh.read()


# ======================================== 1. a silent suite fails (C5/Ruling 1)


def test_a_suite_that_reports_no_result_fails_the_gate():
    """A warning depends on somebody reading it, which is exactly what did not
    happen the first three times."""
    probe = os.path.join(REPO, PROBE_SUITE)
    try:
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write(SILENT_SUITE)
        with tempfile.TemporaryDirectory() as logs:
            r = _py("scripts/run_suites.py", "--only", PROBE_SUITE, logdir=logs)
        assert r.returncode != 0, "a silent suite passed the gate"
        assert PROBE_SUITE in r.stderr, r.stderr
        assert "reported no result" in r.stderr, r.stderr
        # The message names the fix, like every other error in this repo.
        assert "__main__" in r.stderr, r.stderr
    finally:
        if os.path.exists(probe):
            os.remove(probe)
    assert not os.path.exists(probe)


def test_a_deliberately_skipped_suite_does_not_fail_the_gate():
    """`--fast`, `--only` and `--skip` are safe by construction — `names` is the
    SELECTED set, so a skipped suite is never opened and can never be counted
    silent. Asserted rather than assumed."""
    probe = os.path.join(REPO, PROBE_SUITE)
    try:
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write(SILENT_SUITE)
        with tempfile.TemporaryDirectory() as logs:
            r = _py("scripts/run_suites.py", "--only", "test_fail.py",
                    "--only", PROBE_SUITE, "--skip", PROBE_SUITE, logdir=logs)
        assert r.returncode == 0, r.stderr
    finally:
        if os.path.exists(probe):
            os.remove(probe)


def test_the_suite_step_is_a_hard_step_in_ci_sh():
    """A non-zero return only fails the gate if ci.sh runs the step under
    `timed`. `timed_soft` swallows it, and two steps deliberately use it."""
    lines = _ci_text().splitlines()
    hard = [ln for ln in lines
            if "run_suites.py" in ln and ln.strip().startswith("timed ")]
    soft = [ln for ln in lines
            if "run_suites.py" in ln and ln.strip().startswith("timed_soft ")]
    assert hard and not soft, (hard, soft)


# ============================== 2. the gate counts what exists (C5/Ruling 1, js)


def test_every_js_test_file_that_exists_is_one_the_gate_runs():
    r = _py("scripts/check_js_tests.py")
    assert r.returncode == 0, r.stdout
    assert re.search(r"ok: every test-shaped file .*\(\d+ of \d+\)", r.stdout), \
        r.stdout


def test_a_js_test_file_outside_the_glob_fails_the_gate():
    """Wherever it is put: in a subdirectory the glob does not reach, or beside
    the test directory under a name nothing globs for."""
    for rel in PROBE_MJS:
        path = os.path.join(REPO, rel)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(STRAY_MJS)
            r = _py("scripts/check_js_tests.py")
            assert r.returncode != 0, (rel, r.stdout)
            assert rel in r.stdout, (rel, r.stdout)
        finally:
            if os.path.exists(path):
                os.remove(path)
            d = os.path.dirname(path)
            if d != os.path.join(REPO, "js") and os.path.isdir(d):
                os.rmdir(d)
    assert not any(os.path.exists(os.path.join(REPO, r)) for r in PROBE_MJS)


def test_the_js_enumeration_reads_the_glob_out_of_ci_sh():
    """A checker that restated `js/test/*.mjs` would agree with a ci.sh narrowed
    to something else — the same silent drift one level up."""
    with open(os.path.join(REPO, "scripts", "check_js_tests.py"),
              encoding="utf-8") as fh:
        src = fh.read()
    assert "CI_SH" in src and "run_set_globs" in src
    r = _py("scripts/check_js_tests.py")
    assert "ci.sh runs:" in r.stdout, r.stdout


def test_the_js_enumeration_step_is_a_hard_step_in_ci_sh():
    lines = _ci_text().splitlines()
    hard = [ln for ln in lines
            if "check_js_tests.py" in ln and ln.strip().startswith("timed ")]
    soft = [ln for ln in lines
            if "check_js_tests.py" in ln and ln.strip().startswith("timed_soft ")]
    assert hard and not soft, (hard, soft)


# ============================ 3. the gate refuses to run half-blind (C6 / A.4)


def test_a_shell_without_the_linters_fails_at_step_one():
    """`ruff` and `mypy` are invoked bare and this repo keeps both in ./.venv.
    A fresh shell used to die at step NINE with `command not found`, after the
    whole suite, the JS tests and every checker had already run.

    It fails rather than skipping, deliberately: `node` is the one thing this
    gate lets skip, and a green gate that silently type-checked nothing is the
    same dishonesty about its own coverage that section 1 above exists to
    prevent."""
    bare = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp")}
    r = subprocess.run(["/bin/bash", CI_SH], cwd=REPO, env=bare,
                       capture_output=True, text=True)
    assert r.returncode != 0, r.stdout
    assert "not on PATH" in r.stderr, r.stderr
    assert "ruff" in r.stderr and "mypy" in r.stderr, r.stderr
    assert ".venv" in r.stderr, r.stderr
    # Step one, not step nine: nothing expensive ran.
    assert "== test suite ==" not in r.stdout, r.stdout


def test_the_fast_tier_only_requires_what_it_runs():
    """`--fast` does not run mypy, so it must not refuse to start without it."""
    bare = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp")}
    r = subprocess.run(["/bin/bash", CI_SH, "--fast"], cwd=REPO, env=bare,
                       capture_output=True, text=True)
    assert "ruff" in r.stderr, r.stderr
    assert "mypy" not in r.stderr, r.stderr
    assert "--fast" in r.stderr, "the suggested command drops the tier"


def test_the_preflight_runs_before_the_first_timed_step():
    text = _ci_text()
    guard = text.index("not on PATH")
    first_step = min(text.index("timed "), text.index("== test suite =="))
    assert guard < first_step, (guard, first_step)


# ================= 4. no checker the gate does not run (C6 / Ruling 3)
#
# Seven `verify_*.py` scripts accumulated in this repo and NOTHING ran any of
# them. Two were already broken on main by the time C6 counted, and one had
# asserted the opposite of the shipped `path` convention for a whole build.
#
# The remedy is not a fifth mechanism to watch — it is that the category does
# not exist. A verification script graduates into a suite or is deleted when
# its build merges. This is the assertion that makes the rule self-checking,
# which is the first thing five instances of one failure class has earned.


def _verify_scripts():
    found = []
    for dirpath, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs
                   if d not in (".git", ".venv", "__pycache__", ".ci-logs",
                                "node_modules", ".mypy_cache", ".ruff_cache",
                                ".pytest_cache")]
        for f in files:
            if f.startswith("verify_") and f.endswith(".py"):
                rel = os.path.relpath(os.path.join(dirpath, f), REPO)
                found.append(rel.replace(os.sep, "/"))
    return sorted(found)


def test_no_verification_script_exists_for_the_gate_not_to_run():
    """The rule, enforced: a build's verification script is not product code
    and carries no maintenance expectation, so a kept one is a stale assertion
    waiting to mislead. If you are reading this because it failed, the two
    options are the whole of it — move the assertions into a `test_*.py` this
    gate runs, or delete the script."""
    found = _verify_scripts()
    assert not found, (
        "verification script(s) the gate does not run: " + ", ".join(found)
        + " — graduate the durable assertions into a test_*.py, delete the rest")


def test_the_retirement_rule_is_stated_where_the_next_build_reads_it():
    """A rule that lives only in a report is a rule the next build does not
    see."""
    text = _ci_text()
    assert "RETIREMENT RULE" in text, "the rule is not stated in scripts/ci.sh"
    assert "graduates into a suite or is deleted" in text.lower(), text[:0]


def test_the_graduated_assertion_is_in_a_suite_the_gate_runs():
    """`run-batch` answering what `run` answers was asserted only by
    `scripts/verify_batch_equivalence.py`, which nothing ran. It is the one
    claim among the seven with no counterpart anywhere in the suite."""
    graduated = os.path.join(REPO, "test_batch_equivalence.py")
    assert os.path.exists(graduated), "the graduated suite is missing"
    with open(graduated, encoding="utf-8") as fh:
        src = fh.read()
    assert "batch_sources" in src and "_js_raw" in src
    # It is discovered by the runner, which is what "the gate runs it" means.
    r = _py("scripts/check_js_tests.py")   # cheap; proves the tree is sane
    assert r.returncode == 0
    assert os.path.basename(graduated).startswith("test_")


if __name__ == "__main__":
    fails = []
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_")]
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
