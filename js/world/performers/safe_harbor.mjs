// js/world/performers/safe_harbor.mjs — the §15 Safe Harbor fallback
// performer (design doc §15, §22 "GPU failure"; build prompt §2/§3).
//
// MINIMAL BY DESIGN (build prompt §3): exists to preserve subject state and
// visibility when WebGL is unavailable or context loss outlasts
// restoration, not to reach feature or visual parity with the Pixi
// performer. Design doc §15: "It is an honest reduced performer, not a
// claim of visual parity." This performer does not pretend to be Pixi with
// a worse renderer — it is plain Canvas 2D, visibly, with no interpolation,
// no particles, no render-scale tiers. setParticleDensity/setRenderScale
// exist only so main.mjs can treat both performers through one interface;
// they are honest no-ops here, not a silently-dropped feature.
//
// Reuses mapWorldToScreen and colorForKind from pixi_performer.mjs (both
// pure, no Pixi/DOM dependency) so a subject lands in the same screen
// position and color whichever performer is active — a mid-session
// fallback (a real context-loss-past-restoration path) does not relocate
// or recolor the placeholder for a reason that has nothing to do with its
// semantic state.

import { mapWorldToScreen, colorForKind } from "./pixi_performer.mjs";

function cssColor(hexInt) {
  return `#${hexInt.toString(16).padStart(6, "0")}`;
}

export class SafeHarborPerformer {
  constructor(canvas) {
    if (!canvas) throw new TypeError("SafeHarborPerformer requires a canvas element");
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.subjects = new Map();
    this._raf = null;
    this._boundDraw = () => this._draw();
    this._raf = requestAnimationFrame(this._boundDraw);
  }

  // Same contract as pixi_performer.mjs's applyEnvelope: a full, current,
  // normalized world-v1 envelope.
  applyEnvelope(envelope) {
    const id = envelope.identity.id;
    const viewport = { width: this.canvas.width, height: this.canvas.height };
    const { x, y } = mapWorldToScreen(envelope.situation.x, envelope.situation.y, viewport);
    this.subjects.set(id, {
      x,
      y,
      kind: envelope.identity.kind,
      label: `${envelope.identity.displayName ?? id} (${id})`,
      state: envelope.behavior?.stateMachine ?? "",
    });
  }

  removeSubject(id) {
    this.subjects.delete(id);
  }

  // Honest no-ops — see module header.
  setParticleDensity() {}
  setRenderScale() {}

  _draw() {
    const { ctx, canvas } = this;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#12242c";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = "12px monospace";
    ctx.textAlign = "center";
    for (const subject of this.subjects.values()) {
      ctx.fillStyle = cssColor(colorForKind(subject.kind));
      ctx.fillRect(subject.x - 24, subject.y - 24, 48, 48);
      ctx.fillStyle = "#ffffff";
      ctx.fillText(subject.label, subject.x, subject.y + 40);
      if (subject.state) ctx.fillText(subject.state, subject.x, subject.y - 30);
    }
    this._raf = requestAnimationFrame(this._boundDraw);
  }

  // Same plain-data diagnostic shape as pixi_performer.mjs's snapshot().
  snapshot() {
    return Object.fromEntries(
      [...this.subjects.entries()].map(([id, s]) => [id, { current: { x: s.x, y: s.y }, target: { x: s.x, y: s.y } }]),
    );
  }

  spriteCount() {
    return this.subjects.size;
  }

  destroy() {
    if (this._raf !== null) cancelAnimationFrame(this._raf);
    this._raf = null;
  }
}

// Feature-detects whether a real WebGL context is obtainable at all —
// main.mjs calls this before ever attempting createPixiPerformer, so a
// device with no WebGL never even tries Pixi (design doc §15: "If WebGL is
// unavailable ... a separate Safe Harbor ... performer").
export function webglAvailable(testCanvas = null) {
  const canvas = testCanvas ?? (typeof document !== "undefined" ? document.createElement("canvas") : null);
  if (!canvas) return false;
  try {
    const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
    return Boolean(gl);
  } catch {
    return false;
  }
}
