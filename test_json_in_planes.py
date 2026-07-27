"""C1 — JSON, parsed and written in Planes: grammar/json.planes against the
reference.

The claim under test was made twice and never revisited: **Planes cannot parse
JSON without a host, and that is the one irreducible host capability.** It was
made on the strength of Planes having no parser — before `grammar/parser.planes`
existed. Parsing Planes is a considerably harder job than parsing JSON, so the
claim was owed a re-test, and this file is it.

The reference is the specification, on both sides of the boundary:

  * reading — `host.parse_json` (json.loads) followed by `interp.from_foreign`,
    which is what the interpreter's `ask` returns;
  * writing — `interp.to_json`, i.e. `json.dumps(unwrap(v), indent=2)`, which is
    what the `write` effect puts in a file.

grammar/json.planes reproduces both, in the language, with no addition to it:
`json-parse of text` gives a tagged interp.planes value and `json-text-of` gives
the bytes. Every case below is checked against the reference rather than against
a hand-written expectation, so the test cannot drift from what Planes actually
does today.

Three results this file pins down rather than asserts away, because each is a
finding reported in REPORT_HOST_BOUNDARY.md:

  1. **Escapes with no Planes spelling are refused, not mangled.** JSON has
     eight string escapes; a Planes string literal has four (\\" \\\\ \\n \\t)
     and no code-point escape, `chr of n` having been declined when the escapes
     were settled. So \\r, \\b, \\f and \\uXXXX are refused with a message that
     names why. The refusal is the honest behaviour and is asserted here.
  2. **Non-ASCII text is written as itself, not as \\uXXXX** — same cause. The
     output is valid JSON the reference reads back to the same value; it is not
     byte-identical to `ensure_ascii=True`. Both halves are asserted.
  3. **Past 17 significant digits the Planes reader is the exact one.** The
     reference routes a JSON number through a float; this reads the decimal
     text. They agree on every number a float round-trips — every number in the
     corpus — and past that Planes keeps the digits Python drops.
"""
import json
import sys

from interp import (
    Deriv,
    Interpreter,
    PlanesError,
    Traced,
    from_foreign,
    to_json,
)
from planes_num import Number

JSON_PLANES = "grammar/json.planes"

_interp = None


def _get():
    global _interp
    if _interp is None:
        _interp = Interpreter()
        _interp.run_file(JSON_PLANES)
    return _interp


def _t(v):
    return Traced(v, Deriv("literal", "<host value>", v, []))


def _call(name, *args):
    i = _get()
    return i.call(name, [_t(a) for a in args], i.env).value


# ---------------------------------------------------------------- conversions
#
# A tagged interp.planes value <-> a plain Python value, so every comparison
# below is against the reference's own output rather than a literal.

def _tagged(x):
    if x is None:
        return {"kind": "nothing", "value": None, "deriv": None}
    if isinstance(x, bool):
        return {"kind": "boolean", "value": x, "deriv": None}
    if isinstance(x, (int, float, Number)):
        return {"kind": "number", "value": Number.of(x), "approx": None, "deriv": None}
    if isinstance(x, str):
        return {"kind": "text", "value": x, "deriv": None}
    if isinstance(x, list):
        return {"kind": "list", "items": [_tagged(i) for i in x], "deriv": None}
    if isinstance(x, dict):
        return {"kind": "record",
                "fields": [{"key": k, "value": _tagged(v)} for k, v in x.items()],
                "deriv": None}
    raise AssertionError(f"no tagged form for {x!r}")


def _plain(v):
    k = v["kind"]
    if k in ("number", "text", "boolean"):
        return v["value"]
    if k == "nothing":
        return None
    if k == "list":
        return [_plain(x) for x in v["items"]]
    if k == "record":
        return {f["key"]: _plain(f["value"]) for f in v["fields"]}
    raise AssertionError(f"unknown value kind {k!r}")


def _norm(x):
    """Comparable form: an exact number by its canonical text, so 4 and 4.0
    never compare equal by accident."""
    if isinstance(x, Number):
        return ("number", x.text())
    if isinstance(x, bool):
        return x
    if isinstance(x, list):
        return [_norm(i) for i in x]
    if isinstance(x, dict):
        return {k: _norm(v) for k, v in x.items()}
    return x


def _parse(src):
    return _call("json-parse", src)


def _write(value):
    return _call("json-text-of", _tagged(value))


