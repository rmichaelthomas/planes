# Horizon — The Living Passage

**Status:** Approved design, pending written-spec review

**Date:** 2026-08-01

**Audience:** Planes maintainers and implementation agents

**First audience:** Children ages 10–13

**First world:** Ala Eriri

**First delivery:** A browser-native, premium 2.5D vertical slice

## 1. Verdict

Planes should become the semantic heart of a visual world-building game engine, not its pixel renderer.

The child, agent, and engine share Planes as the language of world identity, state, relationships, behavior, affordances, lineage, rationale, and authority. Specialized browser performers render that meaning through high-quality graphics, motion, physics, sound, and accessible interaction. Planes must enhance those performers without constraining them.

The product begins inside Ala Eriri as a real game. A child plays first, discovers that meaningful things can be touched, remixes the world through the Living Lens, tests agent-generated Possibility Echoes, follows Living Traces into exact Planes, and eventually carries chosen transformations across the horizon in a Living World Seed to grow an original world.

The first build is **Horizon — The Living Passage**: one contained but open-ended world cell around Reso Landing and the Passage edge. It must prove the complete loop at production-minded quality before the system expands to more districts, worlds, collaboration, or 3D.

## 2. Why this is the right expression of Planes

Garden proved that Planes can directly produce visual and sonic expression. A Crossing proved that Planes can direct a richer browser performer while retaining deterministic state, visible provenance, and a computed effect surface.

The world builder advances that evolution:

- Planes owns semantic truth and decisions.
- The renderer owns pixels, composition, interpolation, and GPU work.
- The physics adapter owns bounded physical simulation.
- The audio performer owns synthesis, mixing, spatialization, and timing.
- The agent proposes Planes changes but receives no direct mutation power.
- Liminate expresses the active agreement.
- Seshat or an equivalent host enforces the agreement and produces receipts.
- The child remains the author because only the child can turn a proposal into a committed world change.

This is agent-native in the strongest useful sense. An agent can read the language contract, world protocol, current world slice, active agreement, and provenance; propose a bounded patch; and receive machine-derived acceptance or refusal. It does not need to infer an undocumented engine API or manipulate a canvas by imitation.

## 3. Product goals

The first product must:

1. Feel like a beautiful, responsive game before it feels like a programming environment.
2. Give play and making equal status inside one continuous world.
3. Let children directly manipulate meaningful world subjects without opening a conventional editor.
4. Reveal causal structure before syntax while preserving exact, editable Planes underneath.
5. Let an agent broaden imagination without replacing child authorship.
6. Keep safeguards visible, structural, and educational.
7. Preserve deterministic replay, derivation, provenance, undo, and recovery.
8. Run smoothly on ordinary school hardware through adaptive visual fidelity.
9. Treat Ala Eriri as an authored culture and living place, not a disposable tutorial or extractable asset pile.
10. Establish renderer-neutral world semantics that a future 3D performer can consume without rewriting saves or world logic.

## 4. Explicit non-goals for the first vertical slice

The first slice does not include:

- multiplayer;
- public sharing or publishing;
- a marketplace or monetization;
- arbitrary asset uploads;
- unrestricted generated images, models, shaders, scripts, or audio;
- full 3D;
- a native mobile application;
- unbounded agent tools;
- autonomous agent commits;
- a general-purpose game-engine editor separate from the world;
- a classroom surveillance, grading, or student-risk system;
- ownership transfer of canonical Ala Eriri culture or lore.

These are deferred seams, not implied commitments.

## 5. Governing product principles

### 5.1 Game first

The first screen is a playable world, not a tutorial, code pane, asset browser, dashboard, or project picker. The child learns movement, consequence, and relationships by playing.

### 5.2 Inside-out making

The child stays inside Ala Eriri while learning to make. Authoring appears through the world itself. There is no gray editor mode.

### 5.3 Progressive depth

The Living Lens has three approved depths:

1. **Glance** — identify a meaningful subject, its boundary, and signs of memory or possibility.
2. **Touch** — expose compact, type-appropriate direct actions anchored to the subject.
3. **Make** — reveal behavior, relationships, rationale, agent help, and exact Planes only through deliberate curiosity.

Complexity is available without being imposed.

### 5.4 Broad touchability with semantic affordances

Everything meaningful is touchable. Not every pixel is independently editable. A subject’s semantic identity determines what actions make sense: water may flow and sound; a creature may move and respond; a place may contain and remember; a rule may connect cause and effect; lore may carry restrictions and provenance.

### 5.5 One semantic world

The renderer, agent, quality tier, accessible mirror, and future 3D performer all consume bounded interpretations of the same Planes world. None becomes an alternate source of truth.

### 5.6 Reversible creativity

Preview, undo, branch comparison, replay, autosave, snapshot recovery, and explicit commit are part of the creative grammar. Failure must not threaten the child’s existing world.

### 5.7 AI is optional

Direct Lens tools, authored recipes, deterministic hints, parser feedback, Living Trace, `why`, `because`, local generation, save, replay, and world-seed creation remain available with AI disabled.

## 6. Child experience

The approved experience arc is:

1. **Enter** — arrive in Ala Eriri without a lesson screen.
2. **Explore** — move, listen, meet needs, cross places, and see consequences.
3. **Notice** — Glance through the Living Lens and discover semantic subjects.
4. **Remix** — Touch and directly change position, expression, sound, or behavior where the subject permits it.
5. **Co-build** — ask the agent for a complex change and enter a Possibility Echo before trusting it.
6. **Understand** — follow the Living Trace from event to Planes decision to visible effect, rationale, provenance, and receipt.
7. **Own** — keep, revise, combine, or discard the change.
8. **Cross** — gather chosen patterns and child-authored transformations into a Living World Seed and grow an original world cell.

The core loop repeats at every scale:

> Explore → notice → change → play-test → understand → keep or revise

There is no experience-point gate on creativity. Progress is demonstrated through authored relationships and systems, not through extracting Ala Eriri’s culture as collectible material.

## 7. The Living Lens

### 7.1 Selection

Every selectable subject has:

- a stable semantic ID;
- a human-readable localized name;
- a focus and hit region independent of transparent sprite pixels;
- keyboard, pointer, touch, and accessible-DOM focus behavior;
- a subject type and affordance registry entry;
- a provenance and authority status;
- a source-map path to its Planes definition or generated patch.

Dense scenes use semantic selection priorities, spatial indexes, zoom-sensitive grouping, and optional disambiguation. They do not expose thousands of overlapping pixel fragments.

### 7.2 Direct actions

Touch actions are derived from the complete subject, not hard-coded into the page. Initial action families are:

- move or place;
- change expression;
- hear or change sound;
- change state;
- define or revise behavior;
- connect or disconnect a relation;
- inspect why;
- ask the co-builder;
- undo or restore.

The affordance registry must state required facets, accepted value shapes, authority requirements, preview behavior, inverse operation, and child-facing explanation.

### 7.3 The Bidirectional Living Trace

The Living Trace presents:

1. the world event;
2. the Planes decision or relationship;
3. the visible or audible effect;
4. the `because` rationale where one exists;
5. the exact Planes source;
6. derivation and provenance;
7. agent and child attribution;
8. the active authority decision when AI participated.

World edits, trace edits, and exact source edits must round-trip through one source map. A visual node without exact source correspondence is read-only until a faithful mapping exists. The UI must never pretend an approximate visual edit was a lossless source edit.

## 8. Planes-native world model

Every meaningful subject composes seven orthogonal facets. These are World IR concepts and library records, not seven new language keywords.

### 8.1 Identity plane — what

- stable semantic ID;
- kind and subkind;
- display names and aliases;
- canonical, remixable, restricted, or child-authored status;
- schema and protocol version.

### 8.2 Situation plane — where and now

- containing place;
- normalized or world-space transform;
- current state;
- occupancy;
- spatial anchors;
- active/inactive chunk status;
- physics and audio position references.

### 8.3 Relation plane — with what

Typed, directed relationships such as:

- contains / contained-by;
- connects / connected-to;
- serves / served-by;
- near;
- causes / caused-by;
- belongs-to;
- depends-on;
- remembers;
- derived-from.

Relations have stable IDs and provenance. They are not anonymous pointers.

### 8.4 Behavior plane — when

- record-shaped event patterns;
- Planes `when` dispatch;
- deterministic transitions;
- timers expressed in simulation ticks;
- conditions;
- local state machines;
- emitted semantic events;
- declared failure paths.

Simulation behavior must not read ambient `clock` or `random`. Replayable time comes from fixed ticks. Replayable generation comes from a pure, versioned seed algorithm.

### 8.5 Expression plane — how shown

- visual asset identity;
- layer and depth;
- animation state;
- material and shader-graph parameters;
- lighting response;
- particle intent;
- collider and sensor identities;
- audio anchors, beds, cues, and music state;
- Sun, Breeze, and Harbor variants;
- reduced-motion and accessible alternatives.

Expression never decides semantic outcomes.

### 8.6 Affordance plane — what can change

- available child actions;
- preconditions;
- accepted value shapes;
- preview and inverse behavior;
- authority requirements;
- learning explanation;
- source-map target;
- deterministic fallback.

The Living Lens derives its current controls from this plane plus all other facets.

### 8.7 Lineage and authority plane — why, from whom, and who may

- original corpus source;
- cultural status;
- author and contributor attribution;
- child, agent, or system origin;
- `because` rationale;
- active agreement fingerprint;
- permitted transformations;
- publishing and collaboration restrictions;
- immutable system boundaries.

## 9. World IR protocol

### 9.1 Location and ownership

The versioned host contract extends the existing scene-intent precedent under `grammar/protocols/`. The first engine contract should be `grammar/protocols/world-v1.json`, accompanied by generated error and coverage projections where the repository’s existing generation rules require them.

The language grammar remains distinct from a renderer contract. The protocol file must identify itself as a host protocol and declare which decisions belong to Planes and which belong to performers.

### 9.2 Structured `show`, not an eighth effect

World envelopes cross the existing `show` boundary. This preserves the seven closed effect kinds and the existing static effect surface.

The browser runtime gains an optional typed observation beside canonical display text:

```text
Planes value
  ├─ canonical rendered text → CLI, logs, compatibility hosts
  └─ typed shown value + derivation → world host
```

Requirements:

