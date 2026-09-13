// Render.swift — the Planes canonical renderer, ported from render.py.
//
// The Swift counterpart of js/render.mjs, keeping its structure and names.
// render(parse(src)) parses back to an equal AST: canonical, not literal — every
// call rendered `name of (args)`, every compound sub-expression parenthesised.
// With rules and a surface it also emits the generated rule markers
// (`~ [name] applies here`), which is what `render-rules` (shapes_cli.py
// --render) prints; test_swift_rules.py holds that output byte for byte against
// render.py. Every node kind has a real case and no safe fallback: an unhandled
// kind throws, naming it.

/// A node the renderer has no case for.
public struct RenderError: Error, CustomStringConvertible, Sendable {
    public let message: String
    public var description: String { message }
}

private let INDENT = "  "

// Sub-expressions that need parens wherever they are read at less than full
// precedence.
private let COMPOUND: Set<AST.Kind> = [.BinOp, .Not, .IsNothing, .ListPlus, .OrFail, .RecordUpdate, .ForEach]

// Expressions whose own trailing structure swallows a following keyword or `:`
// delimiter.
private let OPEN_TRAILING: Set<AST.Kind> = [.OrFail, .RecordUpdate, .ForEach]

// Expression node kinds that may stand alone as a statement.
private let EXPR_STMT: Set<AST.Kind> = [
    .Num, .Str, .Bool, .Nothing, .Var, .ListLit, .RecordLit, .RecordUpdate, .ListPlus, .BinOp, .Not,
    .IsNothing, .Field, .Call, .Round, .ForEach, .OrFail,
]

private func delimited(_ node: AST.Node) throws -> String {
    OPEN_TRAILING.contains(node.kind) ? "(\(try renderExpr(node)))" : try renderExpr(node)
}

// ================================================================ comma-list elements

// The greedy comma-extensible list that terminates renderExpr(node) at top level:
// "of" (a call's argument list), "with" (a record update's field list), or nil.
private func greedyTail(_ node: AST.Node) -> String? {
    switch node {
    case let c as AST.Call: return c.args.isEmpty ? nil : "of"
    case is AST.RecordUpdate: return "with"
    case let fe as AST.ForEach: return fe.body.first.flatMap(greedyTail)
    case let b as AST.BinOp: return COMPOUND.contains(b.right.kind) ? nil : greedyTail(b.right)
    case let n as AST.Not: return COMPOUND.contains(n.expr.kind) ? nil : greedyTail(n.expr)
    case let l as AST.ListPlus: return COMPOUND.contains(l.item.kind) ? nil : greedyTail(l.item)
    default: return nil
    }
}

// Render `node` as an element of a comma-separated list, parenthesising it when
// its greedy tail would be swallowed by the list's own separator.
private func commaElement(_ node: AST.Node, _ sep: String) throws -> String {
    let text = try renderExpr(node)
    let tail = greedyTail(node)
    let dangerous = tail == "of" || (tail == "with" && sep == "record")
    return dangerous ? "(\(text))" : text
}

// The base of a `X.name` field access.
private func fieldBase(_ node: AST.Node) throws -> String {
    if COMPOUND.contains(node.kind) || greedyTail(node) != nil {
        return "(\(try renderExpr(node)))"
    }
    return try renderExpr(node)
}

// ================================================================ expressions

// A BinOp the parser SYNTHESISED for a unary minus, `-X`: a subtraction from a
// literal zero renders as the unary form whether the zero was synthesised or
// written.
private func isNegation(_ node: AST.BinOp) -> Bool {
    guard sameText(node.op, "-"), let zero = node.left as? AST.Num else { return false }
    return zero.value.isZero()
}

private func renderOperand(_ node: AST.Node) throws -> String {
    let text = try renderExpr(node)
    return COMPOUND.contains(node.kind) ? "(\(text))" : text
}

private func recordFields(_ fields: [(name: String, expr: AST.Node)]) throws -> String {
    try fields.map { "\($0.name): \(try commaElement($0.expr, "record"))" }.joined(separator: ", ")
}

