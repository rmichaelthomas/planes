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

C2 UPDATE. The measurement has three states now, not four buckets: names a fix,
deliberately names none, and should name one and does not. The third is the
only one that is a work list, and its target is zero — which it reaches here.
Two further things changed, and both are asserted below:

  * The inclusion rule is stated rather than incidental. An entry is an error
    iff it constructs one of the seven error classes the reference defines;
    rules.py's rule-plane reports are catalogued as reports and not measured.
    Four of them had been counted as passes, which inflated S8's 70.
  * A site that deliberately names no fix says why, in words, at the raise
    site — the `no_fix` argument, read as a literal exactly as the message is.
    Five sites qualify. A silence without a stated reason is still shortfall.

The middle sections assert the fix clause C2 wrote for each message that had
none, in both implementations where the message is a parse-time one.
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


# ================================== 3. C2 — the messages that had no fix clause
#
# One test per clause, asserting what the error is and what the author is told
# to do. A clause that only restates the error passes a "has a continuation
# line" check and helps nobody, so each assertion names the *new* information
# the clause carries.

def test_the_lexer_escape_messages_name_their_fix_structurally():
    """Three messages that already named their fix, inline in prose after a
    `--`. The information was there; a catalogue and a tool need it in a field
    or on its own line, so the clause moved to a continuation line."""
    cases = [
        ('x = "a\\qb"\n', "unrecognized escape", "write the character itself"),
        ('x = "abc\n', "no closing quote", "add the closing quote"),
        ('x = "abc\\"\n', "backslash right before the closing quote",
         "for a literal trailing backslash"),
    ]
    for src, in_detail, in_fix in cases:
        msg = _py_error(src)
        assert in_detail in msg, msg
        assert FIX_CLAUSE in msg, f"no continuation line:\n{msg}"
        head, fix = msg.split(FIX_CLAUSE, 1)
        assert in_fix in fix, (src, fix)
        assert "\n" not in head, f"the detail line must be one line:\n{msg}"


def test_the_lexer_escape_messages_are_identical_in_javascript():
    if NODE is None:
        return
    for src in ('x = "a\\qb"\n', 'x = "abc\n', 'x = "abc\\"\n'):
        assert _js_error(src) == _py_error(src), src


def test_an_effect_name_names_the_seven_kinds():
    """`doing frobnicate` said what was expected and not what the vocabulary
    is. The seven kinds are the whole of it, so the clause can just list them —
    and it names where `nothing` is allowed, which is not the same place."""
    msg = _py_error('foreign f of x from "m.f" doing 5\n')
    assert "expected an effect name after" in msg, msg
    fix = msg.split(FIX_CLAUSE, 1)[1]
    for kind in ("ask", "clock", "env", "random", "read", "show", "write"):
        assert kind in fix, (kind, fix)
    assert "'nothing' after 'doing'" in fix, fix


def test_expected_a_value_names_what_can_start_one():
    """`expected a value, found 'show'` is true and names nothing. The clause
    lists what can begin an expression, and says why a statement word cannot."""
    msg = _py_error('x = show "hi"\n')
    assert "expected a value" in msg, msg
    fix = msg.split(FIX_CLAUSE, 1)[1]
    assert "a number, a quoted string, true, false, nothing, a name" in fix, fix
    assert "statement word" in fix, fix


def test_expected_a_name_says_what_a_name_is_here():
    """`read_multiword_name` is reached from exactly one form — the old and new
    spellings of a `use ... with ... as ...` rename — so the clause names that
    form rather than describing names in general. A clause that misdescribes
    where the author is is worse than no clause."""
    msg = _py_error("use file with 5 as x\n")
    assert "expected a name" in msg, msg
    fix = msg.split(FIX_CLAUSE, 1)[1]
    assert "one or more plain words" in fix, fix
    assert "`use ... with <old> as <new>` rename" in fix, fix
    assert "a quoted string, a number, or a punctuation mark" in fix, fix


def test_a_duplicate_record_field_names_with():
    """The author wrote the field twice, which usually means they wanted to
    change its value. `with` is how you do that, and the message now says so —
    information the error itself does not contain."""
    msg = _py_error("x = { a: 1, a: 2 }\n")
    assert "field 'a' appears twice" in msg, msg
    fix = msg.split(FIX_CLAUSE, 1)[1]
    assert "`r with a: value`" in fix, fix


def test_the_c2_parser_messages_are_identical_in_javascript():
    """A.5, for every message this build changed on the parse side."""
    if NODE is None:
        return
    for src in ('foreign f of x from "m.f" doing 5\n',
                'x = show "hi"\n',
                "use file with 5 as x\n",
                "x = { a: 1, a: 2 }\n"):
        assert _js_error(src) == _py_error(src), src


