"""S5, Phase 2 — the JS analyser, checked against shapes.py.

js/shapes.mjs is a port of shapes.py: the fixed-point effect-surface
computation, import following across files, constant propagation for
destinations, and the StaticDeriv provenance graph. This is the build's centre
(A.1), and this is its central test.

The oracle is canonical-form agreement (A.3), reusing the existing published
surface form — shapes_cli.as_json — rather than inventing a fourth. Both
implementations produce the surface and this compares the JSON structure:

  * the whole corpus, following imports (analyse_file), so the multi-file
    constant-propagation and rename paths are exercised;
  * a battery of inline programs mirroring test_shapes.py — specialisation,
    widening at branch/loop joins, recursion never specialised, libraries,
    computed targets, foreign declarations;
  * the per-function breakdown (shapes-fn);
  * totality (A.1 ruling 1): the analyser never raises on a parseable program,
    including partially-resolvable ones (unresolved calls, undeclared foreigns).

The analyser must reproduce shapes.py's widening EXACTLY — a JS analyser more
precise than the Python one is a divergence, not an improvement (A.1 ruling 2).
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

from modules import ModuleError
from parser import PlanesSyntaxError
from shapes import analyse_file
from shapes_cli import as_json

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))


def _run(args):
    r = subprocess.run([NODE, "js/cli.mjs", *args], cwd=REPO,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node {args} failed: {r.stderr}")
    return r.stdout


def _js_shapes(path, follow=True):
    args = ["shapes", path] + ([] if follow else ["--no-follow"])
    return json.loads(_run(args))


def _js_shapes_fn(path, follow=True):
    args = ["shapes-fn", path] + ([] if follow else ["--no-follow"])
    return json.loads(_run(args))


def _py_functions(surface):
    """The same per-function breakdown js/shapes.mjs's functionsBreakdown emits:
    sorted function name -> its (already-sorted) effects, as plain fields."""
    return {
        name: [
            {"kind": e.kind, "boundary": e.boundary, "target": e.target,
             "computed": e.computed, "claimed": e.claimed}
            for e in surface.functions[name]
        ]
        for name in sorted(surface.functions)
    }


def all_planes_files():
    return sorted(f for f in glob.glob("**/*.planes", recursive=True)
                  if ".venv" not in f)


def _src_to_tmp(src, d):
    p = os.path.join(d, "p.planes")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(src)
    return p


# ================================================================ inline programs
#
# Curated from test_shapes.py — every case that exercises a distinct analyser
# path. Shared with test_js_shapes_derivation.py.

INLINE = [
    # pure, and pure library
    "to add of a, b:\n  give a + b\n\nr = add of 2, 3",
    "to square of n:\n  give n * n",
    # transitive effects up the call graph
    ('use http\nto inner:\n  give ask "https://example.com/a.json"\n\n'
     'to middle:\n  give inner\n\nto outer:\n  give middle\n\nr = outer'),
    # mutual recursion terminates
    ('use http\nto ping of n:\n  if n > 0:\n    give pong of (n - 1)\n'
     '  give ask "https://example.com/a.json"\n\n'
     'to pong of n:\n  give ping of (n - 1)\n\nr = ping of 3'),
    # literal target is exact
    'use http\nx = ask "https://example.com/a.json"',
    # computed target keeps the host
    ('use http\nto f of n:\n'
     '  give ask "https://example.com/item/" + text of n + ".json"\n\n'
     'xs = for each i in [1, 2]: f of i'),
    # target resolves through a variable
    ('use http\nlet base = "https://api.example.com"\n'
     'let endpoint = base + "/users"\nx = ask endpoint'),
    # target resolves through a call argument
    ('use http\nto get of url:\n  give ask url\n\n'
     'r = get of "https://api.example.com/data.json"'),
    # stays unknown when it really is
    ('use http\nto get of url:\n  give ask url\n\n'
     'xs = for each u in [1, 2]: get of u'),
    # recursive function is never specialised
    ('to countdown of n:\n  show text of n\n  if n > 0:\n'
     '    give countdown of (n - 1)\n  give 0\n\ncountdown of 3'),
    # text of a known number is known
    ('use file\nlet n = 7\nwrite [1] to "out" + text of n + ".json"'),
    # constant folding does not loop on recursion
    ('use http\nto grow of n:\n  give grow of (n + 1)\n\n'
     'x = ask "https://example.com/" + text of (grow of 1)'),
    # a variable rebound in a branch widens
    ('use http\nlet u = "https://example.com/default.json"\n'
     'if 1 > 0:\n  let u = "https://example.com/other.json"\nx = ask u'),
    # a variable rebound in a loop widens
    ('use http\nlet u = "https://example.com/default.json"\n'
     'for each i in [1, 2]:\n  let u = "https://example.com/other.json"\n'
     'x = ask u'),
    # sequential rebinding tracks both targets
    ('use http\nlet u = "https://example.com/one.json"\nx = ask u\n'
     'let u = "https://example.com/two.json"\ny = ask u'),
    # one function called with known and unknown args
    ('use http\nto get of url:\n  give ask url\n\n'
     'a = get of "https://example.com/known.json"\n'
     'b = for each u in ["https://example.com/x.json"]: get of u'),
    # declared but unused modules
    'use http\nuse file\nx = 5',
    # used but undeclared (no `use http`)
    'x = ask "https://example.com/a.json"',
    # effects deduplicated by site
    ('use http\nto f:\n  give ask "https://example.com/a.json"\n\na = f\nb = f'),
    # a library is not pure
    'use http\nto get of url:\n  give ask url',
    # effect hidden two calls deep
    ('use http\nto helper of n:\n  give n + 1\n\n'
     'to compute of n:\n  let r = helper of n\n  give beacon of r\n\n'
     'to beacon of r:\n  give ask "https://collect.example.com/?v=" + text of r'),
    # foreign, undeclared -> incomplete surface
    'foreign x of a from "m.f"\nr = x of 1',
    # foreign, declared with a param destination
    ('foreign fetch of url from "net.get" doing ask url\n'
     'r = fetch of "https://declared.example.com/x"'),
    # foreign, declared doing nothing
    'foreign pure calc of n from "math.f" doing nothing\nr = pure calc of 3',
    # the ten adversarial smuggling attempts
    ('use http\nto probe of n:\n'
     '  give count of (ask "https://example.com/a.json") > 0\n\n'
     'xs = for each i in [1, 2] where probe of i: i'),
    ('use http\nto src:\n  give ask "https://example.com/list.json"\n\n'
     'xs = for each i in src: i'),
    ('use http\nx = ask "https://example.com/a.json"\n  or fail as down'),
    ('use http\nto outer:\n  to inner:\n'
     '    give ask "https://example.com/deep.json"\n  give inner\n\nr = outer'),
    ('use http\nto check:\n'
     '  give count of (ask "https://example.com/flag.json") > 0\n\n'
     'if check:\n  show "yes"'),
    ('use http\nto id of x:\n  give x\n\n'
     'r = id of (ask "https://example.com/arg.json")'),
    ('use http\nxs = [ask "https://example.com/one.json", 2]'),
    ('use http\nr = (ask "https://example.com/rec.json").a'),
    ('use http\nr = later\n\nto later:\n'
     '  give ask "https://example.com/late.json"'),
]


# ================================================================ corpus agreement

def test_effect_surface_agrees_across_the_corpus():
    """The build's central result: for every analysable file, the JS effect
    surface equals shapes.py's, following imports."""
    files = all_planes_files()
    assert len(files) >= 40, len(files)
    checked = 0
    mismatches = []
    for f in files:
        try:
            surface = analyse_file(f, follow=True)
        except (PlanesSyntaxError, ModuleError):
            # Not analysable standalone (ambiguous fixture, multi-file-only,
            # missing module). Parse/module agreement is covered elsewhere.
            continue
        py = as_json(surface, f)
        js = _js_shapes(f, follow=True)
        if js != py:
            mismatches.append(f"{f}:\n  py={json.dumps(py)}\n  js={json.dumps(js)}")
        checked += 1
    assert checked >= 30, f"only {checked} files analysed"
    assert not mismatches, "surface divergences:\n" + "\n".join(mismatches)