public func renderExpr(_ node: AST.Node) throws -> String {
    switch node {
    case let n as AST.Num: return n.value.text()
    case let s as AST.Str: return "\"\(escapeStringLiteral(s.value))\""
    case let b as AST.Bool: return b.value ? "true" : "false"
    case is AST.Nothing: return "nothing"
    case let v as AST.Var: return v.name
    case let l as AST.ListLit:
        return "[" + (try l.items.map { try commaElement($0, "list") }).joined(separator: ", ") + "]"
    case let l as AST.ListPlus:
        return "\(try renderOperand(l.base)) plus \(try renderOperand(l.item))"
    case let r as AST.RecordLit:
        let fields = try recordFields(r.fieldList)
        return fields.isEmpty ? "{}" : "{ " + fields + " }"
    case let r as AST.RecordUpdate:
        return "\(try renderOperand(r.base)) with \(try recordFields(r.fieldList))"
    case let b as AST.BinOp:
        if sameText(b.op, "first") {
            return "first (\(try renderExpr(b.left))) of (\(try renderExpr(b.right)))"
        }
        if isNegation(b) {
            return "-\(try renderOperand(b.right))"
        }
        return "\(try renderOperand(b.left)) \(b.op) \(try renderOperand(b.right))"
    case let n as AST.Not: return "not \(try renderOperand(n.expr))"
    case let n as AST.IsNothing: return "\(try renderOperand(n.expr)) is nothing"
    case let f as AST.Field: return "\(try fieldBase(f.obj)).\(f.name)"
    case let c as AST.Call: return try renderCall(c)
    case let r as AST.Round: return "round \(try renderOperand(r.value)) to \(try renderOperand(r.places)) places"
    case let fe as AST.ForEach: return try renderForeachExpr(fe)
    case let o as AST.OrFail: return try renderOrfail(o)
    case is AST.Builtin:
        throw RenderError(message: "renderExpr: Builtin is unreachable by design")
    default:
        throw RenderError(message: "renderExpr: unhandled node type \(node.kind.rawValue)")
    }
}

private func renderCall(_ node: AST.Call) throws -> String {
    if node.args.isEmpty { return node.name }
    let args = try node.args.map { "(\(try renderExpr($0)))" }.joined(separator: ", ")
    return "\(node.name) of \(args)"
}

private func renderForeachExpr(_ node: AST.ForEach) throws -> String {
    let whereText = try node.whereClause.map { " where \(try delimited($0))" } ?? ""
    guard let first = node.body.first else {
        throw RenderError(message: "renderExpr: a for-each expression with no body")
    }
    return "for each \(node.variable) in \(try delimited(node.source))\(whereText): \(try renderExpr(first))"
}

private func renderWritetoInline(_ node: AST.WriteTo) throws -> String {
    "write \(try delimited(node.value)) to \(try delimited(node.dest))"
}

private func renderOrfail(_ node: AST.OrFail) throws -> String {
    let inner = try (node.expr as? AST.WriteTo).map(renderWritetoInline) ?? delimited(node.expr)
    return "\(inner) or fail as \(node.tag)"
}

// ================================================================ statements

private func renderBecauseSuffix(_ annotation: AST.Because?) -> String {
    guard let annotation else { return "" }
    return " because \"\(escapeStringLiteral(annotation.text))\""
}

private func renderAssign(_ node: AST.Assign) throws -> String {
    let prefix = node.isLet ? "let " : ""
    return "\(prefix)\(node.name) = \(try renderExpr(node.expr))\(renderBecauseSuffix(node.annotation))"
}

private func renderRule(_ node: AST.Rule) -> String {
    let verb = sameText(node.assertion, "forbid") ? "may not" : "may"
    var text = "rule [\(node.name)] \(node.subject) \(verb) \(node.effectKind)"
    if let target = node.target { text += " to \"\(escapeStringLiteral(target))\"" }
    if let supersedes = node.supersedes {
        text += " supersedes [\(supersedes)]"
        if let fp = node.supersedesFingerprint { text += " @\(fp)" }
    }
    return text + renderBecauseSuffix(node.annotation)
}

private func renderNote(_ node: AST.Note, _ indent: String) -> String {
    var lines = [indent + "note:"]
    for e in node.entries {
        if sameText(e.kind, "from") {
            lines.append(indent + INDENT + "from \"\(escapeStringLiteral(e.value))\"")
        } else if sameText(e.kind, "derives-from") {
            lines.append(indent + INDENT + "derives-from [\(e.value)]")
        }
    }
    return lines.joined(separator: "\n")
}

private func renderUse(_ node: AST.Use) -> String {
    var text = "use \(node.module)"
    for r in node.renames { text += " with \(r.old) as \(r.new)" }
    return text
}

