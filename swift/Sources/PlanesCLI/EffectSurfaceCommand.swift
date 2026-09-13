// EffectSurfaceCommand.swift — `shapes <file> [--no-follow] [--rules]`,
// js/cli.mjs's `case "shapes"`.
//
// The published effect surface (as_json), the effect-surface oracle against
// shapes_cli.as_json. No trailing newline: js writes it with `out`.
//
// --rules (H1) additionally checks this file's own rules — a second parse of
// the same file for its top-level Rule statements, declaringFile = the
// resolved path, matching shapes_cli.py's --json --rules path
// (analyseFile(follow) + abspath) — and merges the result the same way. A
// RuleConflict / RuleNotSupported is reported the same way RulesCommand
// reports it, as {error, message}, since this is the oracle CLI, not
// shapes_cli.py's own stderr-and-exit-1 convention.
import Planes

enum EffectSurfaceCommand {
    static func run(_ rest: [String]) {
        guard let path = rest.first else { CLI.fail("shapes: expected a file") }
        let follow = !rest.contains("--no-follow")
        do {
            let surface = try analyseFile(path, follow: follow)
            guard rest.contains("--rules") else {
                CLI.write(asJson(surface, path).jsonText)
                return
            }
            let src = try readModuleSource(path)
            let found = try parse(src).compactMap { $0 as? AST.Rule }
            let declaringFile = absolutePath(path)
            do {
                let results = try check(found, surface, declaringFile: declaringFile)
                let rulesDoc = GrammarJSON.object([
                    ("checked", .number(String(found.count))),
                    ("resolved_subjects", .array(results.resolvedSubjects.map { .string($0) })),
                    ("violations", .array(results.map { $0.asJSON() })),
                ])
                CLI.write(asJson(surface, path, rules: rulesDoc).jsonText)
            } catch let e as RuleConflict {
                CLI.write(GrammarJSON.object([("error", .string("RuleConflict")), ("message", .string(e.message))]).jsonText)
            } catch let e as RuleNotSupported {
                CLI.write(GrammarJSON.object([("error", .string("RuleNotSupported")), ("message", .string(e.message))]).jsonText)
            }
        } catch {
            CLI.fail("shapes: \(error)")
        }
    }
}
