// js/paint/painter.mjs — applies the drawing protocol (planes-drawing-
// protocol-v1.md §§4-8, normative) to a 2D canvas context.
//
// A pure function of (ctx, lines, dimensions): it reads no globals and no DOM
// beyond the context handed to it. Every piece of state a program can set —
// colour, width, cap, corner, size, align, the transform, whether a path is
// open — resets to the specification's table (§5) at the start of every
// call; nothing persists between calls except what a program re-states in
// its own output (the canvas itself is drawn on cumulatively across ticks,
// which is what `clear`/`background` are for).

import { parseCommand } from "./protocol.mjs";

const SUPPORTED_VERSIONS = new Set([1]);

const DEFAULT_STROKE = Object.freeze([0, 0, 0, 1]);
const DEFAULT_FILL = Object.freeze([0, 0, 0, 0]);
const DEFAULT_WIDTH = 1;
const DEFAULT_CAP = "butt";
const DEFAULT_CORNER = "miter";
const DEFAULT_SIZE = 16;
const DEFAULT_ALIGN = "left";

// ---- OKLCH -> sRGB, pure arithmetic (specification §4, §7.3) ---------------
//
// No CSS `oklch()` string and no dependency, so this runs identically in
// every browser and is testable headless. Structure: OKLCH -> OKLab -> LMS
// cubed -> linear sRGB matrix -> gamma. Out-of-gamut colours clamp silently,
// per channel, after the full conversion (specification §4.2) — clamping the
// linear value before the gamma curve is what makes that well-defined (a
// negative linear channel has no real gamma-corrected value).