def _agrees(src):
    """The Planes reader gives what parse_json + from_foreign gives."""
    got = _parse(src)
    assert got["ok"], f"{src!r} refused: {got['detail']}"
    mine = _norm(_plain(got["value"]))
    theirs = _norm(from_foreign(json.loads(src)))
    assert mine == theirs, f"{src!r}: planes={mine!r} reference={theirs!r}"


# ---------------------------------------------------------------- reading

def test_scalars_agree_with_the_reference():
    for src in ('null', 'true', 'false', '0', '42', '-42', '3.5', '-3.5',
                '"hello"', '""', '"a b"'):
        _agrees(src)


def test_empty_containers_agree():
    for src in ('[]', '{}', '[[]]', '{"a": {}}', '{"a": []}', '[{}, []]'):
        _agrees(src)


def test_nesting_agrees():
    for src in ('[[[[1]]]]',
                '{"a": {"b": {"c": [1, 2, {"d": null}]}}}',
                '[{"x": [{"y": [[]]}]}]',
                '{"n": [true, false, null], "e": {}, "l": []}'):
        _agrees(src)


def test_the_four_escapes_planes_can_spell_agree():
    for src in (r'"a\"b"', r'"a\\b"', r'"a\/b"', r'"line\nbreak"',
                r'"tab\there"', r'"\\\\"', r'"\"\""'):
        _agrees(src)


def test_whitespace_between_tokens_is_insignificant():
    for src in ('  [ 1 , 2 ]  ', '{\n  "a" : 1\n}', '\t[\r\n1]\n'):
        _agrees(src)


def test_exact_numbers_agree_wherever_a_float_round_trips():
    # The reference reads a JSON number as a float and converts via the
    # shortest decimal that round-trips it. Up to 17 significant digits that
    # decimal is the input, so the two readers agree exactly.
    for src in ('0.1', '0.2', '0.30000000000000004', '1e3', '1E3', '1e+3',
                '1e-3', '2.5e2', '-2.5e-2', '1e17', '1e-17', '0.0',
                '9007199254740993', '12345678901234567890', '-0'):
        _agrees(src)


def test_past_seventeen_digits_the_planes_reader_keeps_what_the_float_drops():
    # A named divergence, one-directional: Planes is the exact side. Asserted
    # so it cannot change silently.
    cases = {
        "1.0000000000000000001": ("1.0000000000000000001", "1"),
        "3.141592653589793238462643383279":
            ("3.141592653589793238462643383279", "3.141592653589793"),
    }
    for src, (exact, lossy) in cases.items():
        got = _parse(src)
        assert got["ok"], got["detail"]
        assert _plain(got["value"]).text() == exact
        assert from_foreign(json.loads(src)).text() == lossy


def test_a_repeated_field_keeps_both_pairs_in_order():
    # json.loads keeps the last; a Planes record value is a list of pairs and
    # keeps both, in order. The difference is real, so it is asserted rather
    # than compared to the reference.
    got = _parse('{"a": 1, "a": 2}')
    assert got["ok"]
    keys = [f["key"] for f in got["value"]["fields"]]
    values = [_plain(f["value"]).text() for f in got["value"]["fields"]]
    assert keys == ["a", "a"] and values == ["1", "2"]
    assert json.loads('{"a": 1, "a": 2}') == {"a": 2}


# ---------------------------------------------------------------- refusing

# Text the reference accepts and Planes cannot represent: JSON's other four
# escapes. The message names why, and the caller falls back to the raw text
# exactly as the reference falls back when json.loads raises.
UNSPELLABLE = ('"esc\\r"', '"esc\\b"', '"esc\\f"', '"esc\\u0041"',
               '"esc\\u00e9"', '"esc\\ud83d\\ude00"')


def test_the_escapes_planes_cannot_spell_are_refused_by_name():
    for src in UNSPELLABLE:
        json.loads(src)                      # the reference accepts it
        got = _parse(src)
        assert not got["ok"], f"{src!r} should be refused"
        assert "has no Planes spelling" in got["detail"], got["detail"]
        assert "four escapes" in got["detail"], got["detail"]
        # names the fix, per the language-level commitment
        assert "send the character itself" in got["detail"], got["detail"]


MALFORMED = ('', '[1,]', '{,}', '{"a" 1}', '[1 2]', 'tru', '01x',
             '"unterminated', '[1', '}', ']', '1 2', '.5', '1.', '1e',
             '{"a": }', '[,1]', '{"a": 1,}', 'nul', '--1', '1..2')


