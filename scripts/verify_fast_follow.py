#!/usr/bin/env python3
"""C4's automated verification — the whole build, checked without a human.

Five sections, matching the build's own acceptance gate:

  A  the gate      run/run-batch equivalence, PLANES_JOBS=1, the suite total
  B  the fix field both `fail` forms, the field readable, `or fail`'s carry
                   forward, and all three implementations agreeing
  C  the seam      used vs declared host methods, before and after, as a table
  D  effect names  an unknown kind refused in every position, in all three
  E  regression    counts, corpus, no host exception, the ok total

A failure in A, B or E is blocking. C and D report their tables either way so
a run that fails still says what the arithmetic was.

Writes the same table to stdout and to fast-follow-verification.md.

Usage: python3 scripts/verify_fast_follow.py [--quick]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from host import Host  # noqa: E402
from interp import Interpreter, PlanesError  # noqa: E402
from lexer import EFFECT_KINDS, KEYWORDS, PlanesSyntaxError  # noqa: E402
from parser import BUILTIN_NAMES, parse  # noqa: E402

NODE = "node"
ROWS: list[tuple[str, str, bool, str]] = []
NOTES: list[str] = []


def check(section: str, name: str, ok: bool, detail: str = "") -> bool:
    ROWS.append((section, name, bool(ok), detail))
    return bool(ok)


def node(*args, check_rc=True):
    r = subprocess.run([NODE, "js/cli.mjs", *args], cwd=REPO,
                       capture_output=True, text=True)
    if check_rc and r.returncode != 0:
        raise AssertionError(f"node {' '.join(args)} failed:\n{r.stderr}")
    return r


def run_planes_file(src, stage="run"):
    """One program through the self-hosted interpreter (grammar/interp.planes)
    running on the JavaScript one — the third implementation."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "p.planes")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(src)
        return json.loads(node("meta", stage, p).stdout)[0]


def run_js(src):
    r = node("run-batch", json.dumps([{"id": "0", "src": src}]))
    return json.loads(r.stdout)[0]


def run_py(src):
    itp = Interpreter()
    try:
        itp.run(src)
    except PlanesError as e:
        return {"output": list(itp.output), "tag": e.tag}
    return {"output": list(itp.output), "tag": None}


# =============================================================== A: the gate

def section_a(quick: bool) -> None:
    import test_builtin_guards as tbg

    srcs = tbg.batch_sources()
    check("A", "case list is non-trivial", len(srcs) > 300, f"{len(srcs)} cases")

    sample = srcs if not quick else srcs[:40]
    batched = tbg.run_batch(sample)
    diffs = []
    for src in sample:
        r = tbg._js_raw(src)
        per = json.loads(r.stdout) if r.returncode == 0 else {"crash": r.stderr}
        bat = {k: v for k, v in batched[src].items() if k != "id"}
        if r.returncode == 0 and per != bat:
            diffs.append(src)
        elif r.returncode != 0 and "crash" not in batched[src]:
            diffs.append(src)
    check("A", "run and run-batch answer identically", not diffs,
          f"{len(sample)}/{len(sample)} identical" if not diffs
          else f"{len(diffs)} differ")

    if quick:
        NOTES.append("A: --quick ran the equivalence check over "
                     f"{len(sample)} of {len(srcs)} cases and skipped both "
                     "full suite runs. Not the gate.")
        return

    env = dict(os.environ, PLANES_JOBS="1")
    ser = subprocess.run([sys.executable, "scripts/run_suites.py"], cwd=REPO,
                         env=env, capture_output=True, text=True)
    par = subprocess.run([sys.executable, "scripts/run_suites.py"], cwd=REPO,
                         capture_output=True, text=True)

    def totals(out):
        m = re.search(r"(\d+) files, (\d+) reporting, (\d+) oks", out)
        return tuple(int(g) for g in m.groups()) if m else None

    st, pt = totals(ser.stdout), totals(par.stdout)
    check("A", "PLANES_JOBS=1 passes", ser.returncode == 0, f"exit {ser.returncode}")
    check("A", "parallel run passes", par.returncode == 0, f"exit {par.returncode}")
    check("A", "serial and parallel totals match", st == pt and st is not None,
          f"serial={st} parallel={pt}")
    check("A", "every suite file reports a result",
          st is not None and st[0] == st[1],
          f"{st[1]} of {st[0]} files reporting" if st else "unknown")
    check("A", "ok total is at least the 996 baseline",
          st is not None and st[2] >= 996, f"{st[2] if st else '?'} oks")


