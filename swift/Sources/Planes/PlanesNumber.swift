// PlanesNumber.swift — Planes numbers, exact rationals over BigInt.
//
// The Swift counterpart of planes_num.py and js/planes_num.mjs, in js's order
// and with js's names. A number is exact: 0.1 + 0.2 is 0.3, not
// 0.30000000000000004, and 1 / 3 is one third, not 0.3333333333333333. why
// exists to answer "what combined to make this number", and a derivation with
// a silent rounding step does not answer that — so numbers never round. The
// cost is real and paid deliberately: denominators grow, and MAX_DENOMINATOR
// bounds that cost by refusing (visibly) rather than rounding (invisibly).
//
// The representation is a Fraction of two BigInts (BigInt.swift), always in
// lowest terms with a positive denominator, mirroring Python's
// fractions.Fraction. No `Double` is on any path that computes a Planes value.
// A Double appears in exactly two places, both boundaries the reference itself
// crosses with a float: `PlanesNumber.of(Double)` (foreign data coming in,
// Python's `Fraction(repr(v))`) and `toNumber()` (a value going out to the
// host, Python's `float(q)`). Each is ported to Python's exact semantics, not
// to JavaScript's.
//
// WHERE THIS FOLLOWS PYTHON AND NOT js/. The reference is planes_num.py. Three
// things js/planes_num.mjs does differently are ported here as Python does
// them: `fractionFromString` accepts exactly the grammar of Python's
// `Fraction(str)` (Unicode decimal digits, `_` separators, Python whitespace)
// and nothing else; `numberFromText` strips Python's whitespace set and its
// `\d` is Unicode's decimal digits, as Python's `str.strip` and `re` are; and
// `toNumber` is correctly rounded, as Python's int true division is.
//
// EXACT, AND APPROXIMATE. A number also carries whether it is exact: it is
// APPROXIMATE when the true result of the operation that produced it cannot be
// represented as a rational, and EXACT otherwise. `approx` is that property
// AND its provenance in one field — nil when exact, an Approximation when not.
//
// Two rules that look like exceptions and are not: `roundTo` on one third
// gives EXACTLY 0.33 (a deliberate, named reduction in precision is not
// approximation), and `eq` between two approximate values compares the
// underlying rationals with no allowance of any kind (an allowance nobody chose
// is the silent behaviour this design refuses).

/// Roughly 4,000 bits — planes_num.py's MAX_DENOMINATOR = 2 ** 4000, unchanged.
public let MAX_DENOMINATOR = BigInt.one << 4000

// ------------------------------------------------------------------ errors

/// Everything the numeric tower refuses, each case named for the Python
/// exception the reference raises, carrying the reference's message.
public enum NumberError: Error, Sendable, Equatable {
    /// planes_num.Inexact.
    case inexact(Inexact)
    /// planes_num.NotANumber.
    case notANumber(NotANumber)
    /// ZeroDivisionError.
    case zeroDivision(String)
    /// ValueError.
    case value(String)
    /// TypeError.
    case type(String)
    /// OverflowError.
    case overflow(String)

    public var message: String {
        switch self {
        case .inexact(let e): return e.message
        case .notANumber(let e): return e.message
        case .zeroDivision(let m), .value(let m), .type(let m), .overflow(let m): return m
        }
    }
}

// ------------------------------------------------------------------ Fraction

/// An exact rational of two BigInts, reduced, denominator positive. The subset
/// of fractions.Fraction that Planes numbers use.
public struct Fraction: Sendable, Hashable {
    public let n: BigInt
    public let d: BigInt

    /// Python's `Fraction(num, den)`: reduced, sign on the numerator.
    public init(_ num: BigInt, _ den: BigInt = .one) throws(NumberError) {
        if den.isZero { throw .zeroDivision("Fraction(\(num), 0)") }
        self.init(unchecked: num, den)
    }

    /// A whole number.
    public init(_ num: BigInt) {
        n = num
        d = .one
    }

    /// Reduce `num/den`; `den` is known to be non-zero.
    init(unchecked num: BigInt, _ den: BigInt) {
        var g = BigInt.gcd(num, den)
        if g.isZero { g = .one }
        if den.isNegative { g = -g }
        n = num / g
        d = den / g
    }

    /// Already in lowest terms with a positive denominator.
    init(coprime num: BigInt, _ den: BigInt) {
        n = num
        d = den
    }

