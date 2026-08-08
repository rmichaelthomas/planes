# a_crossing_checkpoint_v1_0_nine_landings.md

# CANONICAL CHECKPOINT DOCUMENT
## A Crossing / Nine Landings
### v1.0 — Passage becomes the playable proof: a build-design checkpoint

**Status:** LOCKED — FIRST PROJECT-LOCAL CHECKPOINT  
**Date:** August 01, 2026  
**Author:** Rob Thomas / R. Michael Thomas (architect) and Codex (analytical and design partner)  
**Domain prefix:** `a_crossing` — provisional, project-local  
**Session type:** Design reframing and build-specification checkpoint  
**Relationship to prior checkpoints:** No prior A Crossing/Nine Landings checkpoint exists in `docs/` or `reports/` as searched on August 01, 2026. This begins the project-local chain.

> *The crossing is the proof: a visible decision that remains accountable to the world it changes.*

## HOW TO READ THIS DOCUMENT

This document records how a broad Planes sandbox became a specific playable demonstration. It locks the design decisions, source boundaries, visual correction, and performance posture that future design and implementation sessions must inherit. It does not claim that production code has been built. The companion engineering specification is `docs/superpowers/specs/2026-08-01-a-crossing-nine-landings-design.md`.

## PART I — THE OPEN SANDBOX

### §1.1 The original question

**Decision: Garden's proof of visual and interactive Planes should be extended, not repeated. LOCKED.**

The starting question was open-ended: given Garden's movement, sound, granular clickable marks, seeded variation, and explainability, what should be built next? The first answer was `The Commons`, a generic civic sandbox. It established useful technical commitments—Planes-owned state, pointer/keyboard input, `when` dispatch, replayable seeds, sound, provenance, and object selection—but its fictional town was not yet a singular world.

### §1.2 The named gap

**Decision: A generic town does not use Planes' expressive range or the available world corpus fully enough. LOCKED.**

The first mockup became a low-detail canvas sketch. Rob identified it as a visual regression from Garden and the earlier rich promise. That feedback clarified a permanent standard: a technical prototype may explain interaction flow, but it is never the visual bar. The task required a world with its own internal logic, visual specificity, and material stakes.

## PART II — THE ALA ERIRI REFRAME

### §2.1 Canon becomes build material

**Decision: Ala Eriri's binder is canonical design input; factbook and encyclopedia are supporting renders. LOCKED.**

The supplied corpus introduced a complete fictional archipelago: nine volcanic islands; the Passage, Watershed, Fishery, Ledger, Landing, and Verification jurisdictions; a Registry of Continuity; hydrofoils; market cycles; *rolu grandi* swell; fog capture and wave energy; cord-anchored terraces; a provenance culture; and deliberate unresolved civic questions.

The insight was structural rather than cosmetic: the country already describes a language-native world of conditions, outcomes, continuity, evidence, and declared revision. Those are direct counterparts to Planes' state, `when`, trace, Shapes, and provenance capabilities.

### §2.2 The chosen proof

**Decision: Passage is the first scenario. LOCKED.**

The user selected Passage over managed retreat. The standard—access to employment, primary care, and secondary education within 90 minutes—gives movement visible stakes without reducing the system to logistics. It ties weather, energy, water, ferry service, care, education, markets, and outcome jurisdictions together.

## PART III — THE EXPERIENCE IS NAMED

### §3.1 A Crossing

**Decision: The product experience is `A Crossing`, not a city-management dashboard. LOCKED.**

The visitor follows a simulated resident's hydrofoil crossing between islands. They may make bounded route, power, radio, or landing-support decisions. The program may preserve, delay, or honestly refuse a crossing. There is no win/loss score, no claim that a real service was dispatched, and no independent JavaScript decision model.

### §3.2 The Registry becomes interaction grammar

**Decision: Meaningful decisions emit a Statement of Revision. LOCKED.**

The Statement of Revision is the in-world expression of the Registry of Continuity: it shows what changed, what remains standing, why the condition mattered, and what tradeoff remains. It is generated from captured Planes state/output/provenance, not invented after the fact by interface code.

## PART IV — THE HORIZON BECOMES THE CAMERA

### §4.1 The two spatial alternatives

**Decision: Horizon Crossing opens the experience; the Nine Landings atlas is secondary. LOCKED.**

Two visual compositions were evaluated. `Horizon Crossing` places one resident's journey at human scale, with other islands acting as depth and consequence. `Atlas Crossing` makes the whole country legible at once. The horizon was selected for the opening because it preserves intimacy; the atlas remains valuable as a replay and inspection view.

### §4.2 The route cord

**Decision: An unbroken ivory cord is the central spatial and explanatory device. LOCKED.**

The cord grows from origin through the moving ferry route toward destination. It can twist, reroute, or pause under changing conditions, but it never silently vanishes. This connects the country’s flag, recordkeeping, and continuity principle to an immediately readable Planes state transition.

## PART V — VISUAL CORRECTION

### §5.1 The rejected tone

**Decision: Dark, medieval-European port imagery is excluded. LOCKED.**

The first Ala Eriri visual direction proved composition but carried a dark stormy English-port mood. Rob approved its crossing layout while explicitly correcting the tonal mismatch: Ala Eriri should be more cheerful, more Caribbean-island/Atlantic in spirit, and much more responsive to its cultural anchors.

### §5.2 The current visual anchor

**Decision: Bright, contemporary Atlantic island life is the visual anchor. LOCKED.**

The approved revision uses turquoise and ultramarine water, coral/terracotta landing materials, bright slopes, market life, contemporary electric hydrofoils, fog mesh, radio, wave infrastructure, birds, and luminous post-squall weather. It remains serious about conditions and civic consequence without becoming foreboding, resort-generic, pirate fantasy, or decorative pastiche.

