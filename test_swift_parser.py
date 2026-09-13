"""The Swift parser, checked against parser.py.

The Swift counterpart of test_js_parser.py, with `planes-swift` in place of
`node js/cli.mjs`. swift/Sources/Planes/Parser.swift is a port of parser.py,
including the four amber disambiguation sites. This test:

  * parses every .planes file in the repo with both implementations and compares
    canonical AST forms (A.3, reusing test_parser_in_planes.py's form), passing
    the identical cross-file `known` mapping to both parsers the way
    scripts/parser_corpus_agreement.py does;
  * confirms all four amber sites fire identically on the synthetic ambiguous
    fixtures the Planes parser build wrote (probe/amber/site{1..4}), with both
    readings named — the corpus fire rate is zero, so this is the only way to
    exercise the sites (Phase 4);
  * ports test_amber.py's inline fire and near-miss scenarios for every site,
    including the unknown-arity variants, and checks the Swift refusal message is
    byte-identical to parser.py's.

The last two sections have no JavaScript counterpart. One drives every raise
site in parser.py that the corpus never reaches, so each message is compared
byte for byte rather than only the ones a corpus file happens to trip. The
other parses non-ASCII programs — digits of other scripts in number literals,
combining marks and emoji in strings, messages quoting them — where Swift's
grapheme-cluster `String` and Python's code points would part ways.
"""
import glob
import json
import os
import subprocess
import sys
import tempfile

from parser import PlanesAmbiguity, PlanesSyntaxError, parse
from scripts.parser_corpus_agreement import cross_file_known
from swift_host import REPO, SWIFT, command
from test_parser_in_planes import canonical_program


def _swift_ast_file(path, known):
    args = command("ast", path)
    if known is not None:
        args.append(json.dumps(known))
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"planes-swift failed on {path}: {r.stderr}")
    return r.stdout


def _swift_ast_src(src, known):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "p.planes")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(src)
        return _swift_ast_file(p, _known_json(known))


