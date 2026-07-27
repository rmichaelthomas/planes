#!/usr/bin/env python3
"""C5's automated verification — the whole build, checked without a human.

Four sections, matching the build's own acceptance gate:

  A  silent suites  a runner-less Python suite fails the gate and is named; a
                    stray .mjs fails the gate; a deliberately skipped suite
                    still passes; and both checks are HARD steps in ci.sh
  B  the split      the sub-counts sum to the shortfall they split, the
                    multiplicity figure is reported rather than resolved, and
                    the reference work list is untouched at 0 of 109
  C  the convention `{ path }` binds on every error in all three
                    implementations, a real path still carries the same steps,
                    `{ fix }` is unchanged, and the three still agree on tag
                    and detail across 348 shapes
  D  regression     the suite totals, the four counts, the JS test count

A failure in A, C or D is blocking. B reports its arithmetic either way, so a
run that fails still says what the numbers were.

Section A works by construction — it writes a temporary suite file and a
temporary .mjs, checks that the gate refuses them, and removes them in a
`finally`. It never edits a real suite.

Writes the same table to stdout and to three-rulings-verification.md.

Usage: python3 scripts/verify_three_rulings.py [--quick]
       --quick skips section D's full suite run (the only slow step).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import errors_coverage as ec  # noqa: E402
from interp import Interpreter, PlanesError, error_record  # noqa: E402
from lexer import EFFECT_KINDS, KEYWORDS  # noqa: E402
from parser import BUILTIN_NAMES  # noqa: E402

ROWS: list[tuple[str, str, bool, str]] = []
NOTES: list[str] = []

PROBE_SUITE = "test_zz_c5_silent_probe.py"
PROBE_MJS = ("js/test/_c5_probe_sub/stray.test.mjs", "js/_c5_stray.test.mjs")


def check(section: str, name: str, ok: bool, detail: str = "") -> bool:
    ROWS.append((section, name, bool(ok), detail))
    return bool(ok)


def have_node() -> bool:
    return subprocess.run(["which", "node"], capture_output=True).returncode == 0


def py(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=REPO,
                          capture_output=True, text=True)


def node_cli(*args: str) -> subprocess.CompletedProcess:
    r = subprocess.run(["node", "js/cli.mjs", *args], cwd=REPO,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node {' '.join(args)} failed:\n{r.stderr}")
    return r


def run_py(src: str) -> list[str]:
    itp = Interpreter()
    try:
        itp.run(src)
    except PlanesError:
        pass
    return list(itp.output)


def run_js(src: str) -> list[str]:
    out = node_cli("run-batch", json.dumps([{"id": "0", "src": src}])).stdout
    return json.loads(out)[0]["output"]


def run_self_hosted(src: str) -> list[str]:
    """One program through grammar/interp.planes running on the JavaScript
    interpreter — the third implementation."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "p.planes")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(src)
        return json.loads(node_cli("meta", "run", p).stdout)[0]["output"]


def three_ways(src: str) -> tuple[list[str], list[str], list[str]]:
    if not have_node():
        raise AssertionError("node is not on PATH — cannot check three ways")
    return run_py(src), run_js(src), run_self_hosted(src)


# ======================================================== A: silent suites

SILENT_SUITE = '''"""C5 verification probe — a suite file with no `__main__` runner.

Written by scripts/verify_three_rulings.py and removed by it. If this file is
in your working tree, that script died between writing it and its `finally`.
"""


def test_this_runs_but_reports_nothing():
    assert True
'''

STRAY_MJS = 'import { test } from "node:test";\ntest("stray", () => {});\n'


