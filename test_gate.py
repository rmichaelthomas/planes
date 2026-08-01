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
#
# THE SIXTH INSTANCE ARRIVED IN A DIFFERENT LANGUAGE. This check was written
# for `verify_*.py` because that is the shape the problem had at the time, and
# three JavaScript builds then shipped `scripts/verify-*.mjs` — hyphens, .mjs —
# which walked straight past it. `verify-canvas-runtime.mjs` reported BLOCKING
# FAILURE on green main for two builds, still asserting a retired ten-verb
# whitelist, and nobody knew, because nobody ran it. A guard written to the
# shape of the last instance catches only the last instance; this one matches
# the NAME, in either spelling, in any language the repo executes.


VERIFY_SUFFIXES = (".py", ".mjs", ".js", ".ts", ".sh")


def _verify_scripts():
    found = []
    for dirpath, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs
                   if d not in (".git", ".venv", "__pycache__", ".ci-logs",
                                "node_modules", ".mypy_cache", ".ruff_cache",
                                ".pytest_cache")]
        for f in files:
            named_verify = f.startswith("verify_") or f.startswith("verify-")
            if named_verify and f.endswith(VERIFY_SUFFIXES):
                rel = os.path.relpath(os.path.join(dirpath, f), REPO)
                found.append(rel.replace(os.sep, "/"))
    return sorted(found)


def test_no_verification_script_exists_for_the_gate_not_to_run():
    """The rule, enforced: a build's verification script is not product code
    and carries no maintenance expectation, so a kept one is a stale assertion
    waiting to mislead. If you are reading this because it failed, the two
    options are the whole of it — move the assertions into a suite this gate
    runs (`test_*.py`, or `js/test/*.test.mjs` for the JavaScript side), or
    delete the script. Both spellings and every executable extension count:
    the rule is about the category, not about Python."""
    found = _verify_scripts()
    assert not found, (
        "verification script(s) the gate does not run: " + ", ".join(found)
        + " — graduate the durable assertions into a suite the gate runs"
          " (test_*.py, or js/test/*.test.mjs), delete the rest")


def test_the_retirement_rule_is_stated_where_the_next_build_reads_it():
    """A rule that lives only in a report is a rule the next build does not
    see."""
    text = _ci_text()
    assert "RETIREMENT RULE" in text, "the rule is not stated in scripts/ci.sh"
    assert "graduates into a suite or is deleted" in text.lower(), text[:0]


# ================== 5. identity/ is outside the gate, by ruling (D / §4.1)


def test_the_identity_directory_is_excluded_from_ruff_and_mypy():
    """`render_logo.py` is a design-asset generator, not part of the language
    implementation. Holding it to the language's linting and typing gate would
    create work with no payoff."""
    with open(os.path.join(REPO, "pyproject.toml"), encoding="utf-8") as fh:
        toml = fh.read()
    assert 'exclude = ["identity"]' in toml, "ruff still walks identity/"
    assert 'exclude = ["^identity/"]' in toml, "mypy still walks identity/"


def test_nothing_in_identity_can_become_a_gate_dependency():
    """Invariant 7, checked rather than assumed — and the assumption was wrong.
    Six suites glob `**/*.planes` recursively from the repo root and one walks
    the whole tree, so `identity/` is NOT invisible to them by construction. It
    is invisible because it holds no `.planes` file and no host call, and those
    are the two facts that have to stay true."""
    ident = os.path.join(REPO, "identity")
    if not os.path.isdir(ident):
        return
    stray = []
    for dirpath, _dirs, files in os.walk(ident):
        for f in files:
            if f.endswith(".planes") or f.startswith("test_"):
                stray.append(os.path.relpath(os.path.join(dirpath, f), REPO))
    assert not stray, (
        "identity/ holds a file the language's suites would pick up: "
        + ", ".join(stray) + " — identity/ is outside the gate by ruling")


def test_the_animated_mark_is_generated_not_hand_written():
    """D-Q1, completing v7.0 §89. The hand-written CSS restated PLANES by hand;
    a superseded artifact left alongside its generator is the drift the ruling
    exists to prevent, so there is exactly one of it and the generator owns it."""
    mark = os.path.join(REPO, "identity", "planes-icon-animated.html")
    if not os.path.exists(mark):
        return
    with open(mark, encoding="utf-8") as fh:
        html = fh.read()
    assert "GENERATED by render_logo.py" in html, html[:200]
    # Derived from the data, not restated: the hand-written file's oblique
    # plane was `rotateX(45deg) rotateY(45deg)`, which is not the basis
    # `record` declares.
    assert "matrix3d(" in html
    assert "rotateX(45deg) rotateY(45deg)" not in html


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


