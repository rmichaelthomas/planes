#!/usr/bin/env node
// scripts/world_renderer_bench.mjs — the §16/§23.4 frame-time harness,
// driver half (build prompt §3; the in-page half is js/world/performers/
// frame_bench.mjs).
//
// WHY THIS DOES NOT `import "playwright"`. This repo has no package.json
// and no node_modules (§10.5's no-build-step rule, applied to the whole
// repo, not just what ships) — a bare `import "playwright"` here would
// resolve only on a machine that happens to have it cached globally, and
// silently fail (or silently pass with a stale cache) everywhere else.
// This repo's own established pattern for "drive a real browser" is
// documented, tool-driven capture (see the memory of prior Horizon-
// adjacent builds: "Live-verified via playwright-cli against a local
// server", A Crossing/garden/paint.html all report this same shape), not a
// project dependency. This file supplies the half that IS honestly
// reusable without that tool: a zero-dependency local static server (so
// `fetch`-based module loading works — see world_ir.mjs's own module
// docstring on why `file://` does not), and a formatter that turns
// already-collected measurements into horizon-renderer-pipeline-results.md
// in the exact shape build prompt §6.2.G requires. Driving the browser
// itself is this build's own agent-performed step; see
// horizon-renderer-pipeline-results.md for which tool and what it found.
//
// Run directly (`node scripts/world_renderer_bench.mjs`) to start the
// server and print the bench URL. Import { serve, writeResultsMarkdown }
// to drive both halves programmatically from wherever the browser
// automation lives.

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".planes": "text/plain; charset=utf-8",
  ".woff2": "font/woff2",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

// A minimal static file server over the repo root — no dependency beyond
// node:http/fs/path, deliberately: this script's own job is to make the
// fetch-based module graph (world_ir.mjs, module_loader_browser.mjs, the
// vendored Pixi bundle) loadable at all, which `file://` cannot do.
export function serve(port = 0) {
  const server = http.createServer((req, res) => {
    let reqPath = decodeURIComponent(req.url.split("?")[0]);
    if (reqPath === "/") reqPath = "/horizon.html";
    const filePath = path.join(REPO_ROOT, reqPath);
    if (!filePath.startsWith(REPO_ROOT)) {
      res.writeHead(403);
      res.end("forbidden");
      return;
    }
    fs.readFile(filePath, (err, data) => {
      if (err) {
        res.writeHead(404);
        res.end("not found: " + reqPath);
        return;
      }
      const ext = path.extname(filePath);
      res.writeHead(200, { "content-type": MIME[ext] ?? "application/octet-stream" });
      res.end(data);
    });
  });
  return new Promise((resolve) => {
    server.listen(port, "127.0.0.1", () => resolve(server));
  });
}

export function runMachineSpecs() {
  const cpus = os.cpus();
  return {
    platform: `${os.type()} ${os.release()} (${os.arch()})`,
    cpuModel: cpus[0]?.model ?? "unknown",
    cpuCount: cpus.length,
    totalMemGB: Math.round((os.totalmem() / (1024 ** 3)) * 10) / 10,
    nodeVersion: process.version,
  };
}

function fmtPct(p) {
  if (!p || p.count === 0) return "(no samples)";
  return `count=${p.count} min=${p.min.toFixed(2)} p50=${p.p50.toFixed(2)} p95=${p.p95.toFixed(2)} p99=${p.p99.toFixed(2)} max=${p.max.toFixed(2)} mean=${p.mean.toFixed(2)}`;
}

