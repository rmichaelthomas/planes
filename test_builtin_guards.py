"""C2, Phase 3 — the thirteen divergences, and the sweep that found more.

C1 found 13 places where `interp.py` and `js/interp.mjs` disagreed about what
to say to a person, in two families:

  * `count of` a number, a boolean, or nothing raised a bare Python
    `TypeError` — a host exception escaping into a Planes program, which is
    the most complete failure of the fix-clause commitment there is. The
    JavaScript side already refused with `not-a-collection`.
  * `lower`, `upper`, and `normalize` of a non-string handed the value to the
    host's own string conversion, so `lower of [1, 2]` answered `'[1, 2]'`
    through CPython and `'1,2'` through V8. Ten cases where *both* were
    confidently wrong in the same way, because the answer depended on which
    host ran the program.

C2 rules on both: family 1 raises a `PlanesError` naming the fix, and family 2
errors naming `text of`. The chain was already consistent on this everywhere
else — `+` does not coerce, ordering across types errors naming both operands,
`join` refuses a non-text element — so an explicit conversion exists and
implicit coercion bought nothing but the loss of a value's type.

The thirteen were where the JSON work happened to look. This suite sweeps for
siblings instead of asserting the thirteen: every builtin against every value
kind, then every other operation that reaches a host primitive. Two invariants,
both from C2's constraint 6, and neither limited to builtins:

  1. no host exception escapes into a Planes program, and
  2. no host stringification is observable from one — which means the two
     implementations agree, because a leak is exactly what makes them differ.

The sweep found five more families the thirteen did not cover: `ask`, `read`,
and `write ... to` accepted a non-text target and handed it to the host;
`first n of` a non-sequence crashed both; and `in` with a non-collection on the
right raised a TypeError here and answered `unknown-operator` there, which
named the wrong thing — `in` is an operator the language defines.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from host import TestHost
from interp import Interpreter, PlanesError
from lexer import PlanesSyntaxError
from modules import ModuleError

NODE = shutil.which("node")
REPO = os.path.dirname(os.path.abspath(__file__))

# The eleven builtins, and one value of every kind the language has.
BUILTINS = ("count", "text", "lower", "upper", "whole", "normalize", "join",
            "rest", "ask", "read")
VALUES = (("number", "5"), ("text", '"ab"'), ("list", "[1, 2]"),
          ("record", "{ a: 1 }"), ("boolean", "true"), ("nothing", "nothing"))

# A stub for the two effect builtins, so `ask "ab"` and `read "ab"` succeed and
# the sweep measures the type guard rather than a missing response.
CFG = {"responses": {"ab": "{}"}, "files": {"ab": "body"}}

# The value kinds `lower`, `upper`, and `normalize` used to coerce. Named so the
# assertion below is about the ruled cases and not only about agreement.
COERCED = ("number", "list", "record", "boolean", "nothing")


def _prog(builtin, literal):
    """`show text of (<builtin> of x)` — C1's one-line reproduction, with the
    value bound first. Bound rather than juxtaposed on purpose: `count true`
    and `count { a: 1 }` are *parse* errors, so a sweep written the short way
    never reaches the guard for three of the six value kinds."""
    use = {"ask": "use http\n", "read": "use file\n"}.get(builtin, "")
    return f"{use}x = {literal}\nshow text of ({builtin} of x)\n"


def _py(src):
    """Run through interp.py, classifying the outcome. `HOST-EXCEPTION` is the
    thing constraint 6 forbids: anything that is not one of the language's own
    refusals reaching the top."""
    itp = Interpreter(host=TestHost(responses=CFG["responses"],
                                   files=dict(CFG["files"])))
    try:
        itp.run(src)
    except PlanesError as e:
        return ("error", e.tag, [])
    except PlanesSyntaxError:
        return ("refused", "PARSE", [])
    except ModuleError:
        return ("refused", "MODULE", [])
    except Exception as e:                              # noqa: BLE001
        return ("HOST-EXCEPTION", f"{type(e).__name__}: {e}", [])
    return ("ok", None, list(itp.output))


def _js_raw(src):
    """One case, one node process — the original per-case path. Kept because
    `test_batch_equivalence.py` runs every case through *both* this and the
    batch and asserts they answer identically; a batch mode with no surviving
    per-case path could not be checked against anything. That suite is where
    C6 graduated the assertion from `scripts/verify_batch_equivalence.py`,
    which made the claim and which nothing ever ran."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "p.planes")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(src)
        return subprocess.run([NODE, "js/cli.mjs", "run", p, json.dumps(CFG)],
                              cwd=REPO, capture_output=True, text=True)


