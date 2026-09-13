// CoreRestrict.swift — the core-restricted mode's policy, as pure data.
//
// The Swift counterpart of js/core_restrict.mjs. grammar/core.json declares the
// PORT SURFACE: the keywords and builtins a second host must implement in order to
// run grammar/interp.planes. core_check.py enforces that interp.planes never
// MENTIONS a construct outside the declared core; the converse — THAT THE
// DECLARED CORE IS ENOUGH — is testable only by a host that implements the core
// and REFUSES everything else. This module says which keywords a given AST node's
// construct spends, so an interpreter can refuse AT THE MOMENT OF EVALUATION.
//
// This file holds no copy of the core: grammar/core.json's lists are read at
// runtime (Grammar.swift's core()). What IS here is the association between an
// AST node kind and the keywords its construct is written with.
import Foundation

// ================================================================ node -> keywords
//
// Every keyword a node kind can EVER carry, ignoring the node's own fields, in
// js's order. The completeness check (coverageGaps) reads this: a keyword in no
// entry would be a construct the restricted mode is structurally blind to.
public let KEYWORDS_A_NODE_CAN_CARRY: [(kind: AST.Kind, keywords: [String])] = [
    // --- statements
    (.Use, ["use", "with", "as"]),
    (.Foreign, ["foreign", "from", "of", "doing"]),
    (.Rule, ["rule", "not", "to"]),
    (.FuncDef, ["to", "of"]),
    (.Assign, ["let"]),
    (.Give, ["give"]),
    (.Show, ["show"]),
    (.Why, ["why"]),
    (.If, ["if", "else"]),
    (.When, ["when", "else"]),
    (.Fail, ["fail", "as"]),
    (.ForEach, ["for", "each", "in", "where"]),
    // --- expressions
    (.Num, []),
    (.Str, []),
    (.Var, []),
    (.Field, []),
    (.ListLit, []),
    (.RecordLit, []),
    (.Bool, ["true", "false"]),
    (.Nothing, ["nothing"]),
    (.IsNothing, ["nothing"]),
    (.Not, ["not"]),
    (.ListPlus, ["plus"]),
    (.RecordUpdate, ["with"]),
    (.BinOp, ["and", "or", "in", "first", "of"]),
    (.Call, ["of"]),
    (.Builtin, ["of"]),
    (.Round, ["round", "to", "places"]),
    (.WriteTo, ["write", "to"]),
    (.OrFail, ["or", "fail", "as"]),
    // --- parsed, never evaluated. `note:` and `because` are NAME tokens, not
    // reserved words, so neither carries a keyword; the nodes are listed so a
    // node kind reaching the checker is never an unknown one.
    (.Note, []),
    (.Because, []),
]

// `first N of L` is the one BinOp whose operator is spelled with two reserved
// words. The comparison operators (<, ==, ...) are OP tokens and no keyword.
// NOT A VOCABULARY TABLE: `and`/`or`/`in`/`first` are the only operators ever
// spelled with a keyword at all — the whole closed set.
private let BINOP_KEYWORDS: [(op: String, keywords: [String])] = [
    ("and", ["and"]),
    ("or", ["or"]),
    ("in", ["in"]),
    ("first", ["first", "of"]),
]

// One keyword is carried but NOT DISTINGUISHABLE at evaluation time: `round x to
// 2 places` and `round x to 2` produce the identical Round node. A Round node is
// treated as spending `places` whether the author wrote the word or not.
public let APPROXIMATE_KEYWORDS: [(keyword: String, reason: String)] = [
    ("places", "optional in the source and unrecorded in the AST; a Round node is " +
        "read as spending it either way"),
]

