"""The Swift rule checker, checked against rules.py.

The Swift counterpart of test_js_rules.py, with `planes-swift` in place of
`node js/cli.mjs`. swift/Sources/Planes/Rules.swift is a port of rules.py, on the
host's SHA-256. A rule is never triggered; it is checked against a surface
computed without running anything. The oracle (A.3) is pass/fail per rule WITH
the message text — errors-that-name-the-fix is a language-level commitment, so a
divergent message is a divergent implementation.

This drives every scenario in test_rules.py through both check() implementations
and compares the full result: each violation's render text, is_violation, and
vacuous flag; the resolved subjects; the exit category; and the RuleConflict /
RuleNotSupported message on refusal. Plus fingerprint byte-identity (the
FINGERPRINT token embeds it), the four rule-bearing corpus files through the
shapes_cli --rules path (follow + declaring_file), and the generated rule markers
(render-rules, which needed Render.swift). rules.py is the specification.

The last sections were written for this port and then taken into
test_js_rules.py. Rule names are ASCII by the
grammar, so the non-ASCII text a rule compares is its target, its `because`, and
the paths it names: targets that differ only by normalisation must not match,
code-point order decides the derived-from line, a fingerprint hashes UTF-8, and
a declaring file whose path is non-ASCII must still resolve its subjects. The
render-rules form is also held across the whole corpus, since Render.swift has no
suite of its own.
"""
import glob
import json
import os
import subprocess
import sys
import tempfile

from lexer import Rule
from modules import ModuleError
from parser import PlanesSyntaxError, parse
from planes_text import escape_string_literal
from rules import RuleConflict, RuleNotSupported, check, fingerprint
from shapes import analyse, analyse_file
from shapes_cli import as_json, rules_json
from swift_host import REPO, SWIFT, command


def _run(args):
    r = subprocess.run(command(*args), cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"planes-swift {args} failed: {r.stderr}")
    return json.loads(r.stdout)


