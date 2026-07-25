"""Property-based tests over the value-model invariants (planes v9.0
Phase B). Scope is value semantics only -- not effects (test_shapes.py's
oracle covers those) and not the trace.

No dependency on `hypothesis`: the venv has no pytest and no hypothesis,
consistent with this repo's minimal-dependency posture (pyproject.toml's
only dev deps are ruff/mypy/coverage), so each property below is a
hand-rolled generator over a `random.Random` with a fixed seed -- runs are
deterministic and reproducible, matching TestHost's deterministic clock.

Immutability (v9.0 Phase B lists `r with f: v` / `xs plus item`): neither
`with` nor `plus` exists anywhere in this language yet (grep confirms --
`with` is reserved only for `use x with old as new` renames). There is no
mutation syntax of any kind, so the properties below test what is actually
true today: no operation available in the language ever changes what a
previously-bound name evaluates to. That is the substance of section 72's
"immutability" claim in a language with zero mutation operators.
"""
import random
import sys
from decimal import Decimal
from fractions import Fraction

from interp import Interpreter, PlanesError, equal
from planes_num import MAX_DENOMINATOR, Inexact, Number

SEED = 20260724
CASES = 200


# ================================================================ generators

def rand_string(rng, max_len=8):
    """Random text, including some combining-mark and astral code points.

    Excludes '"' -- Planes strings have no escape syntax, so a generated
    string must embed directly into source for the text-law tests below.
    """
    pool = (
        [chr(c) for c in range(0x20, 0x7F) if c != ord('"')]   # ascii, no quote
        + ["é", "é", "日", "🎈", "́", "ñ", " "]                  # multi-byte / combining
    )
    return "".join(rng.choice(pool) for _ in range(rng.randint(0, max_len)))


def rand_number(rng):
    n = rng.randint(-10_000, 10_000)
    d = rng.randint(1, 1000)
    return Number(Fraction(n, d))


def rand_bool(rng):
    return rng.choice([True, False])


def rand_list(rng, depth=0):
    n = rng.randint(0, 4)
    return [rand_scalar(rng, depth + 1) for _ in range(n)]


def rand_record(rng, depth=0):
    fields = rng.sample(["a", "b", "c", "d"], rng.randint(0, 3))
    return {f: rand_scalar(rng, depth + 1) for f in fields}


def rand_scalar(rng, depth=0):
    if depth >= 2:
        return rng.choice([rand_number(rng), rand_string(rng), rand_bool(rng)])
    kind = rng.choice(["number", "string", "bool", "list", "record"])
    return {
        "number": lambda: rand_number(rng),
        "string": lambda: rand_string(rng),
        "bool": lambda: rand_bool(rng),
        "list": lambda: rand_list(rng, depth),
        "record": lambda: rand_record(rng, depth),
    }[kind]()


TYPE_GENS = {
    "number": rand_number,
    "string": rand_string,
    "bool": rand_bool,
    "list": rand_list,
    "record": rand_record,
}


# ================================================================ equality (section 59)

def test_equality_is_reflexive():
    """equal(x, x) for any single-type x -- nothing is the sole, explicit
    exception (nothing cannot be compared with ==, even to itself)."""
    rng = random.Random(SEED)
    for _ in range(CASES):
        kind = rng.choice(list(TYPE_GENS))
        x = TYPE_GENS[kind](rng)
        assert equal(x, x) is True, (kind, x)


def test_equality_is_symmetric_when_defined():
    """equal(a, b) == equal(b, a) whenever neither side raises."""
    rng = random.Random(SEED + 1)
    checked = 0
    for _ in range(CASES):
        kind = rng.choice(list(TYPE_GENS))
        a, b = TYPE_GENS[kind](rng), TYPE_GENS[kind](rng)
        try:
            ab = equal(a, b)
        except PlanesError:
            continue    # a nested mismatch inside a list/record -- not
                        # "defined" for this property, skip it
        ba = equal(b, a)
        assert ab == ba, (a, b, ab, ba)
        checked += 1
    assert checked > CASES // 2, "too few same-type pairs actually compared"


def test_equality_raises_never_returns_false_across_incomparable_types():
    rng = random.Random(SEED + 2)
    kinds = list(TYPE_GENS)
    for _ in range(CASES):
        k1, k2 = rng.sample(kinds, 2)
        a, b = TYPE_GENS[k1](rng), TYPE_GENS[k2](rng)
        try:
            result = equal(a, b)
            assert False, f"expected raise for {k1}/{k2}, got {result!r}"
        except PlanesError as e:
            assert e.tag == "cannot-compare"


# ================================================================ immutability (section 72)

def rand_literal_ascii(rng, max_len=6):
    """Short ascii text, source-embeddable directly (no quote, no digits
    at the start position issues -- only used inside string literals)."""
    pool = [chr(c) for c in range(0x61, 0x7B)]     # a-z
    return "".join(rng.choice(pool) for _ in range(rng.randint(0, max_len)))


def rand_literal_scalar(rng):
    """A value with a direct Planes source-literal form: a non-negative
    whole number, a quote-free string, or a bool. Not `rand_scalar` --
    that one produces `Number`/`Fraction` values with no clean literal
    spelling (fractions, negatives), which is fine for the equality tests
    (compared as Python objects) but not for embedding into source text."""
    return rng.choice([
        lambda: rng.randint(0, 999),
        lambda: rand_literal_ascii(rng),
        lambda: rng.choice([True, False]),
    ])()


