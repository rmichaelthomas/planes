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
/// matched against nothing at all. Four shapes, told apart by `clearedBy` /
/// `narrowedBy` / `vacuous`: a real violation (none set); a violation narrowed by
/// a more specific sibling forbid; a prohibition a permit cleared (`isViolation`
/// false, still rendered); and a named-subject rule that matched nothing
/// (`vacuous`, no effect).
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

    public init(_ rule: AST.Rule, _ effect: Effect?, uncertain: Bool = false, clearedBy: AST.Rule? = nil,
                narrowedBy: [AST.Rule] = [], origins: [(name: String, file: String?)] = [], vacuous: Bool = false) {
        self.rule = rule
        self.effect = effect
        self.uncertain = uncertain
        self.clearedBy = clearedBy
        self.narrowedBy = narrowedBy
        self.origins = origins
        self.vacuous = vacuous
    }

    public var isViolation: Bool { clearedBy == nil && !vacuous }

    public func render() -> String {
        if vacuous { return renderVacuous() }
        let site = effect?.site ?? 0

        if let clearedBy {
            return "[\(rule.name)] would have been violated at " +
                "line \(site) — excepted by " +
                "[\(clearedBy.name)] " +
                "(line \(clearedBy.line))"
        }

        var lines = ["[\(rule.name)] violated at line \(site)."]
        lines.append("  \(effect.map { String(describing: $0) } ?? "None")")
        if uncertain {
            lines.append(
                "  target could not be pinned down statically — this " +
                    "computed value may or may not be " +
                    "\"\(escapeStringLiteral(rule.target ?? "None"))\"")
        }
        lines.append("  rule declared at line \(rule.line): \(condition(rule))")
        if !narrowedBy.isEmpty {
            let names = narrowedBy.map { "[\($0.name)] (line \($0.line))" }.joined(separator: ", ")
            lines.append("  narrowed here by \(names)")
        }
        if !origins.isEmpty {
            let parts = pySortedUnique(origins.map { o in
                if let f = o.file, !f.isEmpty { return "\(o.name) (\(f))" }
                return o.name
            })
            lines.append("  derived from: \(parts.joined(separator: ", "))")
        }
        return lines.joined(separator: "\n")
    }

    /// Every field `render()` reads, as data rather than prose (H1). A
    /// `--json --rules` consumer gets the rule name, the rule's own
    /// kind/target/assertion/`because`, the specific effect (kind, boundary,
    /// target, line) it matched or null for the vacuous shape, and the
    /// supersedes/permit outcome (`clearedBy`) or narrowing sibling
    /// (`narrowedBy`) — every structural fact `render()`'s prose is built
    /// from. `message` is `render()`'s own text, included verbatim beside the
    /// fields so a host can print exactly what text mode prints without
    /// re-deriving it (rules.py's `Violation.as_json` and js/rules.mjs's
    /// `Violation.asJson` must agree with this field for field). `origins`
    /// dedupes the same way `render()`'s derivation line does — by the
    /// formatted "name (file)" string, not by the raw pair.
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
        return .object([
            ("rule", .string(rule.name)),
            ("rule_line", .number(String(rule.line))),
            ("assertion", .string(rule.assertion)),
            ("kind", .string(rule.effectKind)),
            ("target", rule.target.map { GrammarJSON.string($0) } ?? .null),
            ("condition", .string(condition(rule))),
            ("because", rule.annotation.map { GrammarJSON.string($0.text) } ?? .null),
            ("is_violation", .bool(isViolation)),
            ("vacuous", .bool(vacuous)),
            ("vacuous_situation", vacuousSituation.map { GrammarJSON.number(String($0)) } ?? .null),
            ("uncertain", .bool(uncertain)),
            ("effect", effect.map { e in
                GrammarJSON.object([("kind", .string(e.kind)), ("boundary", .string(e.boundary)),
                                    ("target", .string(e.target)), ("line", .number(String(e.site)))])
            } ?? .null),
            ("cleared_by", clearedBy.map { c in
                GrammarJSON.object([("rule", .string(c.name)), ("line", .number(String(c.line)))])
            } ?? .null),
            ("narrowed_by", .array(narrowedBy.map { r in
                .object([("rule", .string(r.name)), ("line", .number(String(r.line)))])
            })),
            ("origins", .array(originsJSON)),
            ("message", .string(render())),
        ])
    }

    private func renderVacuous() -> String {
        let header: String
        let reason: String
        let fix: String

        if vacuousSituation == 1 {
            header = "[\(rule.name)] (line \(rule.line)) checked nothing " +
                "— subject '\(rule.subject)' resolves in this file, " +
                "but the program performs no '\(rule.effectKind)' effect " +
                "at all"
            reason = "the rule is inert against this program as written"
            fix = "check the program still performs the effect you " +
                "expect, or remove the rule if it no longer applies"
        } else if vacuousSituation == 3 {
            header = "[\(rule.name)] (line \(rule.line)) checked nothing " +
                "— subject '\(rule.subject)' derives a " +
                "'\(rule.effectKind)' effect, but the rule's target " +
                "excludes every one"
            reason = "'\(rule.subject)' reaches this effect kind, but " +
                "never at \"\(escapeStringLiteral(rule.target ?? "None"))\""
            fix = "check the target matches where '\(rule.subject)' " +
                "actually goes, or remove the target to check every " +
                "'\(rule.effectKind)' effect '\(rule.subject)' reaches"
        } else {
            header = "[\(rule.name)] (line \(rule.line)) checked nothing " +
                "— subject '\(rule.subject)' resolves in this file, " +
                "but no '\(rule.effectKind)' effect derives from it"
            reason = "the program performs '\(rule.effectKind)', but to a " +
                "target that does not derive from '\(rule.subject)'"
            fix = "check the subject names the value you meant, or " +
                "write the rule against 'anything'"
        }

        return [header, "  \(reason)", "  \(fix)"].joined(separator: "\n")
    }

    public var description: String { render() }
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

