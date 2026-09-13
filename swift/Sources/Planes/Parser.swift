// Parser.swift — the Planes parser, ported from parser.py.
//
// The Swift counterpart of js/parser.mjs, keeping its structure and its (Python)
// method names so the three can be read side by side. Recursive descent, turning
// a token stream into the AST of Nodes.swift. Checked against parser.py's parse()
// by canonical-AST agreement on every corpus file (test_swift_parser.py); the four
// amber disambiguation sites are exercised against the synthetic ambiguous
// fixtures in probe/amber/. parser.py's output is the specification, and every
// message below is its text, byte for byte.
//
// One structural difference from both references: parser.py and js hold the name
// table in a class attribute (`Parser.known_funcs`) that parse() overwrites before
// each parse. Here it is the parser instance's own, handed over by parse(), so two
// parses cannot see each other's table. Nothing else reads it.
import Foundation

// Two or more readings of the same source, and nothing says which. A program the
// name table cannot resolve, not a malformed one — a subclass, so every catch of
// PlanesSyntaxError still catches it, matching parser.py.
public final class PlanesAmbiguity: PlanesSyntaxError, @unchecked Sendable {}

/// A cross-file name table entry's arity: a count, or nil where the arity is not
/// known (parser.py's `None`).
public typealias KnownName = (name: String, arity: Int?)

// ================================================================ text helpers

/// Python's `s[1:-1]`, by code point: a STRING token's value without its quotes,
/// or a FINGERPRINT's without its `@` when `dropLast` is false.
private func strip1(_ s: String, dropLast: Bool = true) -> String {
    let cps = Array(s.unicodeScalars)
    let end = dropLast ? cps.count - 1 : cps.count
    guard end > 1 else { return "" }
    return String(String.UnicodeScalarView(cps[1..<end]))
}

/// Python's `value or "end of line"`.
private func orEndOfLine(_ s: String) -> String {
    s.isEmpty ? "end of line" : s
}

/// Python's `sorted(...)` over text, then `", ".join(...)`.
private func sortedJoined(_ words: [String]) -> String {
    words.map(CodePoints.init).sorted().map(\.string).joined(separator: ", ")
}

private func sortedJoined(_ words: Set<CodePoints>) -> String {
    words.sorted().map(\.string).joined(separator: ", ")
}

/// Python's `name.split(" ")`.
private func splitOnSpace(_ s: String) -> [String] {
    s.unicodeScalars.split(separator: " ", omittingEmptySubsequences: false)
        .map { String(String.UnicodeScalarView($0)) }
}

// ================================================================ amber messages

/// Python's `str.format(**slots)` for the templates in
/// grammar/messages/amber.json: `{name}` slots and the `{{`/`}}` escapes. A slot
/// the site did not fill, or any other replacement-field syntax, is refused —
/// str.format would raise on the first and the templates use none of the second.
private func fmt(_ template: String, _ slots: [(String, String)]) throws -> String {
    let cps = Array(template.unicodeScalars)
    var out = String.UnicodeScalarView()
    var i = 0
    func refuse(_ why: String) -> GrammarDataError {
        GrammarDataError("grammar-data-missing", "amber template \(GrammarJSON.string(template).jsonText) \(why)",
                         "regenerate with python3 scripts/swift_grammar_gen.py")
    }
    while i < cps.count {
        let c = cps[i]
        if c == "{" {
            if i + 1 < cps.count, cps[i + 1] == "{" {
                out.append("{")
                i += 2
                continue
            }
            guard let close = cps[(i + 1)...].firstIndex(of: "}") else { throw refuse("has an unclosed '{'") }
            let name = String(String.UnicodeScalarView(cps[(i + 1)..<close]))
            guard let value = slots.first(where: { sameText($0.0, name) })?.1 else {
                throw refuse("names a slot {\(name)} its raise site does not fill")
            }
            out.append(contentsOf: value.unicodeScalars)
            i = close + 1
        } else if c == "}" {
            guard i + 1 < cps.count, cps[i + 1] == "}" else { throw refuse("has a single '}'") }
            out.append("}")
            i += 2
        } else {
            out.append(c)
            i += 1
        }
    }
    return String(out)
}

/// Render one of amber's refusal messages from grammar/messages/amber.json.
/// `readings` is a list of (source, gloss) pairs, lettered A, B, C in order.
public func renderAmber(_ templateId: String, _ line: Int, _ readings: [(String, String)],
                        _ slots: [(String, String)] = []) throws -> String {
    guard let t = try amberTemplates()[templateId] else {
        throw GrammarDataError("grammar-data-missing", "grammar/messages/amber.json has no template \(templateId)",
                               "regenerate with python3 scripts/swift_grammar_gen.py")
    }
    func part(_ key: String) throws -> String {
        guard let s = t[key]?.string else {
            throw GrammarDataError("grammar-data-missing", "amber template \(templateId) has no \(key)",
                                   "regenerate with python3 scripts/swift_grammar_gen.py")
        }
        return s
    }
    let base = [("line", String(line))] + slots
    var lines = [try fmt(part("headline"), base), ""]
    for (i, (source, gloss)) in readings.enumerated() {
        let letter = String(Unicode.Scalar(UInt8(ascii: "A") + UInt8(i)))
        lines.append(try fmt(part("readings"), [("letter", letter), ("source", source), ("gloss", gloss)]))
    }
    lines.append("")
    lines.append(try fmt(part("reason"), base))
    lines.append(try fmt(part("fix"), base))
    return lines.joined(separator: "\n")
}

// ================================================================ the parser

public final class Parser {
    let toks: [Token]
    var i = 0
    // A multi-line bracket literal raises the indentation on its continuation
    // lines, so the tokenizer emits a BEGIN inside the brackets whose matching END
    // lands AFTER the closing bracket. This counts the leaked ENDs owed so
    // skip_blank can absorb them before the block sees them.
    var pending_ends = 0
    let knownFuncs: [CodePoints: Int?]
    let tables: LexerTables

    init(_ tokens: [Token], _ knownFuncs: [CodePoints: Int?]) throws {
        toks = tokens
        self.knownFuncs = knownFuncs
        tables = try ensureCompiled()
    }

    // Python's Parser.known_funcs.get(name): the stored arity, or nil for unknown
    // — and nil when absent, so absent and known-unknown both read as nil, exactly
    // as `.get` returning None does.
    func arityOf(_ name: String) -> Int? {
        knownFuncs[CodePoints(name)] ?? nil
    }

    func knows(_ name: String) -> Bool {
        knownFuncs.index(forKey: CodePoints(name)) != nil
    }

    // ---- token helpers

    func peek(_ k: Int = 0) -> Token {
        toks[min(i + k, toks.count - 1)]
    }

