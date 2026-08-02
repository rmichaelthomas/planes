const KNOWN_ASSETS = new Set([
  "reso-landing", "nkwo-eriri", "hydrofoil-main", "market", "kordas",
  "fog-capture", "radio-mast", "clinic-beacon", "wave-array", "petrels",
]);

export function resolveSceneAsset(asset) {
  return KNOWN_ASSETS.has(asset) ? asset : "canonical-silhouette";
}

export function resolveCameraLayout({ width, height, camera }) {
  const portrait = width <= 760 && width / Math.max(1, height) < .9;
  if (!portrait) return { portrait: false, panX: 0, worldWidth: width, zoom: camera.zoom };
  const progress = Math.max(0, Math.min(1, (camera.x - .42) / .19));
  const centerX = 320 + progress * 970;
  const scale = height / 900;
  return {
    portrait: true,
    panX: width / 2 - centerX * scale,
    worldWidth: height * 1600 / 900,
    zoom: 1,
  };
}

export function createSceneModel(intent, previous = null) {
  const subjects = previous?.subjects ?? new Map();
  const present = new Set();
  for (const value of intent.subjects ?? []) {
    present.add(value.id);
    const subject = subjects.get(value.id) ?? { id: value.id };
    Object.assign(subject, value, { asset: resolveSceneAsset(value.asset) });
    subjects.set(value.id, subject);
  }
  for (const [id, subject] of subjects) subject.present = present.has(id);

  const model = previous ?? {
    subjects,
    selected: null,
    paused: false,
    select(id) {
      if (!this.subjects.get(id)?.present) return false;
      this.selected = id;
      return true;
    },
    pause() { this.paused = true; },
    resume() { this.paused = false; },
  };
  model.camera = { ...intent.camera };
  model.environment = { ...intent.environment };
  model.routes = (intent.routes ?? []).map((route) => ({ ...route, progress: Number(route.progress) }));
  model.signals = (intent.signals ?? []).map((signal) => ({ ...signal }));
  model.weather = (intent.weather ?? []).map((weather) => ({ ...weather }));
  model.actions = (intent.actions ?? []).map((action) => ({ ...action }));
  model.cues = (intent.cues ?? []).map((cue) => ({ ...cue }));
  return model;
}

