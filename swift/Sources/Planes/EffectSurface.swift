// EffectSurface.swift — the Planes static effect analyser, ported from shapes.py.
// Named for the capability, not the tool: the capitalized product name is
// retired (planes v1.1 §29), and a Swift file name is capitalized.
//
// The Swift counterpart of js/shapes.mjs (and js/shapes_node.mjs's analyseFile),
// keeping its structure and names. Computes a program's total effect surface
// without running it: a function's effects include the effects of everything it
// calls, transitively, and calls can be mutually recursive, so this is a fixed
// point over the call graph, not a tree walk.
//
// Checked against shapes.py by canonical-form agreement (test_swift_shapes.py,
// test_swift_shapes_derivation.py): the published surface form
// (shapes_cli.as_json), the per-function breakdown, and the derivation graph.
// shapes.py is the specification. Where js/shapes.mjs and shapes.py part ways,
// this follows shapes.py:
//
//   * `+` folds text + text only. shapes.py's same-type test asks
//     `isinstance(left, (int, float))`, which a Planes `Number` is not, so a sum
//     of two known numbers widens to unknown there; js folds it.
//   * a known list or record reads as Python's `str()` of it, and `repr()` of a
//     text inside escapes every character Python does not count printable
//     (`'\xa0'`); js escapes only quote, backslash, tab, newline and return.
//   * `lower of` / `upper of` / `normalize of` a known value are Python's
//     `str.lower`, `str.upper` and `unicodedata.normalize("NFC", ...)`, fixed at
//     Python's Unicode version (PythonUnicode.swift); js uses JavaScript's.
//
// Every name, target and module is Planes text: keyed, compared and sorted by
// code point (swift/README.md rule 1), and every ordering that reaches output is
// insertion order or an explicit stable sort (rule 2).
import Foundation

// ================================================================ effect kinds

/// The closed vocabulary of boundaries, grouped as shapes.py groups them.
public let BOUNDARIES = ["network", "file", "console", "ambient", "foreign"]

/// A value the constant evaluator holds: what shapes.py's `const` returns, or
/// `unknown` — the analogue of its `Unknown` singleton — when it cannot pin the
/// value down statically. Widening to `unknown` is always sound.
public indirect enum StaticValue: Sendable {
    case unknown
    case text(String)
    case number(PlanesNumber)
    case bool(Bool)
    case list([StaticValue])
    case record([(key: String, value: StaticValue)])

    public var isUnknown: Bool {
        if case .unknown = self { return true }
        return false
    }
}

/// shapes.py's `UNKNOWN`.
public let UNKNOWN = StaticValue.unknown

// ---- Python str()/repr() analogues, so a fully-known list/record target reads
// exactly as shapes.py's as_text(str(v)) does.

/// Python's `repr()` of a `str`: single quotes unless the text holds a single
/// quote and no double quote, and every character Python does not count
/// printable escaped as `\xhh`, `\uhhhh` or `\Uhhhhhhhh`.
func pythonReprText(_ s: String) -> String {
    let scalars = s.unicodeScalars
    let q: Unicode.Scalar = scalars.contains("'") && !scalars.contains("\"") ? "\"" : "'"
    // Built as a String, appended to in place: a UnicodeScalarView appended to
    // from another string copies itself each time.
    var out = ""
    func escape(_ prefix: String, _ value: UInt32, _ width: Int) {
        let digits = String(value, radix: 16)
        out += prefix + String(repeating: "0", count: max(0, width - digits.count)) + digits
    }
    out.unicodeScalars.append(q)
    for c in scalars {
        if c == q || c == "\\" {
            out += "\\"
            out.unicodeScalars.append(c)
        } else if c == "\t" {
            out += "\\t"
        } else if c == "\n" {
            out += "\\n"
        } else if c == "\r" {
            out += "\\r"
        } else if c.value < 0x20 || c.value == 0x7F {
            escape("\\x", c.value, 2)
        } else if c.value < 0x7F || pythonIsPrintable(c) {
            out.unicodeScalars.append(c)
        } else if c.value <= 0xFF {
            escape("\\x", c.value, 2)
        } else if c.value <= 0xFFFF {
            escape("\\u", c.value, 4)
        } else {
            escape("\\U", c.value, 8)
        }
    }
    out.unicodeScalars.append(q)
    return out
}

func pyRepr(_ v: StaticValue) -> String {
    if case let .text(s) = v { return pythonReprText(s) }
    return pyStr(v)
}

func pyStr(_ v: StaticValue) -> String {
    switch v {
    case .unknown: return "{...}"
    case let .bool(b): return b ? "True" : "False"
    case let .number(n): return n.text()
    case let .text(s): return s
    case let .list(items): return "[" + items.map(pyRepr).joined(separator: ", ") + "]"
    case let .record(entries):
        return "{" + entries.map { "\(pythonReprText($0.key)): \(pyRepr($0.value))" }.joined(separator: ", ") + "}"
    }
}

// Python's str.lower, str.upper, NFC and str.isprintable are in
// PythonUnicode.swift, at Python's Unicode version.

/// Code-point order, Python's `<` on `str` — which is UTF-8 byte order, so it
/// compares the bytes.
func pyLess(_ a: String, _ b: String) -> Bool {
    a.utf8.lexicographicallyPrecedes(b.utf8)
}

/// `sorted()` of Planes text: code-point order.
func pySorted<S: Sequence>(_ xs: S) -> [String] where S.Element == String {
    Array(xs).sorted(by: pyLess)
}

/// `sorted(set(xs))` of Planes text.
func pySortedUnique<S: Sequence>(_ xs: S) -> [String] where S.Element == String {
    var seen = Set<CodePoints>()
    var out: [String] = []
    for x in xs where seen.insert(CodePoints(x)).inserted { out.append(x) }
    return pySorted(out)
}

func sameOptionalText(_ a: String?, _ b: String?) -> Bool {
    switch (a, b) {
    case (nil, nil): return true
    case let (x?, y?): return sameText(x, y)
    default: return false
    }
}

/// Text as a set or dictionary key, equal and hashed by code point like
/// `CodePoints`, without copying the scalars out: two strings have the same code
/// points exactly when they have the same UTF-8 bytes. An effect's target can be
/// long, and the fixed point keys every effect many times over.
struct TextKey: Hashable {
    let text: String

    init(_ text: String) { self.text = text }

    static func == (a: TextKey, b: TextKey) -> Bool {
        a.text.utf8.elementsEqual(b.text.utf8)
    }

    func hash(into hasher: inout Hasher) {
        var copy = text
        copy.withUTF8 { hasher.combine(bytes: UnsafeRawBufferPointer($0)) }
    }
}

/// A stable sort, as Python's `sorted` is. Swift's `sort` does not promise one.
func stableSorted<T>(_ xs: [T], by less: (T, T) -> Bool) -> [T] {
    xs.enumerated().sorted { a, b in
        if less(a.element, b.element) { return true }
        if less(b.element, a.element) { return false }
        return a.offset < b.offset
    }.map(\.element)
}

