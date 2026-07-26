// js/parser.mjs — the Planes parser, ported from parser.py.
//
// Recursive descent, turning a token stream into the AST of js/nodes.mjs.
// Checked against parser.py's parse() by canonical-AST agreement on every
// corpus file (test_js_parser.py); the four amber disambiguation sites are
// exercised against the synthetic ambiguous fixtures the Planes parser build
// wrote. parser.py's output is the specification.

import {
  tokenize,
  PlanesSyntaxError,
  keywords,
  effectKinds,
  builtinNames,
  builtinsArity,
  fieldNameKinds,
} from "./lexer.mjs";
import { PlanesNumber } from "./planes_num.mjs";
import { amberTemplates } from "./grammar_data.mjs";
import {
  Num,
  Str,
  Bool,
  Nothing,
  Var,
  ListLit,
  RecordLit,
  RecordUpdate,
  ListPlus,
  BinOp,
  Not,
  IsNothing,
  Field,
  Assign,
  Why,
  Use,
  FuncDef,
  Call,
  Give,
  Show,
  ForEach,
  If,
  When,
  OrFail,
  Fail,
  Foreign,
  WriteTo,
  Round,
  Rule,
  Because,
  Note,
  tup,
} from "./nodes.mjs";

// Two or more readings of the same source, and nothing says which. A program
// the name table cannot resolve, not a malformed one — the base is shared so
// every catch of PlanesSyntaxError still catches it, matching parser.py.
export class PlanesAmbiguity extends PlanesSyntaxError {
  constructor(message) {
    super(message);
    this.name = "PlanesAmbiguity";
  }
}

// Fill {name} placeholders from a slots object, the equivalent of Python str
// .format(**slots). The amber templates use only simple {identifier} slots.
function fmt(template, slots) {
  return template.replace(/\{(\w+)\}/g, (_, k) => String(slots[k]));
}

// Render one of amber's refusal messages from grammar/messages/amber.json.
// `readings` is a list of [source, gloss] pairs, lettered A, B, C in order.
export function renderAmber(templateId, line, readings, slots = {}) {
  const t = amberTemplates()[templateId];
  const base = { line, ...slots };
  const lines = [fmt(t.headline, base), ""];
  readings.forEach(([source, gloss], i) => {
    const letter = String.fromCharCode("A".charCodeAt(0) + i);
    lines.push(fmt(t.readings, { letter, source, gloss }));
  });
  lines.push("");
  lines.push(fmt(t.reason, base));
  lines.push(fmt(t.fix, base));
  return lines.join("\n");
}

export class Parser {
  static knownFuncs = new Map();

  constructor(tokens) {
    this.toks = tokens;
    this.i = 0;
    this.pending_ends = 0;
  }

  arityOf(name) {
    // Python's Parser.known_funcs.get(name): the stored value (an int arity or
    // null for unknown), or null when absent — so absent and known-unknown both
    // read as null, exactly as `.get` returning None does.
    const v = Parser.knownFuncs.get(name);
    return v === undefined ? null : v;
  }
  knows(name) {
    return Parser.knownFuncs.has(name);
  }

  // ---- token helpers
  peek(k = 0) {
    return this.toks[Math.min(this.i + k, this.toks.length - 1)];
  }
  next() {
    return this.toks[this.i++];
  }
  at(kind, value = null) {
    const t = this.peek();
    return t.kind === kind && (value === null || t.value === value);
  }
  accept(kind, value = null) {
    return this.at(kind, value) ? this.next() : null;
  }
  // The generic token expectation, with the two ways it can name a fix
  // (S8, identical to parser.py's). `errors name the fix` is a language-level
  // commitment, and a bare token mismatch honours its letter and not its
  // substance: `expected }, found ':'` is true and tells nobody what to write.
  //   * a reserved word where a NAME was wanted gets its own message — that is
  //     never a punctuation slip, it is the 42-name reserved surface (32
  //     keywords + 10 builtins) being hit. The builtin half already errored
  //     naming the collision; this is the keyword half, in the same voice.
  //   * every other site may pass a `fix` clause naming what to write instead.
  expect(kind, value = null, fix = null) {
    const t = this.accept(kind, value);
    if (t === null) {
      const g = this.peek();
      const found = g.value || "end of line";
      if (kind === "NAME" && keywords().has(g.value)) {
        throw new PlanesSyntaxError(
          `line ${g.line}: '${found}' is a keyword, so it cannot be used as a name\n` +
            `  keyword names are reserved like builtins; pick another name`,
        );
      }
      let msg = `line ${g.line}: expected ${value || kind.toLowerCase()}, found '${found}'`;
      if (fix) msg += `\n  ${fix}`;
      throw new PlanesSyntaxError(msg);
    }
    return t;
  }

  check_binding_name(name, line, what) {
    if (builtinNames().has(name)) {
      throw new PlanesSyntaxError(
        `line ${line}: '${name}' is a builtin, so it cannot be ${what}\n` +
          `  builtin names are reserved like keywords; pick another ` +
          `name (a function definition may still shadow it with ` +
          `\`to ${name} ...:\`)`,
      );
    }
  }

