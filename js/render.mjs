// js/render.mjs — the Planes canonical renderer, ported from render.py.
//
// render(parse(src)) must parse to an equal AST for every program in the repo —
// not byte-identical to the original source, but canonical: the same formatting
// decision everywhere, every call rendered `name of (args)`, every compound
// sub-expression parenthesised. Source position is not preserved, so round-trip
// equality is checked with astEqual, which ignores `line`.
//
// A.4: every AST node kind has a real case, no safe fallback — an unhandled kind
// raises, naming it (the two node kinds that were silently unrenderable in
// render.py were caught exactly because there was no fallback to hide them).
// Checked against render.py's output byte for byte across the corpus, with a
// per-node-kind round-trip and cross-implementation round-trips both directions
// (test_js_render.py). render.py is the specification.
//
// Browser-safe (A.7): imports rules.mjs (itself browser-safe) for the marker
// path, and nothing Node-only.

import { escapeStringLiteral } from "./planes_text.mjs";
import { isNode, isTup } from "./nodes.mjs";
import { PlanesNumber } from "./planes_num.mjs";
import { check } from "./rules.mjs";

const INDENT = "  ";

// Sub-expressions that need parens wherever they are read at less than full
// precedence. BinOp/Not/IsNothing were the original set; S6's composition
// generator showed it was incomplete — ListPlus, OrFail, RecordUpdate, and
// ForEach are all low-precedence and are otherwise split, or swallow a following
// token, when embedded. (`first` and `round` render as primaries.)
const COMPOUND = new Set([
  "BinOp", "Not", "IsNothing", "ListPlus", "OrFail", "RecordUpdate", "ForEach",
]);

// Expressions whose own trailing structure swallows a following keyword or `:`
// delimiter: an or-fail's `as tag[:...]`, a record update's `with` fields, a
// for-each's `: body`. Distinct from COMPOUND — a BinOp before `:` (`if x > 0:`)
// does not collide, so these positions must NOT wrap it.
const OPEN_TRAILING = new Set(["OrFail", "RecordUpdate", "ForEach"]);

// An expression read up to a trailing keyword or `:` delimiter — a for-each
// source or where, an if/when subject, a write value or dest, a fail message, an
// or-fail inner (S6). Parenthesise the kinds whose trailing structure would
// otherwise swallow that delimiter.
function delimited(node) {
  return OPEN_TRAILING.has(node.__node) ? `(${renderExpr(node)})` : renderExpr(node);
}

// Expression node kinds that may stand alone as a statement. Listed explicitly
// so renderStmt raises on a node that is neither a known statement nor a
// renderable expression, rather than routing an unknown node through renderExpr.
const EXPR_STMT = new Set([
  "Num", "Str", "Bool", "Nothing", "Var", "ListLit", "RecordLit",
  "RecordUpdate", "ListPlus", "BinOp", "Not", "IsNothing", "Field", "Call",
  "Round", "ForEach", "OrFail",
]);

// A RecordLit/RecordUpdate/Use/Note field Tup — its items.
function parts(t) {
  return isTup(t) ? t.items : t;
}

// ================================================================ comma-list elements
//
// The composition defect (S6): an expression whose rendering ends in a GREEDY
// comma-extensible list is misparsed when placed as an element of an enclosing
// comma-separated list — the element's own commas are read as the enclosing
// list's separators. A call's `of` argument list extends on a following primary;
// a record update's `with` field list extends on a following `name: expr`. The
// parser is correct; the renderer emits text whose meaning differs from the AST.
// The fix is parenthesisation, identical to render.py (its specification).

// The greedy comma-extensible list that terminates renderExpr(node) at top
// level: "of" (a call's argument list), "with" (a record update's field list),
// or null (renders self-delimited). Recursive through the renderings that end in
// a sub-expression — a `for each` body, a BinOp/Not/plus trailing operand,
// unless renderOperand parenthesises that operand (a COMPOUND operand ends ')').
function greedyTail(node) {
  switch (node.__node) {
    case "Call":
      return node.args.length ? "of" : null;
    case "RecordUpdate":
      return "with";
    case "ForEach":
      return greedyTail(node.body[0]);
    case "BinOp":
      return COMPOUND.has(node.right.__node) ? null : greedyTail(node.right);
    case "Not":
      return COMPOUND.has(node.expr.__node) ? null : greedyTail(node.expr);
    case "ListPlus":
      return COMPOUND.has(node.item.__node) ? null : greedyTail(node.item);
    default:
      return null;
  }
}