    // The four operations in CPython's forms (fractions.py `_add`, `_sub`,
    // `_mul`, `_div`): reduce by the gcds of the operands' parts before
    // combining, rather than by one gcd of the full cross-product afterwards.
    // A reduced fraction is unique, so the result is the same either way; the
    // gcds are of far smaller numbers. Summing 1/1 .. 1/2000 took 22 s in a
    // debug build with the one-gcd form and takes 0.12 s with these.
    public func add(_ o: Fraction) -> Fraction { addOrSub(o, subtract: false) }
    public func sub(_ o: Fraction) -> Fraction { addOrSub(o, subtract: true) }

    private func addOrSub(_ o: Fraction, subtract: Bool) -> Fraction {
        func combine(_ x: BigInt, _ y: BigInt) -> BigInt { subtract ? x - y : x + y }
        let g = BigInt.gcd(d, o.d)
        if g == .one {
            return Fraction(coprime: combine(n * o.d, d * o.n), d * o.d)
        }
        let s = d / g
        let t = combine(n * (o.d / g), o.n * s)
        let g2 = BigInt.gcd(t, g)
        if g2 == .one {
            return Fraction(coprime: t, s * o.d)
        }
        return Fraction(coprime: t / g2, s * (o.d / g2))
    }

    public func mul(_ o: Fraction) -> Fraction {
        var (na, da, nb, db) = (n, d, o.n, o.d)
        let g1 = BigInt.gcd(na, db)
        if g1 > .one {
            na = na / g1
            db = db / g1
        }
        let g2 = BigInt.gcd(nb, da)
        if g2 > .one {
            nb = nb / g2
            da = da / g2
        }
        return Fraction(coprime: na * nb, db * da)
    }

    public func div(_ o: Fraction) throws(NumberError) -> Fraction {
        var (nb, db) = (o.n, o.d)
        if nb.isZero { throw .zeroDivision("Fraction(\(db), 0)") }
        var (na, da) = (n, d)
        let g1 = BigInt.gcd(na, nb)
        if g1 > .one {
            na = na / g1
            nb = nb / g1
        }
        let g2 = BigInt.gcd(db, da)
        if g2 > .one {
            da = da / g2
            db = db / g2
        }
        let (rn, rd) = (na * db, nb * da)
        return rd.isNegative ? Fraction(coprime: -rn, -rd) : Fraction(coprime: rn, rd)
    }

    public func neg() -> Fraction { Fraction(coprime: -n, d) }

    /// Sign of (self - o): cross-multiply with positive denominators.
    public func cmp(_ o: Fraction) -> Int {
        let l = n * o.d
        let r = o.n * d
        return l < r ? -1 : (l > r ? 1 : 0)
    }
    public func eq(_ o: Fraction) -> Bool { n == o.n && d == o.d }
    public func lt(_ o: Fraction) -> Bool { cmp(o) < 0 }
}

// ------------------------------------------------------------------ text to Fraction

/// The characters Python's `str.isspace()` accepts — the set `str.strip()`
/// removes and `re`'s `\s` matches. Wider than Swift's and JavaScript's.
let pythonWhitespace: Set<UInt32> = [
    0x9, 0xA, 0xB, 0xC, 0xD, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x85, 0xA0, 0x1680,
    0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008,
    0x2009, 0x200A, 0x2028, 0x2029, 0x202F, 0x205F, 0x3000,
]

/// Python's `str.strip()`.
func pythonStrip(_ s: String) -> String {
    let cps = Array(s.unicodeScalars)
    var lo = 0
    var hi = cps.count
    while lo < hi && pythonWhitespace.contains(cps[lo].value) { lo += 1 }
    while hi > lo && pythonWhitespace.contains(cps[hi - 1].value) { hi -= 1 }
    return String(String.UnicodeScalarView(cps[lo..<hi]))
}

/// The value of a character `re`'s `\d` and `int()` accept — a Unicode decimal
/// digit, of any script — or nil.
func pythonDecimalDigit(_ c: Unicode.Scalar) -> UInt8? {
    if c.value >= 48 && c.value <= 57 { return UInt8(c.value - 48) }
    guard c.value > 127, c.properties.numericType == .decimal,
          let v = c.properties.numericValue, let digit = UInt8(exactly: v), digit <= 9 else { return nil }
    return digit
}

