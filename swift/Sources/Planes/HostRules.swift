// HostRules.swift — Planes rules for a host application that runs no Planes.
//
// A host (a browser, say) ships its policy as Planes rules — `.planes` source —
// and wants to ask, before it performs something: do these rules admit it? It
// has no Planes program to analyse; it knows the effects it is about to perform
// (a request to this URL, a write to that file). This file is the thin entry
// point for that, and it adds no semantics of its own:
//
//   * `HostRuleSet(source:)` is `parse`, keeping the `Rule` statements — what
//     shapes_cli.py --rules collects.
//   * `hostSurface(_:)` builds the `Surface` that `analyse` computes for the
//     program which performs exactly those effects, one per line, each with a
//     literal destination — `ask "https://…"`, `read "…"`, `write 0 to "…"`,
//     `show "…"` — from the same `Effect`, `StaticDeriv`, `EffectSet` and sort
//     that Shapes.swift uses. test_swift_host_rules.py holds that claim against
//     Python: it writes that program, runs shapes.py's `analyse` and rules.py's
//     `check`, and compares surface and results.
//   * `HostRuleSet.check(_:)` is `check(rules, surface)` with no declaring file,
//     as for any surface computed from source with no path.
//
//     let rules = try HostRuleSet(source: policySource)
//     let outcome = try rules.check([.ask("https://tracker.example/pixel")])
//     if !outcome.admitted {
//         for v in outcome.violations { print(v.render()); print(v.because ?? "") }
//     }
//
// What a host cannot express, because no Planes program with a literal target
// expresses it: the ambient kinds (`clock`, `random`, `env`) take no
// destination, so `analyse` never gives them a literal target — `hostSurface`
// refuses them rather than inventing a surface shapes.py would never produce.
// And a rule with a named subject (anything other than `anything`) needs a value
// in a derivation graph; a host's effects derive from literals only, so `check`
// raises RuleNotSupported for it, exactly as it does for that program.
//
// `because` is not part of a violation's rendered text — rules.py's render()
// never prints it — so each `Violation` exposes its rule's `because` text
// beside `render()` for a host that wants to show the reason.

/// One effect a host intends to perform: an effect kind of the vocabulary and
/// its literal destination. `site` is the line the effect stands on in the
/// equivalent program, and what a violation reports as "violated at line N";
/// nil places it at its position in the list (1-based). Sites must increase
/// down the list for the equivalent program to exist.
public struct HostEffect: Sendable {
    public let kind: String
    public let target: String
    public let site: Int?

    public init(kind: String, target: String, site: Int? = nil) {
        self.kind = kind
        self.target = target
        self.site = site
    }

    /// A network request to `url` — `ask "url"`.
    public static func ask(_ url: String, site: Int? = nil) -> HostEffect {
        HostEffect(kind: "ask", target: url, site: site)
    }
}

/// An effect `hostSurface` cannot build a surface for.
public struct HostEffectError: Error, CustomStringConvertible, Sendable {
    public let message: String
    public var description: String { message }
}

/// The effect kinds whose Planes form takes a literal destination.
public let HOST_EFFECT_KINDS = ["ask", "read", "write", "show"]

/// The Surface `analyse` computes for the program performing `effects`, each
/// on its own line with a literal destination.
public func hostSurface(_ effects: [HostEffect]) throws -> Surface {
    let kinds = try effectKinds()
    let top = EffectSet()
    var previous = 0
    for (i, e) in effects.enumerated() {
        guard HOST_EFFECT_KINDS.contains(where: { sameText($0, e.kind) }), let boundary = kinds[e.kind] else {
            throw HostEffectError(message:
                "a host effect must be one of \(HOST_EFFECT_KINDS.joined(separator: ", ")) " +
                    "with a literal destination, not '\(e.kind)'")
        }
        let site = e.site ?? i + 1
        if site <= previous {
            throw HostEffectError(message:
                "host effect \(i + 1) is at line \(site), which is not after line \(previous) — " +
                    "sites must increase down the list")
        }
        previous = site
        // `const`'s Str case: a literal destination derives from nothing but
        // itself, in a surface computed with no file.
        let literal = StaticDeriv("literal", "\"\(escapeStringLiteral(e.target))\"")
        top.add(Effect(e.kind, boundary, e.target, false, site: site, derivation: literal))
    }
    return Surface(effects: top.sorted())
}

/// The outcome of checking a host's effects against its rules.
public struct HostCheck {
    /// Everything `check` returned: violations, cleared matches, vacuous rules.
    public let results: RuleResults
    public let surface: Surface

    /// No genuine violation: every effect is admitted.
    public var admitted: Bool { !results.contains { $0.isViolation } }
    /// The genuine violations — what refuses the effects.
    public var violations: [Violation] { results.filter(\.isViolation) }
    /// Prohibitions a permit cleared, still reported so the exception is visible.
    public var cleared: [Violation] { results.filter { $0.clearedBy != nil } }
}

/// Rules read from Planes source.
public struct HostRuleSet {
    public let rules: [AST.Rule]

    /// Parses `source` and keeps its `rule` statements. Throws
    /// PlanesSyntaxError on source that does not parse.
    public init(source: String) throws {
        rules = try parse(source).compactMap { $0 as? AST.Rule }
    }

    public init(rules: [AST.Rule]) {
        self.rules = rules
    }

    /// Checks these rules against the effects a host intends to perform. Throws
    /// HostEffectError, RuleConflict or RuleNotSupported.
    public func check(_ effects: [HostEffect]) throws -> HostCheck {
        let surface = try hostSurface(effects)
        return HostCheck(results: try Planes.check(rules, surface), surface: surface)
    }
}

extension Violation {
    /// The rule's `because` text, if it has one — the reason, which render()
    /// does not print.
    public var because: String? { rule.annotation?.text }
}
