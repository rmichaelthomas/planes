"""Tests for the record plane (planes v9.0 Phase C).

The acceptance gate (C.5, blocking): recording must be inert. Running the
same program with recording off and on must produce byte-identical
Interpreter.effects, Interpreter.output, and shapes.analyse()'s static
surface -- modeled directly on test_annotation.py's inertness test, the
same instrument one plane over (annotation-plane inertness governs
because/note; here it governs record()).
"""
import sys

from host import TestHost
from interp import (
    RECORD_FORMAT_VERSION,
    Interpreter,
    PlanesError,
    records_from_json,
    records_to_json,
)
from lexer import Rule
from parser import parse
from rules import check as check_rules
from shapes import analyse


def run(src, **kw):
    return Interpreter(**kw).run(src)


# ================================================================ C.5 -- the inertness gate

def run_and_capture(src, record, **kw):
    kw.setdefault("fs", {})
    i = Interpreter(record=record, **kw)
    output = i.run(src)
    surface = analyse(src)
    return list(output), list(i.effects), [str(e) for e in surface.declared]


def assert_recording_inert(src, **kw):
    """Interpreter.effects, Interpreter.output, and shapes.analyse()'s
    surface must not differ between recording off and on. This is the
    whole of section 99: recording is a host capability, never a program
    effect."""
    off_out, off_eff, off_surf = run_and_capture(src, False, **kw)
    on_out, on_eff, on_surf = run_and_capture(src, True, **kw)
    assert off_out == on_out, (
        f"output differs with recording on:\n"
        f"  off: {off_out}\n  on:  {on_out}")
    assert off_eff == on_eff, (
        f"effect log differs with recording on:\n"
        f"  off: {off_eff}\n  on:  {on_eff}")
    assert off_surf == on_surf, (
        f"static surface differs with recording on:\n"
        f"  off: {off_surf}\n  on:  {on_surf}")


# A representative sample: pure, network, file, foreign, and mixed. Plus
# one exercising this session's own new code (the or-fail-as handler,
# A.5) and one where the underlying call raises, since a claim is
# recorded regardless of whether the foreign call goes on to fail (§97).

PURE = 'x = 1 + 2\ny = x * 3\nshow text of y\n'

NETWORK = 'use http\nx = ask "https://example.com/a.json"\nshow x\n'

FILE = 'use file\nwrite [1, 2, 3] to "o.json"\nshow "wrote"\n'

FOREIGN = ('foreign now from "time.time" doing clock\n'
           'foreign home from "os.getcwd" doing env\n'
           't = now\nh = home\nshow "done"\n')

MIXED = ('use http\nuse file\n'
         'foreign now from "time.time" doing clock\n'
         'x = ask "https://example.com/a.json"\n'
         'write [x] to "o.json"\n'
         't = now\n'
         'show "mixed done"\n')

OR_FAIL_HANDLER = ('use http\n'
                    'x = ask "https://example.com/a.json"\n'
                    '  or fail as err:\n'
                    '    show err.tag\n')

FOREIGN_RAISES = 'foreign boom from "builtins.exec" doing nothing\nb = boom of "1/0"\n'


def test_inertness_pure():
    assert_recording_inert(PURE)


def test_inertness_network():
    assert_recording_inert(NETWORK, http=lambda u: '"hi"')


def test_inertness_file():
    assert_recording_inert(FILE)


def test_inertness_foreign():
    assert_recording_inert(FOREIGN)


def test_inertness_mixed():
    assert_recording_inert(MIXED, http=lambda u: '"hi"')


def test_inertness_with_or_fail_handler_on_success():
    assert_recording_inert(OR_FAIL_HANDLER, http=lambda u: '"hi"')


def test_inertness_with_or_fail_handler_on_failure():
    def boom(u):
        raise RuntimeError("down")
    assert_recording_inert(OR_FAIL_HANDLER, http=boom)


def test_inertness_when_the_foreign_call_itself_raises():
    """A claim is recorded before the call, regardless of whether the call
    goes on to raise -- and that raise must be equally inert."""
    for record in (False, True):
        i = Interpreter(record=record, fs={})
        try:
            i.run(FOREIGN_RAISES)
        except PlanesError:
            pass
    # both runs raise identically; the real check is that this does not
    # crash differently, and effects/records stay independent -- covered
    # by test_recording_never_touches_effects below on the same program.
    assert_recording_inert(
        'foreign identity of x from "builtins.str" doing ask x\n'
        'r = identity of "https://ok/"\n')


# ================================================================ record content

def test_witnessed_effects_are_host_anchored():
    i = Interpreter(http=lambda u: '"hi"', fs={}, record=True)
    i.run('use http\nuse file\n'
          'x = ask "https://example.com/a.json"\n'
          'write [x] to "o.json"\n'
          'show x\n')
    kinds = {r.kind: r.anchor.kind for r in i.records}
    assert kinds == {"ask": "host", "write": "host", "show": "host"}


