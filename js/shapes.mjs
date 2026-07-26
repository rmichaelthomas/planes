// js/shapes.mjs — the Planes static effect analyser, ported from shapes.py.
//
// Computes a program's total effect surface without running it. The runtime
// effect log in interp.mjs records what a program *did* on one run; this
// computes what a program *can do* on any run, and every runtime effect must
// appear in the static surface — that is the oracle. The hard part is not
// finding `ask` in the AST: a function's effects include the effects of
// everything it calls, transitively, and calls can be mutually recursive, so
// this is a fixed point over the call graph, not a tree walk.
//
// Checked against shapes.py by canonical-form agreement (test_js_shapes.py):
// the published surface form (shapes_cli.as_json), the per-function breakdown,
// and the derivation graph. shapes.py is the specification. The port introduces
// no type information (A.1 ruling 3) and reproduces shapes.py's widening
// exactly — a more precise JS analyser would be a divergence, not an
// improvement (A.1 ruling 2).
//
// Browser-safe (A.7): imports only the browser-loadable modules. Following
// imports across files needs the filesystem, so `analyseFile` lives in the
// Node-only shapes_node.mjs; this module holds `analyse(src)`, which is what the
// browser effect-surface view calls.

import { effectKinds, builtinNames } from "./lexer.mjs";
import { parse } from "./parser.mjs";
import { escapeStringLiteral } from "./planes_text.mjs";
import { PlanesNumber } from "./planes_num.mjs";
import { isTup } from "./nodes.mjs";

// ================================================================ effect kinds

// The closed vocabulary of boundaries, grouped as shapes.py groups them.
export const BOUNDARIES = ["network", "file", "console", "ambient", "foreign"];

// A value the analyser cannot pin down statically. A single sentinel, compared
// by identity (=== UNKNOWN), the analogue of shapes.py's Unknown singleton.
export const UNKNOWN = Object.freeze({ __unknown: true });

// ---- Python str()/repr() analogues, so a fully-known list/record target reads
// exactly as shapes.py's as_text(str(v)) would. No such target occurs in the
// corpus, but the analyser stays total on any input and must not diverge if one
// ever does.
function pyRepr(v) {
  if (v === null || v === undefined) return "None";
  if (typeof v === "boolean") return v ? "True" : "False";
  if (v instanceof PlanesNumber) return v.text();
  if (typeof v === "string") {
    const q = v.includes("'") && !v.includes('"') ? '"' : "'";
    let body = "";
    for (const c of v) {
      if (c === "\\") body += "\\\\";
      else if (c === q) body += "\\" + q;
      else if (c === "\n") body += "\\n";
      else if (c === "\t") body += "\\t";
      else if (c === "\r") body += "\\r";
      else body += c;
    }
    return q + body + q;
  }
  return pyStr(v);
}
function pyStr(v) {
  if (v === null || v === undefined) return "None";
  if (typeof v === "boolean") return v ? "True" : "False";
  if (v instanceof PlanesNumber) return v.text();
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return "[" + v.map(pyRepr).join(", ") + "]";
  if (v instanceof Map) {
    return (
      "{" +
      [...v.entries()].map(([k, val]) => `${pyRepr(k)}: ${pyRepr(val)}`).join(", ") +
      "}"
    );
  }
  return String(v);
}

// Compare two strings by Unicode code point, the way Python's < does (JS's <
// compares UTF-16 code units, which differs for astral characters).
function pyStrCmp(a, b) {
  if (a === b) return 0;
  const ca = [...a];
  const cb = [...b];
  const n = Math.min(ca.length, cb.length);
  for (let i = 0; i < n; i++) {
    const x = ca[i].codePointAt(0);
    const y = cb[i].codePointAt(0);
    if (x !== y) return x < y ? -1 : 1;
  }
  return ca.length < cb.length ? -1 : ca.length > cb.length ? 1 : 0;
}

// The sort shapes.py applies everywhere: (boundary, kind, target).
function effCmp(a, b) {
  return (
    pyStrCmp(a.boundary, b.boundary) ||
    pyStrCmp(a.kind, b.kind) ||
    pyStrCmp(a.target, b.target)
  );
}

// One node in the static derivation graph. Mirrors interp.mjs's Deriv shape and
// shapes.py's StaticDeriv: same field names, same meanings.
export class StaticDeriv {
  constructor(kind, label, inputs = [], origin = null, file = null) {
    this.kind = kind;
    this.label = label;
    this.inputs = inputs;
    this.origin = origin;
    this.file = file;
  }
}

// One thing a program can do at a boundary. `derivation` is excluded from the
// value identity (key()), exactly as shapes.py excludes it from hash/equality:
// two structurally identical effects reached by different paths must remain one
// effect, or the fixed point may not terminate.
export class Effect {
  constructor(
    kind,
    boundary,
    target,
    computed = false,
    { site = 0, claimed = false, derivation = null } = {},
  ) {
    this.kind = kind;
    this.boundary = boundary;
    this.target = target;
    this.computed = computed;
    this.site = site;
    this.claimed = claimed;
    this.derivation = derivation;
  }

  // The value identity — every compared field, derivation excluded.
  key() {
    return [
      this.kind,
      this.boundary,
      this.target,
      this.computed ? "T" : "F",
      String(this.site),
      this.claimed ? "T" : "F",
    ].join("\x00");
  }

  toString() {
    if (this.kind === "unknown") {
      return `unknown — ${this.target} declares no effects`;
    }
    let t = this.target;
    if (this.computed && !t.endsWith(")")) t += " (computed)";
    if (this.claimed) t += " (declared, not verified)";
    return `${this.kind} ${t}`;
  }
}

