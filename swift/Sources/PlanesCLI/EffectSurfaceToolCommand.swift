// EffectSurfaceToolCommand.swift — `shapes-cli --index|--search|--diff ...`, the port of
// js/shapes_cli.mjs (shapes_cli.py's --index / --search / --diff).
//
// js runs this as its own entry point (`node js/shapes_cli.mjs`); here it is a
// subcommand of the one agreement CLI. A thin shell: every line of analysis is
// in EffectSurface.swift (analyseFile, the Surface queries, diff). This only enumerates
// files, calls the engine, and prints the text the Python CLI prints, with its
// exit code. Where js/shapes_cli.mjs approximates Python, this follows Python:
// glob skips hidden files and understands `?` and `[...]`, file lists sort by
// code point, and a column pads by code points, as `f"{s:16}"` does.
import Foundation
import Planes

enum EffectSurfaceToolCommand {
    static func run(_ args: [String]) -> Never {
        exit(main(args))
    }

    private static func err(_ s: String) {
        FileHandle.standardError.write(Data((s + "\n").utf8))
    }

    // f"{s:<n}": pad with spaces on the right to n code points, no truncation.
    private static func ljust(_ s: String, _ n: Int) -> String {
        let count = s.unicodeScalars.count
        return count >= n ? s : s + String(repeating: " ", count: n - count)
    }

    private static func textOf(_ scalars: ArraySlice<Unicode.Scalar>) -> String {
        String(String.UnicodeScalarView(scalars))
    }

    private static func basename(_ p: String) -> String {
        let s = Array(p.unicodeScalars)
        guard let i = s.lastIndex(of: "/") else { return p }
        return textOf(s[(i + 1)...])
    }

    // os.path.basename(p).replace(".planes", "") — every occurrence.
    private static func pkgName(_ p: String) -> String {
        let hay = Array(basename(p).unicodeScalars)
        let needle = Array(".planes".unicodeScalars)
        var out = String.UnicodeScalarView()
        var i = 0
        while i < hay.count {
            if i + needle.count <= hay.count && hay[i..<(i + needle.count)].elementsEqual(needle) {
                i += needle.count
            } else {
                out.append(hay[i])
                i += 1
            }
        }
        return String(out)
    }

    private static func isDirectory(_ p: String) -> Bool {
        var dir: ObjCBool = false
        return FileManager.default.fileExists(atPath: p, isDirectory: &dir) && dir.boolValue
    }

    // fnmatch's translation for a POSIX file name: `*`, `?`, `[...]` / `[!...]`,
    // case-sensitive, matched code point by code point.
    private static func fnmatch(_ name: [Unicode.Scalar], _ pat: [Unicode.Scalar]) -> Bool {
        func match(_ n: Int, _ p: Int) -> Bool {
            if p == pat.count { return n == name.count }
            switch pat[p] {
            case "*":
                var k = n
                while true {
                    if match(k, p + 1) { return true }
                    if k == name.count { return false }
                    k += 1
                }
            case "?":
                return n < name.count && match(n + 1, p + 1)
            case "[":
                var j = p + 1
                if j < pat.count && pat[j] == "!" { j += 1 }
                if j < pat.count && pat[j] == "]" { j += 1 }
                while j < pat.count && pat[j] != "]" { j += 1 }
                if j >= pat.count {
                    return n < name.count && name[n] == "[" && match(n + 1, p + 1)
                }
                guard n < name.count else { return false }
                var k = p + 1
                var negate = false
                if pat[k] == "!" {
                    negate = true
                    k += 1
                }
                let content = Array(pat[k..<j])
                var hit = false
                var c = 0
                while c < content.count {
                    if c + 2 < content.count && content[c + 1] == "-" {
                        if content[c].value <= name[n].value && name[n].value <= content[c + 2].value { hit = true }
                        c += 3
                    } else {
                        if content[c] == name[n] { hit = true }
                        c += 1
                    }
                }
                return hit != negate && match(n + 1, j + 1)
            default:
                return n < name.count && name[n] == pat[p] && match(n + 1, p + 1)
            }
        }
        return match(0, 0)
    }

