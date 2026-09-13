// Nodes.swift — the AST node types.
//
// The Swift counterpart of js/nodes.mjs, and of the AST dataclasses at the bottom
// of lexer.py (defined there, historically, so parser.py could `from lexer import
// *`). Each node is a class — reference semantics, as a Python dataclass instance
// and a js object have: parse_because sets `annotation` on a node it was handed,
// and core_restrict stamps a line on one by identity. Stored properties are typed
// for the interpreter; `fields` lists them under their Python names verbatim
// (is_let, is_expr, supersedes_fingerprint, ...) in the SAME declaration order as
// the Python dataclass, because the canonical AST form (Canonical.swift) prints
// them in that order. Order is load-bearing.
//
// The node types live inside `AST` so that `AST.Bool`, `AST.If` and `AST.Call`
// neither shadow Swift's own names nor land in the namespace of a program that
// imports Planes. Inside this file, Swift's `Bool` is spelled `Swift.Bool`.
//
// A Python tuple becomes an `ASTValue.tuple`; a Python list an `ASTValue.list`.
// The distinction only matters at the item level of a sequence field:
// RecordLit.fields holds (name, expr) pairs (tuples), while ListLit.items holds
// nodes. The typed shapes (`AST.Matcher`, `AST.EffectClaim`, ...) render back to
// exactly the tuple shapes parser.py builds.

/// One field value, as the canonical form sees it: the dynamic shape of the
/// Python value behind a dataclass field.
public indirect enum ASTValue {
    case none
    case bool(Swift.Bool)
    case string(String)
    case int(Int)
    case number(PlanesNumber)
    case node(AST.Node)
    case list([ASTValue])
    case tuple([ASTValue])
}

/// A node a trailing `because "..."` may attach to — Assign and Rule, the two
/// dataclasses with an `annotation` field.
public protocol Annotated: AST.Node {
    var annotation: AST.Because? { get set }
}

extension AST.Assign: Annotated {}
extension AST.Rule: Annotated {}

public enum AST {
    /// The node type names — the Python class names, which the canonical form
    /// prints. `KEYWORDS_A_NODE_CAN_CARRY` (CoreRestrict.swift) is keyed by it.
    public enum Kind: String, Sendable, CaseIterable {
        case Num, Str, Bool, Nothing, Var, ListLit, RecordLit, RecordUpdate, ListPlus
        case BinOp, Not, IsNothing, Field, Assign, Why, Use, FuncDef, Call, Give, Show
        case ForEach, If, When, OrFail, Fail, Builtin, Foreign, WriteTo, Round, Rule
        case Because, Note
    }

    /// Every node. `kind` is js's `__node`.
    public class Node {
        public let kind: Kind
        /// core_restrict's line stamp, beside the tree rather than in it: never
        /// one of `fields`, so it cannot change the AST's shape. js keeps it in
        /// a WeakMap for the same reason.
        var stampedLine: Int?

        init(_ kind: Kind) { self.kind = kind }

        /// The dataclass fields, in declaration order.
        public var fields: [(name: String, value: ASTValue)] { [] }
    }

    // ---- the tuple shapes

    /// A `when` pattern entry's matcher: ("match", expr) or ("bind", name).
    public enum Matcher {
        case match(Node)
        case bind(String)

        var value: ASTValue {
            switch self {
            case let .match(e): return .tuple([.string("match"), .node(e)])
            case let .bind(n): return .tuple([.string("bind"), .string(n)])
            }
        }
    }

    /// Where a foreign's claimed effect goes: ("literal", text) or ("param", name).
    public enum ClaimTarget {
        case literal(String)
        case param(String)

        var value: ASTValue {
            switch self {
            case let .literal(s): return .tuple([.string("literal"), .string(s)])
            case let .param(s): return .tuple([.string("param"), .string(s)])
            }
        }
    }

    /// One `doing` claim: (kind, target-or-None).
    public struct EffectClaim {
        public let kind: String
        public let target: ClaimTarget?

        public init(_ kind: String, _ target: ClaimTarget?) {
            self.kind = kind
            self.target = target
        }

        var value: ASTValue { .tuple([.string(kind), target?.value ?? .none]) }
    }

