// js/test/hash.test.mjs — pure-JS unit tests for the SHA-256 (Phase 1).
//
// The byte-identity check against hashlib lives in test_js_hash.py. This file
// covers the JS side directly: the empty-string anchor, that the digest is 64
// lowercase hex characters, and that it is deterministic and synchronous (the
// return value is a string, never a Promise — A.2's whole point).
//
// Run: node --test js/test/

import { test } from "node:test";
import assert from "node:assert/strict";
import { sha256Hex } from "../sha256.mjs";

test("empty input matches the known SHA-256 of the empty string", () => {
  assert.equal(
    sha256Hex(""),
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  );
});

test("the digest is 64 lowercase hex characters", () => {
  for (const s of ["a", "abc", "café", "😀", "x".repeat(1000)]) {
    assert.match(sha256Hex(s), /^[0-9a-f]{64}$/, s);
  }
});

test("the abc anchor is correct", () => {
  assert.equal(
    sha256Hex("abc"),
    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
  );
});

test("the result is synchronous — a string, not a Promise", () => {
  const r = sha256Hex("anything\x1fforbid\x1fask\x1f");
  assert.equal(typeof r, "string");
  assert.ok(!(r instanceof Promise));
});

test("a Uint8Array of raw bytes hashes the same as its UTF-8 string", () => {
  const s = "https://example.com/ünïcode.json";
  const bytes = new TextEncoder().encode(s);
  assert.equal(sha256Hex(bytes), sha256Hex(s));
});