// The sort shapes.py applies everywhere: (boundary, kind, target).
func effLess(_ a: Effect, _ b: Effect) -> Bool {
    if !sameText(a.boundary, b.boundary) { return pyLess(a.boundary, b.boundary) }
    if !sameText(a.kind, b.kind) { return pyLess(a.kind, b.kind) }
    return pyLess(a.target, b.target)
}

func sortedEffects(_ xs: [Effect]) -> [Effect] {
    stableSorted(xs, by: effLess)
}

/// An insertion-ordered map keyed by Planes text — a Python `dict` / js `Map`
/// whose keys are names. Re-setting a key keeps its original position.
struct NameMap<Value> {
    private(set) var keys: [String] = []
    private var index: [CodePoints: Int] = [:]
    private var values: [Value] = []

    init() {}

    subscript(_ key: String) -> Value? {
        get { index[CodePoints(key)].map { values[$0] } }
        set {
            let k = CodePoints(key)
            if let i = index[k] {
                if let v = newValue { values[i] = v }
            } else if let v = newValue {
                index[k] = values.count
                keys.append(key)
                values.append(v)
            }
        }
    }

    func has(_ key: String) -> Bool { index[CodePoints(key)] != nil }
    var isEmpty: Bool { keys.isEmpty }
    var entries: [(key: String, value: Value)] { Array(zip(keys, values)) }
}

// ================================================================ derivation and effects

/// One node in the static derivation graph. Mirrors shapes.py's StaticDeriv:
/// same field names, same meanings. A class, so the graph shares nodes by
/// identity as shapes.py's frozen dataclasses do and `originsOf` walks each
/// once.
public final class StaticDeriv: @unchecked Sendable {
    public let kind: String
    public let label: String
    public let inputs: [StaticDeriv]
    public let origin: String?
    public let file: String?

    public init(_ kind: String, _ label: String, _ inputs: [StaticDeriv] = [], _ origin: String? = nil,
                _ file: String? = nil) {
        self.kind = kind
        self.label = label
        self.inputs = inputs
        self.origin = origin
        self.file = file
    }
}

/// One thing a program can do at a boundary. `derivation` is excluded from the
/// value identity (`key`), exactly as shapes.py excludes it from hash/equality:
/// two structurally identical effects reached by different paths must remain one
/// effect, or the fixed point may not terminate.
public struct Effect: CustomStringConvertible, @unchecked Sendable {
    public let kind: String
    public let boundary: String
    public let target: String
    public let computed: Bool
    public let site: Int
    public let claimed: Bool
    public let derivation: StaticDeriv?

    public init(_ kind: String, _ boundary: String, _ target: String, _ computed: Bool = false,
                site: Int = 0, claimed: Bool = false, derivation: StaticDeriv? = nil) {
        self.kind = kind
        self.boundary = boundary
        self.target = target
        self.computed = computed
        self.site = site
        self.claimed = claimed
        self.derivation = derivation
    }

    struct Key: Hashable {
        let kind: TextKey
        let boundary: TextKey
        let target: TextKey
        let computed: Bool
        let site: Int
        let claimed: Bool
    }

    /// The value identity — every compared field, derivation excluded.
    var key: Key {
        Key(kind: TextKey(kind), boundary: TextKey(boundary), target: TextKey(target),
            computed: computed, site: site, claimed: claimed)
    }

    /// (kind, target, computed) — the identity `declared`, `render` and `diff`
    /// dedupe by.
    struct ShortKey: Hashable {
        let kind: TextKey
        let target: TextKey
        let computed: Bool
    }

    var shortKey: ShortKey { ShortKey(kind: TextKey(kind), target: TextKey(target), computed: computed) }

    public var description: String {
        if sameText(kind, "unknown") {
            return "unknown — \(target) declares no effects"
        }
        var t = target
        if computed && t.unicodeScalars.last != ")" { t += " (computed)" }
        if claimed { t += " (declared, not verified)" }
        return "\(kind) \(t)"
    }
}

/// A value-identity set of Effects: first-wins on collision (keeping the earlier
/// derivation, as Python set union does), insertion-ordered. Ordering never
/// reaches output — every surface field is sorted — but first-wins does, because
/// it decides which derivation an effect carries.
final class EffectSet {
    private var order: [Effect] = []
    private var keys = Set<Effect.Key>()

    init() {}

    init<S: Sequence>(_ items: S) where S.Element == Effect {
        union(items)
    }

    func add(_ e: Effect) {
        if keys.insert(e.key).inserted { order.append(e) }
    }

    @discardableResult
    func union<S: Sequence>(_ items: S) -> EffectSet where S.Element == Effect {
        for e in items { add(e) }
        return self
    }

    @discardableResult
    func union(_ other: EffectSet) -> EffectSet {
        union(other.order)
    }

    func copy() -> EffectSet { EffectSet(order) }

    func subsetOf(_ other: EffectSet) -> Bool { keys.isSubset(of: other.keys) }

    var count: Int { order.count }
    var list: [Effect] { order }
    func sorted() -> [Effect] { sortedEffects(order) }
}

// ================================================================ the surface

public final class Surface {
    /// What running this file performs.
    public let effects: [Effect]
    /// name -> sorted effects, in declaration order.
    public let functions: [(name: String, effects: [Effect])]
    /// The modules `use`d, each once.
    public let modules: [String]
    public let unresolved: [String]
    public let foreign: [Effect]
    /// Routes from an entry point to `sine` or `root`.
    public let approximate: [[String]]

    public init(effects: [Effect] = [], functions: [(name: String, effects: [Effect])] = [],
                modules: [String] = [], unresolved: [String] = [], foreign: [Effect] = [],
                approximate: [[String]] = []) {
        self.effects = effects
        self.functions = functions
        var seen = Set<CodePoints>()
        self.modules = modules.filter { seen.insert(CodePoints($0)).inserted }
        self.unresolved = unresolved
        self.foreign = foreign
        self.approximate = approximate
    }

    /// Every effect any function here can perform, plus top-level ones. Includes
    /// foreign declarations even when nothing calls them.
    public private(set) lazy var declared: [Effect] = {
        var out = effects
        for f in functions { out.append(contentsOf: f.effects) }
        struct KB: Hashable { let kind: TextKey; let boundary: TextKey }
        var resolved = Set<KB>()
        for e in out where !e.computed { resolved.insert(KB(kind: TextKey(e.kind), boundary: TextKey(e.boundary))) }
        for e in foreign {
            if e.computed && resolved.contains(KB(kind: TextKey(e.kind), boundary: TextKey(e.boundary))) { continue }
            out.append(e)
        }
        var seen = Set<Effect.ShortKey>()
        var uniq: [Effect] = []
        for e in out where seen.insert(e.shortKey).inserted { uniq.append(e) }
        return sortedEffects(uniq)
    }()

    public func isLibrary() -> Bool {
        let anyFn = functions.contains { !$0.effects.isEmpty }
        return effects.isEmpty && (anyFn || !foreign.isEmpty)
    }

    public func kinds() -> [String] { pySortedUnique(declared.map(\.kind)) }
    public func boundaries() -> [String] { pySortedUnique(declared.map(\.boundary)) }
    public func touches(_ boundary: String) -> Bool { declared.contains { sameText($0.boundary, boundary) } }
    public func at(_ boundary: String) -> [Effect] { declared.filter { sameText($0.boundary, boundary) } }
    public func isPure() -> Bool { declared.isEmpty }

