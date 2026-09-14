// Rules.swift — the rule-plane checker, ported from rules.py.
//
// The Swift counterpart of js/rules.mjs, keeping its structure and names.
// Permits, exception resolution, and fingerprinting. EffectSurface.swift computes a
// program's effect surface; this only consumes it, through the public Surface
// queries (declared, originsOf). Matching is static and structural — a rule is
// never triggered; it is only ever checked against a surface computed without
// running anything.
//
// Checked against rules.py by agreement on pass/fail per rule WITH the message
// text (test_swift_rules.py): errors-that-name-the-fix is a language-level
// commitment, so a divergent message is a divergent implementation. rules.py is
// the specification. Names, subjects, kinds and targets are Planes text, so
// every comparison below is by code point (swift/README.md rule 1).

/// A rule this checker cannot evaluate: a named subject that does not resolve,
/// or resolves only in another file.
public struct RuleNotSupported: Error, CustomStringConvertible, Sendable {
    public let message: String
    public init(_ message: String) { self.message = message }
    public var description: String { message }
}

/// The rule set itself does not resolve — a compile error (v2.0 §32).
public struct RuleConflict: Error, CustomStringConvertible, Sendable {
    public let message: String
    public init(_ message: String) { self.message = message }
    public var description: String { message }
}

/// A stable, content-derived identity for a rule (v2.0 §29): subject, assertion,
/// kind, target — never name or line. sha256, truncated to six hex, byte-for-byte
/// what rules.py's fingerprint() produces.
public func fingerprint(_ rule: AST.Rule) -> String {
    let canonical = [rule.subject, rule.assertion, rule.effectKind, rule.target ?? ""].joined(separator: "\u{1F}")
    return String(sha256Hex(canonical).prefix(6))
}

/// A rule's condition, exactly as written, for echoing into a message.
public func condition(_ rule: AST.Rule) -> String {
    let verb = sameText(rule.assertion, "forbid") ? "may not" : "may"
    var text = "\(rule.subject) \(verb) \(rule.effectKind)"
    if let target = rule.target {
        text += " to \"\(escapeStringLiteral(target))\""
    }
    return text
}

/// One forbid rule matched against one effect — or, for the vacuous shape,
/// matched against nothing at all. Five shapes, told apart by `clearedBy` /
/// `narrowedBy` / `vacuous` / `contradictsRule`: a real violation (none set); a
/// violation narrowed by a more specific sibling forbid; a prohibition a permit
/// cleared (`isViolation` false, still rendered); a named-subject rule that
/// matched nothing (`vacuous`, no effect); and a contradiction (B3, Track 0 #5)
/// — both rules of a declared `contradicts` pair matched at least one effect.
/// `isViolation` is true for a contradiction, same as a real violation.
public final class Violation: CustomStringConvertible {
    public let rule: AST.Rule
    public let effect: Effect?
    public let uncertain: Bool
    public let clearedBy: AST.Rule?
    public let narrowedBy: [AST.Rule]
    public let origins: [(name: String, file: String?)]
    public let vacuous: Bool
    /// Which of the three vacuous situations produced this entry: 1 = no effect
    /// of the rule's kind at all; 2 = effects of the kind exist but none derive
    /// from the subject; 3 = the subject derives an effect of the kind, but the
    /// rule's target excludes every one.
    public internal(set) var vacuousSituation: Int?
    /// The other rule of a declared `contradicts` pair, and the effect IT
    /// matched — set only for the contradiction shape (B3).
    public let contradictsRule: AST.Rule?
    public let contradictsEffect: Effect?

    public init(_ rule: AST.Rule, _ effect: Effect?, uncertain: Bool = false, clearedBy: AST.Rule? = nil,
                narrowedBy: [AST.Rule] = [], origins: [(name: String, file: String?)] = [], vacuous: Bool = false,
                contradictsRule: AST.Rule? = nil, contradictsEffect: Effect? = nil) {
        self.rule = rule
        self.effect = effect
        self.uncertain = uncertain
        self.clearedBy = clearedBy
        self.narrowedBy = narrowedBy
        self.origins = origins
        self.vacuous = vacuous
        self.contradictsRule = contradictsRule
        self.contradictsEffect = contradictsEffect
    }

    public var isViolation: Bool { contradictsRule != nil ? true : (clearedBy == nil && !vacuous) }

    /// The human-readable finding — a pure function of `asJSON()`'s own
    /// fields (B4): see `renderViolation` below, which this simply calls.
    /// Proves the structured form is complete: nothing here reads `rule`/
    /// `effect`/… directly any more, only what `asJSON()` already published.
    public func render() -> String { renderViolation(asJSON()) }

    private static func effectJSON(_ e: Effect) -> GrammarJSON {
        .object([("kind", .string(e.kind)), ("boundary", .string(e.boundary)),
                 ("target", .string(e.target)), ("line", .number(String(e.site))),
                 ("computed", .bool(e.computed)), ("declared", .bool(e.claimed))])
    }

