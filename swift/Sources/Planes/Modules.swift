// Modules.swift — Planes module resolution, ported from modules.py.
//
// The Swift counterpart of js/modules.mjs together with js/module_loader_node.mjs:
// `use http` / `use file` name builtin capability modules; `use utils` names a
// file utils.planes resolved relative to the importing file's own directory (or
// the working directory when there is none). js splits the four host-bound
// operations (locate, read, key, label) into a loader object so the same graph
// code runs in a browser; this host has only the file system, so they are plain
// functions here, doing exactly what the Node loader does — which is what
// modules.py does. Only the parts analyseFile needs are ported: the graph, the
// names in it, the renames and the collision check. hoistAndRun belongs to the
// interpreter.
//
// A file is read as modules.py reads it — `open(path, encoding="utf-8")`, in
// Python's text mode — so "\r\n" and a lone "\r" arrive as "\n", and a leading
// byte-order mark is kept.
import Foundation

public let BUILTIN_MODULES = ["file", "http"]

/// A module that cannot be resolved, a cycle, or two modules defining one name.
public struct ModuleError: Error, CustomStringConvertible, Sendable {
    public let name: String
    public let detail: String
    public let fix: String
    public let message: String

    public init(_ name: String, _ detail: String, _ fix: String = "") {
        self.name = name
        self.detail = detail
        self.fix = fix
        var msg = detail
        if !fix.isEmpty { msg += "\n  try: \(fix)" }
        message = msg
    }

    public var description: String { message }
}

/// A source file that could not be read as UTF-8 text.
public struct SourceReadError: Error, CustomStringConvertible, Sendable {
    public let path: String
    public var description: String { "cannot read \(path) as UTF-8 text" }
}

/// The ModuleError raised when `name` cannot be found.
public func missingModuleError(_ name: String) -> ModuleError {
    ModuleError(
        name,
        "no module named '\(name)'",
        "create \(name).planes next to this file, or use one of: \(BUILTIN_MODULES.joined(separator: ", "))")
}

/// A file's text as Python's `open(path, encoding="utf-8").read()` returns it:
/// universal newlines translated, every other code point kept.
public func readModuleSource(_ path: String) throws -> String {
    guard let data = FileManager.default.contents(atPath: path),
          String(data: data, encoding: .utf8) != nil else {
        throw SourceReadError(path: path)
    }
    let raw = String(decoding: data, as: UTF8.self)
    guard raw.unicodeScalars.contains("\r") else { return raw }
    var out = ""
    var pendingCR = false
    for c in raw.unicodeScalars {
        if pendingCR {
            pendingCR = false
            out += "\n"
            if c == "\n" { continue }
        }
        if c == "\r" { pendingCR = true } else { out.unicodeScalars.append(c) }
    }
    if pendingCR { out += "\n" }
    return out
}

/// `os.path.abspath`: joined to the working directory when relative, then
/// `os.path.normpath` — "." and empty segments dropped, ".." applied, and
/// POSIX's two leading slashes kept.
public func absolutePath(_ path: String) -> String {
    var scalars = Array(path.unicodeScalars)
    if scalars.first != "/" {
        scalars = Array((FileManager.default.currentDirectoryPath + "/").unicodeScalars) + scalars
    }
    var leading = 0
    while leading < scalars.count && scalars[leading] == "/" { leading += 1 }
    let prefix = leading == 2 ? "//" : "/"
    var parts: [[Unicode.Scalar]] = []
    for comp in scalars.split(separator: "/", omittingEmptySubsequences: true) {
        if comp.elementsEqual(["."]) { continue }
        if comp.elementsEqual([".", "."]) {
            if !parts.isEmpty { parts.removeLast() }
            continue
        }
        parts.append(Array(comp))
    }
    let joined = parts.map { String(String.UnicodeScalarView($0)) }.joined(separator: "/")
    return prefix + joined
}