def _render_rules(path):
    r = subprocess.run(command("render-rules", path), cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


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
     'rule [new] anything may not ask to "https://b.example.com" '
     'supersedes [old] @375bb2\n'
     'x = ask "https://a.example.com"\n'),
    'rule [new] anything may not ask supersedes [ghost]\n',
    # missing fingerprint (raises) -- B3, Track 0 #3
    ('use http\nrule [old] anything may not ask to "https://a.example.com"\n'
     'rule [new] anything may not ask to "https://b.example.com" '
     'supersedes [old]\n'
     'x = ask "https://a.example.com"\n'),
    # equal-specificity conflict, quote in the shared target, supersedes resolves it
    ('use http\nrule [a] anything may not ask to "https://x.example.com"\n'
     'rule [b] anything may not ask to "https://x.example.com"\n'
     'y = ask "https://x.example.com"\n'),
    ('use http\nrule [a] anything may not ask to "https://x.example.com/a\\"b"\n'
     'rule [b] anything may not ask to "https://x.example.com/a\\"b"\n'
     'y = ask "https://x.example.com/a\\"b"\n'),
    ('use http\nrule [a] anything may not ask to "https://x.example.com"\n'
     'rule [b] anything may not ask to "https://x.example.com" '
     'supersedes [a] @8e65b9\n'
     'y = ask "https://x.example.com"\n'),
    # permits: supersedes-clears, narrows-clears, broad-still-applies, different-target
    ('use http\nrule [no-external-sends] anything may not ask\n'
     'rule [audit-allowed] anything may ask to "https://audit.internal" '
     'supersedes [no-external-sends] @960178\nx = ask "https://audit.internal"\n'),
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
     'rule [b] anything may ask to "https://x.example.com" '
     'supersedes [a] @8e65b9\n'
     'y = ask "https://x.example.com"\n'),
    # vacuous: subject resolves, but the program performs no effect of the kind
    ('cap = "a.json"\nrule [cap-guard] cap may not ask\n'
     'use file\nwrite [1] to cap\n'),
    # B3 (Track 0 #5): contradicts -- parse/resolution errors, a pair that
    # both apply (reported), a pair where one is vacuous (not reported),
    # and a contradiction involving a permit rule.
    'rule [a] anything may not ask contradicts [ghost]\n',
    'rule [a] anything may not ask contradicts [a]\n',
    ('rule [a] anything may not ask contradicts [b]\n'
     'rule [b] anything may not write contradicts [a]\n'),
    ('use http\nuse file\n'
     'rule [no-writes] anything may not write\n'
     '  because "writes are audited separately"\n'
     'rule [no-sends] anything may not ask contradicts [no-writes]\n'
     'write 1 to "out.txt"\n'
     'x = ask "https://x.example.com"\n'),
    ('use http\n'
     'rule [no-writes] anything may not write\n'
     'rule [no-sends] anything may not ask contradicts [no-writes]\n'
     'x = ask "https://x.example.com"\n'),
    ('use http\nuse file\n'
     'rule [no-sends] anything may not ask\n'
     'rule [audit-allowed] anything may ask to "https://audit.internal" '
     'supersedes [no-sends] @960178\n'
     'rule [no-writes] anything may not write contradicts [audit-allowed]\n'
     'x = ask "https://audit.internal"\n'
     'write 1 to "out.txt"\n'),
    # B1 (Sprint B): forbid ask covers a send to the same target
    ('foreign send-it of x from "m.post" doing send "https://a.example.com"\n'
     'r = send-it of 1\n'
     'rule [deny] anything may not ask to "https://a.example.com"\n'),
    # forbid ask with no target forbids every send too
    ('foreign send-it of x from "m.post" doing send "https://a.example.com"\n'
     'r = send-it of 1\nrule [deny] anything may not ask\n'),
    # forbid send forbids only send, not ask at the same target
    ('foreign fetch-it of x from "m.get" doing ask "https://c.example.com"\n'
     'r = fetch-it of 1\n'
     'rule [deny-send] anything may not send to "https://c.example.com"\n'),
    # a permit for ask, even with an explicit supersedes at the exact target,
    # never clears a forbidden send (v37.1 §533's worked example)
    ('foreign send-it of x from "m.post" doing send "https://a.example.com"\n'
     'r = send-it of 1\nrule [deny] anything may not ask\n'
     'rule [ok] anything may ask to "https://a.example.com" supersedes [deny] @960178\n'),
    # the one way to except it: a send permit naming the forbid explicitly
    ('foreign send-it of x from "m.post" doing send "https://a.example.com"\n'
     'r = send-it of 1\nrule [deny] anything may not ask\n'
     'rule [ok] anything may send to "https://a.example.com" supersedes [deny] @960178\n'),
    # the structural collision: ask-forbid and send-permit, same target, no
    # supersedes -- a RuleConflict, exactly like a same-kind equal-specificity
    # pair
    ('rule [deny] anything may not ask to "https://e.example.com"\n'
     'rule [also] anything may send to "https://e.example.com"\n'),
    # ...resolved by naming the forbid explicitly
    ('foreign send-it of x from "m.post" doing send "https://e.example.com"\n'
     'r = send-it of 1\n'
     'rule [deny] anything may not ask to "https://e.example.com"\n'
     'rule [also] anything may send to "https://e.example.com" supersedes [deny] @1e7b2b\n'),
    # two forbids over overlapping kinds (ask covers send) never conflict
    # with each other -- both simply apply
    ('foreign send-it of x from "m.post" doing send "https://f.example.com"\n'
     'r = send-it of 1\n'
     'rule [deny-ask] anything may not ask to "https://f.example.com"\n'
     'rule [deny-send] anything may not send to "https://f.example.com"\n'),
]


def test_rule_check_agrees_on_every_scenario():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.planes")
        mismatches = []
        for src in RULE_PROGRAMS:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(src)
            py = _py_rules_src(src)
            sw = _run(["rules-src", p])
            if sw != py:
                mismatches.append(f"src:\n{src}\n  py={json.dumps(py)}\n"
                                  f"  swift={json.dumps(sw)}")
        assert not mismatches, "rule-check divergences:\n" + "\n".join(mismatches)


