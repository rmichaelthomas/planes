"""The Swift analyser, checked against shapes.py.

The Swift counterpart of test_js_shapes.py, with `planes-swift` in place of
`node js/cli.mjs`. swift/Sources/Planes/Shapes.swift is a port of shapes.py: the
fixed-point effect-surface computation, import following across files
(Modules.swift), constant propagation for destinations, and the StaticDeriv
provenance graph.

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

The analyser must reproduce shapes.py's widening EXACTLY — a Swift analyser more
precise than the Python one is a divergence, not an improvement (A.1 ruling 2).

The last sections have no JavaScript counterpart. One holds the places the
JavaScript analyser parts from shapes.py (a sum of two known numbers widens; a
known list reads as Python's repr, escapes and all). The others are non-ASCII:
targets that differ only by normalisation or sort differently by code point than
by UTF-16 unit, every code point through `text of [...]`, `lower of`, `upper of`
and `normalize of`, final sigma, a CRLF file, non-ASCII file names — where
Swift's canonical-equivalence `String` and its own Unicode tables would part
ways with Python's code points.
"""
import glob
import json
import os
import subprocess
import sys
import tempfile

from modules import ModuleError
from parser import PlanesSyntaxError
from shapes import analyse_file
from shapes_cli import as_json
from swift_host import REPO, SWIFT, command


def _run(args):
    r = subprocess.run(command(*args), cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"planes-swift {args} failed: {r.stderr}")
    return r.stdout


def _swift_shapes(path, follow=True):
    args = ["shapes", path] + ([] if follow else ["--no-follow"])
    return json.loads(_run(args))


def _swift_shapes_fn(path, follow=True):
    args = ["shapes-fn", path] + ([] if follow else ["--no-follow"])
    return json.loads(_run(args))


def _py_functions(surface):
    """The same per-function breakdown Shapes.swift's functionsBreakdown emits:
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


def _src_to_tmp(src, d, name="p.planes"):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(src)
    return p


# ================================================================ inline programs
#
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
    """The build's central result: for every analysable file, the Swift effect
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
        sw = _swift_shapes(f, follow=True)
        if sw != py:
            mismatches.append(f"{f}:\n  py={json.dumps(py)}\n  swift={json.dumps(sw)}")
        checked += 1
    assert checked >= 30, f"only {checked} files analysed"
    assert not mismatches, "surface divergences:\n" + "\n".join(mismatches)


def test_the_hn_scraper_surface_agrees():
    """The main event, called out: hn.planes touches network and file, and its
    published surface must match byte for byte (structurally)."""
    py = as_json(analyse_file("hn.planes"), "hn.planes")
    sw = _swift_shapes("hn.planes")
    assert sw == py
    assert "network" in sw["boundaries"] and "file" in sw["boundaries"]


def test_effect_surface_agrees_on_inline_programs():
    with tempfile.TemporaryDirectory() as d:
        for src in INLINE:
            p = _src_to_tmp(src, d)
            py = as_json(analyse_file(p, follow=False), p)
            sw = _swift_shapes(p, follow=False)
            assert sw == py, (f"src:\n{src}\n  py={json.dumps(py)}\n"
                              f"  swift={json.dumps(sw)}")


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
        sw = _swift_shapes_fn(f, follow=True)
        if sw != py:
            mismatches.append(f"{f}:\n  py={json.dumps(py)}\n  swift={json.dumps(sw)}")
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
            sw = _swift_shapes_fn(p, follow=False)
            assert sw == py, f"src:\n{src}\n  py={py}\n  swift={sw}"


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
            # Swift: must not raise (a non-zero exit would make _run raise).
            sw = _swift_shapes(p, follow=False)
            assert sw == py, f"src:\n{src}\n  py={json.dumps(py)}\n  swift={json.dumps(sw)}"


def test_single_file_view_reports_unresolved_identically():
    """--no-follow admits the calls it cannot see, the same on both sides."""
    py = as_json(analyse_file("demo/app/main.planes", follow=False),
                 "demo/app/main.planes")
    sw = _swift_shapes("demo/app/main.planes", follow=False)
    assert sw == py
    assert sw["unresolved_calls"], "must report calls it cannot resolve"


# ============================================= where shapes.py, not JavaScript, is the reference

# js/shapes.mjs folds a sum of two known numbers and escapes only five characters
# in a known list's repr; shapes.py does neither, and Shapes.swift follows it.
PYTHON_REFERENCE = [
    # a sum of two known numbers widens: shapes.py's numeric test never sees a Number
    'use http\nlet n = 1 + 2\nx = ask "https://x/" + text of n\n',
    'use http\nx = ask "https://x/" + text of (2 + 0.5)\n',
    # a known list reads as Python's repr, every non-printable escaped
    ('use http\nx = ask text of ["a\\tb", "c\u00a0d", "\u200b\u2028\U000e0001", "it\'s", '
     '"\\"q\\"", "\\\\"]\n'),
    'use http\nx = ask text of { k: "\u0085", n: 2, b: true, l: [1, "\U0010ffff"] }\n',
    'use http\nx = ask text of ({ a: "x", b: 1 } with a: "\u00e9", c: false)\n',
    'use http\nx = ask lower of [true, "\u0130"]\ny = ask upper of { k: 0.25 }\n',
    'use http\nx = ask text of ["it\'s \\"both\\""]\ny = ask text of ([] plus "\u3000")\n',
]


