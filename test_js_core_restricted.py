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


def test_why_and_when_report_their_own_line_not_an_enclosing_one():
    """`Why`, `Assign` and `When` AST nodes carry no `line` field — three of the
    four keywords once excluded. The line rides in a parser-stamped WeakMap
    instead, because giving those nodes a field would change the AST's SHAPE,
    which grammar/parser.planes pins. If that stamp regressed, these would report
    an enclosing statement's line and `approximateLine` would be true.

    `why` is checked against the real core. `when` is core now, so it is checked
    against a core that excludes it — which keeps the `When`-node half of the
    stamp covered rather than letting it lapse the moment the keyword moved."""
    got, _ = _run_source("x = 1 + 1\nwhy x\n", "--core")
    assert "core" in got, got
    assert got["core"]["construct"] == "why", got["core"]
    assert got["core"]["line"] == 2, got["core"]
    assert got["core"]["approximateLine"] is False, got["core"]

    core = _crafted(drop_keywords=["when"])
    got, _ = _run_source(
        "v = { kind: \"a\" }\n"
        "when v is { kind: \"a\" }:\n"
        "  show \"matched\"\n", "--core", "--core-json", core)
    assert "core" in got, got
    assert got["core"]["construct"] == "when", got["core"]
    assert got["core"]["line"] == 2, got["core"]
    assert got["core"]["approximateLine"] is False, got["core"]


def test_a_non_core_builtin_is_refused_by_name():
    for word in sorted(set(BUILTIN_NAMES) - set(core_check.load_core()[1])):
        got, _ = _run_source(f"show {word} of 9\n", "--core")
        assert "core" in got, (word, got)
        assert got["core"]["construct"] == word, got["core"]
        assert got["core"]["category"] == "builtin", got["core"]
        assert got["core"]["line"] == 1, got["core"]


def test_a_let_in_an_uncalled_function_does_not_refuse():
    """THE ASSERTION THAT SEPARATES THIS FROM A SECOND COPY OF core_check.py.

    The restriction is evaluation-time, so a construct the run never REACHES is
    never refused — and this is the case where the two checks give different
    answers on purpose. core_check.py flags the `let` below; the restricted run
    does not, because nothing calls the function. Both are right about their own
    question, and a restricted run that completes therefore means "every
    construct this run reached was core", never "every construct in the file is
    core". If this ever starts refusing, the mode has become a source scan."""
    src = ("to never-called of n:\n"
           "  let x = n * 2\n"
           "  give x\n"
           "show 1\n")
    got, _ = _run_source(src, "--core")
    assert "core" not in got, (
        f"refused a `let` the run never reached — this is a source scan now, "
        f"not an evaluation-time check: {got['core']}")
    assert got["output"] == ["1"], got
    # and the static check, on the same text, does flag it
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "probe.planes")
        with open(p, "w", encoding="utf-8") as f:
            f.write(src)
        core_keywords, core_builtins, _ = core_check.load_core()
        static = core_check.violations(p, core_keywords, core_builtins)
    assert [(c, v) for _, c, v in static] == [("keyword", "let")], static


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

def test_the_declared_core_is_sufficient_and_the_whole_graph_runs():
    """THE CLAIM core.json MAKES, now with a checker behind it. `when` has joined
    the core (reports/CORE_SUBSET.md §4a records why it was ever out), so a host
    implementing only the declared port surface runs interp.planes and its whole
    module graph. This assertion was inverted to get here — it read "expected a
    refusal" for exactly one build."""
    got = _cli("meta", "run", "--core", "ordinary.planes")
    assert isinstance(got, list), (
        f"the declared core is no longer sufficient: {got.get('core')}")
    assert got[0]["output"] == ["above threshold"], got