  skip_blank() {
    while (this.accept("EOL") || this.accept("OP", ";")) {
      // skip
    }
    while (this.pending_ends > 0 && this.at("END")) {
      this.accept("END");
      this.pending_ends -= 1;
      while (this.accept("EOL") || this.accept("OP", ";")) {
        // skip
      }
    }
  }

  skip_bracket_ws() {
    for (;;) {
      if (this.accept("EOL") || this.accept("OP", ";")) continue;
      if (this.accept("BEGIN")) {
        this.pending_ends += 1;
        continue;
      }
      if (this.accept("END")) {
        if (this.pending_ends > 0) this.pending_ends -= 1;
        continue;
      }
      break;
    }
  }

  // ---- structure
  parse_program() {
    const stmts = [];
    this.skip_blank();
    while (!this.at("EOF")) {
      if (this.accept("END")) {
        this.skip_blank();
        continue;
      }
      stmts.push(this.parse_statement());
      this.skip_blank();
    }
    return stmts;
  }

  parse_block() {
    if (this.accept("EOL")) {
      this.expect("BEGIN");
      const stmts = [];
      this.skip_blank();
      while (!this.at("END") && !this.at("EOF")) {
        stmts.push(this.parse_statement());
        this.skip_blank();
      }
      this.accept("END");
      return stmts;
    }
    return [this.parse_statement()];
  }

  // ---- statements
  parse_statement() {
    if (this.accept("USE")) {
      const module = this.expect("NAME").value;
      const renames = [];
      let with_tok = this.accept("WITH");
      while (with_tok) {
        const old = this.read_multiword_name();
        this.check_rename_name_ambiguity(old, with_tok);
        this.expect("AS");
        const nw = this.read_multiword_name();
        renames.push(tup(old, nw));
        with_tok = this.accept("WITH");
      }
      return Use(module, renames);
    }

    if (this.at("FOREIGN")) return this.parse_foreign();

    if (this.at("RULE")) return this.parse_because(this.parse_rule());

    if (
      this.at("NAME", "note") &&
      this.peek(1).kind === "OP" &&
      this.peek(1).value === ":"
    ) {
      return this.parse_note();
    }

    if (this.at("TO") && this.peek(1).kind === "NAME") return this.parse_funcdef();

    if (this.accept("GIVE")) return Give(this.parse_expr());

    const show_tok = this.accept("SHOW");
    if (show_tok) return Show(this.parse_expr(), show_tok.line);

    if (this.accept("WHY")) return Why(this.parse_expr());

    const write_tok = this.accept("WRITE");
    if (write_tok) {
      const value = this.parse_or();
      this.expect("TO");
      const dest = this.parse_or();
      return this.trailing_or_fail(WriteTo(value, dest, write_tok.line));
    }

    if (this.accept("IF")) {
      const cond = this.parse_expr();
      this.expect("OP", ":");
      const then = this.parse_block();
      let els = [];
      const save = this.i;
      this.skip_blank();
      if (this.accept("ELSE")) {
        this.expect("OP", ":");
        els = this.parse_block();
      } else {
        this.i = save;
      }
      return If(cond, then, els);
    }

    if (this.accept("WHEN")) return this.parse_when();

    if (this.at("FOR")) return this.parse_foreach(false);

    if (this.accept("LET")) {
      const tok = this.expect("NAME");
      this.check_binding_name(tok.value, tok.line, "bound by `let`");
      this.expect("OP", "=");
      return this.parse_because(Assign(tok.value, this.parse_expr(), true));
    }

    if (
      this.at("NAME") &&
      this.peek(1).kind === "OP" &&
      this.peek(1).value === "="
    ) {
      const tok = this.next();
      this.check_binding_name(tok.value, tok.line, "assigned to");
      this.next();
      return this.parse_because(Assign(tok.value, this.parse_expr()));
    }

    const fail_tok = this.accept("FAIL");
    if (fail_tok) {
      const message = this.parse_expr();
      this.expect("AS");
      const tag = this.expect("NAME").value;
      return Fail(message, tag, fail_tok.line);
    }

    return this.parse_expr();
  }

  parse_foreign() {
    const foreign_tok = this.expect("FOREIGN");
    const parts = [this.expect("NAME").value];
    while (this.at("NAME")) parts.push(this.next().value);
    const name = parts.join(" ");
    const params = [];
    if (this.accept("OF")) {
      params.push(this.read_param());
      while (this.accept("OP", ",")) params.push(this.read_param());
    }
    this.expect("FROM");
    const target = this.expect("STRING").value.slice(1, -1);
    let effects = [];
    let declared = false;
    if (this.accept("DOING")) {
      declared = true;
      const claims = [this.read_claim(params)];
      while (this.accept("OP", ",")) claims.push(this.read_claim(params));
      effects = claims.filter((c) => c.items[0] !== "nothing");
    }
    return Foreign(name, params, target, effects, declared, foreign_tok.line);
  }

