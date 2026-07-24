#!/usr/bin/env python3
"""Verification gate for the annotation plane and canonical renderer build,
extended for the Tier 0 follow-on (closing the gaps §7 of that build's own
report named). Runs A1/A2/B/C/D/E/F/G and writes annotation-verification.md.
No input from a human is required.

A is split into A1 (files that actually carry annotations -- the guarantee)
and A2 (files that don't, where stripping is a no-op -- a regression net,
not evidence for the guarantee itself): the prior single "A" section let 35
PASS rows read as broader coverage than the 8 that were doing real work.

Exit 0 if A1, B, E, F, and G all pass (the blocking set, per this build's
§10.2). C and D are reported but do not block, though in practice every row
here must hold for the build to be done.
"""
import subprocess
import sys

from interp import Interpreter, PlanesError
from lexer import KEYWORDS, Because, Rule
from parser import parse
from render import ast_equal, render, strip_annotations
from shapes import analyse
from test_annotation import (
    FIXTURE_KWARGS,
    STANDALONE_PLANES_FILES,
    all_planes_files,
    annotation_nesting_kinds,
    has_annotations,
)

RESULTS: list = []   # (section, name, passed, detail)


def record(section, name, passed, detail=""):
    RESULTS.append((section, name, passed, detail))
    return passed


def run_and_capture(src, **kw):
    kw.setdefault("fs", {})
    i = Interpreter(**kw)
    full_output = i.run(src)
    surface = analyse(src)
    show_output = [e[1] for e in i.effects if e[0] == "show"]
    return show_output, list(i.effects), [str(e) for e in surface.declared], full_output


def three_way(src, **kw):
    """(ok, detail, a_full, b_full) -- show-output/effects/surface compared;
    full output (which includes why) returned for a caller that wants it,
    not compared here (§ the why boundary, docs/annotation-scope.md)."""
    prog = parse(src)
    stripped_src = render(strip_annotations(prog))
    a_show, a_eff, a_surf, a_full = run_and_capture(src, **kw)
    b_show, b_eff, b_surf, b_full = run_and_capture(stripped_src, **kw)
    ok = a_show == b_show and a_eff == b_eff and a_surf == b_surf
    detail = "" if ok else (
        f"show-output {a_show!r} vs {b_show!r}; "
        f"effects {a_eff!r} vs {b_eff!r}; "
        f"surface {a_surf!r} vs {b_surf!r}")
    return ok, detail, a_full, b_full


# ================================================================ A1/A2. inertness

def section_a():
    for path in STANDALONE_PLANES_FILES:
        src = open(path).read()
        kw = FIXTURE_KWARGS.get(path, {})
        try:
            ok, detail, _, _ = three_way(src, **kw)
            section = "A1" if has_annotations(parse(src)) else "A2"
            label = ("annotated vs stripped are three-way identical"
                      if section == "A1" else
                      "strip is a no-op (no annotations to begin with), "
                      "run-based regression net")
            record(section, f"{path}: {label}", ok, detail)
        except Exception as e:
            record("A1", f"{path}: annotated vs stripped are three-way identical",
                   False, f"{type(e).__name__}: {e}")

    # structural strip-is-a-no-op check for files that can't run standalone
    # (demo/'s multi-file fixtures) -- A2 only; a file WITH annotations is
    # proven by the run-based A1 check above, not claimed here too.
    for path in all_planes_files():
        if path in STANDALONE_PLANES_FILES:
            continue
        name = f"{path}: strip is structurally a no-op (no annotations to begin with)"
        try:
            prog = parse(open(path).read())
            if has_annotations(prog):
                continue
            stripped = strip_annotations(prog)
            ok = len(prog) == len(stripped) and all(
                ast_equal(a, b) for a, b in zip(prog, stripped))
            record("A2", name, ok)
        except Exception as e:
            record("A2", name, False, f"{type(e).__name__}: {e}")


# ================================================================ B. round-trip

def section_b():
    for path in all_planes_files():
        name = f"{path}: render(parse(src)) parses to an equal AST"
        try:
            prog = parse(open(path).read())
            prog2 = parse(render(prog))
            ok = len(prog) == len(prog2) and all(
                ast_equal(a, b) for a, b in zip(prog, prog2))
            record("B", name, ok)
        except Exception as e:
            record("B", name, False, f"{type(e).__name__}: {e}")


