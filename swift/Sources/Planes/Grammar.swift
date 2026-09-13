// Grammar.swift — the grammar's data: vocabulary, core, amber templates.
//
// The Swift counterpart of js/grammar_data.mjs, and of lexer.py's
// _load_vocabulary. grammar/vocabulary.json is the single source of truth, as it
// is for the other two hosts. They read it off disk (lexer.py directly, js via
// loader_node.mjs); this library has to run inside an app that does not carry the
// repo, so the files are embedded verbatim in Generated/GrammarData.swift by
// scripts/swift_grammar_gen.py and parsed here, once, at first use. The setters
// remain, as in js, for a host that wants to inject a document of its own; each
// validates exactly as js does.
//
// Documents are held as `GrammarJSON`, which keeps object keys in source order
// (porting rule 2) and strings as exact code points (rule 1).
import Foundation

// Mirrors lexer.py's GrammarDataError — refuse, don't guess.
public struct GrammarDataError: Error, CustomStringConvertible, Sendable {
    public let tag: String
    public let detail: String
    public let fix: String
    public let message: String

    public init(_ tag: String, _ detail: String = "", _ fix: String = "") {
        self.tag = tag
        self.detail = detail
        self.fix = fix
        var msg = tag
        if !detail.isEmpty { msg += ": \(detail)" }
        if !fix.isEmpty { msg += "\n  try: \(fix)" }
        message = msg
    }

    public var description: String { message }
}

// ================================================================ JSON, order-preserving

/// A parsed grammar document. Objects keep their keys in source order; numbers
/// keep their literal text (the grammar only holds small integers).
public enum GrammarJSON: Sendable, Equatable {
    case null
    case bool(Bool)
    case number(String)
    case string(String)
    case array([GrammarJSON])
    case object([(key: String, value: GrammarJSON)])

    public static func == (a: GrammarJSON, b: GrammarJSON) -> Bool {
        switch (a, b) {
        case (.null, .null): return true
        case let (.bool(x), .bool(y)): return x == y
        case let (.number(x), .number(y)): return sameText(x, y)
        case let (.string(x), .string(y)): return sameText(x, y)
        case let (.array(x), .array(y)): return x == y
        case let (.object(x), .object(y)):
            return x.count == y.count && zip(x, y).allSatisfy { sameText($0.key, $1.key) && $0.value == $1.value }
        default: return false
        }
    }

    /// The value under `key`, for an object that has it. The first occurrence
    /// wins; the grammar files have no duplicate keys.
    public subscript(_ key: String) -> GrammarJSON? {
        guard case let .object(entries) = self else { return nil }
        return entries.first { sameText($0.key, key) }?.value
    }

    public func has(_ key: String) -> Bool { self[key] != nil }

    public var string: String? { if case let .string(s) = self { s } else { nil } }
    public var array: [GrammarJSON]? { if case let .array(a) = self { a } else { nil } }
    public var int: Int? { if case let .number(n) = self { Int(n) } else { nil } }

    /// JSON text for a value, as `JSON.stringify` writes it, keys in order — used
    /// to name a bad value in a refusal, and by the agreement CLI to emit the
    /// surface and rule forms (EffectSurface.swift's asJson and its siblings).
    public var jsonText: String {
        switch self {
        case .null: return "null"
        case let .bool(b): return b ? "true" : "false"
        case let .number(n): return n
        case let .string(s):
            var out = "\""
            for c in s.unicodeScalars {
                switch c {
                case "\"": out += "\\\""
                case "\\": out += "\\\\"
                case "\n": out += "\\n"
                case "\t": out += "\\t"
                case "\r": out += "\\r"
                default:
                    if c.value < 0x20 { out += String(format: "\\u%04x", c.value) } else { out.unicodeScalars.append(c) }
                }
            }
            return out + "\""
        case let .array(a): return "[" + a.map(\.jsonText).joined(separator: ",") + "]"
        case let .object(o): return "{" + o.map { GrammarJSON.string($0.key).jsonText + ":" + $0.value.jsonText }.joined(separator: ",") + "}"
        }
    }

