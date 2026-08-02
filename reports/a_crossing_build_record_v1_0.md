# A Crossing / Nine Landings — build record v1.0

> Historical record. The visual-first Planes-as-director rebuild supersedes
> this implementation. Continue from `a_crossing_build_record_v2_0.md`; retain
> this file to preserve why the architectural boundary changed.

Date: 2026-08-01  
Branch: codex/a-crossing-nine-landings  
Isolated worktree: /private/tmp/planes-a-crossing

## Purpose

A Crossing is the second substantial demonstration of Planes after Garden. It
proves that one Planes program can own an explorable, game-like visual world:
state, seeded variation, event decisions, motion, sound, drawing, explanation,
replay, and a computed effect boundary. JavaScript presents the run but does
not contain a parallel crossing model.

The experience is a fictional, local simulation. It never claims to alter a
real route, service, place, or person.

## Approved decisions that shaped the build

- Product title: A Crossing / Nine Landings.
- Opening: Horizon.
- Decision line: a simulated Ala Eriri Passage crossing from Reso to Nkwo
  Eriri, evaluated against the ninety-minute Passage standard.
- Form: an open-ended sandbox with real game-like choices, movement, granular
  clickability, sound, seeded weather, and deterministic replay.
- Visual direction: bright contemporary Atlantic and Caribbean island life,
  with paper-editorial framing inherited from Garden and the Planes identity.
- Avoided direction: dark medieval port, pirate fantasy, resort imagery,
  generic dashboard, and abstract prototype shapes.
- Canon: Eriri is never tone-marked. Unresolved binder questions remain
  unresolved.

## Corpus translated into the scene

The country corpus supplied the nine-island setting, the Reso–Nkwo Eriri
Passage, hydrofoils, kordas and terraces, markets, fog capture, radio relays,
wave power, clinic reserve, petrels, and the ninety-minute access promise.
Those details became interactive systems rather than decorative labels.

The visual view is intentionally layered:

1. Reso is close, terraced, inhabited, and market-active.
2. The Passage occupies the middle as moving turquoise water and an ivory
   route cord.
3. The electric hydrofoil crosses the active channel.
4. Nkwo Eriri carries contemporary radio, care, fog, and wave infrastructure.
5. Sunbreaks, seeded swell, and petrels keep the horizon alive.

## Architecture

### One authoritative result

Every tick enters paint/a_crossing.planes through stepGraph. The result carries
the exact output lines, trace, annotations, next state, effects, and errors.
The page retains that result as one unit.

- paint consumes its drawing lines.
- the audio player consumes its sound lines.
- markSink walks those same drawing lines.
- hitTest selects actual recorded marks.
- card explains the selected trace node.
- the source pane highlights the traced Planes line.
- the revision pane reads Planes-owned state.
- the atlas parses only Planes-emitted atlas observations.
- replay folds ordered browser input events back through Planes.

There are no JavaScript route, power, weather, or Passage calculations.

### Planes-owned state

The state file includes status, minutes, route, selected subject, sea state,
available power, radio state, and a statement of revision. The current statuses
are:

- crossing-ready
- crossing-delayed
- crossing-refused
- crossing-arrived

Named derivations include sea-state, available-power, safe-route,
passage-minutes, meets-passage, decision, and revision. Their because
annotations make the model inspectable without rerunning it.

### Event protocol

The browser contributes only JSON-shaped input:

- route / depart
- route / shelter
- route / reserve
- power / clinic
- radio / relay
- select / subject-id

Planes dispatches these records with when. Selection revises inspection focus
without secretly changing the crossing.

### Seed and replay

Seed 481027 is the initial fixture. Seed affects swell, market color, motion
phase, and atmosphere. A fixed seed plus an ordered event list reproduces the
same Planes state and output. The page keeps the event list only as presentation
history and replays it through the interpreter on reset.

## Interaction design

The canvas is the primary play surface. A person can:

- start and pause continuous motion;
- run at normal or three-times visual speed;
- generate new seeded weather;
- enable Planes-emitted sound;
- depart, shelter, retain reserve, protect clinic power, or relay radio;
- click a visible mark;
- select any of twelve emitted subjects from the living index;
- inspect the value origin, because annotations, and exact source line;
- review an output-derived secondary atlas and ordered replay;
- read the statically computed effect surface.

The selected outline is itself a second drawing-protocol stream. No direct
Canvas drawing path exists in the page.

## Visual system