def test_malformed_json_is_refused_exactly_where_the_reference_refuses():
    for src in MALFORMED:
        try:
            json.loads(src)
            reference_ok = True
        except Exception:                    # noqa: BLE001
            reference_ok = False
        assert not reference_ok, f"{src!r} is not malformed after all"
        got = _parse(src)
        assert not got["ok"], f"{src!r} accepted: {_plain(got['value'])!r}"
        assert got["detail"], f"{src!r} refused with no reason"


# ---------------------------------------------------------------- writing

WRITE_CASES: tuple[object, ...] = (
    {"query": "2 + 2", "result": 4},
    {},
    [],
    [1, 2, 3],
    {"a": {"b": {"c": [1, 2, {"d": None}]}}},
    {"t": True, "f": False, "n": None},
    "plain text",
    42,
    -7,
    Number.of(1) / Number.of(3),
    [Number.of(1) / Number.of(2), 4],
    {"quote": 'he said "hi"', "back": "a\\b", "nl": "one\ntwo", "tab": "a\tb"},
    {"deep": [[[["x"]]]]},
    [[], {}, [[]], [{}]],
)


def test_the_writer_is_byte_identical_to_the_reference():
    for case in WRITE_CASES:
        mine, theirs = _write(case), to_json(case)
        assert mine == theirs, f"{case!r}:\n planes={mine!r}\n reference={theirs!r}"


def test_a_non_whole_number_goes_out_as_exact_text_not_a_float():
    # to_json's unwrap: whole stays whole, anything else becomes text, so an
    # exact value is never silently rounded on the way to a file.
    third = Number.of(1) / Number.of(3)
    out = _write({"n": third})
    assert out == to_json({"n": third})
    assert '"~0.333333333333"' in out, out
    assert "0.3333333333333333" not in out          # no float ever appears


def test_the_writer_and_the_reader_round_trip_through_each_other():
    for case in WRITE_CASES:
        text = _write(case)
        # the reference reads the Planes bytes back to the same value
        assert json.loads(text) == json.loads(to_json(case))
        # and Planes reads the reference's bytes back to the same value
        got = _parse(to_json(case))
        assert got["ok"], got["detail"]
        assert (_norm(_plain(got["value"]))
                == _norm(from_foreign(json.loads(to_json(case)))))


# ---------------------------------------------------------------- Unicode

NON_ASCII = ("café", "中文", "\U0001f600", "a\U0001f600b", "naïve — ok")


def test_non_ascii_is_written_as_itself_and_the_reference_reads_it_back():
    for s in NON_ASCII:
        mine = _write({"s": s})
        # NOT byte-identical: json.dumps escapes non-ASCII, Planes cannot
        assert mine != to_json({"s": s})
        # but it is valid JSON carrying the same value
        assert json.loads(mine) == {"s": s}


def test_the_reference_escaped_form_of_non_ascii_cannot_be_read_back():
    # The other direction of the same absence, asserted so the boundary is
    # exact: an astral-plane character round-trips Planes -> reference, and not
    # reference -> Planes, because the reference writes a surrogate pair as
    # \uXXXX and Planes has no code-point escape.
    for s in NON_ASCII:
        got = _parse(to_json({"s": s}))
        assert not got["ok"]
        assert "has no Planes spelling" in got["detail"]


# ---------------------------------------------------------------- depth

def test_the_reader_costs_no_interpreter_depth():
    """The reader is a fold with an explicit stack, not recursive descent, so
    nesting costs a stack entry rather than a frame. 400 levels is far past the
    interpreted-recursion ceiling (32) and past the writer's own limit."""
    for n in (1, 40, 100, 400):
        src = "[" * n + "1" + "]" * n
        got = _parse(src)
        assert got["ok"], f"nesting {n}: {got['detail']}"
        depth, v = 0, got["value"]
        while v["kind"] == "list":
            depth += 1
            v = v["items"][0]
        assert depth == n


def test_the_writer_is_recursive_and_its_ceiling_is_measured_not_guessed():
    """The writer's output shape follows the value's, so it recurses once per
    level — the same shape interp.planes's own canonical-of-value already has.
    The ceiling is a measured number, reported rather than worked around."""
    def wrote(n):
        v = 1
        for _ in range(n):
            v = [v]
        try:
            return _write(v) == to_json(v)
        except (PlanesError, RecursionError):
            return False

    assert wrote(1) and wrote(20) and wrote(60)
    lo, hi = 1, 200
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if wrote(mid):
            lo = mid
        else:
            hi = mid - 1
    print(f"    [writer nesting ceiling, called from the host: {lo}]")
    assert lo >= 60, f"the writer regressed to {lo} levels"


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
