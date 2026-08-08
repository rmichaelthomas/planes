// js/world/runtime/main.mjs — the main-thread orchestrator (design doc
// §11.2, build prompt §2/§3).
//
// Owns: spawning the worker, message discipline (§11.5 — sequence and
// cancellation-token admission, discarding stale/out-of-order messages
// rather than applying them late), folding the delta stream into a running
// per-subject envelope mirror, handing that mirror to the Pixi performer
// and DOM mirror, driving the fidelity controller, and falling back to Safe
// Harbor on missing/lost WebGL. It never runs simulation and never mutates
// semantic state — every value it touches came from a worker message; every
// value it hands a performer is that same value, at most re-expressed
// (folded onto a running copy), never invented.
//
// SPLIT FOR TESTABILITY. MessageGate and foldDelta are pure — no DOM, no
// Worker, no Pixi — importable and testable under plain `node --test`
// exactly like worker.mjs's SimulationWorkerHandle. WorldClient is the
// orchestration core: constructed with an injected worker-like object
// (anything with postMessage) and injected performers, so it, too, is
// testable without a real Worker or GPU. Only boot() at the bottom touches
// `document`/`Worker`/a real canvas.

import { createPixiPerformer } from "../performers/pixi_performer.mjs";
import { SafeHarborPerformer, webglAvailable } from "../performers/safe_harbor.mjs";
import { DomMirror } from "../performers/dom_mirror.mjs";
import { FidelityController } from "../performers/fidelity_controller.mjs";

// ---- message discipline (§11.5) --------------------------------------------
//
// A message is admitted only if its cancellation token matches the one
// currently active AND its sequence is strictly greater than the last
// admitted sequence. The first message received adopts its token as the
// baseline (the worker generates its own initial token — see worker.mjs);
// main.mjs can later move the baseline itself via adoptCancellationToken,
// which is what makes a stale in-flight message from before a reset
// correctly recognized as stale even though it arrives after the reset.
export class MessageGate {
  constructor() {
    this.lastAppliedSequence = 0;
    this.activeCancellationToken = null;
    this.admittedCount = 0;
    this.discardedCount = 0;
  }

  admit(message) {
    if (this.activeCancellationToken === null) {
      this.activeCancellationToken = message.cancellationToken;
    } else if (message.cancellationToken !== this.activeCancellationToken) {
      this.discardedCount += 1;
      return false;
    }
    if (typeof message.sequence !== "number" || message.sequence <= this.lastAppliedSequence) {
      this.discardedCount += 1;
      return false;
    }
    this.lastAppliedSequence = message.sequence;
    this.admittedCount += 1;
    return true;
  }

  adoptCancellationToken(token) {
    this.activeCancellationToken = token;
  }
}

// Pure. Applies one delta's facetPatches/relation changes onto a COPY of
// `envelope`, returning the new envelope — never mutates its argument.
// Returns null when the delta replaces the subject outright (createdSubjects/
// removedSubjects non-empty): folding a patch list cannot synthesize a
// brand-new subject's full envelope, so the caller must wait for a fresh
// snapshot rather than guess.
export function foldDelta(envelope, delta) {
  if (delta.createdSubjects.length > 0 || delta.removedSubjects.length > 0) return null;
  const next = structuredClone(envelope);
  for (const patch of delta.facetPatches) {
    if (!next[patch.facet]) next[patch.facet] = {};
    next[patch.facet][patch.field] = patch.new;
  }
  if (delta.relationsRemoved.length > 0) delete next.relation;
  if (delta.relationsAdded.length > 0) next.relation = { ...delta.relationsAdded[delta.relationsAdded.length - 1] };
  return next;
}

function subjectIdOfDelta(delta) {
  return delta.facetPatches[0]?.id ?? delta.relationsAdded[0]?.fromId ?? delta.relationsRemoved[0]?.fromId ?? null;
}

// ---- orchestration core ------------------------------------------------

export class WorldClient {
  constructor({ worker, performer, domMirror = null, fidelityController = null } = {}) {
    if (!worker || typeof worker.postMessage !== "function") {
      throw new TypeError("WorldClient requires a worker-like object with postMessage");
    }
    if (!performer || typeof performer.applyEnvelope !== "function") {
      throw new TypeError("WorldClient requires a performer with applyEnvelope");
    }
    this.worker = worker;
    this.performer = performer;
    this.domMirror = domMirror;
    this.fidelityController = fidelityController;
    this.gate = new MessageGate();
    this.envelopes = new Map();
    this.pendingInputs = new Map();
    this.inputSequence = 0;
    // stepMsSamples: the worker's own per-tick elapsedSeconds (renamed
    // stepMs on the wire), one entry per admitted delta — this is the
    // "simulation step (worker)" distribution build prompt §16/§6.2.G asks
    // frame_bench.mjs to report SEPARATELY from main-thread frame time.
    this.metrics = { snapshotsApplied: 0, deltasApplied: 0, discarded: 0, errors: [], stepMsSamples: [] };
  }

  // Swap the active visual performer (Pixi -> Safe Harbor on a lost cause,
  // per design doc §22). Re-hydrates the new performer with every envelope
  // already known, so the fallback does not start blank.
  setPerformer(performer) {
    this.performer = performer;
    for (const envelope of this.envelopes.values()) this.performer.applyEnvelope(envelope);
  }

