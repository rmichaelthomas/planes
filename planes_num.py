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

Exact, and approximate
----------------------
A number also carries whether it is exact. It is APPROXIMATE when the true
result of the operation that produced it cannot be represented as a rational,
and EXACT otherwise. Nothing in the language produced an approximate value
until `sine` arrived; the property is carried by every number regardless, so
that when one does appear it cannot cross a boundary unmarked.

`approx` is that property AND its provenance in one field: `None` when the
value is exact, and otherwise an immutable record naming where approximation
entered and with what parameters. One field rather than a flag beside a
record, because a flag that says "approximate" with no provenance beside it is
a state the type should not be able to hold.

Two rules that look like exceptions and are not:

  * `round total to 2 places` on one third gives EXACTLY 0.33. Not one third —
    but the exact result of the operation that was asked for. A deliberate,
    named reduction in precision is not approximation, and if it were, every
    invoice in the corpus would come out flagged and the exact-money claim
    would be destroyed by the feature meant to make precision visible.
  * `==` between two approximate values compares the underlying rationals and
    answers plainly. No epsilon, no tolerance. A tolerance nobody chose is
    exactly the silent behaviour this design refuses; `why` shows both sides'
    entry points instead, which is what makes the plain answer defensible.
"""
from fractions import Fraction

# Roughly 4,000 bits. Chosen empirically: summing 1/1 .. 1/2000 stays under
# it, and arithmetic at that size is still fast. A program that exceeds it
# is doing something where the rounding point is a real decision, not an
# implementation detail to be settled silently.
MAX_DENOMINATOR = 2 ** 4000

# Kept as the old name for compatibility with anything that imported it.
ROUND_AFTER = MAX_DENOMINATOR


class Approximation:
    """Where a value stopped being exact, and with what parameters.

    Immutable and shared: an approximate value's arithmetic results carry the
    same record by reference, so a chain of a thousand operations off one
    `sine` allocates one of these, not a thousand.
    """

    __slots__ = ("op", "detail")

    def __init__(self, op, detail=""):
        self.op = op
        self.detail = detail

    def __eq__(self, o):
        return isinstance(o, Approximation) and (self.op, self.detail) == (o.op, o.detail)

    def __hash__(self):
        return hash((self.op, self.detail))

    def __repr__(self):
        return f"Approximation({self.op!r}, {self.detail!r})"


class Number:
    """A number, exact unless it says otherwise.

    Wraps Fraction, renders like a person would write it, and carries `approx`
    — `None` when exact, an Approximation when not.
    """

    __slots__ = ("q", "approx")

    def __init__(self, q, approx=None):
        self.q = q if isinstance(q, Fraction) else Fraction(q)
        self.approx = approx

    @property
    def is_exact(self):
        return self.approx is None

    # ---- construction

    @classmethod
    def parse(cls, text):
        """From source. `0.1` is exactly one tenth, not the nearest float."""
        return cls(Fraction(text))

    def with_approx(self, approx):
        """The same rational, carrying this approximation. The one place a
        value becomes approximate; `sine` is currently its only caller."""
        return Number(self.q, approx)

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

    # exact + exact is exact; anything touching an approximate value is
    # approximate, and inherits the FIRST entry point on the left-to-right
    # reading of the expression. `why` on a comparison still shows both sides,
    # because the derivation tree keeps both input branches and each branch's
    # own number carries its own entry.
    def __add__(self, o):
        o = Number.of(o)
        return self._check(Number(self.q + o.q, self.approx or o.approx), "+")

    def __sub__(self, o):
        o = Number.of(o)
        return self._check(Number(self.q - o.q, self.approx or o.approx), "-")

    def __mul__(self, o):
        o = Number.of(o)
        return self._check(Number(self.q * o.q, self.approx or o.approx), "*")

    def __truediv__(self, o):
        d = Number.of(o)
        if d.q == 0:
            raise ZeroDivisionError("divided by zero")
        return self._check(Number(self.q / d.q, self.approx or d.approx), "/")

    def __neg__(self):
        return Number(-self.q, self.approx)

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
        """Round to a number of decimal places. Named, visible, deliberate.

        The result carries whatever the input carried. Rounding an exact value
        gives an exact one — `round (1/3) to 2 places` is exactly 0.33, the
        exact result of the operation asked for — and rounding an approximate
        one does not launder it back to exact.
        """
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
        return Number(Fraction(rounded) / scale, self.approx)

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