    /// Every field `render()` reads, as data rather than prose (H1, B4). A
    /// `--json --rules` consumer gets the rule name, the rule's own
    /// subject/kind/target/assertion/`because`, the specific effect (kind,
    /// boundary, target, line, `computed`, `declared`) it matched or null
    /// for the vacuous shape, and the supersedes/permit outcome
    /// (`clearedBy`) or narrowing sibling (`narrowedBy`) — every structural
    /// fact `render()`'s prose is built from. `message` is `render()`'s own
    /// text, included verbatim beside the fields so a host can print
    /// exactly what text mode prints without re-deriving it (rules.py's
    /// `Violation.as_json` and js/rules.mjs's `Violation.asJson` must agree
    /// with this field for field).
    ///
    /// B4: `render()` is itself defined as `renderViolation(asJSON())` —
    /// every fact the rendered text states is one of these fields, never
    /// something only `render()` itself knows. Two fields exist only
    /// because of that proof: `subject` (`rule.subject` — used raw in the
    /// vacuous shapes' prose, never folded into `condition` the way the
    /// other three are) and the effect object's `computed`/`declared`
    /// (`Effect.computed`/`Effect.claimed` — the source of the text
    /// rendering's `" (computed)"` / `" (declared, not verified)"`
    /// suffixes, §4.2 of docs/surface-format-v2.md). `message` is computed
    /// from the fields built so far — before it is itself added to the
    /// object — so this is never circular: `renderViolation` never reads
    /// the `"message"` key.
    ///
    /// `contradiction` (B3) is null except for the contradiction shape,
    /// where it names both rules of the declared pair and one effect each
    /// matched — self-contained, so a consumer reading only this key gets
    /// both sides without also reading the top-level `rule`/`effect`.
    /// `origins` dedupes the same way `render()`'s derivation line does —
    /// by the formatted "name (file)" string, not by the raw pair.
    public func asJSON() -> GrammarJSON {
        var seenKeys = Set<String>()
        var pairs: [(key: String, name: String, file: String?)] = []
        for o in origins {
            let key = (o.file.map { !$0.isEmpty } == true) ? "\(o.name) (\(o.file!))" : o.name
            if seenKeys.insert(key).inserted { pairs.append((key, o.name, o.file)) }
        }
        let originsJSON = stableSorted(pairs) { pyLess($0.key, $1.key) }.map { p in
            GrammarJSON.object([("name", .string(p.name)), ("file", p.file.map { GrammarJSON.string($0) } ?? .null)])
        }
        let clearedByJSON: GrammarJSON = clearedBy.map { c in
            .object([("rule", .string(c.name)), ("line", .number(String(c.line)))])
        } ?? .null
        let narrowedByJSON: GrammarJSON = .array(narrowedBy.map { r in
            .object([("rule", .string(r.name)), ("line", .number(String(r.line)))])
        })
        let contradictionJSON: GrammarJSON = contradictsRule.map { other in
            GrammarJSON.object([
                ("rule", .string(rule.name)),
                ("effect", effect.map { Violation.effectJSON($0) } ?? .null),
                ("with_rule", .string(other.name)),
                ("with_effect", contradictsEffect.map { Violation.effectJSON($0) } ?? .null),
            ])
        } ?? .null
        let fields: [(String, GrammarJSON)] = [
            ("rule", .string(rule.name)),
            ("rule_line", .number(String(rule.line))),
            ("subject", .string(rule.subject)),
            ("assertion", .string(rule.assertion)),
            ("kind", .string(rule.effectKind)),
            ("target", rule.target.map { GrammarJSON.string($0) } ?? .null),
            ("condition", .string(condition(rule))),
            ("because", rule.annotation.map { GrammarJSON.string($0.text) } ?? .null),
            ("is_violation", .bool(isViolation)),
            ("vacuous", .bool(vacuous)),
            ("vacuous_situation", vacuousSituation.map { GrammarJSON.number(String($0)) } ?? .null),
            ("uncertain", .bool(uncertain)),
            ("effect", effect.map { Violation.effectJSON($0) } ?? .null),
            ("cleared_by", clearedByJSON),
            ("narrowed_by", narrowedByJSON),
            ("contradiction", contradictionJSON),
            ("origins", .array(originsJSON)),
        ]
        let message: GrammarJSON = .string(renderViolation(.object(fields)))
        return .object(fields + [("message", message)])
    }

    public var description: String { render() }
}

/// The text `Effect.description` renders, rebuilt from a `Violation.
/// effectJSON`-shaped object instead of an `Effect` value —
/// `renderViolation`'s equivalent of `String(describing: effect)`. Must
/// stay byte-for-byte what `Effect.description` (EffectSurface.swift)
/// produces; rules.py's `_render_effect_text` and js/rules.mjs's
/// `renderEffectText` must agree with this.
private func effectDescription(_ effect: GrammarJSON) -> String {
    let kind = effect["kind"]?.string ?? ""
    let target = effect["target"]?.string ?? ""
    if sameText(kind, "unknown") { return "unknown — \(target) declares no effects" }
    var t = target
    if effect["computed"] == .bool(true), t.unicodeScalars.last != ")" { t += " (computed)" }
    if effect["declared"] == .bool(true) { t += " (declared, not verified)" }
    return "\(kind) \(t)"
}

/// The contradiction shape's text (B3), rebuilt from `contradiction` (a
/// `Violation.asJSON()`-shaped object's own `"contradiction"` value) —
/// `renderViolation`'s delegate for this shape, mirroring how `render()`
/// always kept this on its own (formerly the method `renderContradiction`).
private func renderContradictionText(_ fields: GrammarJSON, _ contradiction: GrammarJSON) -> String {
    let aName = contradiction["rule"]?.string ?? ""
    let bName = contradiction["with_rule"]?.string ?? ""
    let ea = contradiction["effect"] ?? .null
    let eb = contradiction["with_effect"] ?? .null
    let line = "[\(aName)] contradicts [\(bName)]: both apply to this " +
        "program — [\(aName)] at line \(ea["line"]?.int ?? 0) (\(effectDescription(ea))), " +
        "[\(bName)] at line \(eb["line"]?.int ?? 0) (\(effectDescription(eb)))"
    guard let because = fields["because"]?.string else { return line }
    return line + "\n  [\(aName)] because \"\(because)\""
}

/// §2's three vacuous situations, one message each — never the word
/// "violated" (§3.1) — rebuilt from `fields` instead of an `AST.Rule`.
/// `renderViolation`'s delegate for this shape (formerly the method
/// `renderVacuous`).
private func renderVacuousText(_ fields: GrammarJSON) -> String {
    let name = fields["rule"]?.string ?? ""
    let line = fields["rule_line"]?.int ?? 0
    let subject = fields["subject"]?.string ?? ""
    let kind = fields["kind"]?.string ?? ""
    let target = fields["target"]?.string
    let situation = fields["vacuous_situation"]?.int

    let header: String
    let reason: String
    let fix: String

    if situation == 1 {
        header = "[\(name)] (line \(line)) checked nothing " +
            "— subject '\(subject)' resolves in this file, " +
            "but the program performs no '\(kind)' effect " +
            "at all"
        reason = "the rule is inert against this program as written"
        fix = "check the program still performs the effect you " +
            "expect, or remove the rule if it no longer applies"
    } else if situation == 3 {
        header = "[\(name)] (line \(line)) checked nothing " +
            "— subject '\(subject)' derives a " +
            "'\(kind)' effect, but the rule's target " +
            "excludes every one"
        reason = "'\(subject)' reaches this effect kind, but " +
            "never at \"\(escapeStringLiteral(target ?? "None"))\""
        fix = "check the target matches where '\(subject)' " +
            "actually goes, or remove the target to check every " +
            "'\(kind)' effect '\(subject)' reaches"
    } else {
        header = "[\(name)] (line \(line)) checked nothing " +
            "— subject '\(subject)' resolves in this file, " +
            "but no '\(kind)' effect derives from it"
        reason = "the program performs '\(kind)', but to a " +
            "target that does not derive from '\(subject)'"
        fix = "check the subject names the value you meant, or " +
            "write the rule against 'anything'"
    }

    return [header, "  \(reason)", "  \(fix)"].joined(separator: "\n")
}