def _known_json(known):
    """Normalise a `known` (dict, set, or None) to the JSON object the CLI
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
        sout = _swift_ast_file(f, known)
        if py_err is not None:
            try:
                sd = json.loads(sout)
            except json.JSONDecodeError:
                mismatches.append(f"{f}: py raised {py_err[0]}, swift produced a form")
                continue
            if (sd.get("error"), sd.get("message")) != py_err:
                mismatches.append(
                    f"{f}: error mismatch\n  py={py_err}\n  swift=({sd.get('error')!r}, "
                    f"{sd.get('message')!r})")
            continue
        if sout.startswith('{"error"'):
            mismatches.append(f"{f}: swift raised but py produced a form: {sout[:160]}")
            continue
        if sout != py_form:
            pl, sl = py_form.split("\n"), sout.split("\n")
            i = next((k for k in range(min(len(pl), len(sl))) if pl[k] != sl[k]),
                     min(len(pl), len(sl)))
            py_line = pl[i] if i < len(pl) else None
            swift_line = sl[i] if i < len(sl) else None
            mismatches.append(
                f"{f}: first divergence line {i}\n  py={py_line!r}\n  swift={swift_line!r}")
    assert not mismatches, "AST divergences:\n" + "\n".join(mismatches)


def test_the_swift_parser_parses_the_interpreter_to_an_identical_ast():
    """grammar/interp.planes — the ~1400-line interpreter, 117 top-level nodes
    — parses identically. The strongest single-file parser agreement case."""
    py_form, py_err, known = _py_form_and_known("grammar/interp.planes")
    assert py_err is None, py_err
    assert _swift_ast_file("grammar/interp.planes", known) == py_form


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
        sd = json.loads(_swift_ast_file(f, None))
        assert sd.get("error") == "PlanesAmbiguity", f"{f}: swift did not fire amber: {sd}"
        assert sd["message"] == py_msg, f"{f}:\n  py={py_msg!r}\n  swift={sd['message']!r}"
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
        sd = json.loads(_swift_ast_src(src, known))
        assert sd.get("error") == "PlanesAmbiguity", f"swift did not fire on:\n{src}\n{sd}"
        assert sd["message"] == py_msg, f"src:\n{src}\n  py={py_msg!r}\n  swift={sd['message']!r}"


def test_inline_amber_near_misses_parse_clean_and_identically():
    for src, known in AMBER_CLEAN:
        py_form = canonical_program(parse(src, known))
        sout = _swift_ast_src(src, known)
        assert not sout.startswith('{"error"'), f"swift refused a near-miss:\n{src}\n{sout[:160]}"
        assert sout == py_form, f"src:\n{src}\n  divergence"


# ============================================ every raise site, message for message

# Sources that reach each PlanesSyntaxError raise in parser.py, most of which no
# corpus file trips: the generic token gate with and without a fix clause, the
# keyword and builtin collisions in every binding position, the effect-word
# check in both of its positions, each rule / note / because / supersedes /
# fingerprint refusal, the name-table prescan's two reserved-word refusals, and a
# lexer refusal arriving through `ast`.
SYNTAX_ERRORS = [
    "let if = 1\n",
    "x = { k: f of a, k2: 9 }\n",
    "x = (1\n",
    "when x is 3\n",
    'fail "m"\n',
    "write 1\n",
    "count = 1\n",
    "let rest = 1\n",
    "to f of count:\n  give 1\n",
    "x = 1 or fail as text\n",
    "for each lower in xs:\n  show 1\n",
    "when r is { upper }:\n  show 1\n",
    'foreign f of x from "m.f" doing ask y\n',
    'foreign f from "m.f" doing ask y\n',
    'foreign f of x from "m.f" doing frobnicate\n',
    'foreign f of x from "m.f" doing\n',
    "rule [r] anything may not nothing\n",
    "rule [r] anything may 7\n",
    "rule r x may not ask\n",
    'rule ["r"] x may not ask\n',
    "rule [r] x must not ask\n",
    "rule [r] x\n",
    "rule [r] x may not ask supersedes q\n",
    "rule [r] x may not ask supersedes [1]\n",
    "rule [r] x may not ask supersedes [q] @12\n",
    "rule [r] x may not ask supersedes [q] @\n",
    "x = 1 because 2\n",
    "x = 1\n  because\n",
    "note: from 1\n",
    "note: derives-from x\n",
    "note: derives-from [1]\n",
    "note: hello\n",
    'note:\n  from "a"\n  7\n',
    "x = s[1]\n",
    'use m with "a" as b\n',
    "use m with a as\n",
    "x = { 1: 2 }\n",
    "when x is { 1 }:\n  show 1\n",
    "x = { a: 1, a: 2 }\n",
    "x = show\n",
    "x =\n",
    "x = r.\n",
    "to if:\n  give 1\n",
    "to get first:\n  give 1\n",
    "to dawn and dusk:\n  give 1\n",
    "to\n",
    'x = "abc\n',
]

# Clean programs through the grammar's less common paths: wrapped `for each`
# headers, wrapped `or fail` with a handler, wrapped `because`, a bracket literal
# spanning an indent (pending_ends), fingerprints, note blocks, keyword field
# names, `with` chains, `when ... else` ladders, and every `doing` claim shape.
CLEAN = [
    "ys = for each s in xs\n  where s > 1: s * 2\n",
    "ys = for each s in xs:\n  s + 1\n",
    'x = ask "u"\n  or fail as oops:\n    show oops.tag\n',
    'cap = 200\n  because "the reason"\n',
    "to f:\n  xs = [\n    1,\n    2,\n  ]\n  give xs\nshow f\n",
    "to f:\n  xs = [1,\n    2]\n  r = { a: 1,\n      b: 2 }\n  give xs\nshow f\n",
    'rule [a] anything may not ask to "x.com"\n'
    'rule [b] anything may ask supersedes [a] @3f9c2d because "ok"\n',
    'note:\n  from "somewhere"\n  derives-from [a]\n',
    "note: derives-from [a]\n",
    'r = { to: 1, from: 2, in: 3 }\nshow r.to + r.first\n',
    "p = q with a: 1, b: 2 with c: 3\n",
    "when r is { kind: \"a\", v }:\n  show v\nelse:\n  when r is {}:\n    show 0\n  else: show 1\n",
    'foreign f of u, v from "m.f" doing ask u, write "p", read, show\n',
    'foreign g from "m.g" doing nothing\n',
    "x = round 1.25 to 1 places\ny = first 2 of xs plus 3\n",
    "z = not a is nothing and b in c or d != e\n",
    "x = -1 - -2 * (3 / 4)\n",
    "if a: show 1\nelse: show 2\n",
    'why x\ngive 1\nfail "m" as boom\nwrite x to "p" or fail as nope\n',
]


def _py_result(src, known=None):
    try:
        return canonical_program(parse(src, known))
    except PlanesSyntaxError as e:
        return {"error": type(e).__name__, "message": str(e)}


def _agree(src, known=None):
    want = _py_result(src, known)
    got = _swift_ast_src(src, known)
    if isinstance(want, dict):
        try:
            got = json.loads(got)
        except json.JSONDecodeError:
            raise AssertionError(
                f"py raised, swift produced a form:\n{src}\n  py={want!r}") from None
        assert got == want, f"src:\n{src}\n  py={want!r}\n  swift={got!r}"
    else:
        assert got == want, f"src:\n{src}\n  py=\n{want}\n  swift=\n{got}"
    return want


def test_every_raise_site_refuses_with_an_identical_message():
    for src in SYNTAX_ERRORS:
        want = _agree(src)
        assert isinstance(want, dict), f"parser.py parsed an error scenario:\n{src}"


def test_the_less_common_grammar_paths_parse_identically():
    for src in CLEAN:
        want = _agree(src)
        assert not isinstance(want, dict), f"parser.py refused a clean scenario:\n{src}\n{want}"


# ============================================ non-ASCII programs: code points, not graphemes

UNICODE = [
    # digits of other scripts are NUMBER tokens, and exact numbers
    ("x = \u0663 + \u0661\u0662.\u0665 * \uff11\uff12 - \U0001d7d9\n", None),
    # combining marks and emoji inside strings, next to the quotes and escapes
    ('show "e\u0301 \U0001f468\u200d\U0001f469\u200d\U0001f467 \\"q\\" \\\\ \\t \\n"\n', None),
    ('show "\u0301"\nshow "a\u0301"\nshow "\U0001f600"\n', None),
    # a byte-order mark and CRLF line endings around a statement
    ("\ufeffx = 1\r\ny = 2\r\n", None),
    # annotations, targets and fingerprints carrying non-ASCII text
    ('rule [r] x may not ask to "\u00fc\u0301" supersedes [q] @abcdef '
     'because "\U0001f600"\n', None),
    ('foreign f of u from "m.\u00e9" doing ask "\u210c", write u\n', None),
    ('note: from "\u540d\u524d"\n', None),
    ('r = { a: "\u00e9", b: [\U0001f600] }\n', None),
    # messages that quote non-ASCII token values
    ('let "na\u00efve \U0001f600" = 1\n', None),
    ('x = { "\u00e9": 1 }\n', None),
    ('rule [r] x may not ask supersedes [q] @\u0663\u0664\n', None),
    # amber readings built from non-ASCII token text
    ('x = remote ("\u00e9\U0001f468\u200d\U0001f469\u200d\U0001f467") + 2\n', {"remote"}),
    ('x = remote ("\u00e9\u0301") + 2\n', {"remote": 1}),
    ('to word:\n  give 1\n\nto word count:\n  give 2\n\nr = word count "\U0001f600" + 1\n', None),
]


def test_non_ascii_programs_parse_and_refuse_identically():
    for src, known in UNICODE:
        _agree(src, known)


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
