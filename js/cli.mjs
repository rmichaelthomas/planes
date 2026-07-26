// js/cli.mjs — the command-line front door to the JavaScript implementation.
//
// The Python-side agreement tests (test_js_*.py) shell out to this and compare
// its output, string for string, against lexer.py / parser.py / interp.py /
// host.py. It grows one subcommand per phase. A.3's oracle is canonical-form
// agreement, and this is where the JS side emits its canonical form.
//
// Usage:
//   node js/cli.mjs host <op> [args...]     — probe a NodeHost method
//
// Later phases add: tokens, ast, run.

import { NodeHost, HostError, Host } from "./host.mjs";

const [, , sub, ...rest] = process.argv;

function out(s) {
  process.stdout.write(s);
}

function hostCmd(argv) {
  const op = argv[0];
  const host = new NodeHost();
  switch (op) {
    case "methods": {
      // The eight methods a host must provide, as seen on the prototype.
      const required = [
        "ask",
        "read",
        "write",
        "show",
        "clock",
        "resolve",
        "parseJson",
        "toJson",
      ];
      const present = required.filter(
        (m) => typeof Host.prototype[m] === "function",
      );
      out(JSON.stringify(present));
      return;
    }
    case "to_json": {
      const value = JSON.parse(argv[1]);
      out(host.toJson(value));
      return;
    }
    case "parse_json": {
      const parsed = host.parseJson(argv[1]);
      out(JSON.stringify(parsed));
      return;
    }
    case "resolve": {
      const target = argv[1];
      const args = JSON.parse(argv[2] ?? "[]");
      const fn = host.resolve(target);
      out(JSON.stringify(fn(...args)));
      return;
    }
    case "resolve_bad": {
      const target = argv[1];
      try {
        host.resolve(target);
        out("RESOLVED");
      } catch (e) {
        if (e instanceof HostError) out("HOSTERROR:" + e.message);
        else throw e;
      }
      return;
    }
    case "read": {
      try {
        out(host.read(argv[1]));
      } catch (e) {
        if (e instanceof HostError) out("HOSTERROR:" + e.message);
        else throw e;
      }
      return;
    }
    case "write": {
      host.write(argv[1], argv[2]);
      out("ok");
      return;
    }
    case "clock": {
      out(String(host.clock()));
      return;
    }
    case "record": {
      // The optional record plane is a no-op on NodeHost; it must not throw.
      host.record({ any: "entry" });
      out("ok");
      return;
    }
    default:
      throw new Error(`unknown host op: ${op}`);
  }
}

switch (sub) {
  case "host":
    hostCmd(rest);
    break;
  default:
    process.stderr.write(`unknown subcommand: ${sub}\n`);
    process.exit(2);
}