    /// Parses RFC 8259 JSON text. `nil` on anything malformed.
    public static func parse(_ text: String) -> GrammarJSON? {
        var p = JSONScanner(Array(text.unicodeScalars))
        p.skipSpace()
        guard let v = p.value() else { return nil }
        p.skipSpace()
        return p.i == p.s.count ? v : nil
    }
}

private struct JSONScanner {
    let s: [Unicode.Scalar]
    var i = 0
    init(_ s: [Unicode.Scalar]) { self.s = s }

    mutating func skipSpace() {
        while i < s.count, s[i] == " " || s[i] == "\n" || s[i] == "\t" || s[i] == "\r" { i += 1 }
    }

    mutating func literal(_ word: String) -> Bool {
        let w = Array(word.unicodeScalars)
        guard i + w.count <= s.count, Array(s[i..<i + w.count]) == w else { return false }
        i += w.count
        return true
    }

    mutating func value() -> GrammarJSON? {
        guard i < s.count else { return nil }
        switch s[i] {
        case "{": return object()
        case "[": return array()
        case "\"": return string().map(GrammarJSON.string)
        case "t": return literal("true") ? .bool(true) : nil
        case "f": return literal("false") ? .bool(false) : nil
        case "n": return literal("null") ? .null : nil
        default: return number()
        }
    }

    mutating func object() -> GrammarJSON? {
        i += 1
        var entries: [(key: String, value: GrammarJSON)] = []
        skipSpace()
        if i < s.count, s[i] == "}" { i += 1; return .object(entries) }
        while true {
            skipSpace()
            guard i < s.count, s[i] == "\"", let key = string() else { return nil }
            skipSpace()
            guard i < s.count, s[i] == ":" else { return nil }
            i += 1
            skipSpace()
            guard let v = value() else { return nil }
            entries.append((key, v))
            skipSpace()
            guard i < s.count else { return nil }
            if s[i] == "," { i += 1; continue }
            if s[i] == "}" { i += 1; return .object(entries) }
            return nil
        }
    }

    mutating func array() -> GrammarJSON? {
        i += 1
        var items: [GrammarJSON] = []
        skipSpace()
        if i < s.count, s[i] == "]" { i += 1; return .array(items) }
        while true {
            skipSpace()
            guard let v = value() else { return nil }
            items.append(v)
            skipSpace()
            guard i < s.count else { return nil }
            if s[i] == "," { i += 1; continue }
            if s[i] == "]" { i += 1; return .array(items) }
            return nil
        }
    }

    mutating func hex4() -> UInt32? {
        guard i + 4 <= s.count else { return nil }
        var v: UInt32 = 0
        for c in s[i..<i + 4] {
            guard let d = c.properties.isASCIIHexDigit ? UInt32(String(c), radix: 16) : nil else { return nil }
            v = v * 16 + d
        }
        i += 4
        return v
    }

    mutating func string() -> String? {
        i += 1
        var out = String.UnicodeScalarView()
        while i < s.count {
            let c = s[i]
            i += 1
            if c == "\"" { return String(out) }
            if c.value < 0x20 { return nil }
            guard c == "\\" else { out.append(c); continue }
            guard i < s.count else { return nil }
            let e = s[i]
            i += 1
            switch e {
            case "\"": out.append("\"")
            case "\\": out.append("\\")
            case "/": out.append("/")
            case "b": out.append("\u{08}")
            case "f": out.append("\u{0C}")
            case "n": out.append("\n")
            case "r": out.append("\r")
            case "t": out.append("\t")
            case "u":
                guard var v = hex4() else { return nil }
                if (0xD800..<0xDC00).contains(v), i + 1 < s.count, s[i] == "\\", s[i + 1] == "u" {
                    let save = i
                    i += 2
                    if let lo = hex4(), (0xDC00..<0xE000).contains(lo) {
                        v = 0x10000 + ((v - 0xD800) << 10) + (lo - 0xDC00)
                    } else {
                        i = save
                    }
                }
                guard let scalar = Unicode.Scalar(v) else { return nil }  // a lone surrogate
                out.append(scalar)
            default: return nil
            }
        }
        return nil
    }

