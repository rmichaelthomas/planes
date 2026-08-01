// scripts/measure-page-tick.mjs — what one tick costs THE PAGE, in a browser.
//
// THIS IS A MEASUREMENT, NOT A GATE. Like scripts/measure-density.mjs it never
// exits non-zero on a slow machine and nothing in scripts/ci.sh calls it. It
// exists because measure-density.mjs measures the INTERPRETER — compose, parse,
// run, collect — and the garden page's backing-store resolution does not touch
// any of that. Tripling the backing store triples the pixels the RASTERISER
// fills per frame and changes nothing else, so a number that omits `paint` is
// blind to exactly the cost the change introduces.
//
// WHAT IS TIMED. The three calls garden.html's own `runAt` makes, per tick, in
// their order:
//
//   1. session.runAt(tick, seed)     — compose, parse the graph, run, collect
//   2. markSink() + walk(lines)      — the third sink, for hit-testing
//   3. paint(ctx, lines, DIMENSIONS) — the rasteriser, at DIMENSIONS.scale
//
// Not a reimplementation of the scene: the same modules the page imports, the
// same program file, the same dimensions object. `--scale` is the one knob,
// because it is the one thing this build changes.
//
// WHY A REAL BROWSER. There is no canvas in Node, and a stub would report the
// cost of a stub. Playwright's chromium is a dev-time tool here — it is not in
// any manifest and no committed suite depends on it. If it is absent this
// script says so and exits 0; a measurement that cannot run is a missing
// number, not a failure.
//
//   npx playwright install chromium
//   node scripts/measure-page-tick.mjs --scale 1 --ticks 30,130,260

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = fileURLToPath(new URL("..", import.meta.url));

