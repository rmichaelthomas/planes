// Lexer.swift — the Planes lexer, ported from lexer.py.
//
// The Swift counterpart of js/lexer.mjs, keeping its structure and names.
// Indentation-sensitive; emits EOL, BEGIN, END, EOF. The token classes and their
// order come from grammar/vocabulary.json (the single source of truth), tried in
// that order at each position exactly as lexer.py's one combined regex tries its
// alternatives: the first class that matches wins.
//
// Where js compiles the vocabulary's patterns verbatim, this file scans by hand
// over unicode scalars. Swift's `Regex` matches by grapheme cluster and
// `NSRegularExpression` counts UTF-16 units, and either would silently disagree
// with Python's `re` on non-ASCII text — which is what positions, `pos += 1` on
// a stray character, and `\d` all turn on. So each pattern the vocabulary
// declares has a scanner below, keyed by the pattern's exact text, and the
// lexer refuses to run against a vocabulary holding a pattern it has no scanner
// for, rather than guessing at what the new pattern means.
//
// Python semantics the scanners reproduce (lexer.py compiles with no flags):
//   `\d`   any Unicode decimal digit (category Nd), not just 0-9
//   `.`    any code point but "\n"
//   str.strip / lstrip  Python's str.isspace set, not Swift's or JavaScript's
//
// Checked against lexer.py's tokenize() by agreement on every corpus file
// (test_swift_lexer.py). lexer.py's output is the specification.
import Foundation

// A malformed program — refuse, don't guess. The Swift analogue of lexer.py's
// PlanesSyntaxError, which tokenize() raises on an unrecognized escape or a
// trailing backslash that consumes the closing quote.
// `noFix` mirrors lexer.py's `no_fix` (C2): a reason why this raise site names
// no fix clause. Never rendered — the message is byte-identical either way.
public struct PlanesSyntaxError: Error, CustomStringConvertible, Sendable {
    public let message: String
    public let noFix: String?

    public init(_ message: String, noFix: String? = nil) {
        self.message = message
        self.noFix = noFix
    }

    public var description: String { message }
}

// One token. Mirrors lexer.py's Token dataclass.
public struct Token: Sendable, Equatable {
    public var kind: String
    public var value: String
    public var line: Int

    public init(_ kind: String, _ value: String, _ line: Int) {
        self.kind = kind
        self.value = value
        self.line = line
    }

    public static func == (a: Token, b: Token) -> Bool {
        sameText(a.kind, b.kind) && sameText(a.value, b.value) && a.line == b.line
    }
}

// ================================================================ Python's character classes

/// Python's `str.isspace()`, which `str.strip()` and `str.lstrip()` strip:
/// bidirectional class WS, B or S, or category Zs. Enumerated from Python 3.14
/// (Unicode 16.0); test_swift_lexer.py checks it against the running Python.
func isPythonSpace(_ c: Unicode.Scalar) -> Bool {
    switch c.value {
    case 0x09...0x0D, 0x1C...0x20, 0x85, 0xA0, 0x1680, 0x2000...0x200A,
         0x2028, 0x2029, 0x202F, 0x205F, 0x3000:
        return true
    default:
        return false
    }
}

/// Python `re`'s `\d` for a str pattern: category Nd. Enumerated from Python
/// 3.14 (Unicode 16.0) rather than read from Swift's own Unicode tables, which
/// are a version ahead (Swift 6.3 adds U+11DE0...U+11DE9); test_swift_lexer.py
/// checks it against the running Python.
func isPythonDigit(_ c: Unicode.Scalar) -> Bool {
    let v = c.value
    if v <= 0x39 { return v >= 0x30 }
    var lo = 0
    var hi = decimalDigitRanges.count
    while lo < hi {
        let mid = (lo + hi) / 2
        let r = decimalDigitRanges[mid]
        if v < r.lowerBound { hi = mid } else if v > r.upperBound { lo = mid + 1 } else { return true }
    }
    return false
}