Visual asset: `docs/superpowers/specs/assets/2026-08-01-a-crossing-ala-eriri-visual-direction-v2.png`.

## PART VI — SEMANTIC AND PERFORMANCE ARCHITECTURE

### §6.1 Ownership boundary

**Decision: Planes owns the world; JavaScript owns the stage. LOCKED.**

Planes owns seed, weather, swell, energy, need, route, Passage result, next state, output, and explanation values. JavaScript receives input, advances the shared loop, renders actual output, builds hit regions, manages browser audio, and formats observed values. JavaScript does not choose an outcome.

### §6.2 Smoothness through attention tiers

**Decision: Simulate one crossing deeply and the archipelago suggestively. LOCKED.**

The active runtime has a compact world record and one active crossing. Continuous atmosphere is cheap; high-detail motion, hit regions, sound, and explanation are concentrated on the active route and selection. The atlas does not continuously simulate all nine islands at cinematic density. The first optimization, if measurement demands one, is session-scoped immutable program-artifact caching with semantic-equivalence proof.

### §6.3 Determinism

**Decision: Surprise enters only through a displayed, replayable seed. LOCKED.**

`Roll` samples browser entropy once and immediately exposes a numeric seed. The same seed and ordered input-event sequence must reproduce state, output, effects, errors, and provenance. No hidden ambient randomness is permitted.

## PART VII — INTEGRITY CONDITIONS

### §7.1 Canon and culture

**Decision: Canon is data, not garnish. LOCKED.**

The binder's locked/unresolved distinction governs all use of Ala Eriri. The build cannot resolve its live disputes, invent unverified cultural motifs, infer the pronunciation of `Eriri`, or turn cultural history into a decorative game skin.

### §7.2 Accessibility and truthfulness

**Decision: Every active element is inspectable and accessible; every outcome is called simulated. LOCKED.**

Keyboard access, reduced motion, visible sound controls, and text equivalents are acceptance conditions. Source, effects, static boundary, and trace remain distinct. The page never presents a simulated boat movement as a host action or real service.

## WHAT IS LOCKED

- Ala Eriri is the world and source corpus for this demonstration.
- `A Crossing` is the experience name and is centered on Passage.
- Horizon Crossing is the opening camera; Nine Landings atlas is secondary inspection/replay.
- A simulated hydrofoil route from Reso toward Nkwo Eriri is the first scenario.
- Planes owns world decisions; JavaScript renders and captures input only.
- `when` dispatch, state threading, sound, granular object selection, fixed-seed replay, and provenance are all part of the proof.
- The Statement of Revision is the core explanation form.
- Bright, joyful, contemporary Atlantic-island tone is mandatory; dark medieval-European port imagery is excluded.
- One crossing receives dense simulation; broader world detail is attention-tiered for smoothness.

## WHAT IS NOT LOCKED

- Exact module imports and page-specific JavaScript component boundaries, pending a source audit and implementation plan.
- Exact resident narrative, destination need, and the initial set of bounded interventions.
- Exact runtime budgets, pending benchmark measurement on a declared reference environment.
- Exact use and presentation of the supplied pronunciation recording.
- Later scenarios: managed retreat, market cycle, Ledger/provenance, health, or other outcome jurisdictions.

## WHAT IS LOGGED

- Garden remains the visual and technical sibling/anchor.
- The original Commons document remains an historical design artifact, not the current build target.
- A flow-only HTML mockup exists but is explicitly not a visual-quality reference.
- The corpus includes real-world source material as well as fictional canon; build output must preserve the binder's source boundaries.

---

## UPDATED OPEN QUESTIONS (v1.0 status)

| # | Question | Status |
|---|---|---|
| AC-1 | Which simulated reason initiates the first Reso → Nkwo Eriri crossing: primary care, education, or work? | Open — implementation content choice |
| AC-2 | Which interventions are available in the first build, and which should be visible but unavailable? | Open — constrain after source audit |
| AC-3 | How is the provided pronunciation recording presented without implying a phonetic transcription? | Open — requires content/audio treatment |
| AC-4 | What performance budgets are appropriate for the supported browser/device baseline? | Open — measurement required |
| AC-5 | Does the secondary atlas become interactive in v1 or remain a replay/inspection view? | Open — scope decision after core crossing works |

## DOCUMENTS PRODUCED THIS SESSION

| Document | Type | Status |
|---|---|---|
| `docs/superpowers/specs/2026-08-01-a-crossing-nine-landings-design.md` | Engineering design specification | Complete; awaiting review |
| `reports/a_crossing_checkpoint_v1_0_nine_landings.md` | Checkpoint / future-reference record | Complete, LOCKED |

## RESUME PROMPT (v1.0)

*Resume from `a_crossing_checkpoint_v1_0_nine_landings.md` and the approved design specification `2026-08-01-a-crossing-nine-landings-design.md`. All v1.0 locked decisions are in force: build `A Crossing`, a local deterministic Planes demonstration in Ala Eriri, centered on a simulated Reso → Nkwo Eriri Passage crossing; use Horizon Crossing as the first camera and the Nine Landings atlas as a secondary inspection/replay surface; let Planes own seed, state, conditions, decisions, output, and provenance while JavaScript renders and gathers input only; use `when`, existing tick/input/state routes, granular object selection, optional sound, fixed-seed replay, and a Statement of Revision; retain a bright, contemporary Atlantic-island tone and exclude dark medieval-European port imagery. No production A Crossing code has been built (verified: only design assets/specs were added in this session); before implementation, inspect current Garden/Paint interfaces and resolve AC-1 through AC-4 enough to create a detailed implementation plan. Do not build a generic town, a real service integration, a separate JavaScript rules engine, or continuous full-archipelago simulation.*
