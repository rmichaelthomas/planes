// RenderRulesCommand.swift — `render-rules <file>`, js/cli.mjs's
// `case "render-rules"`.
//
// Canonical source with the generated rule markers, like shapes_cli.py --render:
// single-file, unfollowed, so a rule subject resolves against a surface whose
// nodes all carry file = nil. Written byte for byte, no newline added.
import Planes

enum RenderRulesCommand {
    static func run(_ rest: [String]) {
        guard let path = rest.first else { CLI.fail("render-rules: expected a file") }
        do {
            let src = try readModuleSource(path)
            let prog = try parse(src)
            let found = prog.compactMap { $0 as? AST.Rule }
            CLI.write(found.isEmpty ? try render(prog) : try render(prog, rules: found, surface: try analyse(src)))
        } catch {
            CLI.fail("render-rules: \(error)")
        }
    }
}