def test_the_hn_scraper_surface_agrees():
    """The main event, called out: hn.planes touches network and file, and its
    published surface must match byte for byte (structurally)."""
    py = as_json(analyse_file("hn.planes"), "hn.planes")
    js = _js_shapes("hn.planes")
    assert js == py
    assert "network" in js["boundaries"] and "file" in js["boundaries"]


def test_effect_surface_agrees_on_inline_programs():
    with tempfile.TemporaryDirectory() as d:
        for src in INLINE:
            p = _src_to_tmp(src, d)
            py = as_json(analyse_file(p, follow=False), p)
            js = _js_shapes(p, follow=False)
            assert js == py, (f"src:\n{src}\n  py={json.dumps(py)}\n"
                              f"  js={json.dumps(js)}")


# ================================================================ per-function breakdown

def test_per_function_breakdown_agrees_across_the_corpus():
    checked = 0
    mismatches = []
    for f in all_planes_files():
        try:
            surface = analyse_file(f, follow=True)
        except (PlanesSyntaxError, ModuleError):
            continue
        if not surface.functions:
            continue
        py = _py_functions(surface)
        js = _js_shapes_fn(f, follow=True)
        if js != py:
            mismatches.append(f"{f}:\n  py={json.dumps(py)}\n  js={json.dumps(js)}")
        checked += 1
    assert checked >= 10, checked
    assert not mismatches, "per-function divergences:\n" + "\n".join(mismatches)


