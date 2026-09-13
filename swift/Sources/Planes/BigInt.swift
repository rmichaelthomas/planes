// BigInt.swift — unbounded integers, for Planes numbers.
//
// Python's `int` and JavaScript's `BigInt` are unbounded; Swift has no
// arbitrary-precision integer, and this package takes no dependencies. Planes
// numbers are exact rationals over unbounded integers (PlanesNumber.swift), so
// this is the integer they are built on.
//
// Sign and magnitude: the magnitude is little-endian UInt32 limbs with no high
// zero limbs, so zero is the empty array and is never negative. UInt32 limbs
// keep every limb product and every carry inside a UInt64.
//
// DIVISION HAS TWO SEMANTICS, and a port that picks the wrong one is silently
// wrong on negative operands only. `/` and `%` truncate toward zero, as Swift's
// `Int` and JavaScript's BigInt do. `floorDivMod` floors, as Python's `//` and
// `%` do. planes_num.py uses `//` on a possibly negative dividend in exactly one
// place — sine's reduction into [0, 360) — and everywhere else on non-negative
// operands, where the two agree.

public struct BigInt: Sendable, Hashable {
    /// True only for a value below zero; zero is never negative.
    public private(set) var isNegative: Bool
    /// Little-endian limbs, no trailing zero limbs.
    @usableFromInline var limbs: [UInt32]

    @usableFromInline init(negative: Bool, limbs: [UInt32]) {
        var l = limbs
        while let last = l.last, last == 0 { l.removeLast() }
        self.limbs = l
        self.isNegative = l.isEmpty ? false : negative
    }

    public init(_ v: Int) {
        let m = v.magnitude
        self.init(negative: v < 0, limbs: [UInt32(truncatingIfNeeded: m), UInt32(truncatingIfNeeded: m >> 32)])
    }

    public init(_ v: UInt64) {
        self.init(negative: false, limbs: [UInt32(truncatingIfNeeded: v), UInt32(truncatingIfNeeded: v >> 32)])
    }

    /// Decimal text: an optional `+` or `-`, then one or more ASCII digits.
    /// Nothing else — no whitespace, no underscores. Callers that accept more
    /// (fractionFromString) normalise first.
    public init?(_ text: String) {
        var scalars = Substring(text).unicodeScalars[...]
        var negative = false
        if let first = scalars.first, first == "-" || first == "+" {
            negative = first == "-"
            scalars = scalars.dropFirst()
        }
        if scalars.isEmpty { return nil }
        var digits: [UInt8] = []
        digits.reserveCapacity(scalars.count)
        for s in scalars {
            guard s.value >= 48, s.value <= 57 else { return nil }
            digits.append(UInt8(s.value - 48))
        }
        self.init(negative: negative, digits: digits)
    }

    /// From decimal digit values (each 0...9), most significant first.
    init(negative: Bool, digits: [UInt8]) {
        var mag: [UInt32] = []
        var i = 0
        // The first chunk takes the remainder so every later chunk is 9 digits.
        var chunk = digits.count % 9
        if chunk == 0 { chunk = 9 }
        while i < digits.count {
            var v: UInt32 = 0
            for k in i..<min(i + chunk, digits.count) { v = v * 10 + UInt32(digits[k]) }
            BigInt.mulAddSmall(&mag, 1_000_000_000, v)
            i += chunk
            chunk = 9
        }
        self.init(negative: negative, limbs: mag)
    }

    public static let zero = BigInt(0)
    public static let one = BigInt(1)

    public var isZero: Bool { limbs.isEmpty }
    public func signum() -> Int { isZero ? 0 : (isNegative ? -1 : 1) }
    public var magnitude: BigInt { BigInt(negative: false, limbs: limbs) }

    /// The number of bits in the magnitude; 0 for zero. Python's `bit_length`.
    public var bitLength: Int {
        guard let top = limbs.last else { return 0 }
        return limbs.count * 32 - top.leadingZeroBitCount
    }

    /// The value as an `Int`, when it fits.
    public var asInt: Int? {
        if limbs.count > 2 { return nil }
        let m = UInt64(limbs.first ?? 0) | (limbs.count > 1 ? UInt64(limbs[1]) << 32 : 0)
        if isNegative {
            return m <= UInt64(Int.max) + 1 ? Int(truncatingIfNeeded: 0 &- m) : nil
        }
        return m <= UInt64(Int.max) ? Int(m) : nil
    }

