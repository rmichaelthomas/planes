// js/lexer.mjs — the Planes lexer, ported from lexer.py.
//
// Indentation-sensitive; emits EOL, BEGIN, END, EOF. The token classes and
// their order come from grammar/vocabulary.json (the single source of truth),
// combined into one named-group regex exactly as lexer.py does. The patterns in
// vocabulary.json are already valid JavaScript regular expressions, so they are
// used verbatim.
//
// Checked against lexer.py's tokenize() by agreement on every corpus file
// (test_js_lexer.py). lexer.py's output is the specification.

import { vocabulary, GrammarDataError } from "./grammar_data.mjs";
import { resolveStringEscapes, StringEscapeError } from "./planes_text.mjs";

export { GrammarDataError };

// A malformed program — refuse, don't guess. The JS analogue of lexer.py's
// PlanesSyntaxError, which tokenize() raises on an unrecognized escape or a
// trailing backslash that consumes the closing quote.
// `noFix` mirrors lexer.py's `no_fix` (C2): a reason why this raise site names
// no fix clause. Never rendered — the message is byte-identical either way.
export class PlanesSyntaxError extends Error {
  constructor(message, noFix = null) {
    super(message);
    this.name = "PlanesSyntaxError";
    this.noFix = noFix;
  }
}

// One token. Mirrors lexer.py's Token dataclass.
export class Token {
  constructor(kind, value, line) {
    this.kind = kind;
    this.value = value;
    this.line = line;
  }
}

// Compiled lazily, on first tokenize, so this module can be imported before the
// vocabulary is injected (loader_node.mjs under Node, the page under a browser).
let _tokenRe = null;
let _groupNames = null;
let _keywords = null;

function ensureCompiled() {
  if (_tokenRe !== null) return;
  const vocab = vocabulary();
  const specs = vocab.token_classes; // JSON array order is load-bearing
  _groupNames = specs.map((t) => t.name);
  const combined = specs.map((t) => `(?<${t.name}>${t.pattern})`).join("|");
  // The sticky flag anchors each match at lastIndex — the equivalent of
  // lexer.py's TOKEN_RE.match(stripped, pos), which anchors rather than
  // searching, so a position where nothing matches is visible as such.
  _tokenRe = new RegExp(combined, "y");
  _keywords = new Set(vocab.keywords.map((e) => e.word));
}

export function keywords() {
  ensureCompiled();
  return _keywords;
}

// The closed vocabulary of effect kinds, kind -> boundary. lexer.py holds this
// (EFFECT_KINDS) so the parser can validate a rule's kind at parse time. Here it
// is derived lazily from the injected vocabulary.
let _effectKinds = null;
export function effectKinds() {
  if (_effectKinds === null) {
    _effectKinds = new Map(vocabulary().effect_kinds.map((e) => [e.kind, e.boundary]));
  }
  return _effectKinds;
}

// Builtin names, and builtin name -> arity (default 1). parser.py reads these
// from _VOCAB: BUILTIN_NAMES so a bare `count of xs` is a call, and the arity
// for the parse-time name table.
let _builtinNames = null;
export function builtinNames() {
  if (_builtinNames === null) {
    _builtinNames = new Set(vocabulary().builtins.map((b) => b.name));
  }
  return _builtinNames;
}
export function builtinsArity() {
  const m = new Map();
  for (const b of vocabulary().builtins) m.set(b.name, b.arity ?? 1);
  return m;
}

// The token kinds that may name a record field or a with/when-pattern entry —
// grammar/vocabulary.json's field_name_token_kinds.
let _fieldNameKinds = null;
export function fieldNameKinds() {
  if (_fieldNameKinds === null) {
    _fieldNameKinds = new Set(vocabulary().field_name_token_kinds);
  }
  return _fieldNameKinds;
}

// `raw` is a STRING token's content between the delimiting quotes. Resolves the
// four escapes; on an unrecognized escape, raises PlanesSyntaxError with the
// line, exactly as lexer.py's _resolve_string_escapes wraps planes_text's bare
// error with source position.
function resolveWithLine(raw, lineno) {
  try {
    return resolveStringEscapes(raw);
  } catch (e) {
    if (!(e instanceof StringEscapeError)) throw e;
    const nxt = e.badChar;
    throw new PlanesSyntaxError(
      `line ${lineno}: unrecognized escape '\\${nxt}' in a ` +
        `string literal\n` +
        `  the four recognized escapes are ` +
        `\\" \\\\ \\n \\t -- for any other character, write the ` +
        `character itself`,
    );
  }
}

// Tokenize a source string. A faithful port of lexer.py's tokenize().
export function tokenize(src) {
  ensureCompiled();
  const out = [];
  const indents = [0];
  const lines = src.split("\n");
  let lineno = 0;
  for (let li = 0; li < lines.length; li++) {
    lineno = li + 1;
    const raw = lines[li];
    const stripped = raw.trim();
    if (stripped === "" || stripped.startsWith("#")) continue;
    const indent = raw.length - raw.trimStart().length;
    if (indent > indents[indents.length - 1]) {
      indents.push(indent);
      out.push(new Token("BEGIN", "", lineno));
    }
    while (indent < indents[indents.length - 1]) {
      indents.pop();
      out.push(new Token("END", "", lineno));
    }
    let pos = 0;
    const n = stripped.length;
    while (pos < n) {
      _tokenRe.lastIndex = pos;
      const m = _tokenRe.exec(stripped);
      if (m === null) {
        if (stripped[pos] === '"') {
          if (stripped.slice(pos).endsWith('"')) {
            throw new PlanesSyntaxError(
              `line ${lineno}: unterminated string literal -- a ` +
                `backslash right before the closing quote escapes ` +
                `that quote (\\") instead of ending the string\n` +
                `  the four recognized escapes are ` +
                `\\" \\\\ \\n \\t -- write \\\\ for a literal ` +
                `trailing backslash`,
            );
          }
          throw new PlanesSyntaxError(
            `line ${lineno}: unterminated string literal -- no ` +
              `closing quote found before the end of the line\n` +
              `  add the closing quote; a Planes string cannot span ` +
              `multiple lines, so a long one has to be joined with ` +
              `+ across lines`,
          );
        }
        pos += 1;
        continue;
      }
      let kind = null;
      for (const name of _groupNames) {
        if (m.groups[name] !== undefined) {
          kind = name;
          break;
        }
      }
      let val = m[0];
      const end = pos + m[0].length;
      if (kind === "WS" || kind === "COMMENT") {
        pos = end;
        continue;
      }
      if (kind === "NAME" && _keywords.has(val)) {
        kind = val.toUpperCase();
      } else if (kind === "STRING") {
        val = '"' + resolveWithLine(val.slice(1, -1), lineno) + '"';
      }
      out.push(new Token(kind, val, lineno));
      pos = end;
    }
    out.push(new Token("EOL", "", lineno));
  }
  while (indents.length > 1) {
    indents.pop();
    out.push(new Token("END", "", lineno));
  }
  out.push(new Token("EOF", "", lineno + 1));
  return out;
}
