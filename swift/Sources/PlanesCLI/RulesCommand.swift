// RulesCommand.swift — `rules <file>` and `rules-src <file>`, js/cli.mjs's
// `case "rules"` / `case "rules-src"`.
//
//   rules <file>      shapes_cli.py --rules: surface via analyseFile(follow),
//                     check with declaringFile = abspath(file).
//   rules-src <file>  rule_violations(src): surface via analyse(src)
//                     (file = nil), check with declaringFile = nil.
//
// Both emit each violation's render text + is_violation + vacuous, the resolved
// subjects, and the exit category — or {error, message} on a conflict or an
// unsupported subject. The rule-results oracle (A.3).
import Planes

enum RulesCommand {
    static func run(_ rest: [String], sourceOnly: Bool) {
        let name = sourceOnly ? "rules-src" : "rules"
        guard let path = rest.first else { CLI.fail("\(name): expected a file") }
        do {
            let src = try readModuleSource(path)
            let found = try parse(src).compactMap { $0 as? AST.Rule }
            let surface: Surface
            var declaringFile: String?
            if sourceOnly {
                surface = try analyse(src)
            } else {
                surface = try analyseFile(path, follow: true)
                declaringFile = absolutePath(path)
            }
            CLI.write(form(found, surface, declaringFile: declaringFile).jsonText)
        } catch {
            CLI.fail("\(name): \(error)")
        }
    }

    /// check()'s outcome as the agreement form, or the refusal as {error, message}.
    static func form(_ rules: [AST.Rule], _ surface: Surface, declaringFile: String?) -> GrammarJSON {
        do {
            let results = try check(rules, surface, declaringFile: declaringFile)
            let exit = results.contains { $0.isViolation } ? 1 : results.contains { $0.vacuous } ? 2 : 0
            return .object([
                ("violations", .array(results.map { v in
                    .object([("render", .string(v.render())), ("is_violation", .bool(v.isViolation)),
                             ("vacuous", .bool(v.vacuous))])
                })),
                ("resolved_subjects", .array(results.resolvedSubjects.map { .string($0) })),
                ("exit", .number(String(exit))),
            ])
        } catch let e as RuleConflict {
            return .object([("error", .string("RuleConflict")), ("message", .string(e.message))])
        } catch let e as RuleNotSupported {
            return .object([("error", .string("RuleNotSupported")), ("message", .string(e.message))])
        } catch {
            CLI.fail("rules: \(error)")
        }
    }
}