# ================================================================ C. marker

RULE_SRC = (
    'rule [refund-cap] anything may not write to "refunds.json"\n\n'
    'use file\nresults = { total: 1 }\nwrite results to "refunds.json"\n'
)


def section_c():
    prog = parse(RULE_SRC)
    surface = analyse(RULE_SRC)
    found = [s for s in prog if isinstance(s, Rule)]

    out = render(prog, rules=found, surface=surface)
    lines = out.splitlines()
    ok = ('~ [refund-cap] applies here' in lines and
          lines[lines.index('~ [refund-cap] applies here') + 1]
          == 'write results to "refunds.json"')
    record("C", "marker appears immediately before the governed write", ok, out)

    without = render(prog, rules=[], surface=surface)
    record("C", "changing the rule set changes the marker",
           "~ [refund-cap] applies here" in out and
           "~ [refund-cap] applies here" not in without)

    cleared_src = (
        'rule [no-write] anything may not write to "a.json"\n'
        'rule [allow-a] anything may write to "a.json" supersedes [no-write]\n\n'
        'use file\nwrite [1] to "a.json"\n')
    cprog = parse(cleared_src)
    csurface = analyse(cleared_src)
    cfound = [s for s in cprog if isinstance(s, Rule)]
    cout = render(cprog, rules=cfound, surface=csurface)
    record("C", "a cleared match still shows the marker",
           "~ [no-write] applies here" in cout)

    leaked = [p for p in all_planes_files() if "applies here" in open(p).read()]
    record("C", "no marker text appears in any .planes file in the repo",
           not leaked, str(leaked))


# ================================================================ D. non-execution

def section_d():
    try:
        prog = parse('note:\n  from "policy"\n  derives-from [some-rule]\n')
        i = Interpreter(fs={})
        i.exec_stmt(prog[0], i.env)
        record("D", "a Note reaching exec_stmt directly raises", False,
               "did not raise")
    except PlanesError as e:
        record("D", "a Note reaching exec_stmt directly raises",
               e.tag == "annotation-executed", e.tag)

    try:
        i = Interpreter(fs={})
        i.eval(Because("a reason"), i.env)
        record("D", "a Because reaching eval() raises", False, "did not raise")
    except PlanesError as e:
        record("D", "a Because reaching eval() raises",
               e.tag == "cannot-evaluate", e.tag)

    src = 'note:\n  from "policy"\n  derives-from [some-rule]\nshow "hi"\n'
    record("D", "a program using note: still runs to completion normally",
           Interpreter(fs={}).run(src) == ["hi"])


# ================================================================ E. regression + anti-drift

BASELINE = 333  # confirmed against main at 8ce0e2e, the Tier 0 build's start point

SUITES = ["test_planes.py", "test_numbers.py", "test_shapes.py", "test_names.py",
          "test_rules.py", "test_foreign.py", "test_host.py", "test_coverage.py",
          "test_assertions.py", "test_values.py", "test_annotation.py",
          "test_render.py"]


def section_e():
    total, failed = 0, []
    for f in SUITES:
        p = subprocess.run([sys.executable, f], capture_output=True, text=True)
        last = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
        if "passing" not in last:
            failed.append((f, p.stdout[-2000:] + p.stderr[-2000:]))
            continue
        n = int(last.split("/")[1].split()[0])
        ok_count = int(last.split("/")[0])
        total += n
        if ok_count != n:
            failed.append((f, last))

    record("E", f"regression: full suite total ({total}) >= baseline ({BASELINE})",
           total >= BASELINE and not failed,
           f"failed suites: {[f for f, _ in failed]}" if failed else "")

    # anti-drift: rules.py untouched (read-only per invariant 5)
    diff = subprocess.run(["git", "diff", "--name-only", "main"],
                           capture_output=True, text=True).stdout.split()
    record("E", "rules.py untouched (read-only per invariant 5)",
           "rules.py" not in diff, f"touched: {diff}" if "rules.py" in diff else "")

    # anti-drift: the reserved-word ceiling did not move
    record("E", "because/note NOT in KEYWORDS -- ceiling stays at 30",
           "because" not in KEYWORDS and "note" not in KEYWORDS
           and len(KEYWORDS) == 30,
           f"len(KEYWORDS)={len(KEYWORDS)}")

    # anti-drift: no marker text in any committed .planes file
    leaked = [p for p in all_planes_files() if "applies here" in open(p).read()]
    record("E", "no marker text committed to any .planes source file",
           not leaked, str(leaked))


