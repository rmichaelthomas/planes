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

// Sub-expressions that need parens wherever they are not the outermost
// expression of their statement.
const COMPOUND = new Set(["BinOp", "Not", "IsNothing"]);

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
      return "[" + node.items.map(renderExpr).join(", ") + "]";
    case "ListPlus":
      return `${renderOperand(node.base)} plus ${renderOperand(node.item)}`;
    case "RecordLit": {
      const fields = node.fields
        .map((f) => {
          const [k, v] = parts(f);
          return `${k}: ${renderExpr(v)}`;
        })
        .join(", ");
      return fields ? "{ " + fields + " }" : "{}";
    }
    case "RecordUpdate": {
      const fields = node.fields
        .map((f) => {
          const [k, v] = parts(f);
          return `${k}: ${renderExpr(v)}`;
        })
        .join(", ");
      return `${renderOperand(node.base)} with ${fields}`;
    }
    case "BinOp":
      if (node.op === "first") {
        return `first ${renderOperand(node.left)} of ${renderOperand(node.right)}`;
      }
      return `${renderOperand(node.left)} ${node.op} ${renderOperand(node.right)}`;
    case "Not":
      return `not ${renderOperand(node.expr)}`;
    case "IsNothing":
      return `${renderOperand(node.expr)} is nothing`;
    case "Field":
      return `${renderOperand(node.obj)}.${node.name}`;
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
    ? ` where ${renderExpr(node.where)}`
    : "";
  const body = renderExpr(node.body[0]);
  return `for each ${node.var} in ${renderExpr(node.source)}${where}: ${body}`;
}

function renderWritetoInline(node) {
  return `write ${renderExpr(node.value)} to ${renderExpr(node.dest)}`;
}

function renderOrfail(node) {
  const inner =
    node.expr.__node === "WriteTo"
      ? renderWritetoInline(node.expr)
      : renderExpr(node.expr);
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
  const lines = [indent + `if ${renderExpr(node.cond)}:`];
  lines.push(renderBlock(node.then, indent + INDENT, markers));
  if (node.els.length) {
    lines.push(indent + "else:");
    lines.push(renderBlock(node.els, indent + INDENT, markers));
  }
  return lines.join("\n");
}

function renderForeachStmt(node, indent, markers) {
  const where = node.where !== null && node.where !== undefined
    ? ` where ${renderExpr(node.where)}`
    : "";
  const header = indent + `for each ${node.var} in ${renderExpr(node.source)}${where}:`;
  const body = renderBlock(node.body, indent + INDENT, markers);
  return header + "\n" + body;
}

function renderWhen(node, indent, markers) {
  const entries = [];
  for (const p of node.pattern) {
    const [fname, inner] = p.items;
    const [kind, arg] = inner.items;
    entries.push(kind === "match" ? `${fname}: ${renderExpr(arg)}` : fname);
  }
  const header = indent + `when ${renderExpr(node.subject)} is { ${entries.join(", ")} }:`;
  const lines = [header, renderBlock(node.body, indent + INDENT, markers)];
  if (node.els.length) {
    lines.push(indent + "else:");
    lines.push(renderBlock(node.els, indent + INDENT, markers));
  }
  return lines.join("\n");
}

export function renderStmt(node, indent, markers) {
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
      return indent + `fail ${renderExpr(node.message)} as ${node.tag}`;
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
