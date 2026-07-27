# SVG Renderer and Export Verification (§9.2)

Run at commit `c8eae2b`, on the branch, before merge.

**RETIRED.** `scripts/verify-svg-and-export.mjs` was deleted in the same PR
under `scripts/ci.sh`'s retirement rule — a build's verification script
graduates into a suite or goes, and this one graduated. Its checks now live in
suites `ci.sh` runs on every commit: coverage (A) and programs (C) in
`js/test/paint_examples.test.mjs`, conformance (B) in
`js/test/paint_conformance.test.mjs`, invariants (D) and the page's export
copy (E) in `js/test/drawing_invariants.test.mjs`, and the export mechanics
(E) in `js/test/paint_export.test.mjs`. This table is the record of the gate
having run, not something to re-run.

| Category | Check | Result | Detail |
|---|---|---|---|
| Coverage | every verb in VERBS is drawn by the corpus, or allowlisted with a reason | PASS |  |
| Coverage | the allowlist is empty (a gap named here is a gap the PR must justify) | PASS |  |
| Coverage | the corpus emits fractional alpha, which it never did before | PASS |  |
| Coverage | the whole path group is drawn, not only its easy members | PASS |  |
| Conformance | the all-verbs fixture is generated from VERBS, not a stale hand-list | PASS |  |
| Conformance | both renderers walk the all-verbs stream with no error and the same result | PASS |  |
| Conformance | both renderers report the same error tags, in the same order, in every case | PASS |  |
| Conformance | both renderers refuse an unsupported version identically and emit nothing | PASS |  |
| Conformance | both renderers resolve the same sRGB, including two out-of-gamut requests | PASS |  |
| Conformance | both renderers sweep the same arc, including wrap and full-circle cases | PASS |  |
| Programs | all three programs render through both renderers with zero errors | PASS |  |
| Programs | every <g> the corpus opens is closed, in every frame | PASS |  |
| Programs | the effect surfaces are unchanged: console; console; console and file:write state.json | PASS |  |
| Invariants | the stream walk exists once: no renderer carries its own copy | PASS |  |
| Invariants | oklchToRgb is defined once and imported, never reimplemented | PASS |  |
| Invariants | no CSS oklch() string appears in any renderer .mjs | PASS |  |
| Invariants | VERBS is unchanged from e205e14: twenty-six, exactly these | PASS |  |
| Invariants | the Host interface is still exactly seven methods, plus the two it always had | PASS |  |
| Invariants | grammar/vocabulary.json is unchanged: thirty-two keywords, ten builtins | PASS |  |
| Invariants | no Planes source emits a raw draw string except paint/draw.planes | PASS |  |
| Invariants | no CDN, npm package or runtime network dependency in paint.html | PASS |  |
| Export | the SVG a program produces parses as XML and its root is <svg> | PASS |  |
| Export | a PNG capture is written at twice the device pixel ratio and restores the canvas | PASS |  |
| Export | a data URL decodes to bytes of the type it declares | PASS |  |
| Export | MediaRecorder is constructed with a supported MIME type, or none at all | PASS |  |
| Export | the page states what each export means, under the buttons | PASS |  |

**26/26 checks passed.**

All checks passed, including the three blocking categories (A, B, D).

## Verb coverage, per program

| Program | Verbs drawn |
|---|---|
| turtle | `background` `cap` `clear` `ellipse` `fill` `line` `pop` `push` `rotate` `stroke` `translate` `width` |
| bloom | `arc` `background` `circle` `clear` `close` `corner` `curve` `end` `fill` `pop` `push` `rotate` `scale` `shape` `stroke` `translate` `vertex` `width` |
| snake | `align` `circle` `clear` `fill` `label` `line` `rect` `size` `stroke` `triangle` `width` |

All 26 verbs are drawn. The allowlist is empty.

Note: the per-tick benchmark regression (§9.1) is tracked separately in `reports/feat-corpus-refinement-svg-renderer-and-export-benchmarks-post.md`. It exceeds the 25% threshold and was explicitly accepted; it is not a check in this file.