/// Case-folded scalars, for the one comparison B2 asks to be case-
/// insensitive (scheme and host) — everything else in this file (path,
/// name, target-as-address) stays code-point exact.
private func lowerScalars(_ s: ArraySlice<Unicode.Scalar>) -> [Unicode.Scalar] {
    Array(String(String.UnicodeScalarView(s)).lowercased().unicodeScalars)
}
private func lowerScalars(_ s: [Unicode.Scalar]) -> [Unicode.Scalar] { lowerScalars(s[...]) }

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
    let scalars = Array(target.unicodeScalars)
    let sepMarker = Array("://".unicodeScalars)
    guard let sep = findScalars(sepMarker, in: scalars), sep > 0, isSchemeScalars(scalars[0..<sep]) else {
        return nil
    }
    let scheme = String(String.UnicodeScalarView(scalars[0..<sep]))
    let rest = Array(scalars[(sep + 3)...])

    var hostEnd = rest.count
    for i in 0..<rest.count where rest[i] == "/" || rest[i] == "?" || rest[i] == "#" {
        hostEnd = i
        break
    }
    let host = String(String.UnicodeScalarView(rest[0..<hostEnd]))
    let tail = Array(rest[hostEnd...])

    let path: [Unicode.Scalar]
    let remainder: [Unicode.Scalar]
    if tail.first == "?" || tail.first == "#" {
        path = []
        remainder = tail
    } else {
        var pathEnd = tail.count
        for i in 0..<tail.count where tail[i] == "?" || tail[i] == "#" {
            pathEnd = i
            break
        }
        path = Array(tail[0..<pathEnd])
        remainder = Array(tail[pathEnd...])
    }

    var query: String?
    var fragment: String?
    if remainder.first == "#" {
        fragment = String(String.UnicodeScalarView(remainder))
    } else if remainder.first == "?" {
        if let hashAt = remainder.firstIndex(of: "#") {
            query = String(String.UnicodeScalarView(remainder[0..<hashAt]))
            fragment = String(String.UnicodeScalarView(remainder[hashAt...]))
        } else {
            query = String(String.UnicodeScalarView(remainder))
        }
    }
    return (scheme, host, String(String.UnicodeScalarView(path)), query, fragment)
}

/// Does `rulePath` cover `effectPath` at a "/" boundary (B2)? An empty path
/// or "/" in the rule covers every path on the host. Otherwise `rulePath`
/// must be a prefix of `effectPath`, and either they're equal, `rulePath`
/// itself already ends in "/" (everything under it is covered), or the next
/// character of `effectPath` past the prefix is "/". Compared code-point
/// exact — no percent-decoding, no Unicode normalisation.
func pathCovers(_ rulePath: String, _ effectPath: String) -> Bool {
    if rulePath.isEmpty || rulePath == "/" { return true }
    if sameText(effectPath, rulePath) { return true }
    let rule = Array(rulePath.unicodeScalars)
    let effect = Array(effectPath.unicodeScalars)
    guard effect.count >= rule.count, effect[0..<rule.count].elementsEqual(rule) else { return false }
    if rule.last == "/" { return true }
    return effect.count > rule.count && effect[rule.count] == "/"
}

