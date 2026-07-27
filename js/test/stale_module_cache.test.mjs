// js/test/stale_module_cache.test.mjs — a mixed module set says so.
//
// paint.html and index.html load about twenty-five same-origin ES modules with
// no versioning, because versioning them would need a build step this repo does
// not have. A browser is then free to serve some from cache and fetch others,
// and Safari keeps an instantiated module graph across a plain reload. That
// happened for real: `sine` landed in grammar/vocabulary.json and js/interp.mjs
// in one commit, and a browser holding the fresh JSON beside the cached
// interpreter reported
//
//   ✗ unknown-builtin: no builtin is named 'sine'
//     try: the ten builtins are fixed ...
//
// — blaming the interpreter, telling the reader to file a bug, and saying "ten"
// while the vocabulary beside it said eleven.
//
// The graph cannot be prevented from going stale without a build step. It can
// be made to SAY SO, and these are the tests for that.

import { test } from "node:test";
import assert from "node:assert/strict";
import { loadGrammar } from "../loader_node.mjs";

loadGrammar();

const { unimplementedBuiltins, staleModuleWarning } = await import("../browser_main.mjs");
const vocab = (await import("../../grammar/vocabulary.json", { with: { type: "json" } })).default;

test("a consistent module set reports nothing", () => {
  assert.deepEqual(unimplementedBuiltins(), []);
  assert.equal(staleModuleWarning(), null);
});

test("every builtin the vocabulary declares is one the interpreter implements", () => {
  // The invariant under the check, worth holding on its own: adding a name to
  // grammar/vocabulary.json without adding a case to js/interp.mjs is exactly
  // the half-landed state a stale cache imitates, and it would ship green
  // without this.
  assert.deepEqual(unimplementedBuiltins(), [], "vocabulary and interpreter have drifted apart");
  assert.ok(vocab.builtins.length >= 10, `only ${vocab.builtins.length} builtins declared`);
});

test("a builtin the interpreter has never heard of produces the warning, not a shrug", () => {
  // The real failure, reproduced: the vocabulary declares a name the loaded
  // interpreter does not implement. Restored afterwards whatever happens.
  const invented = { name: "cosine", arity: 1, note: "test scaffolding" };
  vocab.builtins.push(invented);
  try {
    const missing = unimplementedBuiltins();
    assert.deepEqual(missing, ["cosine"]);

    const warning = staleModuleWarning();
    assert.ok(warning, "a mixed module set must produce a warning");
    // The remedy comes first, because a reader who hits this wants to know
    // what to press — not what went wrong inside.
    assert.match(warning, /^This page is running a mix of old and new code/);
    assert.match(warning, /empty your browser's cache and reload/);
    assert.match(warning, /cosine/, "it names which builtin is missing");
    assert.match(warning, /Safari/, "and how, in the browser this actually bit");
    assert.match(warning, /Develop → Empty Caches/);
    assert.match(warning, /Shift/, "and in the others");
    // What it must NOT say: the old message blamed the interpreter and told
    // the reader to report it.
    assert.doesNotMatch(warning, /defect in the interpreter/);
    assert.doesNotMatch(warning, /worth reporting/);
  } finally {
    const i = vocab.builtins.indexOf(invented);
    if (i >= 0) vocab.builtins.splice(i, 1);
  }
});

test("an effectful builtin refusing for its own reasons is not mistaken for a missing one", () => {
  // `read` wants `use file` and `ask` wants a stubbed response; both refuse
  // under the probe. Neither refusal means the interpreter has never heard of
  // them, and a check that could not tell the difference would cry stale on
  // every load.
  assert.ok(vocab.builtins.some((b) => b.name === "read"));
  assert.ok(vocab.builtins.some((b) => b.name === "ask"));
  assert.deepEqual(unimplementedBuiltins(), []);
});

test("the probe is cheap enough to run on every page load", () => {
  const t0 = performance.now();
  for (let i = 0; i < 5; i++) unimplementedBuiltins();
  const each = (performance.now() - t0) / 5;
  assert.ok(each < 25, `${each.toFixed(1)}ms per check is too much for a page load`);
});