/// Python's `repr` of a str: the quote it would choose, and its escapes.
func pythonRepr(_ s: String) -> String {
    let hasSingle = s.unicodeScalars.contains("'")
    let hasDouble = s.unicodeScalars.contains("\"")
    let quote: Unicode.Scalar = (hasSingle && !hasDouble) ? "\"" : "'"
    func hex(_ v: UInt32, _ width: Int) -> String {
        let h = String(v, radix: 16)
        return String(repeating: "0", count: max(0, width - h.count)) + h
    }
    var out = String(quote)
    for c in s.unicodeScalars {
        switch c {
        case quote, "\\": out += "\\" + String(c)
        case "\t": out += "\\t"
        case "\n": out += "\\n"
        case "\r": out += "\\r"
        default:
            if c.value < 0x20 || c.value == 0x7F {
                out += "\\x" + hex(c.value, 2)
            } else if c.value < 0x7F {
                out.unicodeScalars.append(c)
            } else {
                switch c.properties.generalCategory {
                case .control, .format, .surrogate, .privateUse, .unassigned,
                     .lineSeparator, .paragraphSeparator, .spaceSeparator:
                    if c.value <= 0xFF { out += "\\x" + hex(c.value, 2) }
                    else if c.value <= 0xFFFF { out += "\\u" + hex(c.value, 4) }
                    else { out += "\\U" + hex(c.value, 8) }
                default:
                    out.unicodeScalars.append(c)
                }
            }
        }
    }
    out.unicodeScalars.append(quote)
    return out
}

/// Parse text into an exact Fraction, accepting exactly what Python's
/// `Fraction(str)` accepts — its `_RATIONAL_FORMAT`:
///
///     \A\s* [-+]? (?=\d|\.\d) (\d*|\d+(_\d+)*)
///       ( (\s*/\s*\d+(_\d+)*)? | (\.(\d*|\d+(_\d+)*))? (E[-+]?\d+(_\d+)*)? )
///     \s*\z                                             (IGNORECASE)
///
/// Source NUMBER literals are only `\d+(\.\d+)?`, but `PlanesNumber.of` also
/// routes a foreign float's shortest round-trip text here, which may carry a
/// sign and an exponent, and `of` a string routes arbitrary text here.
public func fractionFromString(_ text: String) throws(NumberError) -> Fraction {
    let invalid = NumberError.value("Invalid literal for Fraction: \(pythonRepr(text))")
    let cps = Array(text.unicodeScalars)
    var i = 0
    func skipSpace() { while i < cps.count && pythonWhitespace.contains(cps[i].value) { i += 1 } }
    func digit(at k: Int) -> UInt8? { k < cps.count ? pythonDecimalDigit(cps[k]) : nil }
    // `\d+(_\d+)*`, greedy. No character that can follow a digit group in the
    // pattern is a digit or `_`, so the greedy reading is the only one the
    // regex's backtracking could accept.
    func digitGroups() -> [UInt8] {
        var out: [UInt8] = []
        while let v = digit(at: i) { out.append(v); i += 1 }
        if out.isEmpty { return out }
        while i < cps.count, cps[i] == "_", digit(at: i + 1) != nil {
            i += 1
            while let v = digit(at: i) { out.append(v); i += 1 }
        }
        return out
    }

    skipSpace()
    var negative = false
    if i < cps.count, cps[i] == "-" || cps[i] == "+" {
        negative = cps[i] == "-"
        i += 1
    }
    guard digit(at: i) != nil || (i < cps.count && cps[i] == "." && digit(at: i + 1) != nil) else { throw invalid }
    let numDigits = digitGroups()
    var numerator = BigInt(negative: false, digits: numDigits)
    var denominator = BigInt.one

    // First alternative: a denominator.
    let afterNum = i
    skipSpace()
    if i < cps.count, cps[i] == "/" {
        i += 1
        skipSpace()
        let denDigits = digitGroups()
        if denDigits.isEmpty { throw invalid }
        skipSpace()
        if i != cps.count { throw invalid }
        denominator = BigInt(negative: false, digits: denDigits)
    } else {
        // Second alternative: a fractional part and an exponent.
        i = afterNum
        if i < cps.count, cps[i] == "." {
            i += 1
            let decimal = digitGroups()
            if !decimal.isEmpty {
                let scale = BigInt(10).power(decimal.count)
                numerator = numerator * scale + BigInt(negative: false, digits: decimal)
                denominator = denominator * scale
            }
        }
        if i < cps.count, cps[i] == "e" || cps[i] == "E" {
            var k = i + 1
            var expNegative = false
            if k < cps.count, cps[k] == "-" || cps[k] == "+" {
                expNegative = cps[k] == "-"
                k += 1
            }
            if digit(at: k) != nil {
                i = k
                let expDigits = digitGroups()
                guard let exp = BigInt(negative: false, digits: expDigits).asInt else { throw invalid }
                if expNegative {
                    denominator = denominator * BigInt(10).power(exp)
                } else {
                    numerator = numerator * BigInt(10).power(exp)
                }
            }
        }
        skipSpace()
        if i != cps.count { throw invalid }
    }
    if negative { numerator = -numerator }
    return try Fraction(numerator, denominator)
}