private let decimalDigitRanges: [ClosedRange<UInt32>] = [
    0x30...0x39, 0x660...0x669, 0x6F0...0x6F9, 0x7C0...0x7C9, 0x966...0x96F, 0x9E6...0x9EF,
    0xA66...0xA6F, 0xAE6...0xAEF, 0xB66...0xB6F, 0xBE6...0xBEF, 0xC66...0xC6F, 0xCE6...0xCEF,
    0xD66...0xD6F, 0xDE6...0xDEF, 0xE50...0xE59, 0xED0...0xED9, 0xF20...0xF29, 0x1040...0x1049,
    0x1090...0x1099, 0x17E0...0x17E9, 0x1810...0x1819, 0x1946...0x194F, 0x19D0...0x19D9,
    0x1A80...0x1A89, 0x1A90...0x1A99, 0x1B50...0x1B59, 0x1BB0...0x1BB9, 0x1C40...0x1C49,
    0x1C50...0x1C59, 0xA620...0xA629, 0xA8D0...0xA8D9, 0xA900...0xA909, 0xA9D0...0xA9D9,
    0xA9F0...0xA9F9, 0xAA50...0xAA59, 0xABF0...0xABF9, 0xFF10...0xFF19, 0x104A0...0x104A9,
    0x10D30...0x10D39, 0x10D40...0x10D49, 0x11066...0x1106F, 0x110F0...0x110F9, 0x11136...0x1113F,
    0x111D0...0x111D9, 0x112F0...0x112F9, 0x11450...0x11459, 0x114D0...0x114D9, 0x11650...0x11659,
    0x116C0...0x116C9, 0x116D0...0x116E3, 0x11730...0x11739, 0x118E0...0x118E9, 0x11950...0x11959,
    0x11BF0...0x11BF9, 0x11C50...0x11C59, 0x11D50...0x11D59, 0x11DA0...0x11DA9, 0x11F50...0x11F59,
    0x16130...0x16139, 0x16A60...0x16A69, 0x16AC0...0x16AC9, 0x16B50...0x16B59, 0x16D70...0x16D79,
    0x1CCF0...0x1CCF9, 0x1D7CE...0x1D7FF, 0x1E140...0x1E149, 0x1E2F0...0x1E2F9, 0x1E4F0...0x1E4F9,
    0x1E5F1...0x1E5FA, 0x1E950...0x1E959, 0x1FBF0...0x1FBF9,
]

// ================================================================ the token-class scanners

/// A scanner matches its pattern anchored at `pos` (as `TOKEN_RE.match(stripped,
/// pos)` does) and returns the end of the match, or nil.
typealias Scanner = @Sendable (_ s: [Unicode.Scalar], _ pos: Int) -> Int?

private func isASCIIWord(_ c: Unicode.Scalar) -> Bool {
    ("A"..."Z").contains(c) || ("a"..."z").contains(c) || ("0"..."9").contains(c) || c == "_"
}

private func isASCIIHex(_ c: Unicode.Scalar) -> Bool {
    ("0"..."9").contains(c) || ("a"..."f").contains(c) || ("A"..."F").contains(c)
}

/// Each pattern grammar/vocabulary.json declares, by its exact text, with the
/// scanner that implements it. None of these patterns can backtrack into a
/// different match than a single greedy pass finds, so each is one pass.
private let scanners: [(pattern: String, scan: Scanner)] = [
    // COMMENT — `#` to the end of the line (a line never holds "\n").
    (#"#[^\n]*"#, { s, pos in
        guard s[pos] == "#" else { return nil }
        var i = pos + 1
        while i < s.count, s[i] != "\n" { i += 1 }
        return i
    }),
    // FINGERPRINT — `@` and exactly six ASCII hex digits; nothing about what follows.
    (#"@[0-9a-fA-F]{6}"#, { s, pos in
        guard s[pos] == "@", pos + 6 < s.count else { return nil }
        for i in pos + 1...pos + 6 where !isASCIIHex(s[i]) { return nil }
        return pos + 7
    }),
    // NUMBER — Unicode digits, then an optional `.` that counts only if a digit follows.
    (#"\d+(\.\d+)?"#, { s, pos in
        var i = pos
        while i < s.count, isPythonDigit(s[i]) { i += 1 }
        guard i > pos else { return nil }
        if i + 1 < s.count, s[i] == ".", isPythonDigit(s[i + 1]) {
            i += 2
            while i < s.count, isPythonDigit(s[i]) { i += 1 }
        }
        return i
    }),
    // STRING — a backslash always pairs with the code point after it (`\\.`), so
    // the first unpaired `"` closes the string; a backslash with nothing after
    // it, or reaching the end with no close, is no match.
    (#""(?:\\.|[^"\\])*""#, { s, pos in
        guard s[pos] == "\"" else { return nil }
        var i = pos + 1
        while i < s.count {
            let c = s[i]
            if c == "\"" { return i + 1 }
            if c == "\\" {
                guard i + 1 < s.count, s[i + 1] != "\n" else { return nil }
                i += 2
            } else {
                i += 1
            }
        }
        return nil
    }),
    // NAME — ASCII identifier, hyphen-joined segments; a `-` not followed by a
    // word character is left for OP.
    (#"[A-Za-z_][A-Za-z0-9_]*(-[A-Za-z0-9_]+)*"#, { s, pos in
        let c = s[pos]
        guard ("A"..."Z").contains(c) || ("a"..."z").contains(c) || c == "_" else { return nil }
        var i = pos + 1
        while i < s.count, isASCIIWord(s[i]) { i += 1 }
        while i + 1 < s.count, s[i] == "-", isASCIIWord(s[i + 1]) {
            i += 2
            while i < s.count, isASCIIWord(s[i]) { i += 1 }
        }
        return i
    }),
    // OP — the two-character operators first, in the pattern's order.
    (#"->|==|!=|<=|>=|[+\-*/=<>().,;:\[\]{}@]"#, { s, pos in
        if pos + 1 < s.count {
            let pair = (s[pos], s[pos + 1])
            if pair == ("-", ">") || pair == ("=", "=") || pair == ("!", "=") || pair == ("<", "=") || pair == (">", "=") {
                return pos + 2
            }
        }
        return "+-*/=<>().,;:[]{}@".unicodeScalars.contains(s[pos]) ? pos + 1 : nil
    }),
    // WS — spaces and tabs only; any other whitespace inside a line is a stray character.
    (#"[ \t]+"#, { s, pos in
        var i = pos
        while i < s.count, s[i] == " " || s[i] == "\t" { i += 1 }
        return i > pos ? i : nil
    }),
]

