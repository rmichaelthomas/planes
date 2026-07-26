// js/host.mjs — the host: whatever actually performs an effect (browser-safe).
//
// The JavaScript counterpart of host.py's abstract surface plus the in-memory
// hosts. This module imports nothing node-specific, so it — and everything that
// imports it, including interp.mjs — loads unchanged in a browser tab. The
// real-filesystem NodeHost lives in host_node.mjs; the browser VFS host in
// host_browser.mjs.
//
// host.py names seven required methods (each raises NotImplementedError
// there): ask, read, write, show, clock, resolve, parseJson. `record` is an
// optional no-op, not one of the seven.
//
// It was eight until C4 counted what the reference actually calls rather than
// what host.py declares. `toJson` had no caller anywhere: `interp.py`'s write
// effect uses a *module-level* to_json that unwraps the value model first, and
// the host method took an already-plain value, so it could not have served the
// one site that serialises even if something had reached for it.
// `test_host.py` checked the surface with `hasattr`, which is a declaration
// check and cannot tell a dead method from a live one.
//
// The seam claim is restated at seven, not spent: seven methods, not a
// rewrite. See REPORT_SECOND_HOST.md's seam verdict and REPORT_FAST_FOLLOW.md.

// The host could not do what was asked. Distinct from a program error.
export class HostError extends Error {
  constructor(message) {
    super(message);
    this.name = "HostError";
  }
}

// What a host must provide: five effect capabilities, foreign resolution, and a
// JSON boundary. A host that implements these runs Planes.
export class Host {
  get name() {
    return "abstract";
  }
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
  // The optional record plane — a no-op by default; a host that does nothing
  // here is still complete.
  record(_entry) {}
  resolve(_target) {
    throw new HostError("resolve: not implemented on the abstract host");
  }
  targetHint() {
    return "a name this host understands";
  }
  parseJson(_text) {
    throw new HostError("parseJson: not implemented on the abstract host");
  }
}

// json.dumps(..., indent=2) escapes non-ASCII (ensure_ascii=True); JSON
// .stringify does not. Escape every UTF-16 unit above 0x7e as \uXXXX so a
// written file is byte-identical to interp.py's; an astral char becomes a
// surrogate pair on both sides.
export function ensureAscii(s) {
  let out = "";
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c > 0x7e) out += "\\u" + c.toString(16).padStart(4, "0");
    else out += s[i];
  }
  return out;
}

// json.dumps(value, indent=2) with ensure_ascii — the write effect's
// serialisation, and the only one there is. `interp.mjs`'s module-level
// `toJson` unwraps a Planes value and hands the result here; `interp.py`'s
// does the same with `json.dumps(..., indent=2)`. C4: a `toJson` also sat on
// the host surface, wrapping this, and nothing ever called it.
export function pyJsonDumps(value) {
  return ensureAscii(JSON.stringify(value, null, 2));
}

// Python's sorted/max/min ordering over a homogeneous list — foreign.planes
// resolves builtins.sorted/max/min; these reproduce the default order so a
// resolved foreign agrees with interp.py's.
export function pyCompare(a, b) {
  if (typeof a === "number" && typeof b === "number") return a - b;
  if (typeof a === "string" && typeof b === "string") {
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

// The host-independent foreign targets the corpus resolves. The ambient
// os.getcwd is env-specific (process.cwd under Node, a VFS root in a browser),
// so each host supplies it; everything else is shared.
export function sharedTargets(getcwd) {
  return {
    "builtins.sorted": (arr) => pySorted(arr),
    "builtins.max": (arr) => (Array.isArray(arr) ? pyMax(arr) : arr),
    "builtins.min": (arr) => (Array.isArray(arr) ? pyMin(arr) : arr),
    "builtins.str": (x) => (typeof x === "string" ? x : String(x)),
    "time.time": () => Date.now() / 1000,
    "random.random": () => Math.random(),
    "os.getcwd": getcwd,
  };
}

// resolve() shared by every host: a cache, the target table, then the two
// refusals host.py makes — bad target (no dot) and not-found.
export function resolveWith(table, cache, target) {
  if (target in cache) return cache[target];
  if (target in table) {
    cache[target] = table[target];
    return table[target];
  }
  if (!target.includes(".")) throw new HostError(`bad target: ${target}`);
  throw new HostError(`cannot find '${target}'`);
}

// A host with the outside world replaced — an in-memory VFS for files, a
// responses map for ask, and Math.random/Date.now (or a fixed clock) — the
// browser-safe base for both TestHost (hermetic tests) and BrowserHost (the
// browser backend). The JS analogue of host.py's TestHost, minus any Python
// runtime.
export class MemoryHost extends Host {
  constructor({ responses = {}, files = {}, now = null, cwd = "/" } = {}) {
    super();
    this.responses = responses;
    this.files = { ...files };
    this.now = now;
    this.cwd = cwd;
    this.shown = [];
    this.recorded = [];
    this._resolved = {};
    this._targets = sharedTargets(() => this.cwd);
  }
  get name() {
    return "memory";
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
    return this.now !== null ? this.now : Date.now() / 1000;
  }
  record(entry) {
    this.recorded.push(entry);
  }
  resolve(target) {
    return resolveWith(this._targets, this._resolved, target);
  }
  targetHint() {
    return "`module.function`, e.g. `builtins.sorted`";
  }
  parseJson(text) {
    return JSON.parse(text);
  }
}

// The hermetic host the agreement suite uses — a MemoryHost with a fixed clock,
// so a clock-reading program is reproducible. host.py's TestHost by another
// route (in-memory, not a Python-runtime subclass).
export class TestHost extends MemoryHost {
  constructor({ responses = {}, files = {}, now = 1000000.0 } = {}) {
    super({ responses, files, now });
  }
  get name() {
    return "test";
  }
}
