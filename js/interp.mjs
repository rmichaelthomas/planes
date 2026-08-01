// js/interp.mjs — the Planes evaluator: values, provenance, effects.
//
// A port of interp.py. Values are raw JS: null (nothing), boolean, PlanesNumber,
// string, Array (list), Map (record — a Map, not a plain object, so insertion
// order holds for every key exactly as a Python dict does). Every evaluated
// value is a Traced(value, Deriv(...)) — provenance stays on, per the A.5
// measurement (Phase 2). Checked against interp.py by canonical-output
// agreement on the corpus (test_js_interp.py). interp.py is the specification.

import { MemoryHost, TestHost, HostError, pyJsonDumps } from "./host.mjs";
import { PlanesNumber, Inexact, NotANumber, numberFromText, sineDegrees } from "./planes_num.mjs";
import {
  escapeStringLiteral,
  codePoints,
  codePointLength,
} from "./planes_text.mjs";
import { parse, findDiscardedWrites } from "./parser.mjs";
import { builtinNames, effectKinds } from "./lexer.mjs";

// ================================================================ values

// One node in a derivation graph. Provenance lives here, not in types.
export class Deriv {
  constructor(kind, label, value, inputs = [], origin = null) {
    this.kind = kind;
    this.label = label;
    this.value = value;
    this.inputs = inputs;
    this.origin = origin;
  }
}

export class Traced {
  constructor(value, node) {
    this.value = value;
    this.node = node;
  }
}

export function lit(v, label = null) {
  return new Traced(v, new Deriv("literal", label !== null ? label : fmt(v), v));
}

function isNum(v) {
  return v instanceof PlanesNumber;
}

function isRecord(v) {
  return v instanceof Map;
}

export function fmt(v) {
  if (typeof v === "boolean") return v ? "true" : "false";
  if (v === null || v === undefined) return "nothing";
  if (v instanceof PlanesNumber) return v.text();
  if (typeof v === "number" || typeof v === "bigint") {
    return PlanesNumber.of(v).text();
  }
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return `[${v.length} items]`;
  if (v instanceof Map) return "{record}";
  return String(v);
}

// A caught error, as an ordinary record — discriminated by shape, never by type.
//
// One convention for an absent field (C5, Ruling 3): `fix` (§158) and `path`
// (A.4) are both always present and both `nothing` when they do not apply. A
// missing field is no match under `when`, so an absent `path` made
// `when e is { path }:` fall to the else branch for every error without one —
// and the author could not tell that from failing to match an error record at
// all. Planes already says absent explicitly, with `nothing` and `is nothing`.
//
// An empty path stays an empty list: a top-level mismatch has a path, and it
// has no steps.
function errorRecord(e) {
  const rec = new Map();
  rec.set("tag", e.tag);
  rec.set("detail", e.detail);
  rec.set("fix", e.fix || null);
  rec.set(
    "path",
    e.path === null || e.path === undefined
      ? null
      : e.path.map((p) => (typeof p === "number" ? PlanesNumber.of(p) : p)),
  );
  return rec;
}

// Sameness, guarded. Cross-type comparison is an error, not `false` — the number
// model refuses rather than rounds silently; equality refuses rather than
// answers. `path` accumulates the steps to a nested mismatch.
function equal(a, b, path = null) {
  path = path === null ? [] : path;
  if (a === null || b === null || a === undefined || b === undefined) {
    throw new PlanesError(
      "cannot-compare",
      "nothing cannot be compared with ==",
      "test for absence with `is nothing` — if the nothing is inside a " +
        "compared list or record rather than the whole value (the path " +
        "names which), test that inner value with `is nothing` directly " +
        "rather than rewriting the whole comparison",
      path,
    );
  }
  if (isNum(a) && isNum(b)) return PlanesNumber.of(a).eq(PlanesNumber.of(b));
  const aBool = typeof a === "boolean";
  const bBool = typeof b === "boolean";
  if (aBool !== bBool) {
    throw new PlanesError(
      "cannot-compare",
      `cannot compare ${detailValue(a)} with ${detailValue(b)}`,
      "compare a yes/no value with a yes/no value",
      path,
    );
  }
  if (aBool) return a === b;
  // Distinguish the JS types the way Python's `type(a) is not type(b)` does:
  // number/string/list/record must match kind.
  const kindOf = (x) =>
    isNum(x) ? "num" : typeof x === "string" ? "str" : Array.isArray(x) ? "list" : isRecord(x) ? "rec" : "other";
  if (kindOf(a) !== kindOf(b)) {
    throw new PlanesError(
      "cannot-compare",
      `cannot compare ${detailValue(a)} with ${detailValue(b)}`,
      "compare same-kind values — numbers with numbers, text with text, " +
        "lists with lists (compared element by element), or records with " +
        "records (compared field by field)",
      path,
    );
  }
  if (typeof a === "string") return a === b;
  if (Array.isArray(a)) {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
      if (!equal(a[i], b[i], [...path, i])) return false;
    }
    return true;
  }
  if (isRecord(a)) {
    const ak = [...a.keys()].sort();
    const bk = [...b.keys()].sort();
    if (ak.length !== bk.length || ak.some((k, i) => k !== bk[i])) {
      const sym = [...new Set([...ak, ...bk])].filter(
        (k) => !(a.has(k) && b.has(k)),
      ).sort();
      throw new PlanesError(
        "cannot-compare",
        `records have different fields: ${JSON.stringify(sym)}`,
        "compare records with the same fields",
        path,
      );
    }
    for (const k of a.keys()) {
      if (!equal(a.get(k), b.get(k), [...path, k])) return false;
    }
    return true;
  }
  return a === b;
}

function condition(v) {
  if (typeof v === "boolean") return v;
  throw new PlanesError(
    "not-a-yes-no",
    `a condition needs a yes/no value, found ${detailValue(v)}`,
    "compare it against something explicit rather than a bare value — " +
      "e.g. `if count of items > 0:` for an if, `x > 0 and y` for an " +
      "and/or operand, or `for each x in xs where x > 0:` for a where " +
      "clause",
  );
}

// The guard `lower`, `upper`, and `normalize` share — interp.py's require_text
// (C2, A.6 family 2). Each of the three used to hand its argument to
// `String()`, which is why the two implementations disagreed: `lower of [1, 2]`
// answered '1,2' here and '[1, 2]' in Python. They refuse instead, naming
// `text of`, in the same words on both sides.
function requireText(name, verb, v) {
  if (typeof v !== "string") {
    throw new PlanesError(
      "not-text",
      `cannot ${verb} ${detailValue(v)}`,
      `${name} takes text; convert first — e.g. ${name} of (text of n)`,
    );
  }
}