// ================================================================ compiled tables

/// What js/lexer.mjs's ensureCompiled() builds, plus the tables it derives
/// lazily — built together here, from one vocabulary, and rebuilt if the
/// vocabulary is replaced.
struct LexerTables: Sendable {
    let groups: [(name: String, scan: Scanner)]
    let keywords: Set<CodePoints>
    let effectKinds: TextTable<String>
    let builtinNames: Set<CodePoints>
    let builtinsArity: TextTable<Int>
    let fieldNameKinds: Set<CodePoints>

    init(_ vocab: GrammarJSON) throws(GrammarDataError) {
        var groups: [(name: String, scan: Scanner)] = []
        for spec in vocab["token_classes"]?.array ?? [] {  // JSON array order is load-bearing
            guard let name = spec["name"]?.string, let pattern = spec["pattern"]?.string else {
                throw GrammarDataError("grammar-data-missing", "a token class has no name or pattern",
                                       "reinstall planes, or regenerate with python3 grammar_gen.py")
            }
            guard let scan = scanners.first(where: { sameText($0.pattern, pattern) })?.scan else {
                throw GrammarDataError(
                    "grammar-data-missing",
                    "token class \(name) has pattern \(GrammarJSON.string(pattern).jsonText), which the Swift lexer has no scanner for",
                    "add a scanner for it to swift/Sources/Planes/Lexer.swift, matching Python re's semantics")
            }
            groups.append((name, scan))
        }
        self.groups = groups
        keywords = Set((vocab["keywords"]?.array ?? []).compactMap { $0["word"]?.string }.map(CodePoints.init))
        var kinds = TextTable<String>()
        for e in vocab["effect_kinds"]?.array ?? [] {
            if let k = e["kind"]?.string, let b = e["boundary"]?.string { kinds[k] = b }
        }
        effectKinds = kinds
        let builtins = vocab["builtins"]?.array ?? []
        builtinNames = Set(builtins.compactMap { $0["name"]?.string }.map(CodePoints.init))
        var arity = TextTable<Int>()
        for b in builtins {
            if let n = b["name"]?.string { arity[n] = b["arity"]?.int ?? 1 }
        }
        builtinsArity = arity
        fieldNameKinds = Set((vocab["field_name_token_kinds"]?.array ?? []).compactMap(\.string).map(CodePoints.init))
    }
}

private final class LexerCache: @unchecked Sendable {
    let lock = NSLock()
    var generation = -1
    var tables: LexerTables?
}

private let cache = LexerCache()

// Built lazily, on first use, and again whenever setVocabulary replaces the
// vocabulary it was built from.
func ensureCompiled() throws(GrammarDataError) -> LexerTables {
    let (vocab, generation) = try vocabularyAndGeneration()
    cache.lock.lock()
    defer { cache.lock.unlock() }
    if let t = cache.tables, cache.generation == generation { return t }
    let t = try LexerTables(vocab)
    cache.tables = t
    cache.generation = generation
    return t
}

/// The reserved words.
public func keywords() throws(GrammarDataError) -> Set<CodePoints> {
    try ensureCompiled().keywords
}

// The closed vocabulary of effect kinds, kind -> boundary. lexer.py holds this
// (EFFECT_KINDS) so the parser can validate a rule's kind at parse time.
public func effectKinds() throws(GrammarDataError) -> TextTable<String> {
    try ensureCompiled().effectKinds
}

