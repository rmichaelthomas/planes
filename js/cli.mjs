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

import fs from "node:fs";
import { NodeHost, HostError, Host } from "./host.mjs";
import { loadGrammar } from "./loader_node.mjs";
import { tokenize, PlanesSyntaxError } from "./lexer.mjs";
import { parse, PlanesAmbiguity } from "./parser.mjs";
import { canonicalProgram } from "./canonical.mjs";
import { PlanesNumber, Fraction, Inexact } from "./planes_num.mjs";
import {
  resolveStringEscapes,
  escapeStringLiteral,
  codePoints,
  codePointLength,
  StringEscapeError,
} from "./planes_text.mjs";

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

// Each op is a JSON array [name, ...args]; returns the text/canonical result,
// so the Python oracle can compare planes_num.py's answer string for string.
function numOp(op) {
  const [name, ...a] = op;
  switch (name) {
    case "parse":
      return PlanesNumber.parse(a[0]).text();
    case "of":
      return PlanesNumber.of(a[0]).text();
    case "add":
      return PlanesNumber.parse(a[0]).add(PlanesNumber.parse(a[1])).text();
    case "sub":
      return PlanesNumber.parse(a[0]).sub(PlanesNumber.parse(a[1])).text();
    case "mul":
      return PlanesNumber.parse(a[0]).mul(PlanesNumber.parse(a[1])).text();
    case "div":
      return PlanesNumber.parse(a[0]).div(PlanesNumber.parse(a[1])).text();
    case "round":
      return PlanesNumber.parse(a[0]).roundTo(Number(a[1])).text();
    case "frac":
      return new PlanesNumber(new Fraction(BigInt(a[0]), BigInt(a[1]))).text();
    case "cmp":
      return String(PlanesNumber.parse(a[0]).cmp(PlanesNumber.parse(a[1])));
    case "whole":
      return PlanesNumber.parse(a[0]).isWhole() ? "true" : "false";
    case "asint":
      try {
        return String(PlanesNumber.parse(a[0]).asInt());
      } catch {
        return "ERR";
      }
    case "harmonic": {
      // 1/1 + 1/2 + ... + 1/n, exact — the denominator-growth case.
      let acc = new PlanesNumber(new Fraction(0n));
      for (let k = 1; k <= Number(a[0]); k++) {
        acc = acc.add(new PlanesNumber(new Fraction(1n, BigInt(k))));
      }
      return acc.text();
    }
    case "inexact": {
      // A denominator past MAX_DENOMINATOR must refuse, not round.
      try {
        new PlanesNumber(new Fraction(1n, 2n ** 4001n))
          .add(PlanesNumber.of(0))
          .text();
        return "NO-REFUSAL";
      } catch (e) {
        return e instanceof Inexact ? "INEXACT" : "OTHER:" + e.message;
      }
    }
    default:
      throw new Error(`unknown num op: ${name}`);
  }
}

function textOp(op) {
  const [name, ...a] = op;
  switch (name) {
    case "resolve":
      return resolveStringEscapes(a[0]);
    case "escape":
      return escapeStringLiteral(a[0]);
    case "cplen":
      return String(codePointLength(a[0]));
    case "cps":
      return codePoints(a[0]);
    case "badresolve":
      try {
        resolveStringEscapes(a[0]);
        return "NO-ERROR";
      } catch (e) {
        return e instanceof StringEscapeError ? "BAD:" + e.badChar : "OTHER";
      }
    default:
      throw new Error(`unknown text op: ${name}`);
  }
}

switch (sub) {
  case "host":
    hostCmd(rest);
    break;
  case "num":
    out(JSON.stringify(JSON.parse(rest[0]).map(numOp)));
    break;
  case "text":
    out(JSON.stringify(JSON.parse(rest[0]).map(textOp)));
    break;
  case "tokens": {
    // The canonical token form: [kind, value, line] per token, matching
    // test_lexer_in_planes.py's (t.kind, t.value, t.line). On a syntax error,
    // emit a tagged marker the Python side compares against its own raise.
    loadGrammar();
    const src = fs.readFileSync(rest[0], "utf-8");
    try {
      const toks = tokenize(src);
      out(JSON.stringify(toks.map((t) => [t.kind, t.value, t.line])));
    } catch (e) {
      if (e instanceof PlanesSyntaxError) {
        out(JSON.stringify({ error: "PlanesSyntaxError", message: e.message }));
      } else throw e;
    }
    break;
  }
  case "ast": {
    // ast <file> [known-json]. `known-json` is the identical name->arity mapping
    // the Python harness computes (cross-file `use` resolution), so both parsers
    // see the same module context. Emits the canonical AST program form; a
    // syntax error or ambiguity emits a tagged marker to compare against.
    loadGrammar();
    const src = fs.readFileSync(rest[0], "utf-8");
    let known = null;
    if (rest[1] !== undefined && rest[1] !== "") {
      known = new Map(Object.entries(JSON.parse(rest[1])));
    }
    try {
      out(canonicalProgram(parse(src, known)));
    } catch (e) {
      if (e instanceof PlanesAmbiguity) {
        out(JSON.stringify({ error: "PlanesAmbiguity", message: e.message }));
      } else if (e instanceof PlanesSyntaxError) {
        out(JSON.stringify({ error: "PlanesSyntaxError", message: e.message }));
      } else throw e;
    }
    break;
  }
  default:
    process.stderr.write(`unknown subcommand: ${sub}\n`);
    process.exit(2);
}
