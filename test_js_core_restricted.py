"""The core-restricted mode — is the declared core enough to run interp.planes?

grammar/core.json declares the PORT SURFACE: the keywords and builtins a second
host must implement in order to run grammar/interp.planes. core_check.py has
always enforced one direction of that claim — that interp.planes never MENTIONS
a construct outside the declared core. Nothing has ever enforced the converse,
which is the claim the file actually makes: THAT THE DECLARED CORE IS ENOUGH.

Sufficiency is testable one way. Build a host that implements the core and
refuses everything else, run interp.planes on it, and see what happens. That is
js/interp.mjs's `coreOnly` mode, and this is its suite.

WHAT IT PINS

  * the restriction fires AT EVALUATION, not by reading the source. A token
    pre-pass would only restate core_check.py in a second language; the whole
    point is the converse claim, which only a run can answer. Every assertion
    here goes through a real run.
  * it names the construct, the file and the line, and the line is exact — not
    the enclosing statement's — for `let`, `when` and `why`, the three excluded
    keywords whose AST nodes carry no line of their own.
  * it is OFF BY DEFAULT and identical when off.
  * all seven effect kinds pass. `core.json` sets `effect_kinds_all_core` and
    core_check.py never flags one; neither does this.
  * BOTH READERS AGREE. core_check.py and the JavaScript mode read the same
    grammar/core.json and must classify every keyword and every builtin the same
    way. Asserted here rather than assumed.
  * the node -> keyword map is COMPLETE. A keyword no AST node carries is a
    construct the restricted mode is structurally blind to, and blindness is
    exactly how a sufficiency checker passes vacuously.

THE ANSWER IT RECORDS. The declared core is NOT sufficient. interp.planes
conforms; `grammar/lexer.planes`, which it reaches through `use parser`, does
not — it dispatches on record shape with `when`, sixteen times, and all sixteen
are reached at evaluation time. See core-sufficiency-report.md. The test below
pins the finding rather than the absence of one, so the day it changes, this
says so.
"""
import glob
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile

import core_check
from lexer import KEYWORDS
from parser import BUILTIN_NAMES

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))
LEXER = os.path.join("grammar", "lexer.planes")


