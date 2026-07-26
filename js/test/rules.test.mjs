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
  const src =
    "use http\nrule [no-send] anything may not ask\n" +
    'rule [ok] anything may ask to "https://audit.internal" supersedes [no-send]\n' +
    'x = ask "https://audit.internal"\n';
  const v = check(rulesOf(src), analyse(src));
  assert.equal(v.length, 1);
  assert.equal(v[0].is_violation, false);
  assert.equal(v[0].cleared_by.name, "ok");
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