// A value-identity set of Effects: first-wins on collision (keeping the earlier
// derivation, as Python set union does), insertion-ordered. Ordering never
// reaches output — every surface field is sorted — but first-wins does, because
// it decides which derivation an effect carries.
class EffectSet {
  constructor(iter = null) {
    this.map = new Map(); // key -> Effect
    if (iter) this.union(iter);
  }
  add(e) {
    const k = e.key();
    if (!this.map.has(k)) this.map.set(k, e);
  }
  union(iter) {
    const items = iter instanceof EffectSet ? iter.map.values() : iter;
    for (const e of items) this.add(e);
    return this;
  }
  copy() {
    const s = new EffectSet();
    for (const [k, e] of this.map) s.map.set(k, e);
    return s;
  }
  subsetOf(other) {
    for (const k of this.map.keys()) if (!other.map.has(k)) return false;
    return true;
  }
  get size() {
    return this.map.size;
  }
  list() {
    return [...this.map.values()];
  }
  sorted() {
    return this.list().sort(effCmp);
  }
  [Symbol.iterator]() {
    return this.map.values();
  }
}

// ================================================================ the surface

export class Surface {
  constructor({
    effects = [],
    functions = new Map(),
    modules = new Set(),
    unresolved = [],
    foreign = [],
  } = {}) {
    this.effects = effects; // what running this file performs
    this.functions = functions; // Map name -> sorted Effect[]
    this.modules = modules;
    this.unresolved = unresolved;
    this.foreign = foreign;
  }

  // Every effect any function here can perform, plus top-level ones. Includes
  // foreign declarations even when nothing calls them.
  get declared() {
    const out = [...this.effects];
    for (const es of this.functions.values()) out.push(...es);
    const resolved = new Set();
    for (const e of out) if (!e.computed) resolved.add(e.kind + "\x00" + e.boundary);
    for (const e of this.foreign) {
      if (e.computed && resolved.has(e.kind + "\x00" + e.boundary)) continue;
      out.push(e);
    }
    const seen = new Set();
    const uniq = [];
    for (const e of out) {
      const k = e.kind + "\x00" + e.target + "\x00" + (e.computed ? "T" : "F");
      if (!seen.has(k)) {
        seen.add(k);
        uniq.push(e);
      }
    }
    return uniq.sort(effCmp);
  }

  isLibrary() {
    const anyFn = [...this.functions.values()].some((es) => es.length > 0);
    return this.effects.length === 0 && (anyFn || this.foreign.length > 0);
  }

  kinds() {
    return [...new Set(this.declared.map((e) => e.kind))].sort(pyStrCmp);
  }
  boundaries() {
    return [...new Set(this.declared.map((e) => e.boundary))].sort(pyStrCmp);
  }
  touches(boundary) {
    return this.declared.some((e) => e.boundary === boundary);
  }
  at(boundary) {
    return this.declared.filter((e) => e.boundary === boundary);
  }
  isPure() {
    return this.declared.length === 0;
  }
  hasUnknowns() {
    return this.declared.some((e) => e.kind === "unknown");
  }
  claimsList() {
    return this.declared.filter((e) => e.claimed);
  }
  targets(kind = null) {
    return [
      ...new Set(
        this.declared
          .filter((e) => kind === null || e.kind === kind)
          .map((e) => e.target),
      ),
    ].sort(pyStrCmp);
  }
  derivationOf(effect) {
    return effect.derivation;
  }

  // Every name and file this effect's target provably derives from — the static
  // analogue of interp.origins(). Walks the derivation graph; not deduplicated,
  // matching shapes.py (callers that want a set dedupe).
  originsOf(effect) {
    const node = effect.derivation;
    if (node === null || node === undefined) return [];
    const found = [];
    const seen = new Set();
    const walk = (n) => {
      if (seen.has(n)) return;
      seen.add(n);
      if (n.kind === "name" || n.kind === "param") found.push([n.label, n.file]);
      for (const i of n.inputs) walk(i);
    };
    walk(node);
    return found;
  }

  declaredButUnused() {
    const kinds = effectKinds();
    const needed = new Set();
    for (const e of this.declared) {
      if (kinds.has(e.kind)) needed.add(kinds.get(e.kind));
    }
    const mods = new Set();
    for (const b of needed) mods.add(b === "network" ? "http" : b);
    return [...this.modules].filter((m) => !mods.has(m)).sort(pyStrCmp);
  }

  usedButUndeclared() {
    const missing = [];
    for (const e of this.declared) {
      const mod = e.boundary === "network" ? "http" : e.boundary;
      if ((e.boundary === "network" || e.boundary === "file") && !this.modules.has(mod)) {
        missing.push(e);
      }
    }
    return missing;
  }

  render() {
    const lines = [];
    if (this.isPure()) return "pure — this program touches nothing outside itself";
    if (this.isLibrary()) {
      lines.push(
        "(library — nothing runs at load; these are what its functions can do)",
      );
    }
    for (const b of BOUNDARIES) {
      const at = this.at(b);
      if (!at.length) continue;
      lines.push(`${b}:`);
      const seen = new Set();
      for (const e of at) {
        const key = e.kind + "\x00" + e.target + "\x00" + (e.computed ? "T" : "F");
        if (seen.has(key)) continue;
        seen.add(key);
        lines.push(`  ${e}`);
      }
    }
    if (this.unresolved.length) {
      const uniq = [...new Set(this.unresolved)].sort(pyStrCmp);
      lines.push(`unresolved calls: ${uniq.join(", ")}`);
    }
    if (this.hasUnknowns()) {
      lines.push(
        "this surface is incomplete: a foreign function states no effects",
      );
    }
    return lines.join("\n");
  }
}

