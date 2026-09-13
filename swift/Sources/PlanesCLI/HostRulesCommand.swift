// HostRulesCommand.swift — `host-rules <rules-file> <effects-json>`.
//
// No js/cli.mjs counterpart: this drives HostRules.swift, the entry point for a
// host application that checks the effects it intends to perform against Planes
// rules without running a Planes program. `effects-json` is a JSON array of
// {"kind", "target", "site"?} objects. Emits the host surface (as_json, program
// "host"), check()'s outcome in the `rules` agreement form, whether every effect
// is admitted, and each result's rule `because` — which test_swift_host_rules.py
// compares with shapes.py's analyse and rules.py's check over the Planes program
// that performs those effects.
import Planes

enum HostRulesCommand {
    static func run(_ rest: [String]) {
        guard rest.count >= 2 else { CLI.fail("host-rules: expected a rules file and a JSON array of effects") }
        guard let items = CLI.json(rest[1]) as? [[String: Any]] else {
            CLI.fail("host-rules: effects must be a JSON array of objects")
        }
        let effects = items.map { item -> HostEffect in
            guard let kind = item["kind"] as? String, let target = item["target"] as? String else {
                CLI.fail("host-rules: each effect needs a string kind and target")
            }
            return HostEffect(kind: kind, target: target, site: item["site"] as? Int)
        }
        do {
            let ruleSet = try HostRuleSet(source: try readModuleSource(rest[0]))
            let surface: Surface
            do {
                surface = try hostSurface(effects)
            } catch let e as HostEffectError {
                CLI.write(GrammarJSON.object([("error", .string("HostEffectError")), ("message", .string(e.message))]).jsonText)
                return
            }
            var entries: [(key: String, value: GrammarJSON)] = [
                ("surface", asJson(surface, "host")),
                ("rules", RulesCommand.form(ruleSet.rules, surface, declaringFile: nil)),
            ]
            if let outcome = try? ruleSet.check(effects) {
                entries.append(("admitted", .bool(outcome.admitted)))
                entries.append(("because", .array(outcome.results.map { v in v.because.map { .string($0) } ?? .null })))
            } else {
                entries.append(("admitted", .null))
                entries.append(("because", .null))
            }
            CLI.write(GrammarJSON.object(entries).jsonText)
        } catch {
            CLI.fail("host-rules: \(error)")
        }
    }
}
