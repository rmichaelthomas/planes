// js/test/discarded_write.test.mjs — the discarded-write build, JS side.
//
// The cross-implementation agreement (Python, JavaScript, self-hosted) lives
// in test_discarded_write.py, which shells out to js/cli.mjs. This file
// covers what is cleanest to check JS-side directly: findDiscardedWrites
// (parser.mjs) against the same signature cases parser.py's own test module
// exercises, and Interpreter.run / checkDiscardedWrites actually refusing.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { loadGrammar } from "../loader_node.mjs";
import { parse, findDiscardedWrites } from "../parser.mjs";
import { Interpreter, PlanesError } from "../interp.mjs";
import { TestHost } from "../host.mjs";

await loadGrammar();

const HAZARD_SRC =
  "use file\n" +
  "let total = 0\n" +
  "for each order in [{ amount: 3 }, { amount: 4 }]:\n" +
  "  let total = total + order.amount\n" +
  'write total to "total.json"\n';

const FIXED_SRC =
  "use file\n" +
  "total = 0\n" +
  "for each order in [{ amount: 3 }, { amount: 4 }]:\n" +
  "  total = total + order.amount\n" +
  'write total to "total.json"\n';

test("the A-Q9 case is refused, naming the variable and the fix", () => {
  const h = new TestHost({ files: {} });
  assert.throws(
    () => new Interpreter({ host: h }).run(HAZARD_SRC),
    (e) => {
      assert.ok(e instanceof PlanesError);
      assert.equal(e.tag, "discarded-write");
      assert.match(e.detail, /'total'/);
      assert.match(e.fix, /let/);
      assert.match(e.fix, /bare assignment/);
      return true;
    },
  );
});

test("the corrected form writes the correct sum", () => {
  const h = new TestHost({ files: {} });
  new Interpreter({ host: h }).run(FIXED_SRC);
  assert.equal(JSON.parse(h.files["total.json"]), 7);
});

test("the check runs before any statement executes", () => {
  const src =
    "use file\n" +
    "let seen = 0\n" +
    "for each n in [1, 2, 3]:\n" +
    '  write "should never run" to "side-effect.json"\n' +
    "  let seen = seen + n\n";
  const h = new TestHost({ files: {} });
  assert.throws(() => new Interpreter({ host: h }).run(src), PlanesError);
  assert.deepEqual(h.files, {});
});

// ---- all four conditions required (mirrors parser.py's test_discarded_write.py)

test("condition 1: let outside a loop does not fire", () => {
  const prog = parse("let total = 0\nlet total = total + 1\n");
  assert.deepEqual(findDiscardedWrites(prog), []);
});

test("condition 2: bare assignment inside a loop does not fire", () => {
  const prog = parse(
    "total = 0\nfor each n in [1, 2, 3]:\n  total = total + n\n",
  );
  assert.deepEqual(findDiscardedWrites(prog), []);
});

test("condition 3: a let whose right-hand side does not self-read does not fire", () => {
  const prog = parse(
    "total = 0\nfor each n in [1, 2, 3]:\n  let total = n\n",
  );
  assert.deepEqual(findDiscardedWrites(prog), []);
});

test("condition 4: a genuinely new local with no enclosing binding does not fire", () => {
  const prog = parse("for each n in [1, 2, 3]:\n  let total = n\n");
  assert.deepEqual(findDiscardedWrites(prog), []);
});

test("all four together is what fires", () => {
  const prog = parse(
    "let total = 0\nfor each n in [1, 2, 3]:\n  let total = total + n\n",
  );
  assert.deepEqual(findDiscardedWrites(prog), ["total"]);
});

// ---- soundness: branches don't leak (this build's own self-review finding)

test("a binding in one if branch does not leak into its sibling", () => {
  const prog = parse(
    "if false:\n" +
      "  amt = 5\n" +
      "else:\n" +
      "  for each n in [1, 2, 3]:\n" +
      "    let amt = amt + n\n",
  );
  assert.deepEqual(findDiscardedWrites(prog), []);
});

test("a binding from a sibling statement in the same loop body still counts", () => {
  const prog = parse(
    "for each order in [1]:\n" +
      "  total = 0\n" +
      "  for each part in [1, 2]:\n" +
      "    let total = total + part\n",
  );
  assert.deepEqual(findDiscardedWrites(prog), ["total"]);
});

test("the hazard still fires through a nested if", () => {
  const prog = parse(
    "total = 0\n" +
      "for each n in [1, 2, 3]:\n" +
      "  if true:\n" +
      "    let total = total + n\n",
  );
  assert.deepEqual(findDiscardedWrites(prog), ["total"]);
});

// ---- no behaviour change

test("let still shadows locally when the hazard shape is not present", () => {
  const itp = new Interpreter({ host: new TestHost() });
  itp.run(
    "total = 0\n" +
      "for each n in [1, 2, 3]:\n" +
      "  let total = n\n" +
      "show text of total",
  );
  assert.deepEqual(itp.output, ["0"]);
});

test("bare assignment accumulation is completely unaffected", () => {
  const itp = new Interpreter({ host: new TestHost() });
  itp.run(
    "total = 0\n" +
      "for each n in [1, 2, 3, 4, 5]:\n" +
      "  total = total + n\n" +
      "show text of total",
  );
  assert.deepEqual(itp.output, ["15"]);
});