// ------------------------------------------------------------------ Inexact

/// An operation whose exact result cannot be represented in bounds. Mirrors
/// planes_num.py's Inexact — a refusal, not a silent rounding.
public struct Inexact: Error, Sendable, Equatable {
    public let op: String
    public init(_ op: String) { self.op = op }
    public var message: String {
        "'\(op)' would need more precision than a number can hold. This happens "
            + "when many fractions with unrelated denominators are combined exactly"
    }
}

private let two = BigInt(2)
private let five = BigInt(5)
private let ten = BigInt(10)

/// A fraction has a finite decimal form iff its denominator is 2^a * 5^b.
func terminates(_ denominator: BigInt) -> Bool {
    var d = denominator
    for f in [two, five] {
        while true {
            let (q, r) = d.quotientAndRemainder(dividingBy: f)
            if !r.isZero { break }
            d = q
        }
    }
    return d == .one
}

/// `s` left-padded with zeros to `width` — Python's `rjust(width, "0")`.
private func zeroPad(_ s: String, _ width: Int) -> String {
    let short = width - s.utf8.count
    return short > 0 ? String(repeating: "0", count: short) + s : s
}

/// `s` without trailing zeros — Python's `rstrip("0")`.
private func stripTrailingZeros(_ s: Substring) -> Substring {
    var t = s
    while t.last == "0" { t = t.dropLast() }
    return t
}

/// Exact decimal text for a terminating fraction.
func exactDecimal(_ q: Fraction) -> String {
    let neg = q.n.isNegative
    let n = q.n.magnitude
    let d = q.d
    func multiplicity(_ f: BigInt) -> Int {
        var count = 0
        var dd = d
        while true {
            let (qq, r) = dd.quotientAndRemainder(dividingBy: f)
            if !r.isZero { return count }
            dd = qq
            count += 1
        }
    }
    let places = max(multiplicity(two), multiplicity(five))
    let scaled = (n * ten.power(places)) / d
    let s = zeroPad(scaled.description, places + 1)
    let whole = s.prefix(s.utf8.count - places)
    let frac = stripTrailingZeros(s.suffix(places))
    let out = String(whole) + (frac.isEmpty ? "" : "." + frac)
    return (neg ? "-" : "") + out
}

// ------------------------------------------------------------------ Approximation

/// Where a value stopped being exact, and with what parameters. Immutable and
/// shared: an approximate value's arithmetic results carry the same record by
/// reference (`===`), so a chain of a thousand operations off one `sine`
/// allocates one of these, not a thousand.
public final class Approximation: Sendable {
    public let op: String
    public let detail: String
    public init(_ op: String, _ detail: String = "") {
        self.op = op
        self.detail = detail
    }
    public func eq(_ o: Approximation?) -> Bool {
        guard let o else { return false }
        return sameText(op, o.op) && sameText(detail, o.detail)
    }
}

// ------------------------------------------------------------------ PlanesNumber

/// A number, exact unless it says otherwise. Wraps a Fraction, renders like a
/// person would write it, and carries `approx` — nil when exact, an
/// Approximation when not. planes_num.Number, named as js/ names it.
public struct PlanesNumber: Sendable {
    public let q: Fraction
    public let approx: Approximation?

    public init(_ q: Fraction, _ approx: Approximation? = nil) {
        self.q = q
        self.approx = approx
    }

    public init(_ n: BigInt) { self.init(Fraction(n)) }

    public var isExact: Bool { approx == nil }

    /// The same rational, carrying this approximation. The one place a value
    /// becomes approximate; `sine` is currently its only caller.
    public func withApprox(_ approx: Approximation?) -> PlanesNumber {
        PlanesNumber(q, approx)
    }