// Render `node` as an element of a comma-separated list, parenthesising it when
// its greedy tail would be swallowed by the list's own separator. `sep` is
// "record" (siblings are `name: expr`) or "list" (siblings are exprs). A call's
// `of` list swallows either; a record update's `with` list swallows only a
// `name: expr`, so it is dangerous only between record fields.
function commaElement(node, sep) {
  const text = renderExpr(node);
  const tail = greedyTail(node);
  const dangerous = tail === "of" || (tail === "with" && sep === "record");
  return dangerous ? `(${text})` : text;
}

// The base of a `X.name` field access. Like renderOperand — parenthesise a
// COMPOUND base — but ALSO parenthesise a base with a greedy tail (S6):
// `(f of a, b).kind` bare as `f of (a), (b).kind` binds `.kind` to the argument
// `(b)`, not the call. The `.` is the enclosing separator here.
function fieldBase(node) {
  if (COMPOUND.has(node.__node) || greedyTail(node) !== null) {
    return `(${renderExpr(node)})`;
  }
  return renderExpr(node);
}

// ================================================================ expressions

function renderOperand(node) {
  const text = renderExpr(node);
  return COMPOUND.has(node.__node) ? `(${text})` : text;
}

export function renderExpr(node) {
  switch (node.__node) {
    case "Num":
      return node.value && typeof node.value.text === "function"
        ? node.value.text()
        : String(node.value);
    case "Str":
      return `"${escapeStringLiteral(node.value)}"`;
    case "Bool":
      return node.value ? "true" : "false";
    case "Nothing":
      return "nothing";
    case "Var":
      return node.name;
    case "ListLit":
      return "[" + node.items.map((i) => commaElement(i, "list")).join(", ") + "]";
    case "ListPlus":
      return `${renderOperand(node.base)} plus ${renderOperand(node.item)}`;
    case "RecordLit": {
      const fields = node.fields
        .map((f) => {
          const [k, v] = parts(f);
          return `${k}: ${commaElement(v, "record")}`;
        })
        .join(", ");
      return fields ? "{ " + fields + " }" : "{}";
    }
    case "RecordUpdate": {
      const fields = node.fields
        .map((f) => {
          const [k, v] = parts(f);
          return `${k}: ${commaElement(v, "record")}`;
        })
        .join(", ");
      return `${renderOperand(node.base)} with ${fields}`;
    }
    case "BinOp":
      if (node.op === "first") {
        // `first N of L` (S6): both operands parenthesised so each reads as a
        // single closed primary — a bare Var count is otherwise swallowed as
        // `k of parts`, a sub-unary list is otherwise split by precedence.
        return `first (${renderExpr(node.left)}) of (${renderExpr(node.right)})`;
      }
      return `${renderOperand(node.left)} ${node.op} ${renderOperand(node.right)}`;
    case "Not":
      return `not ${renderOperand(node.expr)}`;
    case "IsNothing":
      return `${renderOperand(node.expr)} is nothing`;
    case "Field":
      // `X.name` (S6): a base with a greedy tail needs wrapping — `(call).kind`
      // bare binds `.kind` to the call's last argument, not the call.
      return `${fieldBase(node.obj)}.${node.name}`;
    case "Call":
      return renderCall(node);
    case "Round":
      return `round ${renderOperand(node.value)} to ${renderOperand(node.places)} places`;
    case "ForEach":
      return renderForeachExpr(node);
    case "OrFail":
      return renderOrfail(node);
    case "Builtin":
      // Dead: the parser never builds this node. Named failure, not a silent
      // fall-through, if that ever stops being true.
      throw new Error("renderExpr: Builtin is unreachable by design");
    default:
      throw new Error(`renderExpr: unhandled node type ${node.__node}`);
  }
}

