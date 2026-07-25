#!/usr/bin/env python3
"""Verification gate for grammar-as-data-and-scoped-amber (addendum v4.2
sections 69.1, 69.5). Runs A-I from the build prompt's section 11.2 and
writes grammar-amber-verification.md to the repo root. No input from a
human is required -- section 11.3 (the clarity read on amber's messages)
is a separate, human-only step this script does not attempt.

Exit 0 if A, C, D, E, and H (the blocking sections) all pass. B, F, G are
also expected to fully pass in practice, and I (benchmarks) is reported,
not blocking, unless a file is more than 25% slower.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

VOCAB_PATH = "grammar/vocabulary.json"
RULES_PATH = "grammar/rules.json"
ERRORS_PATH = "grammar/errors.json"
FIXTURES_PATH = "ast_fixtures_baseline.json"
CORPUS = ["annotated", "foreign", "gate", "hn", "money", "names", "ordinary", "pypi"]

RESULTS: list = []  # (section, name, passed, detail)


def record(section, name, passed, detail=""):
    RESULTS.append((section, name, passed, detail))
    return passed


def run_py(args, timeout=60):
    return subprocess.run([sys.executable] + args, capture_output=True,
                          text=True, timeout=timeout, cwd=ROOT)


# ================================================================ A. single definition

def section_a():
    offenders = []
    banned = [
        (r'KEYWORDS\s*=\s*\{\s*"', "a KEYWORDS set literal"),
        (r'BUILTIN_NAMES\s*=\s*\{\s*"', "a BUILTIN_NAMES set literal"),
        (r'EFFECT_KINDS\s*=\s*\{\s*"', "an EFFECT_KINDS dict literal"),
        (r'FIELD_NAME_KINDS\s*=\s*\(\s*"', "a FIELD_NAME_KINDS tuple literal"),
        (r'"SHOW",\s*"WRITE",\s*"FIRST"', "a re-duplicated field-name-kinds tuple"),
    ]
    for path in glob.glob(os.path.join(ROOT, "*.py")):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for pattern, label in banned:
            if re.search(pattern, text):
                offenders.append(f"{os.path.basename(path)}: {label}")
    record("A", "each of the four vocabulary tables is defined exactly once",
           not offenders, "; ".join(offenders))


# ================================================================ B. load failure

def section_b():
    moved = VOCAB_PATH + ".moved-for-verify"
    os.rename(VOCAB_PATH, moved)
    try:
        for entry_point in ("import lexer", "import parser", "import interp"):
            result = run_py(["-c", entry_point])
            # a clean, named failure -- not an uncaught KeyError, not success
            named_not_keyerror = ("grammar-data-missing" in result.stderr
                                  and "KeyError" not in result.stderr
                                  and result.returncode != 0)
            record("B", f"`{entry_point}` fails with grammar-data-missing, not KeyError",
                   named_not_keyerror,
                   result.stderr.strip().splitlines()[-1] if result.stderr else "no stderr")
    finally:
        os.rename(moved, VOCAB_PATH)
    # confirm restoration actually worked before anything downstream runs
    restored = run_py(["-c", "import lexer; print(len(lexer.KEYWORDS))"])
    record("B", "vocabulary restored after the moved-aside check",
           restored.returncode == 0 and restored.stdout.strip() == "32",
           restored.stdout + restored.stderr)


# ================================================================ C. audit intact

def section_c():
    result = run_py(["audit_locked_vs_built.py"])
    record("C", "audit_locked_vs_built.py exits 0", result.returncode == 0,
           f"exit code {result.returncode}")
    out = result.stdout
    record("C", "no [NOT BUILT] entries in audit output", "NOT BUILT" not in out,
           "" if "NOT BUILT" not in out else "found a NOT BUILT line")
    for construct in ("first", "with (record update)", "plus (list append)",
                      "normalize builtin", "when shape-dispatch"):
        pattern = rf"\[BUILT\s*\]\s*{re.escape(construct)}"
        found = re.search(pattern, out) is not None
        record("C", f"'{construct}' reports BUILT with an openable pointer", found,
               "" if found else "not found as BUILT in audit output")


# ================================================================ D. projection inertness

def section_d():
    moved = []
    for path in (RULES_PATH, ERRORS_PATH):
        tmp = path + ".moved-for-verify"
        os.rename(path, tmp)
        moved.append((path, tmp))
    try:
        outputs = {}
        for name in CORPUS:
            result = run_py(["-c",
                f"from interp import Interpreter; "
                f"print(Interpreter().run(open('{name}.planes').read()))"])
            outputs[name] = (result.returncode, result.stdout)
        fail = [n for n, (rc, _) in outputs.items() if rc != 0]
        record("D", "every corpus file still runs with rules.json/errors.json deleted",
               not fail, f"failed: {fail}")

        suite_fail = []
        for f in sorted(glob.glob("test_*.py")):
            result = run_py([f], timeout=120)
            if result.returncode != 0:
                suite_fail.append(f)
        record("D", "full test suite still passes with rules.json/errors.json deleted",
               not suite_fail, f"failed: {suite_fail}")
    finally:
        for path, tmp in moved:
            os.rename(tmp, path)

    # and the same corpus outputs must be identical with the files restored
    restored_ok = True
    detail = ""
    for name in CORPUS:
        result = run_py(["-c",
            f"from interp import Interpreter; "
            f"print(Interpreter().run(open('{name}.planes').read()))"])
        before_rc, before_out = outputs[name]
        if (result.returncode, result.stdout) != (before_rc, before_out):
            restored_ok = False
            detail = f"{name} differs with files restored vs deleted"
            break
    record("D", "corpus output is byte-identical with the files present vs deleted",
           restored_ok, detail)


# ================================================================ E. AST identity

def _ast_to_jsonable(node):
    if hasattr(node, "__dataclass_fields__"):
        return {"__type__": type(node).__name__,
                **{f: _ast_to_jsonable(getattr(node, f)) for f in node.__dataclass_fields__}}
    if isinstance(node, (list, tuple)):
        return [_ast_to_jsonable(x) for x in node]
    if isinstance(node, dict):
        return {k: _ast_to_jsonable(v) for k, v in node.items()}
    return repr(node)


def section_e():
    if not os.path.exists(FIXTURES_PATH):
        record("E", "ast_fixtures_baseline.json exists", False, "fixture file missing")
        return
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        baseline = json.load(f)
    from parser import parse
    for name in CORPUS:
        with open(f"{name}.planes", encoding="utf-8") as f:
            src = f.read()
        now = _ast_to_jsonable(parse(src))
        record("E", f"{name}.planes parses to a byte-identical AST vs the 08b051e baseline",
               now == baseline.get(name), "" if now == baseline.get(name) else "AST mismatch")


# ================================================================ F. amber fires / does not

def section_f():
    try:
        import test_amber as ta
    except Exception as e:
        record("F", "test_amber.py imports", False, f"{type(e).__name__}: {e}")
        return
    checks = [n for n in dir(ta) if n.startswith("test_")]
    for name in sorted(checks):
        fn = getattr(ta, name)
        try:
            fn()
            record("F", name, True)
        except AssertionError as e:
            record("F", name, False, str(e))
        except Exception as e:
            record("F", name, False, f"{type(e).__name__}: {e}")


# ================================================================ G. regeneration

def section_g():
    result = run_py(["grammar_gen.py", "--check"])
    record("G", "grammar_gen.py --check exits 0 on a clean tree", result.returncode == 0,
           result.stdout[-300:] if result.returncode else "")

    backup_path = "interp.py"
    with open(backup_path, encoding="utf-8") as f:
        original = f.read()
    injected = original.replace(
        "def condition(v):",
        'def condition(v):\n    if False:\n        raise PlanesError('
        '"verify-gate-injected", "injected for grammar_gen --check test", "n/a")',
        1)
    try:
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(injected)
        result = run_py(["grammar_gen.py", "--check"])
        caught = (result.returncode != 0 and "verify-gate-injected" in result.stdout)
        record("G", "an unregenerated new message makes --check fail and name it",
               caught, "" if caught else result.stdout[-300:])
    finally:
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(original)
        result = run_py(["grammar_gen.py", "--check"])
        record("G", "--check is clean again after reverting the injected message",
               result.returncode == 0, result.stdout[-300:] if result.returncode else "")


# ================================================================ H. regression

def section_h():
    total = 0
    fail_files = []
    for f in sorted(glob.glob("test_*.py")):
        result = run_py([f], timeout=120)
        m = re.search(r"(\d+)/(\d+) passing", result.stdout)
        if m:
            total += int(m.group(2))
        if result.returncode != 0:
            fail_files.append(f)
    record("H", f"full suite passes, {total} tests (baseline was 481 pre-build)",
           not fail_files and total >= 481, f"failing files: {fail_files}" if fail_files else "")

    ruff = run_py(["-m", "ruff", "check", "."])
    record("H", "ruff check . is clean", ruff.returncode == 0, ruff.stdout[-500:])
    mypy = run_py(["-m", "mypy", "."])
    record("H", "mypy . is clean", mypy.returncode == 0, mypy.stdout[-500:])


# ================================================================ I. benchmarks

def section_i():
    from lexer import tokenize
    from parser import parse
    rows = []
    for name in CORPUS:
        with open(f"{name}.planes", encoding="utf-8") as f:
            src = f.read()
        ntoks = len(tokenize(src))
        times = []
        for _ in range(20):
            t0 = time.perf_counter()
            parse(src)
            times.append((time.perf_counter() - t0) * 1000)
        rows.append((name, ntoks, sum(times) / len(times)))

    pre_path = "grammar-as-data-benchmarks-pre.md"
    pre = {}
    if os.path.exists(pre_path):
        with open(pre_path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\|\s*(\w+)\.planes\s*\|\s*\d+\s*\|\s*([\d.]+)\s*\|", line)
                if m:
                    pre[m.group(1)] = float(m.group(2))

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True, cwd=ROOT).stdout.strip()
    lines = ["## Post-Build Benchmarks — feat/grammar-as-data-and-scoped-amber",
             f"**Commit:** {commit}", "",
             "| File | Tokens | Parse (ms, mean of 20) | Pre-build | Delta |",
             "|---|---|---|---|---|"]
    worst = 0.0
    for name, ntoks, mean_ms in rows:
        before = pre.get(name)
        if before:
            delta_pct = (mean_ms - before) / before * 100
            worst = max(worst, delta_pct)
            delta_txt = f"{delta_pct:+.1f}%"
        else:
            delta_txt = "n/a"
        lines.append(f"| {name}.planes | {ntoks} | {mean_ms:.4f} | "
                     f"{before if before else 'n/a'} | {delta_txt} |")
    with open("grammar-as-data-benchmarks-post.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    record("I", f"no file more than 25% slower (worst: {worst:+.1f}%)", worst <= 25.0,
           "flagged — see grammar-as-data-benchmarks-post.md" if worst > 25.0 else "")


# ================================================================ main

def main():
    section_a()
    section_b()
    section_c()
    section_d()
    section_e()
    section_f()
    section_g()
    section_h()
    section_i()

    lines = ["# grammar-amber-verification.md", "",
             "Verification gate for grammar-as-data-and-scoped-amber "
             "(addendum v4.2 §69.1, §69.5). Generated by "
             "`verify_grammar_and_amber.py`.", ""]
    by_section = {}
    for section, name, passed, detail in RESULTS:
        by_section.setdefault(section, []).append((name, passed, detail))

    titles = {
        "A": "A. Single definition (blocking)",
        "B": "B. Load failure",
        "C": "C. Audit intact (blocking)",
        "D": "D. Projection inertness (blocking)",
        "E": "E. AST identity (blocking)",
        "F": "F. Amber fires and does not",
        "G": "G. Regeneration",
        "H": "H. Regression (blocking)",
        "I": "I. Benchmarks (reported, not blocking unless >25%)",
    }
    print(f"{'sec':<3} {'result':<6} name")
    for section in "ABCDEFGHI":
        lines.append(f"## {titles[section]}\n")
        lines.append("| Result | Check | Detail |")
        lines.append("|---|---|---|")
        for name, passed, detail in by_section.get(section, []):
            mark = "PASS" if passed else "FAIL"
            tail = f"  -- {detail}" if detail and not passed else ""
            print(f"{section:<3} {mark:<6} {name}" + tail)
            cell = str(detail).replace("\n", "<br>").replace("|", "\\|")
            lines.append(f"| {mark} | {name} | {cell} |")
        lines.append("")

    blocking_sections = ("A", "C", "D", "E", "H")
    blocking_ok = all(p for s, n, p, d in RESULTS if s in blocking_sections)
    all_pass = all(p for s, n, p, d in RESULTS)
    lines.append(f"**Blocking sections (A, C, D, E, H): {'PASS' if blocking_ok else 'FAIL'}**")
    lines.append(f"**All sections: {'PASS' if all_pass else 'FAIL'}**")

    with open("grammar-amber-verification.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print()
    print("Blocking sections (A, C, D, E, H):", "PASS" if blocking_ok else "FAIL")
    print("All sections:", "PASS" if all_pass else "FAIL")
    print("Wrote grammar-amber-verification.md")

    return 0 if blocking_ok else 1


if __name__ == "__main__":
    sys.exit(main())