// The guard on an effect's target — interp.py's require_target. `ask`, `read`,
// and `write ... to` handed the value straight to the host, so a non-text
// target failed in the host's words rather than the language's.
function requireTarget(what, spelled, v) {
  if (typeof v !== "string") {
    throw new PlanesError(
      "not-text",
      `${what} must be text, found ${detailValue(v)}`,
      `wrap it with text of — \`${spelled}\``,
    );
  }
}

// How a value is written when it appears in an error detail — interp.py's
// `detail_value`, and `grammar/interp.planes`'s `detail-of-value`. The rule is
// the same in all three: write the value as the language would write it when
// writing it is bounded, and name its shape when it is not. Text gets quotes
// (`fmt` renders it bare, so `whole of "5"` reported `5` and read as a number,
// which is the one thing the message is about); a list or a record gets its
// shape rather than its contents, because an error detail must be bounded and
// must not spill a credential into stderr.
function detailValue(v) {
  return typeof v === "string" ? `"${escapeStringLiteral(v)}"` : fmt(v);
}

// The ` of a, b` tail of a declaration, and the call it wants — interp.py's
// param_list and call_shape. The arity messages name the parameters rather than
// only counting them.
function paramList(params) {
  return params.length ? ` of ${params.join(", ")}` : "";
}

function callShape(name, params) {
  return params.length ? `${name} of ${params.join(", ")}` : name;
}

// ================================================================ errors

// `noFix` mirrors interp.py's `no_fix` (C2): a reason, in words, why this raise
// site names no fix clause. Never rendered, so a message stays byte-identical
// across the two implementations. The catalogue is generated from the Python
// side, so nothing here reads it — it is carried so the two constructors have
// the same shape and a site marked deliberate in one is marked in both.
export class PlanesError extends Error {
  constructor(tag, detail = "", fix = "", path = null, noFix = null) {
    let msg = tag;
    if (detail) msg += `: ${detail}`;
    if (fix) msg += `\n  try: ${fix}`;
    super(msg);
    this.name = "PlanesError";
    this.tag = tag;
    this.detail = detail;
    this.fix = fix;
    this.path = path;
    this.noFix = noFix;
  }
}

// _Give — the return-value control-flow signal. Named GiveSignal to avoid the
// AST Give node factory.
class GiveSignal {
  constructor(value) {
    this.value = value;
  }
}

// ================================================================ env

export class Env {
  constructor(parent = null) {
    this.vars = new Map();
    this.parent = parent;
  }
  get(name) {
    if (this.vars.has(name)) return this.vars.get(name);
    if (this.parent) return this.parent.get(name);
    throw new PlanesError(
      "unknown-name",
      `no name '${name}' here`,
      `define it first: let ${name} = ...`,
    );
  }
  set(name, val) {
    let scope = this;
    while (scope !== null) {
      if (scope.vars.has(name)) {
        scope.vars.set(name, val);
        return;
      }
      scope = scope.parent;
    }
    this.vars.set(name, val);
  }
  bind_local(name, val) {
    this.vars.set(name, val);
  }
  has(name) {
    return this.vars.has(name) || (this.parent !== null && this.parent.has(name));
  }
}

class PlanesFunction {
  constructor(name, params, body, env, local = "") {
    this.name = name;
    this.params = params;
    this.body = body;
    this.env = env;
    this.local = local;
  }
}

// ================================================================ interpreter

export class Interpreter {
  constructor({ http = null, fs = null, host = null, record = false } = {}) {
    this.env = new Env();
    this.funcs = new Map();
    this.foreigns = new Map();
    this.modules = new Set();
    this.output = [];
    // One entry per line in `output`, in the same order and always the same
    // length: [derivation, source line] for the expression that produced it.
    // Interpreter-level OBSERVATION, like `effects` — not a language feature,
    // nothing a program can read, and it performs nothing: the node is the one
    // `eval` already built, kept rather than dropped. The effect log has never
    // carried a derivation, and the record plane that does is off unless
    // `record` is set and is forbidden from changing output/effects/surface —
    // so this is the third thing, and the smallest one that answers "which
    // expression drew this line". Per run and replaced, never accumulated.
    // interp.py carries the identical field for the identical reason.
    this.trace = [];
    // WHICH FILE A LINE IS IN. The trace's line has to name a line in the
    // source the CALLER handed over, or it is worse than nothing: a page
    // showing garden.planes and highlighting line 45 of draw.planes points the
    // reader at a file that is not on their screen. Each Function remembers
    // the file it was defined in, `currentFile` tracks whose body is running,
    // and `callSites` records where each active call was WRITTEN. A `show`
    // inside a helper then reports the innermost call site written in the
    // entry file — for `circle of x, y, r`, exactly the line that was clicked.
    // A single-file program is unaffected. interp.py carries the identical
    // three fields for the identical reason.
    this.currentFile = null;
    this.entryFile = null;
    this.callSites = [];
    this.effects = [];
    this.annotations = new Map();
    if (host !== null) this.host = host;
    else if (http !== null || fs !== null) {
      this.host = new TestHost({ responses: http ?? {}, files: fs ?? {} });
    } else this.host = new MemoryHost();
    this.record = record;
    this.records = [];
  }

  get fs() {
    return this.host.files ?? {};
  }

  // ---- the record plane (a no-op when record is off — the toggle only ever
  // appends to this.records, never changes output/effects/surface).
  host_anchor() {
    return { kind: "host", identity: this.host.name ?? "host" };
  }
  foreign_anchor(decl) {
    return { kind: "foreign-declaration", identity: decl.name };
  }
  maybe_record(kind, target, anchor, derivation = null, computed = false) {
    if (!this.record) return;
    const entry = {
      kind,
      boundary: effectKinds().get(kind) ?? "foreign",
      target,
      computed,
      anchor,
      when: this.host.clock(),
      derivation,
      format: 1,
    };
    this.records.push(entry);
    this.host.record(entry);
  }

  // ---- driving
  run(src) {
    const prog = parse(src);
    this.checkDiscardedWrites(prog);
    this.hoist(prog, this.env);
    for (const stmt of prog) {
      if (stmt.__node === "Note") continue;
      this.exec_stmt(stmt, this.env);
    }
    return this.output;
  }