def _cli(*args):
    r = subprocess.run([NODE, "js/cli.mjs", *args], cwd=REPO,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"node cli.mjs {args}: {r.stderr[:600]}"
    return json.loads(r.stdout)


def _run_source(src, *flags, config=None):
    """Write `src` to a real file and run it through run-file, so a refusal has
    a file and a line to name. A restricted run reports `core`; an unrestricted
    one does not."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "probe.planes")
        with open(p, "w", encoding="utf-8") as f:
            f.write(src)
        args = ["run-file", *flags, p]
        if config is not None:
            args.append(json.dumps(config))
        # realpath while the directory still exists: on macOS /var is a symlink
        # to /private/var, and the refusal reports the resolved form.
        return _cli(*args), os.path.realpath(p)


# ===================================================== A — the restriction fires

def test_let_is_refused_at_evaluation_and_names_construct_file_and_line():
    src = ("total = 0\n"
           "for each n in [1, 2, 3]:\n"
           "  let doubled = n * 2\n"
           "  total = total + doubled\n"
           "show total\n")
    got, path = _run_source(src, "--core")
    assert "core" in got, f"expected a refusal, got {got}"
    c = got["core"]
    assert c["construct"] == "let", c
    assert c["category"] == "keyword", c
    assert os.path.realpath(c["file"]) == path, (c["file"], path)
    assert c["line"] == 3, f"`let` is on line 3, refusal said {c['line']}"
    assert c["approximateLine"] is False, "the line must be the construct's own"
    assert not got["output"], "a refusal must not also produce output"


def test_the_same_program_runs_clean_with_the_flag_off():
    src = ("total = 0\n"
           "for each n in [1, 2, 3]:\n"
           "  let doubled = n * 2\n"
           "  total = total + doubled\n"
           "show total\n")
    got, _ = _run_source(src)
    assert "core" not in got, got
    assert got["output"] == ["12"], got


def test_when_and_why_are_refused_and_report_their_own_line():
    """The two other excluded keywords whose nodes carry no `line` field. If the
    parser's line stamp regressed, these would report an enclosing statement's
    line and `approximateLine` would be true."""
    for src, word, line in (
            ("v = { kind: \"a\" }\n"
             "when v is { kind: \"a\" }:\n"
             "  show \"matched\"\n", "when", 2),
            ("x = 1 + 1\nwhy x\n", "why", 2)):
        got, _ = _run_source(src, "--core")
        assert "core" in got, (word, got)
        assert got["core"]["construct"] == word, got["core"]
        assert got["core"]["line"] == line, (word, got["core"])
        assert got["core"]["approximateLine"] is False, got["core"]


def test_a_non_core_builtin_is_refused_by_name():
    for word in sorted(set(BUILTIN_NAMES) - set(core_check.load_core()[1])):
        got, _ = _run_source(f"show {word} of 9\n", "--core")
        assert "core" in got, (word, got)
        assert got["core"]["construct"] == word, got["core"]
        assert got["core"]["category"] == "builtin", got["core"]
        assert got["core"]["line"] == 1, got["core"]


def test_a_wholly_core_program_runs_clean_under_restriction():
    """The positive control. A restricted mode that refused everything would
    pass every test above and be worthless."""
    src = ("to double of n:\n"
           "  give n * 2\n"
           "xs = for each n in [1, 2, 3] where n > 1: double of n\n"
           "show count of xs\n"
           "show upper of \"ok\"\n")
    got, _ = _run_source(src, "--core")
    assert "core" not in got, got
    assert got["output"] == ["2", "OK"], got


# ===================================================== B — effect kinds are core

def test_every_effect_kind_is_performed_and_none_is_flagged():
    """core.json sets effect_kinds_all_core; core_check.py never flags one and
    neither does this. All seven PERFORMED — declared would not be enough, since
    a declaration reaches no effect at all — in one program, under restriction."""
    src = ('use file\n'
           'use http\n'
           'foreign now from "time.time" doing clock\n'
           'foreign pick from "random.random" doing random\n'
           'foreign here from "os.getcwd" doing env\n'
           'write { a: 1 } to "out.json"\n'
           'body = ask "https://example.test/x"\n'
           'seen = read "out.json"\n'
           't = now\n'
           'r = pick\n'
           'w = here\n'
           'show "did them all"\n')
    got, _ = _run_source(
        src, "--core",
        config={"responses": {"https://example.test/x": '{"ok": true}'}})
    assert "core" not in got, got
    assert got["output"] == ["did them all"], got
    kinds = {e[0] for e in got["effects"]}
    assert kinds == {"write", "ask", "read", "clock", "random", "env", "show"}, (
        f"all seven effect kinds must be performed, saw {sorted(kinds)}")


def test_the_three_foreign_effect_kinds_are_declared_not_flagged():
    """clock / random / env are foreign targets, never builtins, so the
    restriction has no name to check them under — asserted so the reason is
    recorded and not merely true by accident."""
    for kind in ("clock", "random", "env"):
        assert kind not in BUILTIN_NAMES
        assert kind not in KEYWORDS


# ===================================================== C — identical when off

def test_meta_output_is_unchanged_by_the_flag_being_available():
    """Invariant 1, over the corpus. The full byte-identity check against main
    is in scripts/verify-core-sufficiency.mjs; this pins the cheaper half — that
    an unrestricted `meta run` still reports every standalone file and never
    mentions the restriction."""
    files = [f for f in sorted(glob.glob("**/*.planes", recursive=True))
             if ".venv" not in f
             and not any(ln.strip().startswith("use ")
                         for ln in open(f, encoding="utf-8").read().splitlines())]
    got = _cli("meta", "run", *files)
    assert isinstance(got, list) and len(got) == len(files), (len(got), len(files))
    assert not any(isinstance(m, dict) and "core" in m for m in got)


# ===================================================== D — both readers agree

def test_core_check_py_and_the_js_mode_classify_every_name_the_same_way():
    """Invariant 7. Neither reader is asked what it thinks; both are asked to
    classify the SAME name, and the answers are compared. The JS side answers by
    running — a program using the construct either refuses or does not."""
    core_keywords, core_builtins, _ = core_check.load_core()
    js = _cli("core-classify")
    assert set(js["keywords"]) == core_keywords, (
        set(js["keywords"]) ^ core_keywords)
    assert set(js["builtins"]) == core_builtins, (
        set(js["builtins"]) ^ core_builtins)
    # And every name in the language is classified by both, the same way.
    for word in sorted(KEYWORDS):
        assert (word in core_keywords) == (word in set(js["keywords"])), word
    for word in sorted(BUILTIN_NAMES):
        assert (word in core_builtins) == (word in set(js["builtins"])), word


def test_the_node_to_keyword_map_covers_every_keyword_in_the_vocabulary():
    """A keyword no AST node carries is one the restricted mode cannot refuse,
    however non-core it becomes. The map's completeness is the thing that keeps
    a clean restricted run from being a clean run of a blind checker."""
    js = _cli("core-classify")
    assert js["coverageGaps"] == [], (
        f"no AST node carries {js['coverageGaps']} — the restricted mode is "
        f"blind to it")
    assert set(js["allKeywords"]) == set(KEYWORDS), (
        set(js["allKeywords"]) ^ set(KEYWORDS))


def test_the_only_approximate_keyword_is_places_and_it_is_core():
    """`round x to 2 places` and `round x to 2` are the identical Round node —
    the word is optional and unrecorded, so the map reads a Round as spending
    `places` either way. Harmless while `places` is core; this is the assertion
    that notices if it ever is not."""
    js = _cli("core-classify")
    assert js["approximate"] == ["places"], js["approximate"]
    assert "places" in core_check.load_core()[0], (
        "`places` left the core, and the restricted mode would now over-report "
        "it — give Round a way to say whether the word was written, or record "
        "the answer as an over-approximation")


# ===================================================== E — the graph, measured

def test_the_declared_core_is_not_sufficient_and_lexer_planes_is_why():
    """THE FINDING, pinned. Not an assertion that the run is clean — it is not —
    but that it fails in exactly one place, for exactly one reason. If
    lexer.planes is rewritten or `when` joins the core, this fails and says so."""
    got = _cli("meta", "run", "--core", "ordinary.planes")
    assert "core" in got, f"expected a refusal; the core became sufficient? {got}"
    c = got["core"]
    assert c["construct"] == "when", c
    assert c["category"] == "keyword", c
    assert c["file"].endswith("grammar/lexer.planes"), c
    assert c["line"] == 89, c
    assert got["loaded"] is True, "interp.planes itself loaded; the graph is why"


def test_every_static_when_site_in_lexer_planes_is_actually_reached():
    """The static and runtime readings agree exactly — sixteen mentions, sixteen
    reached, at the same sixteen lines. None of them is dead code, so no reading
    of the finding survives in which the gap is theoretical."""
    core_keywords, core_builtins, _ = core_check.load_core()
    static = sorted(line for line, cat, val
                    in core_check.violations(LEXER, core_keywords, core_builtins)
                    if val == "when")
    got = _cli("meta", "run", "--core-survey", "ordinary.planes")
    reached = sorted(e["line"] for e in got["coreReached"]
                     if e["construct"] == "when"
                     and e["file"].endswith("grammar/lexer.planes"))
    assert static == reached, (static, reached)
    assert len(static) == 16, static


def test_no_other_module_in_the_graph_reaches_past_the_core():
    """One file, one construct. A second offender appearing is a different
    finding and this says so rather than absorbing it."""
    got = _cli("meta", "run", "--core-survey", "ordinary.planes")
    files = {os.path.relpath(e["file"], REPO) for e in got["coreReached"]}
    assert files == {LEXER}, files
    words = {e["construct"] for e in got["coreReached"]}
    assert words == {"when"}, words


def test_core_check_py_follows_the_graph_and_finds_the_same_sixteen():
    """§5.2: the single-file derivation was demonstrably incomplete, so
    core_check.py follows `use` the way analyse_file(follow=True) already did
    for effect kinds. Reported, not gated — the exit code is unchanged."""
    core_keywords, core_builtins, _ = core_check.load_core()
    graph = core_check.graph_violations(
        os.path.join("grammar", "interp.planes"), core_keywords, core_builtins)
    assert len(graph) == 16, graph
    assert {p for p, _, _, _ in graph} == {LEXER}, graph
    assert {v for _, _, _, v in graph} == {"when"}, graph
    r = subprocess.run([sys.executable, "core_check.py"], cwd=REPO,
                       capture_output=True, text=True)
    assert r.returncode == 0, (
        "the graph block must not gate — closing it needs either a wider "
        "core.json or a rewritten module, and this build forbids both")
    assert "REPORTED, NOT GATED" in r.stdout
    assert LEXER in r.stdout


def test_core_checks_graph_block_says_which_modules_conform():
    """A block that only ever printed offenders would leave a reader unable to
    tell a clean graph from an unfollowed one."""
    r = subprocess.run([sys.executable, "core_check.py"], cwd=REPO,
                       capture_output=True, text=True)
    for mod in ("grammar/parser.planes", "grammar/json.planes",
                "grammar/vocabulary.planes"):
        assert mod in r.stdout, mod
    assert "of the 4 module(s)" in r.stdout, r.stdout[:400]


if __name__ == "__main__":
    if NODE is None:
        print("  SKIP  node not on PATH")
        sys.exit(0)
    fails = []
    tests = [(k, f) for k, f in sorted(globals().items())
             if k.startswith("test_")]
    for name, fn in tests:
        params = list(inspect.signature(fn).parameters)
        try:
            if params:
                raise AssertionError(
                    f"unsupported fixture(s) {params} — this runner supplies "
                    f"none; add it here rather than skipping the test")
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