    // ---- construction

    /// From source. `0.1` is exactly one tenth, not the nearest float.
    public static func parse(_ text: String) throws(NumberError) -> PlanesNumber {
        PlanesNumber(try fractionFromString(text))
    }

    public static func of(_ v: PlanesNumber) -> PlanesNumber { v }
    public static func of(_ v: Fraction) -> PlanesNumber { PlanesNumber(v) }
    public static func of(_ v: BigInt) -> PlanesNumber { PlanesNumber(Fraction(v)) }
    public static func of(_ v: Int) -> PlanesNumber { PlanesNumber(Fraction(BigInt(v))) }
    public static func of(_ v: String) throws(NumberError) -> PlanesNumber { try parse(v) }
    public static func of(_ v: Bool) throws(NumberError) -> PlanesNumber {
        throw .type("a yes/no value is not a number")
    }
    /// Only reachable from foreign data. Takes the shortest decimal that
    /// round-trips, not the float's full binary expansion, so a JSON 0.1
    /// becomes one tenth rather than 0.1000000000000000055 — planes_num.py's
    /// `Fraction(repr(v))`. Swift's `description` is the shortest round-trip
    /// digit string, as Python's `repr` is. The two switch to exponent
    /// notation at different magnitudes, which cannot matter: both texts parse
    /// to the same rational. A non-finite value renders as Python renders it
    /// ("inf", "-inf", "nan"), so it is refused with Python's message.
    public static func of(_ v: Double) throws(NumberError) -> PlanesNumber {
        PlanesNumber(try fractionFromString(v.description))
    }

    // ---- shape

    public func isWhole() -> Bool { q.d == .one }

    public func asInt() throws(NumberError) -> BigInt {
        if !isWhole() { throw .value("\(text()) is not a whole number") }
        return q.n
    }

    /// The value as a host float — planes_num.py's `float(q)`, which is
    /// CPython's correctly rounded int true division (round-half-even,
    /// gradual underflow, OverflowError past the largest double). Only the
    /// host boundary uses it; nothing computes a Planes value from it.
    public func toNumber() throws(NumberError) -> Double {
        try fractionToDouble(q)
    }

    // ---- arithmetic, each refusing past the bound rather than rounding

    private func check(_ r: PlanesNumber, _ op: String) throws(NumberError) -> PlanesNumber {
        if r.q.d > MAX_DENOMINATOR { throw .inexact(Inexact(op)) }
        return r
    }

    // exact + exact is exact; anything touching an approximate value is
    // approximate, and inherits the FIRST entry point on the left-to-right
    // reading of the expression.
    public func add(_ o: PlanesNumber) throws(NumberError) -> PlanesNumber {
        try check(PlanesNumber(q.add(o.q), approx ?? o.approx), "+")
    }
    public func sub(_ o: PlanesNumber) throws(NumberError) -> PlanesNumber {
        try check(PlanesNumber(q.sub(o.q), approx ?? o.approx), "-")
    }
    public func mul(_ o: PlanesNumber) throws(NumberError) -> PlanesNumber {
        try check(PlanesNumber(q.mul(o.q), approx ?? o.approx), "*")
    }
    public func div(_ o: PlanesNumber) throws(NumberError) -> PlanesNumber {
        if o.q.n.isZero { throw .zeroDivision("divided by zero") }
        return try check(PlanesNumber(try q.div(o.q), approx ?? o.approx), "/")
    }
    public func neg() -> PlanesNumber { PlanesNumber(q.neg(), approx) }

    // ---- comparison: the plain rational ordering, exact or not
    public func eq(_ o: PlanesNumber) -> Bool { q.eq(o.q) }
    public func cmp(_ o: PlanesNumber) -> Int { q.cmp(o.q) }
    public func lt(_ o: PlanesNumber) -> Bool { cmp(o) < 0 }
    public func le(_ o: PlanesNumber) -> Bool { cmp(o) <= 0 }
    public func gt(_ o: PlanesNumber) -> Bool { cmp(o) > 0 }
    public func ge(_ o: PlanesNumber) -> Bool { cmp(o) >= 0 }
    public func isZero() -> Bool { q.n.isZero }

