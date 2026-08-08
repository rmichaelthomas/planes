// js/world/performers/pixi_performer.mjs — the Pixi v8 visual sink
// (design doc §10.1, build prompt §2/§3).
//
// TWO PROTOCOLS, ONE CLASS. `applyEnvelope` (below) is the Phase 1
// kernel-spike path — a flat colored rect keyed by kind, deliberately a
// placeholder (design doc §24.4). `applySceneIntent` (Horizon Phase 2
// Build 2, build prompt §3.3) is the crossing's real path: it consumes
// `parseSceneIntent`'s own output (js/scene/ir.mjs, imported not
// reimplemented — invariant 3) and renders the environment plate, the
// hydrofoil sprite, and every other subject as a positioned, colored,
// camera-transformed visual — not a placeholder rect, though also not the
// SVG stage's hand-authored vector art (a later Phase 2 art pass; §1's
// visual-acceptance bar is "preserve A Crossing's existing coherence in
// motion", not painterly parity). Both paths share this class because a
// real page only ever drives ONE of them (horizon.html: world-v1;
// horizon-crossing.html: scene-intent) but nothing stops a single Pixi
// app from carrying either — the world-v1 path is untouched below.
//
// SINGLE-SUBJECT TODAY, WRITTEN GENERIC ANYWAY (world-v1 path only). world-
// v1's delta protocol is single-subject by construction (see worker.mjs's
// own header), so today exactly one placeholder ever appears there. This
// class is still keyed by subject ID (a Map, not a single slot) so it
// needs no rewrite the day the protocol carries more than one.
//
// INTERPOLATION, NOT MUTATION. `applyEnvelope` only ever sets a sprite's
// TARGET position; `_onTick` (driven by Pixi's own ticker, i.e. the render
// frame rate, decoupled from the worker's 30 Hz tick rate) eases the
// rendered position toward that target. Nothing here writes back to a
// delta, an envelope, or any semantic value — presentation only, per design
// doc §11.2 and this build's own invariant 1.
//
// COORDINATE MAPPING IS A PRESENTATION CHOICE, STATED HONESTLY. situation.x
// in the reused kernel-spike fixture drifts unboundedly (`tick * 0.05`,
// never wraps) and situation.y oscillates in a tiny band around 4 — neither
// was authored to double as a screen-space layout. mapWorldToScreen wraps x
// into a repeating band and amplifies y's swing so the placeholder visibly
// moves in a bounded viewport. This is presentation math over the real
// semantic field, not a fake position: the same x/y this build's results
// doc reports came from the worker are what this function reads.

import * as PIXI from "../../vendor/pixi/pixi.min.mjs";

const SUBJECT_SIZE = 48;
const INTERP_RATE = 0.18;
const WORLD_BAND_WIDTH = 12;
const Y_AMPLIFY = 900;
const CONTEXT_RESTORE_TIMEOUT_MS = 4000;

const KIND_COLORS = {
  character: 0xe8734a,
  vehicle: 0x3fa7d6,
  structure: 0x8c6e4a,
  place: 0x4f8f6b,
};
const DEFAULT_COLOR = 0xb0b0b0;

export function colorForKind(kind) {
  return KIND_COLORS[kind] ?? DEFAULT_COLOR;
}

// Pure — no Pixi, no DOM. Unit-testable under plain node --test.
export function mapWorldToScreen(x, y, viewport) {
  const width = Math.max(1, viewport.width);
  const height = Math.max(1, viewport.height);
  const bandX = ((x % WORLD_BAND_WIDTH) + WORLD_BAND_WIDTH) % WORLD_BAND_WIDTH;
  const marginX = width * 0.08;
  const usableW = Math.max(1, width - marginX * 2);
  const screenX = marginX + (bandX / WORLD_BAND_WIDTH) * usableW;
  const midY = height * 0.55;
  const screenY = midY - (y - 4) * Y_AMPLIFY * (height / 900);
  return { x: screenX, y: screenY };
}

