// TokensCommand.swift — `tokens <file>`, js/cli.mjs's `case "tokens"`.
import Planes

enum TokensCommand {
    // The canonical token form: [kind, value, line] per token, matching
    // test_lexer_in_planes.py's (t.kind, t.value, t.line). On a syntax error,
    // emit a tagged marker the Python side compares against its own raise.
    static func run(_ rest: [String]) {
        guard let path = rest.first else { CLI.fail("tokens: expected a file") }
        let src = CLI.readFile(path)
        do {
            let toks = try tokenize(src)
            CLI.out(json: toks.map { [$0.kind, $0.value, $0.line] as [Any] })
        } catch let e as PlanesSyntaxError {
            CLI.out(json: ["error": "PlanesSyntaxError", "message": e.message])
        } catch {
            CLI.fail("tokens: \(error)")
        }
    }
}
