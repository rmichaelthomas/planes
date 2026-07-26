// js/test/render.test.mjs — pure-JS unit tests for the renderer (Phase 3).
//
// Cross-implementation agreement against render.py lives in test_js_render.py.
// This file covers the two A.4 raises the CLI cannot reach — a node kind the
// parser never produces (Builtin) and a node that is neither a statement nor a
// renderable expression (Because) — plus astEqual's line-insensitivity.
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { loadGrammar } from "../loader_node.mjs";
import { parse } from "../parser.mjs";
import { renderExpr, renderStmt, render, astEqual } from "../render.mjs";
import { Builtin, Because } from "../nodes.mjs";

loadGrammar();

test("renderExpr raises a named error on the dead Builtin node (no fallback)", () => {
  assert.throws(
    () => renderExpr(Builtin("count", null)),
    /Builtin/,
    "must name Builtin, not fall through silently",
  );
});

test("renderStmt raises a named error on a node it cannot render (no fallback)", () => {
  assert.throws(
    () => renderStmt(Because("x", 1), "", new Map()),
    /Because/,
    "must name Because",
  );
});

test("a simple program round-trips", () => {
  const src = "to f of n:\n  give n + 1\n\nr = f of 2\n";
  const prog = parse(src);
  const prog2 = parse(render(prog));
  assert.equal(prog.length, prog2.length);
  assert.ok(prog.every((a, i) => astEqual(a, prog2[i])));
});

test("astEqual ignores line but not structure", () => {
  const a = parse("x = 1\n");
  const b = parse("\n\nx = 1\n"); // same AST, different line numbers
  assert.ok(astEqual(a[0], b[0]));
  const c = parse("x = 2\n");
  assert.ok(!astEqual(a[0], c[0]));
});