function renderCall(node) {
  if (!node.args.length) return node.name;
  const args = node.args.map((a) => `(${renderExpr(a)})`).join(", ");
  return `${node.name} of ${args}`;
}

function renderForeachExpr(node) {
  const where = node.where !== null && node.where !== undefined
    ? ` where ${delimited(node.where)}`
    : "";
  const body = renderExpr(node.body[0]);
  return `for each ${node.var} in ${delimited(node.source)}${where}: ${body}`;
}

function renderWritetoInline(node) {
  return `write ${delimited(node.value)} to ${delimited(node.dest)}`;
}

function renderOrfail(node) {
  const inner =
    node.expr.__node === "WriteTo"
      ? renderWritetoInline(node.expr)
      : delimited(node.expr);
  return `${inner} or fail as ${node.tag}`;
}

// ================================================================ statements

function renderBecauseSuffix(node) {
  if (node.annotation === null || node.annotation === undefined) return "";
  return ` because "${escapeStringLiteral(node.annotation.text)}"`;
}

function renderAssign(node) {
  const prefix = node.is_let ? "let " : "";
  return `${prefix}${node.name} = ${renderExpr(node.expr)}${renderBecauseSuffix(node)}`;
}

function renderRule(node) {
  const verb = node.assertion === "forbid" ? "may not" : "may";
  let text = `rule [${node.name}] ${node.subject} ${verb} ${node.kind}`;
  if (node.target !== null && node.target !== undefined) {
    text += ` to "${escapeStringLiteral(node.target)}"`;
  }
  if (node.supersedes !== null && node.supersedes !== undefined) {
    text += ` supersedes [${node.supersedes}]`;
    if (node.supersedes_fingerprint !== null && node.supersedes_fingerprint !== undefined) {
      text += ` @${node.supersedes_fingerprint}`;
    }
  }
  return text + renderBecauseSuffix(node);
}

function renderNote(node, indent) {
  const lines = [indent + "note:"];
  for (const e of node.entries) {
    const [kind, value] = parts(e);
    if (kind === "from") {
      lines.push(indent + INDENT + `from "${escapeStringLiteral(value)}"`);
    } else if (kind === "derives-from") {
      lines.push(indent + INDENT + `derives-from [${value}]`);
    }
  }
  return lines.join("\n");
}

function renderUse(node) {
  let text = `use ${node.module}`;
  for (const r of node.renames) {
    const [old, nw] = parts(r);
    text += ` with ${old} as ${nw}`;
  }
  return text;
}

function renderForeign(node) {
  let text = `foreign ${node.name}`;
  if (node.params.length) text += " of " + node.params.join(", ");
  text += ` from "${escapeStringLiteral(node.target)}"`;
  if (node.declared) {
    if (!node.effects.length) {
      text += " doing nothing";
    } else {
      const claims = [];
      for (const eff of node.effects) {
        const [kind, where] = parts(eff);
        if (where === null || where === undefined) {
          claims.push(kind);
        } else if (where.items[0] === "literal") {
          claims.push(`${kind} "${escapeStringLiteral(where.items[1])}"`);
        } else {
          // ("param", name)
          claims.push(`${kind} ${where.items[1]}`);
        }
      }
      text += " doing " + claims.join(", ");
    }
  }
  return text;
}

function renderFuncdef(node, indent, markers) {
  let header = `to ${node.name}`;
  if (node.params.length) header += " of " + node.params.join(", ");
  header += ":";
  const body = renderBlock(node.body, indent + INDENT, markers);
  return indent + header + "\n" + body;
}

function renderIf(node, indent, markers) {
  const lines = [indent + `if ${delimited(node.cond)}:`];
  lines.push(renderBlock(node.then, indent + INDENT, markers));
  if (node.els.length) {
    lines.push(indent + "else:");
    lines.push(renderBlock(node.els, indent + INDENT, markers));
  }
  return lines.join("\n");
}