private func renderForeign(_ node: AST.Foreign) -> String {
    var text = "foreign \(node.name)"
    if !node.params.isEmpty { text += " of " + node.params.joined(separator: ", ") }
    text += " from \"\(escapeStringLiteral(node.target))\""
    if node.declared {
        if node.effects.isEmpty {
            text += " doing nothing"
        } else {
            let claims = node.effects.map { eff -> String in
                switch eff.target {
                case nil: return eff.kind
                case let .literal(value)?: return "\(eff.kind) \"\(escapeStringLiteral(value))\""
                case let .param(name)?: return "\(eff.kind) \(name)"
                }
            }
            text += " doing " + claims.joined(separator: ", ")
        }
    }
    return text
}

private func renderFuncdef(_ node: AST.FuncDef, _ indent: String, _ markers: Markers) throws -> String {
    var header = "to \(node.name)"
    if !node.params.isEmpty { header += " of " + node.params.joined(separator: ", ") }
    header += ":"
    return indent + header + "\n" + (try renderBlock(node.body, indent + INDENT, markers))
}

private func renderIf(_ node: AST.If, _ indent: String, _ markers: Markers) throws -> String {
    var lines = [indent + "if \(try delimited(node.cond)):"]
    lines.append(try renderBlock(node.then, indent + INDENT, markers))
    if !node.els.isEmpty {
        lines.append(indent + "else:")
        lines.append(try renderBlock(node.els, indent + INDENT, markers))
    }
    return lines.joined(separator: "\n")
}

private func renderForeachStmt(_ node: AST.ForEach, _ indent: String, _ markers: Markers) throws -> String {
    let whereText = try node.whereClause.map { " where \(try delimited($0))" } ?? ""
    let header = indent + "for each \(node.variable) in \(try delimited(node.source))\(whereText):"
    return header + "\n" + (try renderBlock(node.body, indent + INDENT, markers))
}

private func renderWhen(_ node: AST.When, _ indent: String, _ markers: Markers) throws -> String {
    var entries: [String] = []
    for p in node.pattern {
        switch p.matcher {
        case let .match(arg): entries.append("\(p.field): \(try commaElement(arg, "record"))")
        case .bind: entries.append(p.field)
        }
    }
    let header = indent + "when \(try delimited(node.subject)) is { \(entries.joined(separator: ", ")) }:"
    var lines = [header, try renderBlock(node.body, indent + INDENT, markers)]
    if !node.els.isEmpty {
        lines.append(indent + "else:")
        lines.append(try renderBlock(node.els, indent + INDENT, markers))
    }
    return lines.joined(separator: "\n")
}

// The or-fail-with-handler at this statement's top, or nil.
private func statementOrfail(_ node: AST.Node) -> AST.OrFail? {
    if let o = node as? AST.OrFail, o.handler != nil { return o }
    if let a = node as? AST.Assign, let o = a.expr as? AST.OrFail, o.handler != nil { return o }
    if let g = node as? AST.Give, let o = g.expr as? AST.OrFail, o.handler != nil { return o }
    return nil
}

// A copy of `node` with its or-fail handler cleared, so the single-line render
// path produces the head line.
private func withoutHandler(_ node: AST.Node) -> AST.Node {
    func cleared(_ o: AST.OrFail) -> AST.OrFail { AST.OrFail(o.expr, o.tag, nil) }
    if let o = node as? AST.OrFail { return cleared(o) }
    if let a = node as? AST.Assign, let o = a.expr as? AST.OrFail {
        return AST.Assign(a.name, cleared(o), isLet: a.isLet, annotation: a.annotation)
    }
    if let g = node as? AST.Give, let o = g.expr as? AST.OrFail { return AST.Give(cleared(o)) }
    return node
}

