// js/host.js — the host: whatever actually performs an effect.
//
// The JavaScript counterpart of host.py. The Python module's whole argument
// carries over unchanged: almost nothing in Planes is host-shaped. The parser
// reads a foreign target as an opaque string, the analyser never parses it,
// and only the interpreter interprets it. So the host question is not "which
// language should Planes be written in" but "what does a host have to
// provide", and the answer is this file: the closed effect vocabulary's five
// capabilities, a way to resolve a foreign name, and a JSON boundary.
//
// host.py names eight required methods (each raises NotImplementedError there):
// ask, read, write, show, clock, resolve, parse_json, to_json. `record` is an
// optional no-op, not one of the eight. That count — eight — is the claim this
// whole build tests; see REPORT_SECOND_HOST.md's seam verdict.

import fs from "node:fs";
import { execFileSync } from "node:child_process";

// The host could not do what was asked. Distinct from a program error: this is
// the machine failing, not the program being wrong. Mirrors host.py's
// HostError.
export class HostError extends Error {
  constructor(message) {
    super(message);
    this.name = "HostError";
  }
}

// What a host must provide. Five effect capabilities matching the closed effect
// vocabulary, plus foreign resolution and a JSON boundary. A host that
// implements these runs Planes; the language does not otherwise care what it is
// written in.
export class Host {
  get name() {
    return "abstract";
  }

  // ---- effects
  ask(_url) {
    throw new HostError("ask: not implemented on the abstract host");
  }
  read(_path) {
    throw new HostError("read: not implemented on the abstract host");
  }
  write(_path, _text) {
    throw new HostError("write: not implemented on the abstract host");
  }
  show(_text) {
    throw new HostError("show: not implemented on the abstract host");
  }
  clock() {
    throw new HostError("clock: not implemented on the abstract host");
  }

  // ---- the record plane — a host capability, not a program effect. Optional,
  // unlike the five above: a host that does nothing here is still a complete
  // host, and the interpreter must not depend on it. The default is a no-op.
  record(_entry) {}

  // ---- foreign resolution. The target is opaque to the language; a Python
  // host reads `builtins.sorted`, a JavaScript host reads whatever it chooses
  // to recognise. The string is host-specific by design, which is why no
  // syntax change is needed to move hosts.
  resolve(_target) {
    throw new HostError("resolve: not implemented on the abstract host");
  }
  targetHint() {
    return "a name this host understands";
  }

  // ---- data at the boundary
  parseJson(_text) {
    throw new HostError("parseJson: not implemented on the abstract host");
  }
  toJson(_value) {
    throw new HostError("toJson: not implemented on the abstract host");
  }
}

// json.dumps(..., indent=2) escapes non-ASCII (ensure_ascii=True); JSON
// .stringify does not. Escape every UTF-16 code unit above 0x7e as \uXXXX so a
// written file is byte-identical to interp.py's. Astral characters become a
// surrogate pair of \uXXXX escapes on both sides, since Python emits the pair
// too. Structural JSON characters are all ASCII, so post-processing the whole
// string is safe.
function ensureAscii(s) {
  let out = "";
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c > 0x7e) {
      out += "\\u" + c.toString(16).padStart(4, "0");
    } else {
      out += s[i];
    }
  }
  return out;
}

// Python's sorted/max/min over a homogeneous list. The corpus's foreign.planes
// calls builtins.sorted / max / min; these reproduce their default ordering
// (numeric for numbers, code-point-lexicographic for strings) so a resolved
// foreign agrees with interp.py's. Numbers here are the marshalled foreign form
// (plain JS numbers), not Planes value records — the interpreter marshals in
// and out around the call.
function pyCompare(a, b) {
  if (typeof a === "number" && typeof b === "number") return a - b;
  if (typeof a === "string" && typeof b === "string") {
    // Python compares strings by code point.
    const as = [...a];
    const bs = [...b];
    const n = Math.min(as.length, bs.length);
    for (let i = 0; i < n; i++) {
      const d = as[i].codePointAt(0) - bs[i].codePointAt(0);
      if (d !== 0) return d;
    }
    return as.length - bs.length;
  }
  throw new HostError("sorted: unorderable mixed types");
}