def test_the_analyser_follows_shapes_py_where_js_does_not():
    with tempfile.TemporaryDirectory() as d:
        for src in PYTHON_REFERENCE:
            p = _src_to_tmp(src, d)
            py = as_json(analyse_file(p, follow=False), p)
            sw = _swift_shapes(p, follow=False)
            assert sw == py, (f"src:\n{src}\n  py={json.dumps(py)}\n"
                              f"  swift={json.dumps(sw)}")


# ================================================================ non-ASCII text

NON_ASCII = [
    # targets equal under canonical equivalence but not by code point: two effects
    'use http\nx = ask "https://caf\u00e9.example"\ny = ask "https://cafe\u0301.example"\n',
    # code-point order is not UTF-16 order, nor Swift's String order
    ('use http\nx = ask "https://x/\uff41"\ny = ask "https://x/\U0001f600"\n'
     'z = ask "https://x/\u00e9"\nw = ask "https://x/e\u0301"\n'),
    # a combining mark joining a known prefix
    'use http\nlet base = "https://e"\nx = ask base + "\u0301/p"\n',
    # a computed target around non-ASCII text
    ('use http\nto get of n:\n  give ask "https://\u00fc/" + n + "/\U0001f600"\n\n'
     'xs = for each i in ["a"]: get of i\n'),
    # final sigma, special casing, and a case-ignorable run before sigma
    ('use http\nx = ask lower of "\u039f\u0394\u039f\u03a3 \u039f\u0394\u039f\u03a3."\n'
     'y = ask upper of "stra\u00dfe \ufb03 \u0149"\n'
     'z = ask lower of "\u0130\u03a3\u0345a A\u03a3\u0301 \u03a3 a\u00ad\u03a3\u00ad"\n'),
    # normalize composes across marks
    'use http\nx = ask normalize of "A\u030a e\u0301 \u1e9b\u0323 \u1100\u1161\u11a8 \u2126"\n',
    # a long run of combining marks with one that decomposes (Foundation's NFC
    # drops it), Kirat Rai's Unicode 16 composites, and Hangul jamo
    ('use http\nx = ask normalize of "a' + "\u0301" * 70 + '\u0340\u0344"\n'
     'y = ask normalize of "\U00016d67\U00016d67\U00016d63\U00016d67\U00016d67"\n'
     'z = ask normalize of "\u1100\u1161\u11a8 \uac00\u11a8 \u0b47\u0b3e"\n'),
    # join and rest of known lists
    ('use http\nx = ask join of ["\U0001f468", "\u200d", "\U0001f469"]\n'
     'y = ask text of (rest of ["a", "\u00e9"])\n'),
    # a foreign's literal and parameter claims
    ('foreign f of u from "m.\u00e9" doing ask "https://\u210c", write u\n'
     'r = f of "\u00fc\u0301.json"\n'),
    # a function specialised on a non-ASCII argument, called twice
    ('use file\nto save of name:\n  write [1] to name + ".json"\n\n'
     'save of "\u00e9"\nsave of "e\u0301"\n'),
    # console text
    'show "\U0001f468\u200d\U0001f469\u200d\U0001f467"\nshow "\u00e9"\nshow "e\u0301"\n',
]


def test_non_ascii_targets_agree():
    with tempfile.TemporaryDirectory() as d:
        for src in NON_ASCII:
            p = _src_to_tmp(src, d)
            py = as_json(analyse_file(p, follow=False), p)
            sw = _swift_shapes(p, follow=False)
            assert sw == py, (f"src:\n{src!r}\n  py={json.dumps(py)}\n"
                              f"  swift={json.dumps(sw)}")
            sf = _swift_shapes_fn(p, follow=False)
            pf = _py_functions(analyse_file(p, follow=False))
            assert sf == pf, f"src:\n{src!r}\n  py={pf}\n  swift={sf}"


def _string_literal(cps):
    out = []
    for c in cps:
        ch = chr(c)
        out.append({'"': '\\"', "\\": "\\\\", "\n": "\\n", "\t": "\\t"}.get(ch, ch))
    return '"' + "".join(out) + '"'


def _probe_code_points():
    """Every code point of planes 0-3 and 14, where Unicode assigns characters,
    and every 256th of the rest (unassigned or private use), with each end —
    all but the surrogates and the carriage return."""
    def wanted(c):
        if 0xD800 <= c < 0xE000 or c == 0x0D:
            return False
        return c < 0x40000 or 0xE0000 <= c < 0xF0000 or c % 0x100 in (0, 0xFF)
    return [c for c in range(0x110000) if wanted(c)]


