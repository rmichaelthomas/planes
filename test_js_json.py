"""C1 — grammar/json.planes on the JavaScript host, agreeing with the Python one.

The JSON reader and writer are a Planes PROGRAM, not a host capability, so
there is nothing to port: the same `grammar/json.planes` runs on interp.py and
on js/interp.mjs. This file is the check that it does, and that both agree with
the reference.

The canonical form is a round trip through the program's own two halves —
`json-text-of (json-parse src)` — which is a stronger comparison than either
half alone: reader and writer must both be right, and the text must be
byte-identical on both hosts. Where Planes refuses (an escape it cannot spell),
the refusal and its message must agree too, which is why the refusing files are
in the fixture list rather than excluded from it.

The third comparison is against the reference: `to_json(from_foreign(
json.loads(src)))` is what interp.py would put in a file after an `ask`, and
the Planes round trip must match it byte for byte — including the quirk that a
non-whole number goes out as exact text rather than as a float.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from interp import Deriv, Interpreter, Traced, from_foreign, to_json

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))
JSON_PLANES = "grammar/json.planes"

# JSON documents that live in the repo already, smallest first. packages.json
# carries \uXXXX escapes, so it is the refusal case — kept in the list on
# purpose: a refusal must agree across implementations exactly as an acceptance
# must.
REPO_FILES = ["results.json", "invoice.json", "big.json", "refunds.json",
              "ast_fixtures_baseline.json", "packages.json"]

# Written to a temp directory: the shapes the gate names — nesting, escapes,
# exact numbers, empty containers, and astral-plane Unicode.
FIXTURES = {
    "nesting.json": '{"a": {"b": {"c": [1, 2, {"d": null}]}}}',
    "deep.json": "[" * 40 + "1" + "]" * 40,
    "escapes.json": r'{"q": "a\"b", "s": "a\\b", "sl": "a\/b", "nl": "x\ny", "tab": "x\ty"}',
    "numbers.json": '[0, -0, 42, -42, 3.5, -3.5, 0.1, 1e3, 1E3, 1e+3, 1e-3, '
                    '2.5e2, -2.5e-2, 12345678901234567890, 9007199254740993]',
    "empties.json": '{"e": {}, "l": [], "n": [[], {}, [[]], [{}]]}',
    "astral.json": '{"s": "a\U0001f600b", "t": "café", "u": "中文"}',
    "escaped-astral.json": '{"s": "a\\ud83d\\ude00b"}',
    "scalars.json": '[null, true, false, "", "text"]',
}

_interp = None


def _get():
    global _interp
    if _interp is None:
        _interp = Interpreter()
        _interp.run_file(JSON_PLANES)
    return _interp


def _t(v, label="<host value>"):
    return Traced(v, Deriv("literal", label, v, []))


def _py_round_trip(src):
    """{ok, detail, text} from grammar/json.planes on interp.py."""
    i = _get()
    r = i.call("json-parse", [_t(src)], i.env).value
    if not r["ok"]:
        return {"ok": False, "detail": r["detail"], "text": None}
    w = i.call("json-text-of", [_t(r["value"])], i.env).value
    return {"ok": True, "detail": "", "text": w}


def _js_round_trip(paths):
    """The same, from grammar/json.planes on js/interp.mjs, one file per entry."""
    r = subprocess.run([NODE, "js/cli.mjs", "meta", "json", *paths],
                       cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed: {r.stderr}")
    return json.loads(r.stdout)


def _reference(src):
    """What interp.py itself produces for the same round trip: parse_json ->
    from_foreign -> to_json. None when json.loads refuses."""
    try:
        return to_json(from_foreign(json.loads(src)))
    except Exception:                                     # noqa: BLE001
        return None


def _all_paths():
    """(path, source) for every fixture, repo files plus the temp ones."""
    tmp = tempfile.mkdtemp(prefix="planes-json-")
    out = []
    for name in REPO_FILES:
        p = os.path.join(REPO, name)
        if os.path.exists(p):
            out.append((p, open(p, encoding="utf-8").read()))
    for name, text in FIXTURES.items():
        p = os.path.join(tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        out.append((p, text))
    return out


def test_the_planes_json_program_agrees_across_implementations():
    if NODE is None:
        return
    cases = _all_paths()
    js = _js_round_trip([p for p, _ in cases])
    assert len(js) == len(cases)
    mism = []
    for (path, src), j in zip(cases, js):
        p = _py_round_trip(src)
        if p != j:
            mism.append(f"{os.path.basename(path)}: py={p!r} js={j!r}")
    assert not mism, "cross-implementation JSON divergences:\n" + "\n".join(mism)


def test_the_planes_round_trip_matches_the_reference_byte_for_byte():
    """Where Planes accepts, its bytes are the reference's bytes. The two
    exceptions are named, not skipped: a document with non-ASCII text (Planes
    writes the character, json.dumps writes \\uXXXX) and a document whose
    escapes Planes cannot spell (refused)."""
    checked, refused, non_ascii = 0, [], []
    for path, src in _all_paths():
        name = os.path.basename(path)
        mine = _py_round_trip(src)
        theirs = _reference(src)
        if not mine["ok"]:
            refused.append(name)
            assert "has no Planes spelling" in mine["detail"], mine["detail"]
            continue
        assert theirs is not None, f"{name}: the reference refused what Planes read"
        if mine["text"] != theirs:
            # the only permitted cause: text the reference escapes and Planes
            # writes literally
            assert any(ord(c) > 0x7e for c in mine["text"]), (
                f"{name}: divergence with no non-ASCII cause\n"
                f" planes={mine['text']!r}\n reference={theirs!r}")
            assert json.loads(mine["text"]) == json.loads(theirs), name
            non_ascii.append(name)
            continue
        checked += 1
    print(f"    [json round trip: {checked} byte-identical to the reference, "
          f"{len(non_ascii)} equal-but-unescaped ({', '.join(non_ascii)}), "
          f"{len(refused)} refused ({', '.join(refused)})]")
    # A clean checkout tracks ast_fixtures_baseline.json plus the generated
    # fixtures above: seven byte-identical acceptances after the named astral
    # and refusal cases. Developer workspaces may contribute more optional
    # REPO_FILES, but the gate cannot require untracked local data.
    assert checked >= 7, checked
    assert refused, "the refusal path was never exercised"


def test_the_refusal_message_is_identical_on_both_implementations():
    if NODE is None:
        return
    tmp = tempfile.mkdtemp(prefix="planes-json-refuse-")
    names = []
    for i, text in enumerate(('"esc\\r"', '"esc\\b"', '"esc\\f"',
                              '"esc\\u0041"', '{"k": "\\ud83d\\ude00"}')):
        p = os.path.join(tmp, f"r{i}.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        names.append((p, text))
    js = _js_round_trip([p for p, _ in names])
    for (path, src), j in zip(names, js):
        p = _py_round_trip(src)
        # the reference accepts every one of these; both Planes hosts refuse
        # them, with the same message
        json.loads(src)
        assert not p["ok"] and not j["ok"], (src, p, j)
        assert p["detail"] == j["detail"], (src, p["detail"], j["detail"])


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
        except Exception as e:                            # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
