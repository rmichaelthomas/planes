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


# ======================================================= non-ASCII source: Python's semantics

NON_ASCII = [
    # digits of other scripts are NUMBER tokens, and exact numbers
    ("x = \u0663\n", None),
    ("x = \u0663 + \u0661\u0662.\u0665 * \uff11\uff12 - \U0001d7d9\n", None),
    ("x = \u0661\u0662.\u0665 + \U0001d7d9\U0001d7d8 * \uff13\n", None),
    ("y = \u0967\u0966\u0966 - \u0e52.\u0e55\u0e50\n", None),
    # Python's whitespace indents a block
    ("if yes:\n\x1cshow 1\n\x1cshow 2\nshow 3\n", None),
    ("to f of a:\n\u3000give a\nshow f of \u0664\n", None),
    # a byte-order mark, and CRLF line endings around a statement
    ("\ufeffx = 1\nshow x\n", None),
    ("\ufeff# a comment\nx = 1\n", None),
    ("\ufeffx = 1\r\ny = 2\r\n", None),
    # combining marks and emoji inside strings, next to the quotes and escapes
    ('show "e\u0301 \U0001f468\u200d\U0001f469\u200d\U0001f467 \\"q\\" \\\\ \\t \\n"\n', None),
    ('show "\u0301"\nshow "a\u0301"\nshow "\U0001f600"\n', None),
    # annotations, targets and fingerprints carrying non-ASCII text
    ('rule [r] x may not ask to "\u00fc\u0301" supersedes [q] @abcdef '
     'because "\U0001f600"\n', None),
    ('foreign f of u from "m.\u00e9" doing ask "\u210c", write u\n', None),
    ('note: from "\u540d\u524d"\n', None),
    ('r = { a: "\u00e9", b: [\U0001f600] }\n', None),
    # messages that quote non-ASCII token values
    ('let "na\u00efve \U0001f600" = 1\n', None),
    ('x = { "\u00e9": 1 }\n', None),
    ("rule [r] x may not ask supersedes [q] @\u0663\u0664\n", None),
    # amber readings built from non-ASCII token text
    ('x = remote ("\u00e9\U0001f468\u200d\U0001f469\u200d\U0001f467") + 2\n', {"remote"}),
    ('x = remote ("\u00e9\u0301") + 2\n', {"remote": 1}),
    ('to word:\n  give 1\n\nto word count:\n  give 2\n\nr = word count "\U0001f600" + 1\n',
     None),
]


def test_non_ascii_programs_parse_and_refuse_identically():
    """lexer.py reads `\\d` as any Unicode decimal digit and indentation as
    Python's whitespace, and parser.py hands a NUMBER token to Fraction(), which
    reads a digit of any script as its value. A NUMBER `٣` used to be skipped by
    js/lexer.mjs — so `supersedes [q] @٣٤` said `found 'end of line'` where
    parser.py says `found '٣٤'` — and one that reached js/planes_num.mjs threw
    from BigInt; a U+001C indent opened no block; a leading byte-order mark
    opened one. The cases test_swift_parser.py drives, and these."""
    for src, known in NON_ASCII:
        try:
            py = canonical_program(parse(src, known))
        except PlanesSyntaxError as e:
            py = json.dumps({"error": type(e).__name__, "message": str(e)})
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.planes")
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(src)
            js = _js_ast_file(p, _known_json(known))
        if js.startswith('{"error"'):
            jd = json.loads(js)
            js = json.dumps({"error": jd["error"], "message": jd["message"]})
        assert js == py, f"src:\n{src!r}\n  py={py[:300]!r}\n  js={js[:300]!r}"


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