    /// The third question (checkpoint §232), answered for numerics. Does this
    /// program produce APPROXIMATE values? Derivable without running it: does the
    /// call graph reach `sine` or `root`.
    public func producesApproximate() -> Bool { !approximate.isEmpty }

    /// "always" if any route reaches an operation that approximates at every
    /// argument, "sometimes" if every route ends at one that only sometimes
    /// does, and nil when there is no route at all.
    public func approximationStrength() -> String? {
        var found: String?
        for route in approximate {
            let strength = route.last.flatMap(approximationSourceStrength)
            if strength == "always" { return "always" }
            if strength == "sometimes" { found = "sometimes" }
        }
        return found
    }

    /// The one line the surface prints about numbers.
    public func approximationSentence() -> String {
        if approximationStrength() == "sometimes" {
            return "numbers: may be approximate — this program reaches `root`, " +
                "which is exact when its argument is a perfect square"
        }
        return "numbers: approximate — this program reaches `sine`"
    }

    public func approximationRoutes() -> [String] { approximate.map { $0.joined(separator: "  ->  ") } }
    public func hasUnknowns() -> Bool { declared.contains { sameText($0.kind, "unknown") } }
    public func claimsList() -> [Effect] { declared.filter(\.claimed) }

    public func targets(_ kind: String? = nil) -> [String] {
        pySortedUnique(declared.filter { kind == nil || sameText($0.kind, kind!) }.map(\.target))
    }

    public func derivationOf(_ effect: Effect) -> StaticDeriv? { effect.derivation }

    /// Every name and file this effect's target provably derives from — the
    /// static analogue of interp.origins(). Walks the derivation graph; not
    /// deduplicated, matching shapes.py (callers that want a set dedupe).
    public func originsOf(_ effect: Effect) -> [(name: String, file: String?)] {
        guard let node = effect.derivation else { return [] }
        var found: [(name: String, file: String?)] = []
        var seen = Set<ObjectIdentifier>()
        func walk(_ n: StaticDeriv) {
            if !seen.insert(ObjectIdentifier(n)).inserted { return }
            if sameText(n.kind, "name") || sameText(n.kind, "param") { found.append((n.label, n.file)) }
            for i in n.inputs { walk(i) }
        }
        walk(node)
        return found
    }

    public func declaredButUnused() -> [String] {
        let kinds = try? effectKinds()
        var mods = Set<CodePoints>()
        for e in declared {
            if let b = kinds?[e.kind] { mods.insert(CodePoints(sameText(b, "network") ? "http" : b)) }
        }
        return pySorted(modules.filter { !mods.contains(CodePoints($0)) })
    }

    public func usedButUndeclared() -> [Effect] {
        let mods = Set(modules.map(CodePoints.init))
        return declared.filter { e in
            let mod = sameText(e.boundary, "network") ? "http" : e.boundary
            return (sameText(e.boundary, "network") || sameText(e.boundary, "file")) && !mods.contains(CodePoints(mod))
        }
    }

    public func render() -> String {
        var lines: [String] = []
        if isPure() {
            if producesApproximate() {
                return "pure — this program touches nothing outside itself\n" +
                    approximationSentence() + "\n" +
                    approximationRoutes().map { "  \($0)" }.joined(separator: "\n")
            }
            return "pure — this program touches nothing outside itself"
        }
        if isLibrary() {
            lines.append("(library — nothing runs at load; these are what its functions can do)")
        }
        for b in BOUNDARIES {
            let here = at(b)
            if here.isEmpty { continue }
            lines.append("\(b):")
            var seen = Set<Effect.ShortKey>()
            for e in here where seen.insert(e.shortKey).inserted {
                lines.append("  \(e)")
            }
        }
        if producesApproximate() {
            lines.append(approximationSentence())
            for route in approximationRoutes() { lines.append("  \(route)") }
        }
        if !unresolved.isEmpty {
            lines.append("unresolved calls: \(pySortedUnique(unresolved).joined(separator: ", "))")
        }
        if hasUnknowns() {
            lines.append("this surface is incomplete: a foreign function states no effects")
        }
        return lines.joined(separator: "\n")
    }
}

// ================================================================ constants

/// Statically known values, scoped like the runtime environment. Stores a
/// (value, StaticDeriv) pair per name. Widening to UNKNOWN is always sound.
final class Consts {
    private var vals: [CodePoints: (StaticValue, StaticDeriv)] = [:]
    private let parent: Consts?

    init(_ parent: Consts? = nil) { self.parent = parent }

    func get(_ name: String) -> (StaticValue, StaticDeriv) {
        if let v = vals[CodePoints(name)] { return v }
        if let parent { return parent.get(name) }
        return (UNKNOWN, StaticDeriv("unknown", name))
    }

    func set(_ name: String, _ value: StaticValue, _ node: StaticDeriv) {
        vals[CodePoints(name)] = (value, node)
    }

    func child() -> Consts { Consts(self) }
}

// ================================================================ approximation
//
// TWO SOURCES, AND THEY DO NOT MEAN THE SAME THING. `sine` approximates at EVERY
// argument, so reaching it promises approximate values. `root` approximates only
// when its argument is not a perfect square (square-root-spec.md §2), so reaching
// it promises nothing — `root of 9` is exactly 3.

let APPROXIMATION_SOURCES: [(name: String, strength: String)] = [("sine", "always"), ("root", "sometimes")]
let APPROXIMATION_SOURCE = "sine"  // the always-source, where one is named

func approximationSourceStrength(_ name: String) -> String? {
    APPROXIMATION_SOURCES.first { sameText($0.name, name) }?.strength
}

/// Every name a subtree calls or reads. Structure-generic rather than a case per
/// node kind: a node type added later cannot hide a call from this pass the way
/// it could from a switch someone forgot to extend.
func calledNames(_ value: ASTValue, _ out: inout Set<CodePoints>) {
    switch value {
    case let .node(n):
        if let c = n as? AST.Call { out.insert(CodePoints(c.name)) }
        if let v = n as? AST.Var { out.insert(CodePoints(v.name)) }
        for f in n.fields { calledNames(f.value, &out) }
    case let .list(items), let .tuple(items):
        for x in items { calledNames(x, &out) }
    default:
        return
    }
}

func calledNames(_ nodes: [AST.Node]) -> Set<CodePoints> {
    var out = Set<CodePoints>()
    calledNames(.list(nodes.map { .node($0) }), &out)
    return out
}

// ================================================================ analyser

public final class Analyser {
    var funcs = NameMap<AST.FuncDef>()  // name -> FuncDef, declaration order
    var modules: [String] = []
    var unresolved: [String] = []
    var depth = 0
    private var recCache: [CodePoints: Bool] = [:]
    var local = NameMap<String>()  // original name -> exported name, for renames
    var foreigns = NameMap<AST.Foreign>()
    var funcFile = NameMap<String?>()
    var foreignFile = NameMap<String?>()
    public var entryFile: String?
    var currentFile: String?

    private let kindsTable: TextTable<String>
    private let builtins: Set<CodePoints>

    public init() throws {
        kindsTable = try effectKinds()
        builtins = try builtinNames()
    }