def test_the_generic_token_gate_still_names_nothing_and_says_why():
    """A.2 item 3: `expect`'s own no-fix path is honest, and is kept. It is
    marked a deliberate decision rather than left in the work list, and the
    reason is at the raise site."""
    msg = _py_error("x = (1\n")
    assert msg.startswith("line 1: expected ), found"), msg
    assert FIX_CLAUSE not in msg, f"the generic gate should stay bare:\n{msg}"
    ec = _coverage()
    generic = [e for e in ec.coverage()["deliberate"]
               if e["id"] == "parser.planessyntaxerror-site.expect-3"]
    assert generic, "expect's generic path is not marked deliberate"
    assert "generic token gate" in generic[0]["no_fix"], generic


def test_the_arity_messages_name_the_parameters():
    """A count leaves an author counting commas. The declared names say which
    values are wanted and in what order, and the clause renders the call."""
    from host import TestHost
    from interp import Interpreter, PlanesError
    try:
        Interpreter(host=TestHost()).run(
            "to add of a, b:\n  give a + b\nshow text of (add of 1)\n")
    except PlanesError as e:
        assert e.tag == "wrong-arity" and "takes 2 values, given 1" in e.detail
        assert "`to add of a, b`" in e.fix, e.fix
        assert "`add of a, b`" in e.fix, e.fix
    else:
        raise AssertionError("a one-argument call to a two-parameter function "
                             "was accepted")


def test_the_foreign_arity_message_names_the_declaration():
    from host import TestHost
    from interp import Interpreter, PlanesError
    try:
        Interpreter(host=TestHost()).run(
            'foreign sorted of xs from "builtins.sorted" doing ask xs\n'
            "show text of (sorted of [1], [2])\n")
    except PlanesError as e:
        assert e.tag == "wrong-arity", e.tag
        assert 'foreign sorted of xs from "builtins.sorted"' in e.fix, e.fix
        assert "`sorted of xs`" in e.fix, e.fix
    else:
        raise AssertionError("a two-argument call to a one-parameter foreign "
                             "was accepted")


def test_whole_of_says_a_number_has_to_arrive_as_one():
    """The clause carries information the error does not: Planes has no
    text-to-number builtin at all, so rounding is not the missing step."""
    from host import TestHost
    from interp import Interpreter, PlanesError
    try:
        Interpreter(host=TestHost()).run('show text of (whole of "5")\n')
    except PlanesError as e:
        assert e.tag == "not-a-number", e.tag
        assert "no text-to-number builtin" in e.fix, e.fix
    else:
        raise AssertionError('whole of "5" was accepted')


def test_the_interpreter_invariants_tell_the_author_it_is_not_their_fault():
    """Four guards unreachable from any program the parser accepts. Naming a
    fix is still the right answer: report it. The alternative — marking them
    deliberate no-fix — would hide from an author that the defect is ours."""
    ec = _coverage()
    cov = ec.coverage()
    cat = json.load(open(os.path.join(REPO, "grammar", "errors.json"),
                         encoding="utf-8"))
    ids = {"interp.cannot-evaluate.eval", "interp.unknown-builtin.builtin",
           "interp.unknown-operator.apply_op", "interp.unknown-operator.arith"}
    found = [e for e in cat["entries"] if e["id"] in ids]
    assert len(found) == 4, sorted(e["id"] for e in found)
    for e in found:
        assert ec.classify(e, True) == ec.NAMES_FIX, e["id"]
        assert "defect in the interpreter" in e["fix"], e["id"]
    assert not any(e["id"] in ids for e in cov["deliberate"])


# ========================================= 4. the catalogue check, as a report

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


def test_the_three_states_account_for_every_error_entry():
    ec = _coverage()
    cov = ec.coverage()
    assert sum(cov["counts"].values()) == cov["errors"]
    assert cov["errors"] + len(cov["reports"]) == cov["total"]
    assert cov["total"] > 0
    assert len(cov["work_list"]) == cov["counts"][ec.SHORTFALL]
    assert len(cov["deliberate"]) == cov["counts"][ec.DELIBERATE]