/// `render()`'s text, computed purely from `Violation.asJSON()`'s own
/// fields (B4) — never from a `Violation`/`AST.Rule`/`Effect` value. This
/// is the proof B4 asks for: if the rendered text needed a fact this
/// function cannot read off `fields`, that fact was missing from the JSON,
/// and `Violation.render()` (which is defined as `renderViolation(asJSON()
/// )`) would be wrong, not just under-documented.
///
/// `fields` is exactly the `GrammarJSON` object `asJSON()` returns —
/// including, in the ordinary case, a `"message"` key already sitting in
/// it — but that key is never read here: this function is what PRODUCES it
/// (`asJSON()` calls this before adding `"message"` at all), and a caller
/// round-tripping `asJSON()`'s output through its `jsonText`/`GrammarJSON.
/// parse` (the CLI JSON path — `EffectSurfaceCommand.swift`'s `--rules`)
/// and passing the result back in gets the identical text regardless of
/// whether a stale `"message"` is sitting alongside the other fields —
/// every OTHER field determines the answer.
///
/// Four shapes, told apart the same way `Violation.render()` always was:
/// `contradiction` non-null, then `vacuous`, then `cleared_by` non-null,
/// else the ordinary violation. The first two delegate (mirroring how
/// `render()` always delegated to `renderContradiction`/`renderVacuous`);
/// the last two stay inline, as `render()`'s own body always had them.
public func renderViolation(_ fields: GrammarJSON) -> String {
    if let contradiction = fields["contradiction"], contradiction != .null {
        return renderContradictionText(fields, contradiction)
    }

    if fields["vacuous"] == .bool(true) {
        return renderVacuousText(fields)
    }

    if let clearedBy = fields["cleared_by"], clearedBy != .null {
        let clearedByRule = clearedBy["rule"]?.string ?? ""
        let clearedByLine = clearedBy["line"]?.int ?? 0
        return "[\(fields["rule"]?.string ?? "")] would have been violated at " +
            "line \(fields["effect"]?["line"]?.int ?? 0) — excepted by " +
            "[\(clearedByRule)] " +
            "(line \(clearedByLine))"
    }

    let effect = fields["effect"] ?? .null
    var lines = ["[\(fields["rule"]?.string ?? "")] violated at line \(effect["line"]?.int ?? 0)."]
    lines.append("  \(effectDescription(effect))")
    if fields["uncertain"] == .bool(true) {
        lines.append(
            "  target could not be pinned down statically — this " +
                "computed value may or may not be " +
                "\"\(escapeStringLiteral(fields["target"]?.string ?? "None"))\"")
    }
    lines.append("  rule declared at line \(fields["rule_line"]?.int ?? 0): " +
        "\(fields["condition"]?.string ?? "")")
    let narrowedBy = fields["narrowed_by"]?.array ?? []
    if !narrowedBy.isEmpty {
        let names = narrowedBy.map { r in
            "[\(r["rule"]?.string ?? "")] (line \(r["line"]?.int ?? 0))"
        }.joined(separator: ", ")
        lines.append("  narrowed here by \(names)")
    }
    let origins = fields["origins"]?.array ?? []
    if !origins.isEmpty {
        let parts = pySortedUnique(origins.map { o in
            let name = o["name"]?.string ?? ""
            if let f = o["file"]?.string, !f.isEmpty { return "\(name) (\(f))" }
            return name
        })
        lines.append("  derived from: \(parts.joined(separator: ", "))")
    }
    return lines.joined(separator: "\n")
}

/// check()'s return value: every Violation, plus the subjects it resolved — the
/// readback shapes_cli needs (P-Q20). rules.py subclasses `list`; this is a
/// collection of the violations with `resolvedSubjects` beside them.
public struct RuleResults: RandomAccessCollection {
    public let violations: [Violation]
    public let resolvedSubjects: [String]

    public init(_ violations: [Violation] = [], resolvedSubjects: [String] = []) {
        self.violations = violations
        self.resolvedSubjects = resolvedSubjects
    }

    public var startIndex: Int { violations.startIndex }
    public var endIndex: Int { violations.endIndex }
    public subscript(_ i: Int) -> Violation { violations[i] }
}

/// Finds `needle` (unicode scalars) in `hay` at or after `from`, code-point
/// exact — the scalar-array counterpart of `String.range(of:)`, which this
/// file avoids for the reason `PlanesText.swift` states: canonical
/// equivalence would let a composed character match a decomposed one.
private func findScalars(_ needle: [Unicode.Scalar], in hay: [Unicode.Scalar], from: Int = 0) -> Int? {
    if needle.isEmpty { return from <= hay.count ? from : nil }
    guard from + needle.count <= hay.count else { return nil }
    var i = from
    while i + needle.count <= hay.count {
        if hay[i..<(i + needle.count)].elementsEqual(needle) { return i }
        i += 1
    }
    return nil
}

/// Folds only ASCII A-Z to a-z; every other scalar is left exactly as
/// written (B2 follow-up). Scheme and host are DNS-shaped, and DNS
/// case-insensitivity is ASCII-only -- a full Unicode fold (`String.
/// lowercased()`) can map a scalar context-dependently (a final Greek
/// sigma U+03A3 becomes U+03C2 under some case-folding rules, U+03C3
/// under others), and there is no guarantee another host's Unicode
/// tables agree with this one's on the exact mapping. That would
/// silently break the byte-for-byte agreement the three hosts promise.
/// Used only where B2 asks for case-insensitive comparison (scheme,
/// host); a rule's path stays case-sensitive and untouched by this
/// function. rules.py's and js/rules.mjs's identically-named function
/// must agree with this one.
private func asciiLower(_ s: ArraySlice<Unicode.Scalar>) -> [Unicode.Scalar] {
    s.map { $0.value >= 0x41 && $0.value <= 0x5A ? Unicode.Scalar($0.value + 0x20)! : $0 }
}
private func asciiLower(_ s: [Unicode.Scalar]) -> [Unicode.Scalar] { asciiLower(s[...]) }

/// Is `s` a legal URL scheme (`ALPHA *( ALPHA / DIGIT / "+" / "-" / "." )`,
/// RFC 3986 §3.1)? ASCII-only by construction, so a plain ASCII check.
private func isSchemeScalars(_ s: ArraySlice<Unicode.Scalar>) -> Bool {
    guard let first = s.first else { return false }
    func isAsciiLetter(_ c: Unicode.Scalar) -> Bool {
        (c.value >= 0x41 && c.value <= 0x5A) || (c.value >= 0x61 && c.value <= 0x7A)
    }
    guard isAsciiLetter(first) else { return false }
    for ch in s.dropFirst() {
        if isAsciiLetter(ch) || (ch.value >= 0x30 && ch.value <= 0x39) || ch == "+" || ch == "-" || ch == "." {
            continue
        }
        return false
    }
    return true
}

/// A URL-shaped target's pieces, as views into the target's own storage.
/// Every scope comparison parses both of its targets; building `String`s and
/// scalar arrays for each piece made a 50-rule check two orders of magnitude
/// slower than exact matching was (Koncord's pin to the Sprint B tag measured
/// it). Views copy nothing, so a parse costs one walk over the target.
///
/// The views are UTF-8, not Unicode scalars, because walking bytes is far
/// cheaper and gives the same answers here: every delimiter is ASCII, so a
/// byte split falls on scalar boundaries; two texts are code-point equal
/// exactly when their UTF-8 is byte equal; one is a code-point prefix of the
/// other exactly when it is a byte prefix; and folding ASCII A-Z bytes folds
/// exactly the scalars `asciiLower` folds, since no byte of a multi-byte
/// scalar is below 0x80.
struct URLPieces {
    typealias Bytes = Substring.UTF8View
    let scheme: Bytes
    let host: Bytes
    let path: Bytes
    let query: Bytes?
    let fragment: Bytes?
}

private let colon = UInt8(ascii: ":"), slash = UInt8(ascii: "/")
private let question = UInt8(ascii: "?"), hash = UInt8(ascii: "#")