    mutating func number() -> GrammarJSON? {
        let start = i
        func digits(_ p: inout JSONScanner) -> Int {
            let from = p.i
            while p.i < p.s.count, ("0"..."9").contains(p.s[p.i]) { p.i += 1 }
            return p.i - from
        }
        if i < s.count, s[i] == "-" { i += 1 }
        guard i < s.count else { return nil }
        if s[i] == "0" { i += 1 } else if digits(&self) == 0 { return nil }
        if i < s.count, s[i] == "." {
            i += 1
            if digits(&self) == 0 { return nil }
        }
        if i < s.count, s[i] == "e" || s[i] == "E" {
            i += 1
            if i < s.count, s[i] == "+" || s[i] == "-" { i += 1 }
            if digits(&self) == 0 { return nil }
        }
        return .number(String(String.UnicodeScalarView(s[start..<i])))
    }
}

/// Text-keyed, insertion-ordered: a JS `Map` whose keys are Planes text.
public struct TextTable<Value: Sendable>: Sendable {
    public private(set) var keys: [String] = []
    private var index: [CodePoints: Value] = [:]

    public init() {}

    public subscript(_ key: String) -> Value? {
        get { index[CodePoints(key)] }
        set {
            let k = CodePoints(key)
            if index[k] == nil, newValue != nil { keys.append(key) }
            if newValue == nil, index[k] != nil { keys.removeAll { sameText($0, key) } }
            index[k] = newValue
        }
    }

    public func has(_ key: String) -> Bool { index[CodePoints(key)] != nil }
    public var count: Int { keys.count }
    public var entries: [(key: String, value: Value)] { keys.map { ($0, index[CodePoints($0)]!) } }
}

// ================================================================ embedded files

struct EmbeddedGrammarFile: Sendable {
    let path: String
    let utf8Count: Int
    let fnv1a64: UInt64
    let text: String

    /// The document, after proving the literal is byte-for-byte the file the
    /// generator read.
    func parsed() throws(GrammarDataError) -> GrammarJSON {
        let fix = "regenerate with python3 scripts/swift_grammar_gen.py"
        var h: UInt64 = 0xCBF29CE484222325
        var n = 0
        for b in text.utf8 {
            h = (h ^ UInt64(b)) &* 0x100000001B3
            n += 1
        }
        guard n == utf8Count, h == fnv1a64 else {
            throw GrammarDataError("grammar-data-missing", "the embedded \(path) does not match the bytes it was generated from", fix)
        }
        guard let doc = GrammarJSON.parse(text) else {
            throw GrammarDataError("grammar-data-missing", "the embedded \(path) is not valid JSON", fix)
        }
        return doc
    }
}

// ================================================================ the loaded documents

private let GRAMMAR_FORMAT_VERSION = "1"
private let REQUIRED_VOCAB_KEYS = ["token_classes", "keywords", "builtins", "effect_kinds", "field_name_token_kinds"]
private let REQUIRED_CORE_KEYS = ["keywords", "builtins", "effect_kinds_all_core"]

private final class GrammarState: @unchecked Sendable {
    let lock = NSLock()
    var vocab: GrammarJSON?
    var core: GrammarJSON?
    var amber: TextTable<GrammarJSON>?
    /// Bumped whenever the vocabulary is replaced, so tables derived from it
    /// (Lexer.swift's) know to rebuild.
    var vocabGeneration = 0

    func locked<T>(_ body: () throws(GrammarDataError) -> T) throws(GrammarDataError) -> T {
        lock.lock()
        defer { lock.unlock() }
        return try body()
    }
}

private let state = GrammarState()

private func formatIs1(_ doc: GrammarJSON) -> Bool {
    // js compares `doc.format !== 1`, so any spelling of the number one passes.
    if case let .number(n) = doc["format"] ?? .null { return Double(n) == Double(GRAMMAR_FORMAT_VERSION) }
    return false
}

