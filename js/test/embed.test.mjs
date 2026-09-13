// js/test/embed.test.mjs — the embedding entry point, end to end.
//
// Imports ONLY "../embed.mjs" — no loader_node.mjs, no manual setVocabulary/
// setCore/setAmberTemplates anywhere in this file. That is the whole point:
// js/embed.mjs's grammar load is a side effect of the import itself, so a
// caller who does nothing but `import ... from "js/embed.mjs"` must never see
// `GrammarDataError: vocabulary not loaded` (the finding 5xFive's VENDOR.md
// records against four review rounds that missed exactly this). Node's test
// runner gives each test FILE its own process, so this file's untouched
// module graph is the honest "a fresh caller imports embed.mjs and nothing
// else" case, not an artifact of some earlier test in the same run having
// already loaded the grammar.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parse,
  analyse,
  asJson,
  check,
  diff,
  Interpreter,
  TestHost,
  PlanesError,
  PlanesSyntaxError,
  RuleNotSupported,
  fmt,
  toHost,
  PlanesNumber,
} from "../embed.mjs";

test("parse: no manual loading needed, and a syntax error still refuses cleanly", () => {
  const prog = parse('let x = 1\nshow x\n');
  assert.equal(prog.length, 2);
  assert.equal(prog[0].__node, "Assign");
  assert.equal(prog[1].__node, "Show");
  assert.throws(() => parse("let x = \n"), PlanesSyntaxError);
});

test("analyse: computes the effect surface without running the program", () => {
  const src = 'foreign fetch of u from "http.get" doing ask "https://example.com"\nshow fetch\n';
  const surface = analyse(src);
  const surfaceJson = asJson(surface, "inline.planes");
  assert.equal(surfaceJson.format, 1);
  assert.deepEqual(surfaceJson.boundaries.sort(), ["console", "network"]);
  assert.ok(
    surfaceJson.effects.some((e) => e.kind === "ask" && e.target === "https://example.com"),
  );
});

test("diff: reports a new destination between two versions of a program", () => {
  const before = analyse('foreign a of x from "http.get" doing ask "https://a.example"\n');
  const after = analyse('foreign a of x from "http.get" doing ask "https://b.example"\n');
  const d = diff(before, after);
  assert.equal(d.isEmpty(), false);
  assert.ok(d.newDestinations().some((e) => e.target === "https://b.example"));
});

test("check: flags a real forbid-rule violation and reports a vacuous rule separately", () => {
  const src = [
    'show "hi"',
    'let dest = "log.json"',
    'write "hi" to dest',
    "",
    'rule [no-console] anything may not show',
    '  because "smoke test"',
    "",
    // `dest` resolves (it origins the write effect above), but never appears
    // in an `ask` effect at all — the well-formed-but-never-triggers shape
    // `Violation#vacuous` reports, distinct from an ordinary non-match.
    'rule [dest-no-ask] dest may not ask',
    '  because "smoke test"',
    "",
  ].join("\n");
  const prog = parse(src);
  const rules = prog.filter((s) => s.__node === "Rule");
  const surface = analyse(src);
  const results = check(rules, surface, null);
  // `anything` never goes through resolveSubject (it always matches); `dest`
  // does, so only it shows up in the readback of resolved subjects.
  assert.deepEqual(results.resolvedSubjects, ["dest"]);
  const byName = Object.fromEntries(results.map((v) => [v.rule.name, v]));
  assert.equal(byName["no-console"].is_violation, true);
  assert.equal(byName["dest-no-ask"].vacuous, true);
  assert.equal(byName["dest-no-ask"].is_violation, false);
});

test("check: a rule whose subject cannot be resolved throws RuleNotSupported", () => {
  const src = 'show "hi"\nrule [bad] nonexistent-name may not show\n';
  const prog = parse(src);
  const rules = prog.filter((s) => s.__node === "Rule");
  assert.throws(() => check(rules, analyse(src), null), RuleNotSupported);
});

test("Interpreter + TestHost: runs a small program end to end with a stub host", () => {
  const host = new TestHost();
  const itp = new Interpreter({ host });
  const output = itp.run([
    'let doubled = 5 + 5',
    "show doubled",
  ].join("\n"));
  assert.deepEqual(output, ["10"]);
  assert.deepEqual(itp.output, ["10"]);
  const traced = itp.env.get("doubled");
  assert.ok(traced.value instanceof PlanesNumber);
  assert.equal(fmt(traced.value), "10");
  assert.equal(toHost(traced.value), 10);
});

test("Interpreter: a program error is a PlanesError naming a tag and a fix", () => {
  const itp = new Interpreter({ host: new TestHost() });
  assert.throws(() => itp.run('show y\n'), (e) => {
    assert.ok(e instanceof PlanesError);
    assert.equal(e.tag, "unknown-name");
    assert.match(e.message, /try:/);
    return true;
  });
});