  // A parse-time-computed, pre-execution refusal: findDiscardedWrites
  // (parser.mjs) is pure and has no way to throw PlanesError itself without
  // interp.mjs importing back into parser.mjs's own dependency, so the one
  // call site that turns its answer into a program error lives here, on the
  // class that already owns PlanesError. Public (not just called from
  // run() above) so modules.mjs's hoistAndRun — which parses each file in a
  // module graph itself, outside this class — can call it once per file
  // through the Interpreter instance it already threads through, the same
  // way it already calls this.hoist / this.exec_stmt rather than importing
  // interp.mjs's exports directly.
  checkDiscardedWrites(prog) {
    const violations = findDiscardedWrites(prog);
    if (violations.length > 0) {
      const name = violations[0];
      throw new PlanesError(
        "discarded-write",
        `'${name}' is bound with \`let\` inside a loop and reads the ` +
          `outer '${name}', so every iteration's value is discarded ` +
          `when that iteration ends`,
        "drop `let` — a bare assignment rebinds the outer name, " +
          "which is what accumulating across a loop needs",
      );
    }
  }

  // The line to record for an emitted output line, in the ENTRY source. A
  // `show` written in the entry file reports its own line; one written in a
  // module reports the innermost call site that WAS written in the entry
  // file. Zero when neither exists — a module's own top-level `show`.
  trace_line(stmtLine) {
    if (this.currentFile === this.entryFile) return stmtLine;
    for (let i = this.callSites.length - 1; i >= 0; i--) {
      if (this.callSites[i][0] === this.entryFile) return this.callSites[i][1];
    }
    return 0;
  }

  hoist(stmts, env, renames = null, file = null) {
    renames = renames ?? {};
    const rn = (k) => (k in renames ? renames[k] : k);
    for (const s of stmts) {
      if (s.__node === "Foreign") {
        this.foreigns.set(rn(s.name), s);
        continue;
      }
      if (s.__node === "FuncDef") {
        const fn = new PlanesFunction(s.name, s.params, s.body, env);
        fn.file = file;
        this.funcs.set(rn(s.name), fn);
        fn.local = s.name;
        this.hoist(s.body, env, renames, file);
      }
    }
  }

  exec_block(stmts, env) {
    let result = null;
    for (const s of stmts) {
      if (s.__node === "Note") continue;
      result = this.exec_stmt(s, env);
    }
    return result;
  }

  exec_stmt(stmt, env) {
    const k = stmt.__node;
    if (k === "Use") {
      this.modules.add(stmt.module);
      return null;
    }
    if (k === "Foreign") {
      this.foreigns.set(stmt.name, stmt);
      return null;
    }
    if (k === "Rule") return null;
    if (k === "Note") {
      throw new PlanesError(
        "annotation-executed",
        "an annotation reached the evaluator",
        "this is a bug in Planes, not in your program — please report it",
      );
    }
    if (k === "FuncDef") {
      // Re-registered when the definition is REACHED, not only when it was
      // hoisted, so a definition in a nested scope closes over that scope's
      // env. It has to carry the file too — dropped, this quietly replaced
      // every hoisted function with a file-less copy and every trace line
      // pointed at a call site instead of at the `show` itself. interp.py
      // carries the same one line for the same reason.
      const fn = new PlanesFunction(stmt.name, stmt.params, stmt.body, env);
      fn.file = this.currentFile;
      this.funcs.set(stmt.name, fn);
      return null;
    }
    if (k === "Assign") {
      const val = this.eval(stmt.expr, env);
      const named = new Traced(
        val.value,
        new Deriv("name", stmt.name, val.value, [val.node]),
      );
      if (stmt.is_let) env.bind_local(stmt.name, named);
      else env.set(stmt.name, named);
      if (stmt.annotation !== null) {
        this.annotations.set(stmt.name, stmt.annotation.text);
      } else this.annotations.delete(stmt.name);
      return named;
    }
    if (k === "Give") throw new GiveSignal(this.eval(stmt.expr, env));
    if (k === "Show") {
      const v = this.eval(stmt.expr, env);
      const text = fmt(v.value);
      this.output.push(text);
      this.trace.push([v.node, this.trace_line(stmt.line)]);
      this.host.show(text);
      this.effects.push(["show", text]);
      this.maybe_record("show", text, this.host_anchor(), v.node);
      return v;
    }
    if (k === "Why") {
      const v = this.eval(stmt.expr, env);
      const because =
        stmt.expr.__node === "Var" ? this.annotations.get(stmt.expr.name) ?? null : null;
      this.output.push(explain(v, because));
      // `why` writes to `output` too, so it writes to `trace` too: the two are
      // `why` writes to `output` too, so it writes to `trace` too: the two are
      // the same length by construction, not by convention. ZERO, and not the
      // statement's own line, because a `Why` node does not carry one —
      // giving it one changes the AST's SHAPE, which grammar/parser.planes
      // pins, and an AST field is therefore a grammar change. interp.py
      // records the identical zero for the identical reason.
      this.trace.push([v.node, 0]);
      return v;
    }
    if (k === "If") {
      const c = this.eval(stmt.cond, env);
      let result = null;
      for (const s of condition(c.value) ? stmt.then : stmt.els) {
        if (s.__node !== "Note") result = this.exec_stmt(s, env);
      }
      return result;
    }
    if (k === "When") return this.exec_when(stmt, env);
    if (k === "Fail") {
      const v = this.eval(stmt.message, env);
      // §158: text, or a record naming the message and, optionally, the fix.
      // `fail` is the one raise site whose message a program writes, and until
      // now it had nowhere to put the continuation clause every other message
      // in the language carries. No new syntax was needed — a record literal
      // already parsed here; what refused it was this guard.
      let message = v.value;
      let fix = null;
      if (isRecord(v.value)) {
        message = v.value.has("message") ? v.value.get("message") : null;
        fix = v.value.has("fix") ? v.value.get("fix") : null;
      }
      if (typeof message !== "string") {
        throw new PlanesError(
          "fail-message-not-text",
          `fail's message must be text, found ${detailValue(message)}`,
          'use text of it, or a record: fail { message: "...", fix: "..." } as tag',
        );
      }
      if (fix !== null && typeof fix !== "string") {
        throw new PlanesError(
          "fail-message-not-text",
          `fail's fix must be text, found ${detailValue(fix)}`,
          "use text for the fix, or leave the field out",
        );
      }
      throw new PlanesError(stmt.tag, message, fix || "");
    }
    return this.eval(stmt, env);
  }