    private func isBuiltinName(_ name: String) -> Bool { builtins.contains(CodePoints(name)) }

    /// `self.func_file.get(name, default)`: a stored nil is a value, not a miss.
    private func fileOf(_ name: String, _ fallback: String?) -> String? {
        if let stored = funcFile[name] { return stored }
        return fallback
    }

    public func analyse(_ src: String) throws -> Surface {
        let prog = try parse(src)
        collectDeclarations(prog, NameMap(), entryFile)
        return analyseProg(prog)
    }

    func analyseProg(_ prog: [AST.Node]) -> Surface {
        // Fixed point over the call graph. A function's effect set grows until it
        // stops; recursion terminates because sets only grow and the vocabulary is
        // finite. Parameters are UNKNOWN here — the generic surface, true for any
        // call site.
        var fnEffects = NameMap<EffectSet>()
        for name in funcs.keys { fnEffects[name] = EffectSet() }
        var changed = true
        var rounds = 0
        while changed {
            changed = false
            rounds += 1
            if rounds > 200 { break }
            for (name, fn) in funcs.entries {
                let inner = Consts()
                currentFile = fileOf(name, entryFile)
                for p in fn.params {
                    inner.set(p, UNKNOWN, StaticDeriv("param", p, [], nil, currentFile))
                }
                let found = EffectSet()
                for stmt in fn.body { found.union(walk(stmt, fnEffects, inner)) }
                let cur = fnEffects[name]!
                if !found.subsetOf(cur) {
                    cur.union(found)
                    changed = true
                }
            }
        }

        // Top-level statements, now that function effects are known.
        let top = EffectSet()
        let topConsts = Consts()
        currentFile = entryFile
        for stmt in prog {
            if stmt is AST.FuncDef { continue }
            top.union(walk(stmt, fnEffects, topConsts))
        }

        let functions = fnEffects.entries.map { (name: $0.key, effects: $0.value.sorted()) }

        let foreignSet = EffectSet()
        for (_, d) in foreigns.entries { foreignSet.union(foreignEffects(d)) }

        return Surface(
            effects: top.sorted(),
            functions: functions,
            modules: modules,
            unresolved: unresolved,
            foreign: foreignSet.sorted(),
            approximate: approximationRoutes(prog)
        )
    }

    // Every route from an entry point to `sine`, shortest first. The top level is
    // the right question for an application, and each declared function the
    // right question for a library. Only functions declared in THIS file are
    // entry points: approximation is production, not authority. A user function
    // of the same name shadows the builtin, and then that name is not a source.
    func approximationRoutes(_ prog: [AST.Node]) -> [[String]] {
        let sources = pySorted(APPROXIMATION_SOURCES.map(\.name).filter { !funcs.has($0) })
        if sources.isEmpty { return [] }

        var calls = NameMap<Set<CodePoints>>()
        for (name, fn) in funcs.entries { calls[name] = calledNames(fn.body) }
        let topCalls = calledNames(prog.filter { !($0 is AST.FuncDef) })

        func sortedNames(_ s: Set<CodePoints>) -> [String] { s.sorted().map(\.string) }

        // Breadth-first, so the route reported is the shortest one — and ONE
        // TARGET AT A TIME.
        func routeFrom(_ entry: String, _ seeds: Set<CodePoints>, _ target: String) -> [String]? {
            var queue = sortedNames(seeds).map { (name: $0, path: [entry, $0]) }
            var seen = seeds
            var head = 0
            while head < queue.count {
                let (name, path) = queue[head]
                head += 1
                if sameText(name, target) { return path }
                for nxt in sortedNames(calls[name] ?? []) where seen.insert(CodePoints(nxt)).inserted {
                    queue.append((nxt, path + [nxt]))
                }
            }
            return nil
        }

        func routesFrom(_ entry: String, _ seeds: Set<CodePoints>) -> [[String]] {
            sources.compactMap { routeFrom(entry, seeds, $0) }
        }

        var found = routesFrom("(top level)", topCalls)
        for name in pySorted(funcs.keys) {
            if !sameOptionalText(fileOf(name, entryFile), entryFile) { continue }
            found.append(contentsOf: routesFrom(name, calls[name]!))
        }
        return found
    }

    func collectDeclarations(_ prog: [AST.Node], _ renames: NameMap<String>, _ file: String?) {
        func scan(_ node: AST.Node) {
            if let f = node as? AST.Foreign {
                let name = renames[f.name] ?? f.name
                foreigns[name] = f
                foreignFile[name] = .some(file)
                if let renamed = renames[f.name] { local[f.name] = renamed }
                return
            }
            if let fn = node as? AST.FuncDef {
                let exported = renames[fn.name] ?? fn.name
                funcs[exported] = fn
                funcFile[exported] = .some(file)
                if !sameText(exported, fn.name) { local[fn.name] = exported }
                for s in fn.body { scan(s) }
            } else if let u = node as? AST.Use {
                if !modules.contains(where: { sameText($0, u.module) }) { modules.append(u.module) }
            } else if let i = node as? AST.If {
                for s in i.then + i.els { scan(s) }
            } else if let fe = node as? AST.ForEach {
                for s in fe.body { scan(s) }
            }
        }
        for stmt in prog { scan(stmt) }
    }

    private func unknownDeriv(_ name: String) -> StaticDeriv {
        StaticDeriv("unknown", name, [], nil, currentFile)
    }