// ================================================================ constants

// Statically known values, scoped like the runtime environment. Stores a
// [value, StaticDeriv] pair per name. Widening to UNKNOWN is always sound.
class Consts {
  constructor(parent = null) {
    this.vals = new Map();
    this.parent = parent;
  }
  get(name) {
    if (this.vals.has(name)) return this.vals.get(name);
    if (this.parent !== null) return this.parent.get(name);
    return [UNKNOWN, new StaticDeriv("unknown", name)];
  }
  set(name, value, node) {
    this.vals.set(name, [value, node]);
  }
  child() {
    return new Consts(this);
  }
}

// ---- small AST helpers, so the walk reads like shapes.py's isinstance chain.
function is(node, kind) {
  return node !== null && node !== undefined && node.__node === kind;
}
// Unpack a RecordLit/RecordUpdate field Tup(key, valueNode).
function fieldParts(f) {
  return isTup(f) ? f.items : f;
}

// ================================================================ analyser

export class Analyser {
  constructor() {
    this.funcs = new Map(); // name -> FuncDef, declaration order
    this.modules = new Set();
    this.unresolved = [];
    this.depth = 0;
    this._recCache = new Map();
    this.local = new Map(); // original name -> exported name, for renames
    this.foreigns = new Map(); // name -> Foreign
    this.funcFile = new Map();
    this.foreignFile = new Map();
    this.entryFile = null;
    this.currentFile = null;
  }

  analyse(src) {
    const prog = parse(src);
    this.collectDeclarations(prog, null, this.entryFile);
    return this.analyseProg(prog);
  }

  analyseProg(prog) {
    // Fixed point over the call graph. A function's effect set grows until it
    // stops; recursion terminates because sets only grow and the vocabulary is
    // finite. Parameters are UNKNOWN here — the generic surface, true for any
    // call site.
    const fnEffects = new Map();
    for (const name of this.funcs.keys()) fnEffects.set(name, new EffectSet());
    let changed = true;
    let rounds = 0;
    while (changed) {
      changed = false;
      rounds += 1;
      if (rounds > 200) break;
      for (const [name, fn] of this.funcs) {
        const inner = new Consts();
        this.currentFile = this.funcFile.get(name) ?? this.entryFile;
        for (const p of fn.params) {
          inner.set(p, UNKNOWN, new StaticDeriv("param", p, [], null, this.currentFile));
        }
        const found = new EffectSet();
        for (const stmt of fn.body) found.union(this.walk(stmt, fnEffects, inner));
        const cur = fnEffects.get(name);
        if (!found.subsetOf(cur)) {
          cur.union(found);
          changed = true;
        }
      }
    }

    // Top-level statements, now that function effects are known.
    const top = new EffectSet();
    const topConsts = new Consts();
    this.currentFile = this.entryFile;
    for (const stmt of prog) {
      if (is(stmt, "FuncDef")) continue;
      top.union(this.walk(stmt, fnEffects, topConsts));
    }

    const functions = new Map();
    for (const [n, s] of fnEffects) functions.set(n, s.sorted());

    const foreignSet = new EffectSet();
    for (const d of this.foreigns.values()) {
      foreignSet.union(this.foreignEffects(d));
    }

    return new Surface({
      effects: top.sorted(),
      functions,
      modules: new Set(this.modules),
      unresolved: [...this.unresolved],
      foreign: foreignSet.sorted(),
    });
  }

  collectDeclarations(prog, renames = null, file = null) {
    renames = renames ?? new Map();
    const ren = renames instanceof Map ? renames : new Map(Object.entries(renames));
    const scan = (node) => {
      if (is(node, "Foreign")) {
        const name = ren.get(node.name) ?? node.name;
        this.foreigns.set(name, node);
        this.foreignFile.set(name, file);
        if (ren.has(node.name)) this.local.set(node.name, ren.get(node.name));
        return;
      }
      if (is(node, "FuncDef")) {
        const exported = ren.get(node.name) ?? node.name;
        this.funcs.set(exported, node);
        this.funcFile.set(exported, file);
        if (exported !== node.name) this.local.set(node.name, exported);
        for (const s of node.body) scan(s);
      } else if (is(node, "Use")) {
        this.modules.add(node.module);
      } else if (is(node, "If")) {
        for (const s of node.then.concat(node.els)) scan(s);
      } else if (is(node, "ForEach")) {
        for (const s of node.body) scan(s);
      }
    };
    for (const stmt of prog) scan(stmt);
  }

