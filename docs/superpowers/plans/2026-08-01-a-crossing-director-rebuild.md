# A Crossing Director Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard-like A Crossing page with a visual-first, game-quality browser diorama directed by Planes through a documented Scene IR.

**Architecture:** Planes remains the only semantic world model and emits state, Scene IR, structured audio intent, replay data, and provenance. A thin browser host maps that intent onto an environment plate, stable semantic SVG scene graph, WebGL/CSS atmosphere, purposeful animation, and conservative Web Audio mix. Source and explanation move into a lazy archive drawer.

**Tech Stack:** Planes, native ES modules, SVG, Canvas/WebGL2 with CSS fallback, Web Animations API, Web Audio API, Node built-in tests, Python unittest, in-app browser automation.

## Global Constraints

- Work only in `/private/tmp/planes-a-crossing` on `codex/a-crossing-nine-landings`.
- Follow `docs/superpowers/specs/2026-08-01-a-crossing-director-design.md`.
- Preserve the existing deterministic Planes ownership boundary; JavaScript must not calculate routes, Passage outcomes, availability, minutes, or revisions.
- Use the approved bright-Atlantic visual direction and canonical corpus artwork as source assets.
- Do not expose source, provenance, Shapes, or effect analysis on initial load.
- Sound is off by default, starts only after a gesture, uses conservative gain, and contains no continuous high unfiltered oscillator.
- WebGL, sound, motion, and generated image enhancements must have designed fallbacks.
- Use TDD for parser, state, renderer, audio, and interaction behavior. Generated bitmap production itself is treated as an asset-production exception and must be visually inspected.
- Do not commit, push, merge, or alter the shared main worktree.

---

## File map

| Path | Responsibility |
|---|---|
| `grammar/protocols/scene-v1.json` | Agent-readable Scene IR vocabulary, records, validation, and fallback semantics. |
| `js/scene/ir.mjs` | Parse and validate Planes-emitted scene/audio intent without making world decisions. |
| `js/scene/a_crossing_stage.mjs` | Stable SVG world, environment plate, atmosphere, interpolation, hit targets, and camera. |
| `js/scene/a_crossing_audio.mjs` | Structured surf, wind, foil, bell, drum, and radio mixer. |
| `js/scene/a_crossing_archive.mjs` | Lazy Revision / Atlas / Why / Source / Shapes archive presentation. |
| `paint/a_crossing.planes` | Semantic crossing, action availability, progress, scene intent, audio intent, revision, and replay state. |
| `assets/a-crossing/ala-eriri-symbols.svg` | Canonical flag, seal, map, and landing woodcut symbols extracted from supplied renders. |
| `assets/a-crossing/passage-environment.webp` | Source-anchored painterly environment plate without embedded UI. |
| `assets/a-crossing/passage-environment.png` | Compatibility fallback for the environment plate. |
| `a-crossing.html` | Full-viewport playable stage and minimal HUD. |
| `js/test/a_crossing_scene_ir.test.mjs` | Scene IR parser/validation tests. |
| `js/test/a_crossing_stage.test.mjs` | Renderer-state, action-surface, and fallback tests. |
| `js/test/a_crossing_audio.test.mjs` | Cue scheduling, gain, and oscillator-safety tests. |
| `js/test/a_crossing_page.test.mjs` | Visual-first structure, archive disclosure, accessibility, and ownership checks. |
| `js/test/a_crossing_scene.test.mjs` | Planes semantic, replay, Scene IR, and action-availability fixtures. |
| `benchmarks/a_crossing_director.md` | Before/after semantic, parsing, rendering, load, and frame measurements. |
| `reports/a_crossing_build_record_v2_0_director.md` | Architecture, visual production, verification, and future expansion record. |

## Task 1: Define the Scene IR boundary

**Files:** Create `grammar/protocols/scene-v1.json`, `js/scene/ir.mjs`, and `js/test/a_crossing_scene_ir.test.mjs`.

**Interfaces:** `parseSceneIntent(lines: string[]) -> { protocol, camera, environment, subjects, routes, signals, weather, actions, cues, audio, warnings }`. `SceneIntentError` identifies malformed critical protocol records.

- [ ] **Step 1: Write failing parser tests.** Hand-author literal Planes output covering camera, environment, subject, route, signal, weather, action, visual cue, audio bed, and audio cue. Name the breaks: a missing parser, acceptance of a malformed critical camera record, and failure to preserve unknown optional records as warnings.
- [ ] **Step 2: Run `node --test js/test/a_crossing_scene_ir.test.mjs`.** Expected: failure because `js/scene/ir.mjs` does not exist.
- [ ] **Step 3: Implement the smallest strict parser.** Parse normalized numbers, known enumerations, asset identifiers, states, and action records. Throw only for malformed protocol/camera/environment records; warn and continue for unknown optional records.
- [ ] **Step 4: Add `scene-v1.json`.** Describe every record, field type, normalized coordinate rule, ownership rule, unknown-record behavior, and fallback. Keep it valid JSON and host-protocol-only.
- [ ] **Step 5: Run the focused test and `python3 -m json.tool grammar/protocols/scene-v1.json`.** Expected: all parser tests pass and JSON validation exits 0.

