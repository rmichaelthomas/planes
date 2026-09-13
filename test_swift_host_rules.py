"""The host entry point to Planes rules, checked against shapes.py and rules.py.

swift/Sources/Planes/HostRules.swift lets a Swift application (a browser, say)
check the effects it intends to perform — a request to this URL, a write to that
file — against Planes rules it ships as source, without running any Planes
program. It claims to add no semantics: the surface it builds is the one
shapes.py's `analyse` computes for the Planes program that performs exactly those
effects, one per line, each to a literal destination, and the results are
rules.py's `check` over it with no declaring file.

This holds that claim. For each scenario the Swift side runs
`planes-swift host-rules <rules-file> <effects-json>`; the Python side writes the
equivalent program (`ask "..."`, `read "..."`, `write 0 to "..."`, `show "..."`,
each on the line its site names), analyses it, and checks the rules parsed from
the same file. Compared: the surface (as_json), every result's render text,
is_violation and vacuous flag, the resolved subjects, the exit category or the
refusal, whether every effect is admitted, and each result's rule `because` —
which render() never prints, so the host API carries it beside.

Planes' own demo/rules/exception.planes (default-deny with a named exception) is
a scenario, with targets that differ from its exception only by normalisation.
Effects no Planes program can perform with a literal destination — the ambient
kinds — have no Python equivalent, so the last test only checks that the Swift
side refuses them rather than inventing a surface.
"""
import json
import os
import subprocess
import sys
import tempfile

from lexer import Rule
from parser import parse
from planes_text import escape_string_literal
from rules import RuleConflict, RuleNotSupported, check
from shapes import analyse
from shapes_cli import as_json
from swift_host import REPO, SWIFT, command


def _swift(rules_path, effects):
    r = subprocess.run(command("host-rules", rules_path, json.dumps(effects)), cwd=REPO,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"planes-swift host-rules failed: {r.stderr}")
    return json.loads(r.stdout)


def program_for(effects):
    """The Planes program that performs `effects`: each on the line its site
    names (its 1-based position when it names none), blank lines between."""
    # not a vocabulary table: only the effect kinds that carry a literal
    # destination have a program form. clock, env and random never do, so
    # HostRules refuses them and there is no equivalent program to build.
    forms = {"ask": "ask {}", "read": "read {}", "write": "write 0 to {}", "show": "show {}"}
    lines = []
    for i, e in enumerate(effects):
        site = e.get("site", i + 1)
        assert site > len(lines), "sites must increase"
        lines.extend([""] * (site - 1 - len(lines)))
        lines.append(forms[e["kind"]].format('"' + escape_string_literal(e["target"]) + '"'))
    return "\n".join(lines) + "\n"


def _python(rules_src, effects):
    found = [s for s in parse(rules_src) if isinstance(s, Rule)]
    surface = analyse(program_for(effects))
    out = {"surface": as_json(surface, "host")}
    try:
        results = check(found, surface)
    except (RuleConflict, RuleNotSupported) as e:
        out["rules"] = {"error": type(e).__name__, "message": str(e)}
        out["admitted"] = None
        out["because"] = None
        return out
    out["rules"] = {
        "violations": [{"render": v.render(), "is_violation": v.is_violation, "vacuous": v.vacuous}
                       for v in results],
        "resolved_subjects": results.resolved_subjects,
        "exit": (1 if any(v.is_violation for v in results)
                 else 2 if any(v.vacuous for v in results) else 0),
    }
    out["admitted"] = not any(v.is_violation for v in results)
    out["because"] = [v.rule.annotation.text if v.rule.annotation else None for v in results]
    return out


def _agree(rules_src, effects, rules_path=None):
    with tempfile.TemporaryDirectory() as d:
        if rules_path is None:
            rules_path = os.path.join(d, "rules.planes")
            with open(rules_path, "w", encoding="utf-8", newline="") as fh:
                fh.write(rules_src)
        sw = _swift(rules_path, effects)
    py = _python(rules_src, effects)
    assert sw == py, (f"rules:\n{rules_src}\neffects: {effects!r}\n"
                      f"  py={json.dumps(py, ensure_ascii=False)}\n"
                      f"  swift={json.dumps(sw, ensure_ascii=False)}")
    return sw


EXCEPTION = "demo/rules/exception.planes"


def test_the_exception_demo_admits_its_exception_and_refuses_the_rest():
    with open(EXCEPTION, encoding="utf-8") as fh:
        src = fh.read()
    out = _agree(src, [
        {"kind": "ask", "target": "https://audit.internal"},
        {"kind": "ask", "target": "https://tracker.example/pixel.gif"},
        {"kind": "show", "target": "sending audit event"},
    ], rules_path=EXCEPTION)
    assert out["admitted"] is False
    renders = [v["render"] for v in out["rules"]["violations"]]
    assert any("excepted by [audit-allowed]" in r for r in renders), renders
    assert any("[no-external-sends] violated at line 2." in r for r in renders), renders
    because = "default-deny keeps audit events from leaking to an unapproved endpoint"
    assert because in out["because"]


