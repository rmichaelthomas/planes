// js/paint/export.mjs — the picture leaves the page: SVG, PNG and WebM.
//
// Three native browser capabilities and no library, no CDN, no bundler. Each
// export works on the LAST RENDERED STREAM — the exact lines that produced
// what is on screen — and never re-runs the program: a ticking program run
// twice is two different pictures, and "save" that saved a different frame
// than the one you were looking at would be a lie about what it did.
//
// WHAT EACH EXPORT MEANS (specification §8.1). A renderer producing a file
// captures ONE STREAM. For a program that draws once that is the whole
// picture; for a program that redraws continuously it is the frame that was
// captured — a snapshot, not an animation. SVG has no notion of "the
// animation this came from", so a learner expecting one has to be told, and
// paint.html says it under the buttons rather than leaving it to be
// discovered.
//
// Everything here that can be tested without a DOM is a plain function taking
// its dependencies as arguments; the browser globals are defaults, not
// assumptions.

import { paint } from "./painter.mjs";

// Local time, sortable: 20260727-140530. Not ISO, because a colon is not a
// filename character everywhere and a saved file should open where it lands.
export function timestamp(date) {
  const p = (n, w = 2) => String(n).padStart(w, "0");
  return (
    `${date.getFullYear()}${p(date.getMonth() + 1)}${p(date.getDate())}` +
    `-${p(date.getHours())}${p(date.getMinutes())}${p(date.getSeconds())}`
  );
}

export function exportFilename(program, extension, date) {
  return `planes-${program}-${timestamp(date)}.${extension}`;
}

// Blob -> object URL -> a synthetic anchor click -> revoke. The revoke is the
// part that is easy to leave out and the part that leaks the whole blob for
// the life of the document if you do.
export function downloadBlob(blob, filename, { doc = globalThis.document, url = globalThis.URL } = {}) {
  const href = url.createObjectURL(blob);
  const a = doc.createElement("a");
  a.href = href;
  a.download = filename;
  a.style.display = "none";
  doc.body.appendChild(a);
  a.click();
  a.remove();
  url.revokeObjectURL(href);
  return filename;
}

// ---- SVG (§6.1) --------------------------------------------------------------

export function downloadSvg(svgText, program, { now = new Date(), ...deps } = {}) {
  const blob = new (deps.BlobCtor || globalThis.Blob)([svgText], { type: "image/svg+xml;charset=utf-8" });
  return downloadBlob(blob, exportFilename(program, "svg", now), deps);
}

// ---- PNG, supersampled (§6.2) ------------------------------------------------

// Twice the device pixel ratio: a drawing meant to be printed or hung leaves
// at archival density, not at whatever monitor happened to be attached.
export function captureScale(devicePixelRatio = 1) {
  return 2 * (devicePixelRatio || 1);
}

// Scale the backing store, re-run the same stream through the same renderer,
// read the pixels, then put the canvas back exactly as it was and repaint —
// so an export is invisible to whatever is on screen, including a running
// animation whose next frame lands a few milliseconds later.
//
// The CSS size is pinned across the swap because a canvas with no CSS size
// lays out at its backing-store size, and a page that jumped to double width
// and back mid-export would be a visible artefact of a silent operation.
export function pngDataUrl(canvas, lines, dimensions, { scale, painter = paint } = {}) {
  const { width, height } = dimensions;
  const priorStyleWidth = canvas.style ? canvas.style.width : undefined;
  const priorStyleHeight = canvas.style ? canvas.style.height : undefined;

  if (canvas.style) {
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
  }

  try {
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    painter(canvas.getContext("2d"), lines, { ...dimensions, scale });
    return canvas.toDataURL("image/png");
  } finally {
    canvas.width = width;
    canvas.height = height;
    painter(canvas.getContext("2d"), lines, dimensions);
    if (canvas.style) {
      canvas.style.width = priorStyleWidth ?? "";
      canvas.style.height = priorStyleHeight ?? "";
    }
  }
}

export function dataUrlToBlob(dataUrl, { atobFn = globalThis.atob, BlobCtor = globalThis.Blob } = {}) {
  const [header, encoded] = dataUrl.split(",");
  const mime = /data:([^;]+)/.exec(header)[1];
  const binary = atobFn(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new BlobCtor([bytes], { type: mime });
}

export function downloadPng(canvas, lines, dimensions, program, { now = new Date(), dpr, ...deps } = {}) {
  const scale = captureScale(dpr ?? globalThis.devicePixelRatio);
  const dataUrl = pngDataUrl(canvas, lines, dimensions, { scale, painter: deps.painter });
  return downloadBlob(dataUrlToBlob(dataUrl, deps), exportFilename(program, "png", now), deps);
}

// ---- WebM (§6.3) -------------------------------------------------------------

// VP9 where it exists, VP8 next, then plain webm, then whatever the browser
// picks for itself. `undefined` is a real answer, not a failure: MediaRecorder
// with no mimeType uses its own default, which is what the graceful fallback
// means.
export const VIDEO_MIME_CANDIDATES = Object.freeze([
  "video/webm;codecs=vp9",
  "video/webm;codecs=vp8",
  "video/webm",
]);

export function pickVideoMimeType(isSupported, candidates = VIDEO_MIME_CANDIDATES) {
  if (typeof isSupported !== "function") return undefined;
  return candidates.find((type) => isSupported(type));
}

export const VIDEO_SECONDS = 10;
export const VIDEO_FPS = 30;

// Records the canvas for `seconds` and stops itself. A recording that ran
// until someone remembered to stop it would be a different length every time
// and, on a page left open, unbounded.
export function recordCanvas(
  canvas,
  program,
  {
    seconds = VIDEO_SECONDS,
    fps = VIDEO_FPS,
    now = new Date(),
    Recorder = globalThis.MediaRecorder,
    isSupported = globalThis.MediaRecorder && globalThis.MediaRecorder.isTypeSupported
      ? (t) => globalThis.MediaRecorder.isTypeSupported(t)
      : undefined,
    schedule = (fn, ms) => setTimeout(fn, ms),
    onFinish,
    ...deps
  } = {},
) {
  if (!Recorder) throw new Error("this browser has no MediaRecorder, so video export is unavailable");

  const stream = canvas.captureStream(fps);
  const mimeType = pickVideoMimeType(isSupported);
  const recorder = new Recorder(stream, mimeType ? { mimeType } : {});
  const chunks = [];

  recorder.ondataavailable = (e) => {
    if (e.data && e.data.size) chunks.push(e.data);
  };
  recorder.onstop = () => {
    const BlobCtor = deps.BlobCtor || globalThis.Blob;
    const blob = new BlobCtor(chunks, { type: recorder.mimeType || mimeType || "video/webm" });
    const filename = downloadBlob(blob, exportFilename(program, "webm", now), deps);
    if (onFinish) onFinish(filename);
  };

  recorder.start();
  schedule(() => {
    if (recorder.state !== "inactive") recorder.stop();
  }, seconds * 1000);

  return {
    mimeType,
    stop() {
      if (recorder.state !== "inactive") recorder.stop();
    },
  };
}