def test_the_catalogue_classifies_every_shape():
    ec = _coverage()
    fix_field = {"class": "PlanesError", "template": "x", "fix": "try: y"}
    continuation = {"class": "PlanesSyntaxError",
                    "template": "line 1: x\n  try: y"}
    amber = {"class": "PlanesAmbiguity", "template": None,
             "note": "delegates to grammar/messages/amber.json"}
    elsewhere = {"class": "PlanesError", "template": None,
                 "note": "message is not a literal/f-string at the call site"}
    deliberate = {"class": "PlanesError", "template": None,
                  "no_fix": "the message is the program's own"}
    bare = {"class": "PlanesSyntaxError", "template": "line 1: x"}
    assert ec.classify(fix_field, True) == ec.NAMES_FIX
    assert ec.classify(continuation, True) == ec.NAMES_FIX
    assert ec.classify(amber, True) == ec.NAMES_FIX
    assert ec.classify(amber, False) == ec.SHORTFALL
    assert ec.classify(elsewhere, True) == ec.SHORTFALL
    assert ec.classify(deliberate, True) == ec.DELIBERATE
    assert ec.classify(bare, True) == ec.SHORTFALL
    # An unreadable message is a figure, not a state: with a stated reason it is
    # a decision, without one it is shortfall. Never a pass either way.
    assert ec.is_unreadable(elsewhere) and ec.is_unreadable(deliberate)
    assert not ec.is_unreadable(fix_field) and not ec.is_unreadable(amber)


def test_a_site_that_names_a_fix_counts_as_naming_one_even_with_a_reason():
    """Order matters in classify(): a `no_fix` reason only settles a site that
    names none. Otherwise a stray annotation could hide a real fix clause."""
    ec = _coverage()
    both = {"class": "PlanesError", "template": "x", "fix": "try: y",
            "no_fix": "a reason that should not win"}
    assert ec.classify(both, True) == ec.NAMES_FIX


def test_the_work_list_is_empty():
    """C2's headline. Every catalogued error either names a fix or states, at
    its raise site, why it names none."""
    ec = _coverage()
    cov = ec.coverage()
    assert cov["counts"][ec.SHORTFALL] == 0, \
        "errors naming no fix and giving no reason:\n" + "\n".join(
            f"  {e['source']} {e['id']}" for e in cov["work_list"])


def test_no_unreadable_entry_is_counted_as_a_pass():
    """A.1's invariant, kept after the bucket disappeared: an entry whose
    message is not a literal at the raise site is never in `names a fix` unless
    its `fix` field is a literal there."""
    ec = _coverage()
    cov = ec.coverage()
    unreadable_ids = {e["id"] for e in cov["unreadable"]}
    accounted = {e["id"] for e in cov["work_list"] + cov["deliberate"]}
    assert unreadable_ids <= accounted, sorted(unreadable_ids - accounted)


def test_every_deliberate_silence_states_its_reason():
    """Constraint 5: marked, never silently counted as a pass. The reason is
    read as a literal at the raise site, so it cannot drift into a variable."""
    ec = _coverage()
    cov = ec.coverage()
    assert cov["deliberate"], "no deliberate no-fix entries at all"
    for e in cov["deliberate"]:
        assert e["no_fix"] and len(e["no_fix"]) > 30, e


def test_the_inclusion_rule_is_stated_and_the_reports_are_not_measured():
    """A.2 item 2. The rule lives in grammar_gen.py next to the class list it
    governs, every entry carries the `kind` it assigns, and the rule-plane
    reports are listed rather than counted against a commitment about errors."""
    import grammar_gen
    assert len(grammar_gen.ERROR_CLASSES) == 7, sorted(grammar_gen.ERROR_CLASSES)
    for cls in ("PlanesError", "PlanesSyntaxError", "PlanesAmbiguity",
                "RuleConflict", "RuleNotSupported", "ModuleError",
                "GrammarDataError"):
        assert cls in grammar_gen.ERROR_CLASSES, cls
    # The three deliberately outside it, each because no program can see one.
    for cls in ("HostError", "Inexact", "_Give"):
        assert cls not in grammar_gen.ERROR_CLASSES, cls

    cat = json.load(open(os.path.join(REPO, "grammar", "errors.json"),
                         encoding="utf-8"))
    assert all(e.get("kind") in ("error", "report") for e in cat["entries"])
    reports = [e for e in cat["entries"] if e["kind"] == "report"]
    assert len(reports) == 5, len(reports)
    assert all(e["source"].startswith("rules.py") for e in reports)
    ec = _coverage()
    cov = ec.coverage()
    assert {e["id"] for e in cov["reports"]} == {e["id"] for e in reports}