def test_the_gap_that_was_found_stays_found_if_when_ever_leaves_again():
    """THE REGRESSION GUARD FOR THE WHOLE FINDING — the reason fixing it does not
    lose the evidence for it.

    Exclude `when` from a crafted core and the old world returns exactly: the
    restricted run refuses at grammar/lexer.planes:89, and the static and runtime
    readings agree on all sixteen sites, same count, same lines, none dead. If
    grammar/lexer.planes is ever rewritten to flat `if`, this fails — and that is
    the correct moment to reconsider whether `when` is still core."""
    core = _crafted(drop_keywords=["when"])
    got = _cli("meta", "run", "--core", "--core-json", core, "ordinary.planes")
    assert "core" in got, f"lexer.planes no longer needs `when`? {got}"
    c = got["core"]
    assert c["construct"] == "when", c
    assert c["category"] == "keyword", c
    assert c["file"].endswith("grammar/lexer.planes"), c
    assert c["line"] == 89, c
    assert got["loaded"] is True, "interp.planes itself loaded; the graph is why"

    with open(core, encoding="utf-8") as f:
        doc = json.load(f)
    static = sorted(line for line, _cat, val in core_check.violations(
        LEXER, set(doc["keywords"]), set(doc["builtins"])) if val == "when")
    survey = _cli("meta", "run", "--core-survey", "--core-json", core,
                  "ordinary.planes")
    reached = sorted(e["line"] for e in survey["coreReached"]
                     if e["construct"] == "when"
                     and e["file"].endswith("grammar/lexer.planes"))
    assert static == reached, (static, reached)
    assert len(static) == 16, static


def test_nothing_anywhere_in_the_graph_reaches_past_the_core():
    """The census over the real core, which must now be empty. An offender
    reappearing is a new finding and this says so rather than absorbing it."""
    got = _cli("meta", "run", "--core-survey", "ordinary.planes")
    assert got["coreReached"] == [], got["coreReached"]


def test_core_check_py_follows_the_graph_and_now_gates_on_it():
    """§5.2: the single-file derivation was demonstrably incomplete, so
    core_check.py follows `use` the way analyse_file(follow=True) already did for
    effect kinds. It REPORTED for exactly one build — while the choice between
    widening the core and rewriting the module was still open — and gates now
    that the choice is made."""
    core_keywords, core_builtins, _ = core_check.load_core()
    graph = core_check.graph_violations(
        os.path.join("grammar", "interp.planes"), core_keywords, core_builtins)
    assert graph == [], graph
    r = subprocess.run([sys.executable, "core_check.py"], cwd=REPO,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-800:]
    assert "REPORTED, NOT GATED" not in r.stdout, (
        "the graph block still calls itself a report")