// ---- scene-intent rendering (Horizon Phase 2 Build 2) ---------------------
//
// The crossing's own world space: 1600x900, matching js/scene/a_crossing_
// stage.mjs's SVG viewBox exactly (same subject IDs, same normalized
// coordinate space, per scene-v1.json's "coordinates" section) — this is
// not an independent choice, it is the same authored space the SVG stage
// already renders, so a subject's Pixi position and its SVG position agree.

export const WORLD_WIDTH = 1600;
export const WORLD_HEIGHT = 900;

const ASSET_BASE = new URL("../../../assets/a-crossing/", import.meta.url);
const ENVIRONMENT_ASSET_URL = new URL("passage-environment.webp", ASSET_BASE).href;
const HYDROFOIL_ASSET_URL = new URL("hydrofoil.webp", ASSET_BASE).href;
const HYDROFOIL_ID = "hydrofoil";
const HYDROFOIL_WORLD_WIDTH = 190;

// One badge per non-hydrofoil subject this crossing's own Planes program
// names (paint/a_crossing.planes's own `show "scene subject ..."` lines) —
// no asset for these beyond what a_crossing_stage.mjs already draws as
// inline SVG vector shapes (invariant 4: no new art). Colors are a
// presentation choice roughly grouped by role (landing/structure/signal/
// creature), not a semantic field this build invented.
export const SUBJECT_VISUALS = {
  "reso-landing": { kind: "landing", color: 0x4a7c3f, radius: 50, label: "Reso" },
  "nkwo-eriri": { kind: "landing", color: 0x3f6a7c, radius: 50, label: "Nkwo Eriri" },
  "market": { kind: "structure", color: 0xd08a3e, radius: 22, label: "Market" },
  "kordas": { kind: "structure", color: 0x8a9c5e, radius: 24, label: "Kordas" },
  "fog-capture": { kind: "structure", color: 0x9fb8c9, radius: 20, label: "Fog capture" },
  "radio-mast": { kind: "signal", color: 0xe0a93b, radius: 16, label: "Radio mast" },
  "clinic-beacon": { kind: "signal", color: 0xd9683f, radius: 14, label: "Clinic" },
  "wave-array": { kind: "structure", color: 0x2f8fa6, radius: 20, label: "Wave array" },
  "petrels": { kind: "creature", color: 0xdedcd0, radius: 12, label: "Petrels" },
};
const DEFAULT_SUBJECT_VISUAL = { kind: "unknown", color: DEFAULT_COLOR, radius: 18, label: null };

// Pure — no Pixi, no DOM. Unit-testable under plain node --test. Scene-
// intent coordinates are normalized (scene-v1.json's own "coordinates"
// section: 0..1, origin top-left) — this just scales them into the shared
// 1600x900 world space above.
export function sceneToWorld(x, y) {
  return { x: x * WORLD_WIDTH, y: y * WORLD_HEIGHT };
}

// Pure. A standard "zoom centered on a focal point" transform: pivot moves
// the local origin to the camera's own focal point (camera.x/y, already in
// the 0..1 scene space), position re-centers that pivot back to the middle
// of the world box, and scale applies zoom. camera.x climbing from ~0.42 to
// ~0.58 as the crossing's own progress advances (a_crossing.planes's own
// `camera-x` derivation) reads as a pan; camera.zoom climbing from 1 to
// ~1.12 reads as the frame tightening on arrival — the same two motions
// a_crossing_stage.mjs's CSS `--camera-x`/`--camera-zoom` custom properties
// already produce, just expressed as a Pixi container transform instead.
export function cameraTransform(camera) {
  return {
    pivotX: camera.x * WORLD_WIDTH,
    pivotY: camera.y * WORLD_HEIGHT,
    x: WORLD_WIDTH / 2,
    y: WORLD_HEIGHT / 2,
    scale: camera.zoom,
  };
}