const STAGE_MARKUP = `
  <div class="passage-camera" data-camera="horizon">
    <picture class="passage-plate">
      <source srcset="./assets/a-crossing/passage-environment.webp" type="image/webp">
      <img src="./assets/a-crossing/passage-environment.jpg" alt="" draggable="false">
    </picture>
    <div class="passage-color-grade" aria-hidden="true"></div>
    <canvas class="passage-atmosphere" aria-hidden="true"></canvas>
    <svg class="passage-world" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" role="group" aria-label="Living Passage between Reso and Nkwo Eriri">
      <defs>
        <filter id="cord-glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <filter id="signal-glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="9" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <linearGradient id="foil-hull" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fffdf3"/><stop offset=".72" stop-color="#e6f3ee"/><stop offset="1" stop-color="#78bfc5"/></linearGradient>
        <linearGradient id="wake-fade" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#f7f2dc" stop-opacity="0"/><stop offset="1" stop-color="#f7f2dc" stop-opacity=".85"/></linearGradient>
      </defs>

      <g class="route-layer" data-subject="route-cord" tabindex="0" role="button" aria-label="Passage route cord">
        <path class="route-shadow" d="M185 677C410 718 720 635 1340 513" pathLength="1"/>
        <path class="route-cord" d="M185 677C410 718 720 635 1340 513" pathLength="1"/>
        <g class="route-beads" aria-hidden="true"></g>
        <path class="hit-route" d="M185 677C410 718 720 635 1340 513"/>
      </g>

      <g class="world-subject landing-hit reso-hit" data-subject="reso-landing" tabindex="0" role="button" aria-label="Reso landing"><path d="M0 390h380v400H0Z"/></g>
      <g class="world-subject landing-hit nkwo-hit" data-subject="nkwo-eriri" tabindex="0" role="button" aria-label="Nkwo Eriri landing"><path d="M1120 220h480v420h-480Z"/></g>
      <g class="world-subject landing-hit market-hit" data-subject="market" tabindex="0" role="button" aria-label="Reso market"><ellipse cx="154" cy="618" rx="150" ry="90"/></g>
      <g class="world-subject landing-hit kordas-hit" data-subject="kordas" tabindex="0" role="button" aria-label="Cord-anchored terraces"><ellipse cx="170" cy="390" rx="160" ry="150"/></g>
      <g class="world-subject landing-hit fog-hit" data-subject="fog-capture" tabindex="0" role="button" aria-label="Fog capture mesh"><ellipse cx="330" cy="235" rx="125" ry="135"/></g>

      <g class="world-subject wave-array" data-subject="wave-array" tabindex="0" role="button" aria-label="Wave energy array" transform="translate(804 538)">
        <path d="M-75 44q25-30 50 0t50 0t50 0" fill="none" stroke="#f1d17d" stroke-width="5" opacity=".88"/>
        <g fill="#f7f3df" stroke="#174f66" stroke-width="3"><circle cx="-62" cy="27" r="9"/><circle cx="-12" cy="26" r="9"/><circle cx="38" cy="23" r="9"/><circle cx="88" cy="19" r="9"/></g>
        <circle class="subject-hit" r="90"/>
      </g>

      <g class="world-subject radio-mast" data-subject="radio-mast" tabindex="0" role="button" aria-label="Nkwo Eriri radio mast" transform="translate(1343 184)">
        <circle class="signal-halo" r="10"/><path class="radio-wave one" d="M-24 18q24-24 48 0"/><path class="radio-wave two" d="M-40 28q40-40 80 0"/>
        <circle class="subject-hit" r="68"/>
      </g>

      <g class="world-subject clinic-beacon" data-subject="clinic-beacon" tabindex="0" role="button" aria-label="Distant clinic beacon" transform="translate(1450 420)">
        <circle class="beacon-aura" r="28"/><circle class="beacon-disc" r="11"/><path class="beacon-cross" d="M-5 0h10M0-5v10"/>
        <circle class="subject-hit" r="54"/>
      </g>

      <g class="world-subject petrels" data-subject="petrels" tabindex="0" role="button" aria-label="Eririan petrels">
        <ellipse class="subject-hit" cx="840" cy="150" rx="190" ry="80"/>
      </g>

      <g class="world-subject hydrofoil" data-subject="hydrofoil" tabindex="0" role="button" aria-label="Electric hydrofoil" transform="translate(260 650)">
        <g class="foil-wake" aria-hidden="true"><path d="M-180 38Q-82 12-8 31"/><path d="M-170 54Q-74 29-3 43"/><path d="M-125 68Q-61 49-2 51"/></g>
        <image class="foil-sprite" href="./assets/a-crossing/hydrofoil.webp" x="-180" y="-126" width="360" height="225" preserveAspectRatio="xMidYMid meet"/>
        <g class="foil-body">
          <path d="M-87 4Q-59 34 42 31 91 29 116 4L82-16h-142Z" fill="url(#foil-hull)" stroke="#173f52" stroke-width="4"/>
          <path d="M-49-17h88l31 19h-141Z" fill="#f9f2dc" stroke="#173f52" stroke-width="4"/>
          <path d="M-31-13h58L46 0h-92Z" fill="#1b7891"/><g fill="#99dde0"><rect x="-26" y="-10" width="14" height="7" rx="2"/><rect x="-8" y="-10" width="14" height="7" rx="2"/><rect x="10" y="-10" width="14" height="7" rx="2"/></g>
          <path d="M-47 31l-8 28M67 30l10 25M-73 59h38M57 55h39" stroke="#173f52" stroke-width="5" stroke-linecap="round"/>
          <path d="M34-18v-26m0 0 18 8" stroke="#f4efe2" stroke-width="4"/>
          <path d="M34-44h22v14H34Z" fill="#16224c"/><path d="M34-37h22" stroke="#f4efe2" stroke-width="2"/>
        </g>
        <ellipse class="subject-hit" rx="132" ry="78"/>
      </g>

      <g class="selection-ring" aria-hidden="true"><circle r="48"/><circle class="selection-pulse" r="61"/></g>
    </svg>
    <div class="stage-fallback-note" role="status" hidden>Atmosphere simplified for this browser.</div>
  </div>`;

class Atmosphere {
  constructor(canvas, enabled, reducedMotion) {
    this.canvas = canvas;
    this.reducedMotion = reducedMotion;
    this.gl = enabled ? canvas.getContext("webgl2", { alpha: true, antialias: false, powerPreference: "low-power" }) : null;
    this.intensity = 2;
    this.running = false;
    this.frames = [];
    if (this.gl) this.#setup();
  }

