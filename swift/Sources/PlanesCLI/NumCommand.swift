// NumCommand.swift — `num <json-ops>`, js/cli.mjs's numOp.
//
// Each op is a JSON array [name, ...args]; the result is the text/canonical
// answer, so the Python oracle can compare planes_num.py's answer string for
// string. The op set is js/cli.mjs's, exactly.
import Planes

enum NumCommand {
    static func run(_ rest: [String]) {
        guard case .array(let ops)? = try? NumJSON.parse(rest.first ?? "") else {
            CLI.fail("num: expected a JSON array of ops")
        }
        CLI.out(json: ops.map(op))
    }

    private static func op(_ op: NumJSON) -> Any {
        guard case .array(let parts) = op, case .string(let name)? = parts.first else {
            CLI.fail("num: malformed op")
        }
        let a = Array(parts.dropFirst())
        func str(_ i: Int) -> String {
            guard i < a.count, case .string(let s) = a[i] else { CLI.fail("num: \(name) expects a string argument \(i)") }
            return s
        }
        func parse(_ i: Int) throws(NumberError) -> PlanesNumber { try PlanesNumber.parse(str(i)) }
        func int(_ i: Int) -> BigInt {
            guard let v = BigInt(str(i)) else { CLI.fail("num: \(name) expects an integer argument \(i)") }
            return v
        }
        do {
            switch name {
            case "parse":
                return try parse(0).text()
            case "of":
                guard let arg = a.first else { CLI.fail("num: of expects an argument") }
                switch arg {
                case .string(let s): return try PlanesNumber.of(s).text()
                case .int(let v): return PlanesNumber.of(v).text()
                case .float(let token):
                    // Python's json.loads reads a non-integer token as float(token);
                    // Swift's Double(String) is the same correctly rounded parse.
                    guard let d = Double(token) else { CLI.fail("num: bad float \(token)") }
                    return try PlanesNumber.of(d).text()
                case .bool(let b): return try PlanesNumber.of(b).text()
                default: CLI.fail("num: not a number: \(arg)")
                }
            case "add":
                return try parse(0).add(parse(1)).text()
            case "sub":
                return try parse(0).sub(parse(1)).text()
            case "mul":
                return try parse(0).mul(parse(1)).text()
            case "div":
                return try parse(0).div(parse(1)).text()
            case "round":
                guard let places = int(1).asInt else { CLI.fail("num: places out of range") }
                return try parse(0).roundTo(places).text()
            case "sine":
                // H6: the four-way sine agreement suite drives this the same
                // way `sine of d` does in a running program — parse the
                // degrees, take the sine, render the same `.text()` a `show`
                // would print.
                return sineDegrees(try parse(0)).text()
            case "root":
                return try rootOf(try parse(0)).text()
            case "frac":
                return PlanesNumber(try Fraction(int(0), int(1))).text()
            case "cmp":
                return String(try parse(0).cmp(parse(1)))
            case "whole":
                return try parse(0).isWhole() ? "true" : "false"
            case "asint":
                do {
                    return try parse(0).asInt().description
                } catch {
                    return "ERR"
                }
            case "harmonic":
                // 1/1 + 1/2 + ... + 1/n, exact — the denominator-growth case.
                guard let n = int(0).asInt else { CLI.fail("num: harmonic count out of range") }
                var acc = PlanesNumber(BigInt.zero)
                if n >= 1 {
                    for k in 1...n {
                        acc = try acc.add(PlanesNumber(try Fraction(.one, BigInt(k))))
                    }
                }
                return acc.text()
            case "inexact":
                // A denominator past MAX_DENOMINATOR must refuse, not round.
                do {
                    _ = try PlanesNumber(try Fraction(.one, BigInt(2).power(4001)))
                        .add(PlanesNumber.of(0))
                        .text()
                    return "NO-REFUSAL"
                } catch {
                    if case .inexact = error { return "INEXACT" }
                    return "OTHER:" + error.message
                }
            default:
                CLI.fail("unknown num op: \(name)")
            }
        } catch {
            CLI.fail("num: \(name): \(error.message)")
        }
    }
}

/// JSON as Python's `json.loads` reads it, for the one thing Foundation's
/// JSONSerialization cannot promise: an integer token is an unbounded `int`
/// and any other number token is a `float`, with its text kept. `["of", 0.1]`
/// and `["of", 100]` take different paths in planes_num.py's `Number.of`.
enum NumJSON: CustomStringConvertible {
    case string(String)
    case int(BigInt)
    case float(String)
    case bool(Bool)
    case null
    case array([NumJSON])
    case object([(String, NumJSON)])

    struct Malformed: Error {}

    var description: String {
        switch self {
        case .string(let s): return "\"\(s)\""
        case .int(let v): return v.description
        case .float(let t): return t
        case .bool(let b): return b ? "true" : "false"
        case .null: return "null"
        case .array(let a): return "[" + a.map(\.description).joined(separator: ", ") + "]"
        case .object(let o): return "{" + o.map { "\"\($0.0)\": \($0.1)" }.joined(separator: ", ") + "}"
        }
    }

    static func parse(_ text: String) throws(Malformed) -> NumJSON {
        var reader = Reader(bytes: Array(text.utf8))
        let value = try reader.value()
        reader.skipSpace()
        if reader.i != reader.bytes.count { throw Malformed() }
        return value
    }

    private struct Reader {
        let bytes: [UInt8]
        var i = 0

        mutating func skipSpace() {
            while i < bytes.count, [0x20, 0x09, 0x0A, 0x0D].contains(bytes[i]) { i += 1 }
        }

