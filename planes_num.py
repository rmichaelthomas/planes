"""Planes numbers.

A number is exact. `0.1 + 0.2` is `0.3`, not `0.30000000000000004`, and
`1 / 3` is one third, not `0.3333333333333333`.

Why this and not floats or Decimal
----------------------------------
Why exists to answer "what combined to make this number". A derivation that
contains a silent rounding step does not answer that — it answers a question
about the answer. Floats round on almost every operation; Decimal rounds on
division at whatever precision happens to be set. Both put a lie inside the
derivation graph, and the lie is invisible at exactly the moment someone is
looking at a number and asking why it is wrong.

Exact rationals never round. `1 / 3` stays one third for as long as it is
one third, so `why` reports arithmetic that actually happened.

The cost is real and is paid deliberately
-----------------------------------------
Denominators grow. Adding many fractions with unrelated denominators builds
a large one — summing 1/1 through 1/n produces a denominator near the least
common multiple of everything below n. Arithmetic slows as it grows.

`MAX_DENOMINATOR` bounds that cost. Past it, an operation is refused rather
than silently rounded, because a refusal is visible and a rounding is not.
The bound is set high enough that ordinary work never reaches it — summing
several thousand distinct fractions stays inside — and the programs that do
reach it are the ones where the user genuinely has to decide where precision
should be given up.

Rounding is available, but only where the program asks for it: `round total
to 2 places` is an operation with a name, and it shows up in the derivation
like any other.
"""
from fractions import Fraction

# Roughly 4,000 bits. Chosen empirically: summing 1/1 .. 1/2000 stays under
# it, and arithmetic at that size is still fast. A program that exceeds it
# is doing something where the rounding point is a real decision, not an
# implementation detail to be settled silently.
MAX_DENOMINATOR = 2 ** 4000

# Kept as the old name for compatibility with anything that imported it.
ROUND_AFTER = MAX_DENOMINATOR


class Number:
    """An exact number. Wraps Fraction, renders like a person would write it."""

    __slots__ = ("q",)

    def __init__(self, q):
        self.q = q if isinstance(q, Fraction) else Fraction(q)

    # ---- construction

    @classmethod
    def parse(cls, text):
        """From source. `0.1` is exactly one tenth, not the nearest float."""
        return cls(Fraction(text))

    @classmethod
    def of(cls, v):
        if isinstance(v, Number):
            return v
        if isinstance(v, bool):
            raise TypeError("a yes/no value is not a number")
        if isinstance(v, float):
            # Only reachable from foreign data. Take the shortest decimal
            # that round-trips, not the float's full binary expansion, so a
            # JSON 0.1 becomes one tenth rather than 0.1000000000000000055.
            return cls(Fraction(repr(v)))
        return cls(Fraction(v))

    # ---- shape

    def is_whole(self):
        return self.q.denominator == 1

    def as_int(self):
        if not self.is_whole():
            raise ValueError(f"{self} is not a whole number")
        return self.q.numerator

    def __float__(self):
        return float(self.q)

    def __int__(self):
        return int(self.q)

    # ---- arithmetic

    def _check(self, r, op):
        if r.q.denominator > MAX_DENOMINATOR:
            raise Inexact(op, self, r)
        return r

    def __add__(self, o):
        return self._check(Number(self.q + Number.of(o).q), "+")

    def __sub__(self, o):
        return self._check(Number(self.q - Number.of(o).q), "-")

    def __mul__(self, o):
        return self._check(Number(self.q * Number.of(o).q), "*")

    def __truediv__(self, o):
        d = Number.of(o)
        if d.q == 0:
            raise ZeroDivisionError("divided by zero")
        return self._check(Number(self.q / d.q), "/")

    def __neg__(self):
        return Number(-self.q)

    # ---- comparison

    def __eq__(self, o):
        if isinstance(o, Number):
            return self.q == o.q
        if isinstance(o, (int, float, Fraction)):
            return self.q == Number.of(o).q
        return NotImplemented

    def __lt__(self, o):
        return self.q < Number.of(o).q

    def __le__(self, o):
        return self.q <= Number.of(o).q

    def __gt__(self, o):
        return self.q > Number.of(o).q

    def __ge__(self, o):
        return self.q >= Number.of(o).q

    def __hash__(self):
        return hash(self.q)

    def __bool__(self):
        return self.q != 0

    # ---- rounding, only when asked

    def round_to(self, places):
        """Round to a number of decimal places. Named, visible, deliberate."""
        p = int(places)
        if p < 0:
            raise ValueError("places cannot be negative")
        scale = Fraction(10) ** p
        scaled = self.q * scale
        # half away from zero — what people mean by "round"
        n, d = scaled.numerator, scaled.denominator
        if d == 1:
            rounded = n
        else:
            sign = -1 if n < 0 else 1
            rounded = sign * ((abs(n) * 2 + d) // (d * 2))
        return Number(Fraction(rounded) / scale)

    # ---- rendering

    def text(self, max_places=12):
        """How this number reads.

        A value with a finite decimal expansion prints exactly. One without
        — a third — prints to `max_places` with a leading `~`, so the
        approximation is visible in the output rather than assumed.
        """
        q = self.q
        if q.denominator == 1:
            return str(q.numerator)
        if _terminates(q.denominator):
            s = _exact_decimal(q)
            return s
        neg = q < 0
        q = -q if neg else q
        scale = 10 ** max_places
        scaled = (q * scale).__floor__()
        digits = str(scaled).rjust(max_places + 1, "0")
        whole, frac = digits[:-max_places], digits[-max_places:]
        frac = frac.rstrip("0") or "0"
        return f"~{'-' if neg else ''}{whole}.{frac}"

    def __str__(self):
        return self.text()

    def __repr__(self):
        return self.text()


class Inexact(Exception):
    """An operation whose exact result cannot be represented in bounds."""

    def __init__(self, op, left, right):
        self.op = op
        super().__init__(
            f"'{op}' would need more precision than a number can hold. "
            f"This happens when many fractions with unrelated denominators "
            f"are combined exactly")


def _terminates(denominator):
    """A fraction has a finite decimal form iff its denominator is 2^a * 5^b."""
    d = denominator
    for f in (2, 5):
        while d % f == 0:
            d //= f
    return d == 1


def _exact_decimal(q):
    """Exact decimal text for a terminating fraction."""
    neg = q < 0
    if neg:
        q = -q
    n, d = q.numerator, q.denominator
    places = 0
    dd = d
    while dd % 2 == 0:
        dd //= 2
        places += 1
    p5 = 0
    dd = d
    while dd % 5 == 0:
        dd //= 5
        p5 += 1
    places = max(places, p5)
    scaled = n * (10 ** places) // d
    s = str(scaled).rjust(places + 1, "0")
    whole, frac = s[:-places], s[-places:]
    frac = frac.rstrip("0")
    out = whole + ("." + frac if frac else "")
    return ("-" if neg else "") + out