  handleWorkerMessage(message) {
    if (!message || typeof message !== "object") return;
    if (message.type === "error") {
      this.metrics.errors.push(message.message);
      return;
    }
    if (!this.gate.admit(message)) {
      this.metrics.discarded += 1;
      return;
    }
    if (message.type === "snapshot") {
      this.envelopes.set(message.envelope.identity.id, message.envelope);
      this._applyToPerformers(message.envelope);
      this.metrics.snapshotsApplied += 1;
    } else if (message.type === "delta") {
      this._applyDelta(message.delta);
      this.metrics.deltasApplied += 1;
      if (typeof message.stepMs === "number") this.metrics.stepMsSamples.push(message.stepMs);
    }
    this._resolvePendingInputs(message.acknowledgedInputSequence);
  }

  _applyDelta(delta) {
    for (const removedId of delta.removedSubjects) this._removeSubject(removedId);
    for (const createdId of delta.createdSubjects) {
      // Honestly logged, not silently dropped — see foldDelta's own
      // contract. Today's single-subject fixture never actually takes this
      // branch (build prompt §2's protocol-scope note), but a generic
      // client does not assume that stays true forever.
      this.metrics.errors.push(
        `subject '${createdId}' created but no snapshot received for it yet — cannot fold, awaiting a snapshot`,
      );
    }
    if (delta.facetPatches.length === 0 && delta.relationsAdded.length === 0 && delta.relationsRemoved.length === 0) {
      return;
    }
    const id = subjectIdOfDelta(delta);
    const current = id === null ? undefined : this.envelopes.get(id);
    if (!current) {
      this.metrics.errors.push(`delta for unknown subject '${id}' — no snapshot on file`);
      return;
    }
    const next = foldDelta(current, delta);
    if (next === null) return;
    this.envelopes.set(id, next);
    this._applyToPerformers(next);
  }

  _applyToPerformers(envelope) {
    this.performer.applyEnvelope(envelope);
    this.domMirror?.applyEnvelope(envelope);
  }

  _removeSubject(id) {
    this.envelopes.delete(id);
    this.performer.removeSubject(id);
    this.domMirror?.removeSubject(id);
  }

  // The build prompt §4 "input to visible response" measurement: a
  // synthetic direct-manipulation poke, sent to the worker, resolved once
  // the worker's ACKNOWLEDGMENT (not application — see worker.mjs's header
  // on why advance() cannot yet be steered) has been admitted by the
  // message gate and the browser has painted a frame after that. Returns a
  // Promise<milliseconds>.
  pokeSubject() {
    this.inputSequence += 1;
    const sequence = this.inputSequence;
    const sentAt = performance.now();
    this.worker.postMessage({ type: "input", sequence, sentAt });
    return new Promise((resolve) => {
      this.pendingInputs.set(sequence, { resolve, sentAt });
    });
  }

  _resolvePendingInputs(acknowledgedInputSequence) {
    if (typeof acknowledgedInputSequence !== "number") return;
    for (const [sequence, pending] of [...this.pendingInputs.entries()]) {
      if (sequence > acknowledgedInputSequence) continue;
      this.pendingInputs.delete(sequence);
      // Two nested rAFs: the first fires before the browser paints this
      // frame's changes, the second after — "visible" should mean painted,
      // not merely applied to a scene graph.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          pending.resolve(performance.now() - pending.sentAt);
        });
      });
    }
  }
}

// ---- real page wiring — the only part of this file that touches
// `document`/`Worker`/a live canvas. Mirrors browser_main.mjs's own guard
// pattern so this module stays importable (and WorldClient/MessageGate/
// foldDelta unit-testable) under plain `node --test`.

export async function boot({ pixiContainer, domMirrorContainer, safeHarborCanvas } = {}) {
  let performer;
  let usingPixi = webglAvailable();
  let pixiHandle = null;

  const attachSafeHarbor = () => {
    const fallback = new SafeHarborPerformer(safeHarborCanvas);
    if (pixiContainer) pixiContainer.hidden = true;
    if (safeHarborCanvas) safeHarborCanvas.hidden = false;
    usingPixi = false;
    // Co-located with the visibility toggles above rather than left for the
    // caller to notice: a fallback that happens well after boot() already
    // returned (a context-loss timeout, not the initial WebGL-unavailable
    // case) needs this updated live, not just at the caller's one-time read
    // of boot()'s return value.
    if (typeof document !== "undefined") document.body.dataset.performer = "safe-harbor";
    return fallback;
  };

  if (usingPixi) {
    try {
      pixiHandle = await createPixiPerformer({
        container: pixiContainer,
        onContextLost: (reason) => {
          if (reason === "timeout") {
            client.setPerformer(attachSafeHarbor());
            client.fidelityController = null;
          }
        },
      });
      performer = pixiHandle.performer;
      if (safeHarborCanvas) safeHarborCanvas.hidden = true;
    } catch {
      performer = attachSafeHarbor();
    }
  } else {
    performer = attachSafeHarbor();
  }

  const domMirror = domMirrorContainer ? new DomMirror(domMirrorContainer) : null;
  const fidelityController = usingPixi ? new FidelityController({ performer }) : null;

  const worker = new Worker(new URL("./worker.mjs", import.meta.url), { type: "module" });
  const client = new WorldClient({ worker, performer, domMirror, fidelityController });
  worker.addEventListener("message", (event) => client.handleWorkerMessage(event.data));

  return { client, pixiApp: pixiHandle?.app ?? null, usingPixi };
}

// Deliberately no auto-boot guard here (unlike browser_main.mjs's own
// document.getElementById("run")-etc. pattern). horizon.html is this
// module's only consumer, and it always calls boot() itself, from its own
// inline script, so it can wire the fidelity-tier buttons, the poke
// button, and the metrics readout to the returned client — a second,
// automatic boot() here raced that explicit one, producing two Workers and
// a doubled DOM mirror (caught in this build's own live-browser
// verification, not left in). If a future page wants a no-wiring default
// boot, give it its own distinctly-guarded block, not this one revived.
