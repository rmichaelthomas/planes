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

/// Does rule `b` cover a strict subset of what rule `a` ranges over? (v2.0 §30.)
/// Kind and target only, never assertion.
public func narrows(_ b: AST.Rule, _ a: AST.Rule) -> Bool {
    if sameText(a.name, b.name) { return false }
    if !sameText(a.effectKind, b.effectKind) { return false }
    return a.target == nil && b.target != nil
}

/// (matched, uncertain).
func targetMatches(_ rule: AST.Rule, _ effect: Effect) -> (Bool, Bool) {
    guard let target = rule.target else { return (true, false) }
    if effect.computed {
        if patternExcludes(target, effect.target) { return (false, false) }
        return (true, true)
    }
    return (sameText(effect.target, target), false)
}

/// rules.py's `_pattern_excludes`, which this must agree with: can a computed
/// target provably never equal the rule's target? Its known chunks must appear
/// in the rule's target in order, the first at the start and the last at the
/// end, a hole standing for any text including none. A target with no hole, or
/// a foreign's "(destination not stated)", excludes nothing. Compared scalar by
/// scalar, never by `String`'s canonical equivalence.
func patternExcludes(_ ruleTarget: String, _ effectTarget: String) -> Bool {
    let hole = Array("{...}".unicodeScalars)
    let rule = Array(ruleTarget.unicodeScalars)
    let effect = Array(effectTarget.unicodeScalars)
    let noDestination = Array(" (destination not stated)".unicodeScalars)

    func find(_ needle: [Unicode.Scalar], in hay: [Unicode.Scalar], from: Int, to: Int) -> Int? {
        if needle.isEmpty { return from <= to ? from : nil }
        var i = from
        while i + needle.count <= to {
            if hay[i..<(i + needle.count)].elementsEqual(needle) { return i }
            i += 1
        }
        return nil
    }

    if effect.count >= noDestination.count && effect.suffix(noDestination.count).elementsEqual(noDestination) {
        return false
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

func checkPermitsAreRelated(_ active: [AST.Rule]) throws {
    let forbids = active.filter { sameText($0.assertion, "forbid") }
    for p in active where sameText(p.assertion, "permit") {
        let related = forbids.contains { f in
            sameText(f.effectKind, p.effectKind) &&
                (sameOptionalText(p.supersedes, f.name) || narrows(p, f) || sameOptionalText(p.target, f.target))
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
            if !sameText(a.effectKind, b.effectKind) || !sameOptionalText(a.target, b.target) { continue }
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