public func renderStmt(_ node: AST.Node, _ indent: String, _ markers: Markers = Markers()) throws -> String {
    if let orfail = statementOrfail(node), let handler = orfail.handler {
        let head = try renderStmt(withoutHandler(node), indent, markers)
        let block = try renderBlock(handler, indent + INDENT, markers)
        return head + ":\n" + block
    }

    switch node {
    case let u as AST.Use: return indent + renderUse(u)
    case let f as AST.Foreign: return indent + renderForeign(f)
    case let r as AST.Rule: return indent + renderRule(r)
    case let n as AST.Note: return renderNote(n, indent)
    case let f as AST.FuncDef: return try renderFuncdef(f, indent, markers)
    case let a as AST.Assign: return indent + (try renderAssign(a))
    case let g as AST.Give: return indent + "give \(try renderExpr(g.expr))"
    case let s as AST.Show: return indent + "show \(try renderExpr(s.expr))"
    case let w as AST.Why: return indent + "why \(try renderExpr(w.expr))"
    case let w as AST.When: return try renderWhen(w, indent, markers)
    case let w as AST.WriteTo: return indent + (try renderWritetoInline(w))
    case let o as AST.OrFail: return indent + (try renderOrfail(o))
    case let f as AST.Fail: return indent + "fail \(try delimited(f.message)) as \(f.tag)"
    case let i as AST.If: return try renderIf(i, indent, markers)
    case let fe as AST.ForEach: return try renderForeachStmt(fe, indent, markers)
    default:
        if EXPR_STMT.contains(node.kind) { return indent + (try renderExpr(node)) }
        throw RenderError(message: "renderStmt: unhandled node type \(node.kind.rawValue)")
    }
}

// ================================================================ the generated marker

/// source line -> rule names, for every site an active rule reaches.
public struct Markers {
    var byLine: [Int: [String]] = [:]
    public init() {}
    public var isEmpty: Bool { byLine.isEmpty }
}

private func lineOfField(_ node: AST.Node) -> Int? {
    for f in node.fields where f.name == "line" {
        if case let .int(n) = f.value { return n }
    }
    return nil
}

// Every source line this node's subtree touches. Matches render.py's _line_span:
// recurses into direct node fields and one level into list/tuple elements that
// are themselves nodes (a tuple element, being no node, is not descended — a
// faithful quirk).
private func lineSpan(_ node: AST.Node, _ seen: inout Set<ObjectIdentifier>) -> Set<Int> {
    if !seen.insert(ObjectIdentifier(node)).inserted { return [] }
    var lines = Set<Int>()
    if let ln = lineOfField(node), ln != 0 { lines.insert(ln) }
    for f in node.fields {
        switch f.value {
        case let .node(v):
            lines.formUnion(lineSpan(v, &seen))
        case let .list(items), let .tuple(items):
            for case let .node(x) in items { lines.formUnion(lineSpan(x, &seen)) }
        default:
            break
        }
    }
    return lines
}

public func computeMarkers(_ rules: [AST.Rule]?, _ surface: Surface?, declaringFile: String? = nil) throws -> Markers {
    guard let rules, !rules.isEmpty else { return Markers() }
    guard let surface else {
        throw RenderError(message:
            "render(): rules given without surface -- markers need a " +
                "computed effect surface\n" +
                "  try: render(prog, rules=found, surface=analyse(src))")
    }
    var markers = Markers()
    for v in try check(rules, surface, declaringFile: declaringFile) {
        guard let effect = v.effect else { continue }
        markers.byLine[effect.site, default: []].append(v.rule.name)
    }
    return markers
}

private func markerLines(_ stmt: AST.Node, _ indent: String, _ markers: Markers) -> [String] {
    if markers.isEmpty { return [] }
    var seenNodes = Set<ObjectIdentifier>()
    let hit = lineSpan(stmt, &seenNodes).filter { markers.byLine[$0] != nil }.sorted()
    var names: [String] = []
    var seen = Set<CodePoints>()
    for ln in hit {
        for name in markers.byLine[ln]! where seen.insert(CodePoints(name)).inserted {
            names.append(name)
        }
    }
    return names.map { indent + "~ [\($0)] applies here" }
}

private func renderBlock(_ stmts: [AST.Node], _ indent: String, _ markers: Markers) throws -> String {
    var out: [String] = []
    for s in stmts {
        out.append(contentsOf: markerLines(s, indent, markers))
        out.append(try renderStmt(s, indent, markers))
    }
    return out.joined(separator: "\n")
}

// ================================================================ entry points

/// Canonical source text for a program. With `rules` and `surface`, governed
/// instruction sites carry a generated marker, computed here from `check`.
public func render(_ prog: [AST.Node], rules: [AST.Rule]? = nil, surface: Surface? = nil) throws -> String {
    let markers = try computeMarkers(rules, surface)
    let body = try renderBlock(prog, "", markers)
    return body.isEmpty ? "" : body + "\n"
}