  exec_when(stmt, env) {
    const subject = this.eval(stmt.subject, env);
    if (!isRecord(subject.value)) {
      throw new PlanesError(
        "not-a-record",
        `cannot match ${detailValue(subject.value)} against a shape`,
        "when matches record shapes only",
      );
    }
    let matched = true;
    const bindings = [];
    for (const entry of stmt.pattern) {
      const [fname, ka] = entry.items;
      const [kind, arg] = ka.items;
      if (!subject.value.has(fname)) {
        matched = false;
        break;
      }
      const field_val = subject.value.get(fname);
      if (kind === "match") {
        const want = this.eval(arg, env);
        if (!equal(field_val, want.value)) {
          matched = false;
          break;
        }
      } else {
        bindings.push([fname, field_val]);
      }
    }
    if (matched) {
      for (const [name, val] of bindings) {
        env.bind_local(
          name,
          new Traced(val, new Deriv("field", `.${name}`, val, [subject.node])),
        );
      }
    }
    let result = null;
    for (const s of matched ? stmt.body : stmt.els) {
      if (s.__node !== "Note") result = this.exec_stmt(s, env);
    }
    const fields = stmt.pattern.map((e) => e.items[0]).join(", ");
    const label = `when {${fields}} ` + (matched ? "matched" : "did not match");
    const rv = result !== null ? result.value : null;
    const rn = result !== null ? result.node : new Deriv("literal", "nothing", null);
    return new Traced(rv, new Deriv("op", label, rv, [subject.node, rn]));
  }

  // ---- expressions
  eval(node, env) {
    const k = node.__node;
    if (k === "Num") return lit(node.value);
    if (k === "Str") {
      const label = `"${escapeStringLiteral(node.value)}"`;
      return new Traced(node.value, new Deriv("literal", label, node.value));
    }
    if (k === "Bool") return lit(node.value);
    if (k === "Nothing") return lit(null);
    if (k === "Var") {
      if (this.funcs.has(node.name) && !env.has(node.name)) {
        return this.call(node.name, [], env, node.line ?? 0);
      }
      return env.get(node.name);
    }
    if (k === "RecordLit") {
      const parts = node.fields.map((pr) => {
        const [key, vn] = pr.items;
        return [key, this.eval(vn, env)];
      });
      const val = new Map();
      for (const [key, t] of parts) val.set(key, t.value);
      return new Traced(
        val,
        new Deriv("record", "{record}", val, parts.map(([, t]) => t.node)),
      );
    }
    if (k === "ListLit") {
      const items = node.items.map((i) => this.eval(i, env));
      const vals = items.map((i) => i.value);
      return new Traced(
        vals,
        new Deriv("list", `[${vals.length} items]`, vals, items.map((i) => i.node)),
      );
    }
    if (k === "RecordUpdate") {
      const base = this.eval(node.base, env);
      if (!isRecord(base.value)) {
        throw new PlanesError(
          "not-a-record",
          `cannot update ${detailValue(base.value)} with with`,
          "with updates a record; check the base is one",
        );
      }
      const parts = node.fields.map((pr) => {
        const [key, vn] = pr.items;
        return [key, this.eval(vn, env)];
      });
      const nw = new Map(base.value);
      for (const [key, t] of parts) nw.set(key, t.value);
      return new Traced(
        nw,
        new Deriv("op", "with", nw, [base.node, ...parts.map(([, t]) => t.node)]),
      );
    }
    if (k === "ListPlus") {
      const base = this.eval(node.base, env);
      if (!Array.isArray(base.value)) {
        throw new PlanesError(
          "not-a-list",
          `cannot append to ${detailValue(base.value)} with plus`,
          "plus appends to a list; check the base is one",
        );
      }
      const item = this.eval(node.item, env);
      const nw = [...base.value, item.value];
      return new Traced(nw, new Deriv("op", "plus", nw, [base.node, item.node]));
    }
    if (k === "Not") {
      const v = this.eval(node.expr, env);
      const r = !condition(v.value);
      return new Traced(r, new Deriv("op", "not", r, [v.node]));
    }
    if (k === "IsNothing") {
      const v = this.eval(node.expr, env);
      const r = v.value === null || v.value === undefined;
      return new Traced(r, new Deriv("op", "is nothing", r, [v.node]));
    }
    if (k === "BinOp") return this.eval_binop(node, env);
    if (k === "Field") {
      const obj = this.eval(node.obj, env);
      if (!isRecord(obj.value)) {
        throw new PlanesError(
          "not-a-record",
          `cannot read .${node.name} from ${detailValue(obj.value)}`,
          "check the value is a record before using dot access",
        );
      }
      const val = obj.value.has(node.name) ? obj.value.get(node.name) : null;
      return new Traced(val, new Deriv("field", `.${node.name}`, val, [obj.node]));
    }
    if (k === "Call") return this.call(node.name, node.args, env, node.line ?? 0);
    if (k === "Builtin") return this.builtin(node.name, this.eval(node.arg, env));
    if (k === "Round") {
      const v = this.eval(node.value, env);
      const p = this.eval(node.places, env);
      if (!isNum(v.value)) {
        throw new PlanesError("not-a-number", `cannot round ${detailValue(v.value)}`, "round only works on numbers");
      }
      const n = PlanesNumber.of(v.value).roundTo(Number(PlanesNumber.of(p.value).asInt()));
      return new Traced(n, new Deriv("op", `round to ${fmt(p.value)} places`, n, [v.node]));
    }
    if (k === "WriteTo") {
      const value = this.eval(node.value, env);
      const dest = this.eval(node.dest, env);
      if (!this.modules.has("file")) {
        throw new PlanesError("module-not-used", "writing a file needs the file module", "add `use file` at the top");
      }
      requireTarget("a destination to write to", "write value to (text of p)", dest.value);
      const payload = toJson(value.value);
      try {
        this.host.write(dest.value, payload);
      } catch (e) {
        if (e instanceof PlanesError) throw e;
        throw new PlanesError(
          "write-failed",
          `writing '${dest.value}' failed: ${e.message ?? e}`,
          "check the directory exists and is writable — the message " +
            "above names the actual OS error when it's something else, " +
            "such as no space left on the device or the destination " +
            "already existing as a directory",
        );
      }
      this.effects.push(["write", dest.value, payload.length]);
      this.maybe_record("write", dest.value, this.host_anchor(), dest.node);
      return new Traced(
        null,
        new Deriv("effect", `write to ${dest.value}`, null, [value.node], `file:${dest.value}`),
      );
    }
    if (k === "OrFail") {
      try {
        return this.eval(node.expr, env);
      } catch (e) {
        if (e instanceof GiveSignal) throw e;
        // The three raises here name no fix of their own, deliberately: each
        // re-tags a message somebody else wrote. The caught error's own `fix`
        // is carried forward (C2) — an error that named a fix must not stop
        // naming it because it crossed an `or fail`.
        if (e instanceof PlanesError) {
          if (node.handler !== null) return this.run_or_fail_handler(node, e, env);
          throw new PlanesError(
            node.tag,
            e.detail || e.tag,
            e.fix,
            e.path,
            "re-tags a message this raise did not write; the fix belongs to whoever raised it, " +
              "and is carried forward",
          );
        }
        const hostForwarded =
          "re-tags a host exception this raise did not write; a host failure is not something " +
          "the language can advise on";
        if (node.handler !== null) {
          return this.run_or_fail_handler(
            node,
            new PlanesError(node.tag, String(e.message ?? e), "", null, hostForwarded),
            env,
          );
        }
        throw new PlanesError(node.tag, String(e.message ?? e), "", null, hostForwarded);
      }
    }
    if (k === "ForEach") return this.eval_foreach(node, env);
    if (k === "If") {
      const c = this.eval(node.cond, env);
      let result = null;
      for (const s of condition(c.value) ? node.then : node.els) {
        if (s.__node !== "Note") result = this.exec_stmt(s, env);
      }
      return result;
    }
    throw new PlanesError(
      "cannot-evaluate",
      `'${k}' has no value — it is a statement, not an expression`,
      "write it on its own line; reaching this from a program the parser accepted is a defect " +
        "in the interpreter, not in the program, and worth reporting with the source that " +
        "produced it",
    );
  }

