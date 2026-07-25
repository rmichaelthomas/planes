"""Tests for the bracket-misparse fix (fix/text-iteration-and-the-lexer).

PROBE_LEXER.md §2 found, by direct AST inspection, that `c = s[1]` does not
raise at all: `parse_primary` returns `Var("s")` for the name, the
assignment completes as `c = s`, and the leftover `[1]` is read as an
unrelated second statement -- a list literal, evaluated and silently
discarded. `c` ends up bound to the whole string, not a character, with
nothing to signal that this happened.

This is not a missing feature (Planes still has no index or slice syntax,
and this build does not add one). It is a missing syntax error: a `[`
immediately following a completed primary expression, with no operator
between them, has exactly one plausible reading -- indexing -- and Planes
has no grammar for it. That should refuse to parse, not silently mean
something else.
"""
import sys

from interp import Interpreter
from parser import PlanesSyntaxError, parse


def parses(src):
    parse(src)
    return True


def outputs(src):
    return Interpreter().run(src)


def raises_bracket_error(src):
    try:
        parse(src)
        return None
    except PlanesSyntaxError as e:
        return str(e)


# ================================================================ the fix fires

def test_name_immediately_followed_by_bracket_raises():
    msg = raises_bracket_error('s = "abc"\nc = s[1]\n')
    assert msg is not None, "should raise"
    assert "index" in msg or "slice" in msg
    assert "first n of" in msg


def test_parenthesized_expr_immediately_followed_by_bracket_raises():
    msg = raises_bracket_error('a = 1\nx = (a)[1]\n')
    assert msg is not None, "should raise"
    assert "first n of" in msg


def test_list_literal_immediately_followed_by_bracket_raises():
    msg = raises_bracket_error('x = [1, 2][0]\n')
    assert msg is not None, "should raise"


def test_string_literal_immediately_followed_by_bracket_raises():
    msg = raises_bracket_error('x = "abc"[0]\n')
    assert msg is not None, "should raise"


def test_call_result_immediately_followed_by_bracket_raises():
    src = 'to f of x:\n  give x\n\nr = f of 1[0]\n'
    msg = raises_bracket_error(src)
    assert msg is not None, "should raise"


# ================================================================ legitimate brackets still parse

def test_list_literal_after_equals_still_parses():
    assert parses('xs = [1, 2]\n')


def test_list_literal_as_of_argument_still_parses():
    assert parses('to f of x:\n  give x\n\nr = f of [1]\n')


def test_list_literal_after_comma_in_call_args_still_parses():
    assert parses('to f of a, b:\n  give a\n\nr = f(1, [2, 3])\n')


def test_list_literal_after_open_paren_still_parses():
    assert parses('x = ([1, 2] == [1, 2])\n')


def test_list_literal_as_record_field_value_still_parses():
    assert parses('r = { xs: [1, 2] }\n')


def test_nested_list_literals_still_parse():
    assert parses('xs = [[1, 2], [3, 4]]\n')


def test_list_literal_after_binary_operator_still_parses():
    assert parses('xs = [1] + [2]\n')


def test_list_literal_as_for_each_source_still_parses():
    assert parses('ys = for each x in [1, 2, 3]: x\n')


def test_list_literal_after_plus_keyword_still_parses():
    assert parses('xs = [1]\nys = xs plus 2\n')


def test_bracketed_rule_name_still_parses():
    """Statement-level `[name]` in `rule [...]` is a different grammar
    position (parse_rule, not parse_primary) and must be unaffected."""
    assert parses('rule [no-network] anything may not ask\n')


# ================================================ S2 §4: multi-line literals in a body

# The defect (REPORT_SELFHOST_SWEEP.md §10): a multi-line record or list
# literal parses at top level but truncates the block when it sits inside an
# indented function body. The literal's continuation line raises the
# indentation, so the tokenizer emits a BEGIN the bracket parser consumes and
# a matching END that leaks to the block level, where parse_block (unlike
# parse_program) mistakes it for the block's close — so `give` falls outside
# the function and the binding is lost. It parses without error; the damage is
# a wrong block structure, so these run the program rather than only parse it.

def test_multiline_record_literal_inside_a_function_body():
    src = ('to mk of n:\n'
           '  r = { a: 1,\n'
           '        b: 2 }\n'
           '  give r\n'
           'show (mk of 5).b\n')
    assert outputs(src) == ["2"], "the block must keep `give r`; it was truncated"


def test_multiline_list_literal_inside_a_function_body():
    src = ('to mk of n:\n'
           '  xs = [1,\n'
           '        2,\n'
           '        3]\n'
           '  give xs\n'
           'show count of (mk of 0)\n')
    assert outputs(src) == ["3"]


def test_statement_after_a_multiline_literal_in_a_body_still_runs():
    # The give is not the only casualty: any statement after the literal was
    # dropped from the block. Here a second binding must survive.
    src = ('to mk of n:\n'
           '  r = { a: 1,\n'
           '        b: 2 }\n'
           '  doubled = r.b + r.b\n'
           '  give doubled\n'
           'show mk of 0\n')
    assert outputs(src) == ["4"]


def test_multiline_nested_record_inside_a_function_body():
    src = ('to mk of n:\n'
           '  r = { outer: { x: 1 },\n'
           '        y: 2 }\n'
           '  give r.y\n'
           'show mk of 0\n')
    assert outputs(src) == ["2"]


def test_multiline_record_at_top_level_still_works():
    # Regression guard: the top-level case worked before and must still work.
    src = ('r = { a: 1,\n'
           '      b: 2 }\n'
           'show r.b\n')
    assert outputs(src) == ["2"]


# ================================================================ full corpus: zero regressions

def test_every_valid_planes_file_in_the_repo_still_parses():
    """The 31-file corpus (8 root files + 23 demo/ files, excluding
    demo/cycle/*) -- 29 at REPORT_GRAMMAR_AMBER.md §4, 30 since
    demo/association.planes entered it (fix/recursion-leak-and-fifth-
    amber-site Phase 3), 31 since demo/status_threading.planes entered it
    (S2 §A.6 / Phase 5) -- each analysed through the real module loader
    (`shapes.analyse_file`, follow=True) rather than parsed standalone --
    module-graph files depend on cross-file known_funcs (e.g.
    demo/app/net.planes's `api base`, defined in config.planes) that only
    exist once the whole graph is loaded.

    demo/clash/main.planes is the one documented exception: it exists to
    demonstrate the two-modules-define-one-name collision error (README
    'Names are flat across a module graph'), so a ModuleError there is
    the correct, pre-existing outcome, not a regression. Everything else
    must analyse clean -- a PlanesSyntaxError anywhere else means the
    bracket guard over-fired on a legitimate construct.
    """
    from modules import ModuleError
    from parser import PlanesSyntaxError
    from shapes import analyse_file

    root_files = ["annotated.planes", "foreign.planes", "gate.planes", "hn.planes",
                  "money.planes", "names.planes", "ordinary.planes", "pypi.planes"]
    import glob
    demo_files = sorted(f for f in glob.glob("demo/**/*.planes", recursive=True)
                        if "cycle" not in f)
    corpus = root_files + demo_files
    assert len(corpus) == 31, f"expected 31 corpus files, found {len(corpus)}"

    for path in corpus:
        try:
            analyse_file(path, follow=True)
        except ModuleError:
            assert path == "demo/clash/main.planes", \
                f"unexpected ModuleError on {path}"
        except PlanesSyntaxError as e:
            raise AssertionError(f"bracket guard regression on {path}: {e}")


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