## Task 2: Make Planes direct the living crossing

**Files:** Modify `paint/a_crossing.planes`, `js/test/a_crossing_scene.test.mjs`, and `test_a_crossing_in_planes.py`.

**Interfaces:** Planes emits `scene protocol 1`, one camera, one environment, subjects, route, signals, weather, available actions, cue, audio bed/cues, existing status/atlas/decision lines, and next state fields `need`, `progress`, `phase`, `actions`, and `cue`.

- [ ] **Step 1: Add failing JS and Python fixtures.** Assert literal initial state values for need, phase, and progress; assert care/education/work selection changes only through Planes events; assert action records match Planes state; assert fixed seed/event replay reproduces Scene IR exactly.
- [ ] **Step 2: Run `node --test js/test/a_crossing_scene.test.mjs` and `python3 -m unittest test_a_crossing_in_planes.py`.** Expected: new assertions fail because the state and IR are absent.
- [ ] **Step 3: Extend Planes state and `when` dispatch.** Add `need` events, spatial actions, commit/depart progression, arrival, shelter, reserve, clinic power, and relay. Keep a compact record and deterministic seed math.
- [ ] **Step 4: Emit Scene IR from Planes-owned values.** Scene asset IDs, normalized positions, action availability, desired camera, visual cue, and audio intent must derive from the current state and event.
- [ ] **Step 5: Preserve existing draw output as a designed fallback.** Simplify it if needed, but keep it semantically derived and replay-equivalent.
- [ ] **Step 6: Re-run both suites.** Expected: semantic, IR, action, and replay fixtures pass in both interpreters.

## Task 3: Produce source-anchored visual assets

**Files:** Create `assets/a-crossing/ala-eriri-symbols.svg`, `assets/a-crossing/passage-environment.webp`, and `assets/a-crossing/passage-environment.png`.

**Interfaces:** SVG exposes symbols `ala-flag`, `ala-seal`, `ala-map`, and `ala-landing-woodcut`. Environment plate is 16:9, contains no interface or legible labels, and leaves the open channel clear for live route/vessel overlays.

- [ ] **Step 1: Extract canonical SVG paths and text.** Copy the flag, seal, map, and woodcut geometry faithfully from the supplied Factbook/encyclopedia files into one local symbol sheet; do not redesign them.
- [ ] **Step 2: Generate one clean environment plate from the approved bright-Atlantic direction.** Use the existing visual-direction image as the reference. Remove all UI, embedded code, route cord, hydrofoil, labels, and badges while preserving composition, cultural tone, inhabited detail, infrastructure, and open-water perspective.
- [ ] **Step 3: Inspect the generated plate at full size.** Reject any dark medieval tone, resort genericity, toy geometry, invented symbols, text artifacts, or missing channel space. Make one targeted correction if needed.
- [ ] **Step 4: Save project assets.** Keep a high-quality PNG source and a WebP delivery asset in the isolated worktree.
- [ ] **Step 5: Validate dimensions and loadability.** Use image metadata and an SVG parse to confirm valid files and expected aspect ratio.

## Task 4: Build the hybrid stage renderer

**Files:** Create `js/scene/a_crossing_stage.mjs` and `js/test/a_crossing_stage.test.mjs`.

**Interfaces:** `createCrossingStage({ root, reducedMotion, webgl })` returns `{ apply(intent, semanticState), select(id), resize(), pause(), resume(), destroy(), metrics() }`.

- [ ] **Step 1: Write failing renderer contract tests using a real DOM fixture supported by the repository test environment.** Name the breaks: recreation of stable subjects, host-invented actions, missing critical-asset fallback, selection without a semantic subject, and motion continuing while paused.
- [ ] **Step 2: Run the focused test.** Expected: failure because the renderer module does not exist.
- [ ] **Step 3: Build a stable semantic SVG scene.** Create route, beads, hydrofoil, landing activity, signals, birds, halos, and 44px transparent hit targets once; update only Planes-directed attributes and transforms.
- [ ] **Step 4: Add frame interpolation.** Interpolate semantic progress and camera intent with `requestAnimationFrame`; never extrapolate an outcome or action.
- [ ] **Step 5: Add atmosphere.** Implement a compact WebGL2 water/light overlay with device-tier scaling and CSS/SVG fallback. Pause when hidden or reduced-motion.
- [ ] **Step 6: Add the signature choreography.** Coordinate the cord write, bead wake, foil lift, camera ease, and cue event from a single Planes `crossing-commit` cue.
- [ ] **Step 7: Re-run focused tests and profile a synthetic 10-second scene.** Expected: contract tests pass; median frame work remains within the plan budget in the reference browser.

## Task 5: Replace tones with structured audio

**Files:** Create `js/scene/a_crossing_audio.mjs` and `js/test/a_crossing_audio.test.mjs`; modify `paint/a_crossing.planes` only if a missing intent field is exposed by tests.

**Interfaces:** `createCrossingAudio({ contextFactory })` returns `{ unlock(), apply(audioIntent), setMuted(boolean), stop(), diagnostics() }`.