        mutating func value() throws(Malformed) -> NumJSON {
            skipSpace()
            guard i < bytes.count else { throw Malformed() }
            switch bytes[i] {
            case UInt8(ascii: "["):
                i += 1
                var items: [NumJSON] = []
                skipSpace()
                if i < bytes.count, bytes[i] == UInt8(ascii: "]") { i += 1; return .array(items) }
                while true {
                    items.append(try value())
                    skipSpace()
                    guard i < bytes.count else { throw Malformed() }
                    if bytes[i] == UInt8(ascii: ",") { i += 1; continue }
                    if bytes[i] == UInt8(ascii: "]") { i += 1; return .array(items) }
                    throw Malformed()
                }
            case UInt8(ascii: "{"):
                i += 1
                var members: [(String, NumJSON)] = []
                skipSpace()
                if i < bytes.count, bytes[i] == UInt8(ascii: "}") { i += 1; return .object(members) }
                while true {
                    skipSpace()
                    guard case .string(let key) = try value() else { throw Malformed() }
                    skipSpace()
                    guard i < bytes.count, bytes[i] == UInt8(ascii: ":") else { throw Malformed() }
                    i += 1
                    members.append((key, try value()))
                    skipSpace()
                    guard i < bytes.count else { throw Malformed() }
                    if bytes[i] == UInt8(ascii: ",") { i += 1; continue }
                    if bytes[i] == UInt8(ascii: "}") { i += 1; return .object(members) }
                    throw Malformed()
                }
            case UInt8(ascii: "\""):
                return .string(try string())
            case UInt8(ascii: "t"): try literal("true"); return .bool(true)
            case UInt8(ascii: "f"): try literal("false"); return .bool(false)
            case UInt8(ascii: "n"): try literal("null"); return .null
            default:
                return try number()
            }
        }

        mutating func literal(_ word: String) throws(Malformed) {
            let w = Array(word.utf8)
            guard i + w.count <= bytes.count, Array(bytes[i..<i + w.count]) == w else { throw Malformed() }
            i += w.count
        }

        mutating func digits() -> Int {
            let start = i
            while i < bytes.count, bytes[i] >= 0x30, bytes[i] <= 0x39 { i += 1 }
            return i - start
        }

        mutating func number() throws(Malformed) -> NumJSON {
            let start = i
            if i < bytes.count, bytes[i] == UInt8(ascii: "-") { i += 1 }
            if digits() == 0 { throw Malformed() }
            var isFloat = false
            if i < bytes.count, bytes[i] == UInt8(ascii: ".") {
                i += 1
                isFloat = true
                if digits() == 0 { throw Malformed() }
            }
            if i < bytes.count, bytes[i] == UInt8(ascii: "e") || bytes[i] == UInt8(ascii: "E") {
                i += 1
                isFloat = true
                if i < bytes.count, bytes[i] == UInt8(ascii: "+") || bytes[i] == UInt8(ascii: "-") { i += 1 }
                if digits() == 0 { throw Malformed() }
            }
            let token = String(decoding: bytes[start..<i], as: UTF8.self)
            if isFloat { return .float(token) }
            guard let v = BigInt(token) else { throw Malformed() }
            return .int(v)
        }

        mutating func hex4() throws(Malformed) -> UInt32 {
            guard i + 4 <= bytes.count else { throw Malformed() }
            var v: UInt32 = 0
            for b in bytes[i..<i + 4] {
                v <<= 4
                switch b {
                case 0x30...0x39: v |= UInt32(b - 0x30)
                case 0x41...0x46: v |= UInt32(b - 0x41 + 10)
                case 0x61...0x66: v |= UInt32(b - 0x61 + 10)
                default: throw Malformed()
                }
            }
            i += 4
            return v
        }

        mutating func string() throws(Malformed) -> String {
            i += 1  // the opening quote
            var out = String.UnicodeScalarView()
            var run = i
            func flush(_ end: Int) {
                out.append(contentsOf: String(decoding: bytes[run..<end], as: UTF8.self).unicodeScalars)
            }
            while i < bytes.count {
                let b = bytes[i]
                if b == UInt8(ascii: "\"") {
                    flush(i)
                    i += 1
                    return String(out)
                }
                if b == UInt8(ascii: "\\") {
                    flush(i)
                    i += 1
                    guard i < bytes.count else { throw Malformed() }
                    let e = bytes[i]
                    i += 1
                    switch e {
                    case UInt8(ascii: "\""): out.append("\"")
                    case UInt8(ascii: "\\"): out.append("\\")
                    case UInt8(ascii: "/"): out.append("/")
                    case UInt8(ascii: "b"): out.append("\u{08}")
                    case UInt8(ascii: "f"): out.append("\u{0C}")
                    case UInt8(ascii: "n"): out.append("\n")
                    case UInt8(ascii: "r"): out.append("\r")
                    case UInt8(ascii: "t"): out.append("\t")
                    case UInt8(ascii: "u"):
                        var cp = try hex4()
                        if cp >= 0xD800 && cp < 0xDC00 {
                            guard i + 1 < bytes.count, bytes[i] == UInt8(ascii: "\\"), bytes[i + 1] == UInt8(ascii: "u") else {
                                throw Malformed()  // a lone surrogate has no Swift String form
                            }
                            i += 2
                            let low = try hex4()
                            guard low >= 0xDC00 && low < 0xE000 else { throw Malformed() }
                            cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00)
                        }
                        guard let scalar = Unicode.Scalar(cp) else { throw Malformed() }
                        out.append(scalar)
                    default:
                        throw Malformed()
                    }
                    run = i
                    continue
                }
                i += 1
            }
            throw Malformed()
        }
    }
}
