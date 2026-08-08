// js/world/performers/fidelity_controller.mjs — the Semantic Fidelity
// Ladder controller (design doc §15, build prompt §2/§3).
//
// POLICY, NOT MECHANISM. This file decides what Sun/Breeze/Harbor MEAN
// (render scale, placeholder particle density, target frame budget); it
// never touches the worker, a delta, or an envelope. The mechanism —
// actually changing the renderer's resolution or particle count — lives in
// pixi_performer.mjs (setRenderScale/setParticleDensity). That split is
// what makes design doc §15's "never adaptive: Planes decisions, semantic
// subjects, ... save compatibility" true BY CONSTRUCTION here: there is no
// code path from this file to the worker, so no tier change can reach
// semantic state even by accident. §16's quality-tier-invariance gate reads
// as a structural fact about this file's own import graph, not just a
// runtime assertion — grep this file for "worker" or "postMessage" and
// find neither.
//
// Tier switching is explicit (setTier), not auto-adaptive on measured FPS.
// The build prompt's own scope is proving the tier SWITCH works cleanly,
// not shipping a quality-auto-tuning algorithm — that would be additional,
// undemonstrated complexity beyond what this build asks for.

export const TIERS = Object.freeze({
  sun: Object.freeze({ renderScale: 1, particleDensity: 24, frameBudgetMs: 16.7 }),
  breeze: Object.freeze({ renderScale: 0.85, particleDensity: 12, frameBudgetMs: 22 }),
  harbor: Object.freeze({ renderScale: 0.65, particleDensity: 0, frameBudgetMs: 33.3 }),
});

export const TIER_NAMES = Object.freeze(Object.keys(TIERS));

export class FidelityController {
  constructor({ performer, initialTier = "sun" } = {}) {
    if (!performer || typeof performer.setRenderScale !== "function") {
      throw new TypeError("FidelityController requires a performer with setRenderScale/setParticleDensity");
    }
    this.performer = performer;
    this.tier = null;
    this.setTier(initialTier);
  }

  setTier(tierName) {
    const tier = TIERS[tierName];
    if (!tier) {
      throw new RangeError(`unknown fidelity tier '${tierName}' — expected one of ${TIER_NAMES.join(", ")}`);
    }
    this.tier = tierName;
    this.performer.setRenderScale(tier.renderScale);
    this.performer.setParticleDensity(tier.particleDensity);
    return tier;
  }

  current() {
    return { name: this.tier, ...TIERS[this.tier] };
  }

  frameBudgetMs() {
    return TIERS[this.tier].frameBudgetMs;
  }
}
