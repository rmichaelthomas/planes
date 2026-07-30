# Protocol v2 verification

Run at 2026-07-30T18:18:04.944Z, by `scripts/verify-protocol-v2.mjs`, which
this build wrote, ran once, and then deleted — per the retirement rule
(`scripts/ci.sh`, enforced by `test_gate.py`'s
`test_no_verification_script_exists_for_the_gate_not_to_run`): a build's
verification script is not product code, and a kept one is a stale assertion
waiting to mislead. Its durable checks graduated into the permanent suite
before the script was removed:

- **A** (v1 invariance against the committed `benchmarks/protocol-v2-pre/`
  baseline) → `js/test/protocol_v2.test.mjs`
- **B** (gradient stops), **C** (shadow parity) → their own dedicated files,
  `js/test/gradient_stops.test.mjs` and `js/test/shadow_parity.test.mjs`
- **D** (blend with/without shadow, structural) → folded into
  `js/test/protocol_v2.test.mjs`'s existing blend tests
- **E** (rotation against hand-computed geometry), **F** (library
  correspondence) → `js/test/protocol_v2.test.mjs`
- **G** (garden.planes purity) → `js/test/protocol_v2.test.mjs`
- **H** (language untouched) is intrinsically a one-time, this-PR-against-
  `main` comparison — not a standing invariant a future PR should be held
  to — so it was run directly (`git diff --stat main -- grammar/`,
  `git diff main -- planes-drawing-protocol-v1.md`, both empty) and is not
  graduated into a suite.

Graduating A, E and G's `Math.cos`/`Math.sin` hand-computation into
`js/test/protocol_v2.test.mjs` required adding that file to
`test_exactness.py`'s `GEOMETRY_ONLY` allowlist (renderer-side geometry
verification, the same reason `paint_conformance.test.mjs` and
`paint_svg.test.mjs` are already there) — found and fixed by running the
full gate after graduating, alongside one `ruff` line-length fix. Neither
affects the table below, which reflects the script's own run, before either
was found.

| Check | What | Status | Blocks |
|---|---|---|---|
| A | v1 invariance (SVG + canvas trace byte-identical) | PASS | unconditionally |
| B | gradient stops (16, identical to both sinks, shorter arc, dedup) | PASS | unless Rob accepts |
| C | shadow parity (one cast; scale 1:4 ratio; SVG matches canvas at scale 1) | PASS | unless Rob accepts |
| D | blend with/without an active shadow (report only, never blocks) | REPORT | never (report) |
| E | rotation (ellipse + rect, both sinks, against hand-computed geometry) | PASS | unless Rob accepts |
| F | library correspondence (one draw.planes helper per live VERBS entry) | PASS | unconditionally |
| G | purity (garden.planes at tick N: fresh == after visiting 0..N) | PASS | unconditionally |
| H | language untouched (grammar/ empty diff; v1.md unmodified) | PASS | unconditionally |

## Detail

### A — v1 invariance (SVG + canvas trace byte-identical)

**PASS**

raw text differs only at the §9.3 call sites: turtle, snake-tick-0, snake-tick-1, snake-tick-5, snake-tick-10, snake-tick-12-gameover

### B — gradient stops (16, identical to both sinks, shorter arc, dedup)

**PASS**

(nothing further)

### C — shadow parity (one cast; scale 1:4 ratio; SVG matches canvas at scale 1)

**PASS**

(nothing further)

### D — blend with/without an active shadow (report only, never blocks)

**REPORT**

without shadow: canvas=lighter true, svg mix-blend-mode present true -> agrees | with shadow: canvas composite op is still "lighter" at the one compositing drawImage call, svg's element carries both filter and mix-blend-mode -> agrees | NOTE: this environment has no rasterizer, so agreement above is STRUCTURAL (both renderers apply both effects to the one operation/element representing the mark) — not verified pixel-for-pixel. Rob's visual check (paint.html, garden, fireflies at night) is the pixel-level confirmation.

### E — rotation (ellipse + rect, both sinks, against hand-computed geometry)

**PASS**

(nothing further)

### F — library correspondence (one draw.planes helper per live VERBS entry)

**PASS**

(nothing further)

### G — purity (garden.planes at tick N: fresh == after visiting 0..N)

**PASS**

tick 137, 577 lines, identical either way

### H — language untouched (grammar/ empty diff; v1.md unmodified)

**PASS**

(nothing further)
