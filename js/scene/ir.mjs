export class SceneIntentError extends Error {
  constructor(record, line, message) {
    super(`scene ${record} at output line ${line}: ${message}`);
    this.name = "SceneIntentError";
    this.record = record;
    this.line = line;
  }
}

const number = (token, record, line, { normalized = false } = {}) => {
  const value = Number(token);
  if (!Number.isFinite(value)) throw new SceneIntentError(record, line, `expected number, received ${token}`);
  if (normalized && (value < 0 || value > 1)) {
    throw new SceneIntentError(record, line, `expected normalized number, received ${token}`);
  }
  return value;
};

const exact = (parts, count, record, line) => {
  if (parts.length !== count) {
    throw new SceneIntentError(record, line, `expected ${count - 2} fields, received ${parts.length - 2}`);
  }
};

export function parseSceneIntent(lines) {
  const intent = {
    protocol: null,
    camera: null,
    environment: null,
    subjects: [],
    routes: [],
    signals: [],
    weather: [],
    actions: [],
    cues: [],
    audio: { beds: [], cues: [] },
    warnings: [],
  };

  lines.forEach((raw, index) => {
    const line = index + 1;
    const parts = raw.trim().split(/\s+/);
    if (parts[0] === "audio") {
      const record = parts[1] || "audio";
      if (record === "bed") {
        exact(parts, 5, record, line);
        intent.audio.beds.push({ id: parts[2], gain: number(parts[3], record, line), anchor: parts[4] });
      } else if (record === "cue") {
        exact(parts, 6, record, line);
        intent.audio.cues.push({
          id: parts[2], gain: number(parts[3], record, line), anchor: parts[4], serial: number(parts[5], record, line),
        });
      } else {
        intent.warnings.push({ line, message: `unknown audio record: ${record}` });
      }
      return;
    }
    if (parts[0] !== "scene") return;

    const record = parts[1] || "scene";
    switch (record) {
      case "protocol":
        exact(parts, 3, record, line);
        intent.protocol = number(parts[2], record, line);
        if (intent.protocol !== 1) throw new SceneIntentError(record, line, `unsupported version ${intent.protocol}`);
        break;
      case "camera":
        exact(parts, 6, record, line);
        intent.camera = {
          id: parts[2],
          x: number(parts[3], record, line, { normalized: true }),
          y: number(parts[4], record, line, { normalized: true }),
          zoom: number(parts[5], record, line),
        };
        if (intent.camera.zoom <= 0) throw new SceneIntentError(record, line, "zoom must be greater than zero");
        break;
      case "environment":
        exact(parts, 5, record, line);
        intent.environment = { id: parts[2], light: parts[3], weather: parts[4] };
        break;
      case "subject":
        exact(parts, 9, record, line);
        intent.subjects.push({
          id: parts[2], asset: parts[3],
          x: number(parts[4], record, line, { normalized: true }),
          y: number(parts[5], record, line, { normalized: true }),
          scale: number(parts[6], record, line), visibility: parts[7], state: parts[8],
        });
        break;
      case "route":
        exact(parts, 9, record, line);
        intent.routes.push({
          id: parts[2],
          fromX: number(parts[3], record, line, { normalized: true }),
          fromY: number(parts[4], record, line, { normalized: true }),
          toX: number(parts[5], record, line, { normalized: true }),
          toY: number(parts[6], record, line, { normalized: true }),
          state: parts[7], progress: number(parts[8], record, line, { normalized: true }),
        });
        break;
      case "signal":
        exact(parts, 7, record, line);
        intent.signals.push({
          id: parts[2],
          x: number(parts[3], record, line, { normalized: true }),
          y: number(parts[4], record, line, { normalized: true }),
          tone: parts[5], state: parts[6],
        });
        break;
      case "weather":
        exact(parts, 5, record, line);
        intent.weather.push({ kind: parts[2], intensity: number(parts[3], record, line), direction: parts[4] });
        break;
      case "action":
        exact(parts, 7, record, line);
        intent.actions.push({ subject: parts[2], kind: parts[3], choice: parts[4], label: parts[5].replaceAll("-", " "), emphasis: parts[6] });
        break;
      case "cue":
        exact(parts, 4, record, line);
        intent.cues.push({ id: parts[2], serial: number(parts[3], record, line) });
        break;
      default:
        intent.warnings.push({ line, message: `unknown scene record: ${record}` });
    }
  });

  if (intent.protocol === null) throw new SceneIntentError("protocol", 0, "missing scene protocol");
  if (!intent.camera) throw new SceneIntentError("camera", 0, "missing critical camera record");
  if (!intent.environment) throw new SceneIntentError("environment", 0, "missing critical environment record");
  return intent;
}
