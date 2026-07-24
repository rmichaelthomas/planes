#!/usr/bin/env python3
"""Verification gate for the value-model semantics build (V-Q1, V-Q5,
record literals). Runs A-E from the build prompt's §9.2 and writes
value-model-verification.md. No input from a human is required.

Exit 0 if A, B, and E all pass (the blocking set). C and D are reported
but do not block, matching §9.2's stated blocking scope — though in
practice every row here must hold for the build to be done.
"""
import json
import subprocess
import sys

from interp import Interpreter, PlanesError, why_tree
from parser import PlanesSyntaxError

RESULTS: list = []   # (section, name, passed, detail)


def record(section, name, passed, detail=""):
    RESULTS.append((section, name, passed, detail))
    return passed


def run(src, **kw):
    return Interpreter(**kw).run(src)


def val(src, name, **kw):
    i = Interpreter(**kw)
    i.run(src)
    return i.env.get(name)


def raised_tag(fn):
    try:
        fn()
        return None
    except PlanesError as e:
        return e.tag


# ================================================================ A. gate program

def section_a():
    try:
        i = Interpreter(fs={})
        out = i.run_file("gate.planes")
        ok = "matches expected" in out and "flag set" in out
        record("A", "gate.planes runs and prints both required lines", ok,
               "" if ok else f"output was: {out}")
    except Exception as e:
        record("A", "gate.planes runs and prints both required lines", False,
               f"{type(e).__name__}: {e}")


# ================================================================ B. equality table

EQUALITY_TABLE = [
    ("1 == 1.0", "true", None),
    ("0.1 + 0.2 == 0.3", "true", None),
    ('5 == "5"', None, "cannot-compare"),
    ("true == 1", None, "cannot-compare"),
    ("0 == false", None, "cannot-compare"),
    ("nothing == nothing", None, "cannot-compare"),
    ("[1,2] == [1,2]", "true", None),
    ('[1,2] == [1,"2"]', None, "cannot-compare"),
    ("[1,2] == [1,2,3]", "false", None),
    ("{a:1} == {a:1}", "true", None),
    ("{a:1} == {b:1}", None, "cannot-compare"),
]


def section_b():
    for expr, expect_val, expect_tag in EQUALITY_TABLE:
        name = f"`{expr}`"
        try:
            v = val(f"r = ({expr})", "r")
            if expect_tag is not None:
                record("B", name, False, f"expected error {expect_tag!r}, got {v.value!r}")
                continue
            got = "true" if v.value is True else "false" if v.value is False else str(v.value)
            record("B", name, got == expect_val, f"expected {expect_val}, got {got}")
        except PlanesError as e:
            if expect_tag is None:
                record("B", name, False, f"unexpected error {e.tag}: {e}")
            else:
                record("B", name, e.tag == expect_tag,
                       f"expected tag {expect_tag}, got {e.tag}")

    # is-nothing rows, separately (not a `==` expression)
    tag = raised_tag(lambda: run("x = 5\ny = 6\nz = (x is nothing)"))
    record("B", "`x is nothing` on an unset-valued x -> true",
           val("x = nothing\nb = x is nothing", "b").value is True)
    record("B", "`x is nothing` on a set value -> false",
           val("x = 5\nb = x is nothing", "b").value is False)

    # if 0 -> not-a-yes-no
    tag = raised_tag(lambda: run('if 0:\n  show "x"'))
    record("B", "`if 0:` -> not-a-yes-no", tag == "not-a-yes-no", f"got tag {tag}")


# ================================================================ C. binding (V-Q5)

def section_c():
    src = ('total = 0\n'
           'for each n in [1, 2, 3, 4, 5]:\n'
           '  total = total + n\n'
           'show text of total')
    record("C", "summing a list in a loop produces the sum",
           run(src) == ["15"])

    src = ('total = 0\n'
           'for each n in [1, 2, 3]:\n'
           '  total = total + n\n')
    tree = why_tree(val(src, "total"))
    record("C", "why on the accumulated total shows each addition",
           tree.count("+ =") == 3, tree)

    src = ('x = 100\n'
           'to bump of x:\n'
           '  x = x + 1\n'
           '  give x\n'
           'y = bump of 5\n'
           'show text of x\n'
           'show text of y')
    record("C", "a parameter named like an outer variable does not modify it",
           run(src) == ["100", "6"])

    src = ('total = 0\n'
           'for each n in [1, 2, 3]:\n'
           '  let total = n\n'
           'show text of total')
    record("C", "let inside a loop shadows and does not escape",
           run(src) == ["0"])

    src = ('x = 1\n'
           'if true:\n'
           '  x = 2\n'
           'show text of x')
    record("C", "assignment inside if still escapes",
           run(src) == ["2"])


# ================================================================ D. records