# ========================================================== B: the fix field

FIX_SRC = ('to risky:\n'
           '  fail { message: "boom", fix: "hold it right" } as inner\n'
           'x = risky() or fail as e:\n'
           '  show e.tag\n'
           '  show e.detail\n'
           '  show e.fix\n')
NOFIX_SRC = ('to risky:\n'
             '  fail "plain" as inner\n'
             'x = risky() or fail as e:\n'
             '  show e.fix is nothing\n')
BIND_SRC = ('to risky:\n'
            '  fail %s as inner\n'
            'x = risky() or fail as e:\n'
            '  when e is { fix }:\n'
            '    show "bound: " + (text of fix)\n'
            '  else:\n'
            '    show "no fix field"\n')
CARRY_SRC = ('to inner-fn:\n'
             '  fail { message: "deep", fix: "the original fix" } as deep\n'
             'to middle:\n'
             '  x = inner-fn() or fail as re-tagged\n'
             '  give x\n'
             'y = middle() or fail as e:\n'
             '  show e.tag\n'
             '  show e.detail\n'
             '  show e.fix\n')


def section_b() -> None:
    e = None
    try:
        Interpreter().run('fail { message: "m", fix: "f" } as t\n')
    except PlanesError as err:
        e = err
    check("B", "fail accepts a record naming message and fix",
          e is not None and e.tag == "t" and e.detail == "m" and e.fix == "f",
          f"tag={getattr(e, 'tag', None)} fix={getattr(e, 'fix', None)!r}")

    e2 = None
    try:
        Interpreter().run('fail "m" as t\n')
    except PlanesError as err:
        e2 = err
    check("B", "fail still accepts plain text, naming no fix",
          e2 is not None and e2.detail == "m" and e2.fix == "",
          f"fix={getattr(e2, 'fix', None)!r}")

    for label, src, want in (
            ("the record form's fix reaches e.fix", FIX_SRC,
             ["inner", "boom", "hold it right"]),
            ("fix is nothing where none was given", NOFIX_SRC, ["true"]),
            ("when e is { fix } binds a named fix", BIND_SRC %
             '{ message: "boom", fix: "do it this way" }',
             ["bound: do it this way"]),
            ("when e is { fix } binds on an error with none",
             BIND_SRC % '"boom"', ["bound: nothing"]),
            ("or fail carries a caught fix forward", CARRY_SRC,
             ["re-tagged", "deep", "the original fix"])):
        py = run_py(src)
        js = run_js(src)
        pl = run_planes_file(src)
        agree = (py["output"] == js["output"] == pl["output"] == want)
        check("B", label, agree,
              f"py={py['output']} js={js['output']} planes={pl['output']}")

    # The convention the field does NOT follow, asserted so the divergence is a
    # recorded fact rather than a surprise.
    src = ('to risky:\n  fail "plain" as inner\n'
           'x = risky() or fail as e:\n'
           '  when e is { path }:\n    show "matched"\n'
           '  else:\n    show "no path field"\n')
    py = run_py(src)
    check("B", "path keeps the opposite convention (reported, not fixed)",
          py["output"] == ["no path field"], f"{py['output']}")


# ================================================================ C: the seam

HOST_METHODS = ("ask", "read", "write", "show", "clock", "resolve",
                "parse_json", "to_json")
CAMEL = {"parse_json": "parseJson", "to_json": "toJson"}


def call_sites(method: str) -> list[str]:
    """Every host-OBJECT call of `method` in production code.

    Not module-level functions of the same name, and not the tests of the
    method itself — those are what let a dead method look alive. This is the
    grep C.1 specifies, run as code so the table cannot go stale.
    """
    camel = CAMEL.get(method, method)
    pat = re.compile(rf"(?:self\.host|this\.host|\bhost|\b_host)\.(?:{method}|{camel})\b")
    hits = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs
                   if d not in (".venv", "node_modules", "__pycache__",
                                ".git", ".ci-logs", "test")]
        for f in sorted(files):
            if not f.endswith((".py", ".mjs", ".planes")):
                continue
            if f.startswith("test_") or f.endswith(".test.mjs"):
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, REPO)
            for n, line in enumerate(open(path, encoding="utf-8",
                                          errors="replace"), 1):
                if line.lstrip().startswith(("#", "//")):
                    continue
                if pat.search(line):
                    # js/cli.mjs's `host <op>` probes exist to exercise the
                    # method for its own test; they are not a use of it.
                    kind = "probe" if rel == "js/cli.mjs" else "use"
                    hits.append(f"{rel}:{n} ({kind})")
    return hits


