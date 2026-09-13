// ShapesDerivCommand.swift — `shapes-deriv <file>`, js/cli.mjs's
// `case "shapes-deriv"`.
//
// The derivation + origins form, computed from this file's own source with
// analyse(src) (file = nil), so derivation `file` fields are null on both sides
// and only structure is compared.
import Planes

enum ShapesDerivCommand {
    static func run(_ rest: [String]) {
        guard let path = rest.first else { CLI.fail("shapes-deriv: expected a file") }
        do {
            CLI.write(derivationForm(try analyse(try readModuleSource(path))).jsonText)
        } catch {
            CLI.fail("shapes-deriv: \(error)")
        }
    }
}
