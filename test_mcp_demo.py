"""H3 — the v37.0 MCP demo, committed and gated.

checkpoint v37.0 (August 24, 2026, Part CC, paragraphs 518-521) opened its
session on a demonstration: could Planes analyse the code class that matters
most for agent safety, the tool layer of an MCP server? It logged the demo as
the first agent-tool artifact authored in Planes and an adoption asset, to
live under `demo/mcp/` -- but the artifact itself was never committed
(confirmed absent at 971961c by addendum v37.1's LOGGED section, paragraph
526). This file reconstructs it and gates it, since the checkpoint records
what the demo showed but not its exact source text.

`demo/mcp/v1.planes` is a small MCP tool, `lookup-package`: it reads an
agent-supplied request over stdio, times the call, asks an internal package
registry at a URL BUILT from the request (so the analyser can only report a
computed target, the literal prefix plus a `{...}` hole), and logs an audit
line to a file -- all through a `foreign` host seam for the clock and the
stdio read, each reported "(declared, not verified)" since a `foreign` claim
is asserted, never derived (paragraph 519). `demo/mcp/v2.planes` adds one
thing: a telemetry call to a fixed, literal host. Neither version can use a
`send` effect kind -- addendum v37.1 accepted one only in principle, for a
later build -- so, exactly as the checkpoint's demo did, the telemetry call
is a `foreign ... doing ask` claim, a POST spelled as a GET (v37.1,
paragraph 531).

The demonstration, end to end:
  * `--json` reports the registry call's hole and marks both foreign calls
    "(declared, not verified)" (paragraph 519);
  * `--diff` v1 -> v2 fails CI on the new telemetry destination (paragraph 519);
  * `--rules`, with one rule forbidding the telemetry host, passes v1 clean
    and fails v2 on the telemetry call -- WITHOUT also flagging the registry
    call, which is a different, provably-incompatible computed target. That
    non-flagging is v37.0 paragraph 513 / PR #104's `_pattern_excludes` fix,
    live against a real program instead of a synthetic one.
Python and JavaScript agree on all of it -- the standing three-implementations
claim, exercised here rather than just asserted.

Reconstructed, not verbatim: the checkpoint describes what the demo's surface
showed (the registry prefix, the hole, "declared, not verified", "NEW
DESTINATIONS", derivation tracing) but not the MCP tool's exact source text,
which was never recovered. See the PR description for exactly which lines are
quoted from the checkpoint versus written to satisfy it.
"""
import json
import os
import shutil
import subprocess
import sys

from shapes import analyse_file
from shapes_cli import as_json

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))
V1 = os.path.join(REPO, "demo", "mcp", "v1.planes")
V2 = os.path.join(REPO, "demo", "mcp", "v2.planes")
V1_JSON = os.path.join(REPO, "demo", "mcp", "v1.surface.json")
V2_JSON = os.path.join(REPO, "demo", "mcp", "v2.surface.json")

TELEMETRY = "https://telemetry.example.com/collect"
REGISTRY_HOLE = "https://registry.internal.example.com/v1/packages/{...}"


def _py_cli(args):
    r = subprocess.run([sys.executable, "shapes_cli.py", *args], cwd=REPO,
                       capture_output=True, text=True)
    return r.stdout, r.returncode


def _js(module, args):
    r = subprocess.run([NODE, module, *args], cwd=REPO,
                       capture_output=True, text=True)
    return r.stdout, r.returncode


def _committed(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ================================================================ the JSON surface (Python)

def test_v1_surface_matches_committed_json_and_shows_the_registry_hole():
    fresh = as_json(analyse_file(V1), V1)
    assert fresh == _committed(V1_JSON)
    assert fresh["complete"] is True
    asks = [e for e in fresh["effects"] if e["kind"] == "ask"]
    assert asks == [{"kind": "ask", "boundary": "network",
                     "target": REGISTRY_HOLE, "computed": True,
                     "declared": False}]


def test_v1_surface_marks_exactly_the_clock_and_stdio_foreigns_unverified():
    """paragraph 519: "the two host calls marked (declared, not verified)" -- the
    clock and the stdio read, each a `foreign` claim, never derived."""
    fresh = as_json(analyse_file(V1), V1)
    claimed = sorted(e["kind"] for e in fresh["effects"] if e["declared"])
    assert claimed == ["clock", "read"]


def test_v2_surface_matches_committed_json_and_adds_the_telemetry_destination():
    fresh = as_json(analyse_file(V2), V2)
    assert fresh == _committed(V2_JSON)
    ask_targets = {e["target"] for e in fresh["effects"] if e["kind"] == "ask"}
    assert ask_targets == {REGISTRY_HOLE, TELEMETRY}


# ================================================================ --diff (paragraphs 519, 521)

def test_diff_v1_to_v2_fails_ci_on_the_new_telemetry_reach():
    out, code = _py_cli(["--diff", V1, V2])
    assert code == 1
    assert "NEW DESTINATIONS" in out
    assert TELEMETRY in out


def test_diff_v2_to_v1_is_not_run_the_reach_is_new_only_forward():
    """Sanity on the direction of the claim above -- v1 has no telemetry
    call to lose, so the reverse diff must not also report it as new."""
    out, _ = _py_cli(["--diff", V2, V1])
    assert TELEMETRY not in out or "NEW DESTINATIONS" not in out


# ================================================================ --rules (PR #104's fix, live)

def test_rules_v1_is_clean():
    out, code = _py_cli([V1, "--rules"])
    assert code == 0
    assert "no violations" in out


def test_rules_v2_flags_telemetry_but_not_the_registry():
    """The load-bearing assertion: the SAME rule that correctly fires on the
    telemetry call must not also fire on the registry call, whose computed
    target is provably a different host (v37.0 paragraph 513's `_pattern_excludes`,
    PR #104). Before that fix, this rule would have reported BOTH."""
    out, code = _py_cli([V2, "--rules"])
    assert code == 1
    assert "no-telemetry-exfiltration" in out
    assert TELEMETRY in out
    assert "registry.internal.example.com" not in out


# ================================================================ Python/JS agreement

def test_js_shapes_agrees_with_the_committed_json():
    if NODE is None:
        return
    for path, committed in ((V1, V1_JSON), (V2, V2_JSON)):
        out, code = _js("js/cli.mjs", ["shapes", path])
        assert code == 0, out
        assert json.loads(out) == _committed(committed)


def test_js_diff_agrees_with_python():
    if NODE is None:
        return
    py_out, py_code = _py_cli(["--diff", V1, V2])
    js_out, js_code = _js("js/shapes_cli.mjs", ["--diff", V1, V2])
    assert (js_out, js_code) == (py_out, py_code)


def test_js_rules_agrees_with_python():
    if NODE is None:
        return
    for path, want_exit in ((V1, 0), (V2, 1)):
        out, code = _js("js/cli.mjs", ["rules", path])
        assert code == 0, out    # the CLI reports the result in JSON, not $?
        doc = json.loads(out)
        assert doc["exit"] == want_exit
        assert any(v["is_violation"] for v in doc["violations"]) == \
            bool(want_exit)


if __name__ == "__main__":
    if NODE is None:
        print("  note  node not on PATH — JS-side checks will no-op")
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