- the text and typed forms originate from the same traced Planes value;
- compatibility hosts may ignore the typed form and print text;
- the effect log remains `show`;
- analyser behavior does not change;
- conformance tests prove typed and canonical forms agree;
- all three Planes implementations preserve language-level semantics;
- an unsupported world protocol version refuses the whole delta batch before application;
- unknown optional records warn and are ignored only when the protocol explicitly marks them optional.

### 9.3 Full snapshot and deltas

Initial load produces a complete World IR snapshot. Later steps produce monotonic revisions containing only semantic changes:

- created subjects;
- removed subjects;
- facet patches;
- relation additions and removals;
- scheduled cues;
- invalidated affordances;
- provenance and source-map updates.

Each delta declares:

- protocol version;
- world package fingerprint;
- previous revision;
- next revision;
- simulation tick;
- ordered operations;
- semantic snapshot hash after application.

Performers reject gaps, duplicate revisions with different content, malformed critical records, and package mismatches. They retain the last valid semantic frame and request resynchronization.

### 9.4 Numeric bridge

Planes numbers are exact unless the language explicitly marks an approximation. GPU and Rapier values are finite machine numbers. The boundary must state the conversion rather than laundering machine floats into apparently exact Planes values.

Rules:

- semantic time is integer ticks;
- semantic positions, velocities, gains, and normalized values use declared fixed-point units at the Planes boundary;
- Rapier outputs are quantized to the declared unit before re-entering Planes;
- renderer interpolation values never become authoritative semantic state;
- approximate values retain the Planes approximation marker and provenance;
- world packages pin the physics engine and numeric-bridge versions;
- determinism tests compare semantic snapshot hashes, not pixels.

## 10. Browser engine architecture

### 10.1 Visual performer

Use PixiJS v8 as a modular visual performer, with production defaulting to stable WebGL. WebGPU remains opt-in until the compatibility matrix, shader parity, accessibility behavior, and fallback path pass the same release gates.

Pixi responsibilities:

- scene graph and transforms;
- render layers independent of semantic parentage;
- texture and asset loading;
- sprite batching and atlases;
- masks, blend modes, filters, and bounded shader graphs;
- particle containers;
- cameras and interpolation;
- culling and render-group caching;
- pointer mapping;
- context-loss restoration;
- accessibility overlay integration where it is reliable.

Pixi does not decide actions, routes, success, behavior, ownership, provenance, or world state.

### 10.2 Physics performer

Use Rapier 2D selectively for subjects whose behavior genuinely requires collisions, sensors, joints, or forces. Do not make every semantic subject a rigid body.

Physics requirements:

- fixed timestep;
- pinned Rapier version;
- declared world-to-physics scale;
- deterministic insertion order;
- snapshot and restore;
- collision and sensor events converted to typed World IR events;
- collision filters derived from Planes semantics;
- no direct renderer mutation;
- no parallel/SIMD mode that weakens the chosen determinism contract.

### 10.3 Audio performer

Use structured Web Audio graphs. Audio intent declares semantic identity and timing; the host chooses synthesis and mixing within declared limits.

Every continuous sound must declare:

- bus;
- anchor;
- start and stop condition;
- gain envelope;
- frequency or playback range;
- maximum duration before renewal;
- priority and voice budget;
- reduced-sensory alternative.

No sound may default to an uncomfortable continuous high-frequency oscillator. Master gain starts conservative. Sound begins only after user activation, can be muted independently, and must stop cleanly on pause, world transition, or worker failure.

AudioWorklet is used only for processing that needs its low-latency audio thread. Ordinary ambience and cues should prefer standard Web Audio nodes and scheduled parameter ramps.

### 10.4 Semantic HTML performer

Semantic HTML remains responsible for:

- Living Lens controls;
- Living Trace;
- Making Agreement and capability compass;
- dialogs, menus, and status;
- keyboard and screen-reader mirrors;
- reduced-motion alternatives;
- recoverable error messages;
- source and provenance inspection.

The DOM is a secondary interaction and accessibility layer over the world, not a page template that visually flattens the game.

### 10.5 Dependency and deployment policy

The existing repository’s no-build-step rule remains load-bearing.

The engine uses browser-native `.mjs` modules. Pinned, audited browser distributions of PixiJS and Rapier live under a servable vendor subtree with recorded versions, licenses, upstream URLs, and integrity hashes. Dependency refresh is a deliberate maintainer operation; opening or deploying Horizon does not require npm, a CDN, a package registry, transpilation, or bundling.

The Pages assembly remains derived from the authored tree. Horizon must be a root HTML showcase linked from `index.html`; its modules, Planes programs, protocol data, vendor modules, and asset packs must be discovered by the same page-surface gate rather than added to a hand-maintained deployment allowlist.

## 11. Concurrency and clocks

Planes does not need language-level concurrency for the first engine.

### 11.1 Simulation worker

A dedicated worker owns:

- persistent Planes VM;
- loaded module graph;
- compiled world program;
- authoritative World IR;
- fixed-step scheduler;
- Rapier world;
- event application;
- source maps and derivations;
- snapshot production;
- world delta production.

It receives immutable input snapshots and typed events. It does not access the DOM.

### 11.2 Main thread

The main thread owns:

- Pixi rendering;
- DOM and accessibility;
- pointer, keyboard, touch, and controller input capture;
- interpolation between accepted world revisions;
- asset lifecycle coordination;
- ordinary Web Audio graph control;
- fidelity-tier controller.

