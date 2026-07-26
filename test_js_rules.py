"""S5, Phase 4 — the JS rule checker, checked against rules.py.

js/rules.mjs is a port of rules.py, on Phase 1's synchronous hash. A rule is
never triggered; it is checked against a surface computed without running
anything. The oracle (A.3) is pass/fail per rule WITH the message text —
errors-that-name-the-fix is a language-level commitment, so a divergent message
is a divergent implementation.

This drives every scenario in test_rules.py through both check() implementations
and compares the full result: each violation's render text, is_violation, and
vacuous flag; the resolved subjects; the exit category; and the RuleConflict /
RuleNotSupported message on refusal. Plus fingerprint byte-identity (the
FINGERPRINT token embeds it) and the four rule-bearing corpus files through the
shapes_cli --rules path (follow + declaring_file). rules.py is the specification.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from lexer import Rule
from parser import parse
from planes_text import escape_string_literal
from rules import RuleConflict, RuleNotSupported, check, fingerprint
from shapes import analyse, analyse_file

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))


def _run(args):
    r = subprocess.run([NODE, "js/cli.mjs", *args], cwd=REPO,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node {args} failed: {r.stderr}")
    return json.loads(r.stdout)


def _py_rules(found, surface, declaring_file=None):
    try:
        results = check(found, surface, declaring_file=declaring_file)
        return {
            "violations": [
                {"render": v.render(), "is_violation": v.is_violation,
                 "vacuous": v.vacuous}
                for v in results
            ],
            "resolved_subjects": results.resolved_subjects,
            "exit": (1 if any(v.is_violation for v in results)
                     else 2 if any(v.vacuous for v in results) else 0),
        }
    except RuleConflict as e:
        return {"error": "RuleConflict", "message": str(e)}
    except RuleNotSupported as e:
        return {"error": "RuleNotSupported", "message": str(e)}


def _py_rules_src(src):
    prog = parse(src)
    found = [s for s in prog if isinstance(s, Rule)]
    return _py_rules(found, analyse(src))


# ============================================================ the test_rules.py scenarios

RULE_PROGRAMS = [
    # clean / violation / kind-never-performed
    'use http\nrule [no-net] anything may not ask\nx = ask "https://example.com/a.json"\n',
    'use file\nrule [no-net] anything may not ask\nwrite [1] to "o.json"\n',
    'use file\nrule [no-clock] anything may not clock\nwrite [1] to "o.json"\n',
    # target match: miss, then hit
    ('use http\nrule [no-telemetry] anything may not ask '
     'to "https://telemetry.example.com"\nx = ask "https://other.example.com/a.json"\n'),
    ('use http\nrule [no-telemetry] anything may not ask '
     'to "https://telemetry.example.com"\nx = ask "https://telemetry.example.com"\n'),
    # computed / uncertain, and a quote in the target
    ('use http\nrule [no-telemetry] anything may not ask '
     'to "https://telemetry.example.com"\n'
     'urls = ["https://a.example.com", "https://telemetry.example.com"]\n'
     'for each u in urls:\n  x = ask u\n'),
    ('use http\nrule [no-telemetry] anything may not ask '
     'to "https://x.example.com/a\\"b"\n'
     'urls = ["https://a.example.com", "https://x.example.com/a\\"b"]\n'
     'for each u in urls:\n  x = ask u\n'),
    # named subject: resolves and checks, unresolvable (raises), does-not-resolve
    ('use http\nto send of payload:\n'
     '  give ask "https://collector.example.com/?d=" + payload\n\n'
     'rule [no-payload-leak] payload may not ask\nx = send of "secret"\n'),
    'use http\nrule [readings-stay-local] readings may not ask\nx = ask "https://example.com/a.json"\n',
    'use http\nrule [x] nonexistent-name may not ask\ny = ask "https://example.com/a.json"\n',
    # derivation line present / absent
    ('use http\nto send of payload:\n'
     '  give ask "https://collector.example.com/?d=" + payload\n\n'
     'rule [no-leak] anything may not ask\nx = send of "secret"\n'),
    'use http\nrule [no-net] anything may not ask\nx = ask "https://example.com/a.json"\n',
    # nested rules (narrowed_by), supersedes drops, supersedes unknown (raises)
    ('use http\nrule [no-net] anything may not ask\n'
     'rule [no-telemetry] anything may not ask to "https://telemetry.example.com"\n'
     'x = ask "https://telemetry.example.com"\n'),
    ('use http\nrule [old] anything may not ask to "https://a.example.com"\n'
     'rule [new] anything may not ask to "https://b.example.com" supersedes [old]\n'
     'x = ask "https://a.example.com"\n'),
    'rule [new] anything may not ask supersedes [ghost]\n',
    # equal-specificity conflict, quote in the shared target, supersedes resolves it
    ('use http\nrule [a] anything may not ask to "https://x.example.com"\n'
     'rule [b] anything may not ask to "https://x.example.com"\n'
     'y = ask "https://x.example.com"\n'),
    ('use http\nrule [a] anything may not ask to "https://x.example.com/a\\"b"\n'
     'rule [b] anything may not ask to "https://x.example.com/a\\"b"\n'
     'y = ask "https://x.example.com/a\\"b"\n'),
    ('use http\nrule [a] anything may not ask to "https://x.example.com"\n'
     'rule [b] anything may not ask to "https://x.example.com" supersedes [a]\n'
     'y = ask "https://x.example.com"\n'),
    # permits: supersedes-clears, narrows-clears, broad-still-applies, different-target
    ('use http\nrule [no-external-sends] anything may not ask\n'
     'rule [audit-allowed] anything may ask to "https://audit.internal" '
     'supersedes [no-external-sends]\nx = ask "https://audit.internal"\n'),
    ('use http\nrule [no-external-sends] anything may not ask\n'
     'rule [audit-allowed] anything may ask to "https://audit.internal"\n'
     'x = ask "https://audit.internal"\n'),
    ('use http\nrule [no-external-sends] anything may not ask\n'
     'rule [audit-allowed] anything may ask to "https://audit.internal"\n'
     'x = ask "https://elsewhere.example.com"\n'),
    ('use http\nrule [no-external-sends] anything may not ask\n'
     'rule [audit-allowed] anything may ask to "https://audit.internal"\n'
     'x = ask "https://audit.internal"\ny = ask "https://not-audit.example.com"\n'),
    # unrelated permit (raises), global permit (raises)
    ('use http\nrule [no-clock] anything may not clock\n'
     'rule [audit-allowed] anything may ask to "https://audit.internal"\n'),
    'rule [x] anything may ask to "https://audit.internal"\n',
    # opposite-assertion conflict, and supersedes resolving it
    ('use http\nrule [a] anything may not ask to "https://x.example.com"\n'
     'rule [b] anything may ask to "https://x.example.com"\n'
     'y = ask "https://x.example.com"\n'),
    ('use http\nrule [a] anything may not ask to "https://x.example.com"\n'
     'rule [b] anything may ask to "https://x.example.com" supersedes [a]\n'
     'y = ask "https://x.example.com"\n'),
    # vacuous: subject resolves, but the program performs no effect of the kind
    ('cap = "a.json"\nrule [cap-guard] cap may not ask\n'
     'use file\nwrite [1] to cap\n'),
]


def test_rule_check_agrees_on_every_scenario():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.planes")
        mismatches = []
        for src in RULE_PROGRAMS:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(src)
            py = _py_rules_src(src)
            js = _run(["rules-src", p])
            if js != py:
                mismatches.append(f"src:\n{src}\n  py={json.dumps(py)}\n"
                                  f"  js={json.dumps(js)}")
        assert not mismatches, "rule-check divergences:\n" + "\n".join(mismatches)


def test_a_real_violation_message_is_byte_identical():
    """Not vacuously agreeing: a concrete violation renders identical text."""
    src = ('use http\nrule [no-net] anything may not ask\n'
           'x = ask "https://example.com/a.json"\n')
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.planes")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(src)
        js = _run(["rules-src", p])
    assert js["exit"] == 1
    r = js["violations"][0]["render"]
    assert "violated at line 3" in r
    assert "rule declared at line 2" in r
    assert r == _py_rules_src(src)["violations"][0]["render"]


def test_a_conflict_message_is_byte_identical():
    src = ('use http\nrule [a] anything may not ask to "https://x.example.com"\n'
           'rule [b] anything may ask to "https://x.example.com"\n'
           'y = ask "https://x.example.com"\n')
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.planes")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(src)
        js = _run(["rules-src", p])
    assert js["error"] == "RuleConflict"
    assert "opposite things" in js["message"]
    assert js == _py_rules_src(src)


# ============================================================ the corpus rule files

RULE_FILES = [
    "annotated.planes",
    "demo/rules/clean.planes",
    "demo/rules/violation.planes",
    "demo/rules/exception.planes",
]


def test_rule_check_agrees_on_the_corpus_rule_files():
    """Through the shapes_cli.py --rules path: surface via analyse_file(follow),
    declaring_file = the file's abspath."""
    for path in RULE_FILES:
        src = open(path, encoding="utf-8").read()
        found = [s for s in parse(src) if isinstance(s, Rule)]
        surface = analyse_file(path, follow=True)
        py = _py_rules(found, surface, declaring_file=os.path.abspath(path))
        js = _run(["rules", path])
        assert js == py, f"{path}:\n  py={json.dumps(py)}\n  js={json.dumps(js)}"


