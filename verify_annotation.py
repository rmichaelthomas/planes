#!/usr/bin/env python3
"""Verification gate for the annotation plane and canonical renderer build.
Runs A-E from the build prompt's §10.2 and writes annotation-verification.md.
No input from a human is required.

Exit 0 if A, B, and E all pass (the blocking set, per §10.2's "Blocking:
any failure in A, B, or E stops the PR"). C and D are reported but do not
block, though in practice every row here must hold for the build to be done.
"""
import glob
import json
import subprocess
import sys

from interp import Interpreter, PlanesError
from lexer import KEYWORDS, Because, Rule
from parser import parse
from render import ast_equal, render, strip_annotations
from shapes import analyse

RESULTS: list = []   # (section, name, passed, detail)


def record(section, name, passed, detail=""):
    RESULTS.append((section, name, passed, detail))
    return passed


# ================================================================ fixtures

STORIES = {
    1: {"title": "Rust 2.0 released",       "score": 450},
    2: {"title": "Why Go is fine",          "score": 300},
    3: {"title": "Rewriting grep in Rust",  "score": 210},
    4: {"title": "A rust postmortem",       "score": 150},
}


def stub_http(url):
    if "topstories" in url:
        return json.dumps(list(STORIES.keys()))
    if "pypi.org" in url:
        name = url.split("/pypi/")[1].split("/json")[0]
        return json.dumps({"info": {
            "name": name,
            "summary": f"{name} does something useful and interesting"}})
    sid = int(url.split("/item/")[1].split(".json")[0])
    return json.dumps(STORIES[sid])


FIXTURE_KWARGS = {"hn.planes": {"http": stub_http}, "pypi.planes": {"http": stub_http}}
NOT_STANDALONE_PARSEABLE = {"demo/app/net.planes"}


def standalone_files():
    return sorted(glob.glob("*.planes"))


def every_planes_file():
    paths = sorted(glob.glob("*.planes")) + \
        sorted(glob.glob("demo/**/*.planes", recursive=True))
    return [p for p in paths if p not in NOT_STANDALONE_PARSEABLE]


def run_and_capture(src, **kw):
    kw.setdefault("fs", {})
    i = Interpreter(**kw)
    output = i.run(src)
    surface = analyse(src)
    return list(output), list(i.effects), [str(e) for e in surface.declared]


# ================================================================ A. inertness

def section_a():
    for path in standalone_files():
        src = open(path).read()
        kw = FIXTURE_KWARGS.get(path, {})
        name = f"{path}: annotated vs stripped are three-way identical"
        try:
            prog = parse(src)
            stripped_src = render(strip_annotations(prog))
            a_out, a_eff, a_surf = run_and_capture(src, **kw)
            b_out, b_eff, b_surf = run_and_capture(stripped_src, **kw)
            ok = a_out == b_out and a_eff == b_eff and a_surf == b_surf
            detail = "" if ok else (
                f"output {a_out!r} vs {b_out!r}; "
                f"effects {a_eff!r} vs {b_eff!r}; "
                f"surface {a_surf!r} vs {b_surf!r}")
            record("A", name, ok, detail)
        except Exception as e:
            record("A", name, False, f"{type(e).__name__}: {e}")

    # structural strip-is-a-no-op check, across every file including demo/
    for path in every_planes_file():
        if path == "annotated.planes":
            continue
        name = f"{path}: strip is structurally a no-op (no annotations to begin with)"
        try:
            prog = parse(open(path).read())
            stripped = strip_annotations(prog)
            ok = len(prog) == len(stripped) and all(
                ast_equal(a, b) for a, b in zip(prog, stripped))
            record("A", name, ok)
        except Exception as e:
            record("A", name, False, f"{type(e).__name__}: {e}")


# ================================================================ B. round-trip

def section_b():
    for path in every_planes_file():
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

    leaked = [p for p in every_planes_file() + ["annotated.planes"]
              if "applies here" in open(p).read()]
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

BASELINE = 333  # confirmed this session against main at 8ce0e2e

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
    leaked = [p for p in every_planes_file() + ["annotated.planes"]
              if "applies here" in open(p).read()]
    record("E", "no marker text committed to any .planes source file",
           not leaked, str(leaked))


def main():
    section_a()
    section_b()
    section_c()
    section_d()
    section_e()

    lines = ["# annotation-verification.md", "",
             "Verification gate for the annotation plane and canonical "
             "renderer build. Generated by `verify_annotation.py`.", ""]
    by_section = {}
    for section, name, passed, detail in RESULTS:
        by_section.setdefault(section, []).append((name, passed, detail))

    all_pass = True
    titles = {"A": "A. Inertness", "B": "B. Round-trip", "C": "C. Marker",
              "D": "D. Non-execution", "E": "E. Regression"}
    print(f"{'section':<3} {'result':<6} name")
    for section in "ABCDE":
        lines.append(f"## {titles[section]}\n")
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

    blocking_ok = all(p for s, n, p, d in RESULTS if s in ("A", "B", "E"))
    lines.append(f"**Blocking sections (A, B, E): {'PASS' if blocking_ok else 'FAIL'}**")
    lines.append(f"**All sections: {'PASS' if all_pass else 'FAIL'}**")

    with open("annotation-verification.md", "w") as f:
        f.write("\n".join(lines) + "\n")

    print()
    print("Blocking sections (A, B, E):", "PASS" if blocking_ok else "FAIL")
    print("All sections:", "PASS" if all_pass else "FAIL")
    print("Wrote annotation-verification.md")

    return 0 if blocking_ok else 1


if __name__ == "__main__":
    sys.exit(main())