    // The token stream always ends in EOF and nothing consumes an EOF, so `i`
    // never passes the last token; the clamp only keeps an impossible read from
    // trapping.
    @discardableResult
    func next() -> Token {
        let t = toks[min(i, toks.count - 1)]
        i += 1
        return t
    }

    func at(_ kind: String, _ value: String? = nil) -> Bool {
        let t = peek()
        return sameText(t.kind, kind) && (value.map { sameText(t.value, $0) } ?? true)
    }

    func accept(_ kind: String, _ value: String? = nil) -> Token? {
        at(kind, value) ? next() : nil
    }

    // The generic token expectation, with the two ways it can name a fix (S8,
    // identical to parser.py's): a reserved word where a NAME was wanted gets its
    // own message, and every other site may pass a `fix` clause.
    @discardableResult
    func expect(_ kind: String, _ value: String? = nil, fix: String? = nil) throws -> Token {
        if let t = accept(kind, value) { return t }
        let g = peek()
        let found = orEndOfLine(g.value)
        if sameText(kind, "NAME"), tables.keywords.contains(CodePoints(g.value)) {
            throw PlanesSyntaxError(
                "line \(g.line): '\(found)' is a keyword, so it cannot be " +
                    "used as a name\n" +
                    "  keyword names are reserved like builtins; pick " +
                    "another name")
        }
        let wanted = (value?.isEmpty ?? true) ? kind.lowercased() : value!
        if let fix, !fix.isEmpty {
            throw PlanesSyntaxError(
                "line \(g.line): expected \(wanted), " +
                    "found '\(found)'\n  \(fix)")
        }
        throw PlanesSyntaxError(
            "line \(g.line): expected \(wanted), " +
                "found '\(found)'",
            noFix: "this is the generic token gate, reached from every " +
                "form in the grammar; it knows which token was due and " +
                "not what the author meant by writing another, so a " +
                "call site that can say more passes `fix=` and a call " +
                "site that cannot says nothing rather than guessing")
    }

    func check_binding_name(_ name: String, _ line: Int, _ what: String) throws {
        if tables.builtinNames.contains(CodePoints(name)) {
            throw PlanesSyntaxError(
                "line \(line): '\(name)' is a builtin, so it cannot be \(what)\n" +
                    "  builtin names are reserved like keywords; pick another " +
                    "name (a function definition may still shadow it with " +
                    "`to \(name) ...:`)")
        }
    }

    func skip_blank() {
        while accept("EOL") != nil || accept("OP", ";") != nil {}
        while pending_ends > 0 && at("END") {
            _ = accept("END")
            pending_ends -= 1
            while accept("EOL") != nil || accept("OP", ";") != nil {}
        }
    }

    func skip_bracket_ws() {
        while true {
            if accept("EOL") != nil || accept("OP", ";") != nil { continue }
            if accept("BEGIN") != nil {
                pending_ends += 1
                continue
            }
            if accept("END") != nil {
                // an END inside the brackets balances a BEGIN already counted
                if pending_ends > 0 { pending_ends -= 1 }
                continue
            }
            break
        }
    }

    // ---- structure

    func parse_program() throws -> [AST.Node] {
        var stmts: [AST.Node] = []
        skip_blank()
        while !at("EOF") {
            if accept("END") != nil {
                skip_blank()
                continue
            }
            stmts.append(try parse_statement())
            skip_blank()
        }
        return stmts
    }

    func parse_block() throws -> [AST.Node] {
        if accept("EOL") != nil {
            try expect("BEGIN")
            var stmts: [AST.Node] = []
            skip_blank()
            while !at("END") && !at("EOF") {
                stmts.append(try parse_statement())
                skip_blank()
            }
            _ = accept("END")
            return stmts
        }
        return [try parse_statement()]
    }

    // ---- statements
    //
    // The one choke point every statement passes through, and therefore the one
    // place the core-restricted mode's line stamp goes (CoreRestrict.swift). Not
    // taken at all unless a restricted interpreter armed it.
    func parse_statement() throws -> AST.Node {
        if !recordingLines() { return try parse_statement_body() }
        let line = peek().line
        return noteLine(try parse_statement_body(), line)
    }

    func parse_statement_body() throws -> AST.Node {
        if accept("USE") != nil {
            let module = try expect("NAME").value
            var renames: [(old: String, new: String)] = []
            var with_tok = accept("WITH")
            while let tok = with_tok {
                let old = try read_multiword_name()
                try check_rename_name_ambiguity(old, tok)
                try expect("AS")
                let nw = try read_multiword_name()
                renames.append((old, nw))
                with_tok = accept("WITH")
            }
            return AST.Use(module, renames)
        }

        if at("FOREIGN") { return try parse_foreign() }

        if at("RULE") { return try parse_because(try parse_rule()) }

        if at("NAME", "note") && sameText(peek(1).kind, "OP") && sameText(peek(1).value, ":") {
            return try parse_note()
        }

        if at("TO") && sameText(peek(1).kind, "NAME") { return try parse_funcdef() }

        if accept("GIVE") != nil { return AST.Give(try parse_expr()) }

        if let show_tok = accept("SHOW") { return AST.Show(try parse_expr(), show_tok.line) }

        if accept("WHY") != nil { return AST.Why(try parse_expr()) }

        if let write_tok = accept("WRITE") {
            let value = try parse_or()
            try expect("TO")
            let dest = try parse_or()
            return try trailing_or_fail(AST.WriteTo(value, dest, write_tok.line))
        }

        if accept("IF") != nil {
            let cond = try parse_expr()
            try expect("OP", ":")
            let then = try parse_block()
            var els: [AST.Node] = []
            let save = i
            skip_blank()
            if accept("ELSE") != nil {
                try expect("OP", ":")
                els = try parse_block()
            } else {
                i = save
            }
            return AST.If(cond, then, els)
        }

        if accept("WHEN") != nil { return try parse_when() }

        if at("FOR") { return try parse_foreach(false) }

        if accept("LET") != nil {
            let tok = try expect("NAME")
            try check_binding_name(tok.value, tok.line, "bound by `let`")
            try expect("OP", "=")
            return try parse_because(AST.Assign(tok.value, try parse_expr(), isLet: true))
        }

        if at("NAME") && sameText(peek(1).kind, "OP") && sameText(peek(1).value, "=") {
            let tok = next()
            try check_binding_name(tok.value, tok.line, "assigned to")
            next()
            return try parse_because(AST.Assign(tok.value, try parse_expr()))
        }

        if let fail_tok = accept("FAIL") {
            let message = try parse_expr()
            try expect("AS")
            let tag = try expect("NAME").value
            return AST.Fail(message, tag, fail_tok.line)
        }

        return try parse_expr()
    }