  // ---- the walk. Returns an EffectSet; never executes anything.
  walk(node, fnEffects, consts) {
    if (node === null || node === undefined) return new EffectSet();
    const out = new EffectSet();
    const K = effectKinds();

    if (is(node, "Builtin")) {
      out.union(this.walk(node.arg, fnEffects, consts));
      if (node.name === "ask" || node.name === "read") {
        const [target, computed, deriv] = this.describe(node.arg, consts);
        out.add(new Effect(node.name, K.get(node.name), target, computed, { derivation: deriv }));
      }
      return out;
    }

    if (is(node, "WriteTo")) {
      out.union(this.walk(node.value, fnEffects, consts));
      out.union(this.walk(node.dest, fnEffects, consts));
      const [target, computed, deriv] = this.describe(node.dest, consts);
      out.add(new Effect("write", "file", target, computed, { site: node.line, derivation: deriv }));
      return out;
    }

    if (is(node, "Show")) {
      out.union(this.walk(node.expr, fnEffects, consts));
      const [target, computed, deriv] = this.describe(node.expr, consts);
      out.add(new Effect("show", "console", target, computed, { site: node.line, derivation: deriv }));
      return out;
    }

    if (is(node, "Call")) {
      for (const a of node.args) out.union(this.walk(a, fnEffects, consts));
      if (K.has(node.name) && !this.funcs.has(node.name)) {
        const arg = node.args.length ? node.args[0] : null;
        const [target, computed, deriv] = this.describe(arg, consts);
        out.add(new Effect(node.name, K.get(node.name), target, computed, { site: node.line, derivation: deriv }));
        return out;
      }
      const target = this.local.get(node.name) ?? node.name;
      if (this.foreigns.has(target)) {
        out.union(this.foreignEffects(this.foreigns.get(target), node.args, consts));
        return out;
      }
      if (fnEffects.has(target)) {
        out.union(this.specialise({ name: target, args: node.args }, fnEffects, consts));
      } else if (!this.funcs.has(target) && !builtinNames().has(target)) {
        this.unresolved.push(node.name);
      }
      return out;
    }

    if (is(node, "Var")) {
      if (fnEffects.has(node.name)) return fnEffects.get(node.name).copy();
      return new EffectSet();
    }

    if (is(node, "Assign")) {
      out.union(this.walk(node.expr, fnEffects, consts));
      const [value, n] = this.const_(node.expr, consts);
      consts.set(node.name, value, n);
      return out;
    }

    if (is(node, "Give") || is(node, "Why")) {
      return this.walk(node.expr, fnEffects, consts);
    }

    if (is(node, "Fail")) {
      return this.walk(node.message, fnEffects, consts);
    }

    if (is(node, "BinOp")) {
      return this.walk(node.left, fnEffects, consts).union(
        this.walk(node.right, fnEffects, consts),
      );
    }

    if (is(node, "Not")) return this.walk(node.expr, fnEffects, consts);

    if (is(node, "Round")) {
      return this.walk(node.value, fnEffects, consts).union(
        this.walk(node.places, fnEffects, consts),
      );
    }

    if (is(node, "Field")) return this.walk(node.obj, fnEffects, consts);

    if (is(node, "ListLit")) {
      for (const i of node.items) out.union(this.walk(i, fnEffects, consts));
      return out;
    }

    if (is(node, "RecordLit")) {
      for (const f of node.fields) {
        const [, v] = fieldParts(f);
        out.union(this.walk(v, fnEffects, consts));
      }
      return out;
    }

    if (is(node, "RecordUpdate")) {
      out.union(this.walk(node.base, fnEffects, consts));
      for (const f of node.fields) {
        const [, v] = fieldParts(f);
        out.union(this.walk(v, fnEffects, consts));
      }
      return out;
    }

    if (is(node, "ListPlus")) {
      return this.walk(node.base, fnEffects, consts).union(
        this.walk(node.item, fnEffects, consts),
      );
    }

    if (is(node, "When")) {
      out.union(this.walk(node.subject, fnEffects, consts));
      for (const p of node.pattern) {
        const [, inner] = p.items;
        const [kind, arg] = inner.items;
        if (kind === "match") out.union(this.walk(arg, fnEffects, consts));
      }
      const inner = consts.child();
      for (const p of node.pattern) {
        const [field, innerT] = p.items;
        const [kind] = innerT.items;
        if (kind === "bind") {
          inner.set(field, UNKNOWN, new StaticDeriv("unknown", field, [], null, this.currentFile));
        }
      }
      for (const s of node.body.concat(node.els)) out.union(this.walk(s, fnEffects, inner));
      for (const name of this.assignedIn(node.body.concat(node.els))) {
        consts.set(name, UNKNOWN, new StaticDeriv("unknown", name, [], null, this.currentFile));
      }
      return out;
    }

    if (is(node, "OrFail")) {
      out.union(this.walk(node.expr, fnEffects, consts));
      if (node.handler !== null && node.handler !== undefined) {
        const inner = consts.child();
        inner.set(node.tag, UNKNOWN, new StaticDeriv("unknown", node.tag, [], null, this.currentFile));
        for (const s of node.handler) out.union(this.walk(s, fnEffects, inner));
        for (const name of this.assignedIn(node.handler)) {
          consts.set(name, UNKNOWN, new StaticDeriv("unknown", name, [], null, this.currentFile));
        }
      }
      return out;
    }

    if (is(node, "ForEach")) {
      out.union(this.walk(node.source, fnEffects, consts));
      const inner = consts.child();
      inner.set(node.var, UNKNOWN, new StaticDeriv("unknown", node.var, [], null, this.currentFile));
      out.union(this.walk(node.where, fnEffects, inner));
      for (const s of node.body) out.union(this.walk(s, fnEffects, inner));
      for (const name of this.assignedIn(node.body)) {
        consts.set(name, UNKNOWN, new StaticDeriv("unknown", name, [], null, this.currentFile));
      }
      return out;
    }

    if (is(node, "If")) {
      out.union(this.walk(node.cond, fnEffects, consts));
      for (const s of node.then.concat(node.els)) out.union(this.walk(s, fnEffects, consts.child()));
      for (const name of this.assignedIn(node.then.concat(node.els))) {
        consts.set(name, UNKNOWN, new StaticDeriv("unknown", name, [], null, this.currentFile));
      }
      return out;
    }

    if (is(node, "FuncDef")) return new EffectSet();

    return new EffectSet();
  }