function pySorted(arr) {
  return [...arr].sort(pyCompare);
}
function pyMax(arr) {
  if (arr.length === 0) throw new HostError("max: empty sequence");
  return arr.reduce((m, x) => (pyCompare(x, m) > 0 ? x : m));
}
function pyMin(arr) {
  if (arr.length === 0) throw new HostError("min: empty sequence");
  return arr.reduce((m, x) => (pyCompare(x, m) < 0 ? x : m));
}

// The named targets the corpus actually resolves. A JS host cannot import an
// arbitrary Python module.function the way PythonHost does with importlib, and
// it does not need to: the whole corpus reaches only these. Everything else is
// a bad target for this host, reported with the host's convention — which is
// exactly host.resolve's job, the one non-effect method interp.planes cannot
// stand in for.
const NODE_TARGETS = {
  "builtins.sorted": (arr) => pySorted(arr),
  "builtins.max": (arr) => (Array.isArray(arr) ? pyMax(arr) : arr),
  "builtins.min": (arr) => (Array.isArray(arr) ? pyMin(arr) : arr),
  "time.time": () => Date.now() / 1000,
  "random.random": () => Math.random(),
  "os.getcwd": () => process.cwd(),
};

// The host Planes runs on under Node: the real filesystem, the real clock, a
// resolver over the targets the corpus names, and JSON.parse/stringify for the
// boundary. The JS analogue of PythonHost.
export class NodeHost extends Host {
  constructor() {
    super();
    this._resolved = {};
  }

  get name() {
    return "node";
  }

  ask(url) {
    // A synchronous GET, to match interp.py's synchronous ask. Node has no sync
    // fetch, so shell out to curl. This is the endpoint path — the tested path
    // is the stub host, exactly as host.py tests PythonHost.ask only via
    // TestHost, never live.
    try {
      return execFileSync("curl", ["-sSL", "-A", "planes/0.1", url], {
        encoding: "utf-8",
        timeout: 20000,
      });
    } catch (e) {
      throw new HostError(`ask failed: ${e.message}`);
    }
  }

  read(path) {
    try {
      return fs.readFileSync(path, "utf-8");
    } catch {
      throw new HostError(`no such file: ${path}`);
    }
  }

  write(path, text) {
    fs.writeFileSync(path, text);
  }

  show(text) {
    process.stdout.write(text + "\n");
  }

  clock() {
    return Date.now() / 1000;
  }

  resolve(target) {
    if (target in this._resolved) return this._resolved[target];
    if (target in NODE_TARGETS) {
      const fn = NODE_TARGETS[target];
      this._resolved[target] = fn;
      return fn;
    }
    if (!target.includes(".")) {
      throw new HostError(`bad target: ${target}`);
    }
    throw new HostError(`cannot find '${target}'`);
  }

  targetHint() {
    return "`module.function`, e.g. `builtins.sorted`";
  }

  parseJson(text) {
    return JSON.parse(text);
  }

  toJson(value) {
    return ensureAscii(JSON.stringify(value, null, 2));
  }
}

// A host with the outside world replaced — a host, not a mock, implementing the
// same eight methods, so the whole agreement suite is hermetic by construction.
// The JS analogue of host.py's TestHost: it stubs the five effects and inherits
// resolve / parseJson / toJson from NodeHost, exactly as TestHost inherits them
// from PythonHost.
export class TestHost extends NodeHost {
  constructor({ responses = {}, files = {}, now = 1000000.0 } = {}) {
    super();
    this.responses = responses;
    this.files = { ...files };
    this.now = now;
    this.shown = [];
    this.recorded = [];
  }

  get name() {
    return "test";
  }

  ask(url) {
    const r = this.responses;
    if (typeof r === "function") return r(url);
    if (Object.prototype.hasOwnProperty.call(r, url)) return r[url];
    throw new HostError(`no stubbed response for ${url}`);
  }

  read(path) {
    if (!Object.prototype.hasOwnProperty.call(this.files, path)) {
      throw new HostError(`no such file: ${path}`);
    }
    return this.files[path];
  }

  write(path, text) {
    this.files[path] = text;
  }

  show(text) {
    this.shown.push(text);
  }

  clock() {
    return this.now;
  }

  record(entry) {
    this.recorded.push(entry);
  }
}