    // glob.glob(pattern) for a pattern whose wildcards are in its last segment.
    private static func globOne(_ pattern: String) -> [String] {
        var p = pattern
        if isDirectory(p) { p = p.unicodeScalars.last == "/" ? p + "*.planes" : p + "/*.planes" }
        let scalars = Array(p.unicodeScalars)
        let slash = scalars.lastIndex(of: "/")
        let dir = slash.map { textOf(scalars[..<$0]) } ?? ""
        let base = Array(slash.map { scalars[($0 + 1)...] } ?? scalars[...])
        if !base.contains(where: { $0 == "*" || $0 == "?" || $0 == "[" }) {
            return FileManager.default.fileExists(atPath: p) ? [p] : []
        }
        guard let entries = try? FileManager.default.contentsOfDirectory(atPath: dir.isEmpty ? "." : dir) else {
            return []
        }
        return entries.filter { e in
            let name = Array(e.unicodeScalars)
            if name.first == "." && base.first != "." { return false }
            return fnmatch(name, base)
        }.map { slash == nil ? $0 : dir + "/" + $0 }
    }

    private static func globAll(_ patterns: [String]) -> [String] {
        patterns.flatMap { globOne($0).sorted { $0.unicodeScalars.lexicographicallyPrecedes($1.unicodeScalars) } }
    }

    private static func surfaceKind(_ s: Surface) -> String {
        s.isLibrary() ? "library" : s.isPure() ? "pure" : "program"
    }

    private static func analysed(_ p: String) -> Result<Surface, PlanesSyntaxError> {
        do {
            return .success(try analyseFile(p))
        } catch let e as PlanesSyntaxError {
            return .failure(e)
        } catch {
            err("\(p): \(error)")
            exit(1)
        }
    }

    private static func main(_ args: [String]) -> Int32 {
        guard let command = args.first else {
            err("usage: shapes-cli --index|--search|--diff ...")
            return 2
        }
        var lines: [String] = []
        func flush() {
            CLI.write(lines.joined(separator: "\n") + (lines.isEmpty ? "" : "\n"))
        }

        switch command {
        case "--index":
            let paths = globAll(args.count > 1 ? Array(args.dropFirst()) : ["*.planes"])
            if paths.isEmpty {
                err("no .planes files found")
                return 1
            }
            var rows: [(String, Surface)] = []
            for p in paths {
                switch analysed(p) {
                case let .success(s): rows.append((p, s))
                case let .failure(e): err("\(p): syntax error — \(e.message)")
                }
            }
            lines.append("\(ljust("package", 16)) \(ljust("kind", 9)) boundaries")
            lines.append(String(repeating: "-", count: 52))
            for (p, s) in rows {
                let bnd = s.boundaries().joined(separator: ", ")
                lines.append("\(ljust(pkgName(p), 16)) \(ljust(surfaceKind(s), 9)) \(bnd.isEmpty ? "-" : bnd)")
            }
            flush()
            return 0

        case "--search":
            guard args.count >= 2 else {
                err("--search needs a boundary (network, file, console)")
                return 2
            }
            let boundary = args[1]
            let paths = globAll(args.count > 2 ? Array(args.dropFirst(2)) : ["*.planes"])
            var hits = 0
            var skipped = 0
            for p in paths {
                switch analysed(p) {
                case let .failure(e):
                    err("\(p): syntax error — \(e.message)")
                    skipped += 1
                case let .success(s):
                    if s.touches(boundary) {
                        hits += 1
                        for eff in s.at(boundary) { lines.append("\(ljust(pkgName(p), 16)) \(eff)") }
                    }
                }
            }
            if hits == 0 {
                let note = skipped > 0 ? " (\(skipped) file(s) could not be parsed and were not searched)" : ""
                lines.append("nothing touches \(boundary) among the files searched\(note)")
            }
            flush()
            return 0

        case "--diff":
            guard args.count >= 3 else {
                err("--diff needs two files")
                return 2
            }
            do {
                let d = diff(try analyseFile(args[1]), try analyseFile(args[2]))
                lines.append("\(args[1]) -> \(args[2])")
                lines.append(d.render())
                flush()
                return d.isSignificant() ? 1 : 0
            } catch {
                err("\(error)")
                return 1
            }

        default:
            err("unknown command: \(command)")
            return 2
        }
    }
}