# ============================================================ fingerprints

FINGERPRINT_FILES = ["annotated.planes", "demo/rules/exception.planes"]


def test_fingerprints_are_byte_identical():
    for path in FINGERPRINT_FILES:
        found = [s for s in parse(open(path, encoding="utf-8").read())
                 if isinstance(s, Rule)]
        py = [[r.name, fingerprint(r)] for r in found]
        js = _run(["fingerprints", path])
        assert js == py, f"{path}: py={py} js={js}"


def test_fingerprint_of_a_constructed_rule_agrees():
    """A direct check across rule shapes, including a target with a quote (the
    canonical string joins subject/assertion/kind/target with \\x1f)."""
    rules = [
        Rule("f", "anything", "ask", None, 1),
        Rule("g", "anything", "write", "refunds.json", 2),
        Rule("h", "payload", "ask", 'a"b', 3),
        Rule("p", "anything", "ask", "https://audit.internal", 4,
             assertion="permit"),
    ]
    src = "\n".join(
        f'rule [{r.name}] {r.subject} '
        f'{"may not" if r.assertion == "forbid" else "may"} {r.kind}'
        + (f' to "{escape_string_literal(r.target)}"' if r.target else "")
        for r in rules) + "\n"
    # Build via the parser so the JS side sees the same rules, then compare
    # fingerprints of the parsed rules on both sides.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.planes")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(src)
        parsed = [s for s in parse(src) if isinstance(s, Rule)]
        py = [[r.name, fingerprint(r)] for r in parsed]
        js = _run(["fingerprints", p])
    assert js == py, f"py={py} js={js}"


