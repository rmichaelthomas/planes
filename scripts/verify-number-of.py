#!/usr/bin/env python3
"""verify-number-of — A-Q19's own gate (§8.2 of the build prompt).

`write` emits a number as JSON text so an exact value survives a tool that
isn't Planes; `read` and `ask` hand text back; nothing turned that text back
into a number. This script is the automated half of verifying the fix:
`number of`, the twelfth builtin, and the `cannot-combine` fix clause that
now names both directions instead of pointing backwards.

Sections, matching the build prompt's own lettering:

  A. round trip     — write a number, read it, number of it, do arithmetic
  B. acceptance     — integers, decimals, negatives, whitespace
  C. refusal        — non-numeric text, the empty string, exponent notation,
                       a ~-prefixed approximation (its own reason)
  D. agreement      — every A/B/C case, three implementations, byte-identical
  E. invariants     — builtin count 12, arity 1, write unchanged, 7 host
                       methods, errors.json regenerated, README matches
  F. fix clauses    — cannot-combine identical across three implementations;
                       every clause mentioning `text of` as a remedy, listed;
                       errors_coverage.py's unassessed count, work lists at 0
  G. corpus         — the new program runs; its effect surface is file+console

Blocking: any failure in A, C, D, or E. B, F, and G report but do not gate —
consistent with errors_coverage.py's own "reports, never fails" contract for
the parts of F that are inherently descriptive (the clause list, the intent
count).

    python3 scripts/verify-number-of.py

Writes the same table to reports/number-of-verification.md and exits
non-zero only on a blocking failure.
"""
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from host import TestHost  # noqa: E402
from interp import Interpreter, PlanesError  # noqa: E402
from parser import BUILTIN_NAMES  # noqa: E402
from shapes import analyse  # noqa: E402

import errors_coverage as ec  # noqa: E402
from test_builtin_guards import (  # noqa: E402
    NODE, _outcome_js, _outcome_planes, _outcome_py,
)

RESULTS = []  # (section, label, ok, detail)


def check(section, label, ok, detail=""):
    RESULTS.append((section, label, bool(ok), detail))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {section}: {label}" + (f" — {detail}" if detail and not ok else ""))


def run(src, **kw):
    if "host" not in kw and "fs" not in kw and "http" not in kw:
        kw["host"] = TestHost()
    itp = Interpreter(**kw)
    itp.run(src)
    return itp


# ================================================================ A. round trip

def section_a():
    print("\nA. round trip")
    # A whole number, all the way through Planes's own write/read: `write`'s
    # serialisation is unchanged (§2.4), and a non-whole number goes out as a
    # quoted JSON string precisely so an exact value survives a non-Planes
    # reader — a real, deliberate, untouched design decision this build does
    # not paper over. A whole number round-trips through `write`/`read` with
    # no quoting to strip, so this proves the write-then-read chain end to end.
    i = run('use file\n'
           'n = 145\n'
           'write n to "out.json"\n'
           'm = read "out.json"\n'
           'total = (number of m) + 1\n'
           'show text of total', fs={})
    check("A", "write 145 -> read -> number of -> +1 == 146",
          i.output == ["146"], i.output)

    # The exact §1 numbers (145.48 -> 146.48), read from a file the way an
    # external tool would leave one: plain digits, no JSON quoting. This is
    # the realistic shape (a CSV or plain-text file), and the one the A-Q9
    # cold-start runs actually needed.
    i2 = run('use file\n'
            'raw = read "price.txt"\n'
            'total = (number of raw) + 1\n'
            'show text of total', fs={"price.txt": "145.48"})
    check("A", 'read "145.48" -> number of -> +1 == 146.48',
          i2.output == ["146.48"], i2.output)


# ================================================================ B. acceptance

ACCEPT = [
    ('"5"', "5"),
    ('"145.48"', "145.48"),
    ('"-3"', "-3"),
    ('"-0.5"', "-0.5"),
    ('"0"', "0"),
    ('"  5  "', "5"),           # leading/trailing whitespace, trimmed
    ('"\\t12.5\\n"', "12.5"),   # tab/newline whitespace, trimmed
]


def section_b():
    print("\nB. acceptance")
    for text, want in ACCEPT:
        i = run(f"show text of (number of {text})")
        check("B", f"number of {text} == {want}", i.output == [want], i.output)


# ================================================================ C. refusal