def test_the_exception_demo_admits_the_exception_alone():
    with open(EXCEPTION, encoding="utf-8") as fh:
        src = fh.read()
    out = _agree(src, [{"kind": "ask", "target": "https://audit.internal"}], rules_path=EXCEPTION)
    assert out["admitted"] is True
    assert out["rules"]["exit"] == 0 and len(out["rules"]["violations"]) == 1


def test_the_exception_is_matched_by_code_point():
    """An exception written with a precomposed é does not admit a request to the
    same-looking URL spelled with a combining accent, nor the reverse."""
    src = ('rule [deny] anything may not ask\n  because "d\u00e9fense par d\u00e9faut \U0001f6ab"\n'
           'rule [cafe-ok] anything may ask to "https://caf\u00e9.example/\u00fc" '
           'supersedes [deny]\n')
    out = _agree(src, [
        {"kind": "ask", "target": "https://caf\u00e9.example/\u00fc"},
        {"kind": "ask", "target": "https://cafe\u0301.example/\u00fc"},
        {"kind": "ask", "target": "https://caf\u00e9.example/u\u0308"},
        {"kind": "ask", "target": "https://\U0001f600.example"},
    ])
    assert out["admitted"] is False
    assert sum(v["is_violation"] for v in out["rules"]["violations"]) == 3


SCENARIOS = [
    # the violation demo's rule, and sites with gaps
    ('rule [readings-stay-local] anything may not ask to "https://metrics.internal/ingest"\n',
     [{"kind": "read", "target": "readings.csv", "site": 3},
      {"kind": "ask", "target": "https://metrics.internal/ingest", "site": 7},
      {"kind": "ask", "target": "https://metrics.internal/other", "site": 12}]),
    # nested rules: a broad deny narrowed by a specific one
    ('rule [no-net] anything may not ask\nrule [no-telemetry] anything may not ask to "https://t.example"\n',
     [{"kind": "ask", "target": "https://t.example"}, {"kind": "ask", "target": "https://x.example"}]),
    # file kinds, and a target with a quote, a backslash and a newline
    ('rule [refund-cap] anything may not write to "refunds.json"\n'
     'rule [no-secrets] anything may not read to "a\\"b\\\\c\\nd"\n',
     [{"kind": "write", "target": "refunds.json"}, {"kind": "read", "target": 'a"b\\c\nd'},
      {"kind": "write", "target": "other.json"}]),
    # no effects: a pure surface, nothing violated
    ('rule [no-net] anything may not ask\n', []),
    # a named subject: no host effect derives from a name, so it cannot be checked
    ('rule [no-leak] payload may not ask\n', [{"kind": "ask", "target": "https://x"}]),
    # a rule set that does not resolve
    ('rule [a] anything may not ask to "https://x"\nrule [b] anything may ask to "https://x"\n',
     [{"kind": "ask", "target": "https://x"}]),
    ('rule [ok] anything may ask to "https://x"\n', [{"kind": "ask", "target": "https://x"}]),
    # a source with more than rules in it: only the rules count
    ('use http\nrule [no-net] anything may not ask\nx = ask "https://ignored"\n',
     [{"kind": "ask", "target": "https://y"}]),
]


def test_host_rules_agree_on_every_scenario():
    for src, effects in SCENARIOS:
        _agree(src, effects)


def test_a_repeated_destination_is_reported_at_one_of_its_lines():
    """The same request made twice is one declared effect, and a violation names
    one line for it. Which line, shapes.py leaves to chance: its top-level
    effects are a Python set, sorted by (boundary, kind, target), so the tie
    between two sites falls in hash order — which PYTHONHASHSEED changes from run
    to run. Swift (like js) keeps the first. So this checks Swift's answer is
    one Python gives, and that Python really gives both."""
    rules_src = 'rule [no-ingest] anything may not ask to "https://metrics.internal/ingest"\n'
    effects = [{"kind": "ask", "target": "https://metrics.internal/ingest", "site": 7},
               {"kind": "ask", "target": "https://metrics.internal/ingest", "site": 9}]
    probe = (
        "import json, sys\n"
        "from test_swift_host_rules import _python\n"
        "print(json.dumps(_python(sys.argv[1], json.loads(sys.argv[2]))))\n")
    seen = {}
    for seed in range(8):
        env = {**os.environ, "PYTHONHASHSEED": str(seed)}
        r = subprocess.run([sys.executable, "-c", probe, rules_src, json.dumps(effects)], cwd=REPO,
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        seen[out["rules"]["violations"][0]["render"].split("\n")[0]] = out
    assert len(seen) == 2, f"expected the reference to vary with the hash seed: {list(seen)}"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "rules.planes")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(rules_src)
        sw = _swift(p, effects)
    first = "[no-ingest] violated at line 7."
    assert sw["rules"]["violations"][0]["render"].startswith(first), sw
    assert sw == seen[first]


def test_effects_with_no_literal_destination_are_refused():
    """clock, random and env take no destination: no Planes program gives them a
    literal target, so there is no Python equivalent to build — the host API
    refuses them, and refuses sites that do not increase."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "rules.planes")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("rule [no-net] anything may not ask\n")
        for effects in ([{"kind": "clock", "target": "now"}],
                        [{"kind": "ask", "target": "https://a", "site": 5},
                         {"kind": "ask", "target": "https://b", "site": 5}]):
            out = _swift(p, effects)
            assert out.get("error") == "HostEffectError", out


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