    // ---- rounding, only when asked; half away from zero, all integer
    // arithmetic. The result carries whatever the input carried: rounding an
    // exact value gives an exact one, and rounding an approximate one does not
    // launder it back to exact.
    public func roundTo(_ places: Int) throws(NumberError) -> PlanesNumber {
        if places < 0 { throw .value("places cannot be negative") }
        let scale = Fraction(ten.power(places))
        let scaled = q.mul(scale)
        let n = scaled.n
        let d = scaled.d
        let rounded: BigInt
        if d == .one {
            rounded = n
        } else {
            let magnitude = (n.magnitude * two + d) / (d * two)
            rounded = n.isNegative ? -magnitude : magnitude
        }
        return PlanesNumber(try Fraction(rounded).div(scale), approx)
    }

    // ---- rendering. A terminating expansion prints exactly; a non-terminating
    // one prints to maxPlaces with a leading ~, so the approximation is visible.
    public func text(_ maxPlaces: Int = 12) -> String {
        if q.d == .one { return q.n.description }
        if terminates(q.d) { return exactDecimal(q) }
        let neg = q.n.isNegative
        let scaled = (q.n.magnitude * ten.power(maxPlaces)) / q.d  // floor, since positive
        let digits = zeroPad(scaled.description, maxPlaces + 1)
        let whole = digits.prefix(digits.utf8.count - maxPlaces)
        var frac = stripTrailingZeros(digits.suffix(maxPlaces))
        if frac.isEmpty { frac = "0" }
        return "~\(neg ? "-" : "")\(whole).\(frac)"
    }
}

extension PlanesNumber: CustomStringConvertible {
    public var description: String { text() }
}

// ------------------------------------------------------------------ float out

/// CPython's `long_true_divide` for `q.n / q.d`: the double nearest the exact
/// quotient, ties to even, with gradual underflow; OverflowError when the
/// rounded result exceeds the largest finite double.
func fractionToDouble(_ q: Fraction) throws(NumberError) -> Double {
    let DBL_MANT_DIG = 53
    let DBL_MAX_EXP = 1024
    let DBL_MIN_EXP = -1021
    let negate = q.n.isNegative
    let a = q.n.magnitude
    let b = q.d
    if a.isZero { return negate ? -0.0 : 0.0 }
    // a/b is in [2**(diff-1), 2**(diff+1)).
    let diff = a.bitLength - b.bitLength
    if diff > DBL_MAX_EXP {
        throw .overflow("integer division result too large for a float")
    } else if diff < DBL_MIN_EXP - DBL_MANT_DIG - 1 {
        return negate ? -0.0 : 0.0
    }
    let shift = max(diff, DBL_MIN_EXP) - DBL_MANT_DIG - 2
    var inexact = false
    var x: BigInt
    if shift <= 0 {
        x = a << -shift
    } else {
        x = a >> shift
        if !(a - (x << shift)).isZero { inexact = true }
    }
    let (quotient, remainder) = x.quotientAndRemainder(dividingBy: b)
    x = quotient
    if !remainder.isZero { inexact = true }
    let xBits = x.bitLength
    // The number of extra bits that have to be rounded away: 2 or 3.
    let extraBits = max(xBits, DBL_MIN_EXP - shift) - DBL_MANT_DIG
    let mask = UInt64(1) << UInt64(extraBits - 1)
    var mantissa = x.magnitudeLow64  // xBits <= 56: the whole value
    let low = mantissa | (inexact ? 1 : 0)
    if (low & mask) != 0 && (low & (3 * mask - 1)) != 0 {
        mantissa += mask
    }
    mantissa &= ~(2 * mask - 1)
    let dx = Double(mantissa)  // exact: at most 54 significant bits, low bits clear
    if shift + xBits >= DBL_MAX_EXP
        && (shift + xBits > DBL_MAX_EXP || dx == Double(sign: .plus, exponent: xBits, significand: 1.0)) {
        throw .overflow("integer division result too large for a float")
    }
    let result = Double(sign: .plus, exponent: shift, significand: dx)
    return negate ? -result : result
}

// ------------------------------------------------------------------ number of (A-Q19)
//
// `write` emits a number as JSON text so an exact value survives a tool that
// isn't Planes; `read` and `ask` hand text back. Nothing turned that text back
// into a number until this builtin. Deliberately narrower than
// PlanesNumber.parse / fractionFromString: no exponent notation and no `a/b`
// form — a source NUMBER token is only ever `\d+(\.\d+)?`, and accepting on
// input what the language cannot itself write would be an asymmetry nobody
// asked for. Whitespace is trimmed first, the same convention Fraction(text)
// already uses.