    // ---- the walk. Returns an EffectSet; never executes anything.
    func walk(_ node: AST.Node?, _ fnEffects: NameMap<EffectSet>, _ consts: Consts) -> EffectSet {
        guard let node else { return EffectSet() }
        let out = EffectSet()

        if let b = node as? AST.Builtin {
            out.union(walk(b.arg, fnEffects, consts))
            if sameText(b.name, "ask") || sameText(b.name, "read") {
                let (target, computed, deriv) = describe(b.arg, consts)
                out.add(Effect(b.name, kindsTable[b.name]!, target, computed, derivation: deriv))
            }
            return out
        }

        if let w = node as? AST.WriteTo {
            out.union(walk(w.value, fnEffects, consts))
            out.union(walk(w.dest, fnEffects, consts))
            let (target, computed, deriv) = describe(w.dest, consts)
            out.add(Effect("write", "file", target, computed, site: w.line, derivation: deriv))
            return out
        }

        if let s = node as? AST.Show {
            out.union(walk(s.expr, fnEffects, consts))
            let (target, computed, deriv) = describe(s.expr, consts)
            out.add(Effect("show", "console", target, computed, site: s.line, derivation: deriv))
            return out
        }

        if let c = node as? AST.Call {
            for a in c.args { out.union(walk(a, fnEffects, consts)) }
            if let boundary = kindsTable[c.name], !funcs.has(c.name) {
                let (target, computed, deriv) = describe(c.args.first, consts)
                out.add(Effect(c.name, boundary, target, computed, site: c.line, derivation: deriv))
                return out
            }
            let target = local[c.name] ?? c.name
            if let decl = foreigns[target] {
                out.union(foreignEffects(decl, c.args, consts))
                return out
            }
            if fnEffects.has(target) {
                out.union(specialise(target, c.args, fnEffects, consts))
            } else if !funcs.has(target) && !isBuiltinName(target) {
                unresolved.append(c.name)
            }
            return out
        }

        if let v = node as? AST.Var {
            if let es = fnEffects[v.name] { return es.copy() }
            return EffectSet()
        }

        if let a = node as? AST.Assign {
            out.union(walk(a.expr, fnEffects, consts))
            let (value, n) = const_(a.expr, consts)
            consts.set(a.name, value, n)
            return out
        }

        if let g = node as? AST.Give { return walk(g.expr, fnEffects, consts) }
        if let w = node as? AST.Why { return walk(w.expr, fnEffects, consts) }
        if let f = node as? AST.Fail { return walk(f.message, fnEffects, consts) }

        if let b = node as? AST.BinOp {
            return walk(b.left, fnEffects, consts).union(walk(b.right, fnEffects, consts))
        }

        if let n = node as? AST.Not { return walk(n.expr, fnEffects, consts) }

        if let r = node as? AST.Round {
            return walk(r.value, fnEffects, consts).union(walk(r.places, fnEffects, consts))
        }

        if let f = node as? AST.Field { return walk(f.obj, fnEffects, consts) }

        if let l = node as? AST.ListLit {
            for i in l.items { out.union(walk(i, fnEffects, consts)) }
            return out
        }

        if let r = node as? AST.RecordLit {
            for f in r.fieldList { out.union(walk(f.expr, fnEffects, consts)) }
            return out
        }

        if let r = node as? AST.RecordUpdate {
            out.union(walk(r.base, fnEffects, consts))
            for f in r.fieldList { out.union(walk(f.expr, fnEffects, consts)) }
            return out
        }

        if let l = node as? AST.ListPlus {
            return walk(l.base, fnEffects, consts).union(walk(l.item, fnEffects, consts))
        }

        if let w = node as? AST.When {
            out.union(walk(w.subject, fnEffects, consts))
            for p in w.pattern {
                if case let .match(arg) = p.matcher { out.union(walk(arg, fnEffects, consts)) }
            }
            let inner = consts.child()
            for p in w.pattern {
                if case .bind = p.matcher { inner.set(p.field, UNKNOWN, unknownDeriv(p.field)) }
            }
            for s in w.body + w.els { out.union(walk(s, fnEffects, inner)) }
            for name in assignedIn(w.body + w.els) { consts.set(name, UNKNOWN, unknownDeriv(name)) }
            return out
        }

        if let o = node as? AST.OrFail {
            out.union(walk(o.expr, fnEffects, consts))
            if let handler = o.handler {
                let inner = consts.child()
                inner.set(o.tag, UNKNOWN, unknownDeriv(o.tag))
                for s in handler { out.union(walk(s, fnEffects, inner)) }
                for name in assignedIn(handler) { consts.set(name, UNKNOWN, unknownDeriv(name)) }
            }
            return out
        }

        if let fe = node as? AST.ForEach {
            out.union(walk(fe.source, fnEffects, consts))
            let inner = consts.child()
            inner.set(fe.variable, UNKNOWN, unknownDeriv(fe.variable))
            out.union(walk(fe.whereClause, fnEffects, inner))
            for s in fe.body { out.union(walk(s, fnEffects, inner)) }
            for name in assignedIn(fe.body) { consts.set(name, UNKNOWN, unknownDeriv(name)) }
            return out
        }

        if let i = node as? AST.If {
            out.union(walk(i.cond, fnEffects, consts))
            for s in i.then + i.els { out.union(walk(s, fnEffects, consts.child())) }
            for name in assignedIn(i.then + i.els) { consts.set(name, UNKNOWN, unknownDeriv(name)) }
            return out
        }

        return EffectSet()  // FuncDef is handled in the fixed point, not inline
    }

    func foreignEffects(_ decl: AST.Foreign, _ args: [AST.Node]? = nil, _ consts: Consts? = nil) -> EffectSet {
        if !decl.declared {
            return EffectSet([
                Effect("unknown", "foreign", decl.target, true, site: decl.line, claimed: true,
                       derivation: StaticDeriv("foreign", decl.target, [], nil, currentFile)),
            ])
        }
        let out = EffectSet()
        for eff in decl.effects {
            let boundary = kindsTable[eff.kind] ?? "foreign"
            let (target, computed, deriv) = claimTarget(decl, eff.target, args, consts)
            out.add(Effect(eff.kind, boundary, target, computed, site: decl.line, claimed: true, derivation: deriv))
        }
        return out
    }

    func claimTarget(_ decl: AST.Foreign, _ claim: AST.ClaimTarget?, _ args: [AST.Node]?,
                     _ consts: Consts?) -> (String, Bool, StaticDeriv) {
        let origin = "foreign:\(decl.target)"
        guard let claim else {
            return ("\(decl.target) (destination not stated)", true,
                    StaticDeriv("foreign", decl.target, [], origin, currentFile))
        }
        switch claim {
        case let .literal(value):
            return (value, false, StaticDeriv("literal", "\"\(escapeStringLiteral(value))\"", [], nil, currentFile))
        case let .param(value):
            // A parameter. Resolve it from the call site if there is one.
            if let args, let consts, let i = decl.params.firstIndex(where: { sameText($0, value) }), i < args.count {
                let (v, n) = const_(args[i], consts)
                if !v.isUnknown {
                    return (asText(v), false, StaticDeriv("foreign", decl.target, [n], origin, currentFile))
                }
                let (text, n2) = pattern(args[i], consts)
                return (text, true, StaticDeriv("foreign", decl.target, [n2], origin, currentFile))
            }
            return ("{...}", true, StaticDeriv("foreign", decl.target, [], origin, currentFile))
        }
    }

    func specialise(_ name: String, _ callArgs: [AST.Node], _ fnEffects: NameMap<EffectSet>,
                    _ consts: Consts) -> EffectSet {
        let generic = fnEffects[name]!.copy()
        guard let fn = funcs[name], depth <= 4 else { return generic }
        if isRecursive(name) { return generic }
        let argPairs = callArgs.map { const_($0, consts) }
        if argPairs.count != fn.params.count || argPairs.allSatisfy({ $0.0.isUnknown }) {
            return generic
        }

        let calleeFile = fileOf(name, currentFile)
        let inner = Consts()
        for (p, pair) in zip(fn.params, argPairs) {
            inner.set(p, pair.0, StaticDeriv("param", p, [pair.1], nil, calleeFile))
        }

        let prevFile = currentFile
        currentFile = calleeFile
        depth += 1
        let special = EffectSet()
        for s in fn.body { special.union(walk(s, fnEffects, inner)) }
        depth -= 1
        currentFile = prevFile

        // Keep every generic effect whose target the specialised pass did not
        // sharpen. Never drop an effect kind the generic pass found.
        let sharpened = EffectSet()
        let specialList = special.list
        for g in generic.list {
            let better = specialList.filter { sameText($0.kind, g.kind) && sameText($0.boundary, g.boundary) && !$0.computed }
            if g.computed && !better.isEmpty { sharpened.union(better) } else { sharpened.add(g) }
        }
        let genericKinds = Set(generic.list.map { CodePoints($0.kind) })
        return sharpened.union(specialList.filter { !genericKinds.contains(CodePoints($0.kind)) })
    }