  foreignEffects(decl, args = null, consts = null) {
    if (!decl.declared) {
      return new EffectSet([
        new Effect("unknown", "foreign", decl.target, true, {
          site: decl.line,
          claimed: true,
          derivation: new StaticDeriv("foreign", decl.target, [], null, this.currentFile),
        }),
      ]);
    }
    const out = new EffectSet();
    const K = effectKinds();
    for (const eff of decl.effects) {
      const [kind, where] = eff.items;
      const boundary = K.get(kind) ?? "foreign";
      const [target, computed, deriv] = this.claimTarget(decl, where, args, consts);
      out.add(new Effect(kind, boundary, target, computed, { site: decl.line, claimed: true, derivation: deriv }));
    }
    return out;
  }

  claimTarget(decl, where, args, consts) {
    if (where === null || where === undefined) {
      return [
        `${decl.target} (destination not stated)`,
        true,
        new StaticDeriv("foreign", decl.target, [], `foreign:${decl.target}`, this.currentFile),
      ];
    }
    const [kind, value] = where.items;
    if (kind === "literal") {
      return [
        value,
        false,
        new StaticDeriv("literal", `"${escapeStringLiteral(value)}"`, [], null, this.currentFile),
      ];
    }
    // A parameter. Resolve it from the call site if there is one.
    if (args !== null && consts !== null) {
      const i = decl.params.indexOf(value);
      if (i >= 0 && i < args.length) {
        const [v, n] = this.const_(args[i], consts);
        if (v !== UNKNOWN) {
          return [
            this.asText(v),
            false,
            new StaticDeriv("foreign", decl.target, [n], `foreign:${decl.target}`, this.currentFile),
          ];
        }
        const [text, n2] = this.pattern(args[i], consts);
        return [
          text,
          true,
          new StaticDeriv("foreign", decl.target, [n2], `foreign:${decl.target}`, this.currentFile),
        ];
      }
    }
    return [
      "{...}",
      true,
      new StaticDeriv("foreign", decl.target, [], `foreign:${decl.target}`, this.currentFile),
    ];
  }

  specialise(node, fnEffects, consts) {
    const generic = fnEffects.get(node.name).copy();
    const fn = this.funcs.get(node.name);
    if (fn === undefined || this.depth > 4) return generic;
    if (this.isRecursive(node.name)) return generic;
    const argPairs = node.args.map((a) => this.const_(a, consts));
    const args = argPairs.map(([v]) => v);
    if (args.length !== fn.params.length || args.every((a) => a === UNKNOWN)) {
      return generic;
    }

    const calleeFile = this.funcFile.get(node.name) ?? this.currentFile;
    const inner = new Consts();
    for (let idx = 0; idx < fn.params.length; idx++) {
      const [v, n] = argPairs[idx];
      inner.set(fn.params[idx], v, new StaticDeriv("param", fn.params[idx], [n], null, calleeFile));
    }

    const prevFile = this.currentFile;
    this.currentFile = calleeFile;
    this.depth += 1;
    const special = new EffectSet();
    try {
      for (const s of fn.body) special.union(this.walk(s, fnEffects, inner));
    } finally {
      this.depth -= 1;
      this.currentFile = prevFile;
    }

    // Keep every generic effect whose target the specialised pass did not
    // sharpen. Never drop an effect kind the generic pass found.
    const sharpened = new EffectSet();
    const specialList = special.list();
    for (const g of generic) {
      const better = specialList.filter(
        (s) => s.kind === g.kind && s.boundary === g.boundary && !s.computed,
      );
      if (g.computed && better.length) sharpened.union(better);
      else sharpened.add(g);
    }
    const genericKinds = new Set(generic.list().map((g) => g.kind));
    const extra = specialList.filter((s) => !genericKinds.has(s.kind));
    return sharpened.union(extra);
  }

  isRecursive(name) {
    if (this._recCache.has(name)) return this._recCache.get(name);
    const seen = new Set();
    let stack = [name];
    let found = false;
    while (stack.length) {
      const cur = stack.pop();
      const fn = this.funcs.get(cur);
      if (fn === undefined) continue;
      for (const callee of this.callsIn(fn.body)) {
        if (callee === name) {
          found = true;
          stack = [];
          break;
        }
        if (!seen.has(callee)) {
          seen.add(callee);
          stack.push(callee);
        }
      }
    }
    this._recCache.set(name, found);
    return found;
  }

  assignedIn(stmts) {
    const out = new Set();
    const scan = (n) => {
      if (n === null || n === undefined) return;
      if (is(n, "Assign")) {
        out.add(n.name);
        scan(n.expr);
      } else if (is(n, "If")) {
        for (const s of n.then.concat(n.els)) scan(s);
      } else if (is(n, "ForEach")) {
        for (const s of n.body) scan(s);
      } else if (is(n, "FuncDef")) {
        for (const s of n.body) scan(s);
      } else if (is(n, "OrFail")) {
        scan(n.expr);
        for (const s of n.handler ?? []) scan(s);
      } else if (is(n, "When")) {
        for (const s of n.body.concat(n.els)) scan(s);
      }
    };
    for (const s of stmts) scan(s);
    return out;
  }