/// planes_num.py's `-?\d+(\.\d+)?`, full match, with Python's Unicode `\d`.
func matchesNumberText(_ s: String) -> Bool {
    let cps = Array(s.unicodeScalars)
    var i = 0
    if i < cps.count, cps[i] == "-" { i += 1 }
    let intStart = i
    while i < cps.count, pythonDecimalDigit(cps[i]) != nil { i += 1 }
    if i == intStart { return false }
    if i == cps.count { return true }
    guard cps[i] == "." else { return false }
    i += 1
    let fracStart = i
    while i < cps.count, pythonDecimalDigit(cps[i]) != nil { i += 1 }
    return i > fracStart && i == cps.count
}

/// Text `number of` refuses. `approximation` distinguishes the `~`-prefixed
/// case (its own reason: the text names an approximation, not a value) from
/// plain non-numeric text, so the caller can raise the right message.
public struct NotANumber: Error, Sendable, Equatable {
    public let text: String
    public let approximation: Bool
    public init(_ text: String, approximation: Bool = false) {
        self.text = text
        self.approximation = approximation
    }
    public var message: String { "not a number: \(pythonRepr(text))" }
}

/// `number of text` — text to an exact PlanesNumber, or a refusal. A
/// `~`-prefixed text is refused before the general check, with its own reason:
/// it is the language's own marker for a rounded display, not a value, so
/// parsing it would silently manufacture a different, terminating rational
/// than the one that was printed.
public func numberFromText(_ text: String) throws(NumberError) -> PlanesNumber {
    let s = pythonStrip(text)
    if s.unicodeScalars.first == "~" { throw .notANumber(NotANumber(text, approximation: true)) }
    if !matchesNumberText(s) { throw .notANumber(NotANumber(text)) }
    return try PlanesNumber.parse(s)
}

// ------------------------------------------------------------------ sine (planes_checkpoint_v21_0 §§251-253)
//
// THE ALGORITHM, once. The port of planes_num.py's sine_degrees, on exactly the
// same integers — which is what makes the hosts bit-identical rather than
// merely close. The full derivation, and why this is scaled integers rather
// than plain exact rationals, is in planes_num.py's comment; the short version
// is that the rational form refuses outright at `sine of 60` (a denominator of
// 10^1224, past MAX_DENOMINATOR).

/// pi/180 to 40 significant decimal digits, correctly rounded:
///   0.01745329251994329576923690768488612713443
/// The error against the true value is under 1.3e-42. Byte-identical to
/// planes_num.py's literal.
public let PI_OVER_180_NUM = BigInt("1745329251994329576923690768488612713443")!
public let PI_OVER_180_DEN = BigInt(10).power(41)
public let PI_OVER_180_DIGITS = 40

/// Eight terms: x - x^3/3! + ... - x^15/15!. After the fold the series argument
/// is at most pi/4, where the first omitted term (x^17/17!) is 4.62e-17.
public let SERIES_TERMS = 8
public let WORKING_PLACES = 50
let WORKING_SCALE = BigInt(10).power(WORKING_PLACES)
public let RESULT_PLACES = 30
let RESULT_SCALE = BigInt(10).power(RESULT_PLACES)

/// Round n/d to the nearest integer, half away from zero. Integers only — the
/// same rule `round x to N places` uses.
func divRound(_ n: BigInt, _ d: BigInt) -> BigInt {
    let negative = n.isNegative != d.isNegative
    let an = n.magnitude
    let ad = d.magnitude
    let r = (an * two + ad) / (ad * two)
    return negative ? -r : r
}

/// sin of (an/ad) degrees, as an integer scaled by WORKING_SCALE. `an/ad` is
/// already folded into [0, 45].
func seriesScaled(_ an: BigInt, _ ad: BigInt) -> BigInt {
    let x = divRound(an * PI_OVER_180_NUM * WORKING_SCALE, ad * PI_OVER_180_DEN)
    let x2 = divRound(x * x, WORKING_SCALE)
    var term = x
    var total = x
    for k in 1..<SERIES_TERMS {
        term = -divRound(term * x2, WORKING_SCALE * BigInt(2 * k) * BigInt(2 * k + 1))
        total += term
    }
    return total
}