It never waits synchronously for an agent or a simulation step.

### 11.3 Audio thread

AudioWorklet, when used, owns only custom audio processing. It receives scheduled parameters and compact control messages, not the World IR.

### 11.4 Agent and build work

Agent calls, proposal compilation, static analysis, authorization, asset preparation, and Possibility Echo simulation are asynchronous and outside the active frame loop.

### 11.5 Message contract

Use structured-clone-compatible plain records and transferable typed buffers only when measurement justifies them. Shared mutable memory is excluded from the first slice.

Messages include explicit protocol version, world fingerprint, sequence, and cancellation token. Stale responses are discarded rather than applied late.

## 12. Persistent Planes runtime

The demonstration loop currently composes source prelude text, parses and runs the graph, renders output to text, writes state through an in-memory JSON file, and repeats. It remains valid for small showcase pages but is not the engine path.

The engine runtime must:

1. hash and load a module graph once;
2. lex, parse, analyse, source-map, and compile only when source changes;
3. instantiate a persistent interpreter or compiled VM state;
4. call a named world initialization function once;
5. call a named advance function for fixed-step input/event batches;
6. keep immutable Planes world values in memory rather than serializing them through JSON each tick;
7. preserve derivations and `because` annotations across revisions;
8. emit typed structured-show deltas;
9. generate periodic serializable snapshots;
10. support cancellation and bounded execution for malformed or adversarial programs.

The first runtime may use a persistent AST interpreter. Bytecode or WASM compilation is a later optimization unless profiling proves the interpreter cannot meet the simulation budget after parse elimination, persistent modules, dirty stepping, and delta output.

This ordering matters: concurrency protects responsiveness; eliminating repeated work creates speed.

## 13. Persistence, branching, and the Living World Seed

### 13.1 World package

A world package includes:

- package format version;
- Planes language and runtime versions;
- World IR protocol version;
- physics and numeric-bridge versions;
- root program fingerprint;
- module graph fingerprints;
- asset manifest fingerprint;
- origin World Seed;
- active agreement fingerprint;
- cultural and licensing manifest.

### 13.2 Event log

Committed changes append attributed events. Each event includes:

- monotonic sequence;
- semantic tick;
- child, agent, system, or migration actor;
- source fingerprint before and after;
- Planes patch or direct semantic operation;
- affected subjects and facets;
- rationale;
- authorization receipt where applicable;
- previous event hash.

### 13.3 Snapshots

Snapshots are produced at bounded event and time intervals and before migrations. A snapshot includes the authoritative World IR, Planes state, physics snapshot, active chunk set, event sequence, and semantic hash.

Undo and redo are events over a branch, not destructive history deletion. Recovery restores the newest valid snapshot and replays later valid events.

### 13.4 Possibility Echo

An Echo is a branch with:

- parent snapshot and event sequence;
- proposed patch;
- proposal and authorization fingerprints;
- isolated runtime state;
- no external effects;
- explicit expiration;
- child-authored modifications;
- outcomes: discard, retain temporarily, combine, or commit.

No Echo changes the parent world until the child commits it.

### 13.5 Living World Seed

A World Seed is executable ancestry, not a full clone. It packages:

- child-selected patterns;
- child-authored behaviors and relations;
- permitted expression assets or references;
- sounds and generators;
- deterministic generator settings;
- provenance and cultural constraints;
- source and event lineage;
- world rules and active agreement.

Canonical Ala Eriri remains intact. Restricted canonical material is referenced or transformed only according to its declared permission; it does not silently become the child’s property.

## 14. Cache design

All caches are content-addressed and versioned.

| Cache | Required key material |
|---|---|
| compiled program | language version, runtime version, grammar fingerprint, ordered module content hashes, compile options |
| static surface | analyser version, rule-plane version, ordered module content hashes |
| world package | seed, compiled-program hash, asset-manifest hash, World IR version, physics version |
| snapshot | world-package hash, event sequence, snapshot format |
| render asset | source content hash, transform pipeline version, fidelity tier, color-space version |
| world chunk | world-package hash, chunk ID, generator version |
| authorization | proposal hash, source hash, agreement hash, policy/enforcer version |

Rules:

- never mix module generations;
- never reuse authorization across changed source or agreement fingerprints;
- refuse stale or partial manifests explicitly;
- stage cache updates atomically;
- keep an indexed rollback generation;
- cap disk and memory caches by named budgets;
- expose a child-safe recovery action and a technical cache report;
- test cold, warm, stale, corrupt, interrupted, and migrated states.

## 15. Semantic Fidelity Ladder

The semantic simulation is invariant across visual tiers.

### Sun

- target 60 FPS;
- full-resolution art within device limits;
- dynamic normal-map lighting;
- rich particles and fog;
- reflections and post-processing;
- full animation density.

### Breeze

- target 45–60 FPS;
- adaptive render scale;
- fewer dynamic lights;
- reduced particles;
- cached effects;
- simplified reflections.

### Harbor

- 30 FPS floor;
- reduced render scale;
- baked or simplified light;
- minimal particles;
- lite shader path;
- reduced motion where needed.

Never adaptive:

- Planes decisions;
- semantic subjects;
- collision outcomes;
- World Seed;
- child changes;
- authority checks;
- save compatibility;
- provenance;
- accessible meaning.