def test_a_catalogue_id_names_the_function_it_is_raised_in():
    """C2 reported that an id was unstable: the running-count suffix was
    assigned across a whole file, so adding one raise site renumbered every
    later site sharing its tag — `whole of` silently moved from
    `interp.not-a-number-3` to `-4`. The disambiguator is the enclosing function
    first, which is data the entry already carried, and a count only where that
    still collides.

    Not a guarantee, and the test says which part is: two raises with the same
    tag in the same function still fall back to a count, and inserting a raise
    above one of those still renumbers it. Nothing short of a hand-assigned key
    makes an id permanent, and ruling D1 exists to refuse a hand-assigned key."""
    cat = json.load(open(os.path.join(REPO, "grammar", "errors.json"),
                         encoding="utf-8"))
    ids = [e["id"] for e in cat["entries"]]
    assert len(ids) == len(set(ids)), "ids are not unique"
    for e in cat["entries"]:
        if not e.get("raised_in"):
            continue
        if e["kind"] == "report":
            # A report entry already named its method before C2 — its id is
            # `rules.<method>.branch-<n>`, so the method is the middle segment.
            assert e["id"].startswith(f"rules.{e['raised_in']}.branch-"), e["id"]
            continue
        stem = e["id"].rsplit("-", 1)[0] if e["id"].rsplit(
            "-", 1)[-1].isdigit() else e["id"]
        assert stem.endswith("." + e["raised_in"]), e["id"]
    # The four this build's other tests pin, by their meaningful names.
    for wanted in ("interp.unknown-operator.apply_op",
                   "interp.unknown-operator.arith",
                   "interp.cannot-evaluate.eval",
                   "interp.unknown-builtin.builtin"):
        assert wanted in ids, wanted


def test_the_running_count_follows_source_order():
    """`ast.walk` is breadth-first, so the suffix did not even follow the file —
    `expect`'s three raises came out in walk order, which is unpredictable from
    reading the source. Entries are sorted by line before numbering, so `-1`
    is the first one written."""
    cat = json.load(open(os.path.join(REPO, "grammar", "errors.json"),
                         encoding="utf-8"))
    def line(e):
        return int(e["source"].rsplit(":", 1)[1].split("-")[0])
    by_file = {}
    for e in cat["entries"]:
        by_file.setdefault(e["source"].split(":")[0], []).append(e)
    for fname, entries in by_file.items():
        lines = [line(e) for e in entries]
        assert lines == sorted(lines), f"{fname} is not in source order"
    expect = [e for e in cat["entries"] if e.get("raised_in") == "expect"]
    assert len(expect) == 3, len(expect)
    assert expect[0]["id"].endswith("expect-1")
    assert "is a keyword" in expect[0]["template"], expect[0]["template"]


def test_the_two_error_classes_the_rule_added_are_measured():
    """ModuleError and GrammarDataError were absent from the catalogue for no
    stated reason — nine raise sites the commitment was never measured over,
    four of which held their fix clause in a local variable."""
    cat = json.load(open(os.path.join(REPO, "grammar", "errors.json"),
                         encoding="utf-8"))
    ec = _coverage()
    added = [e for e in cat["entries"]
             if e["class"] in ("ModuleError", "GrammarDataError")]
    assert len(added) == 9, len(added)
    for e in added:
        assert ec.classify(e, True) == ec.NAMES_FIX, (e["id"], e.get("fix"))


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


# ================= 6. the self-hosted commitment, met (D / §171)
#
# `errors name the fix` has been a language-level commitment since unbound v1.1
# §22. C2 drove the reference implementation's work list to 0 of 109. This
# build drives the self-hosted stack's to 0 of 111, which is the endpoint: the
# commitment is now kept in all three implementations.
#
# These replace C5 and C6's split-arithmetic assertions, which measured a
# shortfall of 71 and its port-versus-write partition. That shortfall is gone,
# so the numbers they pinned are gone with it; 0 is the stricter assertion, and
# the split machinery is kept because it would light up again the moment a new
# self-hosted raise site arrived without a clause.


def test_the_self_hosted_work_list_is_empty():
    """The endpoint. Not "71 clauses were written" — three states, and the
    third at zero, the same shape the reference reached 0 of 109 in."""
    ec = _coverage()
    sites = ec.self_hosted_sites()
    total = sum(len(v) for v in sites.values())
    assert len(sites[ec.SHORTFALL]) == 0, [
        (s[0], s[1], s[2]) for s in sites[ec.SHORTFALL]]
    assert total == 111, total
    assert len(sites[ec.NAMES_FIX]) + len(sites[ec.DELIBERATE]) == total


def test_the_reference_work_list_is_still_empty_too():
    """Both halves, or the commitment is not met. C2 got the reference to zero
    and nothing here may move it."""
    ec = _coverage()
    cov = ec.coverage()
    assert cov["counts"][ec.SHORTFALL] == 0
    assert cov["errors"] == 109, cov["errors"]


