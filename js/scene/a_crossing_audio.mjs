const BED_RECIPES = {
  "channel-day": [
    { id: "surf", source: "noise", filter: "lowpass", frequency: 620, gainRatio: .62, continuous: true },
    { id: "wind", source: "noise", filter: "bandpass", frequency: 1180, gainRatio: .24, continuous: true },
    { id: "foil-wash", source: "noise", filter: "highpass", frequency: 280, gainRatio: .14, continuous: true },
  ],
};

const CUE_RECIPES = {
  "bell-double": { source: "oscillator", frequency: 392, secondFrequency: 523.25, duration: .54, attack: .008, release: .42 },
  "drum-depart": { source: "oscillator", frequency: 92, secondFrequency: 68, duration: .42, attack: .006, release: .34 },
  "radio-click": { source: "noise", filter: "bandpass", frequency: 1450, duration: .16, attack: .003, release: .11 },
};

const clampGain = (gain, maximum) => Math.max(0, Math.min(maximum, Number(gain) || 0));

export function planAudioIntent(intent, heard = new Set()) {
  const warnings = [];
  const beds = [];
  const cues = [];
  const cueKeys = [];
  for (const requested of intent?.beds ?? []) {
    const recipe = BED_RECIPES[requested.id];
    if (!recipe) { warnings.push(`unknown audio bed: ${requested.id}`); continue; }
    const requestedGain = clampGain(requested.gain, .24);
    for (const layer of recipe) beds.push({ ...layer, gain: requestedGain * layer.gainRatio, anchor: requested.anchor });
  }
  for (const requested of intent?.cues ?? []) {
    const recipe = CUE_RECIPES[requested.id];
    if (!recipe) { warnings.push(`unknown audio cue: ${requested.id}`); continue; }
    const key = `${requested.id}:${requested.serial}`;
    cueKeys.push(key);
    if (heard.has(key)) continue;
    cues.push({ ...recipe, id: requested.id, key, gain: clampGain(requested.gain, .22), anchor: requested.anchor });
  }
  return { masterGain: .32, beds, cues, nodes: [...beds, ...cues], warnings, cueKeys };
}

const defaultContextFactory = () => {
  const Context = globalThis.AudioContext || globalThis.webkitAudioContext;
  return Context ? new Context({ latencyHint: "interactive" }) : null;
};

export function createCrossingAudio({ contextFactory = defaultContextFactory } = {}) {
  let context = null;
  let master = null;
  let unlocked = false;
  let muted = true;
  let pending = null;
  const heard = new Set();
  const activeBeds = new Map();
  const warnings = [];

  const makeNoise = (seconds = 3) => {
    const buffer = context.createBuffer(1, Math.ceil(context.sampleRate * seconds), context.sampleRate);
    const channel = buffer.getChannelData(0);
    let last = 0;
    for (let i = 0; i < channel.length; i += 1) {
      const white = Math.random() * 2 - 1;
      last = last * .96 + white * .04;
      channel[i] = last;
    }
    return buffer;
  };

  const panFor = (anchor) => ({ "reso-landing": -.62, hydrofoil: -.12, "nkwo-eriri": .64, "radio-mast": .72 }[anchor] ?? 0);

  const connectSpatial = (node, anchor) => {
    if (!context.createStereoPanner) { node.connect(master); return; }
    const panner = context.createStereoPanner();
    panner.pan.value = panFor(anchor);
    node.connect(panner); panner.connect(master);
  };

  const startBed = (bed) => {
    const existing = activeBeds.get(bed.id);
    if (existing) {
      existing.gain.gain.setTargetAtTime(muted ? 0 : bed.gain, context.currentTime, .35);
      return;
    }
    const source = context.createBufferSource();
    source.buffer = makeNoise(); source.loop = true;
    const filter = context.createBiquadFilter(); filter.type = bed.filter; filter.frequency.value = bed.frequency;
    const gain = context.createGain(); gain.gain.value = 0;
    source.connect(filter); filter.connect(gain); connectSpatial(gain, bed.anchor);
    source.start(); gain.gain.setTargetAtTime(muted ? 0 : bed.gain, context.currentTime, .55);
    activeBeds.set(bed.id, { source, filter, gain });
  };

  const oscillatorCue = (cue) => {
    const now = context.currentTime;
    [cue.frequency, cue.secondFrequency].forEach((frequency, index) => {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = cue.id === "drum-depart" ? "sine" : "triangle";
      oscillator.frequency.setValueAtTime(frequency, now + index * .13);
      if (cue.id === "drum-depart") oscillator.frequency.exponentialRampToValueAtTime(42, now + cue.duration);
      gain.gain.setValueAtTime(.0001, now + index * .13);
      gain.gain.exponentialRampToValueAtTime(Math.max(.0002, cue.gain * (index ? .65 : 1)), now + index * .13 + cue.attack);
      gain.gain.exponentialRampToValueAtTime(.0001, now + index * .13 + cue.release);
      oscillator.connect(gain); connectSpatial(gain, cue.anchor);
      oscillator.start(now + index * .13); oscillator.stop(now + index * .13 + cue.duration);
    });
  };

  const noiseCue = (cue) => {
    const now = context.currentTime;
    const source = context.createBufferSource(); source.buffer = makeNoise(.25);
    const filter = context.createBiquadFilter(); filter.type = cue.filter; filter.frequency.value = cue.frequency;
    const gain = context.createGain(); gain.gain.setValueAtTime(.0001, now);
    gain.gain.exponentialRampToValueAtTime(Math.max(.0002, cue.gain), now + cue.attack);
    gain.gain.exponentialRampToValueAtTime(.0001, now + cue.release);
    source.connect(filter); filter.connect(gain); connectSpatial(gain, cue.anchor);
    source.start(now); source.stop(now + cue.duration);
  };

  const perform = (intent) => {
    if (!context || !master) return;
    const plan = planAudioIntent(intent, heard);
    warnings.push(...plan.warnings);
    plan.beds.forEach(startBed);
    for (const cue of plan.cues) {
      heard.add(cue.key);
      if (muted) continue;
      if (cue.source === "noise") noiseCue(cue); else oscillatorCue(cue);
    }
  };

  return {
    async unlock() {
      if (unlocked) return;
      unlocked = true;
      context = contextFactory();
      if (!context) return;
      if (context.state === "suspended") await context.resume();
      master = context.createGain(); master.gain.value = muted ? 0 : .32; master.connect(context.destination);
      if (pending) perform(pending);
    },
    apply(intent) { pending = intent; if (unlocked) perform(intent); },
    setMuted(value) {
      muted = Boolean(value);
      if (master && context) master.gain.setTargetAtTime(muted ? 0 : .32, context.currentTime, .08);
      if (!muted && pending && unlocked) perform(pending);
    },
    stop() {
      for (const bed of activeBeds.values()) { try { bed.source.stop(); } catch {} }
      activeBeds.clear();
      if (context && context.state !== "closed") context.close();
    },
    diagnostics() {
      return { unlocked, muted, warnings: warnings.slice(), heard: [...heard], activeBeds: [...activeBeds.keys()], masterGain: .32 };
    },
  };
}
