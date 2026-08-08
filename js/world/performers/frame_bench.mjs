// js/world/performers/frame_bench.mjs — the §16/§23.4 frame-time harness,
// in-page half (build prompt §3).
//
// Runs INSIDE horizon.html against a live WorldClient. A separate driver,
// scripts/world_renderer_bench.mjs, starts a local server and formats this
// module's report into horizon-renderer-pipeline-results.md; an external
// tool drives a real/headless browser to horizon.html and calls into this
// module (that script's own header names which tool this build used).
//
// TWO DISTRIBUTIONS, NEVER COLLAPSED INTO ONE. "Frame time" here is the
// MAIN THREAD's own consecutive-rAF-callback spacing — the thing the Sun/
// Breeze/Harbor gates in §16 are actually about. "Simulation step" is the
// WORKER's own per-tick elapsedSeconds, arriving on the wire as each delta
// message's stepMs (see worker.mjs's BrowserWorldKernel.step()) — a
// completely different clock, sampled at the worker's fixed 30 Hz rather
// than the display's refresh rate. Design doc §16 says so explicitly:
// "records frame-time distributions, simulation distributions... Average
// FPS alone is insufficient" — reporting only one would be exactly the
// insufficiency that line warns about.

export function percentiles(samples) {
  if (samples.length === 0) {
    return { count: 0, min: null, max: null, mean: null, p50: null, p95: null, p99: null };
  }
  const ordered = [...samples].sort((a, b) => a - b);
  const n = ordered.length;
  const pct = (p) => ordered[Math.min(n - 1, Math.max(0, Math.ceil(p * n) - 1))];
  return {
    count: n,
    min: ordered[0],
    max: ordered[n - 1],
    mean: ordered.reduce((a, b) => a + b, 0) / n,
    p50: pct(0.5),
    p95: pct(0.95),
    p99: pct(0.99),
  };
}

const LONG_TASK_THRESHOLD_MS = 50;

export class FrameBench {
  constructor({ client } = {}) {
    if (!client) throw new TypeError("FrameBench requires a live WorldClient");
    this.client = client;
    this.frameTimes = [];
    this.longTasks = [];
    this._lastFrameAt = null;
    this._rafHandle = null;
    this._po = null;
    this._running = false;
    // client.metrics.stepMsSamples is owned by WorldClient and keeps
    // accumulating for the whole page session (it is also how the sidebar
    // readout's own totals stay accurate) — reset() below records where it
    // stood, so report() can window simulationStepMs to "since the last
    // reset" the same way frameTimeMs already is, rather than reporting
    // the whole-session distribution under every tier's row.
    this._stepMsBaseline = 0;
  }

  start() {
    if (this._running) return;
    this._running = true;
    this._lastFrameAt = null;
    this._stepMsBaseline = this.client.metrics.stepMsSamples.length;
    const loop = (t) => {
      if (!this._running) return;
      if (this._lastFrameAt !== null) this.frameTimes.push(t - this._lastFrameAt);
      this._lastFrameAt = t;
      this._rafHandle = requestAnimationFrame(loop);
    };
    this._rafHandle = requestAnimationFrame(loop);

    // 'longtask' is Chromium-only (not in the PerformanceObserver spec's
    // universally-supported set) — this build's own capture path uses a
    // Chromium-based headless browser (see world_renderer_bench.mjs), so
    // this is live there. Absent support degrades to frameTimes alone
    // rather than throwing: a frame time sample over the threshold is
    // still visible in the p99/max of frameTime itself.
    if (typeof PerformanceObserver !== "undefined" && PerformanceObserver.supportedEntryTypes?.includes("longtask")) {
      this._po = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) this.longTasks.push(entry.duration);
      });
      this._po.observe({ entryTypes: ["longtask"] });
    }
  }

  stop() {
    this._running = false;
    if (this._rafHandle !== null) cancelAnimationFrame(this._rafHandle);
    this._rafHandle = null;
    this._po?.disconnect();
    this._po = null;
  }

  reset() {
    this.frameTimes = [];
    this.longTasks = [];
    this._stepMsBaseline = this.client.metrics.stepMsSamples.length;
  }

  // A plain-data report — structured-clone-safe, so an external driver
  // reading this back through a browser-automation tool's "evaluate and
  // return" call gets it whole, with nothing Pixi- or DOM-shaped in it.
  report() {
    const engineLongTasks = this.longTasks.filter((d) => d > LONG_TASK_THRESHOLD_MS);
    return {
      frameTimeMs: percentiles(this.frameTimes),
      simulationStepMs: percentiles(this.client.metrics.stepMsSamples.slice(this._stepMsBaseline)),
      longTasksObserved: this.longTasks.length,
      longTasksOverThreshold: engineLongTasks.length,
      longTaskThresholdMs: LONG_TASK_THRESHOLD_MS,
      spriteCount: this.client.performer.spriteCount?.() ?? null,
      domNodeCount: this.client.domMirror?.count?.() ?? null,
      heapUsedMB:
        typeof performance !== "undefined" && performance.memory
          ? performance.memory.usedJSHeapSize / (1024 * 1024)
          : null,
      workerMetrics: {
        snapshotsApplied: this.client.metrics.snapshotsApplied,
        deltasApplied: this.client.metrics.deltasApplied,
        discarded: this.client.metrics.discarded,
        errorCount: this.client.metrics.errors.length,
        errors: [...this.client.metrics.errors],
      },
    };
  }
}