  callsIn(stmts) {
    const out = new Set();
    const scan = (n) => {
      if (n === null || n === undefined) return;
      if (is(n, "Call")) {
        out.add(n.name);
        for (const a of n.args) scan(a);
      } else if (is(n, "Var")) {
        if (this.funcs.has(n.name)) out.add(n.name);
      } else if (is(n, "Give") || is(n, "Why") || is(n, "Show") || is(n, "Not")) {
        scan(n.expr);
      } else if (is(n, "Assign")) {
        scan(n.expr);
      } else if (is(n, "BinOp")) {
        scan(n.left);
        scan(n.right);
      } else if (is(n, "Field")) {
        scan(n.obj);
      } else if (is(n, "Builtin")) {
        scan(n.arg);
      } else if (is(n, "OrFail")) {
        scan(n.expr);
        for (const s of n.handler ?? []) scan(s);
      } else if (is(n, "WriteTo")) {
        scan(n.value);
        scan(n.dest);
      } else if (is(n, "ListLit")) {
        for (const i of n.items) scan(i);
      } else if (is(n, "ForEach")) {
        scan(n.source);
        scan(n.where);
        for (const s of n.body) scan(s);
      } else if (is(n, "If")) {
        scan(n.cond);
        for (const s of n.then.concat(n.els)) scan(s);
      } else if (is(n, "FuncDef")) {
        for (const s of n.body) scan(s);
      } else if (is(n, "RecordLit")) {
        for (const f of n.fields) scan(fieldParts(f)[1]);
      } else if (is(n, "RecordUpdate")) {
        scan(n.base);
        for (const f of n.fields) scan(fieldParts(f)[1]);
      } else if (is(n, "ListPlus")) {
        scan(n.base);
        scan(n.item);
      } else if (is(n, "When")) {
        scan(n.subject);
        for (const p of n.pattern) {
          const [, inner] = p.items;
          const [kind, arg] = inner.items;
          if (kind === "match") scan(arg);
        }
        for (const s of n.body.concat(n.els)) scan(s);
      }
    };
    for (const s of stmts) scan(s);
    return out;
  }

  // ---- constant evaluation. Returns [value, StaticDeriv].
  const_(node, consts) {
    const F = this.currentFile;
    if (node === null || node === undefined) {
      return [UNKNOWN, new StaticDeriv("unknown", "nothing", [], null, F)];
    }
    if (is(node, "Str")) {
      return [node.value, new StaticDeriv("literal", `"${escapeStringLiteral(node.value)}"`, [], null, F)];
    }
    if (is(node, "Num")) {
      return [node.value, new StaticDeriv("literal", String(node.value.text()), [], null, F)];
    }
    if (is(node, "Bool")) {
      const label = node.value ? "true" : "false";
      return [node.value, new StaticDeriv("literal", label, [], null, F)];
    }
    if (is(node, "Var")) {
      const [value, stored] = consts.get(node.name);
      return [value, new StaticDeriv("name", node.name, [stored], null, F)];
    }
    if (is(node, "RecordLit")) {
      const pairs = node.fields.map((f) => {
        const [k, v] = fieldParts(f);
        return [k, this.const_(v, consts)];
      });
      const inputs = pairs.map(([, [, n]]) => n);
      if (pairs.some(([, [v]]) => v === UNKNOWN)) {
        return [UNKNOWN, new StaticDeriv("unknown", "{record}", inputs, null, F)];
      }
      const val = new Map();
      for (const [k, [v]] of pairs) val.set(k, v);
      return [val, new StaticDeriv("literal", "{record}", inputs, null, F)];
    }
    if (is(node, "ListLit")) {
      const items = node.items.map((i) => this.const_(i, consts));
      const inputs = items.map(([, n]) => n);
      if (items.some(([v]) => v === UNKNOWN)) {
        return [UNKNOWN, new StaticDeriv("unknown", "[list]", inputs, null, F)];
      }
      return [items.map(([v]) => v), new StaticDeriv("literal", "[list]", inputs, null, F)];
    }
    if (is(node, "RecordUpdate")) {
      const [base, baseN] = this.const_(node.base, consts);
      const pairs = node.fields.map((f) => {
        const [k, v] = fieldParts(f);
        return [k, this.const_(v, consts)];
      });
      const inputs = [baseN, ...pairs.map(([, [, n]]) => n)];
      if (base === UNKNOWN || !(base instanceof Map) || pairs.some(([, [v]]) => v === UNKNOWN)) {
        return [UNKNOWN, new StaticDeriv("unknown", "with", inputs, null, F)];
      }
      const updated = new Map(base);
      for (const [k, [v]] of pairs) updated.set(k, v);
      return [updated, new StaticDeriv("op", "with", inputs, null, F)];
    }
    if (is(node, "ListPlus")) {
      const [base, baseN] = this.const_(node.base, consts);
      const [item, itemN] = this.const_(node.item, consts);
      if (base === UNKNOWN || !Array.isArray(base) || item === UNKNOWN) {
        return [UNKNOWN, new StaticDeriv("unknown", "plus", [baseN, itemN], null, F)];
      }
      return [[...base, item], new StaticDeriv("op", "plus", [baseN, itemN], null, F)];
    }
    if (is(node, "OrFail")) {
      if (node.handler !== null && node.handler !== undefined) {
        const [, exprN] = this.const_(node.expr, consts);
        return [UNKNOWN, new StaticDeriv("unknown", "or fail as", [exprN], null, F)];
      }
      return this.const_(node.expr, consts);
    }
    if (is(node, "BinOp") && node.op === "+") {
      const [left, leftN] = this.const_(node.left, consts);
      const [right, rightN] = this.const_(node.right, consts);
      if (left === UNKNOWN || right === UNKNOWN) {
        return [UNKNOWN, new StaticDeriv("unknown", "+", [leftN, rightN], null, F)];
      }
      const sameType =
        (typeof left === "string" && typeof right === "string") ||
        (left instanceof PlanesNumber && right instanceof PlanesNumber);
      if (!sameType) {
        return [UNKNOWN, new StaticDeriv("unknown", "+", [leftN, rightN], null, F)];
      }
      const v = typeof left === "string" ? left + right : left.add(right);
      return [v, new StaticDeriv("op", "+", [leftN, rightN], null, F)];
    }
    if (is(node, "Builtin") && node.name === "text") {
      const [v, vn] = this.const_(node.arg, consts);
      if (v === UNKNOWN) return [UNKNOWN, new StaticDeriv("unknown", "text of", [vn], null, F)];
      return [this.asText(v), new StaticDeriv("op", "text of", [vn], null, F)];
    }
    if (is(node, "Builtin") && (node.name === "lower" || node.name === "upper")) {
      const [v, vn] = this.const_(node.arg, consts);
      const label = `${node.name} of`;
      if (v === UNKNOWN) return [UNKNOWN, new StaticDeriv("unknown", label, [vn], null, F)];
      const result = node.name === "lower" ? pyStr(v).toLowerCase() : pyStr(v).toUpperCase();
      return [result, new StaticDeriv("op", label, [vn], null, F)];
    }
    if (is(node, "Call")) {
      if (builtinNames().has(node.name) && !this.funcs.has(node.name)) {
        return this.constBuiltin(node, consts);
      }
      return this.constCall(node, consts);
    }
    return [UNKNOWN, new StaticDeriv("unknown", "{...}", [], null, F)];
  }