/// Every occurrence of `old` in `s` replaced, matched code point for code point
/// as Python's str.replace matches (Foundation's replacement compares by
/// canonical equivalence).
func replaceAllText(_ s: String, _ old: String, _ new: String) -> String {
    let hay = Array(s.unicodeScalars)
    let needle = Array(old.unicodeScalars)
    guard !needle.isEmpty, hay.count >= needle.count else { return s }
    var out = ""
    var i = 0
    while i < hay.count {
        if i + needle.count <= hay.count && hay[i..<(i + needle.count)].elementsEqual(needle) {
            out += new
            i += needle.count
        } else {
            out.unicodeScalars.append(hay[i])
            i += 1
        }
    }
    return out
}

/// `os.path.dirname`.
func dirname(_ path: String) -> String {
    let scalars = Array(path.unicodeScalars)
    guard let slash = scalars.lastIndex(of: "/") else { return "" }
    var head = Array(scalars[..<(slash + 1)])
    if head.contains(where: { $0 != "/" }) {
        while head.last == "/" { head.removeLast() }
    }
    return String(String.UnicodeScalarView(head))
}

/// Locate the file for `use name`. nil for builtins. Throws ModuleError if
/// `name` cannot be found.
public func resolveModule(_ name: String, from fromPath: String?) throws -> String? {
    if BUILTIN_MODULES.contains(where: { sameText($0, name) }) { return nil }
    let base = fromPath.map { dirname(absolutePath($0)) } ?? FileManager.default.currentDirectoryPath
    let candidate = (base.unicodeScalars.last == "/" ? base : base + "/") + "\(name).planes"
    if FileManager.default.fileExists(atPath: candidate) { return candidate }
    throw missingModuleError(name)
}

/// Load a file and everything it uses, depth first. Returns (path, source) in
/// dependency order — imports before importers. Cycles raise.
public func loadGraph(_ path: String) throws -> [(path: String, src: String)] {
    var seen = Set<CodePoints>()
    var stack: [String] = []
    return try loadGraph(path, &seen, &stack)
}

private func loadGraph(_ path: String, _ seen: inout Set<CodePoints>,
                       _ stack: inout [String]) throws -> [(path: String, src: String)] {
    let key = absolutePath(path)
    if seen.contains(CodePoints(key)) { return [] }
    if stack.contains(where: { sameText($0, key) }) {
        let cycle = (stack + [key]).map(basename).joined(separator: " -> ")
        throw ModuleError(basename(path), "module cycle: \(cycle)",
                          "break the cycle by moving shared code to a third file")
    }
    let src = try readModuleSource(path)
    stack.append(key)
    var ordered: [(path: String, src: String)] = []
    for mod in try usesIn(src) {
        if let target = try resolveModule(mod, from: path) {
            ordered.append(contentsOf: try loadGraph(target, &seen, &stack))
        }
    }
    stack.removeLast()
    seen.insert(CodePoints(key))
    ordered.append((path, src))
    return ordered
}

/// Module names this source uses, read from tokens (not a full parse — a file
/// may call multi-word functions from a not-yet-loaded module).
public func usesIn(_ src: String) throws -> [String] {
    let toks = try tokenize(src)
    var out: [String] = []
    for i in toks.indices where sameText(toks[i].kind, "USE") && i + 1 < toks.count && sameText(toks[i + 1].kind, "NAME") {
        out.append(toks[i + 1].value)
    }
    return out
}