/// `parseURLTarget`'s split, without copying (see `URLPieces`).
func urlPieces(_ target: String) -> URLPieces? {
    let all = target.utf8[...]
    var sep: URLPieces.Bytes.Index?
    var i = all.startIndex
    while i < all.endIndex {
        if all[i] == colon {
            let j = all.index(after: i)
            if j < all.endIndex, all[j] == slash {
                let k = all.index(after: j)
                if k < all.endIndex, all[k] == slash {
                    sep = i
                    break
                }
            }
        }
        i = all.index(after: i)
    }
    guard let sep, sep > all.startIndex, isSchemeBytes(all[..<sep]) else { return nil }
    let rest = all[all.index(sep, offsetBy: 3)...]

    let hostEnd = rest.firstIndex { $0 == slash || $0 == question || $0 == hash } ?? rest.endIndex
    let tail = rest[hostEnd...]
    let pathEnd = tail.firstIndex { $0 == question || $0 == hash } ?? tail.endIndex
    let remainder = tail[pathEnd...]

    var query: URLPieces.Bytes?
    var fragment: URLPieces.Bytes?
    if remainder.first == hash {
        fragment = remainder
    } else if remainder.first == question {
        if let hashAt = remainder.firstIndex(of: hash) {
            query = remainder[..<hashAt]
            fragment = remainder[hashAt...]
        } else {
            query = remainder
        }
    }
    return URLPieces(scheme: all[..<sep], host: rest[..<hostEnd], path: tail[..<pathEnd],
                     query: query, fragment: fragment)
}

/// Splits `target` into (scheme, host, path, query, fragment) if it has the
/// shape `scheme://host[:port][/path][?query][#fragment]` (B2); `nil`
/// otherwise — a file path, a `queue:send`-style name, or console text, none
/// of which are addresses this matches by host and path (B2 keeps those on
/// today's exact-string matching, unchanged).
///
/// `query` and `fragment` carry their leading `?`/`#` when present. No
/// percent-decoding, no Unicode normalisation, no default-port folding:
/// every piece is exactly the substring as written (B2). rules.py's
/// `_parse_url_target` and js/rules.mjs's `parseUrlTarget` must agree with
/// this.
func parseURLTarget(_ target: String) -> (scheme: String, host: String, path: String, query: String?, fragment: String?)? {
    guard let p = urlPieces(target) else { return nil }
    func text(_ s: URLPieces.Bytes) -> String { String(Substring(s)) }
    return (text(p.scheme), text(p.host), text(p.path), p.query.map(text), p.fragment.map(text))
}

/// Does `rulePath` cover `effectPath` at a "/" boundary (B2)? An empty path
/// or "/" in the rule covers every path on the host. Otherwise `rulePath`
/// must be a prefix of `effectPath`, and either they're equal, `rulePath`
/// itself already ends in "/" (everything under it is covered), or the next
/// character of `effectPath` past the prefix is "/". Compared code-point
/// exact — no percent-decoding, no Unicode normalisation.
func pathCovers(_ rulePath: String, _ effectPath: String) -> Bool {
    pathCovers(rulePath.utf8[...], effectPath.utf8[...])
}

private func pathCovers(_ rule: URLPieces.Bytes, _ effect: URLPieces.Bytes) -> Bool {
    if rule.isEmpty || (rule.count == 1 && rule.first == slash) { return true }
    guard effect.starts(with: rule) else { return false }
    if rule.last == slash { return true }
    let after = effect.index(effect.startIndex, offsetBy: rule.count)
    return after == effect.endIndex || effect[after] == slash
}

/// Case-insensitive for ASCII letters only (`asciiLower`), code-point exact
/// otherwise — never `String`'s `==`, which is canonical equivalence: a
/// composed and a decomposed host must NOT be treated as the same host.
private func sameASCIIFolded(_ a: URLPieces.Bytes, _ b: URLPieces.Bytes) -> Bool {
    a.count == b.count && a.elementsEqual(b) { foldASCII($0) == foldASCII($1) }
}

private func foldASCII(_ b: UInt8) -> UInt8 { b >= 0x41 && b <= 0x5A ? b + 0x20 : b }

/// `isSchemeScalars` over UTF-8: a non-ASCII scalar's bytes are all 0x80 or
/// above, so they fail the same ASCII test the scalar would.
private func isSchemeBytes(_ s: URLPieces.Bytes) -> Bool {
    guard let first = s.first else { return false }
    func isLetter(_ c: UInt8) -> Bool { (c >= 0x41 && c <= 0x5A) || (c >= 0x61 && c <= 0x7A) }
    guard isLetter(first) else { return false }
    return s.dropFirst().allSatisfy { isLetter($0) || ($0 >= 0x30 && $0 <= 0x39) || $0 == 0x2B || $0 == 0x2D || $0 == 0x2E }
}

private func urlCovers(_ r: URLPieces, _ e: URLPieces) -> Bool {
    sameASCIIFolded(r.scheme, e.scheme) && sameASCIIFolded(r.host, e.host) && pathCovers(r.path, e.path)
}

/// Does the URL-shaped `ruleTarget` cover the URL-shaped `effectTarget`
/// (B2)? Same scheme and host, compared case-insensitively; port is part of
/// the host and compared exactly as written -- no default-port folding, so
/// `https://x` and `https://x:443` differ. The effect's own query and
/// fragment are ignored entirely -- only its path is compared, against the
/// rule's path, by `pathCovers`.
func urlCovers(_ ruleTarget: String, _ effectTarget: String) -> Bool {
    guard let r = urlPieces(ruleTarget), let e = urlPieces(effectTarget) else { return false }
    return urlCovers(r, e)
}

/// Does every address `narrow` (a target string, or `nil`) ranges over also
/// fall inside `wide`'s range (B2)? `nil` is the top of the lattice -- every
/// target of the kind. Identical strings are always the same scope. A
/// URL-shaped pair compares by `urlCovers`; anything else -- a target that
/// isn't URL-shaped, or a URL paired with a non-URL -- only ever covers its
/// own exact string, exactly as before B2.
func scopeCovers(_ wide: String?, _ narrow: String?) -> Bool {
    guard let wide else { return true }
    guard let narrow else { return false }
    if sameText(wide, narrow) { return true }
    guard let w = urlPieces(wide), let n = urlPieces(narrow) else { return false }
    return urlCovers(w, n)
}

/// Do `a` and `b` (two rule targets, or `nil`) range over exactly the same
/// addresses (B2)? Equal by mutual coverage rather than `==`, so
/// `"https://x"` and `"https://x/"` -- two spellings of "every path on x"
/// -- are the same scope even though the strings differ.
func sameScope(_ a: String?, _ b: String?) -> Bool {
    sameScope(a, a.flatMap(urlPieces), b, b.flatMap(urlPieces))
}

/// A rule target parsed once for a pairwise pass: its pieces (`nil` when the
/// target is `nil` or isn't URL-shaped) and its ASCII-folded
/// `scheme://host`. Two URL-shaped targets can only share a scope when those
/// origins are equal, so most pairs are told apart by one array compare.
private struct ParsedScope {
    let target: String?
    let pieces: URLPieces?
    let origin: [UInt8]

