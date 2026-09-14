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
import { check, fingerprint, RuleConflict, RuleNotSupported } from "../rules.mjs";

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
