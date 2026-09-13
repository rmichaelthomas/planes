// FingerprintsCommand.swift — `fingerprints <file>`, js/cli.mjs's
// `case "fingerprints"`: [name, fingerprint] per rule, for byte-identity against
// rules.py's fingerprint() (which the FINGERPRINT token embeds).
import Planes

enum FingerprintsCommand {
    static func run(_ rest: [String]) {
        guard let path = rest.first else { CLI.fail("fingerprints: expected a file") }
        do {
            let found = try parse(try readModuleSource(path)).compactMap { $0 as? AST.Rule }
            CLI.write(GrammarJSON.array(found.map { .array([.string($0.name), .string(fingerprint($0))]) }).jsonText)
        } catch {
            CLI.fail("fingerprints: \(error)")
        }
    }
}