/// Does the URL-shaped `ruleTarget` cover the URL-shaped `effectTarget`
/// (B2)? Same scheme and host, compared case-insensitively; port is part of
/// the host and compared exactly as written -- no default-port folding, so
/// `https://x` and `https://x:443` differ. The effect's own query and
/// fragment are ignored entirely -- only its path is compared, against the
/// rule's path, by `pathCovers`.
func urlCovers(_ ruleTarget: String, _ effectTarget: String) -> Bool {
    guard let r = parseURLTarget(ruleTarget), let e = parseURLTarget(effectTarget) else { return false }
    // Case-insensitive, but still code-point exact (never `String`'s `==`,
    // which is canonical-equivalence: a composed and a decomposed host must
    // NOT be treated as the same host).
    if lowerScalars(Array(r.scheme.unicodeScalars)) != lowerScalars(Array(e.scheme.unicodeScalars)) {
        return false
    }
    if lowerScalars(Array(r.host.unicodeScalars)) != lowerScalars(Array(e.host.unicodeScalars)) {
        return false
    }
    return pathCovers(r.path, e.path)
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
    guard parseURLTarget(wide) != nil, parseURLTarget(narrow) != nil else { return false }
    return urlCovers(wide, narrow)
}

/// Do `a` and `b` (two rule targets, or `nil`) range over exactly the same
/// addresses (B2)? Equal by mutual coverage rather than `==`, so
/// `"https://x"` and `"https://x/"` -- two spellings of "every path on x"
/// -- are the same scope even though the strings differ.
func sameScope(_ a: String?, _ b: String?) -> Bool {
    scopeCovers(a, b) && scopeCovers(b, a)
}

/// Does rule `b` cover a strict subset of what rule `a` ranges over? (v2.0
/// §30; re-proven for host/path covering at B2.) Kind and target only,
/// never assertion. `b` narrows `a` when `a`'s covered set contains `b`'s
/// and the two aren't the same scope -- the pre-B2 case (`a` has no target,
/// `b` does) is one instance of this; a rule whose covered address set is
/// strictly inside another's target now is too.
public func narrows(_ b: AST.Rule, _ a: AST.Rule) -> Bool {
    if sameText(a.name, b.name) { return false }
    if !sameText(a.effectKind, b.effectKind) { return false }
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
    guard let target = rule.target else { return (true, false) }
    if effect.computed {
        if patternExcludes(target, effect.target) { return (false, false) }
        return (true, true)
    }
    if parseURLTarget(target) != nil && parseURLTarget(effect.target) != nil {
        return (urlCovers(target, effect.target), false)
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
    if lowerScalars(first[0..<sep]) != lowerScalars(Array(rScheme.unicodeScalars)) { return true }

    let remainder = Array(first[(sep + 3)...])
    var term = remainder.count
    for i in 0..<remainder.count where remainder[i] == "/" || remainder[i] == "?" || remainder[i] == "#" {
        term = i
        break
    }
    let rHostLower = lowerScalars(Array(rHost.unicodeScalars))
    if term == remainder.count {
        // The host itself isn't fully known here -- only a prefix of it is,
        // from this chunk. Whatever it resolves to will still start with
        // this prefix, so a rule host that does NOT start with it can
        // never be that host.
        return !rHostLower.starts(with: lowerScalars(remainder))
    }

    let eHost = Array(remainder[0..<term])
    let rest = Array(remainder[term...])
    if lowerScalars(eHost) != rHostLower { return true }

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

        if let expected = r.supersedesFingerprint {
            let actual = fingerprint(targetRule)
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
        }

        if sameText(targetRule.assertion, r.assertion) { dropped.insert(CodePoints(supersedes)) }
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
    guard let parsed = parseURLTarget(target) else { return }
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
        let related = forbids.contains { f in
            sameText(f.effectKind, p.effectKind) &&
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

func checkConflicts(_ active: [AST.Rule]) throws {
    for (i, a) in active.enumerated() {
        for b in active[(i + 1)...] {
            if !sameText(a.effectKind, b.effectKind) || !sameScope(a.target, b.target) { continue }
            if narrows(a, b) || narrows(b, a) { continue }
            if sameOptionalText(a.supersedes, b.name) || sameOptionalText(b.supersedes, a.name) { continue }

            var whereText = "'\(a.effectKind)'"
            if let t = a.target, !t.isEmpty { whereText += " to \"\(escapeStringLiteral(t))\"" }
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

    var results: [Violation] = []
    for rule in forbids {
        var nKind = 0
        var nKindSubject = 0
        var matchedAny = false
        for effect in surface.declared {
            if !sameText(effect.kind, rule.effectKind) { continue }
            nKind += 1
            let (matched, uncertain) = targetMatches(rule, effect)
            let subjectOk = subjectMatches(rule, effect, surface, declaringFile)
            if subjectOk { nKindSubject += 1 }
            if !matched || !subjectOk { continue }
            matchedAny = true

            var clearer: AST.Rule?
            for p in permits {
                if !(sameOptionalText(p.supersedes, rule.name) || narrows(p, rule)) { continue }
                let (pMatched, pUncertain) = targetMatches(p, effect)
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

            let narrowers = forbids.filter { other in
                other !== rule && narrows(other, rule) && targetMatches(other, effect).0
            }
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

    return RuleResults(results, resolvedSubjects: resolvedSubjects)
}
