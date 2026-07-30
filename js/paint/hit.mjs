// js/paint/hit.mjs — which mark is under this point.
//
// Reads the list js/paint/marks.mjs recorded and answers, for a point in the
// drawing area's own coordinates, the index of the topmost mark containing it
// — topmost meaning last drawn, so the walk is in reverse.
//
// HOW THE MATRIX IS HONOURED. Each mark carries the transform that was in
// force when it was emitted, and the geometry in the program's coordinates at
// that moment. Rather than transforming the geometry (which would turn an
// ellipse into a general conic and a path into a mess), the POINT is
// transformed the other way: inverted through the mark's own matrix, then
// tested against the untransformed shape. One inversion per mark, exact for
// every affine transform the protocol has.
//
// The tilted-leaf case is the one a naive implementation gets wrong: a
// rotated `ellipse` inside a `push`/`translate`/`scale` pair carries BOTH a
// rotation of its own (§6.2's optional argument, about the mark's own centre)
// and an enclosing CTM, and the two compose in an order that matters.
// js/test/hit.test.mjs pins it with a hand-computed point.
//
// Pure arithmetic. No DOM, no canvas, no Path2D — which is why it can be
// tested headless and why nothing here can break a renderer.

import { applyMatrix } from "./marks.mjs";

const toRad = (deg) => (deg * Math.PI) / 180;

// The inverse of [a, b, c, d, e, f]. Null when the matrix is singular — a
// `scale 0 1` collapses the plane onto a line, and a mark drawn under one has
// no interior to be inside.
export function invert(m) {
  const [a, b, c, d, e, f] = m;
  const det = a * d - b * c;
  if (det === 0) return null;
  return [
    d / det,
    -b / det,
    -c / det,
    a / det,
    (c * f - d * e) / det,
    (b * e - a * f) / det,
  ];
}

// A point rotated by -deg about (cx, cy) — used to test a point against a
// mark's OWN rotation argument (§6.2), which is about the mark's own centre
// and is not part of the transform stack.
function unrotate(px, py, cx, cy, deg) {
  if (!deg) return [px, py];
  const r = toRad(-deg);
  const cos = Math.cos(r);
  const sin = Math.sin(r);
  const dx = px - cx;
  const dy = py - cy;
  return [cx + dx * cos - dy * sin, cy + dx * sin + dy * cos];
}

function pointInPolygon(px, py, points) {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i];
    const [xj, yj] = points[j];
    const straddles = yi > py !== yj > py;
    if (straddles && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function distanceToSegment(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lengthSq = dx * dx + dy * dy;
  if (lengthSq === 0) return Math.hypot(px - x1, py - y1);
  let t = ((px - x1) * dx + (py - y1) * dy) / lengthSq;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

// A path's own points, flattened: a cubic is sampled at eight steps, which is
// finer than a click is accurate at any size this protocol draws.
function pathPoints(ops) {
  const points = [];
  let cx = 0;
  let cy = 0;
  for (const op of ops) {
    if (op[0] === "M" || op[0] === "L") {
      cx = op[1];
      cy = op[2];
      points.push([cx, cy]);
    } else if (op[0] === "C") {
      const [, c1x, c1y, c2x, c2y, x, y] = op;
      for (let i = 1; i <= 8; i++) {
        const t = i / 8;
        const u = 1 - t;
        points.push([
          u * u * u * cx + 3 * u * u * t * c1x + 3 * u * t * t * c2x + t * t * t * x,
          u * u * u * cy + 3 * u * u * t * c1y + 3 * u * t * t * c2y + t * t * t * y,
        ]);
      }
      cx = x;
      cy = y;
    }
  }
  return points;
}

// `slack` widens every test by this many protocol pixels, so a thin stroke
// and a small mark are both clickable. A picture is not a form: a reader
// pointing at a firefly should not have to hit a 1.1-pixel radius.
export function containsPoint(mark, px, py, slack = 3) {
  const g = mark.geometry;
  const reach = slack + (mark.filled ? 0 : mark.strokeWidth / 2);
  switch (mark.kind) {
    case "circle":
      return Math.hypot(px - g.x, py - g.y) <= g.r + reach;
    case "ellipse": {
      const [ux, uy] = unrotate(px, py, g.x, g.y, g.turn);
      const rx = g.rx + reach;
      const ry = g.ry + reach;
      if (rx <= 0 || ry <= 0) return false;
      const nx = (ux - g.x) / rx;
      const ny = (uy - g.y) / ry;
      return nx * nx + ny * ny <= 1;
    }
    case "rect": {
      const [ux, uy] = unrotate(px, py, g.x + g.w / 2, g.y + g.h / 2, g.turn);
      const x0 = Math.min(g.x, g.x + g.w) - reach;
      const x1 = Math.max(g.x, g.x + g.w) + reach;
      const y0 = Math.min(g.y, g.y + g.h) - reach;
      const y1 = Math.max(g.y, g.y + g.h) + reach;
      return ux >= x0 && ux <= x1 && uy >= y0 && uy <= y1;
    }
    case "line":
      return distanceToSegment(px, py, g.x1, g.y1, g.x2, g.y2) <= reach;
    case "triangle": {
      const pts = [
        [g.x1, g.y1],
        [g.x2, g.y2],
        [g.x3, g.y3],
      ];
      if (pointInPolygon(px, py, pts)) return true;
      for (let i = 0; i < 3; i++) {
        const [ax, ay] = pts[i];
        const [bx, by] = pts[(i + 1) % 3];
        if (distanceToSegment(px, py, ax, ay, bx, by) <= reach) return true;
      }
      return false;
    }
    case "arc": {
      const d = Math.hypot(px - g.x, py - g.y);
      if (Math.abs(d - g.r) > reach) return false;
      // The angle, in the protocol's own sense (§7): degrees, zero along
      // positive x, increasing clockwise as pictured.
      let a = (Math.atan2(py - g.y, px - g.x) * 180) / Math.PI;
      while (a < g.start) a += 360;
      return a <= g.end;
    }
    case "path": {
      const pts = pathPoints(g.ops);
      if (pts.length < 2) return false;
      if (mark.filled && pointInPolygon(px, py, pts)) return true;
      for (let i = 1; i < pts.length; i++) {
        if (distanceToSegment(px, py, pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]) <= reach) {
          return true;
        }
      }
      return false;
    }
    default:
      return false;
  }
}

// A mark that covers essentially the whole drawing area is a BACKDROP, not a
// thing you can point at — a vignette, a full-area wash, a sky that fills the
// frame. Pointing at one means pointing at nothing in particular, and
// answering "the vignette" for every click on the picture is the failure this
// exists to prevent: the garden's vignette is the last mark drawn and covers
// every pixel, so without this rule it wins every hit test in the scene.
//
// `area` is the drawing area's own dimensions, which this module cannot know
// and does not guess — omit it and nothing is treated as a backdrop.
function isBackdrop(mark, area) {
  if (!area) return false;
  const pts = outlineOf(mark, { steps: 8 });
  if (!pts.length) return false;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [px, py] of pts) {
    minX = Math.min(minX, px);
    minY = Math.min(minY, py);
    maxX = Math.max(maxX, px);
    maxY = Math.max(maxY, py);
  }
  return (
    minX <= 0.02 * area.width &&
    minY <= 0.02 * area.height &&
    maxX >= 0.98 * area.width &&
    maxY >= 0.98 * area.height
  );
}