    /// The low 64 bits of the magnitude.
    var magnitudeLow64: UInt64 {
        UInt64(limbs.first ?? 0) | (limbs.count > 1 ? UInt64(limbs[1]) << 32 : 0)
    }

    // ---------------------------------------------------------------- magnitudes

    static func compareMagnitudes(_ a: [UInt32], _ b: [UInt32]) -> Int {
        if a.count != b.count { return a.count < b.count ? -1 : 1 }
        var i = a.count - 1
        while i >= 0 {
            if a[i] != b[i] { return a[i] < b[i] ? -1 : 1 }
            i -= 1
        }
        return 0
    }

    static func addMagnitudes(_ a: [UInt32], _ b: [UInt32]) -> [UInt32] {
        let (long, short) = a.count >= b.count ? (a, b) : (b, a)
        var r = [UInt32](repeating: 0, count: long.count + 1)
        var carry: UInt64 = 0
        for i in 0..<long.count {
            let s = UInt64(long[i]) + (i < short.count ? UInt64(short[i]) : 0) + carry
            r[i] = UInt32(truncatingIfNeeded: s)
            carry = s >> 32
        }
        r[long.count] = UInt32(carry)
        return r
    }

    /// a - b, for |a| >= |b|.
    static func subtractMagnitudes(_ a: [UInt32], _ b: [UInt32]) -> [UInt32] {
        var r = a
        var borrow: Int64 = 0
        for i in 0..<a.count {
            let t = Int64(a[i]) - (i < b.count ? Int64(b[i]) : 0) - borrow
            r[i] = UInt32(truncatingIfNeeded: t)
            borrow = t < 0 ? 1 : 0
        }
        return r
    }

    static func multiplyMagnitudes(_ a: [UInt32], _ b: [UInt32]) -> [UInt32] {
        if a.isEmpty || b.isEmpty { return [] }
        var r = [UInt32](repeating: 0, count: a.count + b.count)
        r.withUnsafeMutableBufferPointer { rp in
            a.withUnsafeBufferPointer { ap in
                b.withUnsafeBufferPointer { bp in
                    for i in 0..<ap.count {
                        let ai = UInt64(ap[i])
                        if ai == 0 { continue }
                        var carry: UInt64 = 0
                        for j in 0..<bp.count {
                            // (2^32-1)^2 + 2(2^32-1) = 2^64 - 1: never overflows.
                            let t = ai * UInt64(bp[j]) + UInt64(rp[i + j]) + carry
                            rp[i + j] = UInt32(truncatingIfNeeded: t)
                            carry = t >> 32
                        }
                        rp[i + bp.count] = UInt32(carry)
                    }
                }
            }
        }
        return r
    }

    /// mag = mag * m + add, in place.
    static func mulAddSmall(_ mag: inout [UInt32], _ m: UInt32, _ add: UInt32) {
        var carry = UInt64(add)
        for i in 0..<mag.count {
            let t = UInt64(mag[i]) * UInt64(m) + carry
            mag[i] = UInt32(truncatingIfNeeded: t)
            carry = t >> 32
        }
        if carry != 0 { mag.append(UInt32(carry)) }
    }

    /// (a / d, a % d) for a single-limb divisor.
    static func divideMagnitude(_ a: [UInt32], by d: UInt32) -> ([UInt32], UInt32) {
        var q = [UInt32](repeating: 0, count: a.count)
        var rem: UInt64 = 0
        var i = a.count - 1
        let dd = UInt64(d)
        while i >= 0 {
            let cur = (rem << 32) | UInt64(a[i])
            q[i] = UInt32(truncatingIfNeeded: cur / dd)
            rem = cur % dd
            i -= 1
        }
        return (q, UInt32(rem))
    }