    func parse_foreign() throws -> AST.Node {
        let foreign_tok = try expect("FOREIGN")
        var parts = [try expect("NAME").value]
        while at("NAME") { parts.append(next().value) }
        let name = parts.joined(separator: " ")
        var params: [String] = []
        if accept("OF") != nil {
            params.append(try read_param())
            while accept("OP", ",") != nil { params.append(try read_param()) }
        }
        try expect("FROM")
        let target = strip1(try expect("STRING").value)
        var effects: [AST.EffectClaim] = []
        var declared = false
        if accept("DOING") != nil {
            declared = true
            var claims = [try read_claim(params)]
            while accept("OP", ",") != nil { claims.append(try read_claim(params)) }
            effects = claims.filter { !sameText($0.kind, "nothing") }
        }
        return AST.Foreign(name, params, target, effects, declared, foreign_tok.line)
    }

    func read_claim(_ params: [String]) throws -> AST.EffectClaim {
        let kind = try read_effect_word()
        if sameText(kind, "nothing") { return AST.EffectClaim("nothing", nil) }
        if at("STRING") { return AST.EffectClaim(kind, .literal(strip1(next().value))) }
        if at("NAME") && params.contains(where: { sameText($0, peek().value) }) {
            return AST.EffectClaim(kind, .param(next().value))
        }
        if at("NAME") {
            let g = peek()
            let listed = params.joined(separator: ", ")
            throw PlanesSyntaxError(
                "line \(g.line): '\(g.value)' is not a parameter of this " +
                    "function, so it cannot be where '\(kind)' goes\n" +
                    "  parameters: \(listed.isEmpty ? "none" : listed)")
        }
        return AST.EffectClaim(kind, nil)
    }

    // §160: the membership check lives HERE, so an unknown effect name is refused
    // in every position that reads one. `allowNothing` is explicit rather than
    // inferred from `after`, so the grammar does not depend on a message's wording.
    func read_effect_word(_ after: String = "'doing'", _ allowNothing: Bool = true) throws -> String {
        let t = peek()
        let carriesText = ["NAME", "NOTHING", "SHOW", "WRITE"].contains { sameText($0, t.kind) }
        let word: String? = carriesText ? (t.value.isEmpty ? "nothing" : t.value) : nil
        let known = word.map { tables.effectKinds.has($0) || (allowNothing && sameText($0, "nothing")) } ?? false
        if !known {
            let found = word ?? orEndOfLine(t.value)
            throw PlanesSyntaxError(
                "line \(t.line): expected an effect name after \(after), " +
                    "found '\(found)'\n" +
                    "  valid kinds: \(sortedJoined(tables.effectKinds.keys)) — and " +
                    "'nothing' after 'doing', for a foreign that performs none")
        }
        next()
        return word!
    }

    func parse_rule() throws -> AST.Rule {
        let rule_tok = try expect("RULE")
        if !at("OP", "[") {
            let g = peek()
            throw PlanesSyntaxError(
                "line \(g.line): a rule needs a bracketed name, " +
                    "found '\(orEndOfLine(g.value))'\n" +
                    "  try: rule [name-here] subject may not effect-kind")
        }
        next()
        if !at("NAME") {
            let g = peek()
            throw PlanesSyntaxError(
                "line \(g.line): a rule's bracketed name must be a word, " +
                    "found '\(orEndOfLine(g.value))'\n" +
                    "  try: rule [name-here] subject may not effect-kind")
        }
        let name = next().value
        try expect("OP", "]")
        let subject = try expect("NAME").value
        if !at("NAME", "may") {
            let g = peek()
            throw PlanesSyntaxError(
                "line \(g.line): expected 'may not' or 'may' after a " +
                    "rule's subject, found '\(orEndOfLine(g.value))'\n" +
                    "  try: rule [\(name)] \(subject) may not effect-kind  " +
                    "(forbid)\n" +
                    "    or: rule [\(name)] \(subject) may effect-kind  " +
                    "(permit)")
        }
        next()
        let assertion = accept("NOT") != nil ? "forbid" : "permit"
        let verb = sameText(assertion, "forbid") ? "may not" : "may"
        let form = "rule [\(name)] \(subject) \(verb) effect-kind"
        // §160: one check, in read_effect_word, for both positions.
        let kind = try read_effect_word("'\(verb)'", false)
        var target: String?
        if accept("TO") != nil { target = strip1(try expect("STRING").value) }
        var supersedes: String?
        var supersedes_fingerprint: String?
        if at("NAME", "supersedes") {
            next()
            if !at("OP", "[") {
                let g = peek()
                throw PlanesSyntaxError(
                    "line \(g.line): 'supersedes' needs a bracketed rule " +
                        "name, found '\(orEndOfLine(g.value))'\n" +
                        "  try: \(form) supersedes [other-rule-name]")
            }
            next()
            if !at("NAME") {
                let g = peek()
                throw PlanesSyntaxError(
                    "line \(g.line): 'supersedes' needs a bracketed rule " +
                        "name, found '\(orEndOfLine(g.value))'\n" +
                        "  try: \(form) supersedes [other-rule-name]")
            }
            let superseded = next().value
            supersedes = superseded
            try expect("OP", "]")
            if at("FINGERPRINT") {
                supersedes_fingerprint = strip1(next().value, dropLast: false)
            } else if at("OP", "@") {
                let at_tok = next()
                let bad = peek()
                throw PlanesSyntaxError(
                    "line \(at_tok.line): a fingerprint must be exactly " +
                        "six hex characters after '@', found " +
                        "'\(orEndOfLine(bad.value))'\n" +
                        "  try: \(form) supersedes [\(superseded)] @abcdef " +
                        "— or omit it for an unverified override")
            }
        }
        return AST.Rule(name, subject, kind, target, rule_tok.line, supersedes, assertion, supersedes_fingerprint)
    }

    func parse_funcdef() throws -> AST.Node {
        try expect("TO")
        var parts = [try expect("NAME").value]
        while at("NAME") { parts.append(next().value) }
        let name = parts.joined(separator: " ")
        var params: [String] = []
        if accept("OF") != nil {
            params.append(try read_param())
            while accept("OP", ",") != nil { params.append(try read_param()) }
        }
        try expect("OP", ":")
        return AST.FuncDef(name, params, try parse_block())
    }

    func read_param() throws -> String {
        let tok = try expect("NAME")
        try check_binding_name(tok.value, tok.line, "a parameter")
        return tok.value
    }

    func read_tag() throws -> String {
        let tok = try expect("NAME")
        try check_binding_name(tok.value, tok.line, "an `or fail` tag")
        return tok.value
    }

