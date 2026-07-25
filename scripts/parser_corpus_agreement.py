#!/usr/bin/env python3
"""Phase 4 corpus agreement: run grammar/parser.planes against parser.py
across the full 30-file corpus, and write parser-in-planes-verification.md.

PASS / PARTIAL / FAIL per file, with the first disagreeing canonical-form
line for anything not PASS, classified into one of three categories
(build prompt section 4): a bug in grammar/parser.planes, a language gap
(this build's stated scope limit -- amber/known_funcs-dependent calls,
statement forms past the section 3 ladder), or a genuine difference in
what the two implementations consider the same AST (none found in this
run). This changes nothing; it only measures and reports.
"""
import glob
import sys

sys.path.insert(0, ".")
from parser import parse  # noqa: E402
from test_parser_in_planes import canonical_program, planes_canonical_program  # noqa: E402

ROOT_CORPUS = ["annotated.planes", "foreign.planes", "gate.planes", "hn.planes",
              "money.planes", "names.planes", "ordinary.planes", "pypi.planes"]


def corpus():
    demo = sorted(glob.glob("demo/**/*.planes", recursive=True))
    return ROOT_CORPUS + demo


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
        try:
            py_form = canonical_program(parse(src))
        except Exception as e:
            results.append((f, "FAIL", f"parser.py itself raised: {e}"))
            continue
        try:
            planes_form = planes_canonical_program(src)
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
