// js/module_loader_node.mjs — the Node module loader (real filesystem).
//
// Supplies modules.mjs's four host-bound operations — locate, read, key,
// label — over node:fs / node:path, reproducing today's behaviour exactly:
// a module path resolves relative to the importing file's own directory (or
// process.cwd() when there is none), existence is checked synchronously, and
// a missing module raises the same ModuleError modules.mjs has always raised.
// Not a Host method (js/host.mjs's seven-method interface is unrelated and
// stays closed) — the precedent is js/loader_node.mjs, a host-specific loader
// that sits beside the Host interface rather than inside it.

import fs from "node:fs";
import path from "node:path";
import { missingModuleError } from "./modules.mjs";

export function createNodeModuleLoader({ base = null } = {}) {
  return {
    locate(name, fromLocation) {
      const directory = fromLocation
        ? path.dirname(path.resolve(fromLocation))
        : base
          ? path.dirname(path.resolve(base))
          : process.cwd();
      const candidate = path.join(directory, `${name}.planes`);
      if (fs.existsSync(candidate)) return candidate;
      throw missingModuleError(name);
    },
    read(location) {
      return fs.readFileSync(location, "utf-8");
    },
    key(location) {
      return path.resolve(location);
    },
    label(location) {
      return path.basename(location);
    },
  };
}
