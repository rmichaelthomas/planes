# A Crossing / Nine Landings — director rebuild record v2.0

Date: 2026-08-01  
Branch: `codex/a-crossing-nine-landings`  
Isolated worktree: `/private/tmp/planes-a-crossing`

## Outcome

Version 2 turns A Crossing into a visual-first, browser-game-like diorama of
the Ala Eriri Passage. Planes is the authoritative stage director. It decides
state, available actions, voyage progress, camera intent, weather, cues,
revision language, and structured audio intent. The browser performs those
directions with a painterly environment plate, stable semantic SVG objects,
WebGL atmosphere, CSS choreography, and Web Audio.

The visible surface is play. Code, provenance, the nine-landing atlas, replay,
and the static effect surface remain available in an optional archive rather
than occupying the main composition.

## Why v1 was rebuilt

The first implementation asked Planes' drawing protocol to paint the entire
world. That was useful proof that Planes can be a visual language, as Garden
had already demonstrated, but it imposed three costs on this project:

- the scene regressed to primitive shapes below the approved visual mockup;
- source/provenance framing displaced the play surface;
- a continuous oscillator-like mix was uncomfortable and did not behave as
  environmental sound.

The rebuild does not retreat from Planes. It gives Planes the higher-level job:
authoring an inspectable, replayable scene contract while specialized browser
performers execute image composition, interpolation, shader work, and sound.

## Approved product direction

- Title: **A Crossing**, within **Nine Landings**.
- Opening: **Horizon**.
- Route: Reso to Nkwo Eriri across the fictional Ala Eriri Passage.
- Tone: bright contemporary Atlantic/Caribbean island life—cheerful, inhabited,
  technologically capable, and culturally specific to the supplied corpus.
- Form: open-ended visual sandbox with movement, granular inspectability,
  deterministic variation, choices, sound, and replay.
- Primary surface: the country and the crossing, not an IDE or provenance demo.
- Secondary surface: an archive opened only when requested.

## Authoritative boundary

The invariant for future work is:

> Planes decides what the world means and what may happen. The browser decides
> how those instructions are composed, interpolated, and performed.

`paint/a_crossing.planes` emits Scene Intent Protocol v1:

- `scene camera` — normalized framing intent;
- `scene environment` and `scene weather` — plate/light/weather identity;
- `scene subject` — stable semantic identity, asset, normalized position,
  visibility, and state;
- `scene route` and `scene signal` — crossing progress and infrastructure;
- `scene action` — the exact current player affordances and transport events;
- `scene cue` — finite visual events with serials;
- `audio bed` and `audio cue` — bounded structured sound intent.

The JSON contract is `grammar/protocols/scene-v1.json`. JavaScript must not
invent route outcomes, conditions, or available actions. It may map a known
asset identifier to a performer and adapt normalized camera intent to a
viewport.

Native Planes concurrency is not required for this architecture. Semantic
steps remain ordered and deterministic. The compositor, shader frame loop,
CSS transitions, and audio graph perform concurrently between those steps.

## Visual composition

The stage uses four coordinated layers:

1. A generated painterly environment plate establishes the complete Reso–Nkwo
   Eriri channel, inhabited terraces, working waterfront, contemporary island
   infrastructure, cloud light, and turquoise Passage.
2. A stable SVG scene graph supplies the electric hydrofoil, route cord,
   landing hit regions, wave array, radio relay, care beacon, petrels, and
   selection affordance.
3. A low-power WebGL2 overlay adds extremely subtle moving water atmosphere;
   it has a silent fallback and is removed under reduced motion.
4. Sparse editorial HUD and controls sit above the world. Their paper, type,
   coral, indigo, sea, and gold treatments inherit Planes/Garden identity
   without forcing Garden's page layout onto this experience.

The canonical Ala Eriri flag, seal, map, and landing woodcut were extracted
from the supplied country corpus into a valid SVG symbol sheet. They are used
in the archive and remain available for later landings.

### Generated image assets

- `passage-environment.png` is the high-resolution master environment.
- `passage-environment.webp` is the primary browser delivery asset;
  `passage-environment.jpg` is the compact fallback.
- `hydrofoil.png` is the transparent high-resolution master sprite.
- `hydrofoil.webp` is the 720-pixel transparent delivery sprite. If it cannot
  load, the SVG hydrofoil fallback remains visible.

The environment prompt brief asked for a clean, text-free, UI-free bright
Ala Eriri Passage plate derived from the approved mockup: contemporary
Caribbean/Atlantic terraces and ports on both shores, turquoise working
channel, cloud-lit central mountain, dense inhabited detail, and no vessel or
route overlay. The hydrofoil prompt brief asked for a high-detail contemporary
electric passenger hydrofoil in the same painterly world, broadside three-
quarter view, on a removable chroma field with no text or scenery.

## Play loop