def _three_way_src(expr, names):
    return "".join(f"{k} = {_VAL_SRC[v]}\n" for k, v in names.items()) \
        + f"show text of ({expr})\n"


def batch_sources():
    """Every program this suite sends to the JavaScript implementation.

    A.1: the suite used to spawn one `node` per case — 528 of them, measured,
    at roughly 130 ms of cold start each. Enumerating the cases up front lets
    one process answer all of them. The enumeration is derived from the same
    generators the tests iterate, so it cannot drift out of step with them.
    """
    srcs = [src for _, src in _builtin_cases()]
    srcs += [src for _, src in _other_cases()]
    srcs += [f"xs = [1, 2]\nshow text of ({n} of xs)\n"
             for n in ("lower", "upper", "normalize")]
    srcs += [src for _, src in RUNTIME_MESSAGES]
    srcs += [_three_way_src(expr, names)
             for _, expr, names in _three_way_cases()]
    return list(dict.fromkeys(srcs))            # dedup, order preserved


def run_batch(srcs):
    """One node process for the whole list, keyed by source.

    `run-batch` calls the same `runOne` the per-case `run` calls, so this
    changes how many processes the caller pays for and nothing about what a
    case reports. The case list goes through a file, not argv: it is well past
    the platform's argument-length limit.
    """
    seen = list(dict.fromkeys(srcs))
    cases = [{"id": str(i), "src": s, "config": CFG}
             for i, s in enumerate(seen)]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "cases.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(cases, fh)
        r = subprocess.run([NODE, "js/cli.mjs", "run-batch", "@" + p],
                           cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return {seen[int(d2["id"])]: d2 for d2 in json.loads(r.stdout)}


_BATCH: dict | None = None


def _js_result(src):
    """This case's result, out of the batch. The batch is computed once, on
    first use. A source the enumeration missed falls back to its own call, so
    the enumeration is an optimisation and never a source of a different
    answer — a case cannot silently vanish by being left off the list."""
    global _BATCH
    if _BATCH is None:
        _BATCH = run_batch(batch_sources())
    if src not in _BATCH:
        _BATCH.update(run_batch([src]))
    return _BATCH[src]


def _js(src):
    d2 = _js_result(src)
    if "crash" in d2:
        return ("HOST-EXCEPTION", d2["crash"].split("\n")[0], [])
    if d2["tag"]:
        return ("refused", "PARSE", []) if d2["tag"] == "PARSE" \
            else ("error", d2["tag"], [])
    return ("ok", None, d2["output"])


def _js_message(src):
    """The rendered runtime message, for the byte-identity assertions. `run`
    reports it alongside the tag (C2) because a tag is deliberately shared
    across many different messages, so tag agreement is not text agreement."""
    d2 = _js_result(src)
    assert "crash" not in d2, d2["crash"]
    return d2["message"]


def _py_message(src):
    try:
        Interpreter(host=TestHost(responses=CFG["responses"],
                                  files=dict(CFG["files"]))).run(src)
    except PlanesError as e:
        return str(e)
    raise AssertionError(f"interp.py did not refuse:\n{src}")


def _builtin_cases():
    return [(f"{b} of {kind}", _prog(b, lit))
            for b in BUILTINS for kind, lit in VALUES]


def _other_cases():
    """Every other place a host primitive is reached with a value of the wrong
    kind. Constraint 6 is not limited to builtins, so the sweep is not either."""
    out = []
    for kind, lit in VALUES:
        out += [
            (f"field of {kind}", f"x = {lit}\nshow text of x.a\n"),
            (f"for each over {kind}", f"for each i in {lit}:\n  show i\n"),
            (f"plus onto {kind}", f"show text of ({lit} plus 1)\n"),
            (f"with on {kind}", f"show text of ({lit} with a: 2)\n"),
            (f"in {kind}", f"show text of (1 in {lit})\n"),
            (f"text in {kind}", f'show text of ("a" in {lit})\n'),
            (f"first of {kind}", f"show text of (first 1 of {lit})\n"),
            (f"first {kind} of a list",
             f"show text of (first {lit} of [1, 2])\n"),
            (f"round {kind}", f"show text of (round {lit} to 2 places)\n"),
            (f"{kind} + 1", f"show text of ({lit} + 1)\n"),
            (f"{kind} < 1", f"show text of ({lit} < 1)\n"),
            (f"{kind} / 3", f"show text of ({lit} / 3)\n"),
            (f"not {kind}", f"show text of (not {lit})\n"),
            (f"write to a {kind}", f"use file\nwrite [1] to {lit}\n"),
            (f"show {kind}", f"show {lit}\n"),
            (f"fail with {kind}", f"x = {lit}\nfail x as oops\n"),
            (f"when on {kind}",
             f"when {lit} is {{ a: 1 }}:\n  show 1\nelse:\n  show 2\n"),
        ]
    return out


# =========================================================== constraint 6, both halves

def test_no_host_exception_escapes_from_any_builtin():
    """The first invariant. `count of 5` raised `TypeError: object of type
    'Number' has no len()` before C2 — a Python traceback where a Planes error
    belongs."""
    leaks = [(label, r[1]) for label, src in _builtin_cases()
             if (r := _py(src))[0] == "HOST-EXCEPTION"]
    assert not leaks, "host exceptions escaping interp.py:\n" + "\n".join(
        f"  {lab}: {msg}" for lab, msg in leaks)


def test_no_host_exception_escapes_from_any_other_operation():
    """The same invariant past the builtins, because constraint 6 does not stop
    at them. `first 1 of 5` and `1 in 5` both reached a host primitive."""
    leaks = [(label, r[1]) for label, src in _other_cases()
             if (r := _py(src))[0] == "HOST-EXCEPTION"]
    assert not leaks, "host exceptions escaping interp.py:\n" + "\n".join(
        f"  {lab}: {msg}" for lab, msg in leaks)


def test_every_builtin_agrees_across_both_implementations():
    """The second invariant, as a test: a host stringification leaking is
    exactly what makes the two disagree, so agreement over the whole sweep is
    the assertion that neither leaks."""
    if NODE is None:
        return
    bad = []
    for label, src in _builtin_cases():
        py, js = _py(src), _js(src)
        if py != js:
            bad.append(f"  {label}: py={py} js={js}")
    assert not bad, "builtin divergences:\n" + "\n".join(bad)


def test_every_other_operation_agrees_across_both_implementations():
    if NODE is None:
        return
    bad = []
    for label, src in _other_cases():
        py, js = _py(src), _js(src)
        if py != js:
            bad.append(f"  {label}: py={py} js={js}")
    assert not bad, "operation divergences:\n" + "\n".join(bad)


# ============================================== the two families, named and closed

def test_family_one_count_refuses_a_non_collection_naming_the_fix():
    """`count of` a number, a boolean, or nothing. The tag the JavaScript side
    already used, and the fix clause neither side had."""
    for kind, lit in VALUES:
        if kind in ("text", "list", "record"):
            continue
        try:
            Interpreter(host=TestHost()).run(
                f"x = {lit}\nshow text of (count of x)\n")
        except PlanesError as e:
            assert e.tag == "not-a-collection", (kind, e.tag)
            assert e.fix, f"count of {kind} names no fix"
            assert "a list, a record, or text" in e.fix, e.fix
        else:
            raise AssertionError(f"count of {kind} was accepted")


def test_family_two_the_three_text_builtins_name_text_of_as_the_fix():
    """The ruled fix: they error, naming `text of`. Ten cases — three builtins
    across the five value kinds that are not text, minus the two `lower`/`upper`
    of a boolean cases that used to agree by accident."""
    seen = 0
    for name in ("lower", "upper", "normalize"):
        for kind, lit in VALUES:
            if kind == "text":
                continue
            try:
                Interpreter(host=TestHost()).run(
                    f"x = {lit}\nshow text of ({name} of x)\n")
            except PlanesError as e:
                seen += 1
                assert e.tag == "not-text", (name, kind, e.tag)
                assert f"{name} of (text of n)" in e.fix, e.fix
            else:
                raise AssertionError(f"{name} of {kind} was accepted")
    assert seen == 15, seen


def test_the_three_text_builtins_still_pass_text_through():
    """The guard refuses a non-string and nothing else — normalize still
    composes, and the derivation label is unchanged."""
    itp = Interpreter(host=TestHost())
    itp.run('show upper of (lower of "AbC")\nshow normalize of "é"\n')
    assert itp.output == ["ABC", "é"]


def test_the_family_two_message_is_identical_in_both_implementations():
    """A.5: byte for byte. The whole point of the ruling is that the answer
    stops depending on which host ran the program."""
    if NODE is None:
        return
    for name in ("lower", "upper", "normalize"):
        src = f"xs = [1, 2]\nshow text of ({name} of xs)\n"
        assert _py(src) == _js(src) == ("error", "not-text", []), name


# ================================ every runtime message this build changed, byte for byte

# The whole set, as programs. Each reaches exactly one of the messages C2 wrote
# or rewrote on the runtime side. Tag agreement is not text agreement — the tags
# here are shared across many messages — so these compare the rendered text.
RUNTIME_MESSAGES = (
    ("count of a non-collection", "x = 5\nshow text of (count of x)\n"),
    ("lower of a list", "xs = [1, 2]\nshow text of (lower of xs)\n"),
    ("upper of a record", "r = { a: 1 }\nshow text of (upper of r)\n"),
    ("normalize of nothing", "x = nothing\nshow text of (normalize of x)\n"),
    ("whole of text", 'x = "5"\nshow text of (whole of x)\n'),
    ("whole of a list", "xs = [1, 2]\nshow text of (whole of xs)\n"),
    ("first n of a non-collection", "show text of (first 1 of 5)\n"),
    ("first text of a list", 'show text of (first "5" of [1, 2])\n'),
    ("in a non-collection", "show text of (1 in 5)\n"),
    ("a number in text", 'show text of (1 in "a1b")\n'),
    ("ask a non-text url", "use http\nx = 5\nshow text of (ask of x)\n"),
    ("read a non-text path", "use file\nxs = [1]\nshow text of (read of xs)\n"),
    ("write to a non-text destination",
     "use file\nr = { a: 1 }\nwrite [1] to r\n"),
    ("wrong arity, function",
     "to add of a, b:\n  give a + b\nshow text of (add of 1)\n"),
    ("wrong arity, foreign",
     'foreign sorted of xs from "builtins.sorted" doing ask xs\n'
     "show text of (sorted of [1], [2])\n"),
)


def test_every_runtime_message_this_build_changed_is_byte_identical():
    if NODE is None:
        return
    bad = []
    for label, src in RUNTIME_MESSAGES:
        py, js = _py_message(src), _js_message(src)
        if py != js:
            bad.append(f"  {label}:\n    py={py!r}\n    js={js!r}")
    assert not bad, "runtime message divergences:\n" + "\n".join(bad)


def test_every_runtime_message_this_build_changed_names_a_fix():
    """Each of them carries a continuation clause — the assertion that the
    catalogue's count is a count of what a reader actually sees."""
    for label, src in RUNTIME_MESSAGES:
        msg = _py_message(src)
        assert "\n  try: " in msg, f"{label} names no fix:\n{msg}"


def test_a_text_value_in_an_error_detail_is_quoted():
    """`fmt` renders text without quotes — it is what `show` prints — so
    `whole of "5"` used to report `cannot take the whole part of 5`, which reads
    as a number and is the one thing the message is about. The quotes are the
    whole fix: Planes has one string syntax, so a quoted value is
    unambiguously text.

    C3 applies this at every error-detail site, not the two C2 reached, and
    drops C2's `text ` prefix — the quotes alone carry it, and the bare form is
    what `grammar/interp.planes` already produced."""
    assert 'the whole part of "5"' in _py_message(
        'x = "5"\nshow text of (whole of x)\n')
    assert 'must be a number, found "5"' in _py_message(
        'show text of (first "5" of [1, 2])\n')
    # The four sites C2 reported and left.
    assert 'cannot combine "5" with 1 using +' in _py_message(
        'x = "5"\nshow text of (x + 1)\n')
    assert 'cannot round "5"' in _py_message(
        'x = "5"\nshow text of (round x to 2 places)\n')
    assert "cannot use '-' on \"5\"" in _py_message(
        'x = "5"\nshow text of (x - 1)\n')
    assert 'cannot compare "5" with 1' in _py_message(
        'x = "5"\nshow text of (x < 1)\n')
    # Every other kind still renders as `fmt` renders it, so nothing else moved.
    assert "cannot take the whole part of true" in _py_message(
        "x = true\nshow text of (whole of x)\n")
    assert "cannot take the whole part of [2 items]" in _py_message(
        "x = [1, 2]\nshow text of (whole of x)\n")
    assert "cannot take the whole part of {record}" in _py_message(
        "x = { a: 1 }\nshow text of (whole of x)\n")


def test_a_list_or_record_in_a_detail_names_its_shape_not_its_contents():
    """The reason this does not simply defer to the canonical form: an error
    detail has to be bounded. A canonical render would put every element of a
    10,000-item list — or a record's credential — into text that goes to stderr
    and into logs."""
    big = "xs = [" + ", ".join(str(i) for i in range(200)) + "]\n"
    msg = _py_message(big + "show text of (whole of xs)\n")
    assert "[200 items]" in msg, msg
    assert "17, 18, 19" not in msg, "the detail spilled the list's contents"
    secret = 'r = { token: "hunter2" }\nshow text of (whole of r)\n'
    msg2 = _py_message(secret)
    assert "{record}" in msg2, msg2
    assert "hunter2" not in msg2, "the detail spilled a record's contents"


# ================================================ the siblings the sweep found

def test_an_effect_target_must_be_text():
    """`ask`, `read`, and `write ... to` handed the value straight to the host.
    `open(5, "w")` opens file descriptor 5, which is not a refusal."""
    cases = [("use http\nshow text of (ask 5)\n", "a url to ask"),
             ("use file\nshow text of (read [1])\n", "a path to read"),
             ("use file\nwrite [1] to { a: 1 }\n",
              "a destination to write to")]
    for src, what in cases:
        try:
            Interpreter(host=TestHost()).run(src)
        except PlanesError as e:
            assert e.tag == "not-text", (src, e.tag)
            assert e.detail.startswith(what), e.detail
            assert "text of" in e.fix, e.fix
        else:
            raise AssertionError(f"accepted a non-text target:\n{src}")


def test_first_n_of_guards_both_operands():
    """Neither implementation had either guard."""
    itp = Interpreter(host=TestHost())
    try:
        itp.run("show text of (first 1 of 5)\n")
    except PlanesError as e:
        assert e.tag == "not-a-collection", e.tag
        assert "a list or text" in e.fix, e.fix
    else:
        raise AssertionError("first 1 of 5 was accepted")
    try:
        itp.run('show text of (first "a" of [1, 2])\n')
    except PlanesError as e:
        assert e.tag == "not-a-number", e.tag
        assert "first 3 of items" in e.fix, e.fix
    else:
        raise AssertionError('first "a" of a list was accepted')


def test_in_names_the_collection_not_the_operator():
    """`1 in 5` answered `unknown-operator` on the JavaScript side, which named
    the wrong thing: `in` is an operator the language defines, and what was
    wrong was the value on the right."""
    try:
        Interpreter(host=TestHost()).run("show text of (1 in 5)\n")
    except PlanesError as e:
        assert e.tag == "not-a-collection", e.tag
        assert "a list, a record's field names, or text" in e.fix, e.fix
    else:
        raise AssertionError("1 in 5 was accepted")


def test_in_over_text_looks_for_text():
    """Python raised a TypeError; V8 coerced the number to a string, so
    `1 in "a1b"` would have answered true on one host and raised on the
    other."""
    try:
        Interpreter(host=TestHost()).run('show text of (1 in "a1b")\n')
    except PlanesError as e:
        assert e.tag == "not-text", e.tag
    else:
        raise AssertionError('1 in "a1b" was accepted')


def test_the_membership_cases_that_worked_still_work():
    itp = Interpreter(host=TestHost())
    itp.run('show text of (1 in [1, 2])\nshow text of ("a" in { a: 1 })\n'
            'show text of ("b" in "abc")\n')
    assert itp.output == ["true", "true", "true"]


def test_a_failed_write_is_a_planes_error_not_an_oserror():
    """The third host boundary. `read` and `ask` already converted; a write to
    a directory that does not exist left the host's own OSError to escape."""
    from host import PythonHost
    itp = Interpreter(host=PythonHost())
    dest = os.path.join(tempfile.gettempdir(), "c2-no-such-dir", "f.json")
    try:
        itp.run(f'use file\nwrite [1] to "{dest}"\n')
    except PlanesError as e:
        assert e.tag == "write-failed", e.tag
        assert "writable" in e.fix, e.fix
    else:
        raise AssertionError("a write into a missing directory succeeded")


# ================================================ what the ruling changed for programs

def test_no_corpus_program_relied_on_the_coercion():
    """A.6: a program relying on implicit coercion now fails, and if one did
    that is a finding about the corpus rather than a reason to soften the
    ruling. None did — every corpus program still runs, which this asserts
    directly rather than by reading the CI log."""
    import glob
    broken = []
    for f in sorted(glob.glob("corpus/**/*.planes", recursive=True)):
        src = open(f, encoding="utf-8").read()
        if any(ln.strip().startswith("use ") for ln in src.splitlines()):
            continue            # needs run_file's cross-file table
        itp = Interpreter(host=TestHost(
            responses={}, files={}, now=1_000_000.0))
        try:
            itp.run(src)
        except PlanesError as e:
            if e.tag in ("not-text", "not-a-collection"):
                broken.append(f"{f}: {e.tag}: {e.detail}")
        except Exception:                                # noqa: BLE001, S110
            pass                # every other refusal is the program's own
    assert not broken, "the family-two ruling broke corpus programs:\n" + \
        "\n".join(broken)


# ============================ C3 — the third implementation, and same-kind pairs
#
# C2 swept `<value> <op> 1` and every builtin, and reported two findings it did
# not close: `fmt` renders text unquoted, so a detail could not tell `"5"` from
# `5`; and the self-hosted `grammar/interp.planes` rendered its details through
# `canonical-of-value` — its own TEST-ORACLE form — so a third implementation
# disagreed with both others and nothing asserted it, because the self-hosted
# suites compare error TAGS and not detail text.
#
# The sweep below closes both. It runs every shape through all three
# implementations and compares tag AND detail, and it adds the pairs C2's
# one-sided sweep could not reach: every ordered pair of value kinds, same-kind
# included. Five more host exceptions were hiding there — `{a:1} < {a:2}`,
# `nothing < nothing`, `[1] in {a:1}`, `{a:1} in {a:1}`, and `true in [1,2]` —
# and two accidents of the host answering instead of refusing: `[1] < [2]` was
# `true` out of Python's list comparison and `true < false` was `false`.

_PL = None


def _planes_interp():
    """grammar/interp.planes, loaded once. The third implementation."""
    global _PL
    if _PL is None:
        from interp import Interpreter as _I
        _PL = _I()
        _PL.run_file("grammar/interp.planes")
    return _PL


# A value of every kind, as each implementation spells one.
_VAL_PLANES = {
    "number": '{ kind: "number", value: 5, deriv: nothing }',
    "text": '{ kind: "text", value: "5", deriv: nothing }',
    "list": '{ kind: "list", items: [{ kind: "number", value: 1, deriv: nothing }, '
            '{ kind: "number", value: 2, deriv: nothing }], deriv: nothing }',
    "record": '{ kind: "record", fields: [{ key: "a", value: '
              '{ kind: "number", value: 1, deriv: nothing } }], deriv: nothing }',
    "boolean": '{ kind: "boolean", value: true, deriv: nothing }',
    "nothing": '{ kind: "nothing", value: nothing, deriv: nothing }',
}
_VAL_SRC = {"number": "5", "text": '"5"', "list": "[1, 2]",
            "record": "{ a: 1 }", "boolean": "true", "nothing": "nothing"}
_KINDS = tuple(_VAL_SRC)


def _three_way_cases():
    cases = []
    for k in _KINDS:
        n = {"x": k}
        for b in ("count", "text", "lower", "upper", "normalize", "whole",
                  "join", "rest"):
            cases.append((f"{b} of {k}", f"{b} of x", n))
        cases += [
            (f"round {k}", "round x to 2 places", n),
            (f"not {k}", "not x", n),
            (f"field of {k}", "x.a", n),
            (f"{k} with a: 2", "x with a: 2", n),
            (f"{k} plus 1", "x plus 1", n),
            (f"first 1 of {k}", "first 1 of x", n),
            (f"first text of {k}", 'first "5" of x', n),
            (f"for each over {k}", "(for each i in x: i)", n),
        ]
    for a in _KINDS:
        for b in _KINDS:
            n = {"x": a, "y": b}
            for op in ("+", "-", "*", "/", "<", "==", "in"):
                cases.append((f"{a} {op} {b}", f"x {op} y", n))
    return cases


FIX_MARKER = "\n  try: "


def _fix_of(message):
    """The fix clause out of a rendered message. Both implementations render
    `tag: detail` and then the clause on its own continuation line, and that
    rendering is asserted byte-identical elsewhere in this file — so reading it
    back is reading the same field, not a second source of truth."""
    return message.split(FIX_MARKER, 1)[1] if FIX_MARKER in message else ""


def _outcome_py(expr, names):
    itp = Interpreter(host=TestHost())
    src = "".join(f"{k} = {_VAL_SRC[v]}\n" for k, v in names.items())
    try:
        itp.run(src + f"show text of ({expr})\n")
    except PlanesError as e:
        return ("error", e.tag, e.detail, e.fix)
    except PlanesSyntaxError:
        return ("parse", "PARSE", "", "")
    except Exception as e:                                   # noqa: BLE001
        return ("HOST", type(e).__name__, str(e)[:70], "")
    return ("ok", "", itp.output[-1] if itp.output else "", "")


def _outcome_js(expr, names):
    d = _js_result(_three_way_src(expr, names))
    if "crash" in d:
        return ("HOST", "crash", d["crash"].split("\n")[0][:70], "")
    if d["tag"] == "PARSE":
        return ("parse", "PARSE", "", "")
    if d["tag"]:
        head = d["message"].split("\n")[0]
        return ("error", d["tag"],
                head.split(": ", 1)[1] if ": " in head else head,
                _fix_of(d["message"]))
    return ("ok", "", d["output"][-1] if d["output"] else "", "")


def _outcome_planes(expr, names):
    """Through grammar/interp.planes — the self-hosted interpreter, running on
    interp.py. `builtin-text` is its own `fmt`, so a successful result comes back
    in the same form the other two show."""
    from interp import Deriv as _D
    from interp import Traced as _T
    i = _planes_interp()
    parts = ['{ name: "%s", value: %s }' % (k, _VAL_PLANES[v])
             for k, v in names.items()]
    i.run("__env = [%s]\n" % ", ".join(parts))
    env = i.env.get("__env")
    try:
        node = i.call("node-of-source",
                      [_T(expr, _D("literal", "<src>", expr, []))], i.env)
        val = i.call("eval", [node, env], i.env)
        return ("ok", "",
                i.call("builtin-text", [val], i.env).value.get("value"), "")
    except PlanesError as e:
        return ("error", e.tag, e.detail, e.fix)
    except Exception as e:                                   # noqa: BLE001
        return ("HOST", type(e).__name__, str(e)[:70], "")


def test_no_host_exception_escapes_from_any_operand_pair():
    """The invariant C2 asserted over a one-sided sweep, re-asserted over every
    ordered pair. `{a:1} < {a:2}`, `nothing < nothing`, `[1] in {a:1}`,
    `{a:1} in {a:1}`, and `true in [1,2]` all leaked a raw host exception."""
    leaks = []
    for label, expr, names in _three_way_cases():
        for name, out in (("py", _outcome_py(expr, names)),
                          ("pl", _outcome_planes(expr, names))):
            if out[0] == "HOST":
                leaks.append(f"  {label} [{name}]: {out[1]} {out[2]}")
    assert not leaks, "host exceptions escaping:\n" + "\n".join(leaks)


def test_all_three_implementations_agree_on_tag_detail_and_fix():
    """The convergence, asserted rather than claimed. Detail text, not just the
    tag — a tag is deliberately shared across many messages, which is why the
    self-hosted side could diverge on every detail while its suite stayed
    green.

    D: and the FIX clause. `errors name the fix` has been a language-level
    commitment since unbound v1.1 §22, and until this build the self-hosted
    implementation kept it nowhere. This sweep is the instrument that closes
    it: for every shape it reaches, the correct self-hosted clause is not a
    decision — it is whatever the reference emits for that same shape, and a
    divergence here names both sides."""
    if NODE is None:
        return
    bad = []
    for label, expr, names in _three_way_cases():
        py = _outcome_py(expr, names)
        js = _outcome_js(expr, names)
        pl = _outcome_planes(expr, names)
        if not (py == js == pl):
            bad.append(f"  {label}\n    py={py}\n    js={js}\n    pl={pl}")
    assert not bad, (f"{len(bad)} divergence(s) across the three "
                     f"implementations:\n" + "\n".join(bad))


def test_ordering_works_on_numbers_and_text_and_nothing_else():
    """What `compare`'s docstring said before it was true. A same-kind pair used
    to reach the host's own `<`, so `[1] < [2]` answered `true` out of Python's
    list comparison — an accident of the host, not the language."""
    for lit in ("[1, 2]", "{ a: 1 }", "true", "nothing"):
        try:
            Interpreter(host=TestHost()).run(
                f"x = {lit}\ny = {lit}\nshow text of (x < y)\n")
        except PlanesError as e:
            assert e.tag == "cannot-compare", (lit, e.tag)
            assert "numbers with numbers, or text with text" in e.fix, e.fix
        else:
            raise AssertionError(f"{lit} < {lit} was ordered")
    # And the two kinds it does order still order.
    itp = Interpreter(host=TestHost())
    itp.run('show text of (1 < 2)\nshow text of ("a" < "b")\n')
    assert itp.output == ["true", "true"]


def test_membership_answers_rather_than_refusing_where_it_can():
    """`in` asks whether an equal element is present, and a differently-typed
    element is an answer. Python's `in` went through guarded equality, so
    `true in [1, 2]` leaked planes_num's own TypeError."""
    itp = Interpreter(host=TestHost())
    itp.run('show text of (true in [1, 2])\nshow text of ([1] in { a: 1 })\n'
            'show text of ("a" in { a: 1 })\nshow text of (1 in [1, 2])\n')
    assert itp.output == ["false", "false", "true", "true"]


if __name__ == "__main__":
    if NODE is None:
        print("  note  node not on PATH — agreement tests skipped")
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
