# A Crossing — Planes-Directed Living Passage

**Date:** 2026-08-01  
**Status:** approved architecture, visual-first rebuild  
**Supersedes:** the presentation architecture in `2026-08-01-a-crossing-nine-landings-design.md`; its canon, semantic ownership, replay, and truthfulness requirements remain in force.

## Outcome

Rebuild `A Crossing` as a browser-native playable world in which Planes is the stage director rather than the sole pixel artist. The first screen is the crossing itself: a rich, full-viewport Ala Eriri passage with motion, weather, spatial sound, direct manipulation, and room to explore. Source, provenance, Shapes, replay details, and the Statement of Revision remain real but live in an optional secondary layer.

The proof becomes:

> Planes can author the truth and behavior of a high-fidelity living world while specialized browser renderers perform its visual, motion, and sonic intent.

## Decisions already approved

- The experience is visual-first and play-first.
- Planes owns world truth, decisions, conditions, progression, deterministic variation, explanation values, and revision records.
- A scene renderer owns composition, interpolation, shaders, asset placement, animation playback, camera presentation, and audio performance.
- JavaScript is a thin browser host, not a second rules engine and not the conceptual partner language.
- The host boundary is an agent-readable Scene IR so SVG, Canvas/WebGL, Web Audio, or a future game engine can consume the same intent.
- Garden already proves that Planes can be a visual language. This build proves that Planes can direct a richer visual system.
- The page/canvas is the world. Code and provenance never compete with it on arrival.
- The approved bright-Atlantic Ala Eriri direction and canonical corpus assets are the visual source of truth.

## Approaches considered

### 1. SVG-only stage

Render the complete world as a single declarative SVG scene graph. This offers excellent identity, accessibility, granular hit targets, masks, filters, and inspectability. It is the simplest durable host and a strong fallback, but it is expensive for dense water, particles, and full-screen post-processing.

### 2. Canvas/WebGL game surface

Render everything through Canvas 2D or WebGL. This offers the most headroom for particles, camera motion, water, and lighting, but it weakens semantic object identity and makes the canonical SVG assets and accessibility layer harder to preserve.

### 3. Hybrid living diorama — selected

Use an authored raster environment plate for painterly geographic richness, a semantic SVG scene graph for objects and interaction, a compact WebGL shader layer for water/light/weather, CSS/Web Animations for UI and camera transitions, and Web Audio for structured sound. Planes directs all layers through one Scene IR.

This is selected because it best matches the approved mockup, preserves granular object identity, reaches browser game quality without a framework rewrite, and creates a migration path to a future game engine.

## Experience design

### Arrival

The page opens directly into a 16:9 living passage. There is no conventional site header, right-hand dashboard, three-column lower region, or exposed source listing. The browser window reads as a game stage.

The opening camera looks from Reso across the channel toward Nkwo Eriri. The environment plate carries painterly terrain, architecture, markets, vegetation, cliffs, clouds, and atmospheric depth. Live layers add the hydrofoil, continuous ivory route cord, nine gold route beads, water response, weather, petrels, signal lights, and human-scale landing activity.

A small title appears once and recedes. The persistent HUD is limited to:

- Passage time and destination;
- the current resident need;
- sound and pause controls;
- one quiet invitation: `Choose a crossing`.

### Play loop

1. The player selects the resident's need: care, education, or work.
2. Planes evaluates seeded conditions across Passage, weather, energy, radio, and landing support.
3. The world presents available actions spatially, attached to real objects rather than in a detached control panel.
4. The player may launch, shelter, preserve reserve, route power, relay a signal, or inspect a system when Planes says that action is available.
5. The hydrofoil travels continuously along the Planes-selected route. The camera and soundscape respond without changing the semantic outcome.
6. A consequence appears in the world first: vessel movement, lights, water, route cord, landing activity, and time.
7. A compact Statement of Revision can be opened from the route cord or end-state ribbon.
8. The seed and ordered events can replay the same crossing.

The initial vertical slice remains Reso to Nkwo Eriri, but it must feel like one passage inside a larger navigable archipelago rather than an `Opening I` page. The map toggle reveals all nine landings and makes later expansion legible.

### Direct manipulation

Clickable subjects include the hydrofoil, route cord, nine route beads, Reso landing, market, kordas, fog capture, wave array, radio mast, clinic beacon, weather front, petrels, and the distant Nkwo Eriri landing.