  read_claim(params) {
    const kind = this.read_effect_word();
    if (kind === "nothing") return tup("nothing", null);
    if (this.at("STRING")) return tup(kind, tup("literal", this.next().value.slice(1, -1)));
    if (this.at("NAME") && params.includes(this.peek().value)) {
      return tup(kind, tup("param", this.next().value));
    }
    if (this.at("NAME")) {
      const g = this.peek();
      throw new PlanesSyntaxError(
        `line ${g.line}: '${g.value}' is not a parameter of this ` +
          `function, so it cannot be where '${kind}' goes\n` +
          `  parameters: ${params.join(", ") || "none"}`,
      );
    }
    return tup(kind, null);
  }

  read_effect_word(after = "'doing'") {
    const t = this.peek();
    if (["NAME", "NOTHING", "SHOW", "WRITE"].includes(t.kind)) {
      this.next();
      return t.value || "nothing";
    }
    throw new PlanesSyntaxError(
      `line ${t.line}: expected an effect name after ${after}, ` +
        `found '${t.value || "end of line"}'`,
    );
  }

  parse_rule() {
    const rule_tok = this.expect("RULE");
    if (!this.at("OP", "[")) {
      const g = this.peek();
      throw new PlanesSyntaxError(
        `line ${g.line}: a rule needs a bracketed name, ` +
          `found '${g.value || "end of line"}'\n` +
          `  try: rule [name-here] subject may not effect-kind`,
      );
    }
    this.next();
    if (!this.at("NAME")) {
      const g = this.peek();
      throw new PlanesSyntaxError(
        `line ${g.line}: a rule's bracketed name must be a word, ` +
          `found '${g.value || "end of line"}'\n` +
          `  try: rule [name-here] subject may not effect-kind`,
      );
    }
    const name = this.next().value;
    this.expect("OP", "]");
    const subject = this.expect("NAME").value;
    if (!this.at("NAME", "may")) {
      const g = this.peek();
      throw new PlanesSyntaxError(
        `line ${g.line}: expected 'may not' or 'may' after a ` +
          `rule's subject, found '${g.value || "end of line"}'\n` +
          `  try: rule [${name}] ${subject} may not effect-kind  ` +
          `(forbid)\n` +
          `    or: rule [${name}] ${subject} may effect-kind  ` +
          `(permit)`,
      );
    }
    this.next();
    const assertion = this.accept("NOT") ? "forbid" : "permit";
    const verb = assertion === "forbid" ? "may not" : "may";
    const form = `rule [${name}] ${subject} ${verb} effect-kind`;
    const kind_tok = this.peek();
    const kind = this.read_effect_word(`'${verb}'`);
    if (!effectKinds().has(kind)) {
      throw new PlanesSyntaxError(
        `line ${kind_tok.line}: '${kind}' is not an effect kind a ` +
          `rule can name\n` +
          `  valid kinds: ${[...effectKinds().keys()].sort().join(", ")}`,
      );
    }
    let target = null;
    if (this.accept("TO")) target = this.expect("STRING").value.slice(1, -1);
    let supersedes = null;
    let supersedes_fingerprint = null;
    if (this.at("NAME", "supersedes")) {
      this.next();
      if (!this.at("OP", "[")) {
        const g = this.peek();
        throw new PlanesSyntaxError(
          `line ${g.line}: 'supersedes' needs a bracketed rule ` +
            `name, found '${g.value || "end of line"}'\n` +
            `  try: ${form} supersedes [other-rule-name]`,
        );
      }
      this.next();
      if (!this.at("NAME")) {
        const g = this.peek();
        throw new PlanesSyntaxError(
          `line ${g.line}: 'supersedes' needs a bracketed rule ` +
            `name, found '${g.value || "end of line"}'\n` +
            `  try: ${form} supersedes [other-rule-name]`,
        );
      }
      supersedes = this.next().value;
      this.expect("OP", "]");
      if (this.at("FINGERPRINT")) {
        supersedes_fingerprint = this.next().value.slice(1);
      } else if (this.at("OP", "@")) {
        const at_tok = this.next();
        const bad = this.peek();
        throw new PlanesSyntaxError(
          `line ${at_tok.line}: a fingerprint must be exactly ` +
            `six hex characters after '@', found ` +
            `'${bad.value || "end of line"}'\n` +
            `  try: ${form} supersedes [${supersedes}] @abcdef ` +
            `— or omit it for an unverified override`,
        );
      }
    }
    return Rule(
      name,
      subject,
      kind,
      target,
      rule_tok.line,
      supersedes,
      assertion,
      supersedes_fingerprint,
    );
  }

  parse_funcdef() {
    this.expect("TO");
    const parts = [this.expect("NAME").value];
    while (this.at("NAME")) parts.push(this.next().value);
    const name = parts.join(" ");
    const params = [];
    if (this.accept("OF")) {
      params.push(this.read_param());
      while (this.accept("OP", ",")) params.push(this.read_param());
    }
    this.expect("OP", ":");
    return FuncDef(name, params, this.parse_block());
  }

  read_param() {
    const tok = this.expect("NAME");
    this.check_binding_name(tok.value, tok.line, "a parameter");
    return tok.value;
  }

  read_tag() {
    const tok = this.expect("NAME");
    this.check_binding_name(tok.value, tok.line, "an `or fail` tag");
    return tok.value;
  }