def test_every_deliberate_self_hosted_silence_states_a_reason():
    """A silence without a stated reason is shortfall, on this side too. Three
    shapes qualify and no others: a bare-name re-raise (the message belongs to
    whoever wrote it), `error-no-fix-of` with its reason as a literal, and
    `fail`'s record form carrying `no-fix:` — the generic token gate, which
    knows which token was due and not what the author meant."""
    import re
    ec = _coverage()
    for f, n, src, _tag, _fn in ec.self_hosted_sites()[ec.DELIBERATE]:
        # `src` is truncated for the report; read the whole line.
        with open(os.path.join(REPO, "grammar", f), encoding="utf-8") as fh:
            line = fh.read().split("\n")[n - 1].strip()
        bare = re.match(r"fail\s+[A-Za-z][\w-]*(\.[\w-]+)*\s+as\s", line)
        assert bare or "error-no-fix-of of " in line or "no-fix:" in line, \
            (f, n, line)


def test_the_scanner_does_not_count_its_own_helper_definitions():
    """C6's guard, still holding. Both definitions live in
    grammar/interp.planes and neither raises anything."""
    ec = _coverage()
    sites = ec.self_hosted_sites()
    defs = [s for v in sites.values() for s in v
            if s[2].startswith("to error-of of ")
            or s[2].startswith("to error-fix-of of ")
            or s[2].startswith("to error-no-fix-of of ")]
    assert not defs, defs

    # The guard is the general one and not a list of names. Planes allows a
    # single inline statement as a function body, so a raise on a `to` line is
    # real and must stay counted — a blanket `to `-line skip would trade an
    # over-count for an under-count.
    definition = "to error-of of tag, detail:"
    inline = 'to f of x: give fail-of of (error-of of "y", z), env'
    assert ec._defines(definition, definition.index("error-of of"))
    assert not ec._defines(inline, inline.index("error-of of"))


def test_a_fix_named_through_fails_record_form_is_seen():
    """§158's record form is the ONLY way a `fail` site can name a fix, and
    this scanner predated it. Without this the work list could not have reached
    zero however many clauses were written."""
    ec = _coverage()
    named = [s for s in ec.self_hosted_sites()[ec.NAMES_FIX]
             if s[2].startswith("fail { message:")]
    assert named, "no fail-record site counted as naming a fix"
    for f, n, src, _t, _fn in named:
        # `src` is truncated for the report; read the whole line.
        with open(os.path.join(REPO, "grammar", f), encoding="utf-8") as fh:
            line = fh.read().split("\n")[n - 1]
        assert "fix:" in line, (f, n, line)


def test_a_fix_on_a_continuation_line_is_seen_through_one_helper():
    """A syntax error names its fix inline, after a `\n  `, because both
    implementations render one string and the two are byte-identical. The
    reference half of this checker has read that shape since C2; the
    self-hosted half now reads it too, including through the single message
    helper the lexer composes its message in."""
    ec = _coverage()
    helpers = ec._continuation_helpers("grammar/lexer.planes")
    assert "unterminated-string-message" in helpers, sorted(helpers)
    assert ec._names_fix_inline("unterminated-string-message of state.line",
                                helpers)
    assert ec._names_fix_inline('"line 1: x\\n  try: y"', set())
    assert not ec._names_fix_inline('"line 1: x"', set())


def test_the_split_of_an_empty_shortfall_is_empty():
    """C5 and C6's port-versus-write machinery, kept and now describing an
    empty set. It is not deleted: a new self-hosted raise site with no clause
    lands back on the work list and this partitions it again."""
    ec = _coverage()
    split = ec.split_shortfall(ec.self_hosted_sites()[ec.SHORTFALL])
    assert not split[ec.HAS_TWIN]
    assert not split[ec.PROBABLE_TWIN]
    assert not split[ec.NO_TWIN]
    assert not split["multiplicity"] and not split["tag_unreadable"]
    # The two keys still resolve — the machinery works, there is just no work.
    assert ec.reference_fix_tags() and ec.reference_fix_functions()


def test_every_self_hosted_site_carries_its_tag_or_none():
    ec = _coverage()
    for state, sites in ec.self_hosted_sites().items():
        for site in sites:
            assert len(site) == 5, (state, site)
            f, n, src, tag, fn = site
            assert f.endswith(".planes") and n > 0 and src
            assert tag is None or (tag and " " not in tag), site
            # Every raise site in these files is inside a function.
            assert fn and " " not in fn, site


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
