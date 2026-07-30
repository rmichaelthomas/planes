// js/paint/painter.mjs — the canvas renderer: a SINK for js/paint/stream.mjs
// (planes-drawing-protocol-v1.md §§4-8, planes-drawing-protocol-v2.md,
// normative).
//
// This file knows how to draw a circle on a 2D context. It does not know what
// a stream is, what the version declaration means, when a path is open, or
// what any error is called — all of that is stream.mjs's, shared verbatim
// with svg.mjs. What is left here is exactly the part that is canvas.
//
// `paint` stays a pure function of (ctx, lines, dimensions): it reads no
// globals and no DOM beyond the context handed to it (and, now, an optional
// injected `offscreenCanvas` factory — see §6.1 below). Every piece of state
// a program can set — colour, width, cap, corner, size, align, the
// transform, whether a path is open — resets to the specification's table
// (§5) at the start of every call; nothing persists between calls except
// what a program re-states in its own output (the canvas itself is drawn on
// cumulatively across ticks, which is what `clear`/`background` are for).
//
// STATE TRACKING (v2). Every piece of paint state a program can set is now
// tracked in a JS variable, not just pushed onto `ctx` and left there as the
// source of truth. This is what `unclip` needs: releasing a clip region has
// no native "undo just the clip" in Canvas 2D, only `ctx.restore()`, and
// `ctx.restore()` rolls back EVERYTHING `ctx.save()` captured — fillStyle,
// strokeStyle, width, cap, corner, font, align, dash, alpha and composite
// operation included, not only the clip region. Without re-applying the
// tracked JS state after `ctx.restore()`, `unclip` would silently undo a
// colour or width change made between `clip` and `unclip` — a real
// divergence from svg.mjs, where clipping never touches colour state at all
// (planes-drawing-protocol-v2.md §12, invariant 8: "the two sinks agree").

import { walk, FONT_FAMILY } from "./stream.mjs";
import { oklchToRgb, rgbString, rgbaString } from "./color.mjs";

// Re-exported, not redefined: js/paint/color.mjs holds the one conversion
// both renderers use.
export { oklchToRgb };

const toRad = (deg) => (deg * Math.PI) / 180;

// A real <canvas> (or OffscreenCanvas) when either exists; Node has neither,
// so a headless run only reaches this if a stream actually needs the
// offscreen composite AND the caller supplied no `offscreenCanvas` — tests
// that exercise that path inject a fake one (js/test/shadow_parity.test.mjs).
function defaultOffscreenCanvas(w, h) {
  if (typeof OffscreenCanvas !== "undefined") return new OffscreenCanvas(w, h);
  if (typeof document !== "undefined" && document.createElement) {
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    return c;
  }
  throw new Error(
    "painter.mjs: a shadow needs an offscreen canvas to cast once, and this environment has neither " +
      "OffscreenCanvas nor document.createElement — pass { offscreenCanvas } explicitly",
  );
}