// measurement shape (all fields required, all from a real capture — never
// invented, per this build's own S2/#9 failure-mode discipline):
// {
//   capturedAt, browser: {name, version, headless},
//   tiers: { sun: {frameTimeMs, simulationStepMs, longTasksOverThreshold, longTasksObserved, spriteCount, domNodeCount, heapUsedMB, workerMetrics}, breeze: {...}, harbor: {...} },
//   inputToVisibleMs: [numbers...],
//   determinism: { snapshotHashesMatch: bool, note },
//   tierInvariance: { eventLogsIdentical: bool, saveHashesIdentical: bool, note },
//   screenshotPaths: [...],
// }
export function writeResultsMarkdown(measurement, outPath = path.join(REPO_ROOT, "horizon-renderer-pipeline-results.md")) {
  const specs = runMachineSpecs();
  const gate = {
    sun: 16.7,
    breeze: 22,
    harbor: 33.3,
  };
  const lines = [];
  lines.push("# Horizon Phase 1 — renderer pipeline results");
  lines.push("");
  lines.push(`Captured: ${measurement.capturedAt}`);
  lines.push(
    `Browser: ${measurement.browser.name} ${measurement.browser.version} (${measurement.browser.headless ? "headless" : "headed"})`,
  );
  lines.push(`Run machine: ${specs.platform}, ${specs.cpuModel} x${specs.cpuCount}, ${specs.totalMemGB} GB RAM, node ${specs.nodeVersion}`);
  lines.push("");
  lines.push(
    "**All frame-time gates below are Sun-provisional against this run machine.** " +
      "No named school-hardware reference device exists to measure Breeze/Harbor against yet " +
      "(design doc §16: gates \"must be recalibrated against named reference devices\"); " +
      "recalibration is a Phase 2 gate. A gate that fails here against the placeholder scene " +
      "is a recorded finding about pipeline overhead on this machine, not a shippable-quality verdict.",
  );
  lines.push("");
  lines.push("## Frame-time and simulation-step distributions, per tier");
  lines.push("");
  for (const tierName of ["sun", "breeze", "harbor"]) {
    const t = measurement.tiers[tierName];
    if (!t) {
      lines.push(`### ${tierName}`, "", "(not captured)", "");
      continue;
    }
    const p95 = t.frameTimeMs.p95;
    const passes = p95 !== null && p95 <= gate[tierName];
    lines.push(`### ${tierName} — gate p95 ≤ ${gate[tierName]} ms — ${p95 === null ? "NO DATA" : passes ? "PASS" : "OVER GATE (recorded, not a blocker — see §4)"}`);
    lines.push("");
    lines.push(`- frame time (main thread, ms): ${fmtPct(t.frameTimeMs)}`);
    lines.push(`- simulation step (worker, ms): ${fmtPct(t.simulationStepMs)}`);
    lines.push(`- long tasks observed: ${t.longTasksObserved}, over ${t.longTaskThresholdMs ?? 50}ms: ${t.longTasksOverThreshold}`);
    lines.push(`- sprite count: ${t.spriteCount}, DOM mirror node count: ${t.domNodeCount}`);
    lines.push(`- JS heap used (MB): ${t.heapUsedMB === null ? "(performance.memory unavailable)" : t.heapUsedMB.toFixed(1)}`);
    lines.push(
      `- worker: snapshots=${t.workerMetrics.snapshotsApplied} deltas=${t.workerMetrics.deltasApplied} discarded=${t.workerMetrics.discarded} errors=${t.workerMetrics.errorCount}`,
    );
    lines.push("");
  }

  lines.push("## Input → visible response");
  lines.push("");
  lines.push(
    "Gate: p95 ≤ 70 ms, for a synthetic direct-manipulation poke — the Living Lens is Phase 3, and " +
      "advance(world, tick) has no input-event parameter yet (worker.mjs's own header explains why), " +
      "so this measures the message-contract round trip (main thread → worker → acknowledged on the " +
      "next delta → painted), not a semantic effect of the poke.",
  );
  lines.push("");
  const ivp = percentilesOf(measurement.inputToVisibleMs);
  lines.push(`- ${fmtPct(ivp)}`);
  lines.push(
    `- gate: ${ivp.p95 === null ? "NO DATA" : ivp.p95 <= 70 ? "PASS" : "OVER GATE (recorded, not a blocker — see §4)"}`,
  );
  lines.push("");

  lines.push("## Determinism and quality-tier invariance");
  lines.push("");
  lines.push(`- semantic determinism (identical snapshot hashes, same package/seed/events): ${measurement.determinism.snapshotHashesMatch ? "PASS" : "FAIL"} — ${measurement.determinism.note}`);
  lines.push(`- quality-tier invariance (identical semantic event log + save hash across tiers): ${measurement.tierInvariance.eventLogsIdentical && measurement.tierInvariance.saveHashesIdentical ? "PASS" : "FAIL"} — ${measurement.tierInvariance.note}`);
  lines.push("");

  lines.push("## Diagnostic capture");
  lines.push("");
  lines.push("Screenshots (placeholder scene, diagnostic evidence the pipeline runs — NOT a visual-acceptance capture):");
  lines.push("");
  for (const p of measurement.screenshotPaths) lines.push(`- \`${p}\``);
  lines.push("");

  lines.push("## What this build did not do — owed to Phase 2");
  lines.push("");
  lines.push("- visual acceptance against the §24.4 Reso Landing frame (asset compositor, segmented depth planes, rigs, real cell);");
  lines.push("- Breeze/Harbor frame-gate recalibration against named school hardware;");
  lines.push("- Rapier, audio, and the Living Lens interaction layer;");
  lines.push("- the real Ala Eriri cell replacing the placeholder scene.");
  lines.push("");

  fs.writeFileSync(outPath, lines.join("\n") + "\n");
  return outPath;
}

function percentilesOf(samples) {
  if (!samples || samples.length === 0) return { count: 0, min: null, max: null, mean: null, p50: null, p95: null, p99: null };
  const ordered = [...samples].sort((a, b) => a - b);
  const n = ordered.length;
  const pct = (p) => ordered[Math.min(n - 1, Math.max(0, Math.ceil(p * n) - 1))];
  return { count: n, min: ordered[0], max: ordered[n - 1], mean: ordered.reduce((a, b) => a + b, 0) / n, p50: pct(0.5), p95: pct(0.95), p99: pct(0.99) };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const server = await serve(8934);
  const addr = server.address();
  console.log(`world_renderer_bench: serving ${REPO_ROOT} at http://127.0.0.1:${addr.port}/`);
  console.log(`  bench page: http://127.0.0.1:${addr.port}/horizon.html`);
  console.log("  drive it with a real/headless browser (this build used playwright-cli — see");
  console.log("  horizon-renderer-pipeline-results.md for the exact capture), read back");
  console.log("  window.__horizonBench.report() per tier, and call writeResultsMarkdown().");
  console.log("  Ctrl-C to stop.");
}