private func validatedVocabulary(_ doc: GrammarJSON) throws(GrammarDataError) -> GrammarJSON {
    let fix = "reinstall planes, or regenerate with python3 grammar_gen.py"
    guard formatIs1(doc) else {
        throw GrammarDataError(
            "grammar-data-missing",
            "vocabulary format \((doc["format"] ?? .null).jsonText) is not \(GRAMMAR_FORMAT_VERSION)",
            "regenerate the grammar data with a version of planes matching " +
                "this interpreter — if the data is newer than what this " +
                "interpreter reads, upgrade planes instead of regenerating the " +
                "data")
    }
    let missing = REQUIRED_VOCAB_KEYS.filter { !doc.has($0) }
    if !missing.isEmpty {
        throw GrammarDataError("grammar-data-missing", "vocabulary is missing: \(missing.joined(separator: ", "))", fix)
    }
    return doc
}

private func validatedCore(_ doc: GrammarJSON) throws(GrammarDataError) -> GrammarJSON {
    guard formatIs1(doc) else {
        throw GrammarDataError(
            "grammar-data-missing",
            "core format \((doc["format"] ?? .null).jsonText) is not \(GRAMMAR_FORMAT_VERSION)",
            "regenerate the grammar data with a version of planes matching " +
                "this interpreter")
    }
    let missing = REQUIRED_CORE_KEYS.filter { !doc.has($0) }
    if !missing.isEmpty {
        throw GrammarDataError(
            "grammar-data-missing",
            "core is missing: \(missing.joined(separator: ", "))",
            "reinstall planes — grammar/core.json is hand-edited, and " +
                "core_check.py holds it against the vocabulary")
    }
    return doc
}

private func amberTable(_ doc: GrammarJSON) -> TextTable<GrammarJSON> {
    var table = TextTable<GrammarJSON>()
    for t in doc["templates"]?.array ?? [] {
        if let id = t["id"]?.string { table[id] = t }
    }
    return table
}

/// Validates `doc` exactly as lexer.py's _load_vocabulary does — format
/// version, then the required keys — and makes it the vocabulary.
public func setVocabulary(_ doc: GrammarJSON) throws(GrammarDataError) {
    let v = try validatedVocabulary(doc)
    try state.locked { () throws(GrammarDataError) in
        state.vocab = v
        state.vocabGeneration += 1
    }
}

/// grammar/vocabulary.json — the embedded copy unless one was set.
public func vocabulary() throws(GrammarDataError) -> GrammarJSON {
    try vocabularyAndGeneration().doc
}

func vocabularyAndGeneration() throws(GrammarDataError) -> (doc: GrammarJSON, generation: Int) {
    try state.locked { () throws(GrammarDataError) in
        if state.vocab == nil {
            state.vocab = try validatedVocabulary(EmbeddedGrammar.vocabulary.parsed())
            state.vocabGeneration += 1
        }
        return (state.vocab!, state.vocabGeneration)
    }
}

/// Whether a vocabulary is available. The embedded copy always is, unless it
/// fails its own checks.
public func vocabularyLoaded() -> Bool {
    (try? vocabulary()) != nil
}

/// grammar/core.json — the declared port surface.
public func setCore(_ doc: GrammarJSON) throws(GrammarDataError) {
    let c = try validatedCore(doc)
    try state.locked { () throws(GrammarDataError) in state.core = c }
}

public func core() throws(GrammarDataError) -> GrammarJSON {
    try state.locked { () throws(GrammarDataError) in
        if state.core == nil { state.core = try validatedCore(EmbeddedGrammar.core.parsed()) }
        return state.core!
    }
}

public func coreLoaded() -> Bool {
    (try? core()) != nil
}

/// Amber's refusal-message templates — grammar/messages/amber.json, keyed by id.
public func setAmberTemplates(_ doc: GrammarJSON) {
    let table = amberTable(doc)
    try? state.locked { () throws(GrammarDataError) in state.amber = table }
}

public func amberTemplates() throws(GrammarDataError) -> TextTable<GrammarJSON> {
    try state.locked { () throws(GrammarDataError) in
        if state.amber == nil { state.amber = amberTable(try EmbeddedGrammar.amber.parsed()) }
        return state.amber!
    }
}