// Builtin names, and builtin name -> arity (default 1). parser.py reads these
// from _VOCAB: BUILTIN_NAMES so a bare `count of xs` is a call, and the arity
// for the parse-time name table.
public func builtinNames() throws(GrammarDataError) -> Set<CodePoints> {
    try ensureCompiled().builtinNames
}

public func builtinsArity() throws(GrammarDataError) -> TextTable<Int> {
    try ensureCompiled().builtinsArity
}

// The token kinds that may name a record field or a with/when-pattern entry —
// grammar/vocabulary.json's field_name_token_kinds.
public func fieldNameKinds() throws(GrammarDataError) -> Set<CodePoints> {
    try ensureCompiled().fieldNameKinds
}

// ================================================================ tokenize

private func text(_ s: ArraySlice<Unicode.Scalar>) -> String {
    String(String.UnicodeScalarView(s))
}

// `raw` is a STRING token's content between the delimiting quotes. Resolves the
// four escapes; on an unrecognized escape, raises PlanesSyntaxError with the
// line, exactly as lexer.py's _resolve_string_escapes wraps planes_text's bare
// error with source position.
private func resolveWithLine(_ raw: String, _ lineno: Int) throws(PlanesSyntaxError) -> String {
    do {
        return try resolveStringEscapes(raw)
    } catch {
        let nxt = error.badCharacter
        throw PlanesSyntaxError(
            "line \(lineno): unrecognized escape '\\\(nxt)' in a " +
                "string literal\n" +
                "  the four recognized escapes are " +
                #"\" \\ \n \t -- for any other character, write the "# +
                "character itself")
    }
}

// Tokenize a source string. A faithful port of lexer.py's tokenize().
public func tokenize(_ src: String) throws -> [Token] {
    let tables = try ensureCompiled()
    var out: [Token] = []
    var indents = [0]
    // src.split("\n"): only U+000A separates lines, and empty pieces are kept.
    let lines = Array(src.unicodeScalars).split(separator: "\n", omittingEmptySubsequences: false)
    var lineno = 0
    for (li, raw) in lines.enumerated() {
        lineno = li + 1
        // raw.strip(), and raw.lstrip()'s length for the indent — Python's
        // whitespace, counted in code points.
        guard let first = raw.firstIndex(where: { !isPythonSpace($0) }) else { continue }
        let last = raw.lastIndex(where: { !isPythonSpace($0) })!
        let stripped = Array(raw[first...last])
        if stripped[0] == "#" { continue }
        let indent = first - raw.startIndex
        if indent > indents[indents.count - 1] {
            indents.append(indent)
            out.append(Token("BEGIN", "", lineno))
        }
        while indent < indents[indents.count - 1] {
            indents.removeLast()
            out.append(Token("END", "", lineno))
        }
        var pos = 0
        let n = stripped.count
        while pos < n {
            var matched: (kind: String, end: Int)?
            for g in tables.groups {
                if let end = g.scan(stripped, pos) {
                    matched = (g.name, end)
                    break
                }
            }
            guard let (groupKind, end) = matched else {
                if stripped[pos] == "\"" {
                    if stripped[n - 1] == "\"" {
                        throw PlanesSyntaxError(
                            "line \(lineno): unterminated string literal -- a " +
                                "backslash right before the closing quote escapes " +
                                #"that quote (\") instead of ending the string"# + "\n" +
                                "  the four recognized escapes are " +
                                #"\" \\ \n \t -- write \\ for a literal "# +
                                "trailing backslash")
                    }
                    throw PlanesSyntaxError(
                        "line \(lineno): unterminated string literal -- no " +
                            "closing quote found before the end of the line\n" +
                            "  add the closing quote; a Planes string cannot span " +
                            "multiple lines, so a long one has to be joined with " +
                            "+ across lines")
                }
                pos += 1
                continue
            }
            var kind = groupKind
            var val = text(stripped[pos..<end])
            if sameText(kind, "WS") || sameText(kind, "COMMENT") {
                pos = end
                continue
            }
            if sameText(kind, "NAME"), tables.keywords.contains(CodePoints(val)) {
                kind = val.uppercased()
            } else if sameText(kind, "STRING") {
                let resolved = try resolveWithLine(text(stripped[pos + 1..<end - 1]), lineno)
                val = "\"" + resolved + "\""
            }
            out.append(Token(kind, val, lineno))
            pos = end
        }
        out.append(Token("EOL", "", lineno))
    }
    while indents.count > 1 {
        indents.removeLast()
        out.append(Token("END", "", lineno))
    }
    out.append(Token("EOF", "", lineno + 1))
    return out
}
