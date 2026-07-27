// js/test/paint_export.test.mjs — the three exports, headless.
//
// Every function in js/paint/export.mjs takes its browser dependencies as
// arguments, with the globals only as defaults, so all of this runs under
// plain node with no DOM: fake documents, fake canvases, a fake
// MediaRecorder. What is NOT testable here — that the bytes are a valid PNG,
// that the WebM plays — is the human gate's, and §9.2's category E checks the
// shape of both.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  timestamp,
  exportFilename,
  downloadBlob,
  downloadSvg,
  captureScale,
  pngDataUrl,
  dataUrlToBlob,
  downloadPng,
  pickVideoMimeType,
  recordCanvas,
  VIDEO_MIME_CANDIDATES,
  VIDEO_SECONDS,
} from "../paint/export.mjs";
import { toSvg } from "../paint/svg.mjs";

const DIMENSIONS = { width: 480, height: 360, background: "#ffffff" };
const AT = new Date(2026, 6, 27, 14, 5, 3);

// A document just wide enough for downloadBlob: it records what was clicked.
function fakeDom() {
  const clicked = [];
  const created = [];
  const revoked = [];
  let nextId = 0;
  return {
    clicked,
    created,
    revoked,
    deps: {
      doc: {
        body: { appendChild() {} },
        createElement(tag) {
          const el = { tag, style: {}, remove() {} };
          el.click = () => clicked.push({ href: el.href, download: el.download });
          created.push(el);
          return el;
        },
      },
      url: {
        createObjectURL(blob) {
          const href = `blob:fake/${nextId++}`;
          created.push({ blob, href });
          return href;
        },
        revokeObjectURL(href) {
          revoked.push(href);
        },
      },
      BlobCtor: class FakeBlob {
        constructor(parts, options) {
          this.parts = parts;
          this.type = options ? options.type : undefined;
          this.size = parts.reduce((n, p) => n + (typeof p === "string" ? p.length : p.length || 0), 0);
        }
      },
    },
  };
}

// ---- filenames ---------------------------------------------------------------

test("the timestamp is local, sortable, and carries no filename-hostile character", () => {
  assert.equal(timestamp(AT), "20260727-140503");
  assert.doesNotMatch(timestamp(AT), /[:/\\ ]/);
});

test("a filename names the program, the moment and the format", () => {
  assert.equal(exportFilename("bloom", "svg", AT), "planes-bloom-20260727-140503.svg");
  assert.equal(exportFilename("snake", "png", AT), "planes-snake-20260727-140503.png");
  assert.equal(exportFilename("turtle", "webm", AT), "planes-turtle-20260727-140503.webm");
});

// ---- the download mechanism --------------------------------------------------

test("downloadBlob clicks an anchor and revokes the object URL", () => {
  const dom = fakeDom();
  const blob = new dom.deps.BlobCtor(["x"], { type: "text/plain" });
  const name = downloadBlob(blob, "a.txt", dom.deps);
  assert.equal(name, "a.txt");
  assert.equal(dom.clicked.length, 1);
  assert.equal(dom.clicked[0].download, "a.txt");
  assert.deepEqual(dom.revoked, [dom.clicked[0].href], "the object URL is released, not leaked");
});

// ---- SVG ---------------------------------------------------------------------

test("downloadSvg saves the document it is given under an svg filename", () => {
  const dom = fakeDom();
  const { svg } = toSvg(["draw circle 10 10 5"], DIMENSIONS);
  downloadSvg(svg, "turtle", { now: AT, ...dom.deps });
  assert.equal(dom.clicked[0].download, "planes-turtle-20260727-140503.svg");
  const saved = dom.created.find((c) => c.blob);
  assert.equal(saved.blob.type, "image/svg+xml;charset=utf-8");
  assert.equal(saved.blob.parts[0], svg);
  assert.match(saved.blob.parts[0], /^<svg /);
});

// ---- PNG ---------------------------------------------------------------------

test("the capture scale is twice the device pixel ratio", () => {
  assert.equal(captureScale(1), 2);
  assert.equal(captureScale(2), 4);
  assert.equal(captureScale(undefined), 2, "an unknown ratio is treated as 1, never as 0");
  assert.equal(captureScale(0), 2);
});

// A canvas just wide enough for pngDataUrl: it records the sizes it was set
// to and how each paint was scaled.
function fakeCanvas(width, height) {
  const sizes = [];
  const paints = [];
  const canvas = {
    width,
    height,
    style: {},
    getContext: () => ({}),
    toDataURL(type) {
      sizes.push([canvas.width, canvas.height]);
      return `data:${type};base64,QUJD`; // "ABC"
    },
  };
  return { canvas, sizes, paints };
}

test("pngDataUrl paints at scale, captures, then restores and repaints at 1", () => {
  const { canvas, sizes, paints } = fakeCanvas(480, 360);
  const painter = (ctx, lines, dims) => {
    paints.push({ scale: dims.scale ?? 1, w: canvas.width, h: canvas.height });
    return { drawn: lines.length, text: [], errors: [] };
  };
  const url = pngDataUrl(canvas, ["draw circle 1 1 1"], DIMENSIONS, { scale: 2, painter });

  assert.match(url, /^data:image\/png;base64,/);
  assert.deepEqual(sizes, [[960, 720]], "the capture happened at twice the size");
  assert.deepEqual(paints, [
    { scale: 2, w: 960, h: 720 },
    { scale: 1, w: 480, h: 360 },
  ]);
  assert.equal(canvas.width, 480, "the canvas is back to its own size");
  assert.equal(canvas.height, 360);
  assert.equal(canvas.style.width, "", "the pinned CSS size is released again");
});

