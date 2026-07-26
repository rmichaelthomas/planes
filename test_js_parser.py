"""S4, Phase 4 — the JS parser, checked against parser.py.

js/parser.mjs is a port of parser.py, including the four amber disambiguation
sites. This test:

  * parses every .planes file in the repo with both implementations and compares
    canonical AST forms (A.3, reusing test_parser_in_planes.py's form), passing
    the identical cross-file `known` mapping to both parsers the way
    scripts/parser_corpus_agreement.py does;
  * confirms all four amber sites fire identically on the synthetic ambiguous
    fixtures the Planes parser build wrote (probe/amber/site{1..4}), with both
    readings named — the corpus fire rate is zero, so this is the only way to
    exercise the sites (Phase 4);
  * ports test_amber.py's inline fire and near-miss scenarios for every site,
    including the unknown-arity variants, and checks the JS refusal message is
    byte-identical to parser.py's.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

from parser import PlanesAmbiguity, PlanesSyntaxError, parse
from scripts.parser_corpus_agreement import cross_file_known
from test_parser_in_planes import canonical_program

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))


def _js_ast_file(path, known):
    args = [NODE, "js/cli.mjs", "ast", path]
    if known is not None:
        args.append(json.dumps(known))
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"node failed on {path}: {r.stderr}")
    return r.stdout


def _js_ast_src(src, known):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "p.planes")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(src)
        return _js_ast_file(p, _known_json(known))


def _known_json(known):
    """Normalise a `known` (dict, set, or None) to the JSON object the JS CLI
    takes: name -> arity, with null for a set member (unknown arity)."""
    if known is None:
        return None
    if isinstance(known, dict):
        return dict(known)
    return {name: None for name in known}


def _py_form_and_known(path):
    """Mirror parser_corpus_agreement.run(): standalone parse, else cross-file
    known. Returns (form_or_None, error_or_None, known)."""
    src = open(path, encoding="utf-8").read()
    try:
        return canonical_program(parse(src)), None, None
    except (PlanesAmbiguity, PlanesSyntaxError):
        pass
    known = cross_file_known(path)
    try:
        return canonical_program(parse(src, known)), None, known
    except (PlanesAmbiguity, PlanesSyntaxError) as e:
        return None, (type(e).__name__, str(e)), known


# ================================================================ full-corpus AST agreement

def test_every_planes_file_parses_to_an_identical_ast():
    files = sorted(
        f for f in glob.glob("**/*.planes", recursive=True) if ".venv" not in f)
    assert len(files) >= 40, len(files)
    mismatches = []
    for f in files:
        py_form, py_err, known = _py_form_and_known(f)
        jout = _js_ast_file(f, known)
        if py_err is not None:
            try:
                jd = json.loads(jout)
            except json.JSONDecodeError:
                mismatches.append(f"{f}: py raised {py_err[0]}, js produced a form")
                continue
            if (jd.get("error"), jd.get("message")) != py_err:
                mismatches.append(
                    f"{f}: error mismatch\n  py={py_err}\n  js=({jd.get('error')!r}, "
                    f"{jd.get('message')!r})")
            continue
        if jout.startswith('{"error"'):
            mismatches.append(f"{f}: js raised but py produced a form: {jout[:160]}")
            continue
        if jout != py_form:
            pl, jl = py_form.split("\n"), jout.split("\n")
            i = next((k for k in range(min(len(pl), len(jl))) if pl[k] != jl[k]),
                     min(len(pl), len(jl)))
            py_line = pl[i] if i < len(pl) else None
            js_line = jl[i] if i < len(jl) else None
            mismatches.append(
                f"{f}: first divergence line {i}\n  py={py_line!r}\n  js={js_line!r}")
    assert not mismatches, "AST divergences:\n" + "\n".join(mismatches)


def test_the_js_parser_parses_the_interpreter_to_an_identical_ast():
    """grammar/interp.planes — the ~1400-line interpreter, 117 top-level nodes
    — parses identically. The strongest single-file parser agreement case."""
    py_form, py_err, known = _py_form_and_known("grammar/interp.planes")
    assert py_err is None, py_err
    assert _js_ast_file("grammar/interp.planes", known) == py_form


# ================================================================ the four amber fixtures

AMBER_FIXTURES = [
    "probe/amber/site1_multiword.planes",
    "probe/amber/site2_juxtaposition.planes",
    "probe/amber/site3_paren_arglist.planes",
    "probe/amber/site4_rename.planes",
]


def test_all_four_amber_fixtures_fire_identically_with_both_readings_named():
    for f in AMBER_FIXTURES:
        src = open(f, encoding="utf-8").read()
        try:
            parse(src)
            raise AssertionError(f"{f}: parser.py did not fire amber")
        except PlanesAmbiguity as e:
            py_msg = str(e)
        jd = json.loads(_js_ast_file(f, None))
        assert jd.get("error") == "PlanesAmbiguity", f"{f}: js did not fire amber: {jd}"
        assert jd["message"] == py_msg, f"{f}:\n  py={py_msg!r}\n  js={jd['message']!r}"
        # both readings are lettered A and B in the shared message
        assert "reading A" in py_msg and "reading B" in py_msg, f"{f}: readings not named"


# ============================================ inline site scenarios (fire + near-miss)

# (source, known) that MUST fire amber — sites 1, 1 (two extensions), 2, 2
# (unknown arity), 3, 3 (unknown arity), 4.
AMBER_FIRE = [
    ("to word:\n  give 1\n\nto word count:\n  give 2\n\nr = word count\n", None),
    ("to a b:\n  give 1\n\nto a b c:\n  give 2\n\nr = a b c\n", None),
    ("to main:\n  give 1\n\nr = ask main\n", None),
    ("r = remote thing\n", {"remote"}),
    ('use http\nto base:\n  give "https://x.com"\n\nx = ask (base) + "/y"\n', None),
    ("x = remote (1) + 2\n", {"remote"}),
    ("use cache with load record as cached load", {"load", "load record"}),
]

# (source, known) that MUST parse clean — the near-misses across all four sites.
AMBER_CLEAN = [
    ("to word count:\n  give 2\n\nr = word count\n", None),        # site 1, only longer
    ("to word:\n  give 1\n\nr = word\n", None),                    # site 1, only shorter
    ("to main:\n  give 1\n\nto other:\n  give 2\n\nmain\nother\n", None),  # site 2, arity 0
    ("use http\nx = ask url\n", None),                            # site 2, next not callable
    ("to add of a, b:\n  give a + b\n\nr = add (1) + 2\n", None),  # site 3, arity 2
    ("to main:\n  give 1\n\nr = main + 1\n", None),               # site 3, arity 0
    ("to add of a, b:\n  give a + b\n\nr = add(1, 2)\n", None),    # site 3, plain arglist
    ("use cache with load record as cached load", {"load record"}),  # site 4, unambiguous
    ("use b with greet as greet cached", {"greet", "greet b"}),   # site 4, alias not a lookup
]


def test_inline_amber_fire_scenarios_refuse_with_identical_messages():
    for src, known in AMBER_FIRE:
        try:
            parse(src, known)
            raise AssertionError(f"parser.py did not fire on:\n{src}")
        except PlanesAmbiguity as e:
            py_msg = str(e)
        jd = json.loads(_js_ast_src(src, known))
        assert jd.get("error") == "PlanesAmbiguity", f"js did not fire on:\n{src}\n{jd}"
        assert jd["message"] == py_msg, f"src:\n{src}\n  py={py_msg!r}\n  js={jd['message']!r}"


def test_inline_amber_near_misses_parse_clean_and_identically():
    for src, known in AMBER_CLEAN:
        py_form = canonical_program(parse(src, known))
        jout = _js_ast_src(src, known)
        assert not jout.startswith('{"error"'), f"js refused a near-miss:\n{src}\n{jout[:160]}"
        assert jout == py_form, f"src:\n{src}\n  divergence"


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
