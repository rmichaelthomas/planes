// js/canonical.mjs — the canonical AST text form, for agreement.
//
// A faithful port of test_parser_in_planes.py's canonical(): one node per line,
// two-space indentation for depth, the node type then its fields in declaration
// order, leaf values quoted and escaped so quotes and newlines survive. Both the
// JS parser and parser.py emit this same text and the test compares strings
// (A.3, reuse the existing form — do not invent a fourth). A divergence in this
// form is a divergence in the test, not the implementation, so it mirrors the
// Python renderer exactly, tuple shapes and all.

import { isNode, isTup } from "./nodes.mjs";
import { escapeStringLiteral } from "./planes_text.mjs";
import { PlanesNumber } from "./planes_num.mjs";

function renderScalar(v) {
  if (v === null || v === undefined) return "nothing";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "string") return `"${escapeStringLiteral(v)}"`;
  if (v instanceof PlanesNumber) return v.text(); // str(Number) is its text form
  return String(v);
}

function renderListItem(item, indent, out) {
  if (isNode(item)) {
    out.push(`${indent}-`);
    renderNode(item, indent + "  ", out);
    return;
  }
  if (isTup(item) && item.items.length === 2 && isNode(item.items[1])) {
    const [key, val] = item.items;
    out.push(`${indent}- "${escapeStringLiteral(String(key))}":`);
    renderNode(val, indent + "  ", out);
    return;
  }
  if (
    isTup(item) &&
    item.items.length === 2 &&
    isTup(item.items[1]) &&
    item.items[1].items.length === 2
  ) {
    const [key, inner] = item.items;
    const [tag, payload] = inner.items;
    const head = `${indent}- "${escapeStringLiteral(String(key))}" ${tag}:`;
    if (isNode(payload)) {
      out.push(head);
      renderNode(payload, indent + "  ", out);
    } else {
      out.push(`${head} ${renderScalar(payload)}`);
    }
    return;
  }
  if (isTup(item) && item.items.length === 2) {
    const [key, val] = item.items;
    out.push(`${indent}- (${renderScalar(key)}, ${renderScalar(val)})`);
    return;
  }
  out.push(`${indent}- ${renderScalar(item)}`);
}

function renderValue(name, v, indent, out) {
  if (
    v === null ||
    v === undefined ||
    typeof v === "boolean" ||
    typeof v === "string" ||
    (!Array.isArray(v) && !isNode(v) && !isTup(v))
  ) {
    out.push(`${indent}${name}: ${renderScalar(v)}`);
    return;
  }
  if (isNode(v)) {
    out.push(`${indent}${name}:`);
    renderNode(v, indent + "  ", out);
    return;
  }
  if (Array.isArray(v) || isTup(v)) {
    const arr = isTup(v) ? v.items : v;
    out.push(`${indent}${name}: [${arr.length}]`);
    for (const item of arr) renderListItem(item, indent + "  ", out);
    return;
  }
  out.push(`${indent}${name}: ${renderScalar(v)}`);
}

function renderNode(node, indent, out) {
  out.push(`${indent}${node.__node}`);
  for (const f of Object.keys(node)) {
    if (f === "__node") continue;
    renderValue(f, node[f], indent + "  ", out);
  }
}

// The canonical text form of one AST node.
export function canonical(node) {
  const out = [];
  renderNode(node, "", out);
  return out.join("\n");
}

// The canonical text form of a whole program: canonical() per top-level
// statement, joined — matches test_parser_in_planes.py's canonical_program.
export function canonicalProgram(stmts) {
  const out = [];
  for (const s of stmts) renderNode(s, "", out);
  return out.join("\n");
}