  constBuiltin(node, consts) {
    const F = this.currentFile;
    const K = effectKinds();
    if (node.args.length !== 1 || K.has(node.name)) {
      return [UNKNOWN, new StaticDeriv("unknown", node.name, [], null, F)];
    }
    const [v, n] = this.const_(node.args[0], consts);
    const label = `${node.name} of`;
    if (v === UNKNOWN) return [UNKNOWN, new StaticDeriv("unknown", label, [n], null, F)];
    if (node.name === "text") return [this.asText(v), new StaticDeriv("op", label, [n], null, F)];
    if (node.name === "lower") return [pyStr(v).toLowerCase(), new StaticDeriv("op", label, [n], null, F)];
    if (node.name === "upper") return [pyStr(v).toUpperCase(), new StaticDeriv("op", label, [n], null, F)];
    if (node.name === "normalize") {
      return [pyStr(v).normalize("NFC"), new StaticDeriv("op", label, [n], null, F)];
    }
    if (node.name === "join") {
      if (Array.isArray(v) && v.every((x) => typeof x === "string")) {
        return [v.join(""), new StaticDeriv("op", label, [n], null, F)];
      }
    }
    if (node.name === "rest") {
      if (Array.isArray(v) && v.length) {
        return [v.slice(1), new StaticDeriv("op", label, [n], null, F)];
      }
    }
    return [UNKNOWN, new StaticDeriv("unknown", label, [n], null, F)];
  }

  constCall(node, consts) {
    const F = this.currentFile;
    const fn = this.funcs.get(node.name);
    if (fn === undefined || this.depth > 6) {
      return [UNKNOWN, new StaticDeriv("unknown", node.name, [], null, F)];
    }
    if (this.isRecursive(node.name)) {
      return [UNKNOWN, new StaticDeriv("unknown", node.name, [], null, F)];
    }
    const argPairs = node.args.map((a) => this.const_(a, consts));
    const args = argPairs.map(([v]) => v);
    const argNodes = argPairs.map(([, n]) => n);
    if (args.length !== fn.params.length) {
      return [UNKNOWN, new StaticDeriv("unknown", node.name, argNodes, null, F)];
    }
    const gives = fn.body.filter((s) => is(s, "Give"));
    if (gives.length !== 1 || fn.body.length !== 1) {
      return [UNKNOWN, new StaticDeriv("unknown", node.name, argNodes, null, F)];
    }

    const calleeFile = this.funcFile.get(node.name) ?? this.currentFile;
    const inner = new Consts();
    for (let idx = 0; idx < fn.params.length; idx++) {
      const [v, n] = argPairs[idx];
      inner.set(fn.params[idx], v, new StaticDeriv("param", fn.params[idx], [n], null, calleeFile));
    }

    const prevFile = this.currentFile;
    this.currentFile = calleeFile;
    this.depth += 1;
    let value;
    try {
      [value] = this.const_(gives[0].expr, inner);
    } finally {
      this.depth -= 1;
      this.currentFile = prevFile;
    }
    return [value, new StaticDeriv("call", node.name, argNodes, null, F)];
  }

  asText(v) {
    if (typeof v === "boolean") return v ? "true" : "false";
    if (v instanceof PlanesNumber) return v.text();
    if (typeof v === "string") return v;
    return pyStr(v);
  }

  // ---- target description
  describe(node, consts) {
    const [v, n] = this.const_(node, consts);
    if (v !== UNKNOWN) return [this.asText(v), false, n];
    const [text, n2] = this.pattern(node, consts);
    return [text, true, n2];
  }

  pattern(node, consts) {
    const F = this.currentFile;
    if (node === null || node === undefined) {
      return ["{...}", new StaticDeriv("unknown", "{...}", [], null, F)];
    }
    const [v, n] = this.const_(node, consts);
    if (v !== UNKNOWN) return [this.asText(v), n];
    if (is(node, "OrFail")) return this.pattern(node.expr, consts);
    if (is(node, "BinOp") && node.op === "+") {
      const [lt, ln] = this.pattern(node.left, consts);
      const [rt, rn] = this.pattern(node.right, consts);
      return [lt + rt, new StaticDeriv("op", "+", [ln, rn], null, F)];
    }
    return ["{...}", n];
  }
}