function renderForeachStmt(node, indent, markers) {
  const where = node.where !== null && node.where !== undefined
    ? ` where ${delimited(node.where)}`
    : "";
  const header = indent + `for each ${node.var} in ${delimited(node.source)}${where}:`;
  const body = renderBlock(node.body, indent + INDENT, markers);
  return header + "\n" + body;
}

function renderWhen(node, indent, markers) {
  // A match value is a record-field position (comma-separated `name: expr`), so
  // it parenthesises a greedy tail the same way a record literal's does (S6).
  const entries = [];
  for (const p of node.pattern) {
    const [fname, inner] = p.items;
    const [kind, arg] = inner.items;
    entries.push(kind === "match" ? `${fname}: ${commaElement(arg, "record")}` : fname);
  }
  const header = indent + `when ${delimited(node.subject)} is { ${entries.join(", ")} }:`;
  const lines = [header, renderBlock(node.body, indent + INDENT, markers)];
  if (node.els.length) {
    lines.push(indent + "else:");
    lines.push(renderBlock(node.els, indent + INDENT, markers));
  }
  return lines.join("\n");
}

// The or-fail-with-handler at this statement's top, or null. A handler is a
// statement-level continuation (`... or fail as tag:` then a block), appearing
// as a bare OrFail statement or wrapped in the Assign/Give whose value it is.
function statementOrfail(node) {
  if (node.__node === "OrFail" && node.handler !== null && node.handler !== undefined) {
    return node;
  }
  if (
    (node.__node === "Assign" || node.__node === "Give") &&
    node.expr.__node === "OrFail" &&
    node.expr.handler !== null &&
    node.expr.handler !== undefined
  ) {
    return node.expr;
  }
  return null;
}

// A copy of `node` with its or-fail handler cleared, so the single-line render
// path produces the head line.
function withoutHandler(node) {
  if (node.__node === "OrFail") return { ...node, handler: null };
  return { ...node, expr: { ...node.expr, handler: null } };
}

export function renderStmt(node, indent, markers) {
  // An or-fail HANDLER block turns an otherwise single-line statement into a
  // block (S6): `x = EXPR or fail as tag:` then the indented handler. Render the
  // head line without the handler, then the block. renderOrfail is single-line
  // and renders no handler; this is where the handler is put back.
  const orfail = statementOrfail(node);
  if (orfail !== null) {
    const head = renderStmt(withoutHandler(node), indent, markers);
    const block = renderBlock(orfail.handler, indent + INDENT, markers);
    return head + ":\n" + block;
  }

  switch (node.__node) {
    case "Use":
      return indent + renderUse(node);
    case "Foreign":
      return indent + renderForeign(node);
    case "Rule":
      return indent + renderRule(node);
    case "Note":
      return renderNote(node, indent);
    case "FuncDef":
      return renderFuncdef(node, indent, markers);
    case "Assign":
      return indent + renderAssign(node);
    case "Give":
      return indent + `give ${renderExpr(node.expr)}`;
    case "Show":
      return indent + `show ${renderExpr(node.expr)}`;
    case "Why":
      return indent + `why ${renderExpr(node.expr)}`;
    case "When":
      return renderWhen(node, indent, markers);
    case "WriteTo":
      return indent + renderWritetoInline(node);
    case "OrFail":
      return indent + renderOrfail(node);
    case "Fail":
      return indent + `fail ${delimited(node.message)} as ${node.tag}`;
    case "If":
      return renderIf(node, indent, markers);
    case "ForEach":
      return renderForeachStmt(node, indent, markers);
    default:
      // A bare expression statement. Every expression node kind is dispatched
      // explicitly by renderExpr; a node that is neither a statement above nor
      // a renderable expression raises here, naming the kind (A.4).
      if (EXPR_STMT.has(node.__node)) return indent + renderExpr(node);
      throw new Error(`renderStmt: unhandled node type ${node.__node}`);
  }
}

// ================================================================ the generated marker