    func parse_foreach(_ as_expr: Bool) throws -> AST.Node {
        try expect("FOR")
        try expect("EACH")
        let var_tok = try expect("NAME")
        try check_binding_name(var_tok.value, var_tok.line, "a `for each` loop variable")
        let varName = var_tok.value
        try expect("IN")
        let source = try parse_or()
        // header may wrap: `for each s in stories` \n `  where ...: s`
        var wrapped = false
        if at("EOL") && sameText(peek(1).kind, "BEGIN")
            && (sameText(peek(2).kind, "WHERE") || sameText(peek(2).kind, "OP")) {
            next()
            next()
            wrapped = true
        }
        var whereClause: AST.Node?
        if accept("WHERE") != nil { whereClause = try parse_or() }
        try expect("OP", ":")
        if wrapped {
            let body = [try parse_expr()]
            skip_blank()
            _ = accept("END")
            return AST.ForEach(varName, source, whereClause, body, isExpr: true)
        }
        if as_expr {
            let body: [AST.Node]
            if accept("EOL") != nil {
                try expect("BEGIN")
                body = [try parse_expr()]
                skip_blank()
                _ = accept("END")
            } else {
                body = [try parse_expr()]
            }
            return AST.ForEach(varName, source, whereClause, body, isExpr: true)
        }
        return AST.ForEach(varName, source, whereClause, try parse_block(), isExpr: false)
    }

    func trailing_or_fail(_ node: AST.Node) throws -> AST.Node {
        let save = i
        if at("OR") && sameText(peek(1).kind, "FAIL") {
            next()
            next()
            try expect("AS")
            let tag = try read_tag()
            var handler: [AST.Node]?
            if at("OP", ":") {
                next()
                handler = try parse_block()
            }
            return AST.OrFail(node, tag, handler)
        }
        if at("EOL") && sameText(peek(1).kind, "BEGIN")
            && sameText(peek(2).kind, "OR") && sameText(peek(3).kind, "FAIL") {
            next()
            next()
            next()
            next()
            try expect("AS")
            let tag = try read_tag()
            var handler: [AST.Node]?
            if at("OP", ":") {
                next()
                handler = try parse_block()
            }
            skip_blank()
            _ = accept("END")
            return AST.OrFail(node, tag, handler)
        }
        i = save
        return node
    }

    func parse_because<N: Annotated>(_ attach: N) throws -> N {
        let save = i
        if at("NAME", "because") {
            next()
            return try finish_because(attach)
        }
        if at("EOL") && sameText(peek(1).kind, "BEGIN")
            && sameText(peek(2).kind, "NAME") && sameText(peek(2).value, "because") {
            next()
            next()
            next()
            let node = try finish_because(attach)
            skip_blank()
            _ = accept("END")
            return node
        }
        i = save
        return attach
    }

    func finish_because<N: Annotated>(_ attach: N) throws -> N {
        let g = peek()
        if !at("STRING") {
            throw PlanesSyntaxError(
                "line \(g.line): 'because' needs a quoted reason\n" +
                    "  try: cap = 200 because \"the reason\"")
        }
        let text = strip1(next().value)
        attach.annotation = AST.Because(text, g.line)
        return attach
    }

    func parse_note() throws -> AST.Node {
        let note_tok = next()  // 'note'
        try expect("OP", ":")
        var entries: [(kind: String, value: String)] = []
        if accept("EOL") != nil {
            try expect("BEGIN")
            skip_blank()
            while !at("END") && !at("EOF") {
                entries.append(try parse_note_entry())
                skip_blank()
            }
            _ = accept("END")
        } else {
            entries.append(try parse_note_entry())
        }
        return AST.Note(entries, note_tok.line)
    }

    func parse_note_entry() throws -> (kind: String, value: String) {
        if at("FROM") {
            next()
            if !at("STRING") {
                let g = peek()
                throw PlanesSyntaxError(
                    "line \(g.line): 'from' in a note needs a quoted source\n" +
                        "  try: from \"the source\"")
            }
            return ("from", strip1(next().value))
        }
        if at("NAME", "derives-from") {
            next()
            if !at("OP", "[") {
                let g = peek()
                throw PlanesSyntaxError(
                    "line \(g.line): 'derives-from' needs a bracketed rule " +
                        "name, found '\(orEndOfLine(g.value))'\n" +
                        "  try: derives-from [rule-name]")
            }
            next()
            if !at("NAME") {
                let g = peek()
                throw PlanesSyntaxError(
                    "line \(g.line): 'derives-from' needs a bracketed rule " +
                        "name, found '\(orEndOfLine(g.value))'\n" +
                        "  try: derives-from [rule-name]")
            }
            let name = next().value
            try expect("OP", "]")
            return ("derives-from", name)
        }
        let g = peek()
        throw PlanesSyntaxError(
            "line \(g.line): unrecognised entry in a note, " +
                "found '\(orEndOfLine(g.value))'\n" +
                "  try: from \"source\"  or  derives-from [rule-name]")
    }

    // ---- expressions

    func parse_expr() throws -> AST.Node {
        try trailing_or_fail(try trailing_with(try parse_or()))
    }

    // Field names a with-clause or when-pattern entry may use —
    // grammar/vocabulary.json's field_name_token_kinds.
    func isFieldNameKind(_ kind: String) -> Bool {
        tables.fieldNameKinds.contains(CodePoints(kind))
    }

    func at_field_start(_ ahead: Int = 0) -> Bool {
        let t = peek(ahead)
        let nxt = peek(ahead + 1)
        return isFieldNameKind(t.kind) && sameText(nxt.kind, "OP") && sameText(nxt.value, ":")
    }

    func trailing_with(_ start: AST.Node) throws -> AST.Node {
        var node = start
        while at("WITH") && at_field_start(1) {
            next()
            var fields = [try parse_with_field()]
            while accept("OP", ",") != nil {
                if !at_field_start(0) {
                    i -= 1  // this comma belongs to an outer context
                    break
                }
                fields.append(try parse_with_field())
            }
            node = AST.RecordUpdate(node, fields)
        }
        return node
    }

    func parse_with_field() throws -> (name: String, expr: AST.Node) {
        skip_bracket_ws()
        let t = peek()
        let key: String
        if isFieldNameKind(t.kind) {
            key = next().value
        } else {
            throw PlanesSyntaxError(
                "line \(t.line): expected a field name, " +
                    "found '\(orEndOfLine(t.value))'\n" +
                    "  try: with name: value")
        }
        try expect("OP", ":")
        return (key, try trailing_or_fail(try parse_or()))
    }

    func parse_or() throws -> AST.Node {
        var left = try parse_and()
        while at("OR") && !sameText(peek(1).kind, "FAIL") {
            next()
            left = AST.BinOp("or", left, try parse_and())
        }
        return left
    }

    func parse_and() throws -> AST.Node {
        var left = try parse_not()
        while accept("AND") != nil { left = AST.BinOp("and", left, try parse_not()) }
        return left
    }

