import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const wasmPath = new URL("../target/wasm32-unknown-unknown/release/planes_spike.wasm", import.meta.url);

async function loadWasm() {
  const bytes = await readFile(wasmPath);
  const { instance } = await WebAssembly.instantiate(bytes);
  return instance.exports;
}

function output(exports, packed) {
  const ptr = Number((packed >> 32n) & 0xffff_ffffn);
  const len = Number(packed & 0xffff_ffffn);
  return new TextDecoder().decode(new Uint8Array(exports.memory.buffer, ptr, len));
}

test("WebAssembly record workload agrees with the Rust native result", async () => {
  const exports = await loadWasm();
  assert.equal(output(exports, exports.planes_records(3, 3)), "total 18");
});

test("WebAssembly invoice workload reads exact CSV values and rounds at the end", async () => {
  const exports = await loadWasm();
  const bytes = new TextEncoder().encode("2,1234\n");
  new Uint8Array(exports.memory.buffer, exports.planes_input_ptr(), bytes.length).set(bytes);
  assert.equal(output(exports, exports.planes_invoice(bytes.length)), "due 26.65");
});

test("WebAssembly rejects malformed invoice input with a visible error", async () => {
  const exports = await loadWasm();
  const bytes = new TextEncoder().encode("not,csv,for,this,subset\n");
  new Uint8Array(exports.memory.buffer, exports.planes_input_ptr(), bytes.length).set(bytes);
  assert.match(output(exports, exports.planes_invoice(bytes.length)), /^error /);
});

test("WebAssembly rejects an invoice length larger than its input buffer", async () => {
  const exports = await loadWasm();
  const length = exports.planes_input_capacity() + 1;
  assert.equal(
    output(exports, exports.planes_invoice(length)),
    `error invoice input exceeds ${exports.planes_input_capacity()}-byte limit`,
  );
});