def _first_difference(py, sw):
    for i, (a, b) in enumerate(zip(py, sw)):
        if a != b:
            return (f"at {i}: py {a!r} (U+{ord(a):04X}) vs swift {b!r} (U+{ord(b):04X}) "
                    f"in ...{py[max(0, i - 20):i + 20]!r}")
    return f"lengths {len(py)} vs {len(sw)}"


def test_every_code_point_reads_as_python_reads_it():
    """`text of [...]` is Python's repr, `lower of` / `upper of` its str.lower
    and str.upper, `normalize of` its NFC — each at Python's Unicode version, not
    the platform's (PythonUnicode.swift). Every code point goes through all four,
    in chunks — so runs of combining marks and adjacent composable pairs are
    normalised in context too — except the surrogates and the carriage return,
    which Python's text-mode read would turn into a newline, and planes 4 to 13
    and 15 to 16, which hold no assigned character but private use and are
    sampled."""
    cps = _probe_code_points()
    step = 0x10000
    lines = ["use http"]
    for n, i in enumerate(range(0, len(cps), step)):
        lit = _string_literal(cps[i:i + step])
        lines.append(f"r{n} = ask text of [{lit}]")
        lines.append(f"l{n} = ask lower of {lit}")
        lines.append(f"u{n} = ask upper of {lit}")
        lines.append(f"n{n} = ask normalize of {lit}")
    with tempfile.TemporaryDirectory() as d:
        p = _src_to_tmp("\n".join(lines) + "\n", d)
        py = as_json(analyse_file(p, follow=False), p)
        sw = _swift_shapes(p, follow=False)
    pt = [e["target"] for e in py["effects"]]
    st = [e["target"] for e in sw["effects"]]
    assert len(pt) == len(st), f"{len(pt)} effects in py, {len(st)} in swift"
    for a, b in zip(pt, st):
        assert a == b, _first_difference(a, b)
    assert sw == py


def test_final_sigma_reads_every_neighbour_as_python_does():
    """str.lower() picks final sigma by whether the characters around it are
    cased or case-ignorable — two more per-code-point properties, at Python's
    Unicode version. Each code point stands before a capital sigma ("AcΣ0") and
    after one ("AΣc0"); the digit ends each probe, neither cased nor ignorable."""
    cps = _probe_code_points()
    step = 0x10000
    lines = ["use http"]
    for n, i in enumerate(range(0, len(cps), step)):
        probes = [f"A{chr(c)}\u03a30A\u03a3{chr(c)}0" for c in cps[i:i + step]]
        lines.append(f"s{n} = ask lower of {_string_literal([ord(x) for x in ''.join(probes)])}")
    with tempfile.TemporaryDirectory() as d:
        p = _src_to_tmp("\n".join(lines) + "\n", d)
        py = as_json(analyse_file(p, follow=False), p)
        sw = _swift_shapes(p, follow=False)
    pt = [e["target"] for e in py["effects"]]
    st = [e["target"] for e in sw["effects"]]
    assert len(pt) == len(st), f"{len(pt)} effects in py, {len(st)} in swift"
    for a, b in zip(pt, st):
        assert a == b, _first_difference(a, b)


def test_line_endings_are_read_as_python_reads_them():
    """shapes.py reads a file in text mode: CRLF and a lone CR are newlines."""
    with tempfile.TemporaryDirectory() as d:
        for src in ['use http\r\nx = ask "https://a"\r\nshow "b"\ry = ask "https://c"\r',
                    '\ufeffuse http\r\nto f:\r\n  give ask "https://\u00e9"\r\n\r\nr = f\r\n']:
            p = _src_to_tmp(src, d)
            py = as_json(analyse_file(p, follow=False), p)
            assert _swift_shapes(p, follow=False) == py
            assert _swift_shapes(p, follow=True) == as_json(analyse_file(p, follow=True), p)


def test_non_ascii_paths_follow_imports():
    """A program in a directory whose name differs from another only by
    normalisation, importing a module beside it: the graph is keyed and
    compared by code point."""
    with tempfile.TemporaryDirectory() as d:
        for dirname in ["caf\u00e9", "cafe\u0301", "\U0001f600 dir"]:
            sub = os.path.join(d, dirname)
            os.makedirs(sub, exist_ok=True)
            lib = 'use http\nto fetch of u:\n  give ask "https://\u00e9/" + u\n'
            _src_to_tmp(lib, sub, "lib.planes")
            p = _src_to_tmp('use lib\nuse http\nx = fetch of "\u00fc"\n', sub, "m\u00e4in.planes")
            py = as_json(analyse_file(p, follow=True), p)
            sw = _swift_shapes(p, follow=True)
            assert sw == py, f"{p!r}:\n  py={json.dumps(py)}\n  swift={json.dumps(sw)}"
            assert sw["program"] == "m\u00e4in.planes"


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