def test_a_real_violation_message_is_byte_identical():
    """Not vacuously agreeing: a concrete violation renders identical text."""
    src = ('use http\nrule [no-net] anything may not ask\n'
           'x = ask "https://example.com/a.json"\n')
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.planes")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(src)
        sw = _run(["rules-src", p])
    assert sw["exit"] == 1
    r = sw["violations"][0]["render"]
    assert "violated at line 3" in r
    assert "rule declared at line 2" in r
    assert r == _py_rules_src(src)["violations"][0]["render"]


def test_a_conflict_message_is_byte_identical():
    src = ('use http\nrule [a] anything may not ask to "https://x.example.com"\n'
           'rule [b] anything may ask to "https://x.example.com"\n'
           'y = ask "https://x.example.com"\n')
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.planes")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(src)
        sw = _run(["rules-src", p])
    assert sw["error"] == "RuleConflict"
    assert "opposite things" in sw["message"]
    assert sw == _py_rules_src(src)


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
        sw = _run(["rules", path])
        assert sw == py, f"{path}:\n  py={json.dumps(py)}\n  swift={json.dumps(sw)}"


def test_json_rules_agree_on_the_corpus_rule_files():
    """H1: `shapes --rules` (planes-swift's oracle for shapes_cli's
    `--json --rules`) must merge the identical "rules" document
    shapes_cli.as_json(surface, path, rules=rules_json(found, results))
    would — every structured violation field, plus the rendered message,
    byte for byte with the Python side."""
    for path in RULE_FILES:
        src = open(path, encoding="utf-8").read()
        found = [s for s in parse(src) if isinstance(s, Rule)]
        surface = analyse_file(path, follow=True)
        results = check(found, surface, declaring_file=os.path.abspath(path))
        py = as_json(surface, path, rules=rules_json(found, results))
        sw = _run(["shapes", path, "--rules"])
        assert sw == py, f"{path}:\n  py={json.dumps(py)}\n  swift={json.dumps(sw)}"


def test_json_rules_agree_on_a_contradiction():
    """B3 (Track 0 #5): the "contradiction" field the corpus rule files
    above never exercise (none declares `contradicts`) -- a dedicated file
    that does, checked the same way test_json_rules_agree_on_the_corpus_
    rule_files checks the others."""
    src = ('use http\nuse file\n'
           'rule [no-writes] anything may not write\n'
           'rule [no-sends] anything may not ask contradicts [no-writes]\n'
           'write 1 to "out.txt"\n'
           'x = ask "https://x.example.com"\n')
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "contradicts.planes")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        found = [s for s in parse(src) if isinstance(s, Rule)]
        surface = analyse_file(path, follow=True)
        results = check(found, surface, declaring_file=os.path.abspath(path))
        py = as_json(surface, path, rules=rules_json(found, results))
        sw = _run(["shapes", path, "--rules"])
    assert sw == py, f"py={json.dumps(py)}\n  swift={json.dumps(sw)}"
    contradiction_docs = [v["contradiction"] for v in py["rules"]["violations"]
                          if v["contradiction"] is not None]
    assert len(contradiction_docs) == 1
    assert contradiction_docs[0] == {
        "rule": "no-sends",
        "effect": {"kind": "ask", "boundary": "network",
                   "target": "https://x.example.com", "line": 6},
        "with_rule": "no-writes",
        "with_effect": {"kind": "write", "boundary": "file",
                        "target": "out.txt", "line": 5},
    }


# ============================================================ fingerprints

FINGERPRINT_FILES = ["annotated.planes", "demo/rules/exception.planes"]