def test_every_servable_page_reaches_the_deploy():
    """garden.html shipped in #52 and 404'd on GitHub Pages for two builds
    while Deploy Pages reported success on every push. The workflow copied a
    hardcoded `cp index.html paint.html _site/`, and copying a list of files
    that all exist always succeeds -- a page absent from the list is invisible
    to the only thing that could have noticed. The deploy must be DERIVED from
    the tree, and the derivation must be checked against the authored set."""
    wf = os.path.join(REPO, ".github", "workflows", "pages.yml")
    if not os.path.exists(wf):
        return
    with open(wf, encoding="utf-8") as fh:
        yml = fh.read()
    body = "\n".join(ln for ln in yml.splitlines()
                     if not ln.lstrip().startswith("#"))

    # No page may be named individually in the copy -- that is the allowlist.
    pages = [f for f in os.listdir(REPO) if f.endswith(".html")]
    assert pages, "no root pages to deploy"
    for page in pages:
        assert f"cp {page}" not in body and f" {page} _site" not in body, (
            f"pages.yml names {page} in the copy: an allowlist is how "
            f"garden.html went missing. Copy ./*.html instead.")
    assert "cp ./*.html _site/" in body, (
        "pages.yml must copy every root page, not a named few")

    # js/ must be walked, not enumerated per-directory: `js/*.mjs` plus
    # `js/paint/*.mjs` is what left js/sound/ out of the deploy in #52.
    assert "find js -name '*.mjs'" in body, (
        "pages.yml must walk js/ so a new module directory ships with the "
        "page that imports it")

    # And the built tree is checked against what was authored. Without
    # --source the checker shares the allowlist's blind spot exactly: it
    # walks only the pages that shipped, so an omitted page has no
    # references to fail on and the check passes.
    checker = os.path.join(REPO, "scripts", "check_pages_surface.py")
    assert os.path.exists(checker), "the deploy's own check is missing"
    assert "check_pages_surface.py _site --source=." in body, (
        "pages.yml must run the surface check against _site WITH --source, "
        "or an omitted page passes unnoticed")

    # The check is real here and now, not only on a runner.
    r = _py("scripts/check_pages_surface.py", REPO, f"--source={REPO}")
    assert r.returncode == 0, r.stdout + r.stderr


def _reference_mockups():
    """The pages that exist to be COMPARED AGAINST, not visited.

    Derived, not hardcoded: `garden-page-spec.md` names its reference
    implementations in its own preamble, and a page is exempt from the
    landing-page rule below exactly when a spec cites it that way. A new
    product page cannot become exempt by being added -- someone would have to
    write it into a spec as a reference implementation first, which is the
    point at which it stopped being a destination.
    """
    cited = set()
    subjects = set()
    for name in os.listdir(REPO):
        if not name.endswith("-spec.md"):
            continue
        with open(os.path.join(REPO, name), encoding="utf-8") as fh:
            head = fh.read(2000)
        # A page a spec is FOR is a product page and can never be a mockup, no
        # matter what any sentence says about it. This is the belt to the
        # sentence-scoping braces below: rewording a preamble once put
        # `garden.html` inside the reference sentence and silently exempted the
        # very page the rule was written for.
        for m in re.finditer(r"\*\*For:\*\*\s*`([A-Za-z0-9._-]+\.html)`", head):
            subjects.add(m.group(1))
        # ONLY the reference-implementations sentence. The preamble also says
        # "**For:** `garden.html`" and the body names `paint.html`, so a scan
        # of the whole head exempts the very pages the rule exists to protect
        # -- which is how the first version of this emptied itself out.
        marker = head.find("Reference implementation")
        if marker < 0:
            continue
        sentence = head[marker:]
        end = sentence.find(". ")
        cited.update(re.findall(r"`([A-Za-z0-9._-]+\.html)`",
                                sentence[:end] if end > 0 else sentence))
    return cited - subjects


def test_the_landing_page_links_to_the_pages_it_ships_with():
    """The deploy carried paint.html and garden.html while index.html linked
    to nothing but the repo, so a shipped page was unreachable by anyone who
    did not already know its filename -- indistinguishable, from outside,
    from the page not being deployed at all.

    Reference mockups are exempt because they are not destinations; every
    other page the deploy carries has to be reachable from the front door."""
    idx = os.path.join(REPO, "index.html")
    with open(idx, encoding="utf-8") as fh:
        html = fh.read()
    exempt = _reference_mockups()
    pages = sorted(f for f in os.listdir(REPO)
                   if f.endswith(".html") and f != "index.html")
    linked = [p for p in pages if p not in exempt]
    assert linked, "every page is exempt -- the rule has been emptied out"
    for page in linked:
        assert f'href="./{page}"' in html, (
            f"{page} is deployed but index.html does not link to it")


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
