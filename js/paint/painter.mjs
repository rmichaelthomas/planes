// js/paint/painter.mjs — the canvas renderer: a SINK for js/paint/stream.mjs
// (planes-drawing-protocol-v1.md §§4-8, normative).
//
// This file knows how to draw a circle on a 2D context. It does not know what
// a stream is, what the version declaration means, when a path is open, or
// what any error is called — all of that is stream.mjs's, shared verbatim
// with svg.mjs. What is left here is exactly the part that is canvas.
//
// `paint` stays a pure function of (ctx, lines, dimensions): it reads no
// globals and no DOM beyond the context handed to it. Every piece of state a
// program can set — colour, width, cap, corner, size, align, the transform,
// whether a path is open — resets to the specification's table (§5) at the
// start of every call; nothing persists between calls except what a program
// re-states in its own output (the canvas itself is drawn on cumulatively
// across ticks, which is what `clear`/`background` are for).

import { walk, FONT_FAMILY } from "./stream.mjs";
import { oklchToRgb, rgbString, rgbaString } from "./color.mjs";

// Re-exported, not redefined: js/paint/color.mjs holds the one conversion
// both renderers use.
export { oklchToRgb };

const toRad = (deg) => (deg * Math.PI) / 180;

function canvasSink(ctx, { width, height, background }) {
  let backgroundColor = background;
  const transformStack = [];

  function fillWholeArea(colorString) {
    const savedTransform = ctx.getTransform();
    const savedFillStyle = ctx.fillStyle;
    ctx.resetTransform();
    ctx.fillStyle = colorString;
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = savedFillStyle;
    ctx.setTransform(savedTransform);
  }

  return {
    reset(defaults) {
      ctx.strokeStyle = rgbaString(defaults.stroke);
      ctx.fillStyle = rgbaString(defaults.fill);
      ctx.lineWidth = defaults.width;
      ctx.lineCap = defaults.cap;
      ctx.lineJoin = defaults.corner;
      ctx.font = `${defaults.size}px ${FONT_FAMILY}`;
      ctx.textAlign = defaults.align;
      ctx.resetTransform();
      backgroundColor = background;
    },

    stroke(lcha) {
      ctx.strokeStyle = rgbaString(lcha);
    },
    fill(lcha) {
      ctx.fillStyle = rgbaString(lcha);
    },
    width(w) {
      ctx.lineWidth = w;
    },
    cap(word) {
      ctx.lineCap = word;
    },
    corner(word) {
      ctx.lineJoin = word;
    },

    line(x1, y1, x2, y2) {
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.fill();
      ctx.stroke();
    },
    rect(x, y, w, h) {
      ctx.beginPath();
      ctx.rect(x, y, w, h);
      ctx.fill();
      ctx.stroke();
    },
    circle(x, y, r) {
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fill();
      ctx.stroke();
    },
    ellipse(x, y, rx, ry) {
      ctx.beginPath();
      ctx.ellipse(x, y, rx, ry, 0, 0, 2 * Math.PI);
      ctx.fill();
      ctx.stroke();
    },
    // `end` arrives already wrapped past `start` (stream.mjs, §7). Canvas 2D's
    // own arc() sweeps in this exact direction for its default
    // (anticlockwise=false) — y increasing downward is what makes "increasing
    // angle" read as clockwise on screen — so both angles convert straight to
    // radians with no flip.
    arc(x, y, r, start, end) {
      ctx.beginPath();
      ctx.arc(x, y, r, toRad(start), toRad(end), false);
      ctx.fill();
      ctx.stroke();
    },
    triangle(x1, y1, x2, y2, x3, y3) {
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.lineTo(x3, y3);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    },

    shape() {
      ctx.beginPath();
    },
    vertex(x, y, first) {
      if (first) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    },
    curve(cx1, cy1, cx2, cy2, x, y, first) {
      if (first) ctx.moveTo(x, y);
      else ctx.bezierCurveTo(cx1, cy1, cx2, cy2, x, y);
    },
    close() {
      ctx.closePath();
    },
    end() {
      ctx.fill();
      ctx.stroke();
    },

    push() {
      transformStack.push(ctx.getTransform());
    },
    pop() {
      ctx.setTransform(transformStack.pop());
    },
    translate(x, y) {
      ctx.translate(x, y);
    },
    rotate(deg) {
      ctx.rotate(toRad(deg));
    },
    scale(sx, sy) {
      ctx.scale(sx, sy);
    },

    label(x, y, text) {
      ctx.fillText(text, x, y);
    },
    size(n) {
      ctx.font = `${n}px ${FONT_FAMILY}`;
    },
    align(word) {
      ctx.textAlign = word;
    },

    background(L, C, H) {
      backgroundColor = rgbString(L, C, H);
      fillWholeArea(backgroundColor);
    },
    clear() {
      fillWholeArea(backgroundColor);
    },

    // The canvas is not left rotated/translated/scaled for the next call,
    // whatever happened during this one — identity, not "whatever the
    // transform happened to be", since a dangling unmatched push must not
    // leak its rotation out of this call either.
    finish() {
      ctx.resetTransform();
    },
  };
}

export function paint(ctx, lines, { width, height, background = "#fff" } = {}) {
  const { drawn, text, errors } = walk(lines, canvasSink(ctx, { width, height, background }));
  return { drawn, text, errors };
}