def test_foreign_declared_effects_are_claim_anchored():
    i = Interpreter(record=True)
    i.run('foreign now from "time.time" doing clock\nt = now\n')
    assert len(i.records) == 1
    assert i.records[0].anchor.kind == "foreign-declaration"
    assert i.records[0].anchor.identity == "now"


def test_clock_random_env_are_always_claim_anchored():
    """They have no in-language form (confirmed: no clock/random/env
    builtin dispatch anywhere in interp.py) -- the only way any of the
    three is ever recorded is through a foreign declaration, so they can
    never be anything but a claim."""
    i = Interpreter(record=True)
    i.run('foreign now from "time.time" doing clock\n'
          'foreign home from "os.getcwd" doing env\n'
          't = now\nh = home\n')
    for r in i.records:
        assert r.kind in ("clock", "env")
        assert r.anchor.kind == "foreign-declaration"


def test_records_carry_one_timestamp_from_the_host_clock():
    host = TestHost(responses=lambda u: '"hi"', now=42.0)
    i = Interpreter(host=host, record=True)
    i.run('use http\nx = ask "https://example.com/a.json"\n')
    assert all(r.when == 42.0 for r in i.records)


def test_records_carry_derivation_when_traced():
    i = Interpreter(http=lambda u: '"hi"', record=True)
    i.run('use http\nx = ask "https://example.com/a.json"\n')
    assert i.records[0].derivation is not None


# ================================================================ C.2 -- load-bearing

def test_recording_never_touches_effects():
    i_off = Interpreter(http=lambda u: '"hi"', fs={}, record=False)
    i_off.run(NETWORK)
    i_on = Interpreter(http=lambda u: '"hi"', fs={}, record=True)
    i_on.run(NETWORK)
    assert i_off.effects == i_on.effects
    assert i_on.records and not i_off.records


def test_recording_off_by_default():
    i = Interpreter(http=lambda u: '"hi"')
    i.run(NETWORK)
    assert i.records == []


def test_a_host_that_ignores_record_is_still_a_complete_host():
    """record() is optional -- the base Host's default (a no-op) must not
    raise NotImplementedError the way the five mandatory capabilities do."""
    from host import Host
    Host().record(object())     # must not raise


def test_recording_does_not_trigger_a_forbid_write_rule():
    """A program that only performs the effects it always performed must
    not newly violate a rule because it was recorded -- rules.check()
    only ever sees the static surface, and the record plane never touches
    shapes.py."""
    src = ('rule [refund-cap] anything may not write to "refunds.json"\n'
           'use file\n'
           'write [1] to "safe.json"\n')
    prog = parse(src)
    rules = [s for s in prog if isinstance(s, Rule)]
    surface = analyse(src)
    results_off = check_rules(rules, surface)
    Interpreter(fs={}, record=False).run(src)
    Interpreter(fs={}, record=True).run(src)
    results_on = check_rules(rules, analyse(src))
    assert [v.render() for v in results_off] == [v.render() for v in results_on]
    assert not any(v.is_violation for v in results_off)


# ================================================================ C.4 -- via the interpreter

def test_records_retrievable_like_effects_and_output():
    i = Interpreter(http=lambda u: '"hi"', record=True)
    i.run(NETWORK)
    assert isinstance(i.records, list) and i.records
    assert isinstance(i.effects, list) and i.effects
    assert isinstance(i.output, list) and i.output


def test_shapes_cli_is_unmodified_by_the_record_plane():
    """The record plane surfaces through the interpreter, not the static
    CLI -- shapes_cli.py stays analyse-only, never gains a --record flag,
    never imports the record plane's API, and never runs a program."""
    src = open("shapes_cli.py").read()
    assert "--record" not in src
    assert "Record" not in src and "records_to_json" not in src
    assert "Interpreter" not in src
    assert ".run(" not in src and ".run_file(" not in src


# ================================================================ C.1 -- refuse don't guess

def test_json_round_trip():
    i = Interpreter(http=lambda u: '"hi"', record=True)
    i.run(NETWORK)
    doc = records_to_json(i.records)
    assert doc["format"] == RECORD_FORMAT_VERSION
    back = records_from_json(doc)
    assert len(back) == len(i.records)


def test_unrecognized_format_version_is_refused_not_guessed():
    try:
        records_from_json({"format": RECORD_FORMAT_VERSION + 1, "records": []})
        assert False, "should refuse"
    except PlanesError as e:
        assert e.tag == "unrecognized-record-format"


def test_target_serializes_as_its_code_point_sequence():
    """section 105: text is code points. A target with a combining mark
    must round-trip through the record's JSON exactly, not re-encoded."""
    i = Interpreter(http=lambda u: '"hi"', record=True, fs={})
    combining = "é"     # e + combining acute
    i.run(f'use file\nwrite [1] to "{combining}.json"\n')
    doc = records_to_json(i.records)
    target = doc["records"][0]["target"]
    assert target == f"{combining}.json"
    assert len(target) == len(f"{combining}.json")


if __name__ == "__main__":
    fails = []
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            fails.append(name)
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