    func parse_not() throws -> AST.Node {
        if accept("NOT") != nil { return AST.Not(try parse_not()) }
        return try parse_comparison()
    }

    private static let comparisonOps = ["<", ">", "<=", ">=", "==", "!="]
    private static let additiveOps = ["+", "-"]
    private static let multiplicativeOps = ["*", "/"]
    private static let parenFollowOps = ["+", "-", "*", "/", "<", ">", "<=", ">=", "==", "!="]

    private func atOp(in ops: [String]) -> Bool {
        at("OP") && ops.contains { sameText($0, peek().value) }
    }

    func parse_comparison() throws -> AST.Node {
        var left = try parse_plus()
        while atOp(in: Parser.comparisonOps) || at("IN") || (at("NAME", "is") && sameText(peek(1).kind, "NOTHING")) {
            if accept("NAME", "is") != nil {
                try expect("NOTHING")
                left = AST.IsNothing(left)
                continue
            }
            if accept("IN") != nil {
                left = AST.BinOp("in", left, try parse_plus())
            } else {
                left = AST.BinOp(next().value, left, try parse_plus())
            }
        }
        return left
    }

    func parse_plus() throws -> AST.Node {
        var left = try parse_additive()
        while at("PLUS") {
            next()
            left = AST.ListPlus(left, try parse_additive())
        }
        return left
    }

    func parse_additive() throws -> AST.Node {
        var left = try parse_multiplicative()
        while atOp(in: Parser.additiveOps) {
            left = AST.BinOp(next().value, left, try parse_multiplicative())
        }
        return left
    }

    func parse_multiplicative() throws -> AST.Node {
        var left = try parse_unary()
        while atOp(in: Parser.multiplicativeOps) {
            left = AST.BinOp(next().value, left, try parse_unary())
        }
        return left
    }

    func parse_unary() throws -> AST.Node {
        if at("OP", "-") {
            next()
            return AST.BinOp("-", AST.Num(PlanesNumber.of(0)), try parse_unary())
        }
        return try parse_postfix()
    }

    func parse_postfix() throws -> AST.Node {
        var node = try parse_primary()
        while at("OP", ".") && (sameText(peek(1).kind, "NAME") || tables.keywords.contains(CodePoints(peek(1).value))) {
            next()
            node = AST.Field(node, next().value)
        }
        if at("OP", "[") {
            let g = peek()
            throw PlanesSyntaxError(
                "line \(g.line): '[' has no meaning here — Planes has no " +
                    "index or slice syntax\n" +
                    "  try: first n of x — takes the first n code points or " +
                    "items; there is no way to take one position or a range")
        }
        return node
    }

    func read_multiword_name() throws -> String {
        var parts: [String] = []
        while at("NAME") { parts.append(next().value) }
        if parts.isEmpty {
            let g = peek()
            throw PlanesSyntaxError(
                "line \(g.line): expected a name, " +
                    "found '\(orEndOfLine(g.value))'\n" +
                    "  a name here is one or more plain words — the old or the " +
                    "new spelling in a `use ... with <old> as <new>` rename; a " +
                    "quoted string, a number, or a punctuation mark cannot stand " +
                    "for one")
        }
        return parts.joined(separator: " ")
    }

    // Amber site 4 (§69.5). `name` (the `old` half of a rename) was consumed whole
    // by read_multiword_name; two or more known prefixes of it means the greedy
    // full consumption was not the only viable reading.
    func check_rename_name_ambiguity(_ name: String, _ tok: Token) throws {
        let parts = splitOnSpace(name)
        var hits: [Int] = []
        for k in stride(from: 1, through: parts.count, by: 1) where knows(parts[0..<k].joined(separator: " ")) {
            hits.append(k)
        }
        if hits.count < 2 { return }
        var readings: [(String, String)] = []
        for k in hits {
            let prefix = parts[0..<k].joined(separator: " ")
            let rest = parts[k...].joined(separator: " ")
            let gloss = rest.isEmpty ? "`\(prefix)` alone" : "`\(prefix)`, leaving `\(rest)` unaccounted for"
            readings.append((rest.isEmpty ? prefix : "\(prefix) | \(rest)", gloss))
        }
        let msg = try renderAmber("amber.rename_clause", tok.line, readings, [("source", name)])
        throw PlanesAmbiguity(msg)
    }

    // ---- amber message construction helpers, never consuming

    func _peek_text(_ start: Int, _ end: Int) -> String {
        var parts: [String] = []
        var k = start
        while k < end {
            let t = peek(k)
            parts.append(t.value.isEmpty ? t.kind : t.value)
            k += 1
        }
        return parts.joined(separator: " ")
    }

    func _peek_trailer(_ offset: Int, _ limit: Int = 4) -> String {
        var end = offset
        for n in 0..<limit {
            let tok = peek(offset + n)
            if ["EOL", "EOF", "END", "BEGIN"].contains(where: { sameText($0, tok.kind) }) { break }
            end = offset + n + 1
            if sameText(tok.kind, "OP") && (sameText(tok.value, ":") || sameText(tok.value, ";")) { break }
        }
        return _peek_text(offset, end)
    }

    func _matching_close_paren_offset(_ open_offset: Int) -> Int {
        var depth = 0
        var k = open_offset
        while true {
            let tok = peek(k)
            if sameText(tok.kind, "OP") && sameText(tok.value, "(") {
                depth += 1
            } else if sameText(tok.kind, "OP") && sameText(tok.value, ")") {
                depth -= 1
                if depth == 0 { return k + 1 }
            }
            k += 1
        }
    }

    func raise_amber_multiword(_ t: Token, _ name: String, _ bare_hit: Bool, _ ext_hits: [(Int, String)]) throws -> Never {
        var readings: [(String, String)] = []
        var labels: [String] = []
        if bare_hit {
            let trailer = _peek_trailer(0)
            let source = trailer.isEmpty ? name : "\(name)  then  \(trailer)"
            readings.append((source, "the value `\(name)`, then whatever parses next on its own"))
            labels.append("`\(name)`")
        }
        for (k, probe) in ext_hits {
            let trailer = _peek_trailer(k)
            let source = trailer.isEmpty ? probe : "\(probe)  \(trailer)"
            readings.append((source, "one call to `\(probe)`"))
            labels.append("`\(probe)`")
        }
        let names_txt: String
        if labels.count == 1 {
            names_txt = labels[0]
        } else if labels.count > 2 {
            names_txt = labels.dropLast().joined(separator: ", ") + ", and \(labels[labels.count - 1])"
        } else {
            names_txt = "\(labels[0]) and \(labels[1])"
        }
        let suggestion = ext_hits.last.map { "(\($0.1))" } ?? "(\(name))"
        let msg = try renderAmber("amber.multiword", t.line, readings, [("names", names_txt), ("suggestion", suggestion)])
        throw PlanesAmbiguity(msg)
    }