function oklchToLinearSrgb(L, C, H) {
  const hRad = (H * Math.PI) / 180;
  const a = C * Math.cos(hRad);
  const b = C * Math.sin(hRad);

  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;

  const l = l_ * l_ * l_;
  const m = m_ * m_ * m_;
  const s = s_ * s_ * s_;

  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

function linearToGamma(c) {
  const clamped = Math.max(0, Math.min(1, c));
  return clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * Math.pow(clamped, 1 / 2.4) - 0.055;
}

// OKLCH -> sRGB, each output channel 0-1.
export function oklchToRgb(L, C, H) {
  const [rl, gl, bl] = oklchToLinearSrgb(L, C, H);
  return [linearToGamma(rl), linearToGamma(gl), linearToGamma(bl)];
}

const to255 = (n) => Math.round(n * 255);

function rgbString(L, C, H) {
  const [r, g, b] = oklchToRgb(L, C, H);
  return `rgb(${to255(r)}, ${to255(g)}, ${to255(b)})`;
}

function rgbaString([L, C, H, A]) {
  const [r, g, b] = oklchToRgb(L, C, H);
  return `rgba(${to255(r)}, ${to255(g)}, ${to255(b)}, ${A})`;
}

// ---- the arc convention, pinned (specification §7) --------------------------
//
// Degrees, 0 at positive x, increasing clockwise as pictured. Canvas 2D's own
// arc() already sweeps in this exact direction for its default
// (anticlockwise=false) — y increasing downward is what makes "increasing
// angle" read as clockwise on screen — so start/end convert straight to
// radians with no flip. If `end` <= `start`, add 360 (in degree space, before
// converting) until it exceeds `start`.
function wrapArcEnd(start, end) {
  let e = end;
  while (e <= start) e += 360;
  return e;
}

const toRad = (deg) => (deg * Math.PI) / 180;

export function paint(ctx, lines, { width, height, background = "#fff" } = {}) {
  const errors = [];
  const text = [];
  let drawn = 0;

  function fillWholeArea(colorString) {
    const savedTransform = ctx.getTransform();
    const savedFillStyle = ctx.fillStyle;
    ctx.resetTransform();
    ctx.fillStyle = colorString;
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = savedFillStyle;
    ctx.setTransform(savedTransform);
  }

  // ---- reset table (specification §5) ---------------------------------------
  let stroke = DEFAULT_STROKE;
  let fill = DEFAULT_FILL;
  let cap = DEFAULT_CAP;
  let corner = DEFAULT_CORNER;
  let align = DEFAULT_ALIGN;
  let backgroundColor = background;

  ctx.strokeStyle = rgbaString(stroke);
  ctx.fillStyle = rgbaString(fill);
  ctx.lineWidth = DEFAULT_WIDTH;
  ctx.lineCap = cap;
  ctx.lineJoin = corner;
  ctx.font = `${DEFAULT_SIZE}px sans-serif`;
  ctx.textAlign = align;
  ctx.resetTransform();

  let versionSet = false;
  let sawDrawingCommand = false;
  let pathOpen = false;
  let pathStarted = false; // has the open path received its first point yet
  const transformStack = [];

  try {
    for (const line of lines) {
      const cmd = parseCommand(line);

      if (cmd.kind === "prose") {
        text.push(cmd.text);
        continue;
      }

      if (cmd.kind === "error") {
        errors.push({ tag: cmd.tag, message: cmd.message });
        continue;
      }

      if (cmd.verb === "protocol") {
        if (versionSet) {
          errors.push({
            tag: "protocol-repeated",
            message: 'a second "draw protocol" declaration is not allowed in one stream',
          });
          continue;
        }
        if (sawDrawingCommand) {
          errors.push({
            tag: "protocol-late",
            message: '"draw protocol" must appear before the first drawing command',
          });
          continue;
        }
        const [requested] = cmd.args;
        if (!SUPPORTED_VERSIONS.has(requested)) {
          // The whole stream is refused: nothing is drawn (specification
          // §1.1) — a renderer cannot refuse a picture it has already begun.
          return {
            drawn: 0,
            text: [],
            errors: [
              {
                tag: "unsupported-version",
                message:
                  `this renderer implements protocol version 1 only; the stream declared ` +
                  `version ${requested} and is refused whole`,
              },
            ],
          };
        }
        versionSet = true;
        continue;
      }

      sawDrawingCommand = true;
      let lineErrored = false;

      switch (cmd.verb) {
        case "stroke": {
          stroke = cmd.args;
          ctx.strokeStyle = rgbaString(stroke);
          break;
        }
        case "fill": {
          fill = cmd.args;
          ctx.fillStyle = rgbaString(fill);
          break;
        }
        case "width": {
          ctx.lineWidth = cmd.args[0];
          break;
        }
        case "cap": {
          cap = cmd.args[0];
          ctx.lineCap = cap;
          break;
        }
        case "corner": {
          corner = cmd.args[0];
          ctx.lineJoin = corner;
          break;
        }
        case "line": {
          const [x1, y1, x2, y2] = cmd.args;
          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.fill();
          ctx.stroke();
          break;
        }
        case "rect": {
          const [x, y, w, h] = cmd.args;
          ctx.beginPath();
          ctx.rect(x, y, w, h);
          ctx.fill();
          ctx.stroke();
          break;
        }
        case "circle": {
          const [x, y, r] = cmd.args;
          ctx.beginPath();
          ctx.arc(x, y, r, 0, 2 * Math.PI);
          ctx.fill();
          ctx.stroke();
          break;
        }
        case "ellipse": {
          const [x, y, rx, ry] = cmd.args;
          ctx.beginPath();
          ctx.ellipse(x, y, rx, ry, 0, 0, 2 * Math.PI);
          ctx.fill();
          ctx.stroke();
          break;
        }
        case "arc": {
          const [x, y, r, start, rawEnd] = cmd.args;
          const end = wrapArcEnd(start, rawEnd);
          ctx.beginPath();
          ctx.arc(x, y, r, toRad(start), toRad(end), false);
          ctx.fill();
          ctx.stroke();
          break;
        }
        case "triangle": {
          const [x1, y1, x2, y2, x3, y3] = cmd.args;
          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.lineTo(x3, y3);
          ctx.closePath();
          ctx.fill();
          ctx.stroke();
          break;
        }
        case "shape": {
          if (pathOpen) {
            errors.push({ tag: "path-already-open", message: "a shape is already open" });
            lineErrored = true;
            break;
          }
          ctx.beginPath();
          pathOpen = true;
          pathStarted = false;
          break;
        }
        case "vertex": {
          if (!pathOpen) {
            errors.push({ tag: "path-not-open", message: "vertex outside a shape ... end block" });
            lineErrored = true;
            break;
          }
          const [x, y] = cmd.args;
          if (!pathStarted) {
            ctx.moveTo(x, y);
            pathStarted = true;
          } else {
            ctx.lineTo(x, y);
          }
          break;
        }
        case "curve": {
          if (!pathOpen) {
            errors.push({ tag: "path-not-open", message: "curve outside a shape ... end block" });
            lineErrored = true;
            break;
          }
          const [cx1, cy1, cx2, cy2, x, y] = cmd.args;
          if (!pathStarted) {
            ctx.moveTo(x, y);
            pathStarted = true;
          } else {
            ctx.bezierCurveTo(cx1, cy1, cx2, cy2, x, y);
          }
          break;
        }
        case "close": {
          if (!pathOpen) {
            errors.push({ tag: "path-not-open", message: "close outside a shape ... end block" });
            lineErrored = true;
            break;
          }
          ctx.closePath();
          break;
        }
        case "end": {
          if (!pathOpen) {
            errors.push({ tag: "path-not-open", message: "end without a preceding shape" });
            lineErrored = true;
            break;
          }
          ctx.fill();
          ctx.stroke();
          pathOpen = false;
          pathStarted = false;
          break;
        }
        case "push": {
          transformStack.push(ctx.getTransform());
          break;
        }
        case "pop": {
          if (transformStack.length === 0) {
            errors.push({ tag: "unmatched-pop", message: "pop without a matching push" });
            lineErrored = true;
            break;
          }
          ctx.setTransform(transformStack.pop());
          break;
        }
        case "translate": {
          const [x, y] = cmd.args;
          ctx.translate(x, y);
          break;
        }
        case "rotate": {
          ctx.rotate(toRad(cmd.args[0]));
          break;
        }
        case "scale": {
          const [sx, sy] = cmd.args;
          ctx.scale(sx, sy);
          break;
        }
        case "label": {
          const [x, y] = cmd.args;
          ctx.fillText(cmd.text, x, y);
          break;
        }
        case "size": {
          ctx.font = `${cmd.args[0]}px sans-serif`;
          break;
        }
        case "align": {
          align = cmd.args[0];
          ctx.textAlign = align;
          break;
        }
        case "background": {
          const [L, C, H] = cmd.args;
          backgroundColor = rgbString(L, C, H);
          fillWholeArea(backgroundColor);
          break;
        }
        case "clear": {
          fillWholeArea(backgroundColor);
          break;
        }
      }

      if (!lineErrored) drawn += 1;
    }

    if (pathOpen) {
      errors.push({ tag: "path-unclosed", message: "a shape was left open at the end of the stream" });
    }
    if (transformStack.length > 0) {
      errors.push({ tag: "unmatched-push", message: "a push was left unmatched at the end of the stream" });
    }
  } finally {
    // The canvas is not left rotated/translated/scaled for the next call,
    // whatever happened during this one — identity, not "whatever the
    // transform happened to be", since a dangling unmatched push must not
    // leak its rotation out of this call either.
    ctx.resetTransform();
  }

  return { drawn, text, errors };
}