    init(_ target: String?) {
        self.target = target
        pieces = target.flatMap(urlPieces)
        origin = pieces.map { $0.scheme.map(foldASCII) + Array("://".utf8) + $0.host.map(foldASCII) } ?? []
    }
}

private func sameScope(_ a: ParsedScope, _ b: ParsedScope) -> Bool {
    if a.pieces != nil, b.pieces != nil, a.origin != b.origin { return false }
    return sameScope(a.target, a.pieces, b.target, b.pieces)
}

/// `sameScope` for targets whose pieces are already parsed (`nil` when the
/// target is `nil` or isn't URL-shaped).
private func sameScope(_ a: String?, _ pa: URLPieces?, _ b: String?, _ pb: URLPieces?) -> Bool {
    guard let a, let b else { return a == nil && b == nil }
    if sameText(a, b) { return true }
    guard let pa, let pb else { return false }
    return urlCovers(pa, pb) && urlCovers(pb, pa)
}

/// The set of effect kinds this rule's declared kind matches against (B1,
/// Sprint B, Track 0 #10). Must agree with rules.py's `_covered_kinds` and
/// js/rules.mjs's `coveredKinds`. Only a FORBID on "ask" widens (forbidding
/// ask also forbids send, the same network boundary's outbound half); a
/// PERMIT never widens ("may ask to X" permits only ask, "may send to X"
/// permits only send); a forbid on any other kind, including "send" itself,
/// covers only itself. Effect-kind words are always one of the closed,
/// ASCII, parser-validated vocabulary, never arbitrary program text, so
/// plain `Set<String>` equality (not `sameText`'s scalar-by-scalar compare)
/// is exact here. Orthogonal to B2's scope generalisation above: this is
/// about which KINDS a rule's declared kind stands for, `scopeCovers`/
/// `sameScope` are about which ADDRESSES its target stands for. `narrows`
/// and `checkConflicts` combine both, and this is `public`, the same as
/// `narrows`, for a host that wants to introspect a rule's true coverage.
public func coveredKinds(_ rule: AST.Rule) -> Set<String> {
    if sameText(rule.assertion, "forbid") && sameText(rule.effectKind, "ask") {
        return ["ask", "send"]
    }
    return [rule.effectKind]
}

/// Does rule `b` cover a strict subset of what rule `a` ranges over? (v2.0
/// §30; re-proven for host/path covering at B2, and for kind covering at
/// B1.) Two dimensions, both required, never assertion:
///
/// - KIND: `a`'s and `b`'s covered kinds (`coveredKinds`, B1) must overlap.
///   Comparable within the same literal kind (as before B1 -- `coveredKinds`
///   always includes a rule's own kind); also comparable across ask/send
///   when a forbid's widened coverage reaches a narrower rule's kind -- a
///   `may send to X/public` permit can narrow a bare `may not ask` forbid
///   the same way a `may ask to X/public` permit already did.
/// - SCOPE: `a`'s target must cover `b`'s (B2's `scopeCovers`) and the two
///   must not be the SAME scope -- the pre-B2 case (`a` has no target, `b`
///   does) is one instance; a rule whose covered address set is strictly
///   inside another's target now is too.
///
/// Two rules with overlapping kinds and the same scope are equally
/// specific -- neither narrows the other; that pair is `checkConflicts`'s
/// job.
public func narrows(_ b: AST.Rule, _ a: AST.Rule) -> Bool {
    if sameText(a.name, b.name) { return false }
    if coveredKinds(a).isDisjoint(with: coveredKinds(b)) { return false }
    return scopeCovers(a.target, b.target) && !scopeCovers(b.target, a.target)
}

/// (matched, uncertain). No target on the rule means every target of the
/// kind -- always a certain match. Otherwise, for a computed effect target:
/// a possible match unless its known chunks rule the rule's target out
/// (v37.0 §513, B2's `patternExcludes`). For a literal effect target: when
/// both it and the rule's target are URL-shaped, the rule's target must
/// COVER the effect's -- the same address, or anything under it (B2), the
/// effect's own query and fragment ignored; otherwise (a file path, a
/// `queue:send`-style name, console text) an exact string match, exactly as
/// before B2.
func targetMatches(_ rule: AST.Rule, _ effect: Effect) -> (Bool, Bool) {
    targetMatches(rule.target, rule.target.flatMap(urlPieces), effect,
                  effect.computed ? nil : urlPieces(effect.target))
}

/// `targetMatches` with both targets' pieces already parsed (`nil` when not
/// URL-shaped), so `check` parses each rule and each effect once rather than
/// once per rule-effect pair.
private func targetMatches(_ target: String?, _ targetPieces: URLPieces?,
                           _ effect: Effect, _ effectPieces: URLPieces?) -> (Bool, Bool) {
    guard let target else { return (true, false) }
    if effect.computed {
        if patternExcludes(target, effect.target) { return (false, false) }
        return (true, true)
    }
    if let targetPieces, let effectPieces {
        return (urlCovers(targetPieces, effectPieces), false)
    }
    return (sameText(effect.target, target), false)
}

/// rules.py's `_pattern_excludes`, which this must agree with: can a
/// computed target provably never be COVERED by the rule's target (B2;
/// originally "never equal", v37.0 §513)? When the rule's target isn't
/// URL-shaped, covering is exact-string equality, unchanged since v37.0
/// (`exactPatternExcludes`). When it is, B2 re-proves the guard for
/// host/path covering (`urlPatternExcludes`). A target with no hole, or a
/// foreign's "(destination not stated)", excludes nothing either way.
func patternExcludes(_ ruleTarget: String, _ effectTarget: String) -> Bool {
    let hole = Array("{...}".unicodeScalars)
    let effect = Array(effectTarget.unicodeScalars)
    let noDestination = Array(" (destination not stated)".unicodeScalars)
    if effect.count >= noDestination.count && effect.suffix(noDestination.count).elementsEqual(noDestination) {
        return false
    }
    guard findScalars(hole, in: effect) != nil else { return false }

    guard let ruleURL = parseURLTarget(ruleTarget) else {
        return exactPatternExcludes(ruleTarget, effectTarget)
    }
    return urlPatternExcludes(ruleURL.scheme, ruleURL.host, ruleURL.path, effectTarget)
}

