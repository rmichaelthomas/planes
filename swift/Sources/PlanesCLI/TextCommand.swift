// TextCommand.swift — `text <json-ops>`, js/cli.mjs's textOp.
import Planes

enum TextCommand {
    static func run(_ rest: [String]) {
        guard let ops = CLI.json(rest.first ?? "") as? [[Any]] else { CLI.fail("text: expected a JSON array of ops") }
        CLI.out(json: ops.map(op))
    }

    private static func op(_ op: [Any]) -> Any {
        guard let name = op.first as? String, let arg = op.dropFirst().first as? String else {
            CLI.fail("text: malformed op")
        }
        switch name {
        case "resolve":
            do { return try resolveStringEscapes(arg) } catch { CLI.fail("text: \(error)") }
        case "escape": return escapeStringLiteral(arg)
        case "cplen": return String(codePointLength(arg))
        case "cps": return codePoints(arg)
        case "badresolve":
            do {
                _ = try resolveStringEscapes(arg)
                return "NO-ERROR"
            } catch {
                return "BAD:" + error.badCharacter
            }
        default: CLI.fail("unknown text op: \(name)")
        }
    }
}