- [ ] **Step 1: Write failing tests.** Assert sound cannot start before unlock, master gain never exceeds `0.38`, continuous beds use filtered noise/buffers rather than bare oscillators, cues have finite envelopes, and duplicate semantic ticks do not retrigger cues.
- [ ] **Step 2: Run `node --test js/test/a_crossing_audio.test.mjs`.** Expected: failure because the module does not exist.
- [ ] **Step 3: Implement the conservative mixer.** Add surf/wind filtered-noise beds, foil wash, ogene-inspired double bell, muted hand-drum pulse, and radio click. Spatialize only where supported and always ramp gain.
- [ ] **Step 4: Map only Planes-emitted identifiers.** Unknown audio IDs produce diagnostics and silence.
- [ ] **Step 5: Re-run focused tests.** Expected: all safety, unlock, envelope, and deduplication tests pass.

## Task 6: Rebuild the page around play

**Files:** Replace `a-crossing.html`; modify `js/test/a_crossing_page.test.mjs`.

**Interfaces:** The page loads source once, steps Planes at semantic cadence, parses Scene IR, applies it to stage/audio/archive, returns user events to Planes, and exposes `window.__crossingMetrics` for measurement.

- [ ] **Step 1: Replace the old structure assertions with failing behavioral page tests.** Assert a full-viewport stage, sparse HUD, hidden archive, need choice, spatial action ribbon, sound opt-in, pause, seed/replay control, accessible subject list, and absence of initial source/dashboard panels. Assert no route/outcome algorithm exists in page JavaScript.
- [ ] **Step 2: Run `node --test js/test/a_crossing_page.test.mjs`.** Expected: failures against the current dashboard page.
- [ ] **Step 3: Implement the visual-first shell.** Make the stage fill the viewport; use a cinematic loading veil, receding title, minimal Passage HUD, need chooser, contextual action ribbon, and one archive control.
- [ ] **Step 4: Wire semantic cadence and input.** Parse only completed Planes results; queue user events; interpolate presentation between them; do not run Planes on every visual frame.
- [ ] **Step 5: Add responsive and reduced-motion adaptations.** Mobile uses a bottom action ribbon and map sheet while preserving all actions and subject access.
- [ ] **Step 6: Re-run page and focused scene suites.** Expected: all pass with no ownership-boundary regression.

## Task 7: Move explanation into the archive

**Files:** Create `js/scene/a_crossing_archive.mjs`; modify `a-crossing.html`, `js/test/a_crossing_stage.test.mjs`, and `js/test/a_crossing_page.test.mjs`.

**Interfaces:** `createCrossingArchive({ root, loadSource, loadSurface })` returns `{ open(tab, selection), close(), update(result, subjects, events), destroy() }` and lazy-loads source/Shapes only when their tabs are opened.

- [ ] **Step 1: Add failing tests.** Assert the archive defaults to Revision, source and surface are not loaded at page start, Why uses a real selected trace node, the atlas contains all nine canonical landings, and closing restores focus.
- [ ] **Step 2: Run focused tests.** Expected: failure because archive behavior does not exist.
- [ ] **Step 3: Implement the paper archive drawer.** Add Revision, Map/Replay, Why, Source, and Shapes tabs with focus trapping, Escape close, and selection restoration.
- [ ] **Step 4: Build the nine-island atlas from canonical SVG plus Planes-emitted active-route state.** The host may highlight; it may not choose route state.
- [ ] **Step 5: Re-run focused tests.** Expected: lazy loading, provenance, atlas, and focus behavior pass.

## Task 8: Browser iteration, optimization, and durable record

**Files:** Modify visual/runtime files as evidence requires; create `benchmarks/a_crossing_director.md` and `reports/a_crossing_build_record_v2_0_director.md`.

**Interfaces:** The benchmark records environment, payloads, Planes timing, IR parse, frame work, long tasks, and interaction latency. The build record explains asset provenance, ownership, fallbacks, decisions, and expansion seams.

- [ ] **Step 1: Serve the isolated worktree and capture the baseline.** Record the current page screenshot and metrics before replacement.
- [ ] **Step 2: Iterate visually in the browser.** Check desktop arrival, commitment choreography, mid-crossing, selection, archive, arrival, mobile, reduced motion, muted, keyboard-only, and WebGL fallback. Fix observed composition, clipping, hierarchy, interaction, and console issues.
- [ ] **Step 3: Measure before/after performance.** Capture load payload, LCP/CLS/INP indicators available locally, Planes median/p95, Scene IR parse, frame work, long tasks, and archive open cost. Reduce the demonstrated largest bottleneck first.
- [ ] **Step 4: Run focused suites.** Run all A Crossing JS and Python tests plus JSON validation.
- [ ] **Step 5: Run the full repository gate.** Use the repository CI command and confirm exit 0.
- [ ] **Step 6: Write the v2 build record.** Include screenshots/asset paths, Scene IR contract, audio design, measured budgets, accessibility behavior, known limits, and expansion sequence.
- [ ] **Step 7: Re-read the approved design line by line.** Record any unmet requirement explicitly; do not claim completion while a required item is absent.