/// The v37.0 §513 algorithm, unchanged: can this pattern never equal
/// `ruleTarget` as a flat string? Its known chunks must appear in it in
/// order — the first anchored to the start, the last to the end, unless the
/// pattern opens or closes with a hole — with a hole free to stand for any
/// text, including none. Still what governs a rule target B2 leaves on
/// exact matching (not URL-shaped: a file path, a `queue:send`-style name,
/// console text). Compared scalar by scalar, never by `String`'s canonical
/// equivalence.
func exactPatternExcludes(_ ruleTarget: String, _ effectTarget: String) -> Bool {
    let hole = Array("{...}".unicodeScalars)
    let rule = Array(ruleTarget.unicodeScalars)
    let effect = Array(effectTarget.unicodeScalars)

    func find(_ needle: [Unicode.Scalar], in hay: [Unicode.Scalar], from: Int, to: Int) -> Int? {
        if needle.isEmpty { return from <= to ? from : nil }
        var i = from
        while i + needle.count <= to {
            if hay[i..<(i + needle.count)].elementsEqual(needle) { return i }
            i += 1
        }
        return nil
    }

    var chunks: [[Unicode.Scalar]] = []
    var start = 0
    while let at = find(hole, in: effect, from: start, to: effect.count) {
        chunks.append(Array(effect[start..<at]))
        start = at + hole.count
    }
    if chunks.isEmpty { return false }
    chunks.append(Array(effect[start...]))

    let first = chunks[0], last = chunks[chunks.count - 1]
    if first.count + last.count > rule.count { return true }
    if !rule.prefix(first.count).elementsEqual(first) || !rule.suffix(last.count).elementsEqual(last) {
        return true
    }
    var pos = first.count
    let end = rule.count - last.count
    for chunk in chunks.dropFirst().dropLast() {
        guard let at = find(chunk, in: rule, from: pos, to: end) else { return true }
        pos = at + chunk.count
    }
    return false
}

/// B2's re-proof of the v37.0 §513 guard for a URL-shaped rule target: can
/// this computed target's KNOWN prefix -- the literal text before its first
/// hole, which is a true, certain prefix of whatever the hole goes on to
/// produce (v37.0 §511) -- prove no completion could ever be covered by the
/// rule?
///
/// Reasons from that one chunk only. It's the one piece of the pattern
/// guaranteed to survive regardless of what any hole produces, so a proof
/// built from it alone is sound: it can only prove exclusions that are
/// real. A later chunk could in principle prove more, but skipping it only
/// means staying uncertain more often -- the conservative side of the
/// guarantee ("when in doubt, don't exclude").
func urlPatternExcludes(_ rScheme: String, _ rHost: String, _ rPath: String, _ effectTarget: String) -> Bool {
    let hole = Array("{...}".unicodeScalars)
    let effect = Array(effectTarget.unicodeScalars)
    guard let holeAt = findScalars(hole, in: effect) else { return false }
    let first = Array(effect[0..<holeAt])

    let sepMarker = Array("://".unicodeScalars)
    guard let sep = findScalars(sepMarker, in: first), sep > 0, isSchemeScalars(first[0..<sep]) else {
        return false
    }
    if asciiLower(first[0..<sep]) != asciiLower(Array(rScheme.unicodeScalars)) { return true }

    let remainder = Array(first[(sep + 3)...])
    var term = remainder.count
    for i in 0..<remainder.count where remainder[i] == "/" || remainder[i] == "?" || remainder[i] == "#" {
        term = i
        break
    }
    let rHostLower = asciiLower(Array(rHost.unicodeScalars))
    if term == remainder.count {
        // The host itself isn't fully known here -- only a prefix of it is,
        // from this chunk. Whatever it resolves to will still start with
        // this prefix, so a rule host that does NOT start with it can
        // never be that host.
        return !rHostLower.starts(with: asciiLower(remainder))
    }

    let eHost = Array(remainder[0..<term])
    let rest = Array(remainder[term...])
    if asciiLower(eHost) != rHostLower { return true }

    if rest.first == "?" || rest.first == "#" {
        // The path is fully known here, from certain text -- and empty.
        return !(rPath.isEmpty || rPath == "/")
    }

    let knownPath = rest
    if rPath.isEmpty || rPath == "/" { return false }
    let rPathScalars = Array(rPath.unicodeScalars)
    let lr = rPathScalars.count
    if knownPath.count < lr {
        return !knownPath.elementsEqual(rPathScalars[0..<knownPath.count])
    }
    if !knownPath[0..<lr].elementsEqual(rPathScalars) { return true }
    if knownPath.count == lr { return false }
    return knownPath[lr] != "/"
}

func resolveSubject(_ rule: AST.Rule, _ surface: Surface, _ declaringFile: String?) throws {
    var allOrigins: [(name: String, file: String?)] = []
    for effect in surface.declared {
        allOrigins.append(contentsOf: surface.originsOf(effect))
    }
    let hits = allOrigins.filter { sameText($0.name, rule.subject) }.map(\.file)
    if hits.contains(where: { sameOptionalText($0, declaringFile) }) { return }
    if let first = hits.first {
        let other = first ?? "None"
        throw RuleNotSupported(
            "rule [\(rule.name)] (line \(rule.line)): subject " +
                "'\(rule.subject)' only resolves in \(other), not in the file " +
                "that declares this rule — a rule cannot reach across an " +
                "import boundary to a name it never saw declared\n" +
                "  write the rule in \(other) instead, or name a subject " +
                "local to this file")
    }
    throw RuleNotSupported(
        "rule [\(rule.name)] (line \(rule.line)): subject " +
            "'\(rule.subject)' does not resolve to anything in the traced " +
            "effect surface — checking it needs a value this file's " +
            "derivation graph can reach\n" +
            "  check the name is spelled as it appears in this file, or " +
            "write the rule against 'anything' instead")
}

func subjectMatches(_ rule: AST.Rule, _ effect: Effect, _ surface: Surface, _ declaringFile: String?) -> Bool {
    if sameText(rule.subject, "anything") { return true }
    return surface.originsOf(effect).contains { sameText($0.name, rule.subject) && sameOptionalText($0.file, declaringFile) }
}