    func raise_amber_juxtaposition(_ t: Token, _ head: String, _ next_name: String) throws -> Never {
        let readings = [
            ("\(head) (\(next_name))",
             "one call to `\(head)`, passing the result of calling `\(next_name)`"),
            ("\(head)  then  \(next_name)",
             "`\(head)` with no argument, then a separate call to `\(next_name)`"),
        ]
        let msg = try renderAmber("amber.juxtaposition", t.line, readings, [("head", head), ("next", next_name)])
        throw PlanesAmbiguity(msg)
    }

    func raise_amber_juxtaposition_unknown(_ t: Token, _ subject: String) throws -> Never {
        let readings = [
            ("\(subject)(...)",
             "if `\(subject)` takes an argument here, one call using what follows"),
            ("\(subject)  then  ...",
             "if `\(subject)` takes no argument here, a separate statement follows"),
        ]
        let msg = try renderAmber("amber.juxtaposition.unknown_arity", t.line, readings, [("subject", subject)])
        throw PlanesAmbiguity(msg)
    }

    // Amber site 2 (§69.5). Returns whether the following NAME should be consumed
    // as the argument; raises when both readings fit.
    func check_juxtaposition_ambiguity(_ name: String, _ t: Token) throws -> Bool {
        guard let arity = arityOf(name) else { try raise_amber_juxtaposition_unknown(t, name) }
        if arity == 0 { return false }
        let next_name = peek().value
        if !knows(next_name) { return true }
        guard let next_arity = arityOf(next_name) else { try raise_amber_juxtaposition_unknown(t, next_name) }
        if next_arity == 0 { try raise_amber_juxtaposition(t, name, next_name) }
        return true
    }

    // Amber site 3 (§69.5). Called positioned at the `(`, right after
    // paren_is_arglist returned false for it.
    func check_paren_arglist_ambiguity(_ name: String, _ t: Token) throws {
        let arity = arityOf(name)
        let close = _matching_close_paren_offset(0)
        let paren_src = _peek_text(1, close - 1)
        let rest_src = _peek_trailer(close)
        guard let arity else {
            let readings = [
                ("\(name)(\(paren_src))", "if `\(name)` takes one argument here, this call alone"),
                (pythonStrip("\(name)(\(paren_src)) \(rest_src)"),
                 "if not, the whole expression including what follows"),
            ]
            let msg = try renderAmber("amber.paren_arglist.unknown_arity", t.line, readings, [("head", name)])
            throw PlanesAmbiguity(msg)
        }
        if arity != 1 { return }
        let readings = [
            (pythonStrip("\(name)(\(paren_src)) \(rest_src)"),
             "one call to `\(name)`, argument = everything up to and including `\(rest_src)`"),
            (pythonStrip("(\(name)(\(paren_src))) \(rest_src)"),
             "one call to `\(name)`, argument = `\(paren_src)` alone; " +
                "`\(rest_src)` applies to the call's result, not inside it"),
        ]
        let msg = try renderAmber("amber.paren_arglist", t.line, readings, [("head", name), ("paren_expr", paren_src)])
        throw PlanesAmbiguity(msg)
    }

    func paren_is_arglist() -> Bool {
        var depth = 0
        var k = 0
        while true {
            let t = peek(k)
            if sameText(t.kind, "EOF") { return true }
            if sameText(t.kind, "OP") && sameText(t.value, "(") {
                depth += 1
            } else if sameText(t.kind, "OP") && sameText(t.value, ")") {
                depth -= 1
                if depth == 0 {
                    let nxt = peek(k + 1)
                    if sameText(nxt.kind, "OP") && Parser.parenFollowOps.contains(where: { sameText($0, nxt.value) }) {
                        return false
                    }
                    return true
                }
            }
            k += 1
        }
    }

    func parse_record_field() throws -> (name: String, expr: AST.Node) {
        skip_bracket_ws()
        let t = peek()
        let key: String
        if sameText(t.kind, "NAME") {
            key = next().value
        } else if isFieldNameKind(t.kind) {
            key = next().value
        } else {
            throw PlanesSyntaxError(
                "line \(t.line): expected a field name, " +
                    "found '\(orEndOfLine(t.value))'\n" +
                    "  try: { name: value }")
        }
        try expect("OP", ":")
        return (key, try parse_expr())
    }

    func parse_when() throws -> AST.Node {
        let subject = try parse_expr()
        try expect("NAME", "is")
        try expect("OP", "{")
        var pattern: [(field: String, matcher: AST.Matcher)] = []
        skip_bracket_ws()
        if !at("OP", "}") {
            pattern.append(try parse_when_pattern_entry())
            while accept("OP", ",") != nil {
                skip_bracket_ws()
                if at("OP", "}") { break }
                pattern.append(try parse_when_pattern_entry())
            }
        }
        skip_bracket_ws()
        try expect("OP", "}")
        try expect("OP", ":")
        let body = try parse_block()
        var els: [AST.Node] = []
        let save = i
        skip_blank()
        if accept("ELSE") != nil {
            try expect("OP", ":")
            els = try parse_block()
        } else {
            i = save
        }
        return AST.When(subject, pattern, body, els)
    }

    func parse_when_pattern_entry() throws -> (field: String, matcher: AST.Matcher) {
        skip_bracket_ws()
        let t = peek()
        let name: String
        if sameText(t.kind, "NAME") || isFieldNameKind(t.kind) {
            name = next().value
        } else {
            throw PlanesSyntaxError(
                "line \(t.line): expected a field name, " +
                    "found '\(orEndOfLine(t.value))'\n" +
                    "  try: { name: value }  or  { name }")
        }
        if at("OP", ":") {
            next()
            return (name, .match(try parse_expr()))
        }
        try check_binding_name(name, t.line, "a `when` field binding")
        return (name, .bind(name))
    }