/// The keywords THIS node spends, given its own fields. A subset of
/// KEYWORDS_A_NODE_CAN_CARRY[kind] by construction.
public func keywordsOf(_ node: AST.Node) -> [String] {
    switch node {
    case let n as AST.Use:
        return n.renames.isEmpty ? ["use"] : ["use", "with", "as"]
    case let n as AST.Foreign:
        var out = ["foreign", "from"]
        if !n.params.isEmpty { out.append("of") }
        if n.declared { out.append("doing") }
        return out
    case let n as AST.Rule:
        var out = ["rule"]
        if sameText(n.assertion, "forbid") { out.append("not") }
        if n.target != nil { out.append("to") }
        return out
    case let n as AST.FuncDef:
        return n.params.isEmpty ? ["to"] : ["to", "of"]
    case let n as AST.Assign:
        return n.isLet ? ["let"] : []
    case is AST.Give:
        return ["give"]
    case is AST.Show:
        return ["show"]
    case is AST.Why:
        return ["why"]
    case let n as AST.If:
        return n.els.isEmpty ? ["if"] : ["if", "else"]
    case let n as AST.When:
        return n.els.isEmpty ? ["when"] : ["when", "else"]
    case is AST.Fail:
        return ["fail", "as"]
    case let n as AST.ForEach:
        return n.whereClause != nil ? ["for", "each", "in", "where"] : ["for", "each", "in"]
    case let n as AST.Bool:
        return n.value ? ["true"] : ["false"]
    case is AST.Nothing, is AST.IsNothing:
        return ["nothing"]
    case is AST.Not:
        return ["not"]
    case is AST.ListPlus:
        return ["plus"]
    case is AST.RecordUpdate:
        return ["with"]
    case let n as AST.BinOp:
        return BINOP_KEYWORDS.first { sameText($0.op, n.op) }?.keywords ?? []
    case let n as AST.Call:
        return n.args.isEmpty ? [] : ["of"]
    case is AST.Builtin:
        return ["of"]
    case is AST.Round:
        return ["round", "to", "places"]
    case is AST.WriteTo:
        return ["write", "to"]
    case is AST.OrFail:
        return ["or", "fail", "as"]
    default:
        return []
    }
}

// ================================================================ completeness

/// The keywords no node kind carries, sorted. The suite asserts the answer is
/// empty: an assertion whose subject cannot go missing without it noticing.
public func coverageGaps(_ allKeywords: [String]) -> [String] {
    var carried = Set<CodePoints>()
    for entry in KEYWORDS_A_NODE_CAN_CARRY {
        for w in entry.keywords { carried.insert(CodePoints(w)) }
    }
    return allKeywords.map(CodePoints.init).filter { !carried.contains($0) }.sorted().map(\.string)
}

/// The node kinds that could possibly spend a keyword outside `coreKeywords`.
/// Everything else takes the fast path in the interpreter and is never
/// inspected. Derived from the core document, not hand-listed.
public func suspectKinds(_ coreKeywords: Set<CodePoints>) -> Set<AST.Kind> {
    var out = Set<AST.Kind>()
    for entry in KEYWORDS_A_NODE_CAN_CARRY where entry.keywords.contains(where: { !coreKeywords.contains(CodePoints($0)) }) {
        out.insert(entry.kind)
    }
    return out
}

// ================================================================ source lines
//
// A refusal names the construct, the file and the LINE. Most AST nodes carry no
// line, and giving them one would change the AST's shape, which
// grammar/parser.planes pins. So the line rides beside the AST (Node's
// `stampedLine`, never one of its `fields`), stamped by the parser at the one
// choke point every statement passes through. Off unless a restricted
// interpreter turns it on.

private final class LineRecording: @unchecked Sendable {
    let lock = NSLock()
    var on = false
}

private let recording = LineRecording()

public func recordLines(_ on: Swift.Bool) {
    recording.lock.lock()
    defer { recording.lock.unlock() }
    recording.on = on
}

public func recordingLines() -> Swift.Bool {
    recording.lock.lock()
    defer { recording.lock.unlock() }
    return recording.on
}

/// First write wins: the innermost parse that produced the node knows its own
/// start token, and an enclosing rule that returns the same object must not
/// overwrite it with a line further left.
@discardableResult
public func noteLine(_ node: AST.Node, _ line: Int) -> AST.Node {
    if !recordingLines() { return node }
    if node.stampedLine == nil { node.stampedLine = line }
    return node
}

/// The node's own start line where one was stamped, then its own `line` field for
/// the nodes that have one, then nil — the caller falls back to the enclosing
/// statement's line and says which it used.
public func lineOf(_ node: AST.Node?) -> Int? {
    guard let node else { return nil }
    if let stamped = node.stampedLine { return stamped }
    for f in node.fields where sameText(f.name, "line") {
        if case let .int(n) = f.value, n > 0 { return n }
    }
    return nil
}