// Pure. A quadratic bezier standing in for a_crossing_stage.mjs's own
// hand-authored SVG cord path — not the same curve, but the same visual
// language (an arc lifting between the two landings), built from the
// scene-intent route record alone (fromX/Y, toX/Y — no new authored
// geometry). `segments` is a presentation-quality knob (§15's fidelity
// ladder does not touch it today; it is not itself semantic).
export function routeCurvePoints(route, segments = 24) {
  const from = sceneToWorld(route.fromX, route.fromY);
  const to = sceneToWorld(route.toX, route.toY);
  const controlX = (from.x + to.x) / 2;
  const controlY = Math.min(from.y, to.y) - 70;
  const points = [];
  for (let i = 0; i <= segments; i += 1) {
    const t = i / segments;
    const mt = 1 - t;
    points.push({
      x: mt * mt * from.x + 2 * mt * t * controlX + t * t * to.x,
      y: mt * mt * from.y + 2 * mt * t * controlY + t * t * to.y,
    });
  }
  return points;
}

// A scene subject's visual: the hydrofoil gets a real sprite (set once its
// texture loads); every other subject gets a colored, labeled badge (no
// asset exists for it — see SUBJECT_VISUALS's own header). Interpolation
// mirrors PlaceholderSprite's own tick() below exactly (same INTERP_RATE,
// same target/current split) — presentation easing only, per this file's
// invariant-1 discipline.
class SceneSubjectVisual {
  constructor(id, spec) {
    this.id = id;
    this.container = new PIXI.Container();
    this.container.eventMode = "static";
    this.container.cursor = "pointer";
    this.sprite = null;
    this.badge = null;
    if (id === HYDROFOIL_ID) {
      this.sprite = new PIXI.Sprite();
      this.sprite.anchor.set(0.5);
      this.container.addChild(this.sprite);
    } else {
      this.badge = new PIXI.Graphics()
        .circle(0, 0, spec.radius)
        .fill({ color: spec.color, alpha: 0.88 })
        .stroke({ width: 2, color: 0xfff4d6, alpha: 0.55 });
      this.container.addChild(this.badge);
      if (spec.label) {
        this.label = new PIXI.Text({
          text: spec.label,
          style: { fontFamily: "monospace", fontSize: 11, fill: 0xfff4e2, align: "center" },
        });
        this.label.anchor.set(0.5, 0);
        this.label.y = spec.radius + 3;
        this.container.addChild(this.label);
      }
    }
    this.selectionRing = new PIXI.Graphics()
      .circle(0, 0, (spec.radius ?? 60) + 12)
      .stroke({ width: 2.5, color: 0xfff5c9, alpha: 0.9 });
    this.selectionRing.visible = false;
    this.container.addChild(this.selectionRing);
    this.target = { x: 0, y: 0 };
    this.current = { x: 0, y: 0 };
    this._initialized = false;
  }

  setTexture(texture) {
    if (!this.sprite || !texture) return;
    this.sprite.texture = texture;
    const ratio = texture.height > 0 ? texture.height / texture.width : 1;
    this.sprite.width = HYDROFOIL_WORLD_WIDTH;
    this.sprite.height = HYDROFOIL_WORLD_WIDTH * ratio;
  }

  setTarget(x, y) {
    this.target.x = x;
    this.target.y = y;
    if (!this._initialized) {
      this.current.x = x;
      this.current.y = y;
      this.container.x = x;
      this.container.y = y;
      this._initialized = true;
    }
  }

  setVisible(visible) {
    this.container.visible = visible;
  }

  setSelected(selected) {
    this.selectionRing.visible = selected;
  }

  tick() {
    this.current.x += (this.target.x - this.current.x) * INTERP_RATE;
    this.current.y += (this.target.y - this.current.y) * INTERP_RATE;
    this.container.x = this.current.x;
    this.container.y = this.current.y;
  }
}

