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
import { HostError, Host } from "./host.mjs";
import { NodeHost } from "./host_node.mjs";
import { loadGrammar } from "./loader_node.mjs";
import { tokenize, PlanesSyntaxError } from "./lexer.mjs";
import { parse, PlanesAmbiguity } from "./parser.mjs";
import { canonicalProgram } from "./canonical.mjs";
import { Interpreter, PlanesError, lit } from "./interp.mjs";
import { TestHost } from "./host.mjs";
import { sha256Hex } from "./sha256.mjs";
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

function hostCmd(argv, host) {
  const op = argv[0];
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
    hostCmd(rest, new NodeHost());
    break;
  case "host-browser": {
    const { BrowserHost } = await import("./host_browser.mjs");
    hostCmd(rest, new BrowserHost());
    break;
  }
  case "num":
    out(JSON.stringify(JSON.parse(rest[0]).map(numOp)));
    break;
  case "text":
    out(JSON.stringify(JSON.parse(rest[0]).map(textOp)));
    break;
  case "hash": {
    // hash <json-array-of-strings> — the full 64-char SHA-256 hex digest of
    // each string's UTF-8 bytes, for byte-identity against hashlib (A.2).
    out(JSON.stringify(JSON.parse(rest[0]).map((s) => sha256Hex(s))));
    break;
  }
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
  case "run": {
    // run <file> [hostconfig-json]. Runs a whole program and reports the show
    // output, the terminal error tag, the effect log, and (with a TestHost) the
    // files written — the shape run_corpus_through_planes.py compares, plus
    // effects/files for effect agreement. A parse failure reports tag "PARSE".
    loadGrammar();
    const src = fs.readFileSync(rest[0], "utf-8");
    // A TestHost captures show (into itp.output) instead of printing, so the
    // program's output cannot pollute this command's JSON on stdout. Effect
    // tests pass responses/files; a bare run gets an empty one.
    const cfg =
      rest[1] !== undefined && rest[1] !== "" ? JSON.parse(rest[1]) : {};
    const host = new TestHost({
      responses: cfg.responses ?? {},
      files: cfg.files ?? {},
      now: cfg.now ?? 1000000.0,
    });
    const itp = new Interpreter({ host });
    let tag = null;
    // C2: the rendered message too, not only the tag. Asserting that a runtime
    // message is identical in both implementations needs the text, and the tag
    // is deliberately the same across many different messages.
    let message = null;
    try {
      itp.run(src);
    } catch (e) {
      if (e instanceof PlanesError) tag = e.tag;
      else if (e instanceof PlanesSyntaxError) tag = "PARSE";
      else if (e instanceof RangeError) tag = "recursion-too-deep";
      else throw e;
      message = String(e.message);
    }
    out(
      JSON.stringify({
        output: itp.output,
        tag,
        message,
        effects: itp.effects,
        files: itp.host.files ?? {},
      }),
    );
    break;
  }
  case "run-file": {
    // run-file <file> [hostconfig-json]. Like run, but resolves the module
    // graph (use X -> sibling X.planes) via run_file.mjs, the port of
    // interp.py's run_file. Node-only.
    loadGrammar();
    const cfg =
      rest[1] !== undefined && rest[1] !== "" ? JSON.parse(rest[1]) : {};
    const host = new TestHost({
      responses: cfg.responses ?? {},
      files: cfg.files ?? {},
      now: cfg.now ?? 1000000.0,
    });
    const itp = new Interpreter({ host });
    const { runFile } = await import("./run_file.mjs");
    let tag = null;
    try {
      runFile(itp, rest[0]);
    } catch (e) {
      if (e instanceof PlanesError) tag = e.tag;
      else if (e instanceof PlanesSyntaxError) tag = "PARSE";
      else if (e instanceof RangeError) tag = "recursion-too-deep";
      else if (e && e.name === "ModuleError") tag = "module-error";
      else throw e;
    }
    out(
      JSON.stringify({
        output: itp.output,
        tag,
        effects: itp.effects,
        files: itp.host.files ?? {},
      }),
    );
    break;
  }
  case "render": {
    // render <file> — canonical source, byte-for-byte against render.py.
    loadGrammar();
    const { render } = await import("./render.mjs");
    const src = fs.readFileSync(rest[0], "utf-8");
    out(render(parse(src)));
    break;
  }
  case "render-rules": {
    // render-rules <file> — canonical source with the generated rule markers,
    // like shapes_cli.py --render: single-file, unfollowed, so a rule subject
    // resolves against a surface whose nodes all carry file=null.
    loadGrammar();
    const { render } = await import("./render.mjs");
    const { analyse } = await import("./shapes.mjs");
    const src = fs.readFileSync(rest[0], "utf-8");
    const prog = parse(src);
    const found = prog.filter((s) => s.__node === "Rule");
    out(found.length ? render(prog, found, analyse(src)) : render(prog));
    break;
  }
  case "roundtrip": {
    // roundtrip <file> — parse -> render -> reparse -> astEqual, and the set of
    // AST node kinds the program contains (A.4 per-kind coverage). JS-side.
    loadGrammar();
    const { render, astEqual } = await import("./render.mjs");
    const src = fs.readFileSync(rest[0], "utf-8");
    const prog = parse(src);
    let ok;
    let reparseFailed = false;
    try {
      const prog2 = parse(render(prog));
      ok =
        prog.length === prog2.length &&
        prog.every((a, i) => astEqual(a, prog2[i]));
    } catch (e) {
      // render.py has a construct it renders but cannot reparse (a multi-arg
      // call as a record-field value); the JS port reproduces that exactly, so
      // a reparse failure is a reported result, not a crash.
      if (e instanceof PlanesSyntaxError) {
        ok = false;
        reparseFailed = true;
      } else throw e;
    }
    const kinds = new Set();
    const walk = (v) => {
      if (v && typeof v === "object" && "__node" in v) {
        kinds.add(v.__node);
        for (const k of Object.keys(v)) if (k !== "__node") walk(v[k]);
      } else if (v && v.items !== undefined && Array.isArray(v.items)) {
        for (const x of v.items) walk(x); // Tup
      } else if (Array.isArray(v)) {
        for (const x of v) walk(x);
      }
    };
    for (const s of prog) walk(s);
    out(JSON.stringify({ ok, reparseFailed, kinds: [...kinds].sort() }));
    break;
  }
  case "render-batch": {
    // render-batch <json-array-of-sources> — for each source: {parsed, rendered,
    // ok} where ok is parse -> render -> reparse -> astEqual. One call for the
    // composition generator's many tiny programs (S6, A.3), instead of a node
    // process per case.
    loadGrammar();
    const { render, astEqual } = await import("./render.mjs");
    const srcs = JSON.parse(rest[0]);
    const results = srcs.map((src) => {
      let prog;
      try {
        prog = parse(src);
      } catch (e) {
        if (e instanceof PlanesSyntaxError || e instanceof PlanesAmbiguity) {
          return { parsed: false };
        }
        throw e;
      }
      const rendered = render(prog);
      let ok = false;
      try {
        const p2 = parse(rendered);
        ok = prog.length === p2.length && prog.every((a, i) => astEqual(a, p2[i]));
      } catch (e) {
        if (!(e instanceof PlanesSyntaxError || e instanceof PlanesAmbiguity)) throw e;
        ok = false;
      }
      return { parsed: true, rendered, ok };
    });
    out(JSON.stringify(results));
    break;
  }
  case "astequal": {
    // astequal <fileA> <fileB> — whether parse(A) and parse(B) are astEqual
    // (line-insensitive). Drives the cross-implementation round-trip: Python
    // renders, JS reparses, and this checks it against JS's parse of the source.
    // A parse failure is reported, not thrown, so the caller can assert JS
    // reproduces render.py's non-reparseable output.
    loadGrammar();
    const { astEqual } = await import("./render.mjs");
    try {
      const a = parse(fs.readFileSync(rest[0], "utf-8"));
      const b = parse(fs.readFileSync(rest[1], "utf-8"));
      const equal =
        a.length === b.length && a.every((x, i) => astEqual(x, b[i]));
      out(JSON.stringify({ equal, parseFailed: false }));
    } catch (e) {
      if (e instanceof PlanesSyntaxError) {
        out(JSON.stringify({ equal: false, parseFailed: true }));
      } else throw e;
    }
    break;
  }
  case "shapes": {
    // shapes <file> [--no-follow] — the published effect surface (as_json),
    // the effect-surface oracle against shapes_cli.as_json.
    loadGrammar();
    const { asJson } = await import("./shapes.mjs");
    const { analyseFile } = await import("./shapes_node.mjs");
    const follow = !rest.includes("--no-follow");
    const surface = analyseFile(rest[0], follow);
    out(JSON.stringify(asJson(surface, rest[0])));
    break;
  }
  case "shapes-fn": {
    // shapes-fn <file> [--no-follow] — the per-function effect breakdown.
    loadGrammar();
    const { functionsBreakdown } = await import("./shapes.mjs");
    const { analyseFile } = await import("./shapes_node.mjs");
    const follow = !rest.includes("--no-follow");
    out(JSON.stringify(functionsBreakdown(analyseFile(rest[0], follow))));
    break;
  }
  case "shapes-deriv": {
    // shapes-deriv <file> — the derivation + origins form, computed from this
    // file's own source with analyse(src) (file=null), so derivation `file`
    // fields are null on both sides and only structure is compared.
    loadGrammar();
    const { analyse, derivationForm } = await import("./shapes.mjs");
    const src = fs.readFileSync(rest[0], "utf-8");
    out(JSON.stringify(derivationForm(analyse(src))));
    break;
  }
  case "rules":
  case "rules-src": {
    // rules <file>      — shapes_cli.py --rules: surface via analyseFile(follow),
    //                     check with declaringFile = abspath(file).
    // rules-src <file>  — rule_violations(src): surface via analyse(src)
    //                     (file=null), check with declaringFile=null.
    // Both emit each violation's render text + is_violation + vacuous, the
    // resolved subjects, and the exit category — or {error, message} on a
    // conflict / unsupported subject. The rule-results oracle (A.3).
    loadGrammar();
    const { check, RuleConflict, RuleNotSupported } = await import("./rules.mjs");
    const src = fs.readFileSync(rest[0], "utf-8");
    const found = parse(src).filter((s) => s.__node === "Rule");
    let surface;
    let declaringFile = null;
    if (sub === "rules") {
      const pathmod = await import("node:path");
      const { analyseFile } = await import("./shapes_node.mjs");
      surface = analyseFile(rest[0], true);
      declaringFile = pathmod.resolve(rest[0]);
    } else {
      const { analyse } = await import("./shapes.mjs");
      surface = analyse(src);
    }
    try {
      const results = check(found, surface, declaringFile);
      out(
        JSON.stringify({
          violations: results.map((v) => ({
            render: v.render(),
            is_violation: v.is_violation,
            vacuous: v.vacuous,
          })),
          resolved_subjects: results.resolvedSubjects,
          exit: results.some((v) => v.is_violation)
            ? 1
            : results.some((v) => v.vacuous)
              ? 2
              : 0,
        }),
      );
    } catch (e) {
      if (e instanceof RuleConflict) {
        out(JSON.stringify({ error: "RuleConflict", message: e.message }));
      } else if (e instanceof RuleNotSupported) {
        out(JSON.stringify({ error: "RuleNotSupported", message: e.message }));
      } else throw e;
    }
    break;
  }
  case "fingerprints": {
    // fingerprints <file> — [name, fingerprint] per rule, for byte-identity
    // against rules.py's fingerprint() (which the FINGERPRINT token embeds).
    loadGrammar();
    const { fingerprint } = await import("./rules.mjs");
    const found = parse(fs.readFileSync(rest[0], "utf-8")).filter(
      (s) => s.__node === "Rule",
    );
    out(JSON.stringify(found.map((r) => [r.name, fingerprint(r)])));
    break;
  }
  case "meta": {
    // meta <stage> <corpusfile...> — the metacircular conformance run (A.1):
    // load grammar/<stage>.planes into a JS Interpreter (a Planes
    // implementation running on the JavaScript one) and process each corpus
    // file with it. stage in {lex, parse, run}. One grammar load amortised over
    // all files. Emits a JSON array of per-file results (or {error: tag}).
    loadGrammar();
    const { runFile } = await import("./run_file.mjs");
    const stage = rest[0];
    const files = rest.slice(1);
    const stageFile = {
      lex: "grammar/lexer.planes",
      parse: "grammar/parser.planes",
      run: "grammar/interp.planes",
      json: "grammar/json.planes",
    }[stage];
    const stageItp = new Interpreter({ host: new TestHost() });
    runFile(stageItp, stageFile);

    const num = (v) => (v instanceof PlanesNumber ? Number(v.asInt()) : v);
    const results = [];
    for (const f of files) {
      const src = fs.readFileSync(f, "utf-8");
      // Each file runs on a fresh outer host so show output does not bleed
      // across files, but reuses the loaded stage definitions.
      stageItp.host = new TestHost();
      stageItp.output = [];
      stageItp.effects = [];
      try {
        if (stage === "lex") {
          const r = stageItp.call("tokenize", [lit(src)], stageItp.env);
          results.push(r.value.map((m) => [m.get("kind"), m.get("text"), num(m.get("line"))]));
        } else if (stage === "parse") {
          const r = stageItp.call("canonical-of-program-source", [lit(src)], stageItp.env);
          results.push(r.value);
        } else if (stage === "run") {
          const r = stageItp.call("execute-program", [lit(src)], stageItp.env);
          const status = r.value.get("status");
          let tag = null;
          if (status === "fail") {
            const err = r.value.get("error");
            tag = err && err.get ? err.get("tag") : String(err);
          }
          results.push({ output: stageItp.host.shown, tag });
        } else if (stage === "json") {
          // grammar/json.planes: read the file as JSON and write it straight
          // back out. Reader and writer in one call, so the emitted text is a
          // canonical form both implementations must agree on byte for byte —
          // and a refusal (an escape Planes cannot spell) must agree too.
          const r = stageItp.call("json-parse", [lit(src, "<json source>")], stageItp.env);
          if (!r.value.get("ok")) {
            results.push({ ok: false, detail: r.value.get("detail"), text: null });
          } else {
            const w = stageItp.call(
              "json-text-of",
              [lit(r.value.get("value"), "<json value>")],
              stageItp.env,
            );
            results.push({ ok: true, detail: "", text: w.value });
          }
        } else {
          throw new Error(`unknown meta stage: ${stage}`);
        }
      } catch (e) {
        if (e instanceof PlanesError) results.push({ error: e.tag });
        else if (e instanceof RangeError) results.push({ error: "recursion-too-deep" });
        else if (e instanceof PlanesSyntaxError) results.push({ error: "PARSE" });
        else throw e;
      }
    }
    out(JSON.stringify(results));
    break;
  }
  default:
    process.stderr.write(`unknown subcommand: ${sub}\n`);
    process.exit(2);
}