  #shader(type, source) {
    const shader = this.gl.createShader(type);
    this.gl.shaderSource(shader, source);
    this.gl.compileShader(shader);
    if (!this.gl.getShaderParameter(shader, this.gl.COMPILE_STATUS)) throw new Error(this.gl.getShaderInfoLog(shader));
    return shader;
  }

  #setup() {
    const vertex = this.#shader(this.gl.VERTEX_SHADER, `#version 300 es
      in vec2 p; out vec2 uv; void main(){uv=p*.5+.5;gl_Position=vec4(p,0.,1.);}`);
    const fragment = this.#shader(this.gl.FRAGMENT_SHADER, `#version 300 es
      precision mediump float; in vec2 uv; out vec4 color; uniform float t; uniform float swell;
      void main(){
        float water=1.0-smoothstep(.40,.64,uv.y);
        float shimmer=.5+.22*sin(uv.x*47.+t*.08)+.18*sin(uv.y*61.-t*.06)+.10*sin((uv.x+uv.y)*29.+t*.04);
        shimmer=clamp(shimmer,0.,1.);
        vec3 ink=mix(vec3(.03,.34,.47),vec3(.86,.74,.42),shimmer*.18);
        float alpha=water*(.0008+.00065*swell)*shimmer;
        color=vec4(ink,alpha);
      }`);
    const program = this.gl.createProgram();
    this.gl.attachShader(program, vertex); this.gl.attachShader(program, fragment); this.gl.linkProgram(program);
    if (!this.gl.getProgramParameter(program, this.gl.LINK_STATUS)) throw new Error(this.gl.getProgramInfoLog(program));
    this.program = program;
    this.time = this.gl.getUniformLocation(program, "t");
    this.swell = this.gl.getUniformLocation(program, "swell");
    const buffer = this.gl.createBuffer();
    this.gl.bindBuffer(this.gl.ARRAY_BUFFER, buffer);
    this.gl.bufferData(this.gl.ARRAY_BUFFER, new Float32Array([-1,-1,3,-1,-1,3]), this.gl.STATIC_DRAW);
    const point = this.gl.getAttribLocation(program, "p");
    this.gl.enableVertexAttribArray(point); this.gl.vertexAttribPointer(point, 2, this.gl.FLOAT, false, 0, 0);
  }

  resize() {
    const box = this.canvas.getBoundingClientRect();
    const ratio = Math.min(devicePixelRatio || 1, 1.5);
    this.canvas.width = Math.max(1, Math.round(box.width * ratio));
    this.canvas.height = Math.max(1, Math.round(box.height * ratio));
    if (this.gl) this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
  }

  draw(time) {
    if (!this.gl) return;
    const start = performance.now();
    this.gl.useProgram(this.program);
    this.gl.uniform1f(this.time, time * .001);
    this.gl.uniform1f(this.swell, Math.min(5, this.intensity));
    this.gl.clearColor(0,0,0,0); this.gl.clear(this.gl.COLOR_BUFFER_BIT);
    this.gl.drawArrays(this.gl.TRIANGLES, 0, 3);
    this.frames.push(performance.now() - start);
    if (this.frames.length > 240) this.frames.shift();
  }

  start() {
    if (this.running || this.reducedMotion || !this.gl) return;
    this.running = true;
    const frame = (time) => { if (!this.running) return; this.draw(time); this.raf = requestAnimationFrame(frame); };
    this.raf = requestAnimationFrame(frame);
  }
  stop() { this.running = false; if (this.raf) cancelAnimationFrame(this.raf); }
  destroy() { this.stop(); const ext = this.gl?.getExtension("WEBGL_lose_context"); ext?.loseContext(); }
}

export function createCrossingStage({ root, reducedMotion = false, webgl = true } = {}) {
  if (!root) throw new TypeError("createCrossingStage requires a root element");
  root.innerHTML = STAGE_MARKUP;
  const camera = root.querySelector(".passage-camera");
  const world = root.querySelector(".passage-world");
  const route = root.querySelector(".route-cord");
  const routeLayer = root.querySelector(".route-layer");
  const beads = root.querySelector(".route-beads");
  const selection = root.querySelector(".selection-ring");
  const sprite = root.querySelector(".foil-sprite");
  const atmosphere = new Atmosphere(root.querySelector(".passage-atmosphere"), webgl, reducedMotion);
  const subjectElements = new Map([...root.querySelectorAll("[data-subject]")].map((element) => [element.dataset.subject, element]));
  let model = null;
  let lastCue = null;
  let resizeObserver = null;

  const layoutCamera = () => {
    if (!model?.camera) return;
    const box = root.getBoundingClientRect();
    const layout = resolveCameraLayout({ width: box.width, height: box.height, camera: model.camera });
    camera.style.setProperty("--camera-x", layout.portrait ? "0%" : `${(model.camera.x - .5) * -8}%`);
    camera.style.setProperty("--camera-y", layout.portrait ? "0%" : `${(model.camera.y - .5) * -6}%`);
    camera.style.setProperty("--camera-zoom", String(layout.zoom));
    camera.style.setProperty("--mobile-pan", `${layout.panX}px`);
    camera.style.setProperty("--world-width", `${layout.worldWidth}px`);
    camera.dataset.layout = layout.portrait ? "portrait-pan" : "horizon";
  };

  const spriteReady = () => sprite.classList.add("loaded");
  sprite.addEventListener("load", spriteReady, { once: true });
  if (sprite.complete) spriteReady();

  for (let i = 0; i < 9; i += 1) {
    const bead = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    bead.setAttribute("r", i === 4 ? "8" : "6");
    bead.dataset.bead = String(i);
    beads.append(bead);
  }

  const positionBeads = () => {
    if (!route.getTotalLength) return;
    const length = route.getTotalLength();
    [...beads.children].forEach((bead, index) => {
      const point = route.getPointAtLength(length * (index + 1) / 10);
      bead.setAttribute("cx", point.x); bead.setAttribute("cy", point.y);
    });
  };

  const apply = (intent, semanticState) => {
    model = createSceneModel(intent, model);
    layoutCamera();
    camera.dataset.light = model.environment.light;
    camera.dataset.weather = model.environment.weather;
    atmosphere.intensity = model.weather.find(({ kind }) => kind === "swell")?.intensity ?? 2;

    for (const [id, element] of subjectElements) {
      const subject = model.subjects.get(id);
      element.hidden = !subject?.present || subject.visibility === "hidden";
      if (!subject) continue;
      element.dataset.state = subject.state;
      element.setAttribute("aria-pressed", String(model.selected === id));
      if (id === "hydrofoil") {
        element.style.transform = `translate(${subject.x * 1600}px, ${subject.y * 900}px) scale(${subject.scale})`;
      }
    }

    const activeRoute = model.routes[0];
    if (activeRoute) {
      routeLayer.dataset.state = activeRoute.state;
      route.style.strokeDashoffset = String(1 - Math.max(.04, activeRoute.progress));
      route.style.setProperty("--route-progress", String(activeRoute.progress));
      [...beads.children].forEach((bead, index) => bead.classList.toggle("awake", activeRoute.progress >= (index + 1) / 10));
    }

    for (const cue of model.cues) {
      const key = `${cue.id}:${cue.serial}`;
      if (key === lastCue) continue;
      lastCue = key;
      root.dataset.cue = cue.id;
      if (cue.id === "crossing-commit") {
        root.classList.remove("is-committing");
        requestAnimationFrame(() => root.classList.add("is-committing"));
      }
    }
    root.dataset.phase = semanticState?.phase ?? "unknown";
    return model;
  };

  const select = (id) => {
    if (!model?.select(id)) return false;
    for (const [subjectId, element] of subjectElements) element.setAttribute("aria-pressed", String(subjectId === id));
    const target = subjectElements.get(id);
    if (target) {
      const matrix = target.getCTM?.();
      if (matrix) selection.setAttribute("transform", `translate(${matrix.e} ${matrix.f})`);
      selection.classList.add("visible");
    }
    return true;
  };

  world.addEventListener("click", (event) => {
    const target = event.target.closest?.("[data-subject]");
    if (!target || !select(target.dataset.subject)) return;
    root.dispatchEvent(new CustomEvent("crossing-select", { bubbles: true, detail: { subject: target.dataset.subject } }));
  });
  world.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const target = event.target.closest?.("[data-subject]");
    if (target) { event.preventDefault(); target.dispatchEvent(new MouseEvent("click", { bubbles: true })); }
  });

  const resize = () => { layoutCamera(); atmosphere.resize(); positionBeads(); };
  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(resize); resizeObserver.observe(root);
  }
  requestAnimationFrame(resize);
  if (!atmosphere.gl) { root.dataset.atmosphere = "fallback"; root.querySelector(".stage-fallback-note").hidden = false; }
  atmosphere.start();

  return {
    apply,
    select,
    resize,
    pause() { model?.pause(); atmosphere.stop(); root.dataset.paused = "true"; },
    resume() { model?.resume(); atmosphere.start(); root.dataset.paused = "false"; },
    model: () => model,
    metrics: () => ({ atmosphereFrames: atmosphere.frames.slice(), webgl: Boolean(atmosphere.gl) }),
    destroy() { resizeObserver?.disconnect(); atmosphere.destroy(); root.replaceChildren(); },
  };
}
