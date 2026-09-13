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

    /// Writes text on stdout followed by a newline.
    static func out(text: String) {
        FileHandle.standardOutput.write(Data((text + "\n").utf8))
    }

    /// Writes text on stdout exactly, with no newline added — js/cli.mjs's
    /// `out(s)`, which is `process.stdout.write(s)`. For output a suite compares
    /// byte for byte rather than parsing.
    static func write(_ text: String) {
        FileHandle.standardOutput.write(Data(text.utf8))
    }

    /// `JSON.stringify(value)` for a flat object of strings, keys in the order
    /// given, no newline added.
    static func write(jsonObject entries: [(String, String)]) {
        do {
            let parts = try entries.map { key, value -> String in
                let k = try JSONSerialization.data(withJSONObject: key, options: [.fragmentsAllowed, .withoutEscapingSlashes])
                let v = try JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed, .withoutEscapingSlashes])
                return String(decoding: k, as: UTF8.self) + ":" + String(decoding: v, as: UTF8.self)
            }
            write("{" + parts.joined(separator: ",") + "}")
        } catch {
            fail("planes-swift: could not encode output: \(error)")
        }
    }

    /// The file's text, every code point kept. `String(data:encoding:)` only
    /// validates here: it drops a leading byte-order mark, which Python's
    /// `open(path, encoding="utf-8")` and Node's `readFileSync(path, "utf-8")`
    /// both keep, and which reaches the lexer as a stray character.
    static func readFile(_ path: String) -> String {
        guard let data = FileManager.default.contents(atPath: path),
              String(data: data, encoding: .utf8) != nil else {
            fail("planes-swift: cannot read \(path)")
        }
        return String(decoding: data, as: UTF8.self)
    }
}