def test_the_graph_block_gates_when_a_module_reaches_past_the_core():
    """The gate has teeth, demonstrated rather than described: hand core_check.py
    a crafted core without `when` and its exit code must be the sixteen sites —
    exactly sixteen, since `_crafted` keeps the document self-consistent so the
    drift guard contributes nothing of its own."""
    core = _crafted(drop_keywords=["when"])
    r = subprocess.run([sys.executable, "core_check.py", "--core", core],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 16, (r.returncode, r.stdout[-600:])
    assert "THIS FAILS THE GATE" in r.stdout
    assert LEXER in r.stdout


# =========================================== F — graduated from the verify script
#
# scripts/verify-core-sufficiency.mjs asserted these against CRAFTED core
# documents, and the retirement rule sends its durable assertions here rather
# than leaving them in a file nothing runs. They are the anti-vacuity half: each
# breaks the subject deliberately and confirms the answer changes. Without them,
# every assertion above would still pass against a mode that had `let`, `rule`,
# `when` and `why` hardcoded and never opened grammar/core.json at all.
#
# The one assertion NOT graduated is the byte-identity comparison against `main`:
# it needs a git worktree of a commit that will have moved by next month, and its
# durable form already exists — test_js_metacircular.py compares this whole stack
# against the Python implementation on every gate run, so a change to the
# flag-off behaviour fails there.

def _crafted(**edits):
    """grammar/core.json with one edit, written where --core-json can read it.

    `size.keywords` is recomputed rather than carried over, so the crafted
    document is INTERNALLY CONSISTENT — otherwise core_check.py's drift guard
    fires on the stale count and every exit code from a crafted run is one
    higher than the thing being measured. The two guards compose correctly;
    a test should measure one of them at a time."""
    with open(os.path.join(REPO, "grammar", "core.json"), encoding="utf-8") as f:
        doc = json.load(f)
    for word in edits.get("add_keywords", []):
        doc["keywords"] = sorted(set(doc["keywords"]) | {word})
        doc["excluded_keywords"].pop(word, None)
    for word in edits.get("drop_keywords", []):
        doc["keywords"] = [k for k in doc["keywords"] if k != word]
        doc["excluded_keywords"][word] = "crafted, for the anti-vacuity check"
    doc["size"]["keywords"] = f"{len(doc['keywords'])} of {len(KEYWORDS)}"
    d = tempfile.mkdtemp()
    p = os.path.join(d, "core.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    return p


def test_the_mode_reads_core_json_rather_than_a_hardcoded_list():
    """Move `let` INTO the core and the identical restricted run stops refusing.
    A mode with the four excluded keywords baked in would refuse anyway."""
    src = ("total = 0\n"
           "for each n in [1, 2, 3]:\n"
           "  let doubled = n * 2\n"
           "  total = total + doubled\n"
           "show total\n")
    core = _crafted(add_keywords=["let"])
    got, _ = _run_source(src, "--core", "--core-json", core)
    assert "core" not in got, got
    assert got["output"] == ["12"], got


def test_narrowing_the_core_makes_a_previously_clean_program_refuse():
    """The other direction. `use` is core, and the seven-effects program above
    passes because of it; take it out and the same program must stop."""
    core = _crafted(drop_keywords=["use"])
    got, _ = _run_source("use file\nshow 1\n", "--core", "--core-json", core)
    assert "core" in got, got
    assert got["core"]["construct"] == "use", got["core"]


def test_when_is_the_whole_gap_and_the_corpus_then_runs_restricted():
    """THE DECISIVE CONTROL, and the reason the finding is a number and not a
    direction. Widen the core by `when` and nothing else, and all three
    metacircular stages complete under restriction over the whole corpus, each
    producing output byte-identical to the unrestricted run. The declared port
    surface is short by one keyword — not by an unknown amount."""
    core = _crafted(add_keywords=["when"])
    files = [f for f in sorted(glob.glob("**/*.planes", recursive=True))
             if ".venv" not in f]
    std = [f for f in files
           if not any(ln.strip().startswith("use ")
                      for ln in open(f, encoding="utf-8").read().splitlines())]
    for stage, batch in (("run", std), ("lex", files), ("parse", std)):
        strict = subprocess.run(
            [NODE, "js/cli.mjs", "meta", stage, "--core", "--core-json", core,
             *batch], cwd=REPO, capture_output=True, text=True)
        assert strict.returncode == 0, strict.stderr[:400]
        got = json.loads(strict.stdout)
        assert isinstance(got, list), (
            f"meta {stage} still refused with `when` in the core: "
            f"{got.get('core')} — a SECOND construct is missing, and the "
            f"finding is no longer one keyword")
        assert len(got) == len(batch), (stage, len(got), len(batch))
        plain = subprocess.run([NODE, "js/cli.mjs", "meta", stage, *batch],
                               cwd=REPO, capture_output=True, text=True)
        assert strict.stdout == plain.stdout, (
            f"meta {stage}: the restriction changed an answer")


def test_core_checks_graph_block_says_which_modules_conform():
    """A block that only ever printed offenders would leave a reader unable to
    tell a clean graph from an unfollowed one."""
    r = subprocess.run([sys.executable, "core_check.py"], cwd=REPO,
                       capture_output=True, text=True)
    for mod in ("grammar/lexer.planes", "grammar/parser.planes",
                "grammar/json.planes", "grammar/vocabulary.planes"):
        assert mod in r.stdout, mod
    assert "all 4 module(s)" in r.stdout, r.stdout[:400]


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