  eval_binop(node, env) {
    if (node.op === "and") {
      const left = this.eval(node.left, env);
      if (!condition(left.value)) return new Traced(false, new Deriv("op", "and", false, [left.node]));
      const right = this.eval(node.right, env);
      const v = condition(right.value);
      return new Traced(v, new Deriv("op", "and", v, [left.node, right.node]));
    }
    if (node.op === "or") {
      const left = this.eval(node.left, env);
      if (condition(left.value)) return new Traced(true, new Deriv("op", "or", true, [left.node]));
      const right = this.eval(node.right, env);
      const v = condition(right.value);
      return new Traced(v, new Deriv("op", "or", v, [left.node, right.node]));
    }
    if (node.op === "first") {
      const n = this.eval(node.left, env);
      const src = this.eval(node.right, env);
      // C2 (constraint 6): both guards. Neither implementation had them — a
      // non-number count and a non-sequence source each reached a host
      // primitive, and `first 1 of 5` crashed V8 here and raised a Python
      // TypeError there.
      if (!isNum(n.value)) {
        throw new PlanesError(
          "not-a-number",
          `the count in \`first n of\` must be a number, found ${detailValue(n.value)}`,
          "write the count as a number — `first 3 of items`",
        );
      }
      if (typeof src.value !== "string" && !Array.isArray(src.value)) {
        throw new PlanesError(
          "not-a-collection",
          `cannot take the first ${detailValue(n.value)} of ${detailValue(src.value)}`,
          "`first n of` takes a list or text; a record has no order to take a prefix of",
        );
      }
      const count = truncInt(n.value);
      const v =
        typeof src.value === "string"
          ? codePoints(src.value).slice(0, count).join("")
          : src.value.slice(0, count);
      return new Traced(v, new Deriv("op", `first ${count} of`, v, [src.node]));
    }
    const left = this.eval(node.left, env);
    const right = this.eval(node.right, env);
    const v = applyOp(node.op, left.value, right.value);
    return new Traced(v, new Deriv("op", node.op, v, [left.node, right.node]));
  }

  builtin(name, arg) {
    if (name === "ask") {
      if (!this.modules.has("http")) {
        throw new PlanesError("module-not-used", "asking a url needs the http module", "add `use http` at the top");
      }
      const url = arg.value;
      requireTarget("a url to ask", "ask (text of u)", url);
      let body;
      try {
        body = this.host.ask(url);
      } catch (e) {
        if (e instanceof HostError)
          throw new PlanesError(
            "ask-failed",
            `asking '${url}' failed: ${e.message}`,
            "check the url is reachable and spelled right; a run without the network needs a " +
              "stubbed response",
          );
        throw e;
      }
      this.effects.push(["ask", url, body.length]);
      this.maybe_record("ask", url, this.host_anchor(), arg.node);
      let parsed;
      try {
        parsed = fromForeign(this.host.parseJson(body));
      } catch {
        parsed = body;
      }
      return new Traced(parsed, new Deriv("effect", `ask ${url}`, parsed, [arg.node], `network:${url}`));
    }
    if (name === "read") {
      if (!this.modules.has("file")) {
        throw new PlanesError("module-not-used", "reading a file needs the file module", "add `use file` at the top");
      }
      const path = arg.value;
      requireTarget("a path to read", "read (text of p)", path);
      let body;
      try {
        body = this.host.read(path);
      } catch (e) {
        if (e instanceof HostError) throw new PlanesError("no-such-file", path, "check the path, or write it first");
        throw e;
      }
      this.effects.push(["read", path, body.length]);
      this.maybe_record("read", path, this.host_anchor(), arg.node);
      return new Traced(body, new Deriv("effect", `read ${path}`, body, [arg.node], `file:${path}`));
    }
    if (name === "count") {
      let n;
      if (typeof arg.value === "string") n = codePointLength(arg.value);
      else if (Array.isArray(arg.value)) n = arg.value.length;
      else if (isRecord(arg.value)) n = arg.value.size;
      else
        throw new PlanesError(
          "not-a-collection",
          `cannot count ${detailValue(arg.value)}`,
          "count takes a list, a record, or text — check which of those this value should be",
        );
      const v = PlanesNumber.of(n);
      return new Traced(v, new Deriv("op", "count of", v, [arg.node]));
    }
    if (name === "lower") {
      requireText("lower", "lowercase", arg.value);
      const v = arg.value.toLowerCase();
      return new Traced(v, new Deriv("op", "lower of", v, [arg.node]));
    }
    if (name === "upper") {
      requireText("upper", "uppercase", arg.value);
      const v = arg.value.toUpperCase();
      return new Traced(v, new Deriv("op", "upper of", v, [arg.node]));
    }
    if (name === "whole") {
      if (!isNum(arg.value)) {
        throw new PlanesError(
          "not-a-number",
          `cannot take the whole part of ${detailValue(arg.value)}`,
          "whole of rounds a number to the nearest whole, half away from zero; " +
            "if this is text, convert it first with " +
            "number of — a boolean, a list, a record, or nothing has no path to becoming a number",
        );
      }
      const n = PlanesNumber.of(arg.value).roundTo(0);
      return new Traced(n, new Deriv("op", "whole of", n, [arg.node]));
    }
    if (name === "number") {
      // The twelfth builtin (A-Q19): text to an exact number, closing the
      // round trip `write` opened and nothing closed — `write` emits a
      // number as JSON text so an exact value survives a tool that isn't
      // Planes, and `read` and `ask` hand text back, but nothing turned
      // that text back into a number until now.
      if (typeof arg.value !== "string") {
        throw new PlanesError(
          "not-text",
          `cannot make a number from ${detailValue(arg.value)}`,
          "number of takes text; a number does not need converting, and nothing else has a path to one",
        );
      }
      let n;
      try {
        n = numberFromText(arg.value);
      } catch (e) {
        if (!(e instanceof NotANumber)) throw e;
        if (e.approximation) {
          throw new PlanesError(
            "not-a-number",
            `${detailValue(arg.value)} is an approximation of a number, not a number`,
            "the ~ marks text that was rounded for display, so the original value cannot be " +
              "recovered from it — carry the number itself instead of its text",
          );
        }
        throw new PlanesError(
          "not-a-number",
          `cannot make a number from ${detailValue(arg.value)}`,
          "number of takes an optional leading -, digits, and at most one . — no exponent " +
            'notation, e.g. number of "12.5"',
        );
      }
      return new Traced(n, new Deriv("op", "number of", n, [arg.node]));
    }
    if (name === "sine") {
      // The eleventh builtin, and the only operation in the language that
      // returns an approximate value (checkpoint v21.0 §§251-253). Takes
      // DEGREES, consistent with the drawing protocol's `rotate`: degrees are
      // whole numbers and stay exact under this language's arithmetic, where
      // radians would arrive already approximated.
      if (!isNum(arg.value)) {
        throw new PlanesError(
          "not-a-number",
          `cannot take the sine of ${detailValue(arg.value)}`,
          "sine takes an angle in degrees as a number — e.g. sine of 30; " +
            "if this is text, convert it first with number of",
        );
      }
      const n = sineDegrees(arg.value);
      return new Traced(n, new Deriv("op", "sine of", n, [arg.node]));
    }
    if (name === "text") {
      const v = fmt(arg.value);
      return new Traced(v, new Deriv("op", "text of", v, [arg.node]));
    }
    if (name === "normalize") {
      requireText("normalize", "normalize", arg.value);
      const v = arg.value.normalize("NFC");
      return new Traced(v, new Deriv("op", "normalize of", v, [arg.node]));
    }
    if (name === "join") {
      if (!Array.isArray(arg.value)) {
        throw new PlanesError("cannot-join", `cannot join ${detailValue(arg.value)}`, "join takes a list of text; check the value is a list");
      }
      for (const x of arg.value) {
        if (typeof x !== "string") {
          throw new PlanesError("cannot-join", `join needs a list of text, found ${detailValue(x)}`, "convert each item first — e.g. text of n");
        }
      }
      const v = arg.value.join("");
      return new Traced(v, new Deriv("op", "join of", v, [arg.node]));
    }
    if (name === "rest") {
      if (typeof arg.value === "string") {
        throw new PlanesError("not-a-list", `cannot take the rest of text ${detailValue(arg.value)}`, "rest is for lists; for a text prefix use `first n of`");
      }
      if (!Array.isArray(arg.value)) {
        throw new PlanesError("not-a-list", `cannot take the rest of ${detailValue(arg.value)}`, "rest takes a list; check the value is a list");
      }
      if (arg.value.length === 0) {
        throw new PlanesError("empty-list", "cannot take the rest of an empty list", "check it is not empty first, e.g. `if count of xs > 0:`");
      }
      const v = arg.value.slice(1);
      return new Traced(v, new Deriv("op", "rest of", v, [arg.node]));
    }
    throw new PlanesError(
      "unknown-builtin",
      `no builtin is named '${name}'`,
      "the twelve builtins are fixed and the lexer recognises only those, so reaching this is a " +
        "defect in the interpreter rather than in the program — worth reporting with the source",
    );
  }