export function analyse(src, file = null) {
  const a = new Analyser();
  a.entryFile = file;
  return a.analyse(src);
}

// ================================================================ diffing

export class SurfaceDiff {
  constructor({ added = [], removed = [], newBoundaries = [], droppedBoundaries = [] } = {}) {
    this.added = added;
    this.removed = removed;
    this.newBoundaries = newBoundaries;
    this.droppedBoundaries = droppedBoundaries;
  }
  isEmpty() {
    return this.added.length === 0 && this.removed.length === 0;
  }
  newDestinations() {
    const before = new Set(this.removed.map((e) => e.target));
    return this.added.filter((e) => !before.has(e.target) && !e.computed);
  }
  isSignificant() {
    return this.newBoundaries.length > 0 || this.newDestinations().length > 0;
  }
  render() {
    if (this.isEmpty()) return "no change to the effect surface";
    const lines = [];
    if (this.newBoundaries.length) {
      lines.push("NEW BOUNDARIES CROSSED: " + this.newBoundaries.join(", "));
    }
    const fresh = this.newDestinations();
    if (fresh.length && !this.newBoundaries.length) {
      const dests = [...new Set(fresh.map((e) => e.target))].sort(pyStrCmp);
      lines.push("NEW DESTINATIONS: " + dests.join(", "));
    }
    for (const e of this.added) lines.push(`  + ${e.boundary}: ${e}`);
    for (const e of this.removed) lines.push(`  - ${e.boundary}: ${e}`);
    if (this.droppedBoundaries.length) {
      lines.push("no longer touches: " + this.droppedBoundaries.join(", "));
    }
    return lines.join("\n");
  }
}

// ================================================================ canonical forms
//
// The agreement forms (A.3). `asJson` is shapes_cli.as_json's published surface
// form, reused verbatim rather than invented — the effect-surface oracle. The
// per-function breakdown and the derivation tree are the two facts as_json omits
// but A.3 names; both are plain structural serializations of the actual data, so
// the comparison is field-for-field, not a formatting decision.

// Bumped when a field's meaning changes; matches shapes_cli.FORMAT_VERSION.
export const FORMAT_VERSION = 1;

// The last path segment, without needing node:path (browser-safe).
function basename(p) {
  const parts = String(p).split("/");
  return parts[parts.length - 1];
}

export function asJson(surface, path) {
  return {
    format: FORMAT_VERSION,
    program: basename(path),
    kind: surface.isLibrary() ? "library" : surface.isPure() ? "pure" : "program",
    pure: surface.isPure(),
    complete: !surface.hasUnknowns() && surface.unresolved.length === 0,
    boundaries: surface.boundaries(),
    kinds: surface.kinds(),
    effects: surface.declared.map((e) => ({
      kind: e.kind,
      boundary: e.boundary,
      target: e.target,
      computed: e.computed,
      declared: e.claimed,
    })),
    runs_on_load: surface.effects.map((e) => ({
      kind: e.kind,
      boundary: e.boundary,
      target: e.target,
    })),
    modules_declared: [...surface.modules].sort(pyStrCmp),
    modules_unused: surface.declaredButUnused(),
    effects_undeclared: surface.usedButUndeclared().map((e) => ({
      kind: e.kind,
      target: e.target,
    })),
    unresolved_calls: [...new Set(surface.unresolved)].sort(pyStrCmp),
  };
}

// Per-function effect breakdown: sorted function name -> its sorted effects, as
// plain fields. shapes.functions is already sorted, so this is a direct read.
export function functionsBreakdown(surface) {
  const out = {};
  for (const name of [...surface.functions.keys()].sort(pyStrCmp)) {
    out[name] = surface.functions.get(name).map((e) => ({
      kind: e.kind,
      boundary: e.boundary,
      target: e.target,
      computed: e.computed,
      claimed: e.claimed,
    }));
  }
  return out;
}

// A StaticDeriv graph as nested plain objects — the canonical derivation form.
// Shared identity is broken into a tree the way shapes.py's own walkers do
// (origins_of, derivation_stats both re-walk); a cycle cannot occur because the
// graph is built bottom-up from immutable nodes.
export function derivTree(node) {
  if (node === null || node === undefined) return null;
  return {
    kind: node.kind,
    label: node.label,
    origin: node.origin ?? null,
    file: node.file ?? null,
    inputs: node.inputs.map(derivTree),
  };
}

// Per-effect derivation + origins, in declared order — for derivation agreement.
export function derivationForm(surface) {
  return surface.declared.map((e) => ({
    kind: e.kind,
    boundary: e.boundary,
    target: e.target,
    computed: e.computed,
    origins: surface.originsOf(e),
    derivation: derivTree(e.derivation),
  }));
}

export function diff(before, after) {
  const key = (e) => e.kind + "\x00" + e.target + "\x00" + (e.computed ? "T" : "F");
  const b = new Map();
  for (const e of before.declared) b.set(key(e), e);
  const a = new Map();
  for (const e of after.declared) a.set(key(e), e);
  const added = [...a.keys()].filter((k) => !b.has(k)).map((k) => a.get(k));
  const removed = [...b.keys()].filter((k) => !a.has(k)).map((k) => b.get(k));
  const beforeB = new Set(before.boundaries());
  const afterB = new Set(after.boundaries());
  return new SurfaceDiff({
    added: added.sort(effCmp),
    removed: removed.sort(effCmp),
    newBoundaries: [...afterB].filter((x) => !beforeB.has(x)).sort(pyStrCmp),
    droppedBoundaries: [...beforeB].filter((x) => !afterB.has(x)).sort(pyStrCmp),
  });
}