If WebGL is unavailable or repeatedly loses context, a separate **Safe Harbor** semantic performer uses HTML/SVG/Canvas to preserve navigation, decisions, Lens access, trace, sound cues, and saves. It is an honest reduced performer, not a claim of visual parity.

## 16. Initial performance gates

These are release gates for the vertical slice and must be recalibrated against named reference devices after the engine-kernel spike. Changing a gate requires a recorded measurement and decision.

| Measure | Gate |
|---|---|
| Sun frame time | p95 ≤ 16.7 ms on the Sun reference device |
| Breeze frame time | p95 ≤ 22 ms on the school-hardware reference device |
| Harbor frame time | p95 ≤ 33.3 ms on the constrained reference device |
| simulation step | p95 ≤ 10 ms at the selected fixed-step rate |
| input to visible response | p95 ≤ 70 ms for local direct manipulation |
| steady-play main-thread long tasks | zero tasks over 50 ms attributable to engine work |
| first playable payload | ≤ 6 MB compressed before background streaming |
| sound | no unintended continuous tone, clipped bus, leaked node, or missed stop in a 30-minute soak |
| semantic determinism | identical snapshot hashes for the same pinned package, seed, and events |
| quality-tier invariance | identical semantic event log and save hash across Sun, Breeze, Harbor, reduced-motion, and Safe Harbor performers |

The gate records frame-time distributions, simulation distributions, asset bytes, texture residency, JS heap, worker count, audio-node count, and long-session growth. Average FPS alone is insufficient.

## 17. Agent-native co-building

### 17.1 Scoped context

The agent receives only what the active request needs:

- machine-readable Planes grammar and errors;
- World IR and affordance protocol versions;
- selected subject slice and nearby relations;
- relevant authorized corpus excerpts;
- active Making Agreement;
- current source maps;
- allowed asset and shader registries;
- child’s explicit request.

It does not receive an entire private vault, full child history, unrelated worlds, raw receipts, or persistent voice recordings.

### 17.2 Proposal envelope

The agent must return a typed envelope containing:

- proposed Planes patch;
- expected affected subjects and facets;
- declared asset operations;
- expected effect-surface difference;
- child-facing summary;
- rationale;
- uncertainty and assumptions;
- suggested deterministic fallback;
- no imperative host tool calls.

Malformed envelopes are refused before parsing the patch.

### 17.3 Gate sequence

```text
child request
  → context minimizer
  → agent proposal envelope
  → Planes parse and canonical render/reparse
  → static effect analysis and rule-plane check
  → semantic and source diff
  → Liminate agreement check
  → Seshat/equivalent structural enforcement
  → isolated Possibility Echo
  → child play-test and inspection
  → child commit or rejection
  → attributed event and readable wake
```

The model is not the parser, referee, runtime, authorization authority, or only tutor.

## 18. Making Agreement and authority

The approved hierarchy is:

1. **Immutable system baseline** — cannot be weakened by child, adult, agent, repository content, imported world, or prompt.
2. **Guardian or educator agreement** — may narrow model access, publishing, collaboration, time, corpus, and tool scope; may not weaken the baseline.
3. **Child controls** — may read the agreement, disable AI, approve, reject, undo, inspect, and request an exception; may not silently widen authority.
4. **Agent** — may propose only and has no standing mutation capability.

The Visible Making Agreement presents a child-readable capability compass showing:

- the current agent reach;
- who set each boundary;
- what the current proposal requests;
- why it passed, requires adult review, or was refused;
- what data would leave the device;
- how to disable AI;
- the readable wake after a decision.

Adult constraints and review surfaces must not be invisible to the child.

## 19. Threat and privacy boundaries

The first slice structurally denies:

- direct agent access to renderer, saves, physics, files, network, accounts, or external tools;
- autonomous publishing, contact, purchase, or collaboration;
- instructions embedded in world text, lore, assets, imported content, or receipts from becoming agent authority;
- embedded HTML or JavaScript in imported assets;
- arbitrary shader or audio processor execution;
- covert emotional inference, advertising identity, behavioral sale, or opaque risk scores;
- undisclosed adult surveillance;
- reuse of a stale authorization after source, agreement, or policy change.

Imported and generated assets pass decode, type, dimension, duration, complexity, provenance, licensing, and resource-budget validation. Initial shaders come from a bounded graph of reviewed nodes. Initial procedural audio comes from a bounded registry of safe node graphs and parameter ranges.

Child data is local-first. Network use is explicit, scoped, and disclosed. Voice input is transcribed ephemerally and not stored by default. Telemetry is off by default in the first slice; local performance diagnostics remain available for voluntary export.

## 20. Cultural integrity

Ala Eriri content has at least four statuses:

- canonical and immutable;
- canonical and remixable with lineage;
- restricted or contextual;
- child-authored.

Every transformation preserves status and provenance. The agent receives only excerpts authorized for the requested transformation. It may not invent canonical claims, silently merge child fiction into canon, or strip diacritics and pronunciation metadata where those are semantically meaningful.

The first slice uses the supplied corpus and existing visual assets as authoritative inputs. New art must be produced through a Planes-directed asset-compositor pipeline that records source assets, transformations, generated derivatives, masks, pivots, depth maps, normal maps, animation rigs, audio anchors, and permissions. A generated plate without object segmentation and semantic registration is not an engine-ready world asset.