class PlaceholderSprite {
  constructor(id, kind) {
    this.id = id;
    this.container = new PIXI.Container();
    this.graphics = new PIXI.Graphics()
      .rect(-SUBJECT_SIZE / 2, -SUBJECT_SIZE / 2, SUBJECT_SIZE, SUBJECT_SIZE)
      .fill(colorForKind(kind));
    this.idLabel = new PIXI.Text({
      text: id,
      style: { fontFamily: "monospace", fontSize: 12, fill: 0xffffff, align: "center" },
    });
    this.idLabel.anchor.set(0.5, 0);
    this.idLabel.y = SUBJECT_SIZE / 2 + 4;
    this.stateLabel = new PIXI.Text({
      text: "",
      style: { fontFamily: "monospace", fontSize: 10, fill: 0xf0e6d2, align: "center" },
    });
    this.stateLabel.anchor.set(0.5, 1);
    this.stateLabel.y = -SUBJECT_SIZE / 2 - 4;
    this.container.addChild(this.graphics, this.idLabel, this.stateLabel);
    this.target = { x: 0, y: 0 };
    this.current = { x: 0, y: 0 };
    this._initialized = false;
  }

  setTarget(x, y, stateText) {
    this.target.x = x;
    this.target.y = y;
    if (stateText !== undefined) this.stateLabel.text = stateText;
    if (!this._initialized) {
      this.current.x = x;
      this.current.y = y;
      this.container.x = x;
      this.container.y = y;
      this._initialized = true;
    }
  }

  tick() {
    this.current.x += (this.target.x - this.current.x) * INTERP_RATE;
    this.current.y += (this.target.y - this.current.y) * INTERP_RATE;
    this.container.x = this.current.x;
    this.container.y = this.current.y;
  }
}

// A handful of drifting, non-semantic dots — the "placeholder particle
// density" the fidelity ladder (§15) adjusts. Deliberately keyed by nothing
// but an index: no subject, no semantic field, no source-map path. Purely
// decorative, so tier changes touching this can never be a semantic
// mutation (design doc §15's "never adaptive" list; §16 quality-tier-
// invariance gate).
class Motes {
  constructor(layer) {
    this.layer = layer;
    this.dots = [];
  }

  setCount(count, viewport) {
    while (this.dots.length > count) {
      const dot = this.dots.pop();
      this.layer.removeChild(dot.gfx);
    }
    while (this.dots.length < count) {
      const gfx = new PIXI.Graphics().circle(0, 0, 2 + Math.random() * 2).fill(0xffffff);
      gfx.alpha = 0.12 + Math.random() * 0.12;
      const dot = {
        gfx,
        x: Math.random() * viewport.width,
        y: Math.random() * viewport.height,
        vx: (Math.random() - 0.5) * 6,
        vy: (Math.random() - 0.5) * 6,
      };
      gfx.x = dot.x;
      gfx.y = dot.y;
      this.layer.addChild(gfx);
      this.dots.push(dot);
    }
  }

  tick(viewport, deltaSeconds) {
    for (const dot of this.dots) {
      dot.x = (dot.x + dot.vx * deltaSeconds + viewport.width) % viewport.width;
      dot.y = (dot.y + dot.vy * deltaSeconds + viewport.height) % viewport.height;
      dot.gfx.x = dot.x;
      dot.gfx.y = dot.y;
    }
  }
}