  parse_foreach(as_expr) {
    this.expect("FOR");
    this.expect("EACH");
    const var_tok = this.expect("NAME");
    this.check_binding_name(var_tok.value, var_tok.line, "a `for each` loop variable");
    const varName = var_tok.value;
    this.expect("IN");
    const source = this.parse_or();
    let wrapped = false;
    if (
      this.at("EOL") &&
      this.peek(1).kind === "BEGIN" &&
      ["WHERE", "OP"].includes(this.peek(2).kind)
    ) {
      this.next();
      this.next();
      wrapped = true;
    }
    let where = null;
    if (this.accept("WHERE")) where = this.parse_or();
    this.expect("OP", ":");
    if (wrapped) {
      const body = [this.parse_expr()];
      this.skip_blank();
      this.accept("END");
      return ForEach(varName, source, where, body, true);
    }
    if (as_expr) {
      let body;
      if (this.accept("EOL")) {
        this.expect("BEGIN");
        body = [this.parse_expr()];
        this.skip_blank();
        this.accept("END");
      } else {
        body = [this.parse_expr()];
      }
      return ForEach(varName, source, where, body, true);
    }
    return ForEach(varName, source, where, this.parse_block(), false);
  }

  trailing_or_fail(node) {
    const save = this.i;
    if (this.at("OR") && this.peek(1).kind === "FAIL") {
      this.next();
      this.next();
      this.expect("AS");
      const tag = this.read_tag();
      let handler = null;
      if (this.at("OP", ":")) {
        this.next();
        handler = this.parse_block();
      }
      return OrFail(node, tag, handler);
    }
    if (
      this.at("EOL") &&
      this.peek(1).kind === "BEGIN" &&
      this.peek(2).kind === "OR" &&
      this.peek(3).kind === "FAIL"
    ) {
      this.next();
      this.next();
      this.next();
      this.next();
      this.expect("AS");
      const tag = this.read_tag();
      let handler = null;
      if (this.at("OP", ":")) {
        this.next();
        handler = this.parse_block();
      }
      this.skip_blank();
      this.accept("END");
      return OrFail(node, tag, handler);
    }
    this.i = save;
    return node;
  }

  parse_because(attach) {
    const save = this.i;
    if (this.at("NAME", "because")) {
      this.next();
      return this.finish_because(attach);
    }
    if (
      this.at("EOL") &&
      this.peek(1).kind === "BEGIN" &&
      this.peek(2).kind === "NAME" &&
      this.peek(2).value === "because"
    ) {
      this.next();
      this.next();
      this.next();
      const node = this.finish_because(attach);
      this.skip_blank();
      this.accept("END");
      return node;
    }
    this.i = save;
    return attach;
  }

  finish_because(attach) {
    const g = this.peek();
    if (!this.at("STRING")) {
      throw new PlanesSyntaxError(
        `line ${g.line}: 'because' needs a quoted reason\n` +
          `  try: cap = 200 because "the reason"`,
      );
    }
    const text = this.next().value.slice(1, -1);
    attach.annotation = Because(text, g.line);
    return attach;
  }

  parse_note() {
    const note_tok = this.next(); // 'note'
    this.expect("OP", ":");
    const entries = [];
    if (this.accept("EOL")) {
      this.expect("BEGIN");
      this.skip_blank();
      while (!this.at("END") && !this.at("EOF")) {
        entries.push(this.parse_note_entry());
        this.skip_blank();
      }
      this.accept("END");
    } else {
      entries.push(this.parse_note_entry());
    }
    return Note(entries, note_tok.line);
  }

  parse_note_entry() {
    if (this.at("FROM")) {
      this.next();
      if (!this.at("STRING")) {
        const g = this.peek();
        throw new PlanesSyntaxError(
          `line ${g.line}: 'from' in a note needs a quoted source\n` +
            `  try: from "the source"`,
        );
      }
      return tup("from", this.next().value.slice(1, -1));
    }
    if (this.at("NAME", "derives-from")) {
      this.next();
      if (!this.at("OP", "[")) {
        const g = this.peek();
        throw new PlanesSyntaxError(
          `line ${g.line}: 'derives-from' needs a bracketed rule ` +
            `name, found '${g.value || "end of line"}'\n` +
            `  try: derives-from [rule-name]`,
        );
      }
      this.next();
      if (!this.at("NAME")) {
        const g = this.peek();
        throw new PlanesSyntaxError(
          `line ${g.line}: 'derives-from' needs a bracketed rule ` +
            `name, found '${g.value || "end of line"}'\n` +
            `  try: derives-from [rule-name]`,
        );
      }
      const name = this.next().value;
      this.expect("OP", "]");
      return tup("derives-from", name);
    }
    const g = this.peek();
    throw new PlanesSyntaxError(
      `line ${g.line}: unrecognised entry in a note, ` +
        `found '${g.value || "end of line"}'\n` +
        `  try: from "source"  or  derives-from [rule-name]`,
    );
  }

  // ---- expressions
  parse_expr() {
    return this.trailing_or_fail(this.trailing_with(this.parse_or()));
  }