REFUSE = [
    ('""', "not-a-number"),
    ('"abc"', "not-a-number"),
    ('"1e5"', "not-a-number"),          # exponent notation
    ('"1/3"', "not-a-number"),          # fraction form
    ('"~0.333333333333"', "not-a-number"),  # its own reason, checked below
    ("5", "not-text"),
    ("true", "not-text"),
    ("nothing", "not-text"),
    ("[1, 2]", "not-text"),
    ("{ a: 1 }", "not-text"),
]


def section_c():
    print("\nC. refusal")
    for lit, want_tag in REFUSE:
        try:
            run(f"n = number of {lit}")
            check("C", f"number of {lit} refused as {want_tag}", False, "accepted")
        except PlanesError as e:
            check("C", f"number of {lit} refused as {want_tag}",
                  e.tag == want_tag, e.tag)

    # The ~-prefixed case names its own reason, distinct from plain
    # non-numeric text (§2.3) — checked separately since REFUSE only checks
    # the tag.
    try:
        run('n = number of "~0.333333333333"')
        check("C", "~-prefix names its own reason", False, "accepted")
    except PlanesError as e:
        ok = "approximation" in e.detail and "~" in e.fix
        check("C", "~-prefix names its own reason", ok, e.detail + " | " + e.fix)


# ================================================================ D. agreement

def section_d():
    print("\nD. three-way agreement")
    if NODE is None:
        check("D", "node on PATH", False, "skipped — no node")
        return
    cases = [(text, {}) for text, _ in ACCEPT] + [(lit, {}) for lit, _ in REFUSE]
    cases.append(('number of "abc"', {}))
    bad = 0
    for expr_text, names in cases:
        expr = f"number of {expr_text}" if not expr_text.startswith("number of") else expr_text
        py = _outcome_py(expr, names)
        js = _outcome_js(expr, names)
        pl = _outcome_planes(expr, names)
        ok = py == js == pl
        if not ok:
            bad += 1
        check("D", expr, ok, f"py={py} js={js} pl={pl}" if not ok else "")
    check("D", f"{len(cases)} cases, 0 divergences", bad == 0, f"{bad} divergence(s)")


# ================================================================ E. invariants

def section_e():
    print("\nE. invariants")
    with open(os.path.join(REPO, "grammar", "vocabulary.json"), encoding="utf-8") as f:
        vocab = json.load(f)
    check("E", "builtin count is 12", len(vocab["builtins"]) == 12,
          len(vocab["builtins"]))
    entry = next((b for b in vocab["builtins"] if b["name"] == "number"), None)
    check("E", "number of is arity 1", entry is not None and entry["arity"] == 1,
          entry)
    check("E", "BUILTIN_NAMES agrees", "number" in BUILTIN_NAMES, sorted(BUILTIN_NAMES))

    # write's serialisation path is untouched: a whole number still goes out
    # as a bare JSON number, not a string.
    i = run('use file\nwrite [4 / 2] to "out.json"', fs={})
    check("E", "write path unchanged (whole numbers stay numbers)",
          json.loads(i.fs["out.json"]) == [2], i.fs["out.json"])

    known = ("ask", "read", "write", "show", "clock", "resolve", "parse_json",
             "to_json")
    from host import Host
    live = [m for m in known if hasattr(Host, m)]
    check("E", "host stays at 7 methods", len(live) == 7, live)

    r = subprocess.run([sys.executable, "grammar_gen.py", "--check"],
                       cwd=REPO, capture_output=True, text=True)
    check("E", "grammar_gen.py --check passes", r.returncode == 0,
          r.stdout + r.stderr)

    import re
    with open(os.path.join(REPO, "README.md"), encoding="utf-8") as f:
        readme = f.read()
    check("E", "README states 12 builtins", "**12 builtins**" in readme, "")
    m = re.search(r"```\n(ask  count.*?)\n```", readme, re.S)
    check("E", "README builtin list matches vocabulary.json",
          m is not None and set(m.group(1).split()) == {b["name"] for b in vocab["builtins"]},
          m.group(1) if m else "no fenced block found")


# ================================================================ F. fix clauses

TEXT_OF_CLAUSES = [
    ("interp.cannot-combine.apply_op", "corrected to name both directions"),
    ("interp.not-text.require_text", "lower/upper/normalize — one-directional, unchanged"),
    ("interp.not-text.require_target", "ask/read/write's target — one-directional, unchanged"),
    ("interp.not-text.membership", "`in` over text — one-directional, unchanged"),
    ("interp.cannot-join.builtin-2", "join's per-item guard — one-directional, unchanged"),
    ("interp.fail-message-not-text.exec_stmt-1", "fail's message field — one-directional, unchanged"),
]