## 21. Accessibility and sensory design

The first slice supports:

- keyboard, pointer, and touch;
- remappable actions;
- visible focus and semantic focus order;
- minimum 44 CSS-pixel touch targets for UI controls;
- DOM mirrors for meaningful world subjects and actions;
- captions and visible substitutes for semantic audio cues;
- reduced motion that preserves state and timing meaning;
- independent music, ambience, effects, and narration controls;
- conservative loudness and frequency defaults;
- color-independent state signals;
- scalable text without covering required play controls;
- pause and resume without semantic time drift;
- Safe Harbor fallback when the visual performer is unavailable.

Accessibility variants must pass semantic-fidelity invariance tests.

## 22. Error handling and recovery

### Protocol failure

Refuse the entire malformed or unsupported delta batch. Retain the last valid semantic frame, pause semantic advancement if necessary, and request a full resynchronization. Never apply a partial critical batch silently.

### Planes failure

Stop the semantic clock, keep rendering and DOM responsive, preserve the last valid state, and present:

- a child-facing explanation;
- the nearest safe recovery action;
- exact Planes error and fix clause on request;
- the affected source and branch;
- a path to restore the last snapshot.

### Worker failure

Restart from the newest valid snapshot and replay acknowledged events. Unacknowledged inputs remain visibly pending or are retried only when idempotent.

### GPU failure

Attempt context restoration once within a bounded interval, then lower fidelity or enter Safe Harbor. Semantic simulation and saves survive the renderer transition.

### Asset failure

Use a canonical silhouette, quiet audio substitute, or declared placeholder. Preserve semantic identity and show provenance/error status through the Lens. Never replace a culturally specific asset with an invented generic symbol without disclosure.

### Agent or authorization failure

The parent world remains unchanged. Explain which stage refused the proposal and offer direct tools, a narrower request, or deterministic authored help.

### Corrupt persistence

Validate hash chains and snapshot hashes. Roll back to the newest valid generation, quarantine corrupt material, and preserve a technical recovery report. Never repair by guessing.

## 23. Testing strategy

### 23.1 Language and protocol conformance

- Python, JavaScript, and self-hosted Planes agreement remains green.
- Structured `show` preserves canonical text and effect logs.
- World protocol schema matches the live parser and error sites through generated projections or equivalent drift checks.
- Canonical render/reparse holds for agent patches.
- Source maps survive direct, visual, and agent edits.
- Unknown and unsupported protocol behavior is pinned.

### 23.2 World-model tests

- stable IDs survive renames, renderer swaps, and save/load;
- relations remain referentially valid;
- every affordance declares inverse, authority, preview, and source target;
- canonical and child-authored status cannot collapse;
- facet deltas produce the same result as a full snapshot;
- invalid operation ordering is refused.

### 23.3 Determinism tests

- same package, seed, and events produce the same semantic hashes in supported browsers;
- event replay matches snapshots;
- quality and accessibility performers do not alter semantics;
- physics insertion order and numeric quantization are pinned;
- ambient `clock` and `random` are absent from authoritative world programs.

### 23.4 Performance tests

- named Sun, Breeze, and Harbor reference devices;
- p50, p95, and p99 frame and simulation costs;
- cold and warm first playable;
- chunk streaming and cancellation;
- 30-minute play/edit/undo/branch soak;
- texture, heap, worker, audio-node, snapshot, and event-log growth;
- rapid Lens selection and dense-scene disambiguation;
- agent response never blocks frames.

### 23.5 Trust and adversarial tests

- prompt instructions embedded in lore, names, imported worlds, receipts, and assets;
- malformed and overbroad proposal envelopes;
- direct network/file/publish requests;
- stale agreement and authorization caches;
- forbidden canonical transformations;
- oversized/decompression-bomb assets;
- shader and audio graph budget escapes;
- model timeout, refusal, hallucinated IDs, and invalid Planes;
- child disables AI during an active proposal;
- adult narrows authority while an Echo is open.

### 23.6 Accessibility and UX tests

- complete first-slice loop by keyboard;
- touch-only completion;
- screen-reader navigation of selected subjects and actions;
- reduced-motion semantic parity;
- sound-off completion;
- readable Making Agreement at the target age;
- child usability sessions measuring comprehension, not only task completion.

## 24. First vertical slice: Horizon — The Living Passage

### 24.1 World scope

One premium 2.5D world cell around Reso Landing and its Passage edge, using the supplied Ala Eriri corpus and visual assets.

The cell contains enough semantic variety to prove:

- a place and contained subjects;
- navigable ground and water edge;
- weather and tide state;
- a structure;
- a living ecological subject;
- a spatial soundscape;
- one local activity with consequence;
- one authored remix recipe;
- one agent-generated Possibility Echo, such as a non-canonical high-tide night-market proposal;
- one Living Trace from event through Planes to visible effect;
- one Living World Seed crossing into a small original world cell.

The proposal example remains explicitly non-canonical unless the corpus owner later promotes it through a separate editorial act.

### 24.2 Fifteen-minute proof loop

A new child can, without a compulsory tutorial:

1. enter and move;
2. notice and interact with a local condition;
3. Glance and Touch at least one semantic subject;
4. make and undo a direct change;
5. ask for or open a complex Possibility Echo;
6. enter and play-test the Echo;
7. follow its Living Trace and reveal exact Planes;
8. accept, revise, combine, or discard it;
9. inspect the readable AI wake;
10. package one child-authored transformation into a World Seed;
11. grow and enter one original world cell;
12. close and reopen with state intact.

### 24.3 Success proofs

The slice succeeds only if it proves all six:

1. **Game quality** — movement, depth, animation, weather, light, sound, collision, and delight cohere.
2. **Planes direction** — semantic Planes state visibly controls specialized performers.
3. **Visual authoring** — a non-programmer meaningfully changes the live world without entering a conventional editor.
4. **Agent-native making** — a model can propose valid, bounded Planes while the child remains author.
5. **Learning** — cause, rationale, source, provenance, and AI receipt become understandable through play.
6. **Engine future** — the same seed, IR, saves, and protocols can expand beyond the district and Pixi renderer.

## 25. Delivery decomposition

This program is too large for one implementation plan. Each phase receives its own reviewed sub-spec and implementation plan. The approved order is:

### Phase 0 — Language and protocol substrate

- structured-show observation;
- world-v1 schema and parser;
- source maps for world records;
- persistent loaded-graph invocation;
- immutable in-memory world state;
- deltas, revision checks, and snapshots;
- numeric bridge;
- protocol conformance and cross-implementation tests.

This is the first implementation-planning target after this program specification is approved.

### Phase 1 — Engine kernel

- simulation worker and fixed clocks;
- Pixi visual performer;
- asset manifest and compositor contract;
- selective Rapier adapter;
- audio buses;
- semantic DOM mirror;
- chunking, culling, cache, and fidelity controller;
- deterministic test performer.

### Phase 2 — Playable Ala Eriri cell

- Reso Landing world package;
- movement and camera;
- water, weather, tide, landing, living edge, and soundscape;
- local activity and consequence;
- save, load, pause, replay, and recovery;
- Sun, Breeze, Harbor, and Safe Harbor behavior.

### Phase 3 — Living Lens and learning

- Glance, Touch, and Make;
- semantic selection and disambiguation;
- direct manipulation and inverse operations;
- Living Trace;
- exact Planes reveal and round-trip edit;
- deterministic tutor path.

### Phase 4 — Co-builder and trust

- scoped context builder;
- proposal envelope;
- parser/analyser/rule/Liminate/Seshat gate;
- Visible Making Agreement;
- Possibility Echo branch;
- readable wakes and receipts;
- adversarial and privacy tests;
- AI-off parity.

### Phase 5 — Living World Seed

- seed composer;
- cultural and licensing manifest;
- deterministic world-cell generator;
- original destination cell;
- lineage viewer;
- cross-world save and recovery.

### Phase 6 — Release gates and pilot

- reference-device matrix;
- performance and memory gates;
- accessibility audit;
- sensory audit;
- child usability pilot;
- guardian/educator agreement review;
- threat review;
- live GitHub Pages verification.

## 26. Proposed repository boundaries

Exact filenames are finalized in each phase sub-spec, but implementation should preserve these responsibility boundaries:

```text
grammar/protocols/        machine-readable world host contracts
js/world/runtime/         persistent VM bridge, worker, clocks, deltas
js/world/model/           World IR validation, facets, relations, source maps
js/world/store/           events, branches, snapshots, cache keys, migrations
js/world/performers/      Pixi, audio, physics, DOM, deterministic test sink
js/world/lens/            selection, affordances, Living Trace, direct edits
js/world/agent/           context, proposal envelopes, gates, Echoes, wakes
js/world/assets/          manifests, registries, validation, compositor metadata
js/vendor/                pinned browser-ready third-party distributions
paint/world/              Planes world libraries and first world program
assets/horizon/           authored and derived Ala Eriri engine assets
horizon.html              root showcase and first product entry
```

No single module owns semantic state and rendering. No page-level script becomes a second engine. The root HTML composes bounded modules and remains visually focused on play.

## 27. Rejected approaches

### Planes as sole visual artist

Rejected as the primary engine architecture. Garden already proves direct visual expression. For the world builder, requiring Planes to emit every graphical detail would constrain fidelity and spend semantic runtime on work specialized GPU performers do better.

### Curated hotspots only

Rejected because invisible walls would contradict the open-world authoring promise.

### Every pixel editable

Rejected because broad but semantically empty selection produces noise, shallow actions, and no faithful source mapping.

### Conversation-first editor

Rejected because text would dominate making and weaken direct child authorship.

### Live agent mutation

Rejected because it obscures authorship, complicates rollback, and puts model latency and errors inside the world’s active state.

### Blank-canvas transition

Rejected because it discards accumulated relationships and learning.

### Whole-world fork

Rejected because the child’s new world remains structurally and culturally dependent on a copy of Ala Eriri.

### Full 3D first

Rejected because it multiplies asset, camera, collision, accessibility, generation, and performance burdens before the authoring loop is proven.

### Dual 2.5D and 3D renderers first

Rejected because it doubles renderer and QA work before either reaches quality. World semantics remain renderer-neutral so 3D can be added later.

### Phaser as the semantic framework

Rejected for the first engine because Planes would have to negotiate another framework’s scene lifecycle and object model. Phaser remains a valid reference and fallback candidate if the custom kernel cannot reach reliability within the approved scope.

### Custom WebGL/WebGPU renderer