  run_or_fail_handler(node, error, env) {
    const rec = errorRecord(error);
    const bound = new Traced(rec, new Deriv("record", "{record}", rec, []));
    env.bind_local(node.tag, bound);
    return this.exec_block(node.handler, env);
  }

  eval_foreach(node, env) {
    const source = this.eval(node.source, env);
    const sv = source.value;
    if (!(Array.isArray(sv) || typeof sv === "string")) {
      throw new PlanesError(
        "not-a-collection",
        `cannot loop over ${detailValue(sv)}`,
        "for each needs a list, or a string to walk its code points",
      );
    }
    // A string is walked by code point, not UTF-16 unit.
    const seq = typeof sv === "string" ? codePoints(sv) : sv;
    const results = [];
    const nodes = [];
    for (const item of seq) {
      const inner = new Env(env);
      const item_t = new Traced(item, new Deriv("item", node.var, item, [source.node]));
      inner.bind_local(node.var, item_t);
      if (node.where !== null) {
        if (!condition(this.eval(node.where, inner).value)) continue;
      }
      const r = node.is_expr ? this.eval(node.body[0], inner) : this.exec_block(node.body, inner);
      if (r !== null) {
        results.push(r.value);
        nodes.push(r.node);
      }
    }
    const label = `for each ${node.var}` + (node.where !== null ? " where ..." : "");
    return new Traced(results, new Deriv("comprehension", label, results, [source.node, ...nodes.slice(0, 3)]));
  }

  call(name, args, env, line = 0) {
    if (!this.funcs.has(name) && builtinNames().has(name)) {
      if (args.length !== 1) {
        throw new PlanesError("wrong-arity", `'${name}' takes 1 value, given ${args.length}`, `write it as \`${name} of x\``);
      }
      const arg = args[0] instanceof Traced ? args[0] : this.eval(args[0], env);
      return this.builtin(name, arg);
    }
    if (this.foreigns.has(name) && !this.funcs.has(name)) {
      return this.call_foreign(this.foreigns.get(name), args, env);
    }
    let fn;
    let iname;
    if (this.funcs.has(name)) {
      fn = this.funcs.get(name);
      iname = name;
    } else {
      fn = null;
      for (const f of this.funcs.values()) {
        if (f.local === name) {
          fn = f;
          break;
        }
      }
      if (fn === null) {
        throw new PlanesError("unknown-function", `no function named '${name}'`, `define it: to ${name}: ...`);
      }
      iname = fn.local || fn.name;
    }
    if (args.length !== fn.params.length) {
      const word = fn.params.length === 1 ? "value" : "values";
      throw new PlanesError(
        "wrong-arity",
        `'${iname}' takes ${fn.params.length} ${word}, given ${args.length}`,
        `it is declared \`to ${iname}${paramList(fn.params)}\`, so call it as ` +
          `\`${callShape(iname, fn.params)}\``,
      );
    }
    const arg_vals = args.map((a) => (a instanceof Traced ? a : this.eval(a, env)));
    const inner = new Env(fn.env);
    for (let i = 0; i < fn.params.length; i++) {
      const a = arg_vals[i];
      inner.bind_local(fn.params[i], new Traced(a.value, new Deriv("name", fn.params[i], a.value, [a.node])));
    }
    // Where this call was WRITTEN, and whose body is now running. Both are
    // restored on every exit path — including a `give` and a depth refusal —
    // so an early return can never leave the interpreter believing it is
    // somewhere it is not.
    this.callSites.push([this.currentFile, line]);
    const outerFile = this.currentFile;
    this.currentFile = fn.file ?? null;
    try {
      for (const s of fn.body) {
        if (s.__node !== "Note") this.exec_stmt(s, inner);
      }
      return new Traced(null, new Deriv("call", iname, null, arg_vals.map((a) => a.node)));
    } catch (e) {
      if (e instanceof GiveSignal) {
        return new Traced(
          e.value.value,
          new Deriv("call", iname, e.value.value, [e.value.node, ...arg_vals.map((a) => a.node)]),
        );
      }
      if (e instanceof RangeError) {
        // V8's "Maximum call stack size exceeded" — the JS analogue of CPython's
        // RecursionError, narrowed to this body's own re-entry.
        throw new PlanesError(
          "recursion-too-deep",
          `'${iname}' recursed past the depth this interpreter can follow`,
          "if recursing over a collection, replace it with one `for each` " +
            "pass threading a state record forward — or a cons-list stack " +
            "for nested structure; if recursing on a plain number with no " +
            "collection involved, `for each` has nothing to iterate over, " +
            "so restructure the computation to avoid unbounded recursion " +
            "depth instead",
        );
      }
      throw e;
    } finally {
      this.currentFile = outerFile;
      this.callSites.pop();
    }
  }