    func isRecursive(_ name: String) -> Bool {
        if let cached = recCache[CodePoints(name)] { return cached }
        var seen = Set<CodePoints>()
        var stack = [name]
        var found = false
        outer: while let cur = stack.popLast() {
            guard let fn = funcs[cur] else { continue }
            for callee in callsIn(fn.body) {
                if sameText(callee, name) {
                    found = true
                    break outer
                }
                if seen.insert(CodePoints(callee)).inserted { stack.append(callee) }
            }
        }
        recCache[CodePoints(name)] = found
        return found
    }

    /// Names assigned anywhere in `stmts`, each once — a Python set, iterated only
    /// to widen each name, so its order never reaches output.
    func assignedIn(_ stmts: [AST.Node]) -> [String] {
        var seen = Set<CodePoints>()
        var out: [String] = []
        func scan(_ n: AST.Node?) {
            guard let n else { return }
            if let a = n as? AST.Assign {
                if seen.insert(CodePoints(a.name)).inserted { out.append(a.name) }
                scan(a.expr)
            } else if let i = n as? AST.If {
                for s in i.then + i.els { scan(s) }
            } else if let fe = n as? AST.ForEach {
                for s in fe.body { scan(s) }
            } else if let fn = n as? AST.FuncDef {
                for s in fn.body { scan(s) }
            } else if let o = n as? AST.OrFail {
                scan(o.expr)
                for s in o.handler ?? [] { scan(s) }
            } else if let w = n as? AST.When {
                for s in w.body + w.els { scan(s) }
            }
        }
        for s in stmts { scan(s) }
        return out
    }

    /// Every function name `stmts` calls, in first-seen order (a set in
    /// shapes.py; the order only steers `isRecursive`'s search, never its answer).
    func callsIn(_ stmts: [AST.Node]) -> [String] {
        var seen = Set<CodePoints>()
        var out: [String] = []
        func add(_ name: String) {
            if seen.insert(CodePoints(name)).inserted { out.append(name) }
        }
        func scan(_ n: AST.Node?) {
            guard let n else { return }
            switch n {
            case let c as AST.Call:
                add(c.name)
                for a in c.args { scan(a) }
            case let v as AST.Var:
                if funcs.has(v.name) { add(v.name) }
            case let g as AST.Give: scan(g.expr)
            case let w as AST.Why: scan(w.expr)
            case let s as AST.Show: scan(s.expr)
            case let x as AST.Not: scan(x.expr)
            case let a as AST.Assign: scan(a.expr)
            case let b as AST.BinOp:
                scan(b.left)
                scan(b.right)
            case let f as AST.Field: scan(f.obj)
            case let b as AST.Builtin: scan(b.arg)
            case let o as AST.OrFail:
                scan(o.expr)
                for s in o.handler ?? [] { scan(s) }
            case let w as AST.WriteTo:
                scan(w.value)
                scan(w.dest)
            case let l as AST.ListLit:
                for i in l.items { scan(i) }
            case let fe as AST.ForEach:
                scan(fe.source)
                scan(fe.whereClause)
                for s in fe.body { scan(s) }
            case let i as AST.If:
                scan(i.cond)
                for s in i.then + i.els { scan(s) }
            case let fn as AST.FuncDef:
                for s in fn.body { scan(s) }
            case let r as AST.RecordLit:
                for f in r.fieldList { scan(f.expr) }
            case let r as AST.RecordUpdate:
                scan(r.base)
                for f in r.fieldList { scan(f.expr) }
            case let l as AST.ListPlus:
                scan(l.base)
                scan(l.item)
            case let w as AST.When:
                scan(w.subject)
                for p in w.pattern {
                    if case let .match(arg) = p.matcher { scan(arg) }
                }
                for s in w.body + w.els { scan(s) }
            default:
                return
            }
        }
        for s in stmts { scan(s) }
        return out
    }

    // ---- constant evaluation. Returns (value, StaticDeriv).
    func const_(_ node: AST.Node?, _ consts: Consts) -> (StaticValue, StaticDeriv) {
        let F = currentFile
        guard let node else { return (UNKNOWN, StaticDeriv("unknown", "nothing", [], nil, F)) }

        if let s = node as? AST.Str {
            return (.text(s.value), StaticDeriv("literal", "\"\(escapeStringLiteral(s.value))\"", [], nil, F))
        }
        if let n = node as? AST.Num {
            return (.number(n.value), StaticDeriv("literal", n.value.text(), [], nil, F))
        }
        if let b = node as? AST.Bool {
            return (.bool(b.value), StaticDeriv("literal", b.value ? "true" : "false", [], nil, F))
        }
        if let v = node as? AST.Var {
            let (value, stored) = consts.get(v.name)
            return (value, StaticDeriv("name", v.name, [stored], nil, F))
        }
        if let r = node as? AST.RecordLit {
            let pairs = r.fieldList.map { (key: $0.name, pair: const_($0.expr, consts)) }
            let inputs = pairs.map(\.pair.1)
            if pairs.contains(where: { $0.pair.0.isUnknown }) {
                return (UNKNOWN, StaticDeriv("unknown", "{record}", inputs, nil, F))
            }
            return (.record(recordFrom([], pairs.map { ($0.key, $0.pair.0) })),
                    StaticDeriv("literal", "{record}", inputs, nil, F))
        }
        if let l = node as? AST.ListLit {
            let items = l.items.map { const_($0, consts) }
            let inputs = items.map(\.1)
            if items.contains(where: { $0.0.isUnknown }) {
                return (UNKNOWN, StaticDeriv("unknown", "[list]", inputs, nil, F))
            }
            return (.list(items.map(\.0)), StaticDeriv("literal", "[list]", inputs, nil, F))
        }
        if let r = node as? AST.RecordUpdate {
            let (base, baseN) = const_(r.base, consts)
            let pairs = r.fieldList.map { (key: $0.name, pair: const_($0.expr, consts)) }
            let inputs = [baseN] + pairs.map(\.pair.1)
            guard case let .record(entries) = base, !pairs.contains(where: { $0.pair.0.isUnknown }) else {
                return (UNKNOWN, StaticDeriv("unknown", "with", inputs, nil, F))
            }
            return (.record(recordFrom(entries, pairs.map { ($0.key, $0.pair.0) })),
                    StaticDeriv("op", "with", inputs, nil, F))
        }
        if let l = node as? AST.ListPlus {
            let (base, baseN) = const_(l.base, consts)
            let (item, itemN) = const_(l.item, consts)
            guard case let .list(items) = base, !item.isUnknown else {
                return (UNKNOWN, StaticDeriv("unknown", "plus", [baseN, itemN], nil, F))
            }
            return (.list(items + [item]), StaticDeriv("op", "plus", [baseN, itemN], nil, F))
        }
        if let o = node as? AST.OrFail {
            if o.handler != nil {
                let (_, exprN) = const_(o.expr, consts)
                return (UNKNOWN, StaticDeriv("unknown", "or fail as", [exprN], nil, F))
            }
            return const_(o.expr, consts)
        }
        if let b = node as? AST.BinOp, sameText(b.op, "+") {
            let (left, leftN) = const_(b.left, consts)
            let (right, rightN) = const_(b.right, consts)
            // shapes.py folds text + text only: its numeric test is
            // `isinstance(left, (int, float))`, which a Planes Number is not.
            guard case let .text(l) = left, case let .text(r) = right else {
                return (UNKNOWN, StaticDeriv("unknown", "+", [leftN, rightN], nil, F))
            }
            return (.text(l + r), StaticDeriv("op", "+", [leftN, rightN], nil, F))
        }
        if let b = node as? AST.Builtin, sameText(b.name, "text") {
            let (v, vn) = const_(b.arg, consts)
            if v.isUnknown { return (UNKNOWN, StaticDeriv("unknown", "text of", [vn], nil, F)) }
            return (.text(asText(v)), StaticDeriv("op", "text of", [vn], nil, F))
        }
        if let b = node as? AST.Builtin, sameText(b.name, "lower") || sameText(b.name, "upper") {
            let (v, vn) = const_(b.arg, consts)
            let label = "\(b.name) of"
            if v.isUnknown { return (UNKNOWN, StaticDeriv("unknown", label, [vn], nil, F)) }
            let result = sameText(b.name, "lower") ? pythonLower(pyStr(v)) : pythonUpper(pyStr(v))
            return (.text(result), StaticDeriv("op", label, [vn], nil, F))
        }
        if let c = node as? AST.Call {
            if isBuiltinName(c.name) && !funcs.has(c.name) { return constBuiltin(c, consts) }
            return constCall(c, consts)
        }
        return (UNKNOWN, StaticDeriv("unknown", "{...}", [], nil, F))
    }

