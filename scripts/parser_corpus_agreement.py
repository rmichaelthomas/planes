#!/usr/bin/env python3
"""Corpus agreement: run grammar/parser.planes against parser.py across the
full 31-file corpus, and write parser-in-planes-verification.md.

PASS / PARTIAL / FAIL per file, with the first disagreeing canonical-form
line for anything not PASS. As of S3a Phase 4 the corpus reaches FULL
agreement (31 PASS): the cursor moved to `rest of xs`, the name table
(known_funcs) and the four amber sites landed, and every statement form
past the old ladder -- write, foreign, rule, note, when, why, fail, the
because/with/or-fail trailers, and for-each-as-expression -- now parses to
an AST matching parser.py's. CLASSIFICATION below is retained as a
diagnostic: it fires only if a file regresses, naming what it used to need.
This script changes nothing; it only measures and reports.
"""
import glob
import os
import re
import sys

sys.path.insert(0, ".")
from parser import parse, scan_names  # noqa: E402
from test_parser_in_planes import canonical_program, planes_canonical_program  # noqa: E402

ROOT_CORPUS = ["annotated.planes", "foreign.planes", "gate.planes", "hn.planes",
              "money.planes", "names.planes", "ordinary.planes", "pypi.planes"]


def corpus():
    demo = sorted(glob.glob("demo/**/*.planes", recursive=True))
    return ROOT_CORPUS + demo


def cross_file_known(path):
    """Function names a file calls but defines in a `use`d sibling module.

    Resolves each `use X` to <dir>/X.planes (the same-directory rule
    modules.py enforces) and scans it for defined names. This is the cross-
    file `known` parser.py's parse(src, known) takes; the harness supplies
    it only when a file cannot be parsed standalone (demo/app/net.planes
    calls config.planes's `api base`), and passes the identical mapping to
    both parsers so a PASS proves they agree given the same module context.
    """
    d = os.path.dirname(path)
    known = {}
    for line in open(path, encoding="utf-8").read().splitlines():
        m = re.match(r"\s*use\s+([A-Za-z_][\w-]*)", line)
        if m:
            sibling = os.path.join(d, m.group(1) + ".planes")
            if os.path.exists(sibling):
                known.update(scan_names(open(sibling, encoding="utf-8").read()))
    return known


# Per-file classification, filled in by hand after reading each failure
# (build prompt section 4: "every disagreement is classified before it
# is fixed"). Keyed by path; value is (category, note).
CLASSIFICATION = {
    "annotated.planes": ("language gap", "`rule` statement -- past the section 3 ladder"),
    "foreign.planes": ("language gap", "cons-list cursor ceiling (147 tokens > ~140)"),
    "gate.planes": ("language gap", "cons-list cursor ceiling (201 tokens > ~140)"),
    "hn.planes": ("language gap", "cons-list cursor ceiling (167 tokens > ~140)"),
    "money.planes": ("language gap", "juxtaposition call (`total ...`) -- needs known_funcs"),
    "names.planes": ("language gap", "paren-arglist ambiguity site -- needs known_funcs"),
    "ordinary.planes": ("language gap", "`for each` as an expr (comprehension), out of scope"),
    "pypi.planes": ("language gap", "cons-list cursor ceiling (158 tokens > ~140)"),
    "demo/app/main.planes": ("language gap", "juxtaposition call (`package`), needs known_funcs"),
    "demo/app/net.planes": ("test methodology",
                            "parser.py itself needs cross-file known_funcs (`api base`, from "
                            "config.planes) to parse standalone -- not a disagreement"),
    "demo/clash/cache.planes": ("language gap", "juxtaposition call with a string argument"),
    "demo/clash/loader.planes": ("language gap", "juxtaposition call with a string argument"),
    "demo/clash/main.planes": ("language gap", "multiword function name (`record ...`)"),
    "demo/fdiff/v1.planes": ("language gap", "`foreign` declaration -- past the section 3 ladder"),
    "demo/fdiff/v2.planes": ("language gap", "`foreign` declaration -- past the section 3 ladder"),
    "demo/pkgs/cachelib.planes": ("language gap", "`write ... to ...` -- past the ladder"),
    "demo/pkgs/fetcher.planes": ("language gap", "juxtaposition call (`url ...`)"),
    "demo/pkgs/sneaky.planes": ("language gap", "juxtaposition call with a string argument"),
    "demo/rename/cache.planes": ("language gap", "juxtaposition call with a string argument"),
    "demo/rename/loader.planes": ("language gap", "juxtaposition call with a string argument"),
    "demo/rename/main.planes": ("language gap", "multiword function name (`record ...`)"),
    "demo/rules/clean.planes": ("language gap", "`rule` statement -- past the section 3 ladder"),
    "demo/rules/exception.planes": ("language gap", "`rule` statement -- past the ladder"),
    "demo/rules/violation.planes": ("language gap", "`rule` statement -- past the ladder"),
    "demo/v1.planes": ("language gap", "multiword function name / juxtaposition (`config ...`)"),
    "demo/v2.planes": ("language gap", "juxtaposition call with a string argument"),
}


def run():
    results = []
    for f in corpus():
        src = open(f, encoding="utf-8").read()
        known = None
        try:
            py_form = canonical_program(parse(src))
        except Exception:
            # Standalone parse failed -- a file that calls a sibling module's
            # function (its multi-word name is a syntax error without the
            # name table). Retry with cross-file known, the same mapping the
            # module system would supply, passed identically to both parsers.
            known = cross_file_known(f)
            try:
                py_form = canonical_program(parse(src, known))
            except Exception as e:
                results.append((f, "FAIL", f"parser.py raised even with cross-file known: {e}"))
                continue
        try:
            planes_form = planes_canonical_program(src, known)
        except Exception as e:
            note = CLASSIFICATION.get(f, ("unclassified", ""))[1]
            results.append((f, "FAIL", f"{type(e).__name__}: {e} -- {note}"))
            continue
        if planes_form == py_form:
            results.append((f, "PASS", ""))
            continue
        py_lines = py_form.split("\n")
        pl_lines = planes_form.split("\n")
        idx = next((i for i in range(min(len(py_lines), len(pl_lines)))
                   if py_lines[i] != pl_lines[i]), min(len(py_lines), len(pl_lines)))
        note = CLASSIFICATION.get(f, ("unclassified", ""))[1]
        results.append((f, "PARTIAL", f"first disagreeing node at line {idx} -- {note}"))
    return results


def main():
    results = run()
    counts = {"PASS": 0, "PARTIAL": 0, "FAIL": 0}
    for _, status, _ in results:
        counts[status] += 1
    print(f"{counts['PASS']} PASS, {counts['PARTIAL']} PARTIAL, {counts['FAIL']} FAIL "
         f"out of {len(results)}", file=sys.stderr)
    for f, status, detail in results:
        print(f"{status:8} {f}  {detail}")


if __name__ == "__main__":
    main()
