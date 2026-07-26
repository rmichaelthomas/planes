// js/sha256.mjs — SHA-256, in pure synchronous JavaScript.
//
// rules.py fingerprints a rule with `hashlib.sha256(canonical.encode())
// .hexdigest()[:6]`, and a fingerprint appears in Planes source (the FINGERPRINT
// token the lexer recognizes). A fingerprint that differs by one byte between
// implementations makes source written by one invalid under the other — so this
// must be byte-identical to hashlib, for arbitrary UTF-8 input.
//
// Synchronous by ruling (A.2): crypto.subtle.digest is async, and making it the
// fingerprint path would colour `async` up through rules.js and every caller
// that checks a rule. This is the algorithm itself, ~90 lines, colouring
// nothing. Verified against hashlib across empty, ASCII, multi-byte UTF-8, and
// block-boundary inputs (test_js_hash.py).
//
// No imports: TextEncoder is a global in Node and every modern browser, so this
// module is browser-safe (A.7) and pulls in nothing Node-only.

// The first 32 bits of the fractional parts of the cube roots of the first 64
// primes — the SHA-256 round constants, verbatim from FIPS 180-4.
const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

// A 32-bit right rotation. `>>> 0` keeps the result an unsigned 32-bit int.
function rotr(x, n) {
  return ((x >>> n) | (x << (32 - n))) >>> 0;
}

// SHA-256 of a byte sequence, as the 64-character lowercase hex digest hashlib
// produces. Accepts a JS string (encoded as UTF-8, matching Python's
// str.encode()) or a Uint8Array of raw bytes.
export function sha256Hex(input) {
  const bytes =
    typeof input === "string" ? new TextEncoder().encode(input) : input;

  // ---- preprocessing: append 0x80, pad to 56 mod 64, append the 64-bit
  // big-endian bit length.
  const bitLen = bytes.length * 8;
  const withOne = bytes.length + 1;
  const padded = new Uint8Array(Math.ceil((withOne + 8) / 64) * 64);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  // The message length in bits, big-endian, in the final 8 bytes. bitLen can
  // exceed 32 bits for large inputs, so split via BigInt to stay exact.
  const big = BigInt(bitLen);
  for (let i = 0; i < 8; i++) {
    padded[padded.length - 1 - i] = Number((big >> BigInt(8 * i)) & 0xffn);
  }

  // ---- initial hash values: fractional parts of the square roots of the
  // first 8 primes.
  let h0 = 0x6a09e667,
    h1 = 0xbb67ae85,
    h2 = 0x3c6ef372,
    h3 = 0xa54ff53a,
    h4 = 0x510e527f,
    h5 = 0x9b05688c,
    h6 = 0x1f83d9ab,
    h7 = 0x5be0cd19;

  const w = new Uint32Array(64);

  for (let chunk = 0; chunk < padded.length; chunk += 64) {
    // The 16 big-endian words of this 64-byte block, then the message schedule.
    for (let i = 0; i < 16; i++) {
      const j = chunk + i * 4;
      w[i] =
        ((padded[j] << 24) |
          (padded[j + 1] << 16) |
          (padded[j + 2] << 8) |
          padded[j + 3]) >>>
        0;
    }
    for (let i = 16; i < 64; i++) {
      const s0 =
        (rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3)) >>> 0;
      const s1 =
        (rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10)) >>> 0;
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }

    let a = h0,
      b = h1,
      c = h2,
      d = h3,
      e = h4,
      f = h5,
      g = h6,
      h = h7;

    for (let i = 0; i < 64; i++) {
      const S1 = (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) >>> 0;
      const ch = ((e & f) ^ (~e & g)) >>> 0;
      const temp1 = (h + S1 + ch + K[i] + w[i]) >>> 0;
      const S0 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) >>> 0;
      const maj = ((a & b) ^ (a & c) ^ (b & c)) >>> 0;
      const temp2 = (S0 + maj) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }

    h0 = (h0 + a) >>> 0;
    h1 = (h1 + b) >>> 0;
    h2 = (h2 + c) >>> 0;
    h3 = (h3 + d) >>> 0;
    h4 = (h4 + e) >>> 0;
    h5 = (h5 + f) >>> 0;
    h6 = (h6 + g) >>> 0;
    h7 = (h7 + h) >>> 0;
  }

  const hex = (x) => x.toString(16).padStart(8, "0");
  return hex(h0) + hex(h1) + hex(h2) + hex(h3) + hex(h4) + hex(h5) + hex(h6) + hex(h7);
}