    private static func nodes(_ ns: [Node]) -> ASTValue { .list(ns.map { .node($0) }) }
    private static func strings(_ ss: [String]) -> ASTValue { .list(ss.map { .string($0) }) }
    private static func optional(_ n: Node?) -> ASTValue { n.map { .node($0) } ?? .none }
    private static func optional(_ s: String?) -> ASTValue { s.map { .string($0) } ?? .none }
    private static func pairs(_ ps: [(String, Node)]) -> ASTValue {
        .list(ps.map { .tuple([.string($0.0), .node($0.1)]) })
    }

    // ---- the nodes

    public final class Num: Node {
        public let value: PlanesNumber
        public init(_ value: PlanesNumber) { self.value = value; super.init(.Num) }
        override public var fields: [(name: String, value: ASTValue)] { [("value", .number(value))] }
    }

    public final class Str: Node {
        public let value: String
        public init(_ value: String) { self.value = value; super.init(.Str) }
        override public var fields: [(name: String, value: ASTValue)] { [("value", .string(value))] }
    }

    public final class Bool: Node {
        public let value: Swift.Bool
        public init(_ value: Swift.Bool) { self.value = value; super.init(.Bool) }
        override public var fields: [(name: String, value: ASTValue)] { [("value", .bool(value))] }
    }

    public final class Nothing: Node {
        public init() { super.init(.Nothing) }
    }

    public final class Var: Node {
        public let name: String
        public init(_ name: String) { self.name = name; super.init(.Var) }
        override public var fields: [(name: String, value: ASTValue)] { [("name", .string(name))] }
    }

    public final class ListLit: Node {
        public let items: [Node]
        public init(_ items: [Node]) { self.items = items; super.init(.ListLit) }
        override public var fields: [(name: String, value: ASTValue)] { [("items", nodes(items))] }
    }

    public final class RecordLit: Node {
        public let fieldList: [(name: String, expr: Node)]
        public init(_ fields: [(name: String, expr: Node)]) { fieldList = fields; super.init(.RecordLit) }
        override public var fields: [(name: String, value: ASTValue)] {
            [("fields", pairs(fieldList.map { ($0.name, $0.expr) }))]
        }
    }