  at_field_start(ahead = 0) {
    const t = this.peek(ahead);
    const nxt = this.peek(ahead + 1);
    return (
      fieldNameKinds().has(t.kind) && nxt.kind === "OP" && nxt.value === ":"
    );
  }

  trailing_with(node) {
    while (this.at("WITH") && this.at_field_start(1)) {
      this.next();
      const fields = [this.parse_with_field()];
      while (this.accept("OP", ",")) {
        if (!this.at_field_start(0)) {
          this.i -= 1;
          break;
        }
        fields.push(this.parse_with_field());
      }
      node = RecordUpdate(node, fields);
    }
    return node;
  }

  parse_with_field() {
    this.skip_bracket_ws();
    const t = this.peek();
    let key;
    if (fieldNameKinds().has(t.kind)) {
      key = this.next().value;
    } else {
      throw new PlanesSyntaxError(
        `line ${t.line}: expected a field name, ` +
          `found '${t.value || "end of line"}'\n` +
          `  try: with name: value`,
      );
    }
    this.expect("OP", ":");
    return tup(key, this.trailing_or_fail(this.parse_or()));
  }

  parse_or() {
    let left = this.parse_and();
    while (this.at("OR") && this.peek(1).kind !== "FAIL") {
      this.next();
      left = BinOp("or", left, this.parse_and());
    }
    return left;
  }

  parse_and() {
    let left = this.parse_not();
    while (this.accept("AND")) left = BinOp("and", left, this.parse_not());
    return left;
  }

  parse_not() {
    if (this.accept("NOT")) return Not(this.parse_not());
    return this.parse_comparison();
  }

  parse_comparison() {
    let left = this.parse_plus();
    while (
      (this.at("OP") &&
        ["<", ">", "<=", ">=", "==", "!="].includes(this.peek().value)) ||
      this.at("IN") ||
      (this.at("NAME", "is") && this.peek(1).kind === "NOTHING")
    ) {
      if (this.accept("NAME", "is")) {
        this.expect("NOTHING");
        left = IsNothing(left);
        continue;
      }
      if (this.accept("IN")) {
        left = BinOp("in", left, this.parse_plus());
      } else {
        left = BinOp(this.next().value, left, this.parse_plus());
      }
    }
    return left;
  }

  parse_plus() {
    let left = this.parse_additive();
    while (this.at("PLUS")) {
      this.next();
      left = ListPlus(left, this.parse_additive());
    }
    return left;
  }

  parse_additive() {
    let left = this.parse_multiplicative();
    while (this.at("OP") && ["+", "-"].includes(this.peek().value)) {
      left = BinOp(this.next().value, left, this.parse_multiplicative());
    }
    return left;
  }

  parse_multiplicative() {
    let left = this.parse_unary();
    while (this.at("OP") && ["*", "/"].includes(this.peek().value)) {
      left = BinOp(this.next().value, left, this.parse_unary());
    }
    return left;
  }

  parse_unary() {
    if (this.at("OP", "-")) {
      this.next();
      return BinOp("-", Num(new PlanesNumber(0n)), this.parse_unary());
    }
    return this.parse_postfix();
  }

  parse_postfix() {
    let node = this.parse_primary();
    while (
      this.at("OP", ".") &&
      (this.peek(1).kind === "NAME" || keywords().has(this.peek(1).value))
    ) {
      this.next();
      node = Field(node, this.next().value);
    }
    if (this.at("OP", "[")) {
      const g = this.peek();
      throw new PlanesSyntaxError(
        `line ${g.line}: '[' has no meaning here — Planes has no ` +
          `index or slice syntax\n` +
          `  try: first n of x — takes the first n code points or ` +
          `items; there is no way to take one position or a range`,
      );
    }
    return node;
  }

  read_multiword_name() {
    const parts = [];
    while (this.at("NAME")) parts.push(this.next().value);
    if (parts.length === 0) {
      const g = this.peek();
      throw new PlanesSyntaxError(
        `line ${g.line}: expected a name, found '${g.value || "end of line"}'`,
      );
    }
    return parts.join(" ");
  }

  check_rename_name_ambiguity(name, tok) {
    const parts = name.split(" ");
    const hits = [];
    for (let k = 1; k <= parts.length; k++) {
      if (this.knows(parts.slice(0, k).join(" "))) hits.push(k);
    }
    if (hits.length < 2) return;
    const readings = [];
    for (const k of hits) {
      const prefix = parts.slice(0, k).join(" ");
      const rest = parts.slice(k).join(" ");
      const gloss = !rest
        ? `\`${prefix}\` alone`
        : `\`${prefix}\`, leaving \`${rest}\` unaccounted for`;
      readings.push([!rest ? prefix : `${prefix} | ${rest}`, gloss]);
    }
    const msg = renderAmber("amber.rename_clause", tok.line, readings, {
      source: name,
    });
    throw new PlanesAmbiguity(msg);
  }

  // ---- amber message construction helpers, never consuming
  _peek_text(start, end) {
    const parts = [];
    for (let k = start; k < end; k++) {
      parts.push(this.peek(k).value || this.peek(k).kind);
    }
    return parts.join(" ");
  }