const TYPES = {
  ".html": "text/html", ".mjs": "text/javascript", ".js": "text/javascript",
  ".json": "application/json", ".planes": "text/plain", ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const SCALE = Number(arg("scale", "1"));
const TICKS = arg("ticks", "30,130,260").split(",").map(Number);
const SEED = Number(arg("seed", "481027"));
const REPEATS = Number(arg("repeats", "9"));
const WARMUP = Number(arg("warmup", "3"));
// Software rasterisation is the floor, not the page. This scene is full of
// `filter: blur(...)` — pathological in SwiftShader, ordinary on a GPU — so a
// software-only number would condemn a resolution the real page pays little
// for. `--gpu` asks chromium for hardware rasterisation (ANGLE/Metal here);
// both numbers get reported, because neither alone is the honest one.
const GPU = process.argv.includes("--gpu");

async function serve() {
  const server = createServer(async (req, res) => {
    const rel = normalize(decodeURIComponent(req.url.split("?")[0])).replace(/^(\.\.[/\\])+/, "");
    try {
      const body = await readFile(join(REPO, rel));
      res.writeHead(200, { "content-type": TYPES[extname(rel)] ?? "application/octet-stream" });
      res.end(body);
    } catch {
      res.writeHead(404).end("not found");
    }
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  return { server, port: server.address().port };
}

// The measurement itself, run inside the page. Everything it touches is what
// garden.html touches; nothing about the scene is restated here.
async function measureInPage(page, origin) {
  return page.evaluate(
    async ({ origin, ticks, seed, scale, repeats, warmup }) => {
      const [{ paint }, { createProgramSession }, { walk }, { markSink }] = await Promise.all([
        import(`${origin}/js/paint/painter.mjs`),
        import(`${origin}/js/paint/program_session.mjs`),
        import(`${origin}/js/paint/stream.mjs`),
        import(`${origin}/js/paint/marks.mjs`),
      ]);

      const WIDTH = 480, HEIGHT = 360;
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(WIDTH * scale);
      canvas.height = Math.round(HEIGHT * scale);
      const ctx = canvas.getContext("2d");
      const DIMENSIONS = { width: WIDTH, height: HEIGHT, background: "#ffffff", scale };

      const session = createProgramSession({ file: "paint/garden.planes", cacheBust: "measure" });
      await session.load();

      // One tick, timed in the three parts the page pays for. Split because
      // this build changes the RASTERISER's workload and nothing else: a
      // total that rose would otherwise be unattributable, and "the
      // resolution cost too much" has to be provable against the part that
      // actually carries the resolution.
      const once = async (tick) => {
        const a = performance.now();
        const result = await session.runAt(tick, seed);
        const b = performance.now();
        const recorder = markSink();
        walk(result.lines, recorder);
        const c = performance.now();
        paint(ctx, result.lines, DIMENSIONS);
        const d = performance.now();
        return { run: b - a, walk: c - b, paint: d - c, total: d - a, commands: result.lines.length };
      };

      const mid = (xs) => xs.slice().sort((x, y) => x - y)[Math.floor(xs.length / 2)];
      const out = [];
      for (const tick of ticks) {
        // WARM UP FIRST, AND DISCARD IT. The first tick at a given scale pays
        // for module instantiation, the parse cache, and the rasteriser's own
        // first-use setup — measured once and never again in a running page.
        // Folding it into the sample would report a cost the page pays on
        // load as though it were the per-frame cost.
        for (let w = 0; w < warmup; w++) await once(tick);
        const samples = [];
        for (let r = 0; r < repeats; r++) samples.push(await once(tick));
        out.push({
          tick,
          commands: samples[0].commands,
          run: mid(samples.map((s) => s.run)),
          walk: mid(samples.map((s) => s.walk)),
          paint: mid(samples.map((s) => s.paint)),
          median: mid(samples.map((s) => s.total)),
          min: Math.min(...samples.map((s) => s.total)),
          max: Math.max(...samples.map((s) => s.total)),
        });
      }
      return out;
    },
    { origin, ticks: TICKS, seed: SEED, scale: SCALE, repeats: REPEATS, warmup: WARMUP },
  );
}

// Resolved by name if a node_modules is at hand, otherwise from
// PLAYWRIGHT_MODULE — an absolute path to an install kept OUTSIDE the repo, so
// measuring the page never adds a manifest, a lockfile or a node_modules to a
// tree whose whole claim is that it has no build step. ESM ignores NODE_PATH,
// which is why this is an explicit path rather than a resolver hint.
let chromium;
for (const specifier of ["playwright", process.env.PLAYWRIGHT_MODULE]) {
  if (!specifier) continue;
  try {
    ({ chromium } = await import(specifier));
    break;
  } catch { /* try the next */ }
}
if (!chromium) {
  console.log("measure-page-tick: playwright is not installed — no numbers taken.");
  console.log("  npm install playwright && npx playwright install chromium");
  console.log("  then either run from that directory, or set");
  console.log("  PLAYWRIGHT_MODULE=/abs/path/to/node_modules/playwright/index.mjs");
  process.exit(0);
}

const { server, port } = await serve();
const origin = `http://127.0.0.1:${port}`;
const browser = await chromium.launch(
  GPU
    ? {
        channel: "chromium",
        args: ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist",
               "--enable-features=Vulkan,CanvasOopRasterization"],
      }
    : {},
);
try {
  const page = await browser.newPage();
  const failures = [];
  page.on("pageerror", (e) => failures.push(String(e)));
  await page.goto(`${origin}/garden.html`, { waitUntil: "domcontentloaded" });
  const rows = await measureInPage(page, origin);

  console.log(`# one tick, end to end, in chromium — scale ${SCALE} ` +
    `(${Math.round(480 * SCALE)}x${Math.round(360 * SCALE)} backing), seed ${SEED}, ` +
    `median of ${REPEATS} after ${WARMUP} discarded warmups, ` +
    `${GPU ? "hardware" : "software (SwiftShader)"} rasterisation\n`);
  console.log("| tick | draw commands | run ms | walk ms | paint ms | **total ms** | min | max |");
  console.log("|---:|---:|---:|---:|---:|---:|---:|---:|");
  for (const r of rows) {
    console.log(`| ${r.tick} | ${r.commands} | ${r.run.toFixed(1)} | ${r.walk.toFixed(1)} | ` +
      `${r.paint.toFixed(1)} | **${r.median.toFixed(1)}** | ${r.min.toFixed(1)} | ${r.max.toFixed(1)} |`);
  }
  if (failures.length) console.log(`\npage errors: ${failures.join(" | ")}`);
} finally {
  await browser.close();
  server.close();
}
