// Canonical.swift — the canonical AST text form, for agreement.
//
// The Swift counterpart of js/canonical.mjs: a faithful port of
// test_parser_in_planes.py's canonical(). One node per line, two-space
// indentation for depth, the node type then its fields in declaration order, leaf
// values quoted and escaped so quotes and newlines survive. parser.py, the js
// parser and this one all emit the same text and the suites compare strings (A.3,
// reuse the existing form — do not invent a fourth). A divergence in this form is
// a divergence in the test, not the implementation, so it mirrors the Python
// renderer exactly, tuple shapes and all: each branch below is one of
// _render_value's or _render_list_item's `isinstance` tests, in their order.

private func renderScalar(_ v: ASTValue) -> String {
    switch v {
    case .none: return "nothing"
    case let .bool(b): return b ? "true" : "false"
    case let .string(s): return "\"\(escapeStringLiteral(s))\""
    case let .int(n): return String(n)
    case let .number(n): return n.text()  // str(Number) is its text form
    // str() of a node or a sequence. No field the parser builds reaches a
    // scalar position holding one; this only keeps the function total.
    case let .node(n): return n.kind.rawValue
    case let .list(items): return "[" + items.map(renderScalar).joined(separator: ", ") + "]"
    case let .tuple(items): return "(" + items.map(renderScalar).joined(separator: ", ") + ")"
    }
}

/// `str(key)`, escaped — the key of a pair is always text in practice.
private func keyText(_ v: ASTValue) -> String {
    if case let .string(s) = v { return escapeStringLiteral(s) }
    return escapeStringLiteral(renderScalar(v))
}

private func renderListItem(_ item: ASTValue, _ indent: String, _ out: inout [String]) {
    if case let .node(n) = item {
        out.append("\(indent)-")
        renderNode(n, indent + "  ", &out)
        return
    }
    guard case let .tuple(pair) = item, pair.count == 2 else {
        out.append("\(indent)- \(renderScalar(item))")
        return
    }
    let (key, val) = (pair[0], pair[1])
    if case let .node(n) = val {
        out.append("\(indent)- \"\(keyText(key))\":")
        renderNode(n, indent + "  ", &out)
        return
    }
    if case let .tuple(inner) = val, inner.count == 2 {
        // A (key, (tag, payload)) pair, where the payload may itself be a node —
        // When.pattern's and Foreign.effects's shapes.
        let (tag, payload) = (inner[0], inner[1])
        let tagText: String
        if case let .string(s) = tag { tagText = s } else { tagText = renderScalar(tag) }
        let head = "\(indent)- \"\(keyText(key))\" \(tagText):"
        if case let .node(n) = payload {
            out.append(head)
            renderNode(n, indent + "  ", &out)
        } else {
            out.append("\(head) \(renderScalar(payload))")
        }
        return
    }
    // A plain pair — Use.renames's (old, new), Note.entries's ("from", "..."),
    // and a Foreign effect with no target: ("kind", None).
    out.append("\(indent)- (\(renderScalar(key)), \(renderScalar(val)))")
}

private func renderValue(_ name: String, _ v: ASTValue, _ indent: String, _ out: inout [String]) {
    switch v {
    case let .node(n):
        out.append("\(indent)\(name):")
        renderNode(n, indent + "  ", &out)
    case let .list(items), let .tuple(items):
        out.append("\(indent)\(name): [\(items.count)]")
        for item in items { renderListItem(item, indent + "  ", &out) }
    default:
        out.append("\(indent)\(name): \(renderScalar(v))")
    }
}

private func renderNode(_ node: AST.Node, _ indent: String, _ out: inout [String]) {
    out.append("\(indent)\(node.kind.rawValue)")
    for f in node.fields {
        renderValue(f.name, f.value, indent + "  ", &out)
    }
}

/// The canonical text form of one AST node.
public func canonical(_ node: AST.Node) -> String {
    var out: [String] = []
    renderNode(node, "", &out)
    return out.joined(separator: "\n")
}

/// The canonical text form of a whole program: canonical() per top-level
/// statement, joined — matches test_parser_in_planes.py's canonical_program.
public func canonicalProgram(_ stmts: [AST.Node]) -> String {
    var out: [String] = []
    for s in stmts { renderNode(s, "", &out) }
    return out.joined(separator: "\n")
}