# ============================================================ generated markers (render + rules)

MARKER_SRCS = [
    ('rule [refund-cap] anything may not write to "refunds.json"\n\n'
     'use file\nresults = { total: 1 }\nwrite results to "refunds.json"\n'),
    # a cleared match still shows the marker
    ('rule [no-write] anything may not write to "a.json"\n'
     'rule [allow-a] anything may write to "a.json" supersedes [no-write]\n\n'
     'use file\nwrite [1] to "a.json"\n'),
    # a vacuous rule gets no marker
    ('cap = "a.json"\nrule [cap-guard] cap may not ask\n\n'
     'use file\nwrite [1] to cap\n'),
]


def test_rendered_markers_agree():
    """render-rules (shapes_cli --render) — canonical source with the generated
    rule markers — is byte-identical, so the render+rules integration agrees."""
    from render import render
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "m.planes")
        for src in MARKER_SRCS + [open(f, encoding="utf-8").read()
                                  for f in RULE_FILES]:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(src)
            prog = parse(src)
            found = [s for s in prog if isinstance(s, Rule)]
            py = render(prog, rules=found, surface=analyse(src)) if found \
                else render(prog)
            js = subprocess.run([NODE, "js/cli.mjs", "render-rules", p],
                                cwd=REPO, capture_output=True, text=True)
            assert js.returncode == 0, js.stderr
            assert js.stdout == py, f"src:\n{src}\n--- py ---\n{py}\n--- js ---\n{js.stdout}"


if __name__ == "__main__":
    if NODE is None:
        print("  SKIP  node not on PATH")
        sys.exit(0)
    fails = []
    tests = [(k, f) for k, f in sorted(globals().items())
             if k.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            fails.append(name)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
