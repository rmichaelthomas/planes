// ShapesFnCommand.swift — `shapes-fn <file> [--no-follow]`, js/cli.mjs's
// `case "shapes-fn"`: the per-function effect breakdown.
import Planes

enum ShapesFnCommand {
    static func run(_ rest: [String]) {
        guard let path = rest.first else { CLI.fail("shapes-fn: expected a file") }
        let follow = !rest.contains("--no-follow")
        do {
            CLI.write(functionsBreakdown(try analyseFile(path, follow: follow)).jsonText)
        } catch {
            CLI.fail("shapes-fn: \(error)")
        }
    }
}