  _peek_trailer(offset, limit = 4) {
    let end = offset;
    for (let i = 0; i < limit; i++) {
      const tok = this.peek(offset + i);
      if (["EOL", "EOF", "END", "BEGIN"].includes(tok.kind)) break;
      end = offset + i + 1;
      if (tok.kind === "OP" && [":", ";"].includes(tok.value)) break;
    }
    return this._peek_text(offset, end);
  }

  _matching_close_paren_offset(open_offset) {
    let depth = 0;
    let k = open_offset;
    for (;;) {
      const tok = this.peek(k);
      if (tok.kind === "OP" && tok.value === "(") depth += 1;
      else if (tok.kind === "OP" && tok.value === ")") {
        depth -= 1;
        if (depth === 0) return k + 1;
      }
      k += 1;
    }
  }

  raise_amber_multiword(t, name, bare_hit, ext_hits) {
    const readings = [];
    const labels = [];
    if (bare_hit) {
      const trailer = this._peek_trailer(0);
      const source = !trailer ? name : `${name}  then  ${trailer}`;
      readings.push([source, `the value \`${name}\`, then whatever parses next on its own`]);
      labels.push(`\`${name}\``);
    }
    for (const [k, probe] of ext_hits) {
      const trailer = this._peek_trailer(k);
      const source = !trailer ? probe : `${probe}  ${trailer}`;
      readings.push([source, `one call to \`${probe}\``]);
      labels.push(`\`${probe}\``);
    }
    let names_txt;
    if (labels.length === 1) names_txt = labels[0];
    else if (labels.length > 2) {
      names_txt = labels.slice(0, -1).join(", ") + `, and ${labels[labels.length - 1]}`;
    } else names_txt = `${labels[0]} and ${labels[1]}`;
    const suggestion = ext_hits.length
      ? `(${ext_hits[ext_hits.length - 1][1]})`
      : `(${name})`;
    const msg = renderAmber("amber.multiword", t.line, readings, {
      names: names_txt,
      suggestion,
    });
    throw new PlanesAmbiguity(msg);
  }

  raise_amber_juxtaposition(t, head, next_name) {
    const readings = [
      [
        `${head} (${next_name})`,
        `one call to \`${head}\`, passing the result of calling \`${next_name}\``,
      ],
      [
        `${head}  then  ${next_name}`,
        `\`${head}\` with no argument, then a separate call to \`${next_name}\``,
      ],
    ];
    const msg = renderAmber("amber.juxtaposition", t.line, readings, {
      head,
      next: next_name,
    });
    throw new PlanesAmbiguity(msg);
  }

  raise_amber_juxtaposition_unknown(t, subject) {
    const readings = [
      [
        `${subject}(...)`,
        `if \`${subject}\` takes an argument here, one call using what follows`,
      ],
      [
        `${subject}  then  ...`,
        `if \`${subject}\` takes no argument here, a separate statement follows`,
      ],
    ];
    const msg = renderAmber("amber.juxtaposition.unknown_arity", t.line, readings, {
      subject,
    });
    throw new PlanesAmbiguity(msg);
  }

  check_juxtaposition_ambiguity(name, t) {
    const arity = this.arityOf(name);
    if (arity === null) this.raise_amber_juxtaposition_unknown(t, name);
    if (arity === 0) return false;
    const next_name = this.peek().value;
    if (!this.knows(next_name)) return true;
    const next_arity = this.arityOf(next_name);
    if (next_arity === null) this.raise_amber_juxtaposition_unknown(t, next_name);
    if (next_arity === 0) this.raise_amber_juxtaposition(t, name, next_name);
    return true;
  }

  check_paren_arglist_ambiguity(name, t) {
    const arity = this.arityOf(name);
    const close = this._matching_close_paren_offset(0);
    const paren_src = this._peek_text(1, close - 1);
    const rest_src = this._peek_trailer(close);
    if (arity === null) {
      const readings = [
        [`${name}(${paren_src})`, `if \`${name}\` takes one argument here, this call alone`],
        [
          `${name}(${paren_src}) ${rest_src}`.trim(),
          "if not, the whole expression including what follows",
        ],
      ];
      const msg = renderAmber("amber.paren_arglist.unknown_arity", t.line, readings, {
        head: name,
      });
      throw new PlanesAmbiguity(msg);
    }
    if (arity !== 1) return;
    const readings = [
      [
        `${name}(${paren_src}) ${rest_src}`.trim(),
        `one call to \`${name}\`, argument = everything up to and including \`${rest_src}\``,
      ],
      [
        `(${name}(${paren_src})) ${rest_src}`.trim(),
        `one call to \`${name}\`, argument = \`${paren_src}\` alone; ` +
          `\`${rest_src}\` applies to the call's result, not inside it`,
      ],
    ];
    const msg = renderAmber("amber.paren_arglist", t.line, readings, {
      head: name,
      paren_expr: paren_src,
    });
    throw new PlanesAmbiguity(msg);
  }