    /// `{**base, **updates}`: an existing key keeps its place, a new one is
    /// appended.
    private func recordFrom(_ base: [(key: String, value: StaticValue)],
                            _ updates: [(String, StaticValue)]) -> [(key: String, value: StaticValue)] {
        var out = base
        for (k, v) in updates {
            if let i = out.firstIndex(where: { sameText($0.key, k) }) { out[i].value = v } else { out.append((k, v)) }
        }
        return out
    }

    func constBuiltin(_ node: AST.Call, _ consts: Consts) -> (StaticValue, StaticDeriv) {
        let F = currentFile
        if node.args.count != 1 || kindsTable.has(node.name) {
            return (UNKNOWN, StaticDeriv("unknown", node.name, [], nil, F))
        }
        let (v, n) = const_(node.args[0], consts)
        let label = "\(node.name) of"
        if v.isUnknown { return (UNKNOWN, StaticDeriv("unknown", label, [n], nil, F)) }
        let op = StaticDeriv("op", label, [n], nil, F)
        switch node.name {
        case _ where sameText(node.name, "text"): return (.text(asText(v)), op)
        case _ where sameText(node.name, "lower"): return (.text(pythonLower(pyStr(v))), op)
        case _ where sameText(node.name, "upper"): return (.text(pythonUpper(pyStr(v))), op)
        case _ where sameText(node.name, "normalize"): return (.text(pythonNFC(pyStr(v))), op)
        case _ where sameText(node.name, "join"):
            if case let .list(items) = v {
                let parts = items.compactMap { item -> String? in
                    if case let .text(s) = item { return s }
                    return nil
                }
                if parts.count == items.count { return (.text(parts.joined()), op) }
            }
        case _ where sameText(node.name, "rest"):
            if case let .list(items) = v, !items.isEmpty { return (.list(Array(items.dropFirst())), op) }
        default:
            break
        }
        return (UNKNOWN, StaticDeriv("unknown", label, [n], nil, F))
    }

    func constCall(_ node: AST.Call, _ consts: Consts) -> (StaticValue, StaticDeriv) {
        let F = currentFile
        guard let fn = funcs[node.name], depth <= 6 else {
            return (UNKNOWN, StaticDeriv("unknown", node.name, [], nil, F))
        }
        if isRecursive(node.name) { return (UNKNOWN, StaticDeriv("unknown", node.name, [], nil, F)) }
        let argPairs = node.args.map { const_($0, consts) }
        let argNodes = argPairs.map(\.1)
        if argPairs.count != fn.params.count {
            return (UNKNOWN, StaticDeriv("unknown", node.name, argNodes, nil, F))
        }
        let gives = fn.body.compactMap { $0 as? AST.Give }
        if gives.count != 1 || fn.body.count != 1 {
            return (UNKNOWN, StaticDeriv("unknown", node.name, argNodes, nil, F))
        }

        let calleeFile = fileOf(node.name, currentFile)
        let inner = Consts()
        for (p, pair) in zip(fn.params, argPairs) {
            inner.set(p, pair.0, StaticDeriv("param", p, [pair.1], nil, calleeFile))
        }

        let prevFile = currentFile
        currentFile = calleeFile
        depth += 1
        let (value, _) = const_(gives[0].expr, inner)
        depth -= 1
        currentFile = prevFile
        return (value, StaticDeriv("call", node.name, argNodes, nil, F))
    }

    func asText(_ v: StaticValue) -> String {
        switch v {
        case let .bool(b): return b ? "true" : "false"
        case let .number(n): return n.text()
        case let .text(s): return s
        default: return pyStr(v)
        }
    }

    // ---- target description
    func describe(_ node: AST.Node?, _ consts: Consts) -> (String, Bool, StaticDeriv) {
        let (v, n) = const_(node, consts)
        if !v.isUnknown { return (asText(v), false, n) }
        let (text, n2) = pattern(node, consts)
        return (text, true, n2)
    }

    func pattern(_ node: AST.Node?, _ consts: Consts) -> (String, StaticDeriv) {
        guard let node else { return ("{...}", StaticDeriv("unknown", "{...}", [], nil, currentFile)) }
        let (v, n) = const_(node, consts)
        if !v.isUnknown { return (asText(v), n) }
        if let o = node as? AST.OrFail { return pattern(o.expr, consts) }
        if let b = node as? AST.BinOp, sameText(b.op, "+") {
            let (lt, ln) = pattern(b.left, consts)
            let (rt, rn) = pattern(b.right, consts)
            return (lt + rt, StaticDeriv("op", "+", [ln, rn], nil, currentFile))
        }
        return ("{...}", n)
    }
}

/// The effect surface of a program's source. `file` is the path every
/// derivation node records — nil for source with no file.
public func analyse(_ src: String, file: String? = nil) throws -> Surface {
    let a = try Analyser()
    a.entryFile = file
    return try a.analyse(src)
}

/// A surface for a file plus everything it uses — js/shapes_node.mjs's
/// analyseFile, shapes.py's analyse_file. Without `follow`, the single-file
/// surface: `file` is the path as given, not resolved.
public func analyseFile(_ path: String, follow: Bool = true) throws -> Surface {
    if !follow {
        return try analyse(try readModuleSource(path), file: path)
    }
    let graph = try loadGraph(path)
    try checkCollisions(graph)
    let known = try namesInGraph(graph)
    let renames = try renameMap(graph)
    let combined = try Analyser()
    let targetKey = absolutePath(path)
    combined.entryFile = targetKey
    var entryProg: [AST.Node] = []
    for (location, src) in graph {
        let prog = try parse(src, knownNames: known)
        let key = absolutePath(location)
        var ren = NameMap<String>()
        for (old, new) in renames[location] ?? [] { ren[old] = new }
        combined.collectDeclarations(prog, ren, key)
        if sameText(key, targetKey) { entryProg = prog }
    }
    return combined.analyseProg(entryProg)
}