function canvasSink(ctx, { width, height, background, scale, offscreenCanvas }) {
  let backgroundColor = background;
  const transformStack = [];

  // ---- tracked paint state (see file header) ---------------------------
  let strokeLcha = [0, 0, 0, 1];
  let fillState = { kind: "solid", lcha: [0, 0, 0, 0] }; // | { kind: "gradient", gradient }
  let lineWidthVal = 1;
  let capWord = "butt";
  let cornerWord = "miter";
  let fontSizePx = 16;
  let alignWord = "left";
  let dashOn = 0;
  let dashOff = 0;
  let alphaVal = 1;
  let blendWord = "normal";
  let shadowState = null; // | { dx, dy, blur, L, C, H }
  let pendingClip = false;
  // Real ctx.save() depth this call has opened and not yet closed. Unlike
  // `transformStack` (a plain array scoped to this call, harmless if some
  // pushes are never popped), ctx.save()/restore() is a stack the CONTEXT
  // ITSELF keeps, and `ctx` is reused across calls (once per tick). A stream
  // that ends with a clip left open (stream.mjs's `clip-unclosed`) must not
  // leak an unbalanced save() into the next call on the same ctx — finish()
  // unwinds whatever this call opened and never closed.
  let saveDepth = 0;

  let offCanvas = null;
  let offCtx = null;

  // "Identity" means one protocol pixel, not one device pixel. At scale 1
  // that is the context's own identity; above it — a supersampled export
  // (js/paint/export.mjs) — the backing store is larger than the drawing
  // area, and this is the one place that difference lives. A program's
  // coordinates never change.
  const toIdentity =
    scale === 1
      ? () => ctx.resetTransform()
      : () => ctx.setTransform(scale, 0, 0, scale, 0, 0);

  function fillWholeArea(colorString) {
    const savedTransform = ctx.getTransform();
    const savedFillStyle = ctx.fillStyle;
    toIdentity();
    ctx.fillStyle = colorString;
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = savedFillStyle;
    ctx.setTransform(savedTransform);
  }

  // ---- reapplying tracked state (unclip's counterpart to ctx.restore()) -

  function applyFillStyle() {
    ctx.fillStyle = fillState.kind === "gradient" ? fillState.gradient : rgbaString(fillState.lcha);
  }

  function applyDash(targetCtx) {
    if (!targetCtx.setLineDash) return;
    targetCtx.setLineDash(dashOn === 0 && dashOff === 0 ? [] : [dashOn * scale, dashOff * scale]);
  }

  // §6.2: shadowBlur/OffsetX/OffsetY live in the BACKING STORE's pixel
  // space, which `scale` above 1 stretches relative to a program's own
  // coordinates — every other geometric dimension is already stretched by
  // the CTM `toIdentity` sets up, but the shadow properties are not
  // transform-relative at all, so they are multiplied by `scale` explicitly
  // here. Unhandled, every exported PNG would carry shadows two to four
  // times too small relative to the picture (measured at export's default
  // scale of 2x-4x devicePixelRatio).
  function applyShadow() {
    if (!shadowState) {
      ctx.shadowColor = "transparent";
      ctx.shadowBlur = 0;
      ctx.shadowOffsetX = 0;
      ctx.shadowOffsetY = 0;
      return;
    }
    const { dx, dy, blur, L, C, H } = shadowState;
    // §6, "alpha comes from the current alpha state, not a seventh argument".
    ctx.shadowColor = rgbaString([L, C, H, alphaVal]);
    ctx.shadowBlur = blur * scale;
    ctx.shadowOffsetX = dx * scale;
    ctx.shadowOffsetY = dy * scale;
  }

  function applyAllState() {
    ctx.strokeStyle = rgbaString(strokeLcha);
    applyFillStyle();
    ctx.lineWidth = lineWidthVal;
    ctx.lineCap = capWord;
    ctx.lineJoin = cornerWord;
    ctx.font = `${fontSizePx}px ${FONT_FAMILY}`;
    ctx.textAlign = alignWord;
    applyDash(ctx);
    ctx.globalAlpha = alphaVal;
    ctx.globalCompositeOperation = blendWord === "add" ? "lighter" : "source-over";
    applyShadow();
  }

  // ---- clip (§8.3) -------------------------------------------------------
  //
  // `clip` opens a masking region; the NEXT completed shape or path defines
  // it (by becoming the argument to ctx.clip(), called on its own path right
  // before it is filled/stroked — which paints it exactly as it would have
  // painted unclipped, since a shape is never outside its own boundary);
  // `unclip` releases it. Raw ctx.save()/ctx.restore(), never
  // `transformStack` — that stack holds only the transform push/pop saves,
  // and entangling the two would make an unmatched clip able to leak a
  // rotation, or a pop able to silently release a clip it never opened.
  function maybeClip() {
    if (!pendingClip) return;
    ctx.clip();
    pendingClip = false;
  }

  // ---- shadow single-cast (§6.1) -----------------------------------------
  //
  // Canvas casts a shadow PER DRAWING OPERATION. Every shape here fills then
  // strokes, so with a shadow set, a shape with both a visible fill and a
  // visible stroke casts two overlapping shadows and comes out double-dark
  // — SVG's feDropShadow filters the rendered element once, so this is a
  // real cross-renderer divergence, not a cosmetic one.
  //
  // Fixed by drawing the mark to a reused offscreen canvas — no shadow set
  // there at all — then compositing that ALREADY-fully-painted mark onto the
  // main canvas in one `drawImage`, with the shadow set for that one
  // operation. One cast, over the composited mark: exactly what
  // feDropShadow does. The offscreen canvas is allocated once per paint()
  // call, on first actual need (a stream that never uses `shadow`, or one
  // where a mark is only ever fill-only or stroke-only, allocates nothing),
  // and reused — `clearRect` between marks, not a fresh allocation.
  function getOffscreen() {
    if (!offCtx) {
      const factory = offscreenCanvas || defaultOffscreenCanvas;
      const w = Math.round(width * scale);
      const h = Math.round(height * scale);
      offCanvas = factory(w, h);
      offCtx = offCanvas.getContext("2d");
    }
    return { canvas: offCanvas, ctx: offCtx };
  }

  function fillVisible() {
    return fillState.kind === "gradient" || fillState.lcha[3] > 0;
  }
  function strokeVisible() {
    return strokeLcha[3] > 0;
  }

  // `buildGeometry(c)` performs the shape's own path-construction calls
  // against whichever context it is given — nothing else; renderMark itself
  // owns beginPath, clip, fill, stroke and the shadow single-cast decision
  // uniformly for every shape and for the path block, so none of that logic
  // is duplicated per verb.
  function renderMark(buildGeometry) {
    ctx.beginPath();
    buildGeometry(ctx);
    maybeClip();

    if (!shadowState || !fillVisible() || !strokeVisible()) {
      ctx.fill();
      ctx.stroke();
      return;
    }

    const { canvas: offC, ctx: off } = getOffscreen();
    const w = Math.round(width * scale);
    const h = Math.round(height * scale);
    off.clearRect(0, 0, w, h);
    off.setTransform(ctx.getTransform());
    off.strokeStyle = ctx.strokeStyle;
    off.fillStyle = ctx.fillStyle;
    off.lineWidth = ctx.lineWidth;
    off.lineCap = ctx.lineCap;
    off.lineJoin = ctx.lineJoin;
    off.globalAlpha = alphaVal;
    applyDash(off);
    // No shadow on `off` at all — it stays unset for the life of the
    // context, so even though this mark fills AND strokes, `off` only ever
    // receives one, un-shadowed rendering of it: no double shadow possible.
    off.beginPath();
    buildGeometry(off);
    off.fill();
    off.stroke();

    const savedTransform = ctx.getTransform();
    const savedAlpha = ctx.globalAlpha;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    // globalAlpha back to 1: the mark's own alpha is already baked into what
    // was just drawn onto `off` (via off.globalAlpha above) — multiplying
    // again here would dim it twice. Shadow and blend stay exactly as
    // `applyShadow`/`blend` last set them on `ctx`, so both apply to this
    // one compositing operation, which is the whole point.
    ctx.globalAlpha = 1;
    ctx.drawImage(offC, 0, 0);
    ctx.setTransform(savedTransform);
    ctx.globalAlpha = savedAlpha;
  }

  // A path under construction, recorded rather than drawn immediately, so
  // `end()` can replay it through renderMark exactly like any other shape
  // (needed for the path block to get the same single-shadow, clip and
  // dual-context treatment every other verb gets).
  let pathOps = [];

  return {
    reset(defaults) {
      strokeLcha = defaults.stroke;
      fillState = { kind: "solid", lcha: defaults.fill };
      lineWidthVal = defaults.width;
      capWord = defaults.cap;
      cornerWord = defaults.corner;
      fontSizePx = defaults.size;
      alignWord = defaults.align;
      [dashOn, dashOff] = defaults.dash;
      alphaVal = defaults.alpha;
      blendWord = defaults.blend;
      shadowState = null;
      pendingClip = false;
      pathOps = [];
      toIdentity();
      applyAllState();
      backgroundColor = background;
    },

    stroke(lcha) {
      strokeLcha = lcha;
      ctx.strokeStyle = rgbaString(lcha);
    },
    fill(lcha) {
      fillState = { kind: "solid", lcha };
      applyFillStyle();
    },
    width(w) {
      lineWidthVal = w;
      ctx.lineWidth = w;
    },
    cap(word) {
      capWord = word;
      ctx.lineCap = word;
    },
    corner(word) {
      cornerWord = word;
      ctx.lineJoin = word;
    },

    // §5.2: a gradient replaces the current fill; a later plain `fill`
    // replaces the gradient right back. Canvas already gives this for free
    // — `ctx.fillStyle` accepts either a CSS colour string or a
    // CanvasGradient, and every fill()/stroke() call just uses whatever it
    // currently holds.
    gradient(kindWord, geomArgs, stops) {
      const grad =
        kindWord === "linear"
          ? ctx.createLinearGradient(...geomArgs)
          : ctx.createRadialGradient(geomArgs[0], geomArgs[1], 0, geomArgs[0], geomArgs[1], geomArgs[2]);
      for (const { offset, L, C, H, A } of stops) {
        grad.addColorStop(offset, rgbaString([L, C, H, A]));
      }
      fillState = { kind: "gradient", gradient: grad };
      applyFillStyle();
    },

    shadow(dx, dy, blur, L, C, H) {
      shadowState = { dx, dy, blur, L, C, H };
      applyShadow();
    },
    blend(word) {
      blendWord = word;
      ctx.globalCompositeOperation = word === "add" ? "lighter" : "source-over";
    },
    alpha(a) {
      alphaVal = a;
      ctx.globalAlpha = a;
      // The shadow's own colour carries the current alpha (§6), so a
      // change here must be reflected in the shadow immediately, not only
      // on the next `shadow` call.
      if (shadowState) applyShadow();
    },
    dash(on, off) {
      dashOn = on;
      dashOff = off;
      applyDash(ctx);
    },
    clip() {
      ctx.save();
      saveDepth += 1;
      pendingClip = true;
    },
    unclip() {
      if (pendingClip) {
        // No shape ever consumed the clip — nothing was ever established,
        // so there is nothing to release beyond the save() clip() paired.
        pendingClip = false;
      }
      ctx.restore();
      saveDepth -= 1;
      applyAllState();
    },

    line(x1, y1, x2, y2) {
      renderMark((c) => {
        c.moveTo(x1, y1);
        c.lineTo(x2, y2);
      });
    },
    rect(x, y, w, h, turn) {
      renderMark((c) => {
        if (turn === 0) {
          c.rect(x, y, w, h);
          return;
        }
        c.save();
        c.translate(x + w / 2, y + h / 2);
        c.rotate(toRad(turn));
        c.rect(-w / 2, -h / 2, w, h);
        c.restore();
      });
    },
    circle(x, y, r) {
      renderMark((c) => c.arc(x, y, r, 0, 2 * Math.PI));
    },
    // The rotation parameter canvas's own ellipse() always had, now driven
    // by the protocol's optional fifth argument instead of a hardcoded 0
    // (planes-drawing-protocol-v2.md §9.2: rotation about the mark's own
    // centre — exactly what this call already does with no other change).
    ellipse(x, y, rx, ry, turn) {
      renderMark((c) => c.ellipse(x, y, rx, ry, toRad(turn), 0, 2 * Math.PI));
    },
    // `end` arrives already wrapped past `start` (stream.mjs, §7). Canvas 2D's
    // own arc() sweeps in this exact direction for its default
    // (anticlockwise=false) — y increasing downward is what makes "increasing
    // angle" read as clockwise on screen — so both angles convert straight to
    // radians with no flip.
    arc(x, y, r, start, end) {
      renderMark((c) => c.arc(x, y, r, toRad(start), toRad(end), false));
    },
    triangle(x1, y1, x2, y2, x3, y3) {
      renderMark((c) => {
        c.moveTo(x1, y1);
        c.lineTo(x2, y2);
        c.lineTo(x3, y3);
        c.closePath();
      });
    },

    shape() {
      pathOps = [];
    },
    vertex(x, y, first) {
      pathOps.push(first ? ["moveTo", x, y] : ["lineTo", x, y]);
    },
    curve(cx1, cy1, cx2, cy2, x, y, first) {
      pathOps.push(first ? ["moveTo", x, y] : ["bezierCurveTo", cx1, cy1, cx2, cy2, x, y]);
    },
    close() {
      pathOps.push(["closePath"]);
    },
    end() {
      const ops = pathOps;
      renderMark((c) => {
        for (const [method, ...args] of ops) c[method](...args);
      });
      pathOps = [];
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
      fontSizePx = n;
      ctx.font = `${n}px ${FONT_FAMILY}`;
    },
    align(word) {
      alignWord = word;
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
      // A stream that ends with an unmatched `clip` (stream.mjs's
      // `clip-unclosed`) never calls unclip(), so its ctx.save() is unwound
      // here instead — this ctx is reused across calls, and a leftover
      // save() would otherwise corrupt every later one.
      while (saveDepth > 0) {
        ctx.restore();
        saveDepth -= 1;
      }
      toIdentity();
    },
  };
}

// `scale` above 1 means the context's backing store is that many device
// pixels per protocol pixel — what a supersampled PNG export sets up before
// re-running the same stream (js/paint/export.mjs §6.2). It changes nothing
// about what a program says, only how finely it is resolved.
//
// `offscreenCanvas(w, h)`, optional: a factory for the second canvas the
// single-shadow-cast technique needs (§6.1). Defaults to OffscreenCanvas or
// a real <canvas> element, whichever exists; a test that exercises the
// shadow-compositing path injects a fake one, since neither exists in Node.
export function paint(
  ctx,
  lines,
  { width, height, background = "#fff", scale = 1, offscreenCanvas } = {},
) {
  const { drawn, text, errors } = walk(
    lines,
    canvasSink(ctx, { width, height, background, scale, offscreenCanvas }),
  );
  return { drawn, text, errors };
}