  paren_is_arglist() {
    let depth = 0;
    let k = 0;
    for (;;) {
      const t = this.peek(k);
      if (t.kind === "EOF") return true;
      if (t.kind === "OP" && t.value === "(") depth += 1;
      else if (t.kind === "OP" && t.value === ")") {
        depth -= 1;
        if (depth === 0) {
          const nxt = this.peek(k + 1);
          if (
            nxt.kind === "OP" &&
            ["+", "-", "*", "/", "<", ">", "<=", ">=", "==", "!="].includes(nxt.value)
          ) {
            return false;
          }
          return true;
        }
      }
      k += 1;
    }
  }

  parse_record_field() {
    this.skip_bracket_ws();
    const t = this.peek();
    let key;
    if (t.kind === "NAME") key = this.next().value;
    else if (fieldNameKinds().has(t.kind)) key = this.next().value;
    else {
      throw new PlanesSyntaxError(
        `line ${t.line}: expected a field name, ` +
          `found '${t.value || "end of line"}'\n` +
          `  try: { name: value }`,
      );
    }
    this.expect("OP", ":");
    return tup(key, this.parse_expr());
  }

  parse_when() {
    const subject = this.parse_expr();
    this.expect("NAME", "is");
    this.expect("OP", "{");
    const pattern = [];
    this.skip_bracket_ws();
    if (!this.at("OP", "}")) {
      pattern.push(this.parse_when_pattern_entry());
      while (this.accept("OP", ",")) {
        this.skip_bracket_ws();
        if (this.at("OP", "}")) break;
        pattern.push(this.parse_when_pattern_entry());
      }
    }
    this.skip_bracket_ws();
    this.expect("OP", "}");
    this.expect("OP", ":");
    const body = this.parse_block();
    let els = [];
    const save = this.i;
    this.skip_blank();
    if (this.accept("ELSE")) {
      this.expect("OP", ":");
      els = this.parse_block();
    } else {
      this.i = save;
    }
    return When(subject, pattern, body, els);
  }

  parse_when_pattern_entry() {
    this.skip_bracket_ws();
    const t = this.peek();
    let name;
    if (t.kind === "NAME" || fieldNameKinds().has(t.kind)) {
      name = this.next().value;
    } else {
      throw new PlanesSyntaxError(
        `line ${t.line}: expected a field name, ` +
          `found '${t.value || "end of line"}'\n` +
          `  try: { name: value }  or  { name }`,
      );
    }
    if (this.at("OP", ":")) {
      this.next();
      return tup(name, tup("match", this.parse_expr()));
    }
    this.check_binding_name(name, t.line, "a `when` field binding");
    return tup(name, tup("bind", name));
  }

  parse_primary() {
    const t = this.peek();

    if (t.kind === "FIRST") {
      this.next();
      const n = this.parse_unary();
      this.expect("OF");
      return BinOp("first", n, this.parse_unary());
    }

    if (t.kind === "ROUND") {
      this.next();
      const value = this.parse_unary();
      this.expect("TO");
      const places = this.parse_unary();
      this.accept("PLACES");
      return Round(value, places);
    }

    if (t.kind === "FOR") return this.parse_foreach(true);

    if (t.kind === "NUMBER") {
      this.next();
      return Num(PlanesNumber.parse(t.value));
    }

    if (t.kind === "STRING") {
      this.next();
      return Str(t.value.slice(1, -1));
    }

    if (t.kind === "TRUE") {
      this.next();
      return Bool(true);
    }
    if (t.kind === "FALSE") {
      this.next();
      return Bool(false);
    }
    if (t.kind === "NOTHING") {
      this.next();
      return Nothing();
    }

    if (t.kind === "OP" && t.value === "{") {
      this.next();
      const fields = [];
      this.skip_bracket_ws();
      if (!this.at("OP", "}")) {
        fields.push(this.parse_record_field());
        while (this.accept("OP", ",")) {
          this.skip_bracket_ws();
          if (this.at("OP", "}")) break;
          fields.push(this.parse_record_field());
        }
      }
      this.skip_bracket_ws();
      // The greedy-tail shape, named. `{ k: f of a, k2: 9 }` reads `k2` as a
      // second argument to `f`, then meets `:` where `}` was due.
      this.expect(
        "OP",
        "}",
        "a record is `{ name: value, ... }`; a call or `with` used as a field " +
          "value takes the rest of the list, so parenthesise it: " +
          "`{ k: (f of a, b), k2: 9 }`",
      );
      const seen = new Set();
      for (const f of fields) {
        const k = f.items[0];
        if (seen.has(k)) {
          throw new PlanesSyntaxError(
            `line ${t.line}: field '${k}' appears twice in this record`,
          );
        }
        seen.add(k);
      }
      return RecordLit(fields);
    }

    if (t.kind === "OP" && t.value === "[") {
      this.next();
      const items = [];
      this.skip_bracket_ws();
      if (!this.at("OP", "]")) {
        items.push(this.parse_expr());
        while (this.accept("OP", ",")) {
          this.skip_bracket_ws();
          if (this.at("OP", "]")) break;
          items.push(this.parse_expr());
        }
      }
      this.skip_bracket_ws();
      this.expect("OP", "]");
      return ListLit(items);
    }

    if (t.kind === "OP" && t.value === "(") {
      this.next();
      const e = this.parse_expr();
      this.expect("OP", ")");
      return e;
    }

    if (t.kind === "NAME") {
      this.next();
      const name = t.value;
      if (this.accept("OF")) {
        const args = [this.parse_unary()];
        while (this.accept("OP", ",")) args.push(this.parse_unary());
        return Call(name, args, t.line);
      }
      if (this.at("OP", "(")) {
        if (!this.paren_is_arglist()) {
          this.check_paren_arglist_ambiguity(name, t);
          return Call(name, [this.parse_additive()], t.line);
        }
        this.next();
        const args = [];
        if (!this.at("OP", ")")) {
          args.push(this.parse_expr());
          while (this.accept("OP", ",")) args.push(this.parse_expr());
        }
        this.expect("OP", ")");
        return Call(name, args, t.line);
      }
      if (this.at("NAME")) {
        const ext_hits = [];
        let probe = name;
        let k = 0;
        while (this.peek(k).kind === "NAME") {
          probe += " " + this.peek(k).value;
          k += 1;
          if (this.knows(probe)) ext_hits.push([k, probe]);
        }
        const bare_hit = this.knows(name);
        if ((bare_hit ? 1 : 0) + ext_hits.length >= 2) {
          this.raise_amber_multiword(t, name, bare_hit, ext_hits);
        }
        if (ext_hits.length) {
          const [j, best] = ext_hits[0];
          for (let x = 0; x < j; x++) this.next();
          if (this.accept("OF")) {
            const args = [this.parse_unary()];
            while (this.accept("OP", ",")) args.push(this.parse_unary());
            return Call(best, args, t.line);
          }
          return Call(best, [], t.line);
        }
      }
      if (this.knows(name)) {
        let takes_arg =
          this.at("STRING") ||
          this.at("NUMBER") ||
          this.at("OP", "(") ||
          this.at("OP", "[");
        if (!takes_arg && this.at("NAME")) {
          takes_arg = this.check_juxtaposition_ambiguity(name, t);
        }
        if (takes_arg) return Call(name, [this.parse_additive()], t.line);
        return Call(name, [], t.line);
      }
      return Var(name);
    }

    throw new PlanesSyntaxError(
      `line ${t.line}: expected a value, found '${t.value || "end of line"}'`,
    );
  }
}