The CSS frame reuses the repository’s Red Hat Display and Martian Mono fonts,
paper ground, graphite type, clay, amber, sea, teal, violet, and the real
Planes mark. The Planes drawing supplies the geographic color and movement.

Responsive behavior changes the editorial composition but not the simulation.
At narrow widths the Horizon text follows the canvas and the Passage badge
becomes part of normal flow so it cannot obscure the opening. Reduced-motion
preferences suppress transitions; the scene remains understandable through
state, revision, source, and controls.

## Test-driven build sequence

1. A minimum ready fixture established the state-file contract in JavaScript
   and Python.
2. Route outcomes were made to fail, then implemented with Planes when
   dispatch.
3. Power, radio, selection, no-event, replay, trace, and static-surface
   fixtures expanded the model.
4. Pure output adapters were added for protocol splitting, status, subject
   provenance, atlas observations, and replay.
5. Structural page tests prohibited a JavaScript decision model and direct
   Canvas drawing.
6. The temporary scaffold was removed and replaced by the Horizon page.
7. Browser checks exercised ready, delayed, refused, arrived, and animated
   states with zero console warnings or errors.
8. Performance was measured and recorded in benchmarks/a_crossing.md.

## Defects found and repaired during implementation

- The browser and Node loaders disagreed about a top-level entry base. The Node
  loader now accepts an explicit base just like the browser path.
- Event was absent from the composed input/provenance name sets. It is now a
  first-class page input beside tick, seed, state, keys, and pointer.
- Python CLI tests could leak writes into the repository. They now execute in
  temporary directories.
- The fast CI dependency message mentioned mypy even when fast mode did not
  require it.
- Python module graph reads left file handles open. They now use a scoped,
  UTF-8 file read.
- Record-pattern capture was corrected to Planes shorthand field binding so
  the Python and JavaScript interpreters agree on selection.
- The initial why selection scrolled the entire page to the source pane. Source
  highlighting now scrolls only inside that pane.
- The narrow Passage badge overlapped the Horizon copy. It now enters normal
  flow at the mobile breakpoint.
- The non-fast JSON gate required an eighth byte-identical corpus document that
  only existed as untracked data in the shared workspace. Its minimum now
  matches the seven acceptances available in a clean checkout while retaining
  the named Unicode and refusal cases.
- Provenance initially chose a literal path-end command for the hydrofoil. The
  generic adapter now prefers a traced input-derived output within each
  subject’s emitted interval while retaining the real mark set for hit testing.

## Performance snapshot

On the measured Apple Silicon machine:

- warm Planes steps were about 7.1 ms median;
- the browser’s full subject/provenance mark pass was about 2.9 ms median;
- Canvas painting was about 1.9 ms median;
- hit testing, why-card construction, and sound schedule extraction were each
  below 0.1 ms median.

The complete method and p95 values are in benchmarks/a_crossing.md. These are
local observations, not universal language budgets.

## Durable files

- paint/a_crossing.planes — the world, decisions, drawing, sound, and state
- js/paint/a_crossing.mjs — output-only adapters
- a-crossing.html — the Horizon experience
- js/test/a_crossing_scene.test.mjs — semantic, replay, provenance, and surface
- js/test/a_crossing_page.test.mjs — accessibility and ownership boundary
- test_a_crossing_in_planes.py — reference-interpreter parity
- benchmarks/a_crossing.md — measured processing record

Supporting runtime repairs are intentionally small and covered by the existing
repository suites.

## Expansion seams

Future work should grow through Planes output rather than a page-side world
model:

- Add the remaining seven islands as independently loadable landings.
- Make the route graph an emitted atlas protocol with optional intermediate
  stops and jurisdiction handoffs.
- Add tide windows, fog-water storage, market schedules, and wave-power loads
  as explicit planes whose tradeoffs remain explainable.
- Extend replay into named voyage cards that store only seed and events.
- Add keyboard spatial navigation between emitted subjects.
- Let sound grow into landing-specific signal motifs while retaining one sound
  protocol.
- Add save/export through existing Planes file boundaries, never hidden browser
  persistence.
- Profile larger island graphs before changing the language runtime. The
  current demonstration is not near its measured frame interval, so complexity
  should be added with evidence rather than premature architecture.

## Handoff rule

A future agent should begin by running the three focused suites, serving this
exact worktree, and reading this record beside benchmarks/a_crossing.md. Preserve
the central invariant: Planes decides; the browser observes, renders, and
returns input.