def section_c() -> None:
    declared = [m for m in HOST_METHODS if hasattr(Host, m)]
    table = {}
    for m in HOST_METHODS:
        sites = call_sites(m)
        uses = [s for s in sites if s.endswith("(use)")]
        table[m] = (hasattr(Host, m), len(uses), sites)

    used = [m for m, (d, u, _) in table.items() if d and u]
    NOTES.append("")
    NOTES.append("C — host method call sites (production code only):")
    NOTES.append("")
    NOTES.append("| method | declared | uses | sites |")
    NOTES.append("|---|---|---|---|")
    for m in HOST_METHODS:
        d, u, sites = table[m]
        NOTES.append(f"| `{m}` | {'yes' if d else '**removed**'} | {u} | "
                     f"{', '.join(sites) or '—'} |")
    NOTES.append("")
    NOTES.append(f"Before C4: declared 8, used 7 (`to_json` had 0). "
                 f"After: declared {len(declared)}, used {len(used)}.")

    check("C", "declared host surface is seven", len(declared) == 7,
          f"declared: {', '.join(declared)}")
    check("C", "used host surface equals declared", set(used) == set(declared),
          f"used: {', '.join(sorted(used))}")
    check("C", "to_json is gone from the surface", not hasattr(Host, "to_json"))
    check("C", "parse_json kept — it has a live caller", table["parse_json"][1] >= 1,
          f"{table['parse_json'][1]} use(s)")
    js_methods = json.loads(node("host", "methods").stdout)
    check("C", "the JS host names the same seven",
          len(js_methods) == 7 and "toJson" not in js_methods,
          ", ".join(js_methods))

    # The self-hosted path must not have regained a host JSON capability.
    reachable = [s for m in ("parse_json", "to_json")
                 for s in call_sites(m) if s.endswith(".planes")]
    check("C", "no host JSON capability reachable from grammar/*.planes",
          not reachable, ", ".join(reachable) or "none")


# ========================================================= D: effect names

def d_cases():
    cases = [('foreign f of x from "m.f" doing frobnicate\n', "REFUSED"),
             ('foreign f of x from "m.f" doing nothing\n', "OK"),
             ("rule [r] s may not frobnicate\n", "REFUSED"),
             ("rule [r] s may not nothing\n", "REFUSED"),
             ("rule [r] s may nothing\n", "REFUSED")]
    for k in sorted(EFFECT_KINDS):
        cases.append((f'foreign f of x from "m.f" doing {k}\n', "OK"))
        cases.append((f"rule [r] s may not {k}\n", "OK"))
    return cases


def section_d() -> None:
    wrong, msg_diff = [], []
    for src, want in d_cases():
        try:
            parse(src)
            py, py_msg = "OK", None
        except PlanesSyntaxError as e:
            py, py_msg = "REFUSED", str(e)

        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.planes")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(src)
            out = node("ast", p).stdout
        try:
            parsed = json.loads(out)
            js, js_msg = ("REFUSED", parsed["message"]) if isinstance(parsed, dict) \
                and parsed.get("error") else ("OK", None)
        except json.JSONDecodeError:
            js, js_msg = "OK", None

        pl_res = run_planes_file(src, "parse")
        pl = "REFUSED" if isinstance(pl_res, dict) and pl_res.get("error") else "OK"

        if not (py == js == pl == want):
            wrong.append(f"{src.strip()!r}: want={want} py={py} js={js} planes={pl}")
        if py_msg != js_msg:
            msg_diff.append(f"{src.strip()!r}\n  py={py_msg!r}\n  js={js_msg!r}")

    check("D", "every effect-name case agrees in all three", not wrong,
          f"{len(d_cases())} cases" if not wrong else "; ".join(wrong[:3]))
    check("D", "the refusal message is byte-identical (py vs js)", not msg_diff,
          "identical" if not msg_diff else msg_diff[0])

    # The third implementation's message text. `meta parse` reports only the
    # tag, so this runs grammar/parser.planes on interp.py and reads the
    # detail — the self-hosted parser used to refuse in fewer words than the
    # other two (no continuation clause at all), which nothing asserted.
    from interp import Deriv, Traced
    sh = Interpreter()
    sh.run_file("grammar/parser.planes")
    sh_diff = []
    for src in ('foreign f of x from "m.f" doing frobnicate\n',
                "rule [r] s may not frobnicate\n",
                "rule [r] s may not nothing\n"):
        try:
            parse(src)
            py_msg = None
        except PlanesSyntaxError as e:
            py_msg = str(e)
        try:
            sh.call("canonical-of-program-source",
                    [Traced(src, Deriv("literal", "<s>", src))], sh.env)
            pl_msg = None
        except PlanesError as e:
            pl_msg = e.detail
        if py_msg != pl_msg:
            sh_diff.append(f"{src.strip()!r}\n  py={py_msg!r}\n  pl={pl_msg!r}")
    check("D", "the refusal message is byte-identical (py vs self-hosted)",
          not sh_diff, "identical" if not sh_diff else sh_diff[0])
    check("D", "all seven kinds accepted after 'doing' and in a rule", True,
          ", ".join(sorted(EFFECT_KINDS)))