function _param_arity(tokens, j) {
  if (tokens[j].kind !== "NAME") return 0;
  let count = 1;
  j += 1;
  while (
    tokens[j].kind === "OP" &&
    tokens[j].value === "," &&
    tokens[j + 1].kind === "NAME"
  ) {
    count += 1;
    j += 2;
  }
  return count;
}

// Function names and arities, read before the real parse. A multi-word call is
// several NAME tokens; only a name table can say they are one call.
export function prescan_funcs(tokens) {
  const names = new Map();
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.kind === "FOREIGN") {
      let j = i + 1;
      const parts = [];
      while (tokens[j].kind === "NAME") {
        parts.push(tokens[j].value);
        j += 1;
      }
      if (parts.length) {
        const arity = tokens[j].kind === "OF" ? _param_arity(tokens, j + 1) : 0;
        names.set(parts.join(" "), arity);
      }
      continue;
    }
    if (t.kind !== "TO") continue;
    if (i > 0 && !["EOL", "BEGIN", "END"].includes(tokens[i - 1].kind)) continue;
    let j = i + 1;
    const parts = [];
    while (tokens[j].kind === "NAME") {
      parts.push(tokens[j].value);
      j += 1;
    }
    if (parts.length === 0) {
      throw new PlanesSyntaxError(
        `line ${tokens[i + 1].line}: ` +
          `'${tokens[i + 1].value}' is a reserved word and cannot ` +
          `start a function name\n` +
          `  reserved: ${[...keywords()].sort().join(", ")}`,
      );
    }
    if (!["OF", "OP", "EOL", "EOF"].includes(tokens[j].kind)) {
      throw new PlanesSyntaxError(
        `line ${tokens[j].line}: ` +
          `'${tokens[j].value}' is a reserved word and cannot ` +
          `appear in the function name ` +
          `'${parts.join(" ")} ${tokens[j].value}'\n` +
          `  reserved: ${[...keywords()].sort().join(", ")}`,
      );
    }
    const arity = tokens[j].kind === "OF" ? _param_arity(tokens, j + 1) : 0;
    names.set(parts.join(" "), arity);
  }
  return names;
}

// Parse a program. `known` supplies function names defined elsewhere — a
// mapping of name to arity, or an iterable of names (arity null each). This
// file's own definitions win over `known`, which wins over a builtin.
export function parse(src, known = null) {
  const toks = tokenize(src);
  let known_map;
  if (known === null) known_map = new Map();
  else if (known instanceof Map) known_map = known;
  else {
    known_map = new Map();
    for (const name of known) known_map.set(name, null);
  }
  const merged = new Map();
  for (const [k, v] of builtinsArity()) merged.set(k, v);
  for (const [k, v] of known_map) merged.set(k, v);
  for (const [k, v] of prescan_funcs(toks)) merged.set(k, v);
  Parser.knownFuncs = merged;
  return new Parser(toks).parse_program();
}

export function scan_names(src) {
  return prescan_funcs(tokenize(src));
}