    func parse_primary() throws -> AST.Node {
        let t = peek()

        if sameText(t.kind, "FIRST") {
            next()
            let n = try parse_unary()
            try expect("OF")
            return AST.BinOp("first", n, try parse_unary())
        }

        if sameText(t.kind, "ROUND") {
            next()
            let value = try parse_unary()
            try expect("TO")
            let places = try parse_unary()
            _ = accept("PLACES")
            return AST.Round(value, places)
        }

        if sameText(t.kind, "FOR") { return try parse_foreach(true) }

        if sameText(t.kind, "NUMBER") {
            next()
            // Literals are exact: `0.1` is one tenth, not the nearest float.
            return AST.Num(try PlanesNumber.parse(t.value))
        }

        if sameText(t.kind, "STRING") {
            next()
            return AST.Str(strip1(t.value))
        }

        if sameText(t.kind, "TRUE") {
            next()
            return AST.Bool(true)
        }
        if sameText(t.kind, "FALSE") {
            next()
            return AST.Bool(false)
        }
        if sameText(t.kind, "NOTHING") {
            next()
            return AST.Nothing()
        }

        if sameText(t.kind, "OP") && sameText(t.value, "{") {
            next()
            var fields: [(name: String, expr: AST.Node)] = []
            skip_bracket_ws()
            if !at("OP", "}") {
                fields.append(try parse_record_field())
                while accept("OP", ",") != nil {
                    skip_bracket_ws()
                    if at("OP", "}") { break }  // trailing comma
                    fields.append(try parse_record_field())
                }
            }
            skip_bracket_ws()
            // The greedy-tail shape, named. `{ k: f of a, k2: 9 }` reads `k2` as a
            // second argument to `f`, then meets `:` where `}` was due.
            try expect("OP", "}",
                       fix: "a record is `{ name: value, ... }`; a call or " +
                           "`with` used as a field value takes the rest of " +
                           "the list, so parenthesise it: " +
                           "`{ k: (f of a, b), k2: 9 }`")
            var seen = Set<CodePoints>()
            for f in fields {
                let k = f.name
                if seen.contains(CodePoints(k)) {
                    throw PlanesSyntaxError(
                        "line \(t.line): field '\(k)' appears twice in this " +
                            "record\n  keep one of the two; to change a field's " +
                            "value later, build a new record from this one — " +
                            "`r with \(k): value`")
                }
                seen.insert(CodePoints(k))
            }
            return AST.RecordLit(fields)
        }

        if sameText(t.kind, "OP") && sameText(t.value, "[") {
            next()
            var items: [AST.Node] = []
            skip_bracket_ws()
            if !at("OP", "]") {
                items.append(try parse_expr())
                while accept("OP", ",") != nil {
                    skip_bracket_ws()
                    if at("OP", "]") { break }  // trailing comma
                    items.append(try parse_expr())
                }
            }
            skip_bracket_ws()
            try expect("OP", "]")
            return AST.ListLit(items)
        }

        if sameText(t.kind, "OP") && sameText(t.value, "(") {
            next()
            let e = try parse_expr()
            try expect("OP", ")")
            return e
        }

        if sameText(t.kind, "NAME") {
            next()
            let name = t.value
            if accept("OF") != nil {
                var args = [try parse_unary()]
                while accept("OP", ",") != nil { args.append(try parse_unary()) }
                return AST.Call(name, args, t.line)
            }
            if at("OP", "(") {
                // `add(2, 3)` is an argument list; `ask (api base) + "/"` is one
                // argument that merely starts with a parenthesis. Decide by what
                // follows the closing paren.
                if !paren_is_arglist() {
                    try check_paren_arglist_ambiguity(name, t)
                    return AST.Call(name, [try parse_additive()], t.line)
                }
                next()
                var args: [AST.Node] = []
                if !at("OP", ")") {
                    args.append(try parse_expr())
                    while accept("OP", ",") != nil { args.append(try parse_expr()) }
                }
                try expect("OP", ")")
                return AST.Call(name, args, t.line)
            }
            // multi-word name, longest match against known functions. Amber site 1
            // (§69.5): collect EVERY k (including k=0, the bare name itself) whose
            // joined text is a known function — two or more means the parser will
            // not silently prefer the longest.
            if at("NAME") {
                var ext_hits: [(Int, String)] = []
                var probe = name
                var k = 0
                while sameText(peek(k).kind, "NAME") {
                    probe += " " + peek(k).value
                    k += 1
                    if knows(probe) { ext_hits.append((k, probe)) }
                }
                let bare_hit = knows(name)
                if (bare_hit ? 1 : 0) + ext_hits.count >= 2 {
                    try raise_amber_multiword(t, name, bare_hit, ext_hits)
                }
                if let (j, best) = ext_hits.first {
                    for _ in 0..<j { next() }
                    if accept("OF") != nil {
                        var args = [try parse_unary()]
                        while accept("OP", ",") != nil { args.append(try parse_unary()) }
                        return AST.Call(best, args, t.line)
                    }
                    return AST.Call(best, [], t.line)
                }
            }
            if knows(name) {
                // A known function may take one argument by juxtaposition.
                var takes_arg = at("STRING") || at("NUMBER") || at("OP", "(") || at("OP", "[")
                if !takes_arg && at("NAME") {
                    takes_arg = try check_juxtaposition_ambiguity(name, t)
                }
                if takes_arg { return AST.Call(name, [try parse_additive()], t.line) }
                return AST.Call(name, [], t.line)
            }
            return AST.Var(name)
        }

        throw PlanesSyntaxError(
            "line \(t.line): expected a value, " +
                "found '\(orEndOfLine(t.value))'\n" +
                "  a value starts with a number, a quoted string, true, false, " +
                "nothing, a name, `not`, a list, a record, or a parenthesised " +
                "expression — a statement word like `show` or `write` cannot " +
                "stand in for one")
    }
}

// ================================================================ the name table

/// tokens[j], clamped to the final token. tokenize() always ends the stream in
/// EOF, which stops every scan below before it could run off the end, so the
/// clamp is unobservable on a real stream.
private func tokenAt(_ tokens: [Token], _ j: Int) -> Token {
    tokens[min(j, tokens.count - 1)]
}

private func _param_arity(_ tokens: [Token], _ start: Int) -> Int {
    var j = start
    if !sameText(tokenAt(tokens, j).kind, "NAME") { return 0 }
    var count = 1
    j += 1
    while sameText(tokenAt(tokens, j).kind, "OP") && sameText(tokenAt(tokens, j).value, ",")
        && sameText(tokenAt(tokens, j + 1).kind, "NAME") {
        count += 1
        j += 2
    }
    return count
}