def section_a() -> None:
    # --- A.1: a suite that reports nothing fails, and is named -------------
    probe = os.path.join(REPO, PROBE_SUITE)
    try:
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write(SILENT_SUITE)
        r = py("scripts/run_suites.py", "--only", PROBE_SUITE)
        check("A", "a runner-less suite exits non-zero", r.returncode != 0,
              f"exit {r.returncode}")
        check("A", "the failure names the silent file", PROBE_SUITE in r.stderr,
              (r.stderr.strip().splitlines() or [""])[0][:90])

        # --- A.2: the skip path is safe by construction --------------------
        r = py("scripts/run_suites.py", "--only", "test_fail.py",
               "--only", PROBE_SUITE, "--skip", PROBE_SUITE)
        check("A", "a deliberately skipped suite does not fail the gate",
              r.returncode == 0, f"exit {r.returncode}")
    finally:
        if os.path.exists(probe):
            os.remove(probe)
    check("A", "the probe suite is removed",
          not os.path.exists(probe), PROBE_SUITE)

    # --- A.3: the clean tree passes both checks ---------------------------
    r = py("scripts/check_js_tests.py")
    m = re.search(r"ok: every test-shaped file .*\((\d+) of (\d+)\)", r.stdout)
    check("A", "every js test file that exists is one the gate runs",
          r.returncode == 0 and bool(m),
          f"{m.group(1)} of {m.group(2)}" if m else r.stdout.strip()[-80:])

    # --- A.4: a stray .mjs fails, wherever it is put ----------------------
    for rel in PROBE_MJS:
        path = os.path.join(REPO, rel)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(STRAY_MJS)
            r = py("scripts/check_js_tests.py")
            where = "in a subdirectory" if "/_c5_probe_sub/" in rel else \
                "beside the test directory"
            check("A", f"a stray .mjs {where} fails the gate",
                  r.returncode != 0 and rel in r.stdout, f"exit {r.returncode}")
        finally:
            if os.path.exists(path):
                os.remove(path)
            d = os.path.dirname(path)
            if d != os.path.join(REPO, "js") and os.path.isdir(d):
                os.rmdir(d)
    check("A", "the probe .mjs files are removed",
          not any(os.path.exists(os.path.join(REPO, r)) for r in PROBE_MJS),
          ", ".join(PROBE_MJS))

    # --- A.5: both are HARD steps in ci.sh --------------------------------
    # A non-zero return only fails the gate if ci.sh runs the step under
    # `timed`. `timed_soft` swallows it, and two steps deliberately use it.
    with open(os.path.join(REPO, "scripts", "ci.sh"), encoding="utf-8") as fh:
        ci = fh.read()
    for label, needle in (("run_suites.py", "run_suites.py"),
                          ("check_js_tests.py", "check_js_tests.py")):
        hard = [ln for ln in ci.splitlines()
                if needle in ln and ln.strip().startswith("timed ")]
        soft = [ln for ln in ci.splitlines()
                if needle in ln and ln.strip().startswith("timed_soft ")]
        check("A", f"ci.sh runs {label} as a hard step",
              bool(hard) and not soft,
              f"{len(hard)} timed, {len(soft)} timed_soft")


# ============================================================ B: the split

def section_b() -> None:
    sites = ec.self_hosted_sites()
    shortfall = sites[ec.SHORTFALL]
    twins = ec.reference_fix_tags()
    split = ec.split_shortfall(shortfall, twins)
    has, none = len(split[ec.HAS_TWIN]), len(split[ec.NO_TWIN])

    check("B", "the sub-counts sum to the shortfall they split",
          has + none == len(shortfall), f"{has} + {none} = {len(shortfall)}")
    check("B", "the self-hosted total is unmoved at 72 of 113",
          len(shortfall) == 72 and sum(len(v) for v in sites.values()) == 113,
          f"{len(shortfall)} of {sum(len(v) for v in sites.values())}")

    by_file: dict[str, int] = {}
    for f, _, _, _ in shortfall:
        by_file[f] = by_file.get(f, 0) + 1
    want = {"interp.planes": 54, "parser.planes": 14, "lexer.planes": 3,
            "json.planes": 1}
    check("B", "the per-file breakdown is preserved", by_file == want,
          ", ".join(f"{k} {v}" for k, v in by_file.items()))

    multi = split["multiplicity"]
    check("B", "multiplicity is reported rather than resolved",
          bool(multi) and all(len(twins[s[3]]) > 1 for s in multi),
          f"{len(multi)} sites, {len({s[3] for s in multi})} tags")
    check("B", "an unreadable tag falls to the side nothing checked",
          all(s[3] is None and s in split[ec.NO_TWIN]
              for s in split["tag_unreadable"]),
          f"{len(split['tag_unreadable'])} sites")

    cov = ec.coverage()
    check("B", "the reference work list is still zero of 109",
          cov["counts"][ec.SHORTFALL] == 0 and cov["errors"] == 109,
          f"{cov['counts'][ec.SHORTFALL]} of {cov['errors']}")

    untagged, entries = ec.untagged_reference_entries()
    check("B", "the tag-matching ceiling is reported", untagged > 0,
          f"{untagged} of {entries} catalogued errors carry no tag")

    r = py("errors_coverage.py")
    r2 = py("errors_coverage.py", "--json")
    check("B", "the checker still reports and never fails (invariant 3)",
          r.returncode == 0 and r2.returncode == 0,
          f"exit {r.returncode} / {r2.returncode}")
    carried = json.loads(r2.stdout).get("self_hosted_split", {})
    check("B", "--json carries the split",
          carried.get("counts", {}).get("sum") == len(shortfall)
          and "multiplicity" in carried,
          json.dumps(carried.get("counts", {})))
    NOTES.append(f"B: the split is {has} to port, {none} to write — and "
                 f"{none} is a ceiling, not a measurement: {untagged} of the "
                 f"{entries} catalogued reference errors carry no tag at all, "
                 "so a self-hosted syntax error cannot match one however close "
                 "the message.")


