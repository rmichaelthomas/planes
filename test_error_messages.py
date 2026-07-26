"""S8 — the two messages that did not name their fix, and the catalogue count.

`errors name the fix` is a language-level commitment (unbound v1.1 §22), not a
courtesy: it is the highest-leverage machine-authorship affordance Planes has,
because an author — human or machine — given a true statement and no next move
is stuck. The canonical corpus (S7) surfaced two messages that reported a token
mismatch and named nothing:

    x = { k: f of a, k2: 9 }   ->  line 1: expected }, found ':'
    let rule = 1               ->  line 1: expected name, found 'rule'

Both came from the parser's generic `expect`. Both are fixed here, in both
implementations, and each has a test below asserting the fix clause is present
— and that the two implementations say it identically, byte for byte.

The reserved-word one had a ready answer: the effective reserved surface is 42
names, 32 keywords plus 10 builtins, and the builtin half already errored
naming the collision (`check_binding_name`). The keyword half now says the same
thing in the same voice.

The last section pins `errors_coverage.py` — the first measurement of a
commitment this chain has asserted for many builds and never counted. It is a
report, never a gate, and these tests assert that too.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from parser import PlanesSyntaxError, parse

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))

# The continuation clause every fix-naming message in this repo uses.
FIX_CLAUSE = "\n  "


def _py_error(src):
    try:
        parse(src)
    except PlanesSyntaxError as e:
        return str(e)
    raise AssertionError(f"parser.py did not refuse:\n{src}")


def _js_error(src):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "p.planes")
        with open(p, "w", encoding="utf-8") as f:
            f.write(src)
        r = subprocess.run([NODE, "js/cli.mjs", "ast", p],
                           cwd=REPO, capture_output=True, text=True)
    out = r.stdout.strip()
    assert out.startswith('{"error"'), f"js did not refuse:\n{src}\n{out[:200]}"
    return json.loads(out)["message"]


# The two programs, distilled. Each is the shape the corpus hit.
GREEDY_CALL_IN_RECORD = "x = { k: f of a, k2: 9 }\n"
RESERVED_WORD_AS_NAME = "let rule = 1\n"


# ================================================ 1. a bare call in a record

def test_a_greedy_call_in_a_record_names_the_fix():
    msg = _py_error(GREEDY_CALL_IN_RECORD)
    assert msg.startswith("line 1: expected }, found ':'"), msg
    assert FIX_CLAUSE in msg, f"no fix clause:\n{msg}"
    fix = msg.split(FIX_CLAUSE, 1)[1]
    # The fix must say what to write, not merely restate the mismatch.
    assert "parenthesise" in fix, fix
    assert "{ k: (f of a, b), k2: 9 }" in fix, fix


def test_the_record_fix_clause_is_identical_in_javascript():
    if NODE is None:
        return
    assert _js_error(GREEDY_CALL_IN_RECORD) == _py_error(GREEDY_CALL_IN_RECORD)


# ============================================ 2. a reserved word as a name

def test_a_reserved_word_where_a_name_is_wanted_names_the_fix():
    msg = _py_error(RESERVED_WORD_AS_NAME)
    assert msg.startswith("line 1: 'rule' is a keyword, so it cannot be "
                          "used as a name"), msg
    assert FIX_CLAUSE in msg, f"no fix clause:\n{msg}"
    fix = msg.split(FIX_CLAUSE, 1)[1]
    assert "pick another name" in fix, fix


def test_the_keyword_message_matches_the_builtin_one_in_voice():
    """The 42-name reserved surface, said the same way on both halves: a
    builtin collision already named itself; the keyword half now does too,
    and each points at the other."""
    kw = _py_error(RESERVED_WORD_AS_NAME)
    bi = _py_error("count = 1\n")
    assert "is a keyword, so it cannot be" in kw, kw
    assert "is a builtin, so it cannot be" in bi, bi
    assert "keyword names are reserved like builtins" in kw, kw
    assert "builtin names are reserved like keywords" in bi, bi


def test_the_reserved_word_message_fires_wherever_a_name_is_expected():
    """Not one call site: `expect("NAME")` is the parser's single name
    gate, so a keyword refused there is refused the same way in a let, a
    parameter list, and a loop variable."""
    for src in ("let rule = 1\n",
                "to f of rule:\n  give rule\n",
                "for each rule in xs:\n  show rule\n",
                "let when = 1\n"):
        msg = _py_error(src)
        assert "is a keyword, so it cannot be used as a name" in msg, (src, msg)
        assert FIX_CLAUSE in msg, (src, msg)


def test_the_keyword_fix_clause_is_identical_in_javascript():
    if NODE is None:
        return
    for src in ("let rule = 1\n",
                "to f of rule:\n  give rule\n",
                "for each rule in xs:\n  show rule\n"):
        assert _js_error(src) == _py_error(src), src


# ========================================= 3. the catalogue check, as a report

def _coverage():
    sys.path.insert(0, REPO)
    import errors_coverage
    return errors_coverage


def test_the_catalogue_check_reports_and_never_fails():
    """Invariant: a message with no fix clause is work to schedule, not a
    build to break. The checker always exits 0."""
    ec = _coverage()
    with open(os.devnull, "w", encoding="utf-8") as quiet:
        saved, sys.stdout = sys.stdout, quiet
        try:
            assert ec.main(["errors_coverage.py"]) == 0
            assert ec.main(["errors_coverage.py", "--json"]) == 0
        finally:
            sys.stdout = saved


def test_the_catalogue_buckets_account_for_every_entry():
    ec = _coverage()
    cov = ec.coverage()
    assert sum(cov["counts"].values()) == cov["total"]
    assert cov["total"] > 0
    assert len(cov["shortfall"]) == cov["counts"][ec.NO_FIX]
    assert len(cov["unreadable"]) == cov["counts"][ec.UNREADABLE]


def test_the_catalogue_classifies_the_four_shapes():
    ec = _coverage()
    fix_field = {"class": "PlanesError", "template": "x", "fix": "try: y"}
    continuation = {"class": "PlanesSyntaxError",
                    "template": "line 1: x\n  try: y"}
    amber = {"class": "PlanesAmbiguity", "template": None,
             "note": "delegates to grammar/messages/amber.json"}
    elsewhere = {"class": "PlanesError", "template": None,
                 "note": "message is not a literal/f-string at the call site"}
    bare = {"class": "PlanesSyntaxError", "template": "line 1: x"}
    assert ec.classify(fix_field, True) == ec.NAMES_FIX
    assert ec.classify(continuation, True) == ec.NAMES_FIX
    assert ec.classify(amber, True) == ec.DELEGATES
    assert ec.classify(amber, False) == ec.NO_FIX
    assert ec.classify(elsewhere, True) == ec.UNREADABLE
    assert ec.classify(bare, True) == ec.NO_FIX


def test_the_two_fixed_messages_are_in_the_catalogue_as_naming_a_fix():
    """The point of fixing them: the catalogue now records both as carrying a
    fix clause, so the count this build reports is a count of the code."""
    ec = _coverage()
    cat = json.load(open(os.path.join(REPO, "grammar", "errors.json"),
                         encoding="utf-8"))
    keyword = [e for e in cat["entries"]
               if e.get("template")
               and "is a keyword, so it cannot be used as a name" in e["template"]]
    withfix = [e for e in cat["entries"]
               if e.get("template")
               and "found '{found}'\n  {fix}" in e["template"]]
    assert keyword, "the keyword message is not in the catalogue"
    assert withfix, "the fix-carrying expect() site is not in the catalogue"
    for e in keyword + withfix:
        assert ec.classify(e, True) == ec.NAMES_FIX, e["id"]


if __name__ == "__main__":
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
