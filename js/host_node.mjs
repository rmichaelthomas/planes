// js/host_node.mjs — the Node backend (real filesystem, clock, and resolver).
//
// The JS analogue of host.py's PythonHost: the real world under Node. Kept
// apart from host.mjs because it imports node:fs and node:child_process, which
// a browser cannot resolve; host.mjs (and interp.mjs) stay browser-safe.

import fs from "node:fs";
import { execFileSync } from "node:child_process";
import { Host, HostError, pyJsonDumps, sharedTargets, resolveWith } from "./host.mjs";

// The host Planes runs on under Node: the real filesystem, the real clock, a
// resolver over the targets the corpus names (os.getcwd -> process.cwd), and
// JSON.parse/stringify for the boundary.
export class NodeHost extends Host {
  constructor() {
    super();
    this._resolved = {};
    this._targets = sharedTargets(() => process.cwd());
  }
  get name() {
    return "node";
  }
  ask(url) {
    // A synchronous GET, to match interp.py's synchronous ask — the endpoint
    // path, not the tested one (agreement uses the in-memory host, as host.py
    // tests PythonHost.ask only via TestHost).
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
    return resolveWith(this._targets, this._resolved, target);
  }
  targetHint() {
    return "`module.function`, e.g. `builtins.sorted`";
  }
  parseJson(text) {
    return JSON.parse(text);
  }
}