# ======================================================= C: the convention

PATH_BIND = ('to risky:\n'
             '  fail "plain" as inner\n'
             'x = risky() or fail as e:\n'
             '  when e is { path }:\n'
             '    show "bound: " + (text of path)\n'
             '  else:\n'
             '    show "no path field"\n')

FIX_BIND = ('to risky:\n'
            '  fail "plain" as inner\n'
            'x = risky() or fail as e:\n'
            '  when e is { fix }:\n'
            '    show "bound: " + (text of fix)\n'
            '  else:\n'
            '    show "no fix field"\n')

REAL_PATH = ('x = ({a: [1, "2"]} == {a: [1, 2]})\n'
             '  or fail as e:\n'
             '    show text of (count of e.path)\n'
             '    show join of (for each s in e.path: text of s)\n')


def section_c() -> None:
    if not have_node():
        check("C", "node is on PATH", False, "cannot check three ways")
        return

    for label, src, want in (
            ("`when e is { path }` binds on every error", PATH_BIND,
             ["bound: nothing"]),
            ("`when e is { fix }` is unchanged", FIX_BIND, ["bound: nothing"])):
        p, j, s = three_ways(src)
        check("C", label, p == j == s == want, f"py={p} js={j} planes={s}")

    # A path that DOES apply is unchanged: the record field "a", then list
    # index 1 — a field name as text, a list index as a Planes number.
    p, j = run_py(REAL_PATH), run_js(REAL_PATH)
    check("C", "a real path still carries the same steps",
          p == j == ["2", "a1"], f"py={p} js={j}")

    try:
        Interpreter().run("x = 1 / 0")
        rec = None
    except PlanesError as e:
        rec = error_record(e)
    check("C", "the field is present-and-nothing, not absent",
          rec is not None and "path" in rec and rec["path"] is None,
          f"keys={sorted(rec) if rec else None}")

    # The self-hosted implementation had no `path` field at all — C.1's first
    # question — so the FIELD converging is the whole of its change here.
    with open(os.path.join(REPO, "grammar", "interp.planes"),
              encoding="utf-8") as fh:
        planes = fh.read()
    check("C", "the self-hosted record carries the field too",
          'key: "path"' in planes, "make-error-value")

    # C.4's grep, run rather than remembered: no program anywhere used
    # `{ path }` as a presence test, which is why nothing's behaviour moved.
    trees = ["grammar/*.planes", "corpus/**/*.planes", "demo/**/*.planes",
             "probe/**/*.planes", "*.planes"]
    files = sorted({p for t in trees
                    for p in glob.glob(os.path.join(REPO, t), recursive=True)})
    users = []
    for planes_file in files:
        with open(planes_file, encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                if line.lstrip().startswith("#"):
                    continue
                if re.search(r"\{\s*path\s*\}", line):
                    users.append(f"{os.path.relpath(planes_file, REPO)}:{n}")
    check("C", "no .planes program used `{ path }` as a presence test",
          not users, f"{len(files)} files searched, {len(users)} users")

    import test_builtin_guards as tbg
    cases = len(tbg._three_way_cases())
    try:
        tbg.test_all_three_implementations_agree_on_tag_and_detail()
        agree, why = True, f"{cases} shapes, 0 divergences"
    except AssertionError as e:
        agree, why = False, str(e)[:120]
    check("C", "all three agree on tag and detail across every shape", agree,
          why)


# ========================================================== D: regression

def section_d(quick: bool) -> None:
    check("D", "reserved words still 32", len(KEYWORDS) == 32,
          str(len(KEYWORDS)))
    check("D", "builtins still 10", len(BUILTIN_NAMES) == 10,
          str(len(BUILTIN_NAMES)))
    check("D", "effect kinds still 7", len(EFFECT_KINDS) == 7,
          str(len(EFFECT_KINDS)))
    with open(os.path.join(REPO, "grammar", "vocabulary.json"),
              encoding="utf-8") as fh:
        vocab = json.load(fh)
    check("D", "token classes still 7", len(vocab["token_classes"]) == 7,
          str(len(vocab["token_classes"])))

    if have_node():
        r = subprocess.run(["node", "--test", *sorted(
            glob.glob(os.path.join(REPO, "js", "test", "*.mjs")))],
            cwd=REPO, capture_output=True, text=True)
        m = re.search(r"^# pass (\d+)", r.stdout, re.M)
        failed = re.search(r"^# fail (\d+)", r.stdout, re.M)
        passed = int(m.group(1)) if m else -1
        check("D", "js/test passes and is at least the 47 baseline",
              r.returncode == 0 and passed >= 47
              and failed is not None and failed.group(1) == "0",
              f"{passed} passing")

    if quick:
        NOTES.append("D: --quick skipped the full suite run, so the ok total "
                     "and the reporting count are UNVERIFIED in this run.")
        return
    r = py("scripts/run_suites.py")
    m = re.search(r"== suites: (\d+) files, (\d+) reporting, (\d+) oks", r.stdout)
    if not m:
        check("D", "the suite run reports its totals", False,
              r.stdout.strip()[-120:])
        return
    files, reporting, oks = (int(g) for g in m.groups())
    check("D", "the suite passes", r.returncode == 0, f"exit {r.returncode}")
    check("D", "every suite file reports a result", files == reporting,
          f"{reporting} of {files}")
    check("D", "the ok total is at least the 1085 baseline", oks >= 1085,
          f"{oks} oks")


# =============================================================== the table

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="skip section D's full suite run")
    args = ap.parse_args()

    for sec, fn in (("A", section_a), ("B", section_b), ("C", section_c),
                    ("D", lambda: section_d(args.quick))):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            check(sec, f"section {sec} raised", False, f"{type(e).__name__}: {e}")

    width = max(len(n) for _, n, _, _ in ROWS)
    lines = ["# C5 three-rulings verification", "",
             "| | check | result | detail |", "|---|---|---|---|"]
    out = []
    for sec, name, ok, detail in ROWS:
        mark = "PASS" if ok else "FAIL"
        out.append(f"  [{sec}] {mark:<4} {name:<{width}}  {detail}")
        lines.append(f"| {sec} | {name} | {'✅ pass' if ok else '❌ **FAIL**'} "
                     f"| {detail} |")
    print("\n".join(out))
    print()

    blocking = [r for r in ROWS if not r[2] and r[0] in ("A", "C", "D")]
    other = [r for r in ROWS if not r[2] and r[0] not in ("A", "C", "D")]
    verdict = ("ALL CHECKS PASS" if not (blocking or other)
               else f"{len(blocking)} BLOCKING FAILURE(S), {len(other)} other")
    print(verdict)
    lines += ["", *NOTES, "", f"**{verdict}**"]
    with open(os.path.join(REPO, "three-rulings-verification.md"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
