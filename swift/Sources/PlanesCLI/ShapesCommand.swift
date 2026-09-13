// ShapesCommand.swift — `shapes <file> [--no-follow]`, js/cli.mjs's `case "shapes"`.
//
// The published effect surface (as_json), the effect-surface oracle against
// shapes_cli.as_json. No trailing newline: js writes it with `out`.
import Planes

enum ShapesCommand {
    static func run(_ rest: [String]) {
        guard let path = rest.first else { CLI.fail("shapes: expected a file") }
        let follow = !rest.contains("--no-follow")
        do {
            CLI.write(asJson(try analyseFile(path, follow: follow), path).jsonText)
        } catch {
            CLI.fail("shapes: \(error)")
        }
    }
}