/// One record, shared by every value `sine` ever returns: the operation, and
/// the four numbers that decide how good the answer is.
public let SINE_APPROXIMATION = Approximation(
    "sine",
    "pi/180 to \(PI_OVER_180_DIGITS) significant digits, "
        + "an \(SERIES_TERMS)-term Taylor series, "
        + "\(WORKING_PLACES) working decimal places, "
        + "a result rounded to \(RESULT_PLACES)"
)

/// `sine of d` — d in degrees, exact in, approximate out.
///
/// Steps 1 and 2 are exact: `sine of 360000030` reduces to `sine of 30` with
/// no additional error at all.
public func sineDegrees(_ value: PlanesNumber) -> PlanesNumber {
    let an = value.q.n
    let ad = value.q.d

    // 1. into [0, 360), FLOORED as Python's // is, exactly
    let m = BigInt(360) * ad
    let (_, floorRemainder) = an.floorDivMod(m)
    var rn = floorRemainder  // an - m * (an // m)

    // 2. into [0, 45], exactly — sign flips and subtractions only
    var sign = BigInt.one
    if rn >= BigInt(180) * ad {
        rn -= BigInt(180) * ad
        sign = BigInt(-1)
    }
    if rn > BigInt(90) * ad { rn = BigInt(180) * ad - rn }

    // 3 and 4. the series, at the stated precisions
    let s: BigInt
    if rn <= BigInt(45) * ad {
        s = seriesScaled(rn, ad)
    } else {
        // sin(a) = cos(90 - a) = 1 - 2 * sin((90 - a)/2)^2, and (90-a)/2 <= 22.5
        let h = seriesScaled(BigInt(90) * ad - rn, ad * two)
        s = WORKING_SCALE - divRound(two * h * h, WORKING_SCALE)
    }

    let scaled = divRound(sign * s * RESULT_SCALE, WORKING_SCALE)
    return PlanesNumber(Fraction(unchecked: scaled, RESULT_SCALE), SINE_APPROXIMATION)
}

// ------------------------------------------------------------------ square root (square-root-spec.md)
//
// The thirteenth builtin, and the first operation whose exactness is decided
// by its ARGUMENT rather than by itself. Whether the answer is rational is
// DECIDABLE, and when it is, the exact answer is integer arithmetic.

/// Floor of the square root of a non-negative integer, exactly. Newton from a
/// DECIMAL-LENGTH estimate, not from n itself. The loop ends on
/// x*x <= n < (x+1)*(x+1), which is the definition of the thing rather than a
/// tolerance on it.
public func isqrt(_ n: BigInt) throws(NumberError) -> BigInt {
    if n.isNegative { throw .value("isqrt of a negative integer") }
    if n < two { return n }
    var x = ten.power((n.description.utf8.count + 1) / 2)
    while true {
        let next = (x + n / x) / two
        if next >= x { break }
        x = next
    }
    while x * x > n { x -= .one }
    while (x + .one) * (x + .one) <= n { x += .one }
    return x
}

public let ROOT_APPROXIMATION = Approximation(
    "root",
    "an exact integer square root where the argument is a perfect square, "
        + "otherwise Newton's method on integers scaled by 10^\(RESULT_PLACES), "
        + "a result rounded to \(RESULT_PLACES) places, half away from zero"
)

/// `root of x` — exact when the true result is rational, approximate when it
/// is not. The caller owns the error vocabulary; this function's contract is
/// x >= 0 (a negative argument throws isqrt's ValueError). Because `q` is
/// reduced, sqrt(n/d) is rational exactly when n and d are BOTH perfect
/// squares.
public func rootOf(_ value: PlanesNumber) throws(NumberError) -> PlanesNumber {
    let n = value.q.n
    let d = value.q.d
    let rn = try isqrt(n)
    let rd = try isqrt(d)
    if rn * rn == n && rd * rd == d {
        // Exact — and it keeps whatever the argument carried.
        return PlanesNumber(Fraction(unchecked: rn, rd), value.approx)
    }
    // Doubling before the floor and halving after is how a floor becomes a
    // round-half-away with no division and no rounding mode for the hosts to
    // read differently.
    let scaled = try isqrt((BigInt(4) * n * RESULT_SCALE * RESULT_SCALE) / d)
    return PlanesNumber(Fraction(unchecked: (scaled + .one) / two, RESULT_SCALE), ROOT_APPROXIMATION)
}