export class PixiPerformer {
  // app: an already-init()ed PIXI.Application. onContextLost/onContextRestored:
  // optional callbacks — main.mjs wires these to the §22 "attempt restoration
  // once within a bounded interval, then ... Safe Harbor" behavior. Pixi's own
  // GlContextSystem already listens on the same canvas and drives the actual
  // GL-level recovery (verified against PixiJS's own source before writing
  // this: it calls preventDefault() on 'webglcontextlost' and re-establishes
  // the context and its resources on 'webglcontextrestored') — these
  // callbacks are this build's OWN observation of that, not a reimplementation
  // of it.
  // onSelect: Horizon Phase 2 Build 2's own addition — called with a
  // subject id when its scene visual is clicked/tapped (build prompt §3.5:
  // "clicking a subject ... produces the same state transition"). main.mjs/
  // the crossing's own page wires this to `client.sendInput({kind:"select",
  // subject: id})`. Unused by the world-v1 path (applyEnvelope's
  // PlaceholderSprite is not interactive, unchanged from Phase 1).
  constructor(app, { onContextLost = null, onContextRestored = null, onSelect = null } = {}) {
    this.app = app;
    this.sprites = new Map();
    this.layer = new PIXI.Container();
    this._particleLayer = new PIXI.Container();
    this.app.stage.addChild(this._particleLayer);
    this.app.stage.addChild(this.layer);
    this._motes = new Motes(this._particleLayer);
    this._renderScale = 1;
    this._baseResolution = app.renderer.resolution;
    this._lastTickAt = performance.now();
    this._contextLostAt = null;
    this._restoreTimer = null;
    this._onContextLost = onContextLost;
    this._onContextRestored = onContextRestored;
    this._onSelect = onSelect;

    // Scene-intent state (Horizon Phase 2 Build 2) — lazily built by
    // _ensureSceneLayers() on the first applySceneIntent() call, so a page
    // that only ever drives the world-v1 path never pays for any of this.
    this._cameraContainer = null;
    this._worldLayer = null;
    this._environmentSprite = null;
    this._routeGraphics = null;
    this._sceneSubjectLayer = null;
    this._sceneSubjects = new Map();
    this._hydrofoilTexture = null;
    this._selectedSubjectId = null;
    this._lastIntent = null;

    this._boundTick = () => this._onTick();
    this.app.ticker.add(this._boundTick);

    this._boundLost = (event) => this._handleContextLost(event);
    this._boundRestored = () => this._handleContextRestored();
    this.app.canvas.addEventListener("webglcontextlost", this._boundLost, false);
    this.app.canvas.addEventListener("webglcontextrestored", this._boundRestored, false);
  }

  // envelope: a normalized world-v1 envelope (parseWorldEnvelope's own
  // shape) — either the initial full snapshot or main.mjs's running fold of
  // a snapshot plus every facet patch applied since. Always the FULL
  // current envelope, never a raw delta — this class never has to
  // understand patch semantics.
  applyEnvelope(envelope) {
    const id = envelope.identity.id;
    let sprite = this.sprites.get(id);
    if (!sprite) {
      sprite = new PlaceholderSprite(id, envelope.identity.kind);
      this.sprites.set(id, sprite);
      this.layer.addChild(sprite.container);
    }
    const viewport = { width: this.app.screen.width, height: this.app.screen.height };
    const { x, y } = mapWorldToScreen(envelope.situation.x, envelope.situation.y, viewport);
    sprite.setTarget(x, y, envelope.behavior?.stateMachine ?? "");
  }

  removeSubject(id) {
    const sprite = this.sprites.get(id);
    if (!sprite) return;
    this.layer.removeChild(sprite.container);
    this.sprites.delete(id);
  }