Rejected because it rebuilds batching, assets, filters, input, device handling, and restoration without a product-level visual advantage.

### Single main thread

Rejected because one slow semantic step would freeze play and input.

### Shared-memory worker swarm

Rejected because shared-state races, isolation headers, security constraints, and debugging cost arrive before measurement justifies them.

### Bytecode or WASM before persistent interpretation

Rejected as premature. The existing performance evidence points first to repeated parse/module/run/serialization costs. Remove those costs and measure before changing execution representation.

## 28. Principal risks and mitigations

| Risk | Mitigation |
|---|---|
| visual quality falls below the approved promise | asset-compositor contract; engine-ready segmented assets; premium 2.5D slice before breadth; visual acceptance gate |
| Planes runtime misses simulation budget | persistent VM, no parse per tick, dirty systems, delta output, worker isolation, profile before bytecode/WASM |
| text protocol becomes a bottleneck | structured `show` typed observation with canonical-text compatibility |
| exact Planes numbers conflict with float performers | explicit fixed-point numeric bridge, approximation provenance, quantized physics input |
| world model becomes a generic ECS clone | user-facing seven facets, typed relations, affordance derivation, lineage and `why` as first-class contracts |
| agent bypasses child authorship | proposal envelope, no direct tools, structural gate, isolated Echo, child commit only |
| safeguards become opaque school surveillance | Visible Making Agreement, child-readable wakes, disclosed adult constraints, AI-off control, no covert profiling |
| cultural corpus is flattened or invented over | canonical/remixable/restricted/child-authored statuses, provenance, editorial promotion separate from play |
| school hardware is excluded | Semantic Fidelity Ladder, first-playable streaming, Safe Harbor, named reference-device gates |
| third-party framework changes break worlds | renderer-neutral IR, pinned vendored versions, protocol refusal, world-package versioning |
| no-build-step repository rule is eroded | browser-native `.mjs`, vendored distributions, derived Pages assembly, no runtime CDN or registry |
| scope expands into an unfinishable platform | first slice exclusions; phase-specific sub-specs and plans; proof gates before expansion |

## 29. Future seams deliberately preserved

After the first slice proves the product, the architecture can admit:

- more Ala Eriri districts and passages;
- richer subject and affordance registries;
- additional world generators;
- educator-authored agreements and curricula;
- private collaboration with explicit safety design;
- moderated publishing;
- asset generation through bounded registries;
- a 3D performer consuming the same World IR;
- local or on-device models;
- additional physics or animation performers;
- cross-world portals and libraries of child-authored seeds;
- Planes language additions only when the host protocols expose a repeated semantic need that libraries and records cannot honestly express.

None of these may weaken the semantic-source-of-truth rule, the child-commit rule, lineage, determinism, or the authority hierarchy.

## 30. Current primary-source technology findings

The design relies on current capabilities, not a claim that one library solves the product:

- PixiJS v8 documents WebGL/WebGPU renderers, recommends WebGL for production, and provides render layers, asset management, filters, particles, culling, texture caching, and accessibility overlays.
- Rapier provides JavaScript/WASM bindings, 2D and 3D engines, snapshots, sensors, and cross-platform deterministic JavaScript simulation when initialization and stepping are themselves deterministic.
- Web Workers provide isolated background execution and bounded message passing.
- AudioWorklet provides optional low-latency processing on the audio rendering thread.
- OffscreenCanvas exists as a future measured option, but rendering remains on the main thread initially because the Living Lens and accessibility layers already require coordinated DOM interaction and Pixi’s production path is mature there.

Primary references:

- <https://pixijs.com/8.x/guides/components/renderers>
- <https://pixijs.com/8.x/guides/concepts/render-layers>
- <https://pixijs.com/8.x/guides/components/accessibility>
- <https://pixijs.com/8.x/guides/components/assets>
- <https://pixijs.com/8.x/guides/concepts/performance-tips>
- <https://rapier.rs/docs/user_guides/javascript/determinism/>
- <https://rapier.rs/docs/user_guides/javascript/getting_started/>
- <https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API>
- <https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet>
- <https://developer.mozilla.org/en-US/docs/Web/API/OffscreenCanvas>

## 31. Approval record

The user explicitly approved:

- ages 10–13 as the first audience;
- player-facing world and visual builder on equal footing;
- Ala Eriri as the first living world and springboard;
- Planes as the agent-native semantic language;
- the co-builder as the agent’s first role;
- layered system/adult/child/agent authority;
- inside-out world-making;
- the Living Lens;
- Glance → Touch → Make;
- semantic affordances;
- Possibility Echoes;
- the Living World Seed;
- the Bidirectional Living Trace;
- the Visible Making Agreement;
- premium layered 2.5D first;
- PixiJS as modular performer;
- deterministic worker split;
- Semantic Fidelity Ladder;
- integrated architecture;
- child experience and progression;
- seven-facet World IR and structured `show` boundary;
- persistent runtime and performance architecture;
- agent/tutor/trust architecture;
- Horizon — The Living Passage as the first vertical slice.

## 32. Next gate

After written-spec approval, invoke the writing-plans process for **Phase 0 — Language and protocol substrate only**. Do not begin Pixi integration, world art production, or agent integration until Phase 0 has its own reviewed implementation plan and passes its conformance gates.