def section_d():
    record("D", "literal parses, evaluates, field-accesses",
           run('p = { first: "Ada", last: "Lovelace" }\n'
               'show p.first\nshow p.last') == ["Ada", "Lovelace"])

    record("D", "nests three deep, addresses by path",
           run('r = { a: { b: { c: 42 } } }\nshow text of r.a.b.c') == ["42"])

    dup_tag = None
    try:
        run('r = { a: 1, a: 2 }')
    except PlanesSyntaxError as e:
        dup_tag = "twice" in str(e)
    record("D", "duplicate field name is a syntax error", bool(dup_tag))

    record("D", "trailing comma accepted",
           run('r = { a: 1, b: 2, }\nshow text of r.a') == ["1"])

    record("D", "a keyword-like field name (to, from) works",
           run('r = { to: "x", from: "y" }\nshow r.to\nshow r.from') == ["x", "y"])

    i = Interpreter(fs={})
    i.run('use file\nr = { a: 1, b: "hi", c: [1, 2, 3] }\nwrite r to "out.json"')
    written = json.loads(i.fs["out.json"])
    record("D", "round-trips through write ... to",
           written == {"a": 1, "b": "hi", "c": [1, 2, 3]})


# ================================================================ E. regression + anti-drift

BASELINE = 289          # as stated in the build prompt
ACTUAL_PRE_BUILD = 309  # measured this session: the build prompt's baseline
                        # predates the prior session's test_assertions.py (20
                        # tests); 309 is what HEAD (4c0e190) actually carries.

SUITES = ["test_planes.py", "test_numbers.py", "test_shapes.py", "test_names.py",
          "test_rules.py", "test_foreign.py", "test_host.py", "test_coverage.py",
          "test_assertions.py", "test_values.py"]

INTENTIONAL_ASSERTION_CHANGES = 2  # test_shapes.py ADVERSARIAL fixtures relying
                                    # on truthy list coercion in a where/if condition


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

    record("E", f"regression: full suite total ({total}) >= baseline ({ACTUAL_PRE_BUILD}) net of {INTENTIONAL_ASSERTION_CHANGES} intentional assertion changes",
           total >= ACTUAL_PRE_BUILD and not failed,
           f"failed suites: {[f for f, _ in failed]}" if failed else "")

    # anti-drift: rules.py / shapes.py untouched by this build (read-only per scope)
    diff = subprocess.run(["git", "diff", "--name-only", "main"],
                           capture_output=True, text=True).stdout.split()
    touched_forbidden = [f for f in ("rules.py", "shapes.py") if f in diff]
    record("E", "rules.py and shapes.py untouched (read-only per scope)",
           not touched_forbidden, f"touched: {touched_forbidden}")

    # anti-drift: no governance vocabulary crept into lexer/parser/interp
    banned = ["policy", "precedence", "govern", "allow ", "deny"]
    drift = []
    for fname in ("lexer.py", "parser.py", "interp.py"):
        text = open(fname).read().lower()
        for word in banned:
            if word in text:
                drift.append(f"{word!r} in {fname}")
    record("E", "no governance vocabulary in lexer/parser/interp", not drift, str(drift))

    # anti-drift: truthy is gone, not just unused
    truthy_hits = subprocess.run(
        ["grep", "-rn", "truthy", "lexer.py", "parser.py", "interp.py"],
        capture_output=True, text=True).stdout.strip()
    record("E", "truthy is unreachable (deleted, not merely unused)",
           truthy_hits == "", truthy_hits)


def main():
    section_a()
    section_b()
    section_c()
    section_d()
    section_e()

    lines = ["# value-model-verification.md", "",
             "Verification gate for the value-model semantics build "
             "(V-Q1, V-Q5, record literals). Generated by `verify_values.py`.", ""]
    by_section = {}
    for section, name, passed, detail in RESULTS:
        by_section.setdefault(section, []).append((name, passed, detail))

    all_pass = True
    titles = {"A": "A. Gate program", "B": "B. Equality table",
              "C": "C. Binding (V-Q5)", "D": "D. Records", "E": "E. Regression"}
    print(f"{'section':<3} {'result':<6} name")
    for section in "ABCDE":
        lines.append(f"## {titles[section]}\n")
        lines.append("| Result | Check | Detail |")
        lines.append("|---|---|---|")
        for name, passed, detail in by_section.get(section, []):
            mark = "PASS" if passed else "FAIL"
            print(f"{section:<3} {mark:<6} {name}" + (f"  -- {detail}" if detail and not passed else ""))
            cell = detail.replace("\n", "<br>").replace("|", "\\|")
            lines.append(f"| {mark} | {name} | {cell} |")
            if not passed:
                all_pass = False
        lines.append("")

    blocking_ok = all(p for s, n, p, d in RESULTS if s in ("A", "B", "E"))
    lines.append(f"**Blocking sections (A, B, E): {'PASS' if blocking_ok else 'FAIL'}**")
    lines.append(f"**All sections: {'PASS' if all_pass else 'FAIL'}**")

    with open("value-model-verification.md", "w") as f:
        f.write("\n".join(lines) + "\n")

    print()
    print("Blocking sections (A, B, E):", "PASS" if blocking_ok else "FAIL")
    print("All sections:", "PASS" if all_pass else "FAIL")
    print("Wrote value-model-verification.md")

    return 0 if blocking_ok else 1


if __name__ == "__main__":
    sys.exit(main())