  // intent: parseSceneIntent's own output (js/scene/ir.mjs) — main.mjs
  // parses the worker's lines once and hands the result here (invariant 3:
  // consumed, never reimplemented, never re-derived from the worker's
  // internal world value). Every call carries the COMPLETE current scene
  // (a_crossing.planes re-emits every "scene ..." line unconditionally each
  // tick — there is no facet-patch fold to perform, unlike applyEnvelope
  // above), so this always fully re-applies camera/subjects/route.
  applySceneIntent(intent) {
    this._ensureSceneLayers();
    this._lastIntent = intent;

    const camera = cameraTransform(intent.camera);
    this._cameraContainer.pivot.set(camera.pivotX, camera.pivotY);
    this._cameraContainer.position.set(camera.x, camera.y);
    this._cameraContainer.scale.set(camera.scale);

    const present = new Set();
    for (const subject of intent.subjects) {
      present.add(subject.id);
      let visual = this._sceneSubjects.get(subject.id);
      if (!visual) {
        const spec = SUBJECT_VISUALS[subject.id] ?? { ...DEFAULT_SUBJECT_VISUAL, label: subject.id };
        visual = new SceneSubjectVisual(subject.id, spec);
        if (subject.id === HYDROFOIL_ID && this._hydrofoilTexture) visual.setTexture(this._hydrofoilTexture);
        visual.container.on("pointertap", () => this._onSelect?.(subject.id));
        this._sceneSubjects.set(subject.id, visual);
        this._sceneSubjectLayer.addChild(visual.container);
      }
      const { x, y } = sceneToWorld(subject.x, subject.y);
      visual.setTarget(x, y);
      visual.setVisible(subject.visibility !== "hidden");
      visual.setSelected(subject.id === this._selectedSubjectId);
    }
    for (const [id, visual] of [...this._sceneSubjects]) {
      if (present.has(id)) continue;
      this._sceneSubjectLayer.removeChild(visual.container);
      this._sceneSubjects.delete(id);
    }

    this._routeGraphics.clear();
    const route = intent.routes[0];
    if (route) {
      const points = routeCurvePoints(route);
      this._strokeRoutePath(points, 0xf4efe2, 0.3, 3);
      const traveledCount = Math.round(points.length * Math.max(0, Math.min(1, route.progress)));
      if (traveledCount > 1) this._strokeRoutePath(points.slice(0, traveledCount + 1), 0xffe9a5, 0.95, 4);
    }
  }