/// Function names and arities, read before the real parse. A multi-word call is
/// several NAME tokens; only a name table can say they are one call. In source
/// order, as parser.py's dict is.
public func prescan_funcs(_ tokens: [Token]) throws -> TextTable<Int> {
    var names = TextTable<Int>()
    for (i, t) in tokens.enumerated() {
        if sameText(t.kind, "FOREIGN") {
            var j = i + 1
            var parts: [String] = []
            while sameText(tokenAt(tokens, j).kind, "NAME") {
                parts.append(tokenAt(tokens, j).value)
                j += 1
            }
            if !parts.isEmpty {
                let arity = sameText(tokenAt(tokens, j).kind, "OF") ? _param_arity(tokens, j + 1) : 0
                names[parts.joined(separator: " ")] = arity
            }
            continue
        }
        if !sameText(t.kind, "TO") { continue }
        // `to` also appears inside `write x to "path"`. A definition is the one
        // that starts a statement.
        if i > 0 && !["EOL", "BEGIN", "END"].contains(where: { sameText($0, tokens[i - 1].kind) }) { continue }
        // Collected as one span, all the way to the real end of the name --
        // `of`, a punctuation mark, end of line, or end of file -- rather
        // than stopping at the first non-NAME token. A reserved word can
        // land first (`to and dusk:`), in the middle (`to dawn and
        // dusk:`), or last (`to dawn dusk and:`); scanning past it instead
        // of stopping there is what lets the message quote the name
        // exactly as the author wrote it, instead of just the words seen
        // before the reserved word turned up.
        var j = i + 1
        var span: [Token] = []
        while !["OF", "OP", "EOL", "EOF"].contains(where: { sameText($0, tokenAt(tokens, j).kind) }) {
            span.append(tokenAt(tokens, j))
            j += 1
        }
        let bad = span.firstIndex(where: { !sameText($0.kind, "NAME") })
        if let bad {
            let word = span[bad]
            let fullName = span.map { $0.value }.joined(separator: " ")
            let fix = span.count > 1
                ? "join the words with a hyphen instead of a space, or reword " +
                  "to avoid '\(word.value)'"
                : "reword the name to avoid '\(word.value)'"
            if bad == 0 {
                throw PlanesSyntaxError(
                    "line \(word.line): '\(word.value)' is a reserved word " +
                        "and cannot start the function name '\(fullName)'\n" +
                        "  \(fix)")
            }
            throw PlanesSyntaxError(
                "line \(word.line): '\(word.value)' is a reserved word and " +
                    "cannot appear in the function name '\(fullName)'\n" +
                    "  \(fix)")
        }
        let parts = span.map { $0.value }
        let stop = tokenAt(tokens, j)
        let arity = sameText(stop.kind, "OF") ? _param_arity(tokens, j + 1) : 0
        names[parts.joined(separator: " ")] = arity
    }
    return names
}

/// Parse a program. `known` supplies function names defined elsewhere, each with
/// its arity or nil for unknown. This file's own definitions win over `known`,
/// which wins over a builtin.
public func parse(_ src: String, known: [KnownName]? = nil) throws -> [AST.Node] {
    let toks = try tokenize(src)
    var merged: [CodePoints: Int?] = [:]
    for (k, v) in try builtinsArity().entries { merged[CodePoints(k)] = .some(v) }
    for entry in known ?? [] { merged[CodePoints(entry.name)] = .some(entry.arity) }
    for (k, v) in try prescan_funcs(toks).entries { merged[CodePoints(k)] = .some(v) }
    return try Parser(toks, merged).parse_program()
}

/// parse(src, known) with a bare set of names — parser.py's iterable form, arity
/// unknown (None) for each.
public func parse(_ src: String, knownNames: [String]) throws -> [AST.Node] {
    try parse(src, known: knownNames.map { ($0, nil) })
}

/// Function names defined in a source file, without a full parse.
public func scan_names(_ src: String) throws -> TextTable<Int> {
    try prescan_funcs(tokenize(src))
}

// ================================================================ discarded-write

// Every `Var` name referenced anywhere inside `expr`, however deeply nested — a
// plain recursive walk over the fields, parser.py's `_names_read`.
private func namesRead(_ expr: AST.Node) -> Set<CodePoints> {
    var found = Set<CodePoints>()
    func walk(_ v: ASTValue) {
        switch v {
        case let .node(n):
            if let variable = n as? AST.Var {
                found.insert(CodePoints(variable.name))
                return
            }
            for f in n.fields { walk(f.value) }
        case let .list(items), let .tuple(items):
            for x in items { walk(x) }
        default:
            return
        }
    }
    walk(.node(expr))
    return found
}

// A chain of bound-name sets, opened only where the interpreter's runtime scoping
// opens one — at a `for each` and at a function body. `if`, `when` and an `or
// fail ... as tag:` handler run in the SAME env their surroundings do.
private final class WriteScope {
    var names = Set<CodePoints>()
    let parent: WriteScope?

    init(_ parent: WriteScope? = nil) { self.parent = parent }

    func bound(_ name: String) -> Bool {
        var scope: WriteScope? = self
        while let s = scope {
            if s.names.contains(CodePoints(name)) { return true }
            scope = s.parent
        }
        return false
    }

    func boundInAnAncestor(_ name: String) -> Bool {
        parent?.bound(name) ?? false
    }

    func bind(_ name: String) { names.insert(CodePoints(name)) }

    func child() -> WriteScope { WriteScope(self) }
}

/// The A-Q9 shape, found statically: `let NAME = expr` inside a loop body, where
/// `expr` reads `NAME` and `NAME` is already bound in an enclosing scope — so the
/// loop's own per-iteration binding shadows the outer one and every iteration's
/// write is discarded when it ends. Pure: the violating names, in the order
/// found.
public func findDiscardedWrites(_ prog: [AST.Node]) -> [String] {
    var violations: [String] = []

    func walkStmts(_ stmts: [AST.Node], _ scope: WriteScope, _ inLoop: Bool) {
        for s in stmts { walkStmt(s, scope, inLoop) }
    }

    func walkStmt(_ s: AST.Node, _ scope: WriteScope, _ inLoop: Bool) {
        switch s {
        case let a as AST.Assign:
            if a.isLet && inLoop && namesRead(a.expr).contains(CodePoints(a.name)) && scope.boundInAnAncestor(a.name) {
                violations.append(a.name)
            }
            scope.bind(a.name)
        case let f as AST.ForEach:
            let inner = scope.child()
            inner.bind(f.variable)
            walkStmts(f.body, inner, true)
        case let n as AST.If:
            // A child scope per branch, discarded after: which branch ran is a
            // runtime fact.
            walkStmts(n.then, scope.child(), inLoop)
            walkStmts(n.els, scope.child(), inLoop)
        case let w as AST.When:
            let bodyScope = scope.child()
            for entry in w.pattern {
                if case let .bind(name) = entry.matcher { bodyScope.bind(name) }
            }
            walkStmts(w.body, bodyScope, inLoop)
            walkStmts(w.els, scope.child(), inLoop)
        case let o as AST.OrFail:
            // The handler runs only on failure, so its bindings must not leak.
            if let handler = o.handler {
                let handlerScope = scope.child()
                handlerScope.bind(o.tag)
                walkStmts(handler, handlerScope, inLoop)
            }
        case let fn as AST.FuncDef:
            let fnScope = WriteScope()
            for p in fn.params { fnScope.bind(p) }
            walkStmts(fn.body, fnScope, false)
        default:
            return
        }
    }

    walkStmts(prog, WriteScope(), false)
    return violations
}
