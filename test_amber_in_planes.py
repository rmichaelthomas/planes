"""Amber refusal agreement: parser.py vs. grammar/parser.planes.

The corpus contains no ambiguous file, so its fire rate is zero and the
four amber sites can never be exercised by corpus agreement (S3a A.3).
Each site therefore gets one deliberately ambiguous fragment under
probe/amber/. This test asserts that BOTH parsers refuse each fragment,
that the refusal names both readings, and that the two refusal messages
are byte-identical -- one refusal style, not two (A.3, failure mode 3):
grammar/parser.planes reproduces parser.py's render_amber output exactly,
modulo the `ambiguity: ` fail-tag prefix the Planes runtime prepends. It
also re-asserts that the corpus fire rate stays zero.

The four sites, and the parser.py function each fragment exercises:
  site 1  parse_primary multi-word longest match   raise_amber_multiword
  site 2  parse_primary juxtaposition (takes_arg)   check_juxtaposition_ambiguity
  site 3  paren_is_arglist                          check_paren_arglist_ambiguity
  site 4  parse_statement USE rename clause          check_rename_name_ambiguity
"""
import sys

from interp import Deriv, Interpreter, Traced
from parser import PlanesAmbiguity, parse

_interp = None


def _get_interp():
    global _interp
    if _interp is None:
        _interp = Interpreter()
        _interp.run_file("grammar/parser.planes")
    return _interp


def _traced(v):
    return Traced(v, Deriv("literal", repr(v), v, []))


def _planes_refusal(src):
    """(refused, message) for grammar/parser.planes parsing src."""
    i = _get_interp()
    try:
        i.call("canonical-of-program-source", [_traced(src)], i.env)
        return (False, None)
    except Exception as e:  # noqa: BLE001 -- a refusal is any raise here
        return (True, str(e))


def _py_refusal(src):
    """(refused, message) for parser.py parsing src -- only PlanesAmbiguity
    counts as a refusal; any other exception is a fixture bug, not a site
    firing."""
    try:
        parse(src)
        return (False, None)
    except PlanesAmbiguity as e:
        return (True, str(e))


# fixture path -> the site it exercises
SITES = {
    "probe/amber/site1_multiword.planes": "multi-word longest match",
    "probe/amber/site2_juxtaposition.planes": "juxtaposition single argument",
    "probe/amber/site3_paren_arglist.planes": "parenthesised argument list",
    "probe/amber/site4_rename.planes": "use-rename clause",
}


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_all_four_fixtures_refuse_on_both_sides():
    for path in SITES:
        src = _read(path)
        py_ref, _ = _py_refusal(src)
        pl_ref, _ = _planes_refusal(src)
        assert py_ref, f"{path}: parser.py did not refuse (fixture is not ambiguous)"
        assert pl_ref, f"{path}: grammar/parser.planes did not refuse"


def test_each_refusal_names_both_readings():
    for path in SITES:
        _, pl_msg = _planes_refusal(_read(path))
        assert "reading A:" in pl_msg, f"{path}: reading A missing\n{pl_msg}"
        assert "reading B:" in pl_msg, f"{path}: reading B missing\n{pl_msg}"


def test_refusal_messages_are_byte_identical():
    """The Planes refusal equals parser.py's render_amber output exactly,
    modulo the `ambiguity: ` fail-tag prefix the Planes runtime adds --
    one refusal style, not two (A.3)."""
    for path in SITES:
        src = _read(path)
        _, py_msg = _py_refusal(src)
        _, pl_msg = _planes_refusal(src)
        assert pl_msg == f"ambiguity: {py_msg}", (
            f"{path}: refusal messages diverge\n"
            f"--- planes ---\n{pl_msg}\n--- python ---\nambiguity: {py_msg}")


def test_corpus_fire_rate_is_zero():
    """No corpus file is ambiguous, so a correct implementation refuses
    nothing there (A.3). This guards against a site firing on valid code:
    every corpus file may raise (statement forms past the ladder), but none
    may raise an `ambiguity:` refusal."""
    from scripts.parser_corpus_agreement import corpus
    i = _get_interp()
    fired = []
    for f in corpus():
        try:
            i.call("canonical-of-program-source", [_traced(_read(f))], i.env)
        except Exception as e:  # noqa: BLE001
            if str(e).startswith("ambiguity:"):
                fired.append(f)
    assert not fired, f"amber fired on corpus files (fire rate must be zero): {fired}"


def _make_site_test(path):
    def t():
        src = _read(path)
        py_ref, py_msg = _py_refusal(src)
        pl_ref, pl_msg = _planes_refusal(src)
        assert py_ref, f"{path}: parser.py did not refuse"
        assert pl_ref, f"{path}: grammar/parser.planes did not refuse"
        assert pl_msg == f"ambiguity: {py_msg}", f"{path}: messages diverge"
        assert "reading A:" in pl_msg and "reading B:" in pl_msg
    return t


test_site1_multiword = _make_site_test("probe/amber/site1_multiword.planes")
test_site2_juxtaposition = _make_site_test("probe/amber/site2_juxtaposition.planes")
test_site3_paren_arglist = _make_site_test("probe/amber/site3_paren_arglist.planes")
test_site4_rename = _make_site_test("probe/amber/site4_rename.planes")


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
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