def test_fingerprints_are_byte_identical():
    for path in FINGERPRINT_FILES:
        found = [s for s in parse(open(path, encoding="utf-8").read())
                 if isinstance(s, Rule)]
        py = [[r.name, fingerprint(r)] for r in found]
        sw = _run(["fingerprints", path])
        assert sw == py, f"{path}: py={py} swift={sw}"


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
    # Build via the parser so the Swift side sees the same rules, then compare
    # fingerprints of the parsed rules on both sides.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.planes")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(src)
        parsed = [s for s in parse(src) if isinstance(s, Rule)]
        py = [[r.name, fingerprint(r)] for r in parsed]
        sw = _run(["fingerprints", p])
    assert sw == py, f"py={py} swift={sw}"


# ============================================================ generated markers (render + rules)

MARKER_SRCS = [
    ('rule [refund-cap] anything may not write to "refunds.json"\n\n'
     'use file\nresults = { total: 1 }\nwrite results to "refunds.json"\n'),
    # a cleared match still shows the marker
    ('rule [no-write] anything may not write to "a.json"\n'
     'rule [allow-a] anything may write to "a.json" supersedes [no-write] '
     '@7785b4\n\n'
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
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(src)
            prog = parse(src)
            found = [s for s in prog if isinstance(s, Rule)]
            py = render(prog, rules=found, surface=analyse(src)) if found \
                else render(prog)
            sw = _render_rules(p)
            assert sw == py, f"src:\n{src}\n--- py ---\n{py}\n--- swift ---\n{sw}"



# ============================================================ every message, and the vacuous shapes

MORE_RULE_PROGRAMS = [
    # two rules with one name; a rule superseding itself; a stale fingerprint
    ('use http\nrule [a] anything may not ask\nrule [a] anything may not write\n'
     'x = ask "https://x"\n'),
    'rule [a] anything may not ask supersedes [a]\n',
    ('use http\nrule [a] anything may not ask to "https://x"\n'
     'rule [b] anything may ask to "https://x" supersedes [a] @000000\n'
     'x = ask "https://x"\n'),
    # a permit over a computed target clears nothing
    ('use http\nrule [no-net] anything may not ask\n'
     'rule [ok] anything may ask to "https://a" supersedes [no-net] @960178\n'
     'for each u in ["https://a"]:\n  x = ask u\n'),
    # vacuous situation 2: the kind is performed, but not from the subject
    ('use http\ncap = "https://a"\nrule [cap-guard] cap may not ask\n'
     'x = ask cap\ny = ask "https://b"\n'),
    ('use http\nuse file\ncap = "a.json"\nrule [cap-guard] cap may not ask\n'
     'write [1] to cap\ny = ask "https://b"\n'),
    # vacuous situation 3: the subject reaches the kind, never at the target
    ('use http\nto send of payload:\n  give ask "https://c/?d=" + payload\n\n'
     'rule [leak] payload may not ask to "https://elsewhere"\nx = send of "s"\n'),
    # a computed target's known chunks exclude a rule target they cannot reach
    # (v37.0 §513): another host, a mismatched end, a middle chunk that is absent
    ('use http\nrule [t] anything may not ask to "https://t.example/collect"\n'
     'to get of n:\n  give ask "https://r.example/p/" + n\n\nx = for each i in ["a"]: get of i\n'),
    ('use http\nrule [t] anything may not ask to "https://r.example/p/q"\n'
     'to get of n:\n  give ask "https://r.example/p/" + n\n\nx = for each i in ["a"]: get of i\n'),
    ('use http\nrule [t] anything may not ask to "https://r.example/p.json"\n'
     'to get of n:\n  give ask "https://r.example/" + n + ".xml"\n\n'
     'x = for each i in ["a"]: get of i\n'),
    ('use http\nrule [t] anything may not ask to "https://a/xc"\n'
     'to get of n, m:\n  give ask "https://a/" + n + "b" + m + "c"\n\n'
     'x = for each i in ["a"]: get of i, i\n'),
    # a foreign with no stated destination is never excluded
    ('rule [t] anything may not ask to "https://t.example"\n'
     'foreign post of x from "m.post" doing ask\nr = post of 1\n'),
    # the real target still fires beside an excluded one
    ('use http\nrule [t] anything may not ask to "https://t.example/collect"\n'
     'to get of n:\n  give ask "https://r.example/p/" + n\n\nx = for each i in ["a"]: get of i\n'
     'y = ask "https://t.example/collect"\n'),
    # chunks compare by code point: a decomposed é is not a composed one, and an
    # astral character is one code point
    ('use http\nrule [t] anything may not ask to "https://caf\u00e9/x"\n'
     'to get of n:\n  give ask "https://cafe\u0301/" + n\n\nx = for each i in ["a"]: get of i\n'),
    ('use http\nrule [t] anything may not ask to "https://\U0001f600/x"\n'
     'to get of n:\n  give ask "https://\U0001f600/" + n\n\nx = for each i in ["a"]: get of i\n'),
    # a rule whose target is empty text
    ('use http\nrule [a] anything may not ask to ""\nrule [b] anything may not ask to ""\n'
     'x = ask ""\n'),
    # B2: a narrower permit under a broader host-wide forbid narrows it
    # rather than conflicting, and clears only the subtree it names
    ('use http\nrule [deny] anything may not ask to "https://x"\n'
     'rule [ok] anything may ask to "https://x/public"\n'
     'a = ask "https://x/public/report"\nb = ask "https://x/private"\n'),
    # B2: a trailing-slash rule path covers everything under it but not the
    # bare path
    ('use http\nrule [t] anything may not ask to "https://x/ingest/"\n'
     'a = ask "https://x/ingest/v2"\nb = ask "https://x/ingest"\n'),
    # B2: a different host, and a subdomain, are never covered
    ('use http\nrule [t] anything may not ask to "https://x.com"\n'
     'a = ask "https://api.x.com"\nb = ask "https://x.com/y"\n'),
    # B2: scheme and host are case-insensitive, port is not folded
    ('use http\nrule [t] anything may not ask to "https://X.example/Ingest"\n'
     'a = ask "HTTPS://x.EXAMPLE/Ingest"\nb = ask "https://x.example/ingest"\n'),
    # B2: case-insensitivity is ASCII-only -- a non-ASCII host compares
    # exactly, even where two different full-Unicode lowerings of it
    # (a final-sigma reading and a plain-sigma reading of a trailing
    # capital Sigma) would disagree with each other
    ('use http\nrule [t] anything may not ask to "https://\u0391\u03a3.example"\n'
     'a = ask "https://\u03b1\u03c2.example"\nb = ask "https://\u03b1\u03c3.example"\n'),
    ('use http\nrule [t] anything may not ask to "https://x"\n'
     'a = ask "https://x:443"\n'),
    # B2: the effect's own query and fragment are ignored
    ('use http\nrule [t] anything may not ask to "https://x/ingest"\n'
     'a = ask "https://x/ingest?pkg=requests"\nb = ask "https://x/ingest#frag"\n'),
    # B2: a rule target carrying a query string or fragment is refused
    ('rule [bad] anything may not ask to "https://x/ingest?pkg=1"\n'),
    ('rule [bad] anything may not ask to "https://x/ingest#frag"\n'),
    # B2: computed-target exclusion re-proven for covering, not equality
    ('use http\nrule [t] anything may not ask to "https://x/ingest"\n'
     'to get of n:\n  give ask "https://x/ingest" + n\n\nx = for each i in ["a"]: get of i\n'),
    ('use http\nrule [t] anything may not ask to "https://x/ingest"\n'
     'to get of n:\n  give ask "https://x/ingestion/" + n\n\nx = for each i in ["a"]: get of i\n'),
    ('use http\nrule [t] anything may not ask to "https://x/ingest"\n'
     'to get of n:\n  give ask "https://" + n + "/ingest"\n\nx = for each i in ["a"]: get of i\n'),
    ('use http\nrule [t] anything may not ask to "https://x/"\n'
     'to get of n:\n  give ask "https://api." + n + "/"\n\nx = for each i in ["a"]: get of i\n'),
    ('use http\nrule [t] anything may not ask to "https://x/a"\n'
     'to get of n:\n  give ask "https://x/" + n\n\nx = for each i in ["a"]: get of i\n'),
]


def test_rule_check_agrees_on_every_message_shape():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.planes")
        mismatches = []
        for src in MORE_RULE_PROGRAMS:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(src)
            py = _py_rules_src(src)
            sw = _run(["rules-src", p])
            if sw != py:
                mismatches.append(f"src:\n{src}\n  py={json.dumps(py)}\n"
                                  f"  swift={json.dumps(sw)}")
        assert not mismatches, "rule-check divergences:\n" + "\n".join(mismatches)


# ============================================================ non-ASCII text

NON_ASCII_RULES = [
    # a target equal under canonical equivalence but not by code point: no match
    ('use http\nrule [no-cafe] anything may not ask to "https://caf\u00e9.example"\n'
     'x = ask "https://cafe\u0301.example"\n'),
    ('use http\nrule [no-cafe] anything may not ask to "https://caf\u00e9.example"\n'
     'x = ask "https://caf\u00e9.example"\n'),
    # two rules whose targets look alike: distinct, so not a conflict
    ('use http\nrule [a] anything may not ask to "\u00e9"\n'
     'rule [b] anything may not ask to "e\u0301"\nx = ask "\u00e9"\n'),
    # the same target twice: a conflict that quotes it, emoji and all
    ('use http\nrule [a] anything may not ask to "https://\U0001f600/\u00fc"\n'
     'rule [b] anything may ask to "https://\U0001f600/\u00fc"\n'
     'x = ask "https://\U0001f600/\u00fc"\n'),
    # an uncertain match quoting a non-ASCII target, and a permit that clears it
    ('use http\nrule [no-t] anything may not ask to "https://t\u00e9l\u00e9m\u00e9trie"\n'
     'for each u in ["https://t\u00e9l\u00e9m\u00e9trie"]:\n  x = ask u\n'),
    ('use http\nrule [deny] anything may not ask\n'
     'rule [allow] anything may ask to "https://\u4f8b\u3048.jp" '
     'supersedes [deny] @960178 '
     'because "\u8a31\u53ef \U0001f44d"\n'
     'x = ask "https://\u4f8b\u3048.jp"\ny = ask "https://\u4f8b\u3048.jp/\u0301"\n'),
    # derived-from order over names, and violations sorted by non-ASCII targets
    ('use http\nto send of zeta, alpha:\n  give ask "https://\u00e9/" + zeta + alpha\n\n'
     'rule [leak] anything may not ask\nx = send of "\U0001f600", "\uff41"\n'
     'y = ask "https://\uff41"\nz = ask "https://\U0001f600"\n'),
    # a fingerprinted supersedes over a non-ASCII target
    ('use http\nrule [a] anything may not ask to "https://\u00fc"\n'
     'rule [b] anything may not ask to "https://\u00fc" supersedes [a] @%s\n'
     'x = ask "https://\u00fc"\n' % fingerprint(Rule("a", "anything", "ask", "https://\u00fc", 2))),
]


def test_non_ascii_rule_checks_agree():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.planes")
        for src in NON_ASCII_RULES:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(src)
            py = _py_rules_src(src)
            assert _run(["rules-src", p]) == py, f"src:\n{src!r}\n  py={json.dumps(py)}"
            parsed = [s for s in parse(src) if isinstance(s, Rule)]
            assert _run(["fingerprints", p]) == [[r.name, fingerprint(r)] for r in parsed]
            try:
                py_render = render_program(parse(src), parsed, src)
            except (RuleConflict, RuleNotSupported):
                r = subprocess.run(command("render-rules", p), cwd=REPO,
                                   capture_output=True, text=True)
                assert r.returncode != 0, f"rendered a rule set that does not resolve:\n{src!r}"
                continue
            assert _render_rules(p) == py_render, f"src:\n{src!r}"


def render_program(prog, found, src):
    from render import render
    return render(prog, rules=found, surface=analyse(src)) if found else render(prog)


def test_a_declaring_file_with_a_non_ascii_path_resolves_its_subjects():
    """shapes_cli --rules scopes a named subject to abspath(file); the path is
    compared by code point, and the derived-from line prints it."""
    src = ('use http\nto send of payload:\n'
           '  give ask "https://collector.example.com/?d=" + payload\n\n'
           'rule [no-payload-leak] payload may not ask\nx = send of "secret"\n')
    with tempfile.TemporaryDirectory() as d:
        for name in ["caf\u00e9", "cafe\u0301", "\U0001f600"]:
            sub = os.path.join(d, name)
            os.makedirs(sub, exist_ok=True)
            p = os.path.join(sub, "r\u00e8gles.planes")
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(src)
            found = [s for s in parse(src) if isinstance(s, Rule)]
            py = _py_rules(found, analyse_file(p, follow=True), declaring_file=os.path.abspath(p))
            sw = _run(["rules", p])
            assert sw == py, f"{p!r}:\n  py={json.dumps(py)}\n  swift={json.dumps(sw)}"
            assert py["exit"] == 1 and name in py["violations"][0]["render"]


def test_a_subject_declared_in_another_file_is_refused_naming_that_file():
    """A rule may not reach across an import to a name it never saw declared;
    the refusal names the other file's absolute path, non-ASCII and all."""
    lib = 'use http\nto send of payload:\n  give ask "https://c.example/?d=" + payload\n'
    main = 'use lib\nrule [no-leak] payload may not ask\nx = send of "s\u00e9cret"\n'
    with tempfile.TemporaryDirectory() as d:
        sub = os.path.join(d, "d\u00e9p\u00f4t \U0001f600")
        os.makedirs(sub)
        with open(os.path.join(sub, "lib.planes"), "w", encoding="utf-8") as fh:
            fh.write(lib)
        p = os.path.join(sub, "main.planes")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(main)
        found = [s for s in parse(main, {"send"}) if isinstance(s, Rule)]
        py = _py_rules(found, analyse_file(p, follow=True), declaring_file=os.path.abspath(p))
        sw = _run(["rules", p])
    assert sw == py, f"py={json.dumps(py)}\n  swift={json.dumps(sw)}"
    assert py.get("error") == "RuleNotSupported" and "lib.planes" in py["message"], py


def test_line_endings_in_a_rule_file_are_read_as_python_reads_them():
    """shapes_cli reads the file in text mode, so a lone CR ends a line and moves
    every line number a violation reports."""
    src = ('use http\rrule [no-net] anything may not ask\r\n'
           'x = ask "https://a"\ry = ask "https://b"\r\n')
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.planes")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(src)
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
        found = [s for s in parse(text) if isinstance(s, Rule)]
        py = _py_rules(found, analyse_file(p, follow=True), declaring_file=os.path.abspath(p))
        assert _run(["rules", p]) == py
        assert "violated at line 4" in json.dumps(py)


# ============================================================ render-rules across the corpus

def test_render_rules_agrees_across_the_corpus():
    """Render.swift's canonical source, byte for byte, for every parseable file
    (markers where the file has rules)."""
    checked = 0
    mismatches = []
    for f in sorted(x for x in glob.glob("**/*.planes", recursive=True) if ".venv" not in x):
        try:
            with open(f, encoding="utf-8") as fh:
                src = fh.read()
            prog = parse(src)
            found = [s for s in prog if isinstance(s, Rule)]
            py = render_program(prog, found, src)
        except (PlanesSyntaxError, ModuleError, RuleConflict, RuleNotSupported, ValueError):
            continue
        sw = _render_rules(f)
        if sw != py:
            mismatches.append(f)
        checked += 1
    assert checked >= 40, checked
    assert not mismatches, f"render divergences: {mismatches}"


if __name__ == "__main__":
    if SWIFT is None:
        print("  SKIP  swift not on PATH")
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