def test_per_function_breakdown_agrees_on_inline_programs():
    with tempfile.TemporaryDirectory() as d:
        for src in INLINE:
            p = _src_to_tmp(src, d)
            surface = analyse_file(p, follow=False)
            if not surface.functions:
                continue
            py = _py_functions(surface)
            js = _js_shapes_fn(p, follow=False)
            assert js == py, f"src:\n{src}\n  py={py}\n  js={js}"


# ================================================================ totality (A.1 ruling 1)

TOTALITY = [
    # partially resolvable: a call to a function that does not exist
    "r = mystery of 1",
    # an undeclared foreign contributes `unknown`, not a raise
    'foreign x of a from "m.f"\nr = x of 1',
    # every effect position, nested deeply
    ('use http\nuse file\nto deep of n:\n  if n > 0:\n    for each i in [1, 2]:\n'
     '      write [ask "https://x/" + text of i] to "o" + text of n + ".json"\n'
     '  give n\n\nr = deep of 3'),
    # mutual recursion with an effect
    ('use http\nto a of n:\n  give b of n\n\nto b of n:\n'
     '  give ask "https://example.com/x"\n\nr = a of 1'),
    # a program that is only a bare literal
    "42",
    # a when-expression with binds and matches
    ('to classify of r:\n  when r is { tag: "x", value }:\n    give value\n'
     '  else:\n    give 0\n\nq = classify of { tag: "x", value: 1 }'),
]


def test_analyser_is_total_on_parseable_programs():
    """The analyser never raises on a parseable program (A.1 ruling 1). Every
    case returns a surface on both sides, and the surfaces agree."""
    with tempfile.TemporaryDirectory() as d:
        for src in TOTALITY:
            p = _src_to_tmp(src, d)
            # Python: must not raise.
            surface = analyse_file(p, follow=False)
            py = as_json(surface, p)
            # JS: must not raise (a non-zero exit would make _run raise).
            js = _js_shapes(p, follow=False)
            assert js == py, f"src:\n{src}\n  py={json.dumps(py)}\n  js={json.dumps(js)}"


def test_single_file_view_reports_unresolved_identically():
    """--no-follow admits the calls it cannot see, the same on both sides."""
    py = as_json(analyse_file("demo/app/main.planes", follow=False),
                 "demo/app/main.planes")
    js = _js_shapes("demo/app/main.planes", follow=False)
    assert js == py
    assert js["unresolved_calls"], "must report calls it cannot resolve"


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
