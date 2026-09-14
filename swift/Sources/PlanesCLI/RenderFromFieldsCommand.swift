// RenderFromFieldsCommand.swift — `render-from-fields <file> [--rules-src]`
// (B4, test-only oracle; no js/cli.mjs counterpart -- JS proves the same
// claim in-process, in js/test/rules.test.mjs, since node --test needs no
// subprocess CLI to reach rules.mjs directly).
//
// For every violation `check()` finds, round-trips Violation.asJSON()
// through its own `jsonText`/`GrammarJSON.parse` -- the CLI JSON path
// EffectSurfaceCommand's `shapes --rules` itself writes -- and confirms
// `renderViolation` on the round-tripped document equals `render()` byte for
// byte. That is the proof B4 asks for, run the same way every other Swift
// claim in this repo is oracle-tested: from Python, over subprocess output,
// in test_swift_rules.py.
//
//   render-from-fields <file>              shapes_cli --rules's surface:
//                                           analyseFile(follow), declaringFile
//                                           = abspath(file).
//   render-from-fields <file> --rules-src  rule_violations(src)'s surface:
//                                           analyse(src), declaringFile = nil.
//
// Writes {"checked": N, "mismatches": [...]} -- an empty "mismatches" array
// is the whole claim; a RuleConflict/RuleNotSupported is reported the same
// way RulesCommand/EffectSurfaceCommand report it, as {error, message}.
import Planes

enum RenderFromFieldsCommand {
    static func run(_ rest: [String]) {
        guard let path = rest.first else { CLI.fail("render-from-fields: expected a file") }
        let sourceOnly = rest.contains("--rules-src")
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
            do {
                let results = try check(found, surface, declaringFile: declaringFile)
                var mismatches: [String] = []
                for v in results {
                    let json = v.asJSON()
                    guard let roundTripped = GrammarJSON.parse(json.jsonText) else {
                        mismatches.append("[\(v.rule.name)] asJSON().jsonText did not re-parse")
                        continue
                    }
                    let got = renderViolation(roundTripped)
                    let want = v.render()
                    if got != want {
                        mismatches.append("[\(v.rule.name)] got \(got) want \(want)")
                    }
                }
                CLI.write(GrammarJSON.object([
                    ("checked", .number(String(results.count))),
                    ("mismatches", .array(mismatches.map { .string($0) })),
                ]).jsonText)
            } catch let e as RuleConflict {
                CLI.write(GrammarJSON.object([("error", .string("RuleConflict")), ("message", .string(e.message))]).jsonText)
            } catch let e as RuleNotSupported {
                CLI.write(GrammarJSON.object([("error", .string("RuleNotSupported")), ("message", .string(e.message))]).jsonText)
            }
        } catch {
            CLI.fail("render-from-fields: \(error)")
        }
    }
}