func resolveActive(_ rules: [AST.Rule]) throws -> [AST.Rule] {
    var byName = NameMap<AST.Rule>()
    for r in rules {
        if let other = byName[r.name] {
            throw RuleConflict(
                "two rules are both named [\(r.name)] (line \(other.line) " +
                    "and line \(r.line)) — a rule name must be unique\n" +
                    "  rename one of them")
        }
        byName[r.name] = r
    }

    var dropped = Set<CodePoints>()
    for r in rules {
        guard let supersedes = r.supersedes else { continue }
        if sameText(supersedes, r.name) {
            throw RuleConflict(
                "rule [\(r.name)] (line \(r.line)) supersedes itself\n" +
                    "  supersedes should name an earlier, different rule")
        }
        guard let targetRule = byName[supersedes] else {
            throw RuleConflict(
                "rule [\(r.name)] (line \(r.line)) supersedes " +
                    "[\(supersedes)], which is not a rule in this file\n" +
                    "  check the name, or remove the supersedes clause")
        }

        let actual = fingerprint(targetRule)
        // B3 (Track 0 #3): a supersedes clause with no fingerprint at all is
        // refused — the parser cannot know the other rule's fingerprint, so
        // this is where the requirement is enforced, with the named rule
        // actually in hand to compute one from.
        guard let expected = r.supersedesFingerprint else {
            throw RuleConflict(
                "rule [\(r.name)] (line \(r.line)) supersedes " +
                    "[\(supersedes)] (line \(targetRule.line)) without its " +
                    "fingerprint\n" +
                    "  write supersedes [\(supersedes)] @\(actual)")
        }
        if !sameText(actual, expected) {
            throw RuleConflict(
                "rule [\(r.name)] (line \(r.line)) supersedes " +
                    "[\(supersedes)] (line \(targetRule.line)) as of " +
                    "@\(expected), but [\(supersedes)] " +
                    "is now @\(actual) — it changed after [\(r.name)] was " +
                    "written to override it\n" +
                    "  confirm the override still means what it meant, " +
                    "then update the fingerprint to @\(actual)")
        }

        if sameText(targetRule.assertion, r.assertion) { dropped.insert(CodePoints(supersedes)) }
    }

    // B3 (Track 0 #5): `contradicts` resolution — same error class as
    // supersedes above. Checked against byName (every named rule), whether
    // or not either side later gets dropped above, since these are facts
    // about the clause as written.
    var contradictedPairs: [CodePoints: AST.Rule] = [:]
    for r in rules {
        guard let contradicts = r.contradicts else { continue }
        if sameText(contradicts, r.name) {
            throw RuleConflict(
                "rule [\(r.name)] (line \(r.line)) contradicts itself\n" +
                    "  contradicts should name a different rule")
        }
        guard byName[contradicts] != nil else {
            throw RuleConflict(
                "rule [\(r.name)] (line \(r.line)) contradicts " +
                    "[\(contradicts)], which is not a rule in this file\n" +
                    "  check the name, or remove the contradicts clause")
        }
        let pairKey = CodePoints(r.name) < CodePoints(contradicts)
            ? "\(r.name)\u{1F}\(contradicts)" : "\(contradicts)\u{1F}\(r.name)"
        if let first = contradictedPairs[CodePoints(pairKey)] {
            throw RuleConflict(
                "rule [\(r.name)] (line \(r.line)) contradicts " +
                    "[\(contradicts)], but [\(first.name)] (line " +
                    "\(first.line)) already contradicts [\(first.contradicts ?? "")] " +
                    "— the pair only needs declaring once\n" +
                    "  remove the contradicts clause from one of them")
        }
        contradictedPairs[CodePoints(pairKey)] = r
    }

    return rules.filter { !dropped.contains(CodePoints($0.name)) }
}

/// B2: a rule target names an address, not a request. The matcher ignores
/// an EFFECT's own query string and fragment (B2 §3) -- but a query or
/// fragment written into the RULE's own target is an authoring mistake, not
/// something to silently drop, so a URL-shaped target carrying one is
/// refused before any matching runs. Checked for every declared rule,
/// forbid or permit, superseded or not.
func checkTargetIsAnAddress(_ rule: AST.Rule) throws {
    guard let target = rule.target else { return }
    guard let parsed = urlPieces(target) else { return }
    if parsed.query == nil && parsed.fragment == nil { return }
    throw RuleConflict(
        "rule [\(rule.name)] (line \(rule.line)): target " +
            "\"\(escapeStringLiteral(target))\" has a query string or " +
            "fragment — a rule target names an address, and only an " +
            "effect's own query and fragment are ever ignored, never the " +
            "rule's\n" +
            "  drop everything from the \"?\" or \"#\" onward")
}

func checkPermitsAreRelated(_ active: [AST.Rule]) throws {
    let forbids = active.filter { sameText($0.assertion, "forbid") }
    for p in active where sameText(p.assertion, "permit") {
        // B1: coveredKinds(f) replaces the old sameText(f.effectKind,
        // p.effectKind) -- a "send" permit can be related to (named in
        // supersedes, share a scope with, or be strictly narrower in BOTH
        // scope and kind than) an "ask" forbid, since forbidding ask also
        // forbids send. narrows(p, f) is itself now generalised the same
        // way (kind overlap, not literal equality), so a `may send to
        // X/public` permit narrows a bare `may not ask` forbid
        // automatically, no supersedes needed. Only an equal-scope
        // cross-kind pair still demands an explicit supersedes --
        // checkConflicts's job.
        let related = forbids.contains { f in
            coveredKinds(f).contains(p.effectKind) &&
                (sameOptionalText(p.supersedes, f.name) || narrows(p, f) || sameScope(p.target, f.target))
        }
        if !related {
            throw RuleConflict(
                "rule [\(p.name)] (line \(p.line)) permits '\(p.effectKind)' but " +
                    "excepts no forbid rule — a permit only has force " +
                    "against a prohibition it supersedes or narrows\n" +
                    "  add 'supersedes [name-of-the-forbid-rule]' to " +
                    "[\(p.name)], or give it a target that narrows one of " +
                    "the forbid rules over '\(p.effectKind)'")
        }
    }
}

/// Equal-specificity conflicts (v2.0 §32; B2's `sameScope` in place of `==`
/// on the target; B1's `coveredKinds` overlap in place of `==` on the kind
/// for an opposite-assertion pair). Same assertion + different literal kind
/// (two forbids, one ask one send) never conflicts -- both prohibit, so
/// stacking agrees about everything. Opposite assertion + overlapping
/// covered kinds + same scope does conflict — "rule [deny] anything may
/// not ask to X" beside "rule [also] anything may send to X", with no
/// supersedes, is exactly such a pair — resolved the same way as the
/// same-kind case: an explicit supersedes naming the forbid. A strictly
/// narrower scope needs no supersedes at all, since `narrows` (generalised
/// the same way) resolves it.
func checkConflicts(_ active: [AST.Rule]) throws {
    let scopes = active.map { ParsedScope($0.target) }
    for (i, a) in active.enumerated() {
        for (j, b) in active.enumerated().dropFirst(i + 1) {
            if !sameScope(scopes[i], scopes[j]) { continue }
            if sameText(a.assertion, b.assertion) {
                if !sameText(a.effectKind, b.effectKind) { continue }
            } else if coveredKinds(a).isDisjoint(with: coveredKinds(b)) {
                continue
            }
            if narrows(a, b) || narrows(b, a) { continue }
            if sameOptionalText(a.supersedes, b.name) || sameOptionalText(b.supersedes, a.name) { continue }

            var whereText: String
            if sameText(a.effectKind, b.effectKind) {
                whereText = "'\(a.effectKind)'"
                if let t = a.target, !t.isEmpty { whereText += " to \"\(escapeStringLiteral(t))\"" }
            } else {
                let overlap = coveredKinds(a).intersection(coveredKinds(b)).sorted().joined(separator: "/")
                whereText = "'\(a.effectKind)' and '\(b.effectKind)' (both reach \(overlap))"
                if let t = a.target, !t.isEmpty { whereText += " to \"\(escapeStringLiteral(t))\"" }
            }
            if !sameText(a.assertion, b.assertion) {
                let (forbid, permit) = sameText(a.assertion, "forbid") ? (a, b) : (b, a)
                throw RuleConflict(
                    "rule [\(forbid.name)] (line \(forbid.line)) and rule " +
                        "[\(permit.name)] (line \(permit.line)) demand " +
                        "opposite things over \(whereText) — one forbids it, the " +
                        "other permits it, and neither narrows nor " +
                        "supersedes the other\n" +
                        "  add 'supersedes [\(forbid.name)]' to " +
                        "[\(permit.name)] to make the exception explicit, or " +
                        "give one of them a target the other lacks")
            }
            throw RuleConflict(
                "rule [\(a.name)] (line \(a.line)) and rule [\(b.name)] " +
                    "(line \(b.line)) are equally specific over \(whereText) — " +
                    "neither narrows nor supersedes the other\n" +
                    "  add 'supersedes [\(a.name)]' to [\(b.name)] (or the " +
                    "reverse), or give one of them a target the other lacks")
        }
    }
}

