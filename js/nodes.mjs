// js/nodes.mjs — the AST node constructors.
//
// The JavaScript counterpart of the AST dataclasses at the bottom of lexer.py
// (defined there, historically, so parser.py could `from lexer import *`). Each
// node is a plain object tagged with __node = its type name, with its fields in
// the SAME declaration order as the Python dataclass — the canonical AST form
// (canonical.mjs) walks the fields in insertion order, and the interpreter
// (Phase 5) switches on __node. Field names are the Python names verbatim
// (is_let, is_expr, supersedes_fingerprint, ...) because the canonical form
// prints them.
//
// A Python tuple becomes a Tup; a Python list becomes a JS array. The
// distinction only matters at the item level of a sequence field: RecordLit
// .fields holds (name, expr) pairs (Tups), while ListLit.items holds nodes.

// A Python tuple — an ordered pair (or triple) that is NOT a list. Used for the
// (key, value) and (kind, (tag, target)) shapes the canonical form renders
// specially.
export class Tup {
  constructor(...items) {
    this.items = items;
  }
}
export function tup(...items) {
  return new Tup(...items);
}
export function isTup(v) {
  return v instanceof Tup;
}
export function isNode(v) {
  return v !== null && typeof v === "object" && "__node" in v;
}

export const Num = (value) => ({ __node: "Num", value });
export const Str = (value) => ({ __node: "Str", value });
export const Bool = (value) => ({ __node: "Bool", value });
export const Nothing = () => ({ __node: "Nothing" });
export const Var = (name) => ({ __node: "Var", name });
export const ListLit = (items) => ({ __node: "ListLit", items });
export const RecordLit = (fields) => ({ __node: "RecordLit", fields });
export const RecordUpdate = (base, fields) => ({
  __node: "RecordUpdate",
  base,
  fields,
});
export const ListPlus = (base, item) => ({ __node: "ListPlus", base, item });
export const BinOp = (op, left, right) => ({ __node: "BinOp", op, left, right });
export const Not = (expr) => ({ __node: "Not", expr });
export const IsNothing = (expr) => ({ __node: "IsNothing", expr });
export const Field = (obj, name) => ({ __node: "Field", obj, name });
export const Assign = (name, expr, is_let = false, annotation = null) => ({
  __node: "Assign",
  name,
  expr,
  is_let,
  annotation,
});
export const Why = (expr) => ({ __node: "Why", expr });
export const Use = (module, renames = []) => ({ __node: "Use", module, renames });
export const FuncDef = (name, params, body) => ({
  __node: "FuncDef",
  name,
  params,
  body,
});
export const Call = (name, args, line = 0) => ({
  __node: "Call",
  name,
  args,
  line,
});
export const Give = (expr) => ({ __node: "Give", expr });
export const Show = (expr, line = 0) => ({ __node: "Show", expr, line });
export const ForEach = (v, source, where, body, is_expr = false) => ({
  __node: "ForEach",
  var: v,
  source,
  where,
  body,
  is_expr,
});
export const If = (cond, then, els) => ({ __node: "If", cond, then, els });
export const When = (subject, pattern, body, els) => ({
  __node: "When",
  subject,
  pattern,
  body,
  els,
});
export const OrFail = (expr, tag, handler = null) => ({
  __node: "OrFail",
  expr,
  tag,
  handler,
});
export const Fail = (message, tag, line = 0) => ({
  __node: "Fail",
  message,
  tag,
  line,
});
export const Builtin = (name, arg) => ({ __node: "Builtin", name, arg });
export const Foreign = (
  name,
  params,
  target,
  effects = [],
  declared = false,
  line = 0,
) => ({ __node: "Foreign", name, params, target, effects, declared, line });
export const WriteTo = (value, dest, line = 0) => ({
  __node: "WriteTo",
  value,
  dest,
  line,
});
export const Round = (value, places) => ({ __node: "Round", value, places });
export const Rule = (
  name,
  subject,
  kind,
  target = null,
  line = 0,
  supersedes = null,
  assertion = "forbid",
  supersedes_fingerprint = null,
  annotation = null,
) => ({
  __node: "Rule",
  name,
  subject,
  kind,
  target,
  line,
  supersedes,
  assertion,
  supersedes_fingerprint,
  annotation,
});
export const Because = (text, line = 0) => ({ __node: "Because", text, line });
export const Note = (entries, line = 0) => ({ __node: "Note", entries, line });