test("pngDataUrl restores the canvas even if the capture throws", () => {
  const { canvas } = fakeCanvas(480, 360);
  canvas.toDataURL = () => {
    throw new Error("tainted");
  };
  assert.throws(() => pngDataUrl(canvas, [], DIMENSIONS, { scale: 4, painter: () => {} }), /tainted/);
  assert.equal(canvas.width, 480);
  assert.equal(canvas.height, 360);
});

test("a data URL decodes to bytes of the type it declares", () => {
  const blob = dataUrlToBlob("data:image/png;base64,QUJD", {
    atobFn: (s) => Buffer.from(s, "base64").toString("binary"),
    BlobCtor: class {
      constructor(parts, options) {
        this.parts = parts;
        this.type = options.type;
      }
    },
  });
  assert.equal(blob.type, "image/png");
  assert.deepEqual([...blob.parts[0]], [65, 66, 67]);
});

test("downloadPng saves a png at twice the device ratio", () => {
  const dom = fakeDom();
  const { canvas } = fakeCanvas(480, 360);
  downloadPng(canvas, ["draw circle 1 1 1"], DIMENSIONS, "bloom", {
    now: AT,
    dpr: 2,
    painter: () => {},
    atobFn: (s) => Buffer.from(s, "base64").toString("binary"),
    ...dom.deps,
  });
  assert.equal(dom.clicked[0].download, "planes-bloom-20260727-140503.png");
});

// ---- WebM --------------------------------------------------------------------

test("the codec preference is vp9, then vp8, then plain webm", () => {
  assert.deepEqual(VIDEO_MIME_CANDIDATES, ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"]);
  assert.equal(pickVideoMimeType(() => true), "video/webm;codecs=vp9");
  assert.equal(pickVideoMimeType((t) => !t.includes("vp9")), "video/webm;codecs=vp8");
  assert.equal(pickVideoMimeType((t) => t === "video/webm"), "video/webm");
});

test("a browser that supports none of them falls back to its own default", () => {
  assert.equal(pickVideoMimeType(() => false), undefined, "undefined means: let MediaRecorder choose");
  assert.equal(pickVideoMimeType(undefined), undefined, "no isTypeSupported at all is the same fallback");
});

function fakeRecorderClass(log) {
  return class FakeRecorder {
    constructor(stream, options) {
      this.stream = stream;
      this.mimeType = options.mimeType;
      this.state = "inactive";
      log.push(["construct", options.mimeType]);
    }
    start() {
      this.state = "recording";
      log.push(["start"]);
      this.ondataavailable({ data: { size: 3, length: 3 } });
    }
    stop() {
      this.state = "inactive";
      log.push(["stop"]);
      this.onstop();
    }
  };
}

test("recording starts, stops itself after ten seconds, and saves a webm", () => {
  const dom = fakeDom();
  const log = [];
  let scheduled = null;
  const canvas = { captureStream: (fps) => ({ fps }) };
  let saved = null;

  const handle = recordCanvas(canvas, "bloom", {
    now: AT,
    Recorder: fakeRecorderClass(log),
    isSupported: () => true,
    schedule: (fn, ms) => {
      scheduled = { fn, ms };
    },
    onFinish: (name) => {
      saved = name;
    },
    ...dom.deps,
  });

  assert.equal(handle.mimeType, "video/webm;codecs=vp9");
  assert.deepEqual(log, [["construct", "video/webm;codecs=vp9"], ["start"]]);
  assert.equal(scheduled.ms, VIDEO_SECONDS * 1000, "ten seconds, stated once");
  assert.equal(saved, null, "nothing is saved until the recording stops");

  scheduled.fn();
  assert.deepEqual(log[2], ["stop"]);
  assert.equal(saved, "planes-bloom-20260727-140503.webm");
  assert.equal(dom.clicked[0].download, "planes-bloom-20260727-140503.webm");
});

test("stopping early is safe, and the auto-stop afterwards is a no-op", () => {
  const dom = fakeDom();
  const log = [];
  let scheduled = null;
  const handle = recordCanvas({ captureStream: () => ({}) }, "snake", {
    now: AT,
    Recorder: fakeRecorderClass(log),
    isSupported: () => true,
    schedule: (fn) => {
      scheduled = fn;
    },
    ...dom.deps,
  });
  handle.stop();
  scheduled();
  assert.equal(log.filter((e) => e[0] === "stop").length, 1, "the recorder is stopped once, not twice");
  assert.equal(dom.clicked.length, 1);
});

test("a browser with no MediaRecorder says so rather than failing silently", () => {
  assert.throws(
    () => recordCanvas({ captureStream: () => ({}) }, "bloom", { Recorder: undefined }),
    /no MediaRecorder/,
  );
});