// The index of the topmost mark under (x, y), or -1. Marks are recorded
// front-appended in stream order, so "topmost" is "last", and this walks
// backward. Invisible marks (a fill and stroke both fully transparent, or an
// `alpha` of zero) are skipped: clicking where one would have been finds what
// is actually on the picture underneath. So are backdrops, when the caller
// says how big the drawing area is.
export function hitTest(marks, x, y, { slack = 3, area = null } = {}) {
  for (let i = marks.length - 1; i >= 0; i--) {
    const mark = marks[i];
    if (!mark.visible) continue;
    if (isBackdrop(mark, area)) continue;
    const inverse = invert(mark.matrix);
    if (!inverse) continue;
    const [lx, ly] = applyMatrix(inverse, x, y);
    // The transform also scales what "three pixels of slack" means: three
    // pixels on screen is fewer local units under a `scale 2 2`.
    const shrink = Math.sqrt(Math.abs(mark.matrix[0] * mark.matrix[3] - mark.matrix[1] * mark.matrix[2])) || 1;
    if (containsPoint(mark, lx, ly, slack / shrink)) return i;
  }
  return -1;
}

// Every mark a given stream line drew — the same map read backwards, which is
// what "hover a source line, watch its marks light up" needs.
export function marksForLine(marks, line) {
  const found = [];
  for (let i = 0; i < marks.length; i++) if (marks[i].line === line) found.push(i);
  return found;
}

// A mark's outline in DRAWING-AREA coordinates, as a polygon — for drawing a
// highlight around it. The geometry is sampled in the mark's own coordinates
// and then pushed through its matrix, which is the direction that works: the
// inverse is for testing a point, this is for showing an outline.
export function outlineOf(mark, { steps = 24 } = {}) {
  const g = mark.geometry;
  const local = [];
  const ring = (cx, cy, rx, ry, turn) => {
    for (let i = 0; i < steps; i++) {
      const a = (i / steps) * 2 * Math.PI;
      const x = rx * Math.cos(a);
      const y = ry * Math.sin(a);
      const r = toRad(turn || 0);
      local.push([cx + x * Math.cos(r) - y * Math.sin(r), cy + x * Math.sin(r) + y * Math.cos(r)]);
    }
  };
  switch (mark.kind) {
    case "circle":
      ring(g.x, g.y, g.r, g.r, 0);
      break;
    case "ellipse":
      ring(g.x, g.y, g.rx, g.ry, g.turn);
      break;
    case "arc":
      ring(g.x, g.y, g.r, g.r, 0);
      break;
    case "rect": {
      const cx = g.x + g.w / 2;
      const cy = g.y + g.h / 2;
      const r = toRad(g.turn || 0);
      for (const [dx, dy] of [
        [-g.w / 2, -g.h / 2],
        [g.w / 2, -g.h / 2],
        [g.w / 2, g.h / 2],
        [-g.w / 2, g.h / 2],
      ]) {
        local.push([cx + dx * Math.cos(r) - dy * Math.sin(r), cy + dx * Math.sin(r) + dy * Math.cos(r)]);
      }
      break;
    }
    case "line":
      local.push([g.x1, g.y1], [g.x2, g.y2]);
      break;
    case "triangle":
      local.push([g.x1, g.y1], [g.x2, g.y2], [g.x3, g.y3]);
      break;
    case "path":
      local.push(...pathPoints(g.ops));
      break;
    default:
      return [];
  }
  return local.map(([x, y]) => applyMatrix(mark.matrix, x, y));
}
