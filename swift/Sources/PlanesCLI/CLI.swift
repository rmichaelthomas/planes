// CLI.swift — JSON in and out for the agreement CLI.
import Foundation

enum CLI {
    static func fail(_ message: String) -> Never {
        FileHandle.standardError.write(Data((message + "\n").utf8))
        exit(2)
    }

    /// A JSON argument, parsed. Strings keep their code points exactly.
    static func json(_ text: String) -> Any {
        do {
            return try JSONSerialization.jsonObject(with: Data(text.utf8), options: [.fragmentsAllowed])
        } catch {
            fail("planes-swift: bad JSON argument: \(error)")
        }
    }

    /// Writes `value` as JSON on stdout, as `out(JSON.stringify(v))` does.
    static func out(json value: Any) {
        do {
            let data = try JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed, .withoutEscapingSlashes])
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data("\n".utf8))
        } catch {
            fail("planes-swift: could not encode output: \(error)")
        }
    }

    /// Writes text on stdout, as `out(text)` does.
    static func out(text: String) {
        FileHandle.standardOutput.write(Data((text + "\n").utf8))
    }

    static func readFile(_ path: String) -> String {
        guard let data = FileManager.default.contents(atPath: path),
              let text = String(data: data, encoding: .utf8) else {
            fail("planes-swift: cannot read \(path)")
        }
        return text
    }
}
