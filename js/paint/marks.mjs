// js/paint/marks.mjs — a THIRD sink for js/paint/stream.mjs that draws
// nothing.
//
// It walks the same stream the canvas and SVG sinks walk, and instead of
// painting, it records what each mark IS: its geometry in the program's own
// coordinates, the transform in force when it was emitted, and the index of
// the stream line that emitted it. That list is what makes a picture
// clickable — js/paint/hit.mjs turns it into "which mark is under this
// point", and the garden's why panel turns that into "where did this come
// from".
//
// WHY THIS IS NOT IN THE PAINTER. The painter has a live 2D context with a
// CTM it can read at any moment, and reading it would have been three lines.
// It would also have made every question about provenance a question about a
// canvas: untestable without a DOM, unavailable to the SVG path, and impossible
// to reason about without stepping through drawing code. This module is pure
// arithmetic over numbers. It runs in Node, it cannot break the painter
// because the painter does not import it, and every claim it makes can be
// checked by multiplying three matrices by hand.
//
// IT KEEPS ITS OWN MATRIX STACK, and that is the point. stream.mjs tracks
// `pushDepth` and nothing else about the transform, and stays that way — the
// shared walk has never known how a renderer composes space and must not
// start. So this sink composes its own, in exactly the sense the protocol
// pins (§6.4: `rotate` is clockwise as pictured, degrees; `scale` about the
// current origin).
//
// A matrix is [a, b, c, d, e, f], the same six numbers canvas and SVG both
// use, mapping (x, y) to (a·x + c·y + e, b·x + d·y + f).

const IDENTITY = Object.freeze([1, 0, 0, 1, 0, 0]);

const toRad = (deg) => (deg * Math.PI) / 180;

// m THEN n — n applied in m's coordinate system, which is the order a
// transform stack composes in: `translate` then `rotate` rotates about the
// translated origin.
export function multiply(m, n) {
  return [
    m[0] * n[0] + m[2] * n[1],
    m[1] * n[0] + m[3] * n[1],
    m[0] * n[2] + m[2] * n[3],
    m[1] * n[2] + m[3] * n[3],
    m[0] * n[4] + m[2] * n[5] + m[4],
    m[1] * n[4] + m[3] * n[5] + m[5],
  ];
}

export function applyMatrix(m, x, y) {
  return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
}

export function translation(x, y) {
  return [1, 0, 0, 1, x, y];
}

export function rotation(deg) {
  const r = toRad(deg);
  const c = Math.cos(r);
  const s = Math.sin(r);
  return [c, s, -s, c, 0, 0];
}

export function scaling(sx, sy) {
  return [sx, 0, 0, sy, 0, 0];
}

// The sink. `marks` is filled in stream order — first drawn first — which is
// back-to-front, so a hit test reads it in reverse.
export function markSink() {
  const marks = [];
  let matrix = IDENTITY;
  const stack = [];
  let line = -1;
  let path = null;

  // Only what a hit test needs: is there anything to hit? A mark whose fill
  // and stroke are both fully transparent is not on the picture, and clicking
  // where it would have been should find whatever is actually visible under
  // it. Recorded per mark rather than looked up later, because the state at
  // the moment of the mark is the only state that was ever true of it.
  let fillAlpha = 0;
  let strokeAlpha = 1;
  let alphaVal = 1;
  let gradientFill = false;
  let strokeWidth = 1;

  function visible() {
    return (gradientFill || fillAlpha > 0 || strokeAlpha > 0) && alphaVal > 0;
  }

  function push(kind, geometry) {
    marks.push({
      kind,
      line,
      matrix,
      geometry,
      visible: visible(),
      strokeWidth,
      filled: gradientFill || fillAlpha > 0,
    });
  }

  return {
    marks,

    at(index) {
      line = index;
    },

    reset(defaults) {
      marks.length = 0;
      matrix = IDENTITY;
      stack.length = 0;
      path = null;
      fillAlpha = defaults.fill[3];
      strokeAlpha = defaults.stroke[3];
      alphaVal = defaults.alpha;
      strokeWidth = defaults.width;
      gradientFill = false;
    },

    stroke(lcha) {
      strokeAlpha = lcha[3];
    },
    fill(lcha) {
      fillAlpha = lcha[3];
      gradientFill = false;
    },
    gradient() {
      gradientFill = true;
    },
    width(w) {
      strokeWidth = w;
    },
    alpha(a) {
      alphaVal = a;
    },
    cap() {},
    corner() {},
    dash() {},
    shadow() {},
    // A BLURRED MARK'S RECORDED OUTLINE IS ITS GEOMETRIC OUTLINE, UNBLURRED
    // (v3 §6.1). This is a decision, not an oversight: a blur spreads a
    // cloud's edge over tens of pixels of near-transparent falloff, and
    // recording that as the hit region would mean clicking a cloud required
    // finding its faintest pixel while the solid middle of it belonged to
    // whatever was behind. What a mark IS does not change because of how
    // softly it was painted — the same reason `shadow` has never moved an
    // outline either.
    blur() {},
    blend() {},
    clip() {},
    unclip() {},
    size() {},
    align() {},

    line(x1, y1, x2, y2) {
      push("line", { x1, y1, x2, y2 });
    },
    rect(x, y, w, h, turn) {
      push("rect", { x, y, w, h, turn });
    },
    circle(x, y, r) {
      push("circle", { x, y, r });
    },
    ellipse(x, y, rx, ry, turn) {
      push("ellipse", { x, y, rx, ry, turn });
    },
    arc(x, y, r, start, end) {
      push("arc", { x, y, r, start, end });
    },
    triangle(x1, y1, x2, y2, x3, y3) {
      push("triangle", { x1, y1, x2, y2, x3, y3 });
    },

    shape() {
      path = [];
    },
    vertex(x, y, first) {
      if (path) path.push(first ? ["M", x, y] : ["L", x, y]);
    },
    curve(cx1, cy1, cx2, cy2, x, y, first) {
      if (path) path.push(first ? ["M", x, y] : ["C", cx1, cy1, cx2, cy2, x, y]);
    },
    close() {
      if (path) path.push(["Z"]);
    },
    end() {
      if (path && path.length) push("path", { ops: path });
      path = null;
    },

    // `background` and `clear` repaint the whole area, so every mark before
    // them is gone — the hit list is emptied, exactly as the canvas is.
    background() {
      marks.length = 0;
    },
    clear() {
      marks.length = 0;
    },
    label() {
      // Text has no outline this module can test a point against without
      // measuring a font, which is the one thing svg.mjs's own header says a
      // renderer cannot do portably. Recorded as nothing rather than as a
      // guessed box.
    },

    push() {
      stack.push(matrix);
    },
    pop() {
      matrix = stack.pop() ?? IDENTITY;
    },
    translate(x, y) {
      matrix = multiply(matrix, translation(x, y));
    },
    rotate(deg) {
      matrix = multiply(matrix, rotation(deg));
    },
    scale(sx, sy) {
      matrix = multiply(matrix, scaling(sx, sy));
    },

    finish() {},
  };
}