  _strokeRoutePath(points, color, alpha, width) {
    if (points.length < 2) return;
    this._routeGraphics.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i += 1) this._routeGraphics.lineTo(points[i].x, points[i].y);
    this._routeGraphics.stroke({ width, color, alpha });
  }

  // Programmatic selection (e.g. from a HUD "why" affordance, or to mirror
  // a selection the page itself already knows about) — the click path
  // above (onSelect) is the other way a subject becomes selected.
  selectSceneSubject(id) {
    this._selectedSubjectId = id;
    for (const [subjectId, visual] of this._sceneSubjects) visual.setSelected(subjectId === id);
  }

  _ensureSceneLayers() {
    if (this._cameraContainer) return;
    this._environmentSprite = new PIXI.Sprite();
    this._environmentSprite.width = WORLD_WIDTH;
    this._environmentSprite.height = WORLD_HEIGHT;
    this._routeGraphics = new PIXI.Graphics();
    this._sceneSubjectLayer = new PIXI.Container();
    this._worldLayer = new PIXI.Container();
    this._worldLayer.addChild(this._environmentSprite, this._routeGraphics, this._sceneSubjectLayer);
    this._cameraContainer = new PIXI.Container();
    this._cameraContainer.addChild(this._worldLayer);
    this.app.stage.addChildAt(this._cameraContainer, 0);
    this._loadSceneTextures();
  }

  // Presentation-only and non-fatal by construction: a failed/slow asset
  // load must never touch the semantic pipeline (this file's own invariant
  // 1) — it just means the environment/hydrofoil render blank or as their
  // default Pixi texture until (if ever) this resolves.
  async _loadSceneTextures() {
    try {
      const [environmentTexture, hydrofoilTexture] = await Promise.all([
        PIXI.Assets.load(ENVIRONMENT_ASSET_URL),
        PIXI.Assets.load(HYDROFOIL_ASSET_URL),
      ]);
      if (this._environmentSprite) this._environmentSprite.texture = environmentTexture;
      this._hydrofoilTexture = hydrofoilTexture;
      const boat = this._sceneSubjects.get(HYDROFOIL_ID);
      if (boat) boat.setTexture(hydrofoilTexture);
    } catch {
      // See method header — a render-layer failure, not a semantic one.
    }
  }

  // Plain-data diagnostic snapshot of the scene-intent path, parallel to
  // snapshot() below (world-v1's own). Used by this build's render-presence
  // check (§6.2.F: "the hydrofoil sprite at a non-placeholder position").
  sceneSnapshot() {
    return Object.fromEntries(
      [...this._sceneSubjects.entries()].map(([id, v]) => [
        id,
        { current: { ...v.current }, target: { ...v.target }, visible: v.container.visible },
      ]),
    );
  }

  // Mechanism, not policy — fidelity_controller.mjs decides the count per
  // tier and calls this. 0 is a valid tier choice (Harbor).
  setParticleDensity(count) {
    const viewport = { width: this.app.screen.width, height: this.app.screen.height };
    this._motes.setCount(count, viewport);
  }

  // Mechanism, not policy. scale is in (0, 1] — fidelity_controller.mjs
  // supplies the tier's target. Adjusts the renderer's actual backing-store
  // resolution (not just a visual transform), matching design doc §15's
  // "adaptive render scale".
  setRenderScale(scale) {
    this._renderScale = scale;
    this.app.renderer.resolution = this._baseResolution * scale;
    this.app.renderer.resize(this.app.screen.width, this.app.screen.height);
  }

  _onTick() {
    const now = performance.now();
    const deltaSeconds = Math.min(0.25, (now - this._lastTickAt) / 1000);
    this._lastTickAt = now;
    for (const sprite of this.sprites.values()) sprite.tick();
    for (const visual of this._sceneSubjects.values()) visual.tick();
    this._motes.tick({ width: this.app.screen.width, height: this.app.screen.height }, deltaSeconds);
  }

  _handleContextLost(event) {
    event.preventDefault();
    this._contextLostAt = performance.now();
    this._onContextLost?.();
    this._restoreTimer = setTimeout(() => {
      if (this._contextLostAt !== null) this._onContextLost?.("timeout");
    }, CONTEXT_RESTORE_TIMEOUT_MS);
  }

  _handleContextRestored() {
    this._contextLostAt = null;
    if (this._restoreTimer !== null) {
      clearTimeout(this._restoreTimer);
      this._restoreTimer = null;
    }
    this._onContextRestored?.();
  }

  // Plain-data diagnostic snapshot — no Pixi objects — for the frame bench
  // and verify script to assert against (build prompt §6.2.A: "the
  // performer's sprite state matches the worker's final envelope
  // positions").
  snapshot() {
    return Object.fromEntries(
      [...this.sprites.entries()].map(([id, s]) => [
        id,
        { current: { ...s.current }, target: { ...s.target } },
      ]),
    );
  }

  spriteCount() {
    return this.sprites.size;
  }

  destroy() {
    this.app.ticker.remove(this._boundTick);
    this.app.canvas.removeEventListener("webglcontextlost", this._boundLost, false);
    this.app.canvas.removeEventListener("webglcontextrestored", this._boundRestored, false);
    if (this._restoreTimer !== null) clearTimeout(this._restoreTimer);
    for (const id of [...this.sprites.keys()]) this.removeSubject(id);
    for (const [id, visual] of [...this._sceneSubjects]) {
      this._sceneSubjectLayer?.removeChild(visual.container);
      this._sceneSubjects.delete(id);
    }
  }
}

// Constructs and initializes the PIXI.Application (§10.1: "production
// defaulting to stable WebGL" — preference is stated explicitly rather than
// relied on as an unstated default). Returns { app, performer }.
export async function createPixiPerformer({ container, onContextLost, onContextRestored, onSelect } = {}) {
  const app = new PIXI.Application();
  await app.init({
    resizeTo: container ?? window,
    preference: "webgl",
    backgroundAlpha: 0,
    antialias: true,
    resolution: (typeof window !== "undefined" ? window.devicePixelRatio : 1) || 1,
    autoDensity: true,
  });
  if (container) container.appendChild(app.canvas);
  const performer = new PixiPerformer(app, { onContextLost, onContextRestored, onSelect });
  return { app, performer };
}
