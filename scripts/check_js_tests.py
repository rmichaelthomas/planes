#!/usr/bin/env python3
"""check_js_tests — every test-shaped `.mjs` under `js/` is one the gate runs.

C5 / Ruling 1, the JavaScript half. `scripts/ci.sh` runs

    node --test js/test/*.mjs

and that glob covers exactly one directory, non-recursively. Nothing anywhere
counted how many JS test files *exist* against how many were run — so a test
file under `js/test/sub/`, or one named to a different convention elsewhere
under `js/`, would be invisible in precisely the way the 47 tests in js/test/
were invisible until C4 found them by accident while removing a dead host
method. That was the third instance of one failure class (REPORT_HOST_BOUNDARY
§5, then two Python suites, then the whole of js/test/); this is the mechanism
nothing had ever looked at.

The Python half of the same ruling lives in `scripts/run_suites.py`: a suite
file that reports no result exits non-zero. Between them the gate now counts
what exists on both sides rather than what it happens to have been pointed at.

THE RUN SET IS READ OUT OF ci.sh, NOT RESTATED HERE

A checker that hard-coded `js/test/*.mjs` would agree with a `ci.sh` that had
been changed to something narrower, which is the same silent-drift failure one
level up. So the globs are parsed out of the `node --test` invocation in
`scripts/ci.sh` and expanded here. Change the glob in ci.sh and this check
follows it; delete the invocation and this check says so.

WHAT COUNTS AS TEST-SHAPED

Two rules, unioned, because a file hidden by a naming convention is exactly
what this is looking for:

  * the basename ends in `.test.mjs` — the convention all seven files in
    js/test/ share, confirmed by listing the directory rather than assumed;
  * the path has a `test` or `tests` directory component — so a file that
    lands in js/test/sub/ under any name is still caught.

It reports and exits non-zero; it never edits anything.

    python3 scripts/check_js_tests.py
"""
from __future__ import annotations

import glob
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_DIR = os.path.join(REPO, "js")
CI_SH = os.path.join(REPO, "scripts", "ci.sh")

# The `node --test <glob>...` line in ci.sh. Captures everything after
# `--test` up to end of line; `timed "js/test" node --test js/test/*.mjs`
# yields `js/test/*.mjs`.
NODE_TEST = re.compile(r"^\s*(?:timed(?:_soft)?\s+\S+\s+)?node\s+--test\s+(.+?)\s*$")

TEST_DIR_NAMES = {"test", "tests"}


def run_set_globs(ci_text: str) -> list[str]:
    """The glob arguments ci.sh hands to `node --test`, in order."""
    out: list[str] = []
    for line in ci_text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = NODE_TEST.match(line)
        if m:
            out.extend(m.group(1).split())
    return out


def expand(globs: list[str]) -> set[str]:
    """Repo-relative paths the globs actually match, with `/` separators."""
    found: set[str] = set()
    for pattern in globs:
        for p in glob.glob(os.path.join(REPO, pattern), recursive=True):
            found.add(os.path.relpath(p, REPO).replace(os.sep, "/"))
    return found


def is_test_shaped(rel: str) -> bool:
    parts = rel.split("/")
    if parts[-1].endswith(".test.mjs"):
        return True
    return bool(TEST_DIR_NAMES & set(parts[:-1]))


def test_shaped_files() -> set[str]:
    """Every test-shaped `.mjs` anywhere under js/, recursively."""
    found: set[str] = set()
    for dirpath, _dirs, files in os.walk(JS_DIR):
        for f in files:
            if not f.endswith(".mjs"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), REPO)
            rel = rel.replace(os.sep, "/")
            if is_test_shaped(rel):
                found.add(rel)
    return found


def conventions(files: set[str]) -> tuple[set[str], set[str]]:
    """(named to the `.test.mjs` convention, caught only by directory)."""
    named = {f for f in files if f.split("/")[-1].endswith(".test.mjs")}
    return named, files - named


def check() -> tuple[int, list[str]]:
    lines: list[str] = []
    if not os.path.isdir(JS_DIR):
        return 0, ["check_js_tests: no js/ directory — nothing to count."]

    with open(CI_SH, encoding="utf-8") as fh:
        ci_text = fh.read()
    globs = run_set_globs(ci_text)
    existing = test_shaped_files()
    named, by_dir = conventions(existing)

    lines.append("check_js_tests: test-shaped .mjs under js/ against what "
                 "scripts/ci.sh runs")
    lines.append("=" * 72)
    lines.append("")

    if not globs:
        lines.append("  FAIL: scripts/ci.sh has no `node --test` invocation, so "
                     "nothing runs the")
        lines.append(f"        {len(existing)} test-shaped file(s) under js/.")
        for f in sorted(existing):
            lines.append(f"          {f}")
        lines.append("")
        lines.append("  fix: restore the `node --test js/test/*.mjs` step in "
                     "scripts/ci.sh")
        return 1, lines

    run = expand(globs)
    lines.append(f"  ci.sh runs: {' '.join(globs)}")
    lines.append(f"  {len(existing)} test-shaped file(s) exist under js/; "
                 f"{len(run)} file(s) matched by the gate's glob(s).")
    if by_dir:
        # The prompt's own instruction: confirm the convention rather than
        # assume it, and say so when it is not uniform.
        lines.append(f"  {len(named)} named `*.test.mjs`; {len(by_dir)} caught "
                     "only by living in a test/ directory:")
        for f in sorted(by_dir):
            lines.append(f"      {f}")
    else:
        lines.append(f"  all {len(named)} share one convention: `*.test.mjs`.")
    lines.append("")

    missed = sorted(existing - run)
    if missed:
        lines.append(f"  FAIL: {len(missed)} test-shaped file(s) exist that the "
                     "gate does not run:")
        for f in missed:
            lines.append(f"      {f}")
        lines.append("")
        lines.append("  fix: move the file under a directory the ci.sh glob "
                     "covers, or widen the")
        lines.append("       `node --test` glob in scripts/ci.sh to reach it")
        return 1, lines

    # A run set that matched nothing is the same failure wearing a different
    # hat: the gate would report a green js/test step having executed no test.
    if not run:
        lines.append("  FAIL: the gate's glob(s) match no file at all — the "
                     "js/test step runs nothing.")
        lines.append("  fix: point the `node --test` glob in scripts/ci.sh at "
                     "the test files that exist")
        return 1, lines

    lines.append(f"  ok: every test-shaped file under js/ is inside what the "
                 f"gate runs ({len(run)} of {len(run)}).")
    extra = sorted(run - existing)
    if extra:
        # Not a failure: the gate running a file this checker would not have
        # called test-shaped is the safe direction. Reported so the two
        # definitions can be seen to differ rather than assumed to agree.
        lines.append(f"  note: {len(extra)} file(s) the gate runs are not "
                     "test-shaped by this checker's rule:")
        for f in extra:
            lines.append(f"      {f}")
    return 0, lines


def main(argv: list[str]) -> int:
    rc, lines = check()
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