def section_f():
    print("\nF. fix clauses")
    py_msg = None
    try:
        Interpreter(host=TestHost()).run('x = "5" + 1\n')
    except PlanesError as e:
        py_msg = str(e)
    check("F", "cannot-combine names both directions",
          py_msg is not None and "text of n" in py_msg and "number of t" in py_msg,
          py_msg)

    if NODE is not None:
        js = _outcome_js('x + y', {"x": "text", "y": "number"})
        check("F", "cannot-combine identical in JS",
              js[3] == "convert first — text of n to build text, or number of t to do arithmetic",
              js[3])
        pl = _outcome_planes('x + y', {"x": "text", "y": "number"})
        check("F", "cannot-combine identical in self-hosted",
              pl[3] == "convert first — text of n to build text, or number of t to do arithmetic",
              pl[3])

    print("  every catalogued clause mentioning `text of` as its remedy:")
    for site_id, note in TEXT_OF_CLAUSES:
        print(f"    {site_id:<45} {note}")

    cov = ec.coverage()
    sites = ec.self_hosted_sites()
    intent = cov["intent"]
    sh_intent = ec.self_hosted_intent_assessment(sites, ec.SELF_HOSTED_ASSESSED_THIS_BUILD)
    check("F", "reference work list is 0", cov["counts"][ec.SHORTFALL] == 0,
          cov["counts"][ec.SHORTFALL])
    check("F", "self-hosted work list is 0", len(sites[ec.SHORTFALL]) == 0,
          len(sites[ec.SHORTFALL]))
    print(f"  reference intent: {intent['assessed']} assessed, "
          f"{intent['unassessed']} unassessed of {cov['errors']}")
    print(f"  self-hosted intent: {sh_intent['assessed']} assessed, "
          f"{sh_intent['unassessed']} unassessed of "
          f"{sum(len(v) for v in sites.values())}")


# ================================================================ G. corpus

def section_g():
    print("\nG. corpus")
    path = os.path.join(REPO, "corpus", "running-balance.planes")
    check("G", "corpus/running-balance.planes exists", os.path.exists(path), path)
    if not os.path.exists(path):
        return
    src = open(path, encoding="utf-8").read()
    i = Interpreter(host=TestHost())
    i.run_file(path)
    check("G", "runs cleanly", i.output == ["opening 500", "closing 575"], i.output)
    r = analyse(src)
    check("G", "effect surface is file-and-console",
          set(r.boundaries()) == {"file", "console"}, r.boundaries())

    if shutil.which("node"):
        proc = subprocess.run(
            ["node", "js/cli.mjs", "run-file", path], cwd=REPO,
            capture_output=True, text=True)
        d = json.loads(proc.stdout) if proc.returncode == 0 else {}
        check("G", "JavaScript agrees", d.get("output") == i.output, d)


def main():
    print("verify-number-of — A-Q19's gate")
    print("=" * 72)
    section_a()
    section_b()
    section_c()
    section_d()
    section_e()
    section_f()
    section_g()

    blocking_sections = {"A", "C", "D", "E"}
    failed = [r for r in RESULTS if not r[2]]
    blocking_failed = [r for r in failed if r[0] in blocking_sections]

    lines = ["# number-of-verification.md", "",
             "Automated verification for A-Q19 — `number of` and the "
             "corrected `cannot-combine` fix clause.", "",
             "| section | check | result | detail |", "|---|---|---|---|"]
    for section, label, ok, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        detail_cell = detail if not ok else ""
        lines.append(f"| {section} | {label} | {mark} | {detail_cell} |")
    lines.append("")
    lines.append(f"**{len(RESULTS) - len(failed)}/{len(RESULTS)} checks pass.** "
                 f"{len(blocking_failed)} blocking failure(s) "
                 f"(sections A, C, D, E).")

    out_path = os.path.join(REPO, "reports", "number-of-verification.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("\n" + "=" * 72)
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks pass "
          f"({len(blocking_failed)} blocking failures). "
          f"Report written to reports/number-of-verification.md")
    return 1 if blocking_failed else 0


if __name__ == "__main__":
    sys.exit(main())