    /// Truncating (quotient, remainder) of magnitudes. Knuth's Algorithm D
    /// (TAOCP 4.3.1), in the form of Hacker's Delight's divmnu.
    static func divideMagnitudes(_ u: [UInt32], _ v: [UInt32]) -> ([UInt32], [UInt32]) {
        precondition(!v.isEmpty, "BigInt division by zero")
        if compareMagnitudes(u, v) < 0 { return ([], u) }
        if v.count == 1 {
            let (q, r) = divideMagnitude(u, by: v[0])
            return (q, [r])
        }
        let n = v.count
        let m = u.count - n
        let s = v[n - 1].leadingZeroBitCount
        // Normalise so the divisor's top limb has its high bit set.
        var vn = [UInt32](repeating: 0, count: n)
        var un = [UInt32](repeating: 0, count: u.count + 1)
        if s == 0 {
            for i in 0..<n { vn[i] = v[i] }
            for i in 0..<u.count { un[i] = u[i] }
        } else {
            for i in stride(from: n - 1, to: 0, by: -1) {
                vn[i] = (v[i] << s) | (v[i - 1] >> (32 - s))
            }
            vn[0] = v[0] << s
            un[u.count] = u[u.count - 1] >> (32 - s)
            for i in stride(from: u.count - 1, to: 0, by: -1) {
                un[i] = (u[i] << s) | (u[i - 1] >> (32 - s))
            }
            un[0] = u[0] << s
        }
        var q = [UInt32](repeating: 0, count: m + 1)
        let base: UInt64 = 1 << 32
        un.withUnsafeMutableBufferPointer { up in
            vn.withUnsafeBufferPointer { vp in
                let vTop = UInt64(vp[n - 1])
                let vNext = UInt64(vp[n - 2])
                var j = m
                while j >= 0 {
                    let num = (UInt64(up[j + n]) << 32) | UInt64(up[j + n - 1])
                    var qhat = num / vTop
                    var rhat = num % vTop
                    while qhat >= base || qhat * vNext > ((rhat << 32) | UInt64(up[j + n - 2])) {
                        qhat -= 1
                        rhat += vTop
                        if rhat >= base { break }
                    }
                    // Multiply and subtract.
                    var borrow: Int64 = 0
                    var carry: UInt64 = 0
                    for i in 0..<n {
                        let p = qhat * UInt64(vp[i]) + carry
                        carry = p >> 32
                        let t = Int64(up[i + j]) - borrow - Int64(p & 0xFFFF_FFFF)
                        up[i + j] = UInt32(truncatingIfNeeded: t)
                        borrow = t < 0 ? 1 : 0
                    }
                    let t = Int64(up[j + n]) - borrow - Int64(carry)
                    up[j + n] = UInt32(truncatingIfNeeded: t)
                    if t < 0 {
                        // Overshot by one: add the divisor back.
                        qhat -= 1
                        var c: UInt64 = 0
                        for i in 0..<n {
                            let sum = UInt64(up[i + j]) + UInt64(vp[i]) + c
                            up[i + j] = UInt32(truncatingIfNeeded: sum)
                            c = sum >> 32
                        }
                        up[j + n] = UInt32(truncatingIfNeeded: UInt64(up[j + n]) + c)
                    }
                    q[j] = UInt32(truncatingIfNeeded: qhat)
                    j -= 1
                }
            }
        }
        var r = [UInt32](repeating: 0, count: n)
        if s == 0 {
            for i in 0..<n { r[i] = un[i] }
        } else {
            for i in 0..<n { r[i] = (un[i] >> s) | (un[i + 1] << (32 - s)) }
        }
        return (q, r)
    }

    // ---------------------------------------------------------------- arithmetic

    public static prefix func - (a: BigInt) -> BigInt {
        BigInt(negative: !a.isNegative, limbs: a.limbs)
    }

    public static func + (a: BigInt, b: BigInt) -> BigInt {
        if a.isNegative == b.isNegative {
            return BigInt(negative: a.isNegative, limbs: addMagnitudes(a.limbs, b.limbs))
        }
        if compareMagnitudes(a.limbs, b.limbs) >= 0 {
            return BigInt(negative: a.isNegative, limbs: subtractMagnitudes(a.limbs, b.limbs))
        }
        return BigInt(negative: b.isNegative, limbs: subtractMagnitudes(b.limbs, a.limbs))
    }

    public static func - (a: BigInt, b: BigInt) -> BigInt { a + (-b) }

    public static func * (a: BigInt, b: BigInt) -> BigInt {
        BigInt(negative: a.isNegative != b.isNegative, limbs: multiplyMagnitudes(a.limbs, b.limbs))
    }

    public static func += (a: inout BigInt, b: BigInt) { a = a + b }
    public static func -= (a: inout BigInt, b: BigInt) { a = a - b }
    public static func *= (a: inout BigInt, b: BigInt) { a = a * b }

    /// Truncating quotient and remainder, as Swift's `Int` and JavaScript's
    /// BigInt: the quotient rounds toward zero, the remainder takes the
    /// dividend's sign.
    public func quotientAndRemainder(dividingBy d: BigInt) -> (quotient: BigInt, remainder: BigInt) {
        let (q, r) = BigInt.divideMagnitudes(limbs, d.limbs)
        return (BigInt(negative: isNegative != d.isNegative, limbs: q), BigInt(negative: isNegative, limbs: r))
    }

