# Vendored: PixiJS

Horizon Phase 1 (renderer pipeline). Design doc §10.1/§10.5, §26. The first
vendored third-party JavaScript dependency in this repo — no prior precedent
existed under `js/vendor/`, so this file establishes the pattern the design
doc's "recorded versions, licenses, upstream URLs, and integrity hashes"
requirement asks for.

## What's here

- `pixi.min.mjs` — PixiJS **v8.19.0**, the pre-bundled, minified, dependency-
  free **ES module** distribution. A single self-contained file: zero
  relative imports, zero dynamic `import()` calls, one `export{...}`
  statement at the end (verified below).
- `LICENSE` — PixiJS's own MIT license text, copied verbatim.

## Why this exact file, not the alternatives

The published package ships several browser-usable shapes under `dist/`.
This one was chosen deliberately:

| File | Why not |
|---|---|
| `dist/pixi.js` / `dist/pixi.min.js` | **Not an ES module.** Despite the `.js` extension these are classic global-exposing scripts (`var PIXI=(function(d){...})({})`) meant for a `<script>` tag, not `import`. This repo's engine code is `import`-based `.mjs` throughout (design doc §10.5); an `import` of either file resolves to a module with no exports. |
| `dist/pixi.mjs` (unminified ESM, 2,087,231 bytes) | Genuinely importable, but ~2.6x the vendored file's size for identical behavior — no reason to spend more of the §16 "first playable payload ≤ 6 MB compressed" budget than necessary. The unminified source remains fetchable upstream (URL below) if a future audit wants to read it un-minified; the integrity hash below lets that fetch be verified byte-for-byte against what's vendored here. |
| `dist/webworker.mjs` / `dist/webworker.min.mjs` | A *rendering*-in-a-worker build (OffscreenCanvas-oriented). This design keeps Pixi on the **main thread** (§11.2) — the Worker in this build is the *simulation* worker, not a render worker. Design doc §30 also notes OffscreenCanvas is deferred: "rendering remains on the main thread initially." |
| `dist/packages/*` (advanced-blend-modes, gif, html-source, math-extras, unsafe-eval) | Optional sub-features this build's placeholder scene never touches (compressed-texture transcoding, GIF decode, blend-mode extras, etc.). Not vendored; `pixi.min.mjs` never attempts to fetch them at runtime unless the corresponding API is actually called, and this build calls none of them. |

## Provenance

- **Package**: `pixi.js`
- **Version**: `8.19.0` (resolved from the npm registry's `latest` dist-tag
  on the vendoring date below; pinned here as an exact version, not a
  floating tag — future refresh is a deliberate maintainer operation per
  §10.5, not automatic).
- **License**: MIT. Copyright (c) 2013–2023 Mathew Groves, Chad Engler. Full
  text in `LICENSE`.
- **Upstream URL** (source of the vendored bytes):
  `https://unpkg.com/pixi.js@8.19.0/dist/pixi.min.mjs`
- **Registry record**: `https://registry.npmjs.org/pixi.js/8.19.0`
- **Vendored**: 2026-08-07
- **Integrity** (SHA-256):
  - hex: `28fefb52eeb15bb3e087533456bafc53e91af70932af4dd046ff2938ec3edd0e`
  - SRI (base64): `sha256-KP77Uu6xW7Pgh1M0Vrr8U+ka9wkyr03QRv8pOOw+3Q4=`
  - Independently confirmed against unpkg's own published package metadata
    (`https://unpkg.com/pixi.js@8.19.0/dist/?meta`) before vendoring — the
    integrity value above did not come only from hashing the download, it
    matched a hash unpkg computed and published separately.
- **Re-verify at any time**:
  ```sh
  curl -sS https://unpkg.com/pixi.js@8.19.0/dist/pixi.min.mjs | shasum -a 256
  # expect: 28fefb52eeb15bb3e087533456bafc53e91af70932af4dd046ff2938ec3edd0e
  ```

## No sourcemap vendored

`pixi.min.mjs` carries a trailing `//# sourceMappingURL=pixi.min.mjs.map`
comment. The map (~4.5 MB, larger than the bundle itself) is deliberately
not vendored: it maps back to TypeScript sources this package does not ship,
so it would not actually enable source-level debugging, only bloat the
vendor tree. A browser's devtools will 404 the map silently and harmlessly
if a developer has source maps enabled; functionality is unaffected.

## Renderer preference

Design doc §10.1: "production defaulting to stable WebGL. WebGPU remains
opt-in." PixiJS v8's `Application.init()` is called with an explicit
`preference: "webgl"` wherever this repo constructs one (see
`js/world/performers/pixi_performer.mjs`) — stated in source rather than
relied on as an unstated default, so a future PixiJS version changing its
own default can never silently flip this build onto WebGPU.

## No-build-step compliance (§10.5)

`pixi.min.mjs` is fetched by the browser exactly as authored — no npm
install, no CDN reference at runtime, no bundler, no transpilation.
`scripts/assemble_site.sh` discovers it automatically (`find js -name
'*.mjs' -not -path 'js/test/*'`); nothing needed to change there.