// Every source line this node's subtree touches — the AST-native replacement
// for scanning text. Matches render.py's _line_span: recurses into direct node
// fields and one level into list/tuple elements that are themselves nodes (a
// Tup element, being no node, is not descended — a faithful quirk).
function lineSpan(node, seen) {
  seen = seen ?? new Set();
  if (!isNode(node) || seen.has(node)) return new Set();
  seen.add(node);
  const lines = new Set();
  if (node.line) lines.add(node.line);
  for (const f of Object.keys(node)) {
    if (f === "__node") continue;
    const v = node[f];
    if (isNode(v)) {
      for (const x of lineSpan(v, seen)) lines.add(x);
    } else if (Array.isArray(v)) {
      for (const x of v) {
        if (isNode(x)) for (const y of lineSpan(x, seen)) lines.add(y);
      }
    }
  }
  return lines;
}

export function computeMarkers(rules, surface, declaringFile = null) {
  if (!rules || !rules.length) return new Map();
  if (surface === null || surface === undefined) {
    throw new Error(
      "render(): rules given without surface -- markers need a " +
        "computed effect surface\n" +
        "  try: render(prog, rules=found, surface=analyse(src))",
    );
  }
  const results = check(rules, surface, declaringFile);
  const markers = new Map();
  for (const v of results) {
    if (v.effect === null || v.effect === undefined) continue;
    if (!markers.has(v.effect.site)) markers.set(v.effect.site, []);
    markers.get(v.effect.site).push(v.rule.name);
  }
  return markers;
}

function markerLines(stmt, indent, markers) {
  if (!markers.size) return [];
  const span = lineSpan(stmt);
  const hit = [...span].filter((ln) => markers.has(ln)).sort((a, b) => a - b);
  const names = [];
  const seen = new Set();
  for (const ln of hit) {
    for (const name of markers.get(ln)) {
      if (!seen.has(name)) {
        seen.add(name);
        names.push(name);
      }
    }
  }
  return names.map((name) => indent + `~ [${name}] applies here`);
}

function renderBlock(stmts, indent, markers) {
  const out = [];
  for (const s of stmts) {
    out.push(...markerLines(s, indent, markers));
    out.push(renderStmt(s, indent, markers));
  }
  return out.join("\n");
}

// ================================================================ entry points

export function render(prog, rules = null, surface = null) {
  const markers = computeMarkers(rules, surface);
  const body = renderBlock(prog, "", markers);
  return body ? body + "\n" : "";
}

export function stripAnnotations(prog) {
  const stripStmts = (stmts) =>
    stmts.filter((s) => s.__node !== "Note").map(stripOne);
  const stripOne = (s) => {
    if (s.__node === "Assign" && s.annotation !== null && s.annotation !== undefined) {
      return { ...s, annotation: null };
    }
    if (s.__node === "Rule" && s.annotation !== null && s.annotation !== undefined) {
      return { ...s, annotation: null };
    }
    if (s.__node === "If") {
      return { ...s, then: stripStmts(s.then), els: stripStmts(s.els) };
    }
    if (s.__node === "ForEach") return { ...s, body: stripStmts(s.body) };
    if (s.__node === "FuncDef") return { ...s, body: stripStmts(s.body) };
    return s;
  };
  return stripStmts(prog);
}

// Structural equality that ignores `line` — source position, not meaning. The
// canonical renderer legitimately moves line numbers, so round-trip equality
// checks structure, not accidental line agreement.
export function astEqual(a, b) {
  if (isNode(a) || isNode(b)) {
    if (!isNode(a) || !isNode(b) || a.__node !== b.__node) return false;
    for (const f of Object.keys(a)) {
      if (f === "line" || f === "__node") continue;
      if (!(f in b)) return false;
      if (!astEqual(a[f], b[f])) return false;
    }
    for (const f of Object.keys(b)) {
      if (f === "line" || f === "__node") continue;
      if (!(f in a)) return false;
    }
    return true;
  }
  if (isTup(a) || isTup(b)) {
    if (!isTup(a) || !isTup(b)) return false;
    return astEqual(a.items, b.items);
  }
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    return a.every((x, i) => astEqual(x, b[i]));
  }
  if (a instanceof PlanesNumber || b instanceof PlanesNumber) {
    return a instanceof PlanesNumber && b instanceof PlanesNumber && a.eq(b);
  }
  return a === b;
}