    /// Python's `divmod`: the quotient floors, the remainder takes the
    /// divisor's sign. `a // b` and `a % b` in planes_num.py.
    public func floorDivMod(_ d: BigInt) -> (quotient: BigInt, remainder: BigInt) {
        var (q, r) = quotientAndRemainder(dividingBy: d)
        if !r.isZero && (r.isNegative != d.isNegative) {
            q = q - .one
            r = r + d
        }
        return (q, r)
    }

    /// Truncating division (toward zero). Use `floorDivMod` for Python's `//`.
    public static func / (a: BigInt, b: BigInt) -> BigInt { a.quotientAndRemainder(dividingBy: b).quotient }
    /// Truncating remainder (dividend's sign). Use `floorDivMod` for Python's `%`.
    public static func % (a: BigInt, b: BigInt) -> BigInt { a.quotientAndRemainder(dividingBy: b).remainder }

    /// `self ** e`, e >= 0.
    public func power(_ e: Int) -> BigInt {
        precondition(e >= 0, "BigInt.power with a negative exponent")
        var result = BigInt.one
        var base = self
        var k = e
        while k > 0 {
            if k & 1 == 1 { result = result * base }
            k >>= 1
            if k > 0 { base = base * base }
        }
        return result
    }

    /// The greatest common divisor of |a| and |b|; gcd(0, 0) is 0.
    public static func gcd(_ a: BigInt, _ b: BigInt) -> BigInt {
        var x = a.limbs
        var y = b.limbs
        while !y.isEmpty {
            var (_, r) = divideMagnitudes(x, y)
            while let last = r.last, last == 0 { r.removeLast() }
            x = y
            y = r
        }
        return BigInt(negative: false, limbs: x)
    }

    /// Shift left by `n` bits (n >= 0): multiplication by 2^n.
    public static func << (a: BigInt, n: Int) -> BigInt {
        precondition(n >= 0, "negative shift")
        if a.isZero { return a }
        let whole = n / 32
        let bits = n % 32
        var r = [UInt32](repeating: 0, count: whole + a.limbs.count + 1)
        if bits == 0 {
            for i in 0..<a.limbs.count { r[whole + i] = a.limbs[i] }
        } else {
            var carry: UInt32 = 0
            for i in 0..<a.limbs.count {
                r[whole + i] = (a.limbs[i] << bits) | carry
                carry = a.limbs[i] >> (32 - bits)
            }
            r[whole + a.limbs.count] = carry
        }
        return BigInt(negative: a.isNegative, limbs: r)
    }

    /// Shift right by `n` bits (n >= 0), flooring as Python's `>>` does.
    public static func >> (a: BigInt, n: Int) -> BigInt {
        precondition(n >= 0, "negative shift")
        if a.isNegative { return -(((-a) - .one) >> n) - .one }
        let whole = n / 32
        if whole >= a.limbs.count { return .zero }
        let bits = n % 32
        var r = [UInt32](repeating: 0, count: a.limbs.count - whole)
        for i in 0..<r.count {
            let lo = a.limbs[whole + i] >> bits
            let hi: UInt32 = (bits != 0 && whole + i + 1 < a.limbs.count) ? a.limbs[whole + i + 1] << (32 - bits) : 0
            r[i] = lo | hi
        }
        return BigInt(negative: false, limbs: r)
    }
}

extension BigInt: Comparable {
    public static func < (a: BigInt, b: BigInt) -> Bool {
        if a.isNegative != b.isNegative { return a.isNegative }
        let c = compareMagnitudes(a.limbs, b.limbs)
        return a.isNegative ? c > 0 : c < 0
    }
}

extension BigInt: ExpressibleByIntegerLiteral {
    public init(integerLiteral value: Int) { self.init(value) }
}

extension BigInt: CustomStringConvertible {
    /// Decimal text, a leading `-` when negative — Python's `str(int)`.
    public var description: String {
        if isZero { return "0" }
        var chunks: [UInt32] = []
        var mag = limbs
        while !mag.isEmpty {
            let (q, r) = BigInt.divideMagnitude(mag, by: 1_000_000_000)
            chunks.append(r)
            mag = q
            while let last = mag.last, last == 0 { mag.removeLast() }
        }
        var out = isNegative ? "-" : ""
        out += String(chunks[chunks.count - 1])
        for c in chunks.dropLast().reversed() {
            let s = String(c)
            out += String(repeating: "0", count: 9 - s.count) + s
        }
        return out
    }
}