// ================================================================ diffing

public struct SurfaceDiff {
    public let added: [Effect]
    public let removed: [Effect]
    public let newBoundaries: [String]
    public let droppedBoundaries: [String]

    public func isEmpty() -> Bool { added.isEmpty && removed.isEmpty }

    public func newDestinations() -> [Effect] {
        let before = Set(removed.map { CodePoints($0.target) })
        return added.filter { !before.contains(CodePoints($0.target)) && !$0.computed }
    }

    public func isSignificant() -> Bool { !newBoundaries.isEmpty || !newDestinations().isEmpty }

    public func render() -> String {
        if isEmpty() { return "no change to the effect surface" }
        var lines: [String] = []
        if !newBoundaries.isEmpty {
            lines.append("NEW BOUNDARIES CROSSED: " + newBoundaries.joined(separator: ", "))
        }
        let fresh = newDestinations()
        if !fresh.isEmpty && newBoundaries.isEmpty {
            lines.append("NEW DESTINATIONS: " + pySortedUnique(fresh.map(\.target)).joined(separator: ", "))
        }
        for e in added { lines.append("  + \(e.boundary): \(e)") }
        for e in removed { lines.append("  - \(e.boundary): \(e)") }
        if !droppedBoundaries.isEmpty {
            lines.append("no longer touches: " + droppedBoundaries.joined(separator: ", "))
        }
        return lines.joined(separator: "\n")
    }
}

public func diff(_ before: Surface, _ after: Surface) -> SurfaceDiff {
    var b = NameMapByKey()
    for e in before.declared { b.set(e) }
    var a = NameMapByKey()
    for e in after.declared { a.set(e) }
    let added = a.values.filter { !b.has($0) }
    let removed = b.values.filter { !a.has($0) }
    let beforeB = Set(before.boundaries().map(CodePoints.init))
    let afterB = Set(after.boundaries().map(CodePoints.init))
    return SurfaceDiff(
        added: sortedEffects(added),
        removed: sortedEffects(removed),
        newBoundaries: pySorted(after.boundaries().filter { !beforeB.contains(CodePoints($0)) }),
        droppedBoundaries: pySorted(before.boundaries().filter { !afterB.contains(CodePoints($0)) })
    )
}

/// `{(e.kind, e.target, e.computed): e}` — a later effect replaces an earlier
/// one's value but keeps its position, as a Python dict does.
private struct NameMapByKey {
    private var order: [Effect.ShortKey] = []
    private var map: [Effect.ShortKey: Effect] = [:]

    mutating func set(_ e: Effect) {
        if map[e.shortKey] == nil { order.append(e.shortKey) }
        map[e.shortKey] = e
    }

    func has(_ e: Effect) -> Bool { map[e.shortKey] != nil }
    var values: [Effect] { order.map { map[$0]! } }
}

// ================================================================ canonical forms
//
// The agreement forms (A.3). `asJson` is shapes_cli.as_json's published surface
// form. The per-function breakdown and the derivation tree are the two facts
// as_json omits; both are plain structural serializations of the actual data.

/// Bumped when a field's meaning changes; matches shapes_cli.FORMAT_VERSION.
public let FORMAT_VERSION = 1

/// `os.path.basename`: the text after the last "/".
func basename(_ p: String) -> String {
    let scalars = Array(p.unicodeScalars)
    guard let slash = scalars.lastIndex(of: "/") else { return p }
    return String(String.UnicodeScalarView(scalars[(slash + 1)...]))
}

private func jsonStrings(_ xs: [String]) -> GrammarJSON { .array(xs.map { .string($0) }) }

/// shapes_cli.py's as_json: the machine-readable surface, keys in its order.
public func asJson(_ surface: Surface, _ path: String) -> GrammarJSON {
    let kind = surface.isLibrary() ? "library" : surface.isPure() ? "pure" : "program"
    return .object([
        ("format", .number(String(FORMAT_VERSION))),
        ("program", .string(basename(path))),
        ("kind", .string(kind)),
        ("pure", .bool(surface.isPure())),
        ("complete", .bool(!surface.hasUnknowns() && surface.unresolved.isEmpty)),
        ("boundaries", jsonStrings(surface.boundaries())),
        ("kinds", jsonStrings(surface.kinds())),
        ("effects", .array(surface.declared.map { e in
            .object([("kind", .string(e.kind)), ("boundary", .string(e.boundary)), ("target", .string(e.target)),
                     ("computed", .bool(e.computed)), ("declared", .bool(e.claimed))])
        })),
        ("runs_on_load", .array(surface.effects.map { e in
            .object([("kind", .string(e.kind)), ("boundary", .string(e.boundary)), ("target", .string(e.target))])
        })),
        ("modules_declared", jsonStrings(pySorted(surface.modules))),
        ("modules_unused", jsonStrings(surface.declaredButUnused())),
        ("effects_undeclared", .array(surface.usedButUndeclared().map { e in
            .object([("kind", .string(e.kind)), ("target", .string(e.target))])
        })),
        ("unresolved_calls", jsonStrings(pySortedUnique(surface.unresolved))),
        // The third question, in the machine-readable report too.
        ("approximate", .array(surface.approximate.map(jsonStrings))),
    ])
}

/// Per-function effect breakdown: sorted function name -> its sorted effects.
public func functionsBreakdown(_ surface: Surface) -> GrammarJSON {
    let byName = stableSorted(surface.functions) { pyLess($0.name, $1.name) }
    return .object(byName.map { f in
        (f.name, .array(f.effects.map { e in
            .object([("kind", .string(e.kind)), ("boundary", .string(e.boundary)), ("target", .string(e.target)),
                     ("computed", .bool(e.computed)), ("claimed", .bool(e.claimed))])
        }))
    })
}

private func optionalString(_ s: String?) -> GrammarJSON { s.map { .string($0) } ?? .null }

/// A StaticDeriv graph as nested objects — the canonical derivation form. Shared
/// identity is broken into a tree the way shapes.py's own walkers re-walk.
public func derivTree(_ node: StaticDeriv?) -> GrammarJSON {
    guard let node else { return .null }
    return .object([
        ("kind", .string(node.kind)),
        ("label", .string(node.label)),
        ("origin", optionalString(node.origin)),
        ("file", optionalString(node.file)),
        ("inputs", .array(node.inputs.map(derivTree))),
    ])
}

/// Per-effect derivation + origins, in declared order.
public func derivationForm(_ surface: Surface) -> GrammarJSON {
    .array(surface.declared.map { e in
        .object([
            ("kind", .string(e.kind)),
            ("boundary", .string(e.boundary)),
            ("target", .string(e.target)),
            ("computed", .bool(e.computed)),
            ("origins", .array(surface.originsOf(e).map { .array([.string($0.name), optionalString($0.file)]) })),
            ("derivation", derivTree(e.derivation)),
        ])
    })
}
