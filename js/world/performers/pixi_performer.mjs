// js/world/performers/pixi_performer.mjs — the Pixi v8 visual sink
// (design doc §10.1, build prompt §2/§3).
//
// PLACEHOLDER, DELIBERATELY. Every subject renders as a flat colored rect
// keyed by kind, with its semantic ID as a visible debug label — never
// anything that could be mistaken for Reso Landing (design doc §24.4; build
// prompt §1/§8). This file proves the wiring — a delta's semantic position
// reaching a moving, interpolated sprite — not the art.
//
// SINGLE-SUBJECT TODAY, WRITTEN GENERIC ANYWAY. world-v1's delta protocol is
// single-subject by construction (see worker.mjs's own header), so today
// exactly one placeholder ever appears. This class is still keyed by
// subject ID (a Map, not a single slot) so it needs no rewrite the day the
// protocol carries more than one.
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
  constructor(app, { onContextLost = null, onContextRestored = null } = {}) {
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
  }
}

// Constructs and initializes the PIXI.Application (§10.1: "production
// defaulting to stable WebGL" — preference is stated explicitly rather than
// relied on as an unstated default). Returns { app, performer }.
export async function createPixiPerformer({ container, onContextLost, onContextRestored } = {}) {
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
  const performer = new PixiPerformer(app, { onContextLost, onContextRestored });
  return { app, performer };
}
