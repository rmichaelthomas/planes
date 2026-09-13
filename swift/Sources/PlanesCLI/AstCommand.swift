// AstCommand.swift — `ast <file> [known-json]`, js/cli.mjs's `case "ast"`.
import Foundation
import Planes

enum AstCommand {
    // `known-json` is the identical name->arity mapping the Python harness
    // computes (cross-file `use` resolution), so both parsers see the same module
    // context; a null arity is an unknown one. Emits the canonical AST program
    // form; a syntax error or ambiguity emits a tagged marker to compare against.
    // Neither gets a trailing newline: js writes both with `out`, and the suite
    // compares the form byte for byte.
    static func run(_ rest: [String]) {
        guard let path = rest.first else { CLI.fail("ast: expected a file") }
        let src = CLI.readFile(path)
        var known: [KnownName]?
        if rest.count > 1, !rest[1].isEmpty {
            known = knownNames(rest[1])
        }
        do {
            CLI.write(canonicalProgram(try parse(src, known: known)))
        } catch let e as PlanesAmbiguity {
            CLI.write(jsonObject: [("error", "PlanesAmbiguity"), ("message", e.message)])
        } catch let e as PlanesSyntaxError {
            CLI.write(jsonObject: [("error", "PlanesSyntaxError"), ("message", e.message)])
        } catch {
            CLI.fail("ast: \(error)")
        }
    }

    /// The known-JSON object as name -> arity pairs, in its key order.
    private static func knownNames(_ text: String) -> [KnownName] {
        guard let doc = GrammarJSON.parse(text), case let .object(entries) = doc else {
            CLI.fail("ast: known-json must be a JSON object of name -> arity")
        }
        return entries.map { entry -> KnownName in
            switch entry.value {
            case .null:
                return (entry.key, nil)
            case let .number(n):
                guard let arity = Int(n) else { CLI.fail("ast: arity of \(entry.key) is not a whole number: \(n)") }
                return (entry.key, arity)
            default:
                CLI.fail("ast: arity of \(entry.key) must be a number or null")
            }
        }
    }
}
