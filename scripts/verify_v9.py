#!/usr/bin/env python3
"""Verification gate for planes v9.0 (Tier 2 language, errors as records,
the record plane). Runs A-D from the build prompt's N+3.2 and writes
v9-verification.md to the repo root. No input from a human is required.

Exit 0 if C and D (the blocking sections) both pass. A and B are reported
but do not block, matching N+3.2's stated blocking scope -- though in
practice every row here must hold for the build to be done.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from interp import Interpreter, PlanesError, apply_op  # noqa: E402

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


# ================================================================ A. text laws

def section_a():
    tag = raised_tag(lambda: apply_op("+", "a", 1))
    record("A", '`"a" + 1` raises cannot-combine', tag == "cannot-combine",
           f"got tag {tag}")

    record("A", '`"a" + text of 1` == "a1"',
           run('x = "a" + text of 1\nshow x') == ["a1"])

    v = val('x = first 2 of "hello"', "x").value
    record("A", '`first 2 of "hello"` == "he" and is a string',
           v == "he" and isinstance(v, str), f"got {v!r} ({type(v).__name__})")

    record("A", 'count of "héllo" == 5',
           val('x = count of "héllo"', "x").value.as_int() == 5)

    # explicit escapes, not literal source characters -- a literal
    # pair here risks silent NFC-normalization by an intermediate
    # tool, which would make both strings identical and this whole
    # check vacuous (caught exactly that way while writing this file).
    combining, precomposed = 'é', 'é'
    unequal = val(f'x = ("{combining}" == "{precomposed}")', "x").value is False
    equal_after = val(
        f'x = (normalize of "{combining}" == normalize of "{precomposed}")',
        "x").value is True
    record("A", "one-codepoint vs two-codepoint é are unequal", unequal,
           f"combining has {len(combining)} code points, "
           f"precomposed has {len(precomposed)}")
    record("A", "normalize of both sides makes them equal", equal_after)


# ================================================================ B. errors

def section_b():
    def boom(url):
        raise RuntimeError("connection refused")

    src = ('use http\n'
           'x = ask "https://example.com/a.json"\n'
           '  or fail as err:\n'
           '    show err.tag\n'
           '    show err.detail\n')
    out = run(src, http=boom)
    record("B", "a caught error is a record with tag and detail",
           out == ["err", "connection refused"], f"got {out}")

    # No `when`/pattern-match construct exists anywhere in this repo
    # (confirmed by exhaustive grep before this build) -- discrimination
    # reuses the language's existing if/field-access machinery instead,
    # per the resolved design (v9.0 A.5).
    src2 = ('use http\n'
           'x = ask "https://example.com/a.json"\n'
           '  or fail as err:\n'
           '    if err.tag == "err":\n'
           '      show "matched"\n'
           '    else:\n'
           '      show "unreached"\n')
    out2 = run(src2, http=boom)
    record("B", 'caught-error record selects via if err.tag == "..." '
                "(no when/pattern-match construct exists in this repo)",
           out2 == ["matched"], f"got {out2}")

    tag, path = None, None
    try:
        run('x = ([1, [2, "3"]] == [1, [2, 3]])')
    except PlanesError as e:
        tag, path = e.tag, e.path
    record("B", '[1,[2,"3"]] == [1,[2,3]] raises cannot-compare with path [1,1]',
           tag == "cannot-compare" and path == [1, 1],
           f"tag={tag} path={path}")


# ================================================================ C. record plane inertness

def section_c():
    import test_record as tr

    samples = [
        ("pure", tr.PURE, {}),
        ("network", tr.NETWORK, {"http": lambda u: '"hi"'}),
        ("file", tr.FILE, {}),
        ("foreign", tr.FOREIGN, {}),
        ("mixed", tr.MIXED, {"http": lambda u: '"hi"'}),
        ("or-fail handler, success", tr.OR_FAIL_HANDLER, {"http": lambda u: '"hi"'}),
        ("or-fail handler, failure", tr.OR_FAIL_HANDLER,
         {"http": lambda u: (_ for _ in ()).throw(RuntimeError("down"))}),
    ]
    for label, src, kw in samples:
        try:
            tr.assert_recording_inert(src, **kw)
            record("C", f"recording OFF/ON byte-identical -- {label}", True)
        except AssertionError as e:
            record("C", f"recording OFF/ON byte-identical -- {label}", False, str(e))


# ================================================================ D. retirement guard (blocking)

def section_d():
    hits = []
    targets = list(ROOT.glob("*.py")) + [ROOT / "README.md"]
    for path in targets:
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"\bShapes\b", line):
                hits.append(f"{path.name}:{i}")
    record("D", 'grep -rn "\\bShapes\\b" *.py README.md returns nothing',
           not hits, f"hits: {hits}")


def main():
    section_a()
    section_b()
    section_c()
    section_d()

    lines = ["# v9-verification.md", "",
             "Verification gate for planes v9.0 (Tier 2 language, errors as "
             "records, the record plane). Generated by `scripts/verify_v9.py`.", ""]
    by_section = {}
    for section, name, passed, detail in RESULTS:
        by_section.setdefault(section, []).append((name, passed, detail))

    titles = {"A": "A. Text laws", "B": "B. Errors",
              "C": "C. Record plane inertness (blocking)",
              "D": "D. Retirement guard (blocking)"}
    print(f"{'section':<3} {'result':<6} name")
    for section in "ABCD":
        lines.append(f"## {titles[section]}\n")
        lines.append("| Result | Check | Detail |")
        lines.append("|---|---|---|")
        for name, passed, detail in by_section.get(section, []):
            mark = "PASS" if passed else "FAIL"
            tail = f"  -- {detail}" if detail and not passed else ""
            print(f"{section:<3} {mark:<6} {name}" + tail)
            cell = detail.replace("\n", "<br>").replace("|", "\\|")
            lines.append(f"| {mark} | {name} | {cell} |")
        lines.append("")

    blocking_ok = all(p for s, n, p, d in RESULTS if s in ("C", "D"))
    all_pass = all(p for s, n, p, d in RESULTS)
    lines.append(f"**Blocking sections (C, D): {'PASS' if blocking_ok else 'FAIL'}**")
    lines.append(f"**All sections: {'PASS' if all_pass else 'FAIL'}**")

    (ROOT / "v9-verification.md").write_text("\n".join(lines) + "\n")

    print()
    print("Blocking sections (C, D):", "PASS" if blocking_ok else "FAIL")
    print("All sections:", "PASS" if all_pass else "FAIL")
    print("Wrote v9-verification.md")

    return 0 if blocking_ok else 1


if __name__ == "__main__":
    sys.exit(main())