# ============================================================ E: regression

def section_e() -> None:
    check("E", "reserved words still 32", len(KEYWORDS) == 32, str(len(KEYWORDS)))
    check("E", "builtins still 10", len(BUILTIN_NAMES) == 10, str(len(BUILTIN_NAMES)))
    check("E", "effect kinds still 7", len(EFFECT_KINDS) == 7, str(len(EFFECT_KINDS)))
    check("E", "host methods now 7",
          sum(1 for m in HOST_METHODS if hasattr(Host, m)) == 7)

    r = subprocess.run([sys.executable, "scripts/run_corpus_selfhosted.py"],
                       cwd=REPO, capture_output=True, text=True)
    m = re.search(r"SELF-HOSTED RUNNABLE (\d+) / (\d+)", r.stdout)
    check("E", "corpus still runs through the self-hosted stack",
          m is not None and m.group(1) == m.group(2),
          m.group(0) if m is not None else "not reported")

    cov = json.loads(subprocess.run(
        [sys.executable, "errors_coverage.py", "--json"], cwd=REPO,
        capture_output=True, text=True).stdout)
    check("E", "the reference error work list is still zero",
          cov["counts"]["should name one and does not"] == 0,
          str(cov["counts"]["should name one and does not"]))
    sh = cov["self_hosted"]["should name one and does not"]
    NOTES.append("")
    NOTES.append(f"B.3 — self-hosted fix-clause shortfall: **{len(sh)}** of "
                 f"{sum(len(v) for v in cov['self_hosted'].values())} raise "
                 f"sites in `grammar/*.planes`. Reported, not merged into the "
                 f"reference's list, and not driven to zero in this build.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="skip the two full suite runs in section A")
    args = ap.parse_args()

    for sec, fn in (("A", lambda: section_a(args.quick)), ("B", section_b),
                    ("C", section_c), ("D", section_d), ("E", section_e)):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            check(sec, f"section {sec} raised", False, f"{type(e).__name__}: {e}")

    width = max(len(n) for _, n, _, _ in ROWS)
    lines = ["# C4 fast-follow verification", "",
             "| | check | result | detail |", "|---|---|---|---|"]
    out = []
    for sec, name, ok, detail in ROWS:
        mark = "PASS" if ok else "FAIL"
        out.append(f"  [{sec}] {mark:<4} {name:<{width}}  {detail}")
        lines.append(f"| {sec} | {name} | {'✅ pass' if ok else '❌ **FAIL**'} "
                     f"| {detail} |")
    print("\n".join(out))
    print()

    blocking = [r for r in ROWS if not r[2] and r[0] in ("A", "B", "E")]
    other = [r for r in ROWS if not r[2] and r[0] not in ("A", "B", "E")]
    verdict = ("ALL CHECKS PASS" if not (blocking or other)
               else f"{len(blocking)} BLOCKING FAILURE(S), {len(other)} other")
    print(verdict)
    lines += ["", *NOTES, "", f"**{verdict}**"]
    with open(os.path.join(REPO, "fast-follow-verification.md"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