/// Renames declared by this file, as module -> [(old, new)], in first-declared
/// order with a later rename of the same name replacing the earlier one.
func renamesIn(_ src: String) throws -> NameMap<NameMap<String>> {
    let toks = try tokenize(src)
    func kind(_ j: Int) -> String { j < toks.count ? toks[j].kind : "EOF" }
    var out = NameMap<NameMap<String>>()
    var i = 0
    while i < toks.count {
        if sameText(toks[i].kind, "USE") && sameText(kind(i + 1), "NAME") {
            let mod = toks[i + 1].value
            var j = i + 2
            var pairs = NameMap<String>()
            while sameText(kind(j), "WITH") {
                j += 1
                var old: [String] = []
                while sameText(kind(j), "NAME") {
                    old.append(toks[j].value)
                    j += 1
                }
                if !sameText(kind(j), "AS") { break }
                j += 1
                var new: [String] = []
                while sameText(kind(j), "NAME") {
                    new.append(toks[j].value)
                    j += 1
                }
                if !old.isEmpty && !new.isEmpty { pairs[old.joined(separator: " ")] = new.joined(separator: " ") }
            }
            if !pairs.isEmpty {
                var merged = out[mod] ?? NameMap<String>()
                for (k, v) in pairs.entries { merged[k] = v }
                out[mod] = merged
            }
            i = j
            continue
        }
        i += 1
    }
    return out
}

/// `os.path.basename(path).replace(".planes", "")` — every occurrence, as
/// Python's str.replace removes.
func moduleNameOf(_ path: String) -> String {
    replaceAllText(basename(path), ".planes", "")
}

/// The name each file contributes, after the importer's renames: (path,
/// original, effective) triples.
func effectiveNames(_ graph: [(path: String, src: String)]) throws -> [(path: String, original: String, effective: String)] {
    var applied = NameMap<NameMap<String>>()
    for (_, src) in graph {
        for (mod, pairs) in try renamesIn(src).entries {
            var merged = applied[mod] ?? NameMap<String>()
            for (k, v) in pairs.entries { merged[k] = v }
            applied[mod] = merged
        }
    }
    var out: [(path: String, original: String, effective: String)] = []
    for (path, src) in graph {
        let pairs = applied[moduleNameOf(path)] ?? NameMap<String>()
        for name in try scan_names(src).keys {
            out.append((path, name, pairs[name] ?? name))
        }
    }
    return out
}

/// Every callable name in a loaded graph, after renames (both original and
/// renamed forms), each once.
public func namesInGraph(_ graph: [(path: String, src: String)]) throws -> [String] {
    var seen = Set<CodePoints>()
    var names: [String] = []
    for (_, original, effective) in try effectiveNames(graph) {
        for n in [original, effective] where seen.insert(CodePoints(n)).inserted { names.append(n) }
    }
    return names
}

/// path -> [(original name, name it is known by elsewhere)].
func renameMap(_ graph: [(path: String, src: String)]) throws -> NameMap<[(old: String, new: String)]> {
    var out = NameMap<[(old: String, new: String)]>()
    for (path, original, effective) in try effectiveNames(graph) where !sameText(original, effective) {
        var list = out[path] ?? []
        if let i = list.firstIndex(where: { sameText($0.old, original) }) {
            list[i].new = effective
        } else {
            list.append((original, effective))
        }
        out[path] = list
    }
    return out
}

/// Two files defining the same function name is an error.
public func checkCollisions(_ graph: [(path: String, src: String)]) throws {
    var owners = NameMap<[String]>()
    for (path, _, name) in try effectiveNames(graph) {
        owners[name] = (owners[name] ?? []) + [path]
    }
    let clashes = owners.entries.filter { Set($0.value.map(CodePoints.init)).count > 1 }
    if clashes.isEmpty { return }
    let sorted = stableSorted(clashes) { pyLess($0.key, $1.key) }
    var lines: [String] = []
    for (name, paths) in sorted {
        let whereText = pySortedUnique(paths.map(basename)).joined(separator: ", ")
        lines.append("'\(name)' is defined in \(whereText)")
    }
    let first = sorted[0].key
    let other = pySortedUnique(sorted[0].value.map(basename))[0]
    let otherMod = replaceAllText(other, ".planes", "")
    throw ModuleError(
        first,
        "two modules define the same name:\n  " + lines.joined(separator: "\n  "),
        "rename one at the point of use, e.g. `use \(otherMod) with \(first) as my \(first)`")
}