  call_foreign(decl, args, env) {
    if (args.length !== decl.params.length) {
      const word = decl.params.length === 1 ? "value" : "values";
      throw new PlanesError(
        "wrong-arity",
        `'${decl.name}' takes ${decl.params.length} ${word}, given ${args.length}`,
        `it is declared \`foreign ${decl.name}${paramList(decl.params)} from ` +
          `"${decl.target}"\`, so call it as \`${callShape(decl.name, decl.params)}\``,
      );
    }
    const arg_vals = args.map((a) => (a instanceof Traced ? a : this.eval(a, env)));
    let fn;
    try {
      fn = this.host.resolve(decl.target);
    } catch (e) {
      if (e instanceof HostError && String(e.message).includes("bad target")) {
        throw new PlanesError("bad-foreign-target", decl.target, `write it as ${this.host.targetHint()}`);
      }
      throw new PlanesError("foreign-not-found", `cannot find '${decl.target}' in the host`, "check the module is installed and the name is right");
    }
    for (const eff of decl.effects) {
      const [kind, where] = eff.items;
      let dest = decl.target;
      let dest_node = null;
      if (where !== null) {
        const [tag, target] = where.items;
        if (tag === "literal") dest = target;
        else if (tag === "param" && decl.params.includes(target)) {
          const i = decl.params.indexOf(target);
          if (i < arg_vals.length) {
            dest = fmt(arg_vals[i].value);
            dest_node = arg_vals[i].node;
          }
        }
      }
      this.effects.push([kind, dest]);
      this.maybe_record(kind, dest, this.foreign_anchor(decl), dest_node);
    }
    let raw;
    try {
      raw = fn(...arg_vals.map((a) => toHost(a.value)));
    } catch (e) {
      throw new PlanesError("foreign-failed", `'${decl.name}' raised ${e.name ?? "Error"}: ${e.message ?? e}`, "wrap the call with `or fail as ...` to name the failure");
    }
    const value = fromForeign(raw);
    return new Traced(value, new Deriv("foreign", decl.name, value, arg_vals.map((a) => a.node), `foreign:${decl.target}`));
  }
}

// ================================================================ operators & conversions

function truncInt(v) {
  // int(Number) — truncation toward zero, as Python's int(Fraction).
  const q = PlanesNumber.of(v).q;
  return Number(q.n / q.d);
}

function applyOp(op, a, b) {
  if (op === "+") {
    if (typeof a === "string" && typeof b === "string") return a + b;
    if (Array.isArray(a) && Array.isArray(b)) return [...a, ...b];
    if (isNum(a) && isNum(b)) return arith("+", a, b);
    throw new PlanesError(
      "cannot-combine",
      `cannot combine ${detailValue(a)} with ${detailValue(b)} using +`,
      "convert first — `text of n` to build text, or `number of t` to do " +
        "arithmetic — but only for a text/number pairing; if either side " +
        "is a list or record, neither conversion is meaningful: use " +
        "`plus` to append to a list, `with` to update a record, or " +
        "rewrite the expression",
    );
  }
  if (op === "-") return arith("-", a, b);
  if (op === "*") return arith("*", a, b);
  if (op === "/") {
    if (isNum(b) && PlanesNumber.of(b).isZero()) {
      throw new PlanesError("divided-by-zero", "the right side of / was 0", "guard with `if divisor != 0:`");
    }
    return arith("/", a, b);
  }
  if (op === "<" || op === ">" || op === "<=" || op === ">=") return compareOp(op, a, b);
  if (op === "==") return equal(a, b);
  if (op === "!=") return !equal(a, b);
  if (op === "in") return inOp(a, b);
  throw new PlanesError(
    "unknown-operator",
    `no operator is spelled '${op}'`,
    "the parser builds only the operators the language defines, so reaching this is a defect " +
      "in the interpreter rather than in the program — worth reporting with the source",
  );
}

function arith(op, a, b) {
  for (const v of [a, b]) {
    if (!isNum(v)) {
      throw new PlanesError("not-a-number", `cannot use '${op}' on ${detailValue(v)}`, "check the value is a number before doing arithmetic");
    }
  }
  const x = PlanesNumber.of(a);
  const y = PlanesNumber.of(b);
  try {
    if (op === "+") return x.add(y);
    if (op === "-") return x.sub(y);
    if (op === "*") return x.mul(y);
    if (op === "/") return x.div(y);
  } catch (e) {
    if (e instanceof Inexact) {
      throw new PlanesError("needs-rounding", e.message, "round an intermediate value, e.g. `round x to 6 places`");
    }
    throw e;
  }
  throw new PlanesError(
    "unknown-operator",
    `'${op}' is not an arithmetic operator`,
    "arithmetic is + - * /; reaching this means apply_op routed an operator here that it does " +
      "not itself arithmetic on, which is a defect in the interpreter rather than in the program",
  );
}

