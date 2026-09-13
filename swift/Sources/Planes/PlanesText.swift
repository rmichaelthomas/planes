// PlanesText.swift — Planes text: STRING literal escapes, their inverse, and
// code-point semantics.
//
// The Swift counterpart of planes_text.py and js/planes_text.mjs.
//
// Planes text is a sequence of Unicode CODE POINTS (v9.0 §105). Swift's
// `String` is a sequence of grapheme clusters, and its `==`, hashing and `<`
// use canonical equivalence: "café" with a precomposed é is `==` to "café"
// with a combining accent, and "👨‍👩‍👧" is one `Character` but five code points.
// Python compares and counts code points. So every Planes operation that
// counts, iterates, compares, orders or keys text goes through the
// unicode-scalar view — never through `String` `==`, `Character`, or a
// `Dictionary<String, _>` whose keys could differ only by normalisation.
// `CodePoints` below is the key type for that.

/// The four escapes a STRING literal may contain (v9.0 §105).
public let stringEscapes: [Unicode.Scalar: Unicode.Scalar] = [
    "\"": "\"", "\\": "\\", "n": "\n", "t": "\t",
]

/// The inverse of `stringEscapes`, for any path that prints a value back as
/// Planes source.
public let stringUnescape: [Unicode.Scalar: String] = {
    var inverse: [Unicode.Scalar: String] = [:]
    for (k, v) in stringEscapes { inverse[v] = "\\" + String(k) }
    return inverse
}()

/// A backslash not followed by one of the four legal escapes. Carries the
/// offending character; the lexer adds source position, as lexer.py does with
/// planes_text.py's bare `ValueError(nxt)`.
public struct StringEscapeError: Error, Equatable {
    public let badCharacter: String
}

/// `raw` is a STRING token's content between the delimiting quotes, exactly as
/// the STRING pattern matched it. The pattern only ever matches a backslash
/// paired with a following character, so a backslash is never last.
public func resolveStringEscapes(_ raw: String) throws(StringEscapeError) -> String {
    let cps = Array(raw.unicodeScalars)
    var out = String.UnicodeScalarView()
    var i = 0
    while i < cps.count {
        let c = cps[i]
        if c == "\\" {
            let next = i + 1 < cps.count ? cps[i + 1] : nil
            guard let next, let resolved = stringEscapes[next] else {
                throw StringEscapeError(badCharacter: next.map { String($0) } ?? "")
            }
            out.append(resolved)
            i += 2
        } else {
            out.append(c)
            i += 1
        }
    }
    return String(out)
}

/// `s`, re-escaped as the content of a Planes STRING literal.
public func escapeStringLiteral(_ s: String) -> String {
    var out = ""
    for c in s.unicodeScalars {
        if let escaped = stringUnescape[c] { out += escaped } else { out.unicodeScalars.append(c) }
    }
    return out
}

/// The code points of `s`, one string each — what `for each … in <text>` walks.
public func codePoints(_ s: String) -> [String] {
    s.unicodeScalars.map { String($0) }
}

/// The number of code points in `s` — Planes text length.
public func codePointLength(_ s: String) -> Int {
    s.unicodeScalars.count
}

/// Text as Python sees it: equal, hashed and ordered by code point. Use it as
/// the key of any dictionary or set holding Planes text, and for any
/// comparison or sort whose result must match the reference.
public struct CodePoints: Hashable, Comparable, Sendable, CustomStringConvertible {
    public let scalars: [UInt32]
    public init(_ s: String) { scalars = s.unicodeScalars.map(\.value) }
    public var string: String {
        String(String.UnicodeScalarView(scalars.compactMap(Unicode.Scalar.init)))
    }
    public var description: String { string }
    public static func < (a: CodePoints, b: CodePoints) -> Bool {
        a.scalars.lexicographicallyPrecedes(b.scalars)
    }
}

/// Code-point equality, for the places a `CodePoints` wrapper would be noise.
public func sameText(_ a: String, _ b: String) -> Bool {
    a.unicodeScalars.elementsEqual(b.unicodeScalars)
}