1. The ready horizon asks who needs to cross: care, education, or work.
2. Planes enters planning and emits the route, reserve, power, and relay
   choices available in that state.
3. Launching starts a 160-tick crossing. Planes advances normalized progress,
   camera intent, state, and finite departure/arrival cues.
4. The compositor interpolates the boat, route cord, wake, and camera between
   semantic ticks. Desktop holds the full horizon; portrait converts the same
   Planes camera intent into a smooth pan from Reso to Nkwo Eriri.
5. Arrival resolves entirely from Planes state. A fixed seed and ordered event
   list replay identically.

Every visible semantic object is keyboard-focusable and clickable. Selection
opens a small in-world card. “Why?” opens the archive directly to the traced
Scene IR origin.

## Secondary archive

The archive contains:

- **Revision** — the Planes-authored statement and run identity;
- **Nine Landings** — canonical map plus ordered event replay;
- **Why** — selected Scene IR value origin, nearest author annotation, and
  exact Planes source line;
- **Planes** — source loaded only when requested;
- **Surface** — static effect analysis loaded only when requested.

Source and surface are lazy so the play surface does not pay their presentation
cost or foreground implementation details.

## Structured audio

Audio starts locked and muted. Explicit user action creates the audio graph.
The continuous bed contains only filtered, spatialized noise layers: surf,
wind, and hydrofoil wash. Finite bounded cues provide departure drum, landing
bell, and radio click. Cue serials prevent an eight-Hz semantic loop from
retriggering the same event. The master gain is capped at 0.32 and no bare
continuous oscillator exists.

## Important defects found during the rebuild

### Replaced controls at eight Hz

The first hybrid pass rebuilt action-button HTML on every semantic tick. A
pointer could press one node and release over its replacement, preventing the
browser from emitting `click`. Action surfaces now have stable signatures and
are reconciled only when Planes changes their semantics.

### Provenance still pointed at the legacy painter

The first archive adapter indexed old `subject` drawing intervals, so a
hydrofoil selected in the hybrid world could cite a path-end command. It now
indexes `scene subject` outputs directly and traces the Scene IR expression and
source line that actually directed the performer.

### Portrait cover crop hid the game

A centered 16:9 cover crop hid Reso's hydrofoil on a 390×844 viewport. The
compositor now maps Planes' normalized camera x into a portrait pan over one
undistorted 1600×900 world. The same semantic crossing visibly travels from
the starting dock to the capital without a mobile-specific world model.

### Delivery sprites were oversized

The transparent hydrofoil master was 731 KB at 1586×992 despite being shown at
roughly 360×225. A 720-pixel alpha WebP delivery asset reduces that to about
28 KB while retaining the master for future compositions.

## Verification completed

- Full ready → care → launch → active → arrived voyage in desktop Chromium.
- The same full voyage at 390×844, including start and destination framing.
- Click and keyboard-semantic object selection.
- Why provenance at the correct Scene IR line.
- All archive tabs, lazy Planes source, and lazy static surface.
- Audio unlock, three active filtered beds, departure and arrival cue
  deduplication, and zero audio diagnostics.
- Reduced-motion emulation: shader hidden and sprite animation removed.
- Desktop and mobile console: zero warnings and zero errors.
- Node crossing suites, Python interpreter parity, JSON protocol validation,
  and the repository CI gate.

## GitHub Pages integration

A Crossing remains a root showcase page beside Garden, Paint, Try, and Planes
on Planes. `index.html` carries its card in the same collection and the Planes
mark in the scene title links back to that index without adding a navigation
bar over the visual world.

The Pages assembler now derives and preserves the complete `assets/` tree;
asset-only changes trigger the workflow. The deployment surface checker also
follows cache-busted module imports plus `src`, `href`, and `srcset` references
inside renderer-owned template markup. This closes the exact class of failure
where a root page deploys but its compositor sprites or environment plates do
not.

Measured processing is recorded in `benchmarks/a_crossing.md`.

## Expansion seams

Grow the work by extending Planes Scene IR rather than introducing a second
JavaScript simulation:

- give all nine landings their own environment plates and Scene IR manifests;
- emit a route graph with optional stops, tide windows, weather cells, and
  jurisdiction handoffs;
- add landing-specific sound beds and motifs behind the same structured audio
  protocol;
- support named voyage cards that store only seed, ordered input, and protocol
  version;
- add sprite atlases or lightweight skeletal animation when characters and
  dock activity become independently interactive;
- add depth/parallax or a deliberately bounded WebGPU performer only after a
  scene needs it and browser support/fallback requirements are explicit;
- profile larger scene graphs before changing interpreter architecture.

## Handoff checklist

A future agent should read the v2 design spec, implementation plan, this
record, the benchmark, and `grammar/protocols/scene-v1.json`; then run the
focused Node and Python suites and serve this exact worktree. Preserve the
director/performer boundary and treat the high-resolution PNG files as source
masters, not delivery defaults.