function compareOp(op, a, b) {
  let x = a;
  let y = b;
  if (isNum(a) && isNum(b)) {
    x = PlanesNumber.of(a);
    y = PlanesNumber.of(b);
    if (op === "<") return x.lt(y);
    if (op === ">") return x.gt(y);
    if (op === "<=") return x.le(y);
    return x.ge(y);
  }
  const kindOf = (v) => (typeof v === "string" ? "str" : isNum(v) ? "num" : "other");
  if (kindOf(a) !== kindOf(b) || kindOf(a) === "other") {
    throw new PlanesError("cannot-compare", `cannot compare ${detailValue(a)} with ${detailValue(b)}`, "compare numbers with numbers, or text with text");
  }
  // both strings — Python compares by code point
  const cmp = strCmp(x, y);
  if (op === "<") return cmp < 0;
  if (op === ">") return cmp > 0;
  if (op === "<=") return cmp <= 0;
  return cmp >= 0;
}

function strCmp(a, b) {
  const as = codePoints(a);
  const bs = codePoints(b);
  const n = Math.min(as.length, bs.length);
  for (let i = 0; i < n; i++) {
    const d = as[i].codePointAt(0) - bs[i].codePointAt(0);
    if (d !== 0) return d;
  }
  return as.length - bs.length;
}

// `a in b` — over a list, a record's field names, or text. Guarded on both
// operands (C2, constraint 6): `b` had no guard, so `1 in 5` answered
// `unknown-operator`, which named the wrong thing — `in` is an operator the
// language defines; what was wrong was the value on the right. And text had no
// guard on `a`, so `1 in "a1b"` coerced the 1 to "1" and answered true here
// while Python raised a TypeError.
function inOp(a, b) {
  if (typeof b === "string") {
    if (typeof a !== "string") {
      throw new PlanesError(
        "not-text",
        `cannot look for ${detailValue(a)} in text ${detailValue(b)}`,
        "`in` over text looks for text — wrap the left side with " +
          "`text of`, but only when it is a number, yes/no value, or " +
          "nothing; if it is a list or record, `text of` gives an opaque " +
          "placeholder, not its contents, so the search will not find " +
          "what was probably intended",
      );
    }
    return b.includes(a);
  }
  if (Array.isArray(b)) return b.some((x) => looseEqual(a, x));
  if (isRecord(b)) return b.has(a);
  throw new PlanesError(
    "not-a-collection",
    `cannot look inside ${detailValue(b)}`,
    "`in` looks inside a list, a record's field names, or text",
  );
}

function looseEqual(a, b) {
  if (isNum(a) && isNum(b)) return a.eq(b);
  if (typeof a === "boolean" || typeof b === "boolean") return a === b;
  if (typeof a === "string" && typeof b === "string") return a === b;
  if (a === null || b === null) return a === b;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((x, i) => looseEqual(x, b[i]));
  }
  if (isRecord(a) && isRecord(b)) {
    if (a.size !== b.size) return false;
    for (const [k, v] of a) if (!b.has(k) || !looseEqual(v, b.get(k))) return false;
    return true;
  }
  return false;
}

// json.dumps(unwrap(v), indent=2) — the write effect's payload. Whole numbers
// stay whole; others go out as text so an exact value is not silently rounded.
export function toJson(v) {
  function unwrap(x) {
    if (x instanceof Traced) return unwrap(x.value);
    if (Array.isArray(x)) return x.map(unwrap);
    if (x instanceof Map) {
      const o = {};
      for (const [k, val] of x) o[k] = unwrap(val);
      return o;
    }
    if (x instanceof PlanesNumber) return x.isWhole() ? Number(x.asInt()) : x.text();
    return x;
  }
  return pyJsonDumps(unwrap(v));
}

function toHost(x) {
  if (x instanceof PlanesNumber) return x.isWhole() ? Number(x.asInt()) : x.toNumber();
  if (Array.isArray(x)) return x.map(toHost);
  if (x instanceof Map) {
    const o = {};
    for (const [k, v] of x) o[k] = toHost(v);
    return o;
  }
  return x;
}

function fromForeign(x) {
  if (typeof x === "boolean") return x;
  if (typeof x === "number" || typeof x === "bigint") return PlanesNumber.of(x);
  if (Array.isArray(x)) return x.map(fromForeign);
  if (x !== null && typeof x === "object") {
    const m = new Map();
    for (const [k, v] of Object.entries(x)) m.set(k, fromForeign(v));
    return m;
  }
  return x;
}

// ================================================================ why

// Every distinct approximation entry reachable in a derivation. A comparison
// between two approximate values has TWO of them, and showing both is the
// whole reason the no-tolerance rule is defensible: the answer is plain, and
// the explanation says where each side stopped being exact. Deduped by CONTENT
// rather than by object identity, so two sides that entered the same way name
// it once and two that entered differently name it twice.
export function approximationsIn(node, seen = new Set(), found = []) {
  if (node === null || typeof node !== "object" || seen.has(node)) return found;
  seen.add(node);
  const v = node.value;
  if (v instanceof PlanesNumber && v.approx !== null && !found.some((a) => a.eq(v.approx))) {
    found.push(v.approx);
  }
  for (const inp of node.inputs ?? []) approximationsIn(inp, seen, found);
  return found;
}

export function explain(traced, because = null) {
  const n = traced.node;
  const inner = n.kind === "name" && n.inputs.length ? n.inputs[0] : n;
  let text = `${fmt(traced.value)} from ${render(inner)}`;
  if (because) text += `\n  because "${escapeStringLiteral(because)}"`;
  for (const a of approximationsIn(n)) {
    text += `\n  approximate — ${a.op}: ${a.detail}`;
  }
  return text;
}

export function render(node) {
  const k = node.kind;
  if (k === "literal") return node.label;
  if (k === "name" || k === "item") return `${node.label} (${fmt(node.value)})`;
  if (k === "field") {
    const base = node.inputs.length ? render(node.inputs[0]) : "?";
    return `${base}${node.label}`;
  }
  if (k === "call") {
    const body = node.inputs.length ? node.inputs[0] : null;
    const args = node.inputs.slice(1);
    const arglist = args.map(render).join(", ");
    const head = arglist ? `${node.label}(${arglist})` : node.label;
    return body ? `${head} = ${render(body)}` : head;
  }
  if (k === "effect") return node.label;
  if (k === "comprehension") {
    const src = node.inputs.length ? render(node.inputs[0]) : "?";
    return `${node.label} over ${src}`;
  }
  if (k === "list") return node.label;
  if (k === "record") return node.label;
  if (k === "op") {
    if (node.label.endsWith(" of") || node.label === "not") {
      return `${node.label} ${render(node.inputs[0])}`;
    }
    return node.inputs.map(render).join(` ${node.label} `);
  }
  return fmt(node.value);
}

export function origins(traced) {
  const found = [];
  function walk(n) {
    if (n.origin) found.push(n.origin);
    for (const i of n.inputs) walk(i);
  }
  walk(traced.node);
  return found;
}