Hover/focus reveals a restrained halo and a one-line verb. Selection opens a small in-world action ribbon. Explanations do not open unless the player chooses `Why?`.

Keyboard navigation follows spatial order through subjects. Touch targets are at least 44 CSS pixels even when the visible art is smaller.

## Visual direction

### Source assets

- The approved bright-Atlantic visual direction is the composition and tonal reference.
- The canonical flag, seal, archipelago map, and commemorative landing woodcut are extracted faithfully from the supplied Factbook and encyclopedia SVGs.
- The flag's indigo, ivory, and gold; continuous cord; central twist; and nine beads become functional scene language rather than decoration.
- No invented seal, flag, costume, religious symbol, script, or tone marking is permitted.

### Environment

The main plate is derived from the approved bright-Atlantic visual direction without embedded interface, labels, or source code. It preserves the Reso foreground, open channel, volcanic depth, Nkwo Eriri destination, contemporary infrastructure, and joyful populated-island tone.

The world should feel sunlit, salt-worn, lush, contemporary, and inhabited. It may be painterly, but not toy-like. Avoid primitive geometry as finished scenery, generic resort imagery, pirate motifs, dark medieval ports, glossy 3D plastic, or generic city-builder iconography.

### Signature visual moment

The signature moment is `The Cord Takes the Water`: after the player commits to a crossing, the ivory route cord writes itself across the sea, nine beads wake in sequence, the water shader gathers around the path, the hydrofoil lifts, and the camera eases into motion. This is one orchestrated event, not a pile of unrelated effects.

### Layer stack

1. **Environment plate:** painterly terrain, architecture, vegetation, cloud forms, and distant activity.
2. **Atmosphere shader:** water caustics, sun glint, swell displacement, cloud shadow, weather tint, and vignette; WebGL2 with a static CSS fallback.
3. **Semantic SVG world:** vessel, route, beads, infrastructure signals, birds, landing activity, selection halos, and all hit targets.
4. **Weather particles:** spray, mist, rain, or bright motes; Canvas/OffscreenCanvas where supported, disabled when unnecessary.
5. **HUD:** sparse, paper-and-graphite Planes controls, visually subordinate to the world.
6. **Archive drawer:** map, Statement of Revision, replay, source, trace, Shapes, and effect boundary.

## Planes Scene IR

Planes emits a line-oriented, versioned scene stream alongside existing state and sound output. The protocol is presentation intent, not semantic duplication.

```text
scene protocol 1
scene camera horizon 0.42 0.54 1.00
scene environment bright-passage afternoon rolu-grandi-3
scene subject hydrofoil asset hydrofoil-main 0.38 0.67 1 visible
scene route reso-nkwo 0.10 0.73 0.82 0.55 active
scene signal clinic-beacon 0.91 0.43 warm available
scene weather swell 3 southwest
scene cue crossing-commit
audio bed channel-day 0.34
audio cue bell-double 0.22
```

The normalized values are renderer-independent. The browser maps named assets and cues to visual/audio implementations. Unknown lines are ignored with a visible development warning; missing critical assets fall back to canonical SVG silhouettes.

The IR must be documented in JSON in `grammar/protocols/scene-v1.json` so an agent can discover it without reverse-engineering JavaScript. This documents a host protocol; it does not add a Planes keyword.

## Ownership boundary

### Planes owns

- seed-derived weather, resident need, sea state, available energy, radio state, route state, Passage minutes, and outcome;
- action availability and `when` dispatch;
- voyage progress as semantic state;
- subject visibility, enabled actions, active scene cue, and desired camera state;
- deterministic replay and Statement of Revision values;
- Scene IR, structured audio intent, existing draw fallback, and provenance-bearing output.

### Browser host owns

- loading and caching environment/scene assets;
- mapping Scene IR identifiers to assets and renderer nodes;
- interpolating between Planes states at 60 fps;
- water and lighting shaders;
- particle simulation whose seed and intensity come from Planes;
- camera easing and parallax;
- spatialized, layered audio performance after explicit opt-in;
- input capture, hit testing, responsive layout, reduced-motion presentation, and optional archive formatting.

The host must not choose a route, fabricate available actions, calculate Passage success, alter minutes, or write a competing world state.

## Concurrency model

Native Planes concurrency is not required for this build. Planes advances a deterministic semantic world in ordered steps. Between steps, browser subsystems run concurrently in their own domains:

- `requestAnimationFrame` interpolates camera and scene nodes;
- WebGL renders atmosphere;
- Web Audio schedules beds and cues;
- a Worker may update particles or decode assets;
- the main thread handles input and semantic scene commits.

This separates simultaneous presentation from concurrent language semantics. Future Planes actors/tasks may be useful for independently evolving world agents, but they are not required to make the current world move, sound, or feel alive.

## Structured audio

The current repeating high sine notes are removed. Audio starts only after explicit opt-in and consists of restrained layers:

- broad-band filtered surf and wind beds at low gain;
- hydrofoil motor/foil wash shaped from noise, not a continuous piercing oscillator;
- low, short ogene-inspired double-bell cues for accepted actions;
- muted hand-drum pulse for route commitment and arrival;
- spatial radio clicks and landing signals;
- the supplied pronunciation recording as an explicit archive artifact only.

Planes chooses cue identifiers, intensity, location, and timing class. The host performs synthesis and mixing. Default master gain is conservative, all cues use envelopes, and no continuous oscillator is audible without a filter and gain envelope.

## Secondary archive layer

The archive opens from one discreet control or the route cord's `Why?` action. It is a full-screen translucent paper drawer over a paused or softly moving world, with tabs for:

- Revision;
- Nine Landings map and voyage replay;
- Why / provenance;
- Planes source;
- Shapes and effect boundary.

The default tab is Revision. Source is never rendered on initial load. Closing the archive returns focus to the selected world object.

## Performance strategy

### Budgets

- 60 fps target on a current laptop; never below 50 fps during the signature moment.
- 30 fps graceful tier on a mid-range mobile device.
- Planes semantic step median under 12 ms and p95 under 24 ms for the active crossing.
- Main-thread visual frame median under 12 ms and p95 under 18 ms.
- Initial critical visual payload under 3.5 MB compressed; optional atlas/archive assets lazy-loaded.
- No layout shift from scene or HUD loading.

### Techniques

- Planes runs at semantic cadence, initially 8 Hz; rendering interpolates at display cadence.
- Environment plate is responsive AVIF/WebP with a PNG fallback.
- SVG nodes are stable and updated by transforms/attributes rather than recreated each frame.
- Shader complexity scales by device capability and reduced-motion preference.
- Particles run only when visible and pause when the page is hidden.
- The archive, provenance graph, source, and pronunciation audio load on demand.
- All timings are measured before and after; effects are reduced based on measured bottlenecks.

## Accessibility and resilience

- The world has a semantic object list even though it appears visually as a scene.
- All actions are keyboard accessible and announced with state, consequence, and Passage time.
- Reduced motion preserves a beautiful still plate, discrete state changes, and route progression without parallax, particle drift, camera travel, or continuous swell.
- Sound has visible state, a conservative default, and complete visual equivalents.
- High-contrast mode retains route, focus, and text legibility.
- WebGL failure produces the same scene with SVG/CSS atmosphere.
- Asset failure produces a designed fallback, never an empty black canvas.

## Verification

### Semantic

- Fixed seed and event fixtures reproduce world state, Scene IR, sound intent, output, trace, effects, errors, and Statement of Revision.
- Every action displayed by the host exists in Planes output for that state.
- Every outcome is calculated by Planes.
- Selection and archive inspection do not alter the semantic crossing.

### Visual and interaction

- At first viewport, at least 80% of the visible area is the living world.
- No source listing or multi-panel dashboard is visible at arrival.
- The opening view visually matches the approved bright-Atlantic direction in composition, color, density, and maturity.
- The signature route commitment visibly coordinates cord, beads, water, vessel, camera, and sound.
- At least twelve subjects are independently hoverable, focusable, and selectable.
- Care, education, and work produce distinct Planes-owned crossing conditions.
- The atlas reveals all nine canonical islands.

### Quality gates

- Browser iteration includes desktop, narrow/mobile, reduced-motion, muted, WebGL-disabled, and keyboard-only captures.
- Console remains free of errors and unhandled promise rejections.
- Scene and audio protocol parsers reject malformed critical records and ignore unknown optional records.
- The full existing repository test gate remains green.

## Deliberate limits of this vertical slice

This build does not become a fully streamed 3D open world, networked multiplayer game, real civic service, or all-island agent simulation. It creates a game-quality browser diorama with one deep crossing, a navigable nine-island atlas, and architecture that can expand without changing the Planes/director boundary.