    public final class RecordUpdate: Node {
        public let base: Node
        public let fieldList: [(name: String, expr: Node)]
        public init(_ base: Node, _ fields: [(name: String, expr: Node)]) {
            self.base = base
            fieldList = fields
            super.init(.RecordUpdate)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("base", .node(base)), ("fields", pairs(fieldList.map { ($0.name, $0.expr) }))]
        }
    }

    public final class ListPlus: Node {
        public let base: Node
        public let item: Node
        public init(_ base: Node, _ item: Node) { self.base = base; self.item = item; super.init(.ListPlus) }
        override public var fields: [(name: String, value: ASTValue)] { [("base", .node(base)), ("item", .node(item))] }
    }

    public final class BinOp: Node {
        public let op: String
        public let left: Node
        public let right: Node
        public init(_ op: String, _ left: Node, _ right: Node) {
            self.op = op
            self.left = left
            self.right = right
            super.init(.BinOp)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("op", .string(op)), ("left", .node(left)), ("right", .node(right))]
        }
    }

    public final class Not: Node {
        public let expr: Node
        public init(_ expr: Node) { self.expr = expr; super.init(.Not) }
        override public var fields: [(name: String, value: ASTValue)] { [("expr", .node(expr))] }
    }

    public final class IsNothing: Node {
        public let expr: Node
        public init(_ expr: Node) { self.expr = expr; super.init(.IsNothing) }
        override public var fields: [(name: String, value: ASTValue)] { [("expr", .node(expr))] }
    }

    public final class Field: Node {
        public let obj: Node
        public let name: String
        public init(_ obj: Node, _ name: String) { self.obj = obj; self.name = name; super.init(.Field) }
        override public var fields: [(name: String, value: ASTValue)] { [("obj", .node(obj)), ("name", .string(name))] }
    }

    public final class Assign: Node {
        public let name: String
        public let expr: Node
        public let isLet: Swift.Bool
        public var annotation: Because?
        public init(_ name: String, _ expr: Node, isLet: Swift.Bool = false, annotation: Because? = nil) {
            self.name = name
            self.expr = expr
            self.isLet = isLet
            self.annotation = annotation
            super.init(.Assign)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("name", .string(name)), ("expr", .node(expr)), ("is_let", .bool(isLet)),
             ("annotation", optional(annotation))]
        }
    }

    public final class Why: Node {
        public let expr: Node
        public init(_ expr: Node) { self.expr = expr; super.init(.Why) }
        override public var fields: [(name: String, value: ASTValue)] { [("expr", .node(expr))] }
    }

    public final class Use: Node {
        public let module: String
        /// Renames, as (original, new) — a tuple of pairs in parser.py.
        public let renames: [(old: String, new: String)]
        public init(_ module: String, _ renames: [(old: String, new: String)] = []) {
            self.module = module
            self.renames = renames
            super.init(.Use)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("module", .string(module)),
             ("renames", .tuple(renames.map { .tuple([.string($0.old), .string($0.new)]) }))]
        }
    }

    public final class FuncDef: Node {
        public let name: String
        public let params: [String]
        public let body: [Node]
        public init(_ name: String, _ params: [String], _ body: [Node]) {
            self.name = name
            self.params = params
            self.body = body
            super.init(.FuncDef)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("name", .string(name)), ("params", strings(params)), ("body", nodes(body))]
        }
    }

    public final class Call: Node {
        public let name: String
        public let args: [Node]
        public let line: Int
        public init(_ name: String, _ args: [Node], _ line: Int = 0) {
            self.name = name
            self.args = args
            self.line = line
            super.init(.Call)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("name", .string(name)), ("args", nodes(args)), ("line", .int(line))]
        }
    }

    public final class Give: Node {
        public let expr: Node
        public init(_ expr: Node) { self.expr = expr; super.init(.Give) }
        override public var fields: [(name: String, value: ASTValue)] { [("expr", .node(expr))] }
    }

    public final class Show: Node {
        public let expr: Node
        public let line: Int
        public init(_ expr: Node, _ line: Int = 0) { self.expr = expr; self.line = line; super.init(.Show) }
        override public var fields: [(name: String, value: ASTValue)] { [("expr", .node(expr)), ("line", .int(line))] }
    }

    public final class ForEach: Node {
        public let variable: String
        public let source: Node
        public let whereClause: Node?
        public let body: [Node]
        public let isExpr: Swift.Bool
        public init(_ variable: String, _ source: Node, _ whereClause: Node?, _ body: [Node], isExpr: Swift.Bool = false) {
            self.variable = variable
            self.source = source
            self.whereClause = whereClause
            self.body = body
            self.isExpr = isExpr
            super.init(.ForEach)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("var", .string(variable)), ("source", .node(source)), ("where", optional(whereClause)),
             ("body", nodes(body)), ("is_expr", .bool(isExpr))]
        }
    }

    public final class If: Node {
        public let cond: Node
        public let then: [Node]
        public let els: [Node]
        public init(_ cond: Node, _ then: [Node], _ els: [Node]) {
            self.cond = cond
            self.then = then
            self.els = els
            super.init(.If)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("cond", .node(cond)), ("then", nodes(then)), ("els", nodes(els))]
        }
    }

    public final class When: Node {
        public let subject: Node
        public let pattern: [(field: String, matcher: Matcher)]
        public let body: [Node]
        public let els: [Node]
        public init(_ subject: Node, _ pattern: [(field: String, matcher: Matcher)], _ body: [Node], _ els: [Node]) {
            self.subject = subject
            self.pattern = pattern
            self.body = body
            self.els = els
            super.init(.When)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("subject", .node(subject)),
             ("pattern", .list(pattern.map { .tuple([.string($0.field), $0.matcher.value]) })),
             ("body", nodes(body)), ("els", nodes(els))]
        }
    }

    public final class OrFail: Node {
        public let expr: Node
        public let tag: String
        public let handler: [Node]?
        public init(_ expr: Node, _ tag: String, _ handler: [Node]? = nil) {
            self.expr = expr
            self.tag = tag
            self.handler = handler
            super.init(.OrFail)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("expr", .node(expr)), ("tag", .string(tag)), ("handler", handler.map(nodes) ?? .none)]
        }
    }

    public final class Fail: Node {
        public let message: Node
        public let tag: String
        public let line: Int
        public init(_ message: Node, _ tag: String, _ line: Int = 0) {
            self.message = message
            self.tag = tag
            self.line = line
            super.init(.Fail)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("message", .node(message)), ("tag", .string(tag)), ("line", .int(line))]
        }
    }

    public final class Builtin: Node {
        public let name: String
        public let arg: Node
        public init(_ name: String, _ arg: Node) { self.name = name; self.arg = arg; super.init(.Builtin) }
        override public var fields: [(name: String, value: ASTValue)] { [("name", .string(name)), ("arg", .node(arg))] }
    }

    public final class Foreign: Node {
        public let name: String
        public let params: [String]
        public let target: String
        /// (kind, target) claims — a tuple in parser.py.
        public let effects: [EffectClaim]
        public let declared: Swift.Bool
        public let line: Int
        public init(_ name: String, _ params: [String], _ target: String, _ effects: [EffectClaim] = [],
                    _ declared: Swift.Bool = false, _ line: Int = 0) {
            self.name = name
            self.params = params
            self.target = target
            self.effects = effects
            self.declared = declared
            self.line = line
            super.init(.Foreign)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("name", .string(name)), ("params", strings(params)), ("target", .string(target)),
             ("effects", .tuple(effects.map(\.value))), ("declared", .bool(declared)), ("line", .int(line))]
        }
    }

    public final class WriteTo: Node {
        public let value: Node
        public let dest: Node
        public let line: Int
        public init(_ value: Node, _ dest: Node, _ line: Int = 0) {
            self.value = value
            self.dest = dest
            self.line = line
            super.init(.WriteTo)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("value", .node(value)), ("dest", .node(dest)), ("line", .int(line))]
        }
    }

    public final class Round: Node {
        public let value: Node
        public let places: Node
        public init(_ value: Node, _ places: Node) { self.value = value; self.places = places; super.init(.Round) }
        override public var fields: [(name: String, value: ASTValue)] { [("value", .node(value)), ("places", .node(places))] }
    }

    public final class Rule: Node {
        public let name: String
        public let subject: String
        public let effectKind: String
        public let target: String?
        public let line: Int
        public let supersedes: String?
        public let assertion: String
        public let supersedesFingerprint: String?
        public var annotation: Because?
        public init(_ name: String, _ subject: String, _ kind: String, _ target: String? = nil, _ line: Int = 0,
                    _ supersedes: String? = nil, _ assertion: String = "forbid",
                    _ supersedesFingerprint: String? = nil, _ annotation: Because? = nil) {
            self.name = name
            self.subject = subject
            effectKind = kind
            self.target = target
            self.line = line
            self.supersedes = supersedes
            self.assertion = assertion
            self.supersedesFingerprint = supersedesFingerprint
            self.annotation = annotation
            super.init(.Rule)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("name", .string(name)), ("subject", .string(subject)), ("kind", .string(effectKind)),
             ("target", optional(target)), ("line", .int(line)), ("supersedes", optional(supersedes)),
             ("assertion", .string(assertion)), ("supersedes_fingerprint", optional(supersedesFingerprint)),
             ("annotation", optional(annotation))]
        }
    }

    public final class Because: Node {
        public let text: String
        public let line: Int
        public init(_ text: String, _ line: Int = 0) { self.text = text; self.line = line; super.init(.Because) }
        override public var fields: [(name: String, value: ASTValue)] { [("text", .string(text)), ("line", .int(line))] }
    }

    public final class Note: Node {
        /// (kind, value) pairs: ("from", "..."), ("derives-from", "rule-name").
        public let entries: [(kind: String, value: String)]
        public let line: Int
        public init(_ entries: [(kind: String, value: String)], _ line: Int = 0) {
            self.entries = entries
            self.line = line
            super.init(.Note)
        }
        override public var fields: [(name: String, value: ASTValue)] {
            [("entries", .list(entries.map { .tuple([.string($0.kind), .string($0.value)]) })), ("line", .int(line))]
        }
    }
}
