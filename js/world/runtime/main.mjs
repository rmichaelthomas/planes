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
// Consumed, never reimplemented (invariant 3) — the scene-intent boundary
// a crossing's messages carry (Horizon Phase 2 Build 2, build prompt §3.3).
import { parseSceneIntent } from "../../scene/ir.mjs";

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
    // A performer must support at least one of the two protocols this
    // client can receive: applyEnvelope (world-v1) or applySceneIntent
    // (scene-intent, Horizon Phase 2 Build 2). Most performers only ever
    // see one protocol in practice, so neither is required alone.
    if (!performer || (typeof performer.applyEnvelope !== "function"
        && typeof performer.applySceneIntent !== "function")) {
      throw new TypeError(
        "WorldClient requires a performer with applyEnvelope and/or applySceneIntent",
      );
    }
    this.worker = worker;
    this.performer = performer;
    this.domMirror = domMirror;
    this.fidelityController = fidelityController;
    this.gate = new MessageGate();
    this.envelopes = new Map();
    // Scene-intent's own latest-applied cache (world-v1 uses `envelopes`
    // above instead) — see setPerformer's re-hydration and _applySceneIntent.
    this.lastSceneIntent = null;
    this.pendingInputs = new Map();
    this.inputSequence = 0;
    this._pendingSave = null;
    // stepMsSamples: the worker's own per-tick elapsedSeconds (renamed
    // stepMs on the wire), one entry per admitted delta — this is the
    // "simulation step (worker)" distribution build prompt §16/§6.2.G asks
    // frame_bench.mjs to report SEPARATELY from main-thread frame time.
    this.metrics = { snapshotsApplied: 0, deltasApplied: 0, discarded: 0, errors: [], stepMsSamples: [] };
  }

  // Swap the active visual performer (Pixi -> Safe Harbor on a lost cause,
  // per design doc §22). Re-hydrates the new performer with every envelope
  // already known (world-v1) and/or the latest scene intent (scene-intent),
  // so the fallback does not start blank under either protocol.
  setPerformer(performer) {
    this.performer = performer;
    for (const envelope of this.envelopes.values()) this.performer.applyEnvelope?.(envelope);
    if (this.lastSceneIntent) {
      this.performer.applySceneIntent?.(this.lastSceneIntent.intent, {
        lines: this.lastSceneIntent.lines, trace: this.lastSceneIntent.trace,
      });
    }
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
    if (message.type === "snapshot-saved") {
      this._resolvePendingSave(message.snapshot);
      return;
    }
    if (message.protocol === "scene-intent") {
      this._applySceneIntent(message);
    } else if (message.type === "snapshot") {
      this.envelopes.set(message.envelope.identity.id, message.envelope);
      this._applyToPerformers(message.envelope);
      this.metrics.snapshotsApplied += 1;
    } else if (message.type === "delta") {
      this._applyDelta(message.delta);
      this.metrics.deltasApplied += 1;
      if (typeof message.stepMs === "number") this.metrics.stepMsSamples.push(message.stepMs);
    }
    this._resolvePendingInputs(message.acknowledgedInputSequence, message.revision);
  }

  // Horizon Phase 2 Build 2 (build prompt §3.4): asks the worker to
  // capture the current world value (worker.mjs's own "save"/
  // "snapshot-saved" message pair — see that file's "save" branch for why
  // it has to happen there). Returns a Promise resolving with the plain
  // snapshot object ({revision, tick, world, hash}) once it arrives — the
  // caller persists it however it likes (localStorage, download, ...);
  // this class owns transport, not storage policy.
  saveSnapshot() {
    return new Promise((resolve) => {
      this._pendingSave = resolve;
      this.worker.postMessage({ type: "save" });
    });
  }

  _resolvePendingSave(snapshot) {
    if (!this._pendingSave) return;
    const resolve = this._pendingSave;
    this._pendingSave = null;
    resolve(snapshot);
  }

  // Scene-intent messages (Horizon Phase 2 Build 2, build prompt §3.3) carry
  // a COMPLETE scene description every message — the Planes program re-emits
  // every "scene ..." line unconditionally each call — so there is no
  // facet-patch fold to perform here, unlike world-v1's _applyDelta below:
  // parse once (invariant 3: consumed, never reimplemented) and hand the
  // result straight to the performer/DOM mirror. `message.type` is still
  // either "snapshot" (the first message) or "delta" (every tick after),
  // which is why the metrics counters below still branch on it — that
  // distinction is about WHEN the message arrived, not about how its
  // payload is applied.
  _applySceneIntent(message) {
    let intent;
    try {
      intent = parseSceneIntent(message.lines);
    } catch (err) {
      this.metrics.errors.push(err.message);
      return;
    }
    this.lastSceneIntent = {
      intent, lines: message.lines, trace: message.trace ?? [], revision: message.revision,
    };
    this.performer.applySceneIntent?.(intent, { lines: message.lines, trace: message.trace });
    this.domMirror?.applySceneIntent?.(intent);
    if (message.type === "snapshot") {
      this.metrics.snapshotsApplied += 1;
    } else {
      this.metrics.deltasApplied += 1;
      if (typeof message.stepMs === "number") this.metrics.stepMsSamples.push(message.stepMs);
    }
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
  // the worker's ACKNOWLEDGMENT has been admitted by the message gate and
  // the browser has painted a frame after that. Returns a
  // Promise<milliseconds> — pokeSubject's own, pre-existing contract,
  // preserved exactly (unpacked from _sendInput's richer resolution below,
  // not returned directly). A bare poke (no `event`) — see sendInput below
  // for a poke that actually carries a typed event and steers the program.
  pokeSubject() {
    return this._sendInput(null).then(({ ms }) => ms);
  }

  // Horizon Phase 2 Build 2 (build prompt §3.5): the real input seam — a UI
  // event (subject select, need/route/power/radio choice) becomes an
  // "input" worker message carrying the typed event the crossing's own
  // `advance` matches (`{kind:"select",subject}` / `{kind:"need",
  // choice:"care"}` / etc.), acknowledged and timed exactly like
  // pokeSubject's diagnostic poke — this IS what "acknowledged" meant all
  // along (worker.mjs's own header: "acknowledged now means applied on
  // this tick"), just with a caller that cares what was applied, not only
  // that something was. Returns a Promise<{ms, tick}> — `tick` is the
  // exact Planes-level tick the event was applied at (see
  // _resolvePendingInputs's own comment for why this must come from the
  // acknowledging message itself, not be reconstructed by a caller reading
  // a mutable field later — a caller building a replayable event log
  // needs this exact value, not an approximation).
  sendInput(event) {
    return this._sendInput(event);
  }

  _sendInput(event) {
    this.inputSequence += 1;
    const sequence = this.inputSequence;
    const sentAt = performance.now();
    const message = { type: "input", sequence, sentAt };
    if (event !== null) message.event = event;
    this.worker.postMessage(message);
    return new Promise((resolve) => {
      this.pendingInputs.set(sequence, { resolve, sentAt });
    });
  }

  // `revision` comes from the SAME message that carried
  // `acknowledgedInputSequence` — captured here, synchronously, in the
  // closure below, before ANY further worker message can arrive. This
  // matters: found live (a real replay-mismatch report against
  // horizon-crossing.html) that a caller reading `client.lastSceneIntent
  // .revision` AFTER a sendInput() promise resolves gets a STALE value —
  // the two nested rAFs below (~2 frames) are enough real wall-clock time
  // for the worker's own 30 Hz ticker to have advanced `lastSceneIntent`
  // past the tick that actually acknowledged this input, and even without
  // that race, `revision` itself is one past the Planes-level `tick`
  // `advance` was actually called with (worker.mjs's BrowserSceneKernel
  // increments `revision` AFTER stepping) — resolving with `revision - 1`
  // here, sourced from this exact message, is correct on both counts.
  _resolvePendingInputs(acknowledgedInputSequence, revision) {
    if (typeof acknowledgedInputSequence !== "number") return;
    const tick = typeof revision === "number" ? revision - 1 : null;
    for (const [sequence, pending] of [...this.pendingInputs.entries()]) {
      if (sequence > acknowledgedInputSequence) continue;
      this.pendingInputs.delete(sequence);
      // Two nested rAFs: the first fires before the browser paints this
      // frame's changes, the second after — "visible" should mean painted,
      // not merely applied to a scene graph. `tick` above is captured
      // BEFORE this delay, not read fresh when it fires.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          pending.resolve({ ms: performance.now() - pending.sentAt, tick });
        });
      });
    }
  }
}

// ---- real page wiring — the only part of this file that touches
// `document`/`Worker`/a live canvas. Mirrors browser_main.mjs's own guard
// pattern so this module stays importable (and WorldClient/MessageGate/
// foldDelta unit-testable) under plain `node --test`.

// fixtureUrl/protocol: Horizon Phase 2 Build 2's own addition — forwarded
// as the worker's configuring "boot" message (see worker.mjs's own header
// on why a module Worker has to be configured this way). Both default to
// undefined/"world-v1", reproducing horizon.html's exact prior call
// (`boot({ pixiContainer, domMirrorContainer, safeHarborCanvas })`, no
// fixture/protocol at all) byte-for-byte. onSelect: forwarded to
// createPixiPerformer — a scene subject's click/tap, unused by the
// world-v1 placeholder path.
export async function boot({
  pixiContainer, domMirrorContainer, safeHarborCanvas, fixtureUrl, protocol, onSelect,
} = {}) {
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
        onSelect,
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
  worker.postMessage({ type: "boot", fixtureUrl, protocol });

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