def rand_literal_list(rng, depth=0):
    n = rng.randint(0, 3)
    return [rand_literal_value(rng, depth + 1) for _ in range(n)]


def rand_literal_record(rng, depth=0):
    fields = rng.sample(["a", "b", "c"], rng.randint(0, 3))
    return {f: rand_literal_value(rng, depth + 1) for f in fields}


def rand_literal_value(rng, depth=0):
    if depth >= 2:
        return rand_literal_scalar(rng)
    return rng.choice([rand_literal_scalar, rand_literal_list, rand_literal_record])(rng)


def test_rebinding_a_name_does_not_alias_another():
    """No mutation operator exists (grep-confirmed: no with/plus for
    functional update). Rebinding `x` must never change what `y` -- bound
    earlier to 'the same' record or list -- evaluates to."""
    rng = random.Random(SEED + 3)
    for _ in range(50):
        first = rand_literal_record(rng) if rng.random() < 0.5 else rand_literal_list(rng)
        second = rand_literal_record(rng) if rng.random() < 0.5 else rand_literal_list(rng)
        i = Interpreter(fs={})
        i.run(_planes_assign("x", first) + "\n" +
              "y = x\n" +
              _planes_assign("x", second))
        assert i.env.get("x").value == _to_planes_value(second)
        assert i.env.get("y").value == _to_planes_value(first)


def _planes_source_literal(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, list):
        return "[" + ", ".join(_planes_source_literal(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k}: {_planes_source_literal(x)}"
                                for k, x in v.items()) + " }"
    raise TypeError(type(v))


def _planes_assign(name, v):
    return f"{name} = {_planes_source_literal(v)}"


def _to_planes_value(v):
    """The Python value a Planes program evaluating this literal produces
    -- numbers become Number, everything else is structural."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return Number.of(v)
    if isinstance(v, list):
        return [_to_planes_value(x) for x in v]
    if isinstance(v, dict):
        return {k: _to_planes_value(x) for k, x in v.items()}
    return v


# ================================================================ exact arithmetic (v3.0 s47)

def test_the_classic_float_bug_case():
    assert Number.parse("0.1") + Number.parse("0.2") == Number.parse("0.3")


def test_decimal_addition_matches_an_independent_exact_oracle():
    """Number's sum agrees with Python's Decimal -- a second, independent
    exact-arithmetic implementation -- for random short decimals."""
    rng = random.Random(SEED + 4)
    for _ in range(CASES):
        a = rng.randint(-100000, 100000)
        b = rng.randint(-100000, 100000)
        pa, pb = rng.randint(0, 4), rng.randint(0, 4)
        sa = f"{Decimal(a).scaleb(-pa):f}"
        sb = f"{Decimal(b).scaleb(-pb):f}"
        expected = Decimal(sa) + Decimal(sb)
        got = Number.parse(sa) + Number.parse(sb)
        assert got == Number.parse(f"{expected:f}"), (sa, sb, got, expected)


def test_needs_rounding_raises_rather_than_rounds():
    huge = "1" + "0" * 1250
    try:
        Number(1) / Number.parse(huge)
        assert False, "should refuse"
    except Inexact:
        pass


def test_bounded_arithmetic_never_raises_inexact():
    rng = random.Random(SEED + 5)
    for _ in range(CASES):
        a, b = rand_number(rng), rand_number(rng)
        Number.of(a) + Number.of(b)     # must not raise


def test_arithmetic_result_denominator_never_exceeds_the_bound():
    rng = random.Random(SEED + 6)
    for _ in range(CASES):
        a, b = rand_number(rng), rand_number(rng)
        r = Number.of(a) + Number.of(b)
        assert r.q.denominator <= MAX_DENOMINATOR


# ================================================================ text (section 105, 105.1)

def test_count_of_matches_code_point_length():
    """The string pool never contains '"' (Planes strings have no escape
    syntax), so every generated string embeds directly into source."""
    rng = random.Random(SEED + 7)
    for _ in range(CASES):
        s = rand_string(rng, max_len=12)
        assert '"' not in s
        i = Interpreter()
        i.run(f'x = count of "{s}"\n')
        assert i.env.get("x").value == Number.of(len(s))


def test_first_n_of_string_is_a_code_point_prefix():
    rng = random.Random(SEED + 8)
    for _ in range(CASES):
        s = rand_string(rng, max_len=10)
        n = rng.randint(0, 12)
        i = Interpreter()
        i.run(f'x = first {n} of "{s}"\n')
        v = i.env.get("x").value
        assert isinstance(v, str)
        assert v == s[:n]
        assert len(v) <= n


def test_identical_code_point_sequences_are_equal():
    rng = random.Random(SEED + 9)
    for _ in range(CASES):
        s = rand_string(rng, max_len=10)
        assert equal(s, s) is True


# ================================================================ + homogeneity (105.1)

def test_plus_raises_cannot_combine_across_types():
    rng = random.Random(SEED + 10)
    kinds = ["number", "string", "list"]     # record + anything is not
                                              # even reachable via apply_op
                                              # today (no + on records)
    for _ in range(CASES):
        k1, k2 = rng.sample(kinds, 2)
        a = TYPE_GENS[k1](rng)
        b = TYPE_GENS[k2](rng)
        try:
            from interp import apply_op
            result = apply_op("+", a, b)
            assert False, f"expected raise for {k1}/{k2}, got {result!r}"
        except PlanesError as e:
            assert e.tag == "cannot-combine"


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