/// Does this rule's condition match at least one effect in the surface (B3,
/// Track 0 #5)? A rule *applies* when it matches, whether as a forbid rule
/// that would be violated or cleared, or as a permit rule that matched an
/// effect; a rule matching nothing (vacuous) does not apply. For a forbid
/// rule this is the same widen-on-uncertainty rule the vacuous check uses;
/// for a permit rule an uncertain match must NOT count — the conservatism
/// flips at the permit boundary (v2.0 §34b), the same asymmetry `clearer`
/// matching in `check` uses. `coveredKinds(rule)` (B1) replaces a literal
/// `effect.kind == rule.effectKind`: a `may not ask` rule that declares
/// `contradicts` applies when the surface only ever sends (never asks) --
/// `send` is inside what forbidding `ask` covers. A permit's own covered
/// set is always just `{rule.effectKind}` (permits never widen), so this
/// is a no-op change for permits. Returns (applies,
/// firstMatchingEffectOrNil) — the first effect by `surface.declared`'s
/// existing ordering.
func ruleApplies(_ rule: AST.Rule, _ surface: Surface, _ declaringFile: String?) -> (Bool, Effect?) {
    let covered = coveredKinds(rule)
    for effect in surface.declared {
        if !covered.contains(effect.kind) { continue }
        let (matched, uncertain) = targetMatches(rule, effect)
        if !matched { continue }
        if sameText(rule.assertion, "permit") && uncertain { continue }
        if !subjectMatches(rule, effect, surface, declaringFile) { continue }
        return (true, effect)
    }
    return (false, nil)
}

/// Contradiction violations (B3, Track 0 #5): every declared `contradicts`
/// pair where both rules apply to this surface. Iterates `active` in its
/// existing order, so this is deterministic and identical across hosts given
/// the same source. `resolveActive` already refused declaring the same pair
/// from both sides, so at most one of the two rules carries the
/// `contradicts` clause and no pair is ever reported twice. A pair naming a
/// rule `resolveActive` dropped (superseded away) can never fire: a dropped
/// rule is not in `active` and so cannot apply.
func checkContradictions(_ active: [AST.Rule], _ surface: Surface, _ declaringFile: String?) -> [Violation] {
    var byName = NameMap<AST.Rule>()
    for r in active { byName[r.name] = r }
    var results: [Violation] = []
    for r in active {
        guard let contradicts = r.contradicts, let other = byName[contradicts] else { continue }
        let (applies, effect) = ruleApplies(r, surface, declaringFile)
        if !applies { continue }
        let (otherApplies, otherEffect) = ruleApplies(other, surface, declaringFile)
        if !otherApplies { continue }
        results.append(Violation(r, effect, contradictsRule: other, contradictsEffect: otherEffect))
    }
    return results
}

/// Every violation of every rule, given a computed effect surface. A forbid rule
/// matching an effect is a violation unless a related permit — one that
/// supersedes or narrows it — also matches the same effect; a cleared match is
/// still returned, with `isViolation` false. `declaringFile` scopes
/// named-subject resolution: nil matches a surface built with no file.
/// Throws RuleNotSupported or RuleConflict.
public func check(_ rules: [AST.Rule], _ surface: Surface, declaringFile: String? = nil) throws -> RuleResults {
    for rule in rules {
        try checkTargetIsAnAddress(rule)
    }

    var resolvedSubjects: [String] = []
    for rule in rules where !sameText(rule.subject, "anything") {
        try resolveSubject(rule, surface, declaringFile)
        resolvedSubjects.append(rule.subject)
    }

    let active = try resolveActive(rules)
    try checkPermitsAreRelated(active)
    try checkConflicts(active)

    let forbids = active.filter { sameText($0.assertion, "forbid") }
    let permits = active.filter { sameText($0.assertion, "permit") }
    let forbidPieces = forbids.map { $0.target.flatMap(urlPieces) }
    let permitPieces = permits.map { $0.target.flatMap(urlPieces) }
    let effectPieces = surface.declared.map { $0.computed ? nil : urlPieces($0.target) }

    var results: [Violation] = []
    for (ri, rule) in forbids.enumerated() {
        let covered = coveredKinds(rule)
        var nKind = 0
        var nKindSubject = 0
        var matchedAny = false
        for (ei, effect) in surface.declared.enumerated() {
            if !covered.contains(effect.kind) { continue }
            nKind += 1
            let (matched, uncertain) = targetMatches(rule.target, forbidPieces[ri], effect, effectPieces[ei])
            let subjectOk = subjectMatches(rule, effect, surface, declaringFile)
            if subjectOk { nKindSubject += 1 }
            if !matched || !subjectOk { continue }
            matchedAny = true

            var clearer: AST.Rule?
            for (pi, p) in permits.enumerated() {
                // A permit never widens: it clears an effect only when its
                // own kind is the effect's actual kind, exactly — "a permit
                // for ask never clears a forbidden send" (B1, Track 0 #10).
                if !sameText(p.effectKind, effect.kind) { continue }
                if !(sameOptionalText(p.supersedes, rule.name) || narrows(p, rule)) { continue }
                let (pMatched, pUncertain) = targetMatches(p.target, permitPieces[pi], effect, effectPieces[ei])
                // A computed permit target clears nothing: widening is safe for a
                // prohibition, but widening an EXCEPTION is not.
                if pMatched && !pUncertain && subjectMatches(p, effect, surface, declaringFile) {
                    clearer = p
                    break
                }
            }

            let origins = surface.originsOf(effect)
            if let clearer {
                results.append(Violation(rule, effect, uncertain: uncertain, clearedBy: clearer, origins: origins))
                continue
            }

            let narrowers = forbids.indices.filter { oi in
                forbids[oi] !== rule && narrows(forbids[oi], rule) &&
                    targetMatches(forbids[oi].target, forbidPieces[oi], effect, effectPieces[ei]).0
            }.map { forbids[$0] }
            results.append(Violation(rule, effect, uncertain: uncertain, narrowedBy: narrowers, origins: origins))
        }

        if !sameText(rule.subject, "anything") && !matchedAny {
            let vacuous = Violation(rule, nil, vacuous: true)
            if nKind == 0 {
                vacuous.vacuousSituation = 1
            } else if nKindSubject == 0 {
                vacuous.vacuousSituation = 2
            } else {
                vacuous.vacuousSituation = 3
            }
            results.append(vacuous)
        }
    }

    results.append(contentsOf: checkContradictions(active, surface, declaringFile))

    return RuleResults(results, resolvedSubjects: resolvedSubjects)
}
