// HashCommand.swift — `hash <json-array-of-strings>`, js/cli.mjs's `case "hash"`.
//
// The full 64-char SHA-256 hex digest of each string's UTF-8 bytes, for
// byte-identity against hashlib (A.2).
import Planes

enum HashCommand {
    static func run(_ rest: [String]) {
        guard let strings = CLI.json(rest.first ?? "") as? [String] else {
            CLI.fail("hash: expected a JSON array of strings")
        }
        CLI.out(json: strings.map(sha256Hex))
    }
}