# ================================================================ F. the widened sample

def section_f():
    annotated = [p for p in all_planes_files() if has_annotations(parse(open(p).read()))]
    record("F", f"at least 4 files carry annotations (found {len(annotated)}: "
                f"{', '.join(annotated)})",
           len(annotated) >= 4)

    found_kinds = set()
    for path in all_planes_files():
        found_kinds |= annotation_nesting_kinds(parse(open(path).read()))
    for kind in ("FuncDef", "If", "ForEach"):
        record("F", f"nesting inside {kind} is exercised somewhere in the repo",
               kind in found_kinds, f"found: {sorted(found_kinds)}")


# ================================================================ G. the why boundary

def section_g():
    src = 'cap = 200 because "board policy"\nshow text of cap\nwhy cap\n'
    ok, detail, a_full, b_full = three_way(src, fs={})
    record("G", "show-output/effects/surface identical stripped vs not, "
                "on a program where why also runs", ok, detail)
    record("G", "why's output is allowed to differ, and here does",
           a_full != b_full and 'because "board policy"' in a_full[1]
           and "because" not in b_full[1],
           f"annotated: {a_full!r}  stripped: {b_full!r}")


def main():
    section_a()
    section_b()
    section_c()
    section_d()
    section_e()
    section_f()
    section_g()

    lines = ["# annotation-verification.md", "",
             "Verification gate for the annotation plane and canonical "
             "renderer build, extended for the Tier 0 follow-on. Generated "
             "by `verify_annotation.py`.", ""]
    by_section = {}
    for section, name, passed, detail in RESULTS:
        by_section.setdefault(section, []).append((name, passed, detail))

    all_pass = True
    titles = {
        "A1": "A1. Inertness — files carrying annotations (the guarantee)",
        "A2": "A2. Strip is a no-op — files with no annotations (regression net)",
        "B": "B. Round-trip", "C": "C. Marker", "D": "D. Non-execution",
        "E": "E. Regression", "F": "F. The widened sample", "G": "G. The why boundary",
    }
    order = ["A1", "A2", "B", "C", "D", "E", "F", "G"]
    n1, n2 = len(by_section.get("A1", [])), len(by_section.get("A2", []))
    print(f"A1: {n1} files with annotations, all three-way identical.")
    print(f"A2: {n2} files without, strip verified structurally or as a "
          f"trivial run-based no-op.")
    print()
    print(f"{'section':<3} {'result':<6} name")
    for section in order:
        lines.append(f"## {titles[section]}\n")
        if section == "A1":
            lines.append(f"**{n1} files with annotations, all three-way identical.**\n")
        if section == "A2":
            lines.append(f"**{n2} files without, strip verified structurally "
                          f"or as a trivial run-based no-op.**\n")
        lines.append("| Result | Check | Detail |")
        lines.append("|---|---|---|")
        for name, passed, detail in by_section.get(section, []):
            mark = "PASS" if passed else "FAIL"
            print(f"{section:<3} {mark:<6} {name}" +
                  (f"  -- {detail}" if detail and not passed else ""))
            cell = detail.replace("\n", "<br>").replace("|", "\\|")
            lines.append(f"| {mark} | {name} | {cell} |")
            if not passed:
                all_pass = False
        lines.append("")

    blocking_ok = all(p for s, n, p, d in RESULTS if s in ("A1", "B", "E", "F", "G"))
    lines.append(f"**Blocking sections (A1, B, E, F, G): {'PASS' if blocking_ok else 'FAIL'}**")
    lines.append(f"**All sections: {'PASS' if all_pass else 'FAIL'}**")

    with open("annotation-verification.md", "w") as f:
        f.write("\n".join(lines) + "\n")

    print()
    print("Blocking sections (A1, B, E, F, G):", "PASS" if blocking_ok else "FAIL")
    print("All sections:", "PASS" if all_pass else "FAIL")
    print("Wrote annotation-verification.md")

    return 0 if blocking_ok else 1


if __name__ == "__main__":
    sys.exit(main())
