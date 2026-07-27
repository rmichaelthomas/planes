// js/paint/svg.mjs — the SVG renderer: a second SINK for js/paint/stream.mjs
// (planes-drawing-protocol-v1.md §§4-8, normative).
//
// `toSvg(lines, dimensions)` returns the same three-part result `paint()`
// does — `{ svg, drawn, text, errors }` in place of the canvas's `{ drawn,
// text, errors }` — because it walks the same stream with the same module.
// Everything that is protocol rather than medium (the version declaration and
// its ordering, the path lifecycle, transform balance, the reset table, the
// arc wrap, every error tag) lives in stream.mjs and is shared verbatim with
// painter.mjs. What is here is what it means to draw a circle *as SVG*.
//
// STATED LIMIT: TEXT.
//
// A `<text>` element is laid out by whatever font resolves where the FILE IS
// OPENED, not where it was written. A saved SVG carried to another machine
// can therefore set its labels in a different face at a different width, and
// `align`'s positioning — which is anchoring, not measurement — will look
// right while the text around it shifts. Both renderers name the same family
// (stream.mjs's FONT_FAMILY) so that a file opened on the machine that made
// it matches the canvas exactly; nothing can make that hold everywhere.
// Converting text to paths would, and is deliberately not done: it would make
// the label uneditable and unsearchable, which is most of why anyone opens an
// SVG in an editor at all.
//
// The other divergence worth naming: SVG has no cumulative surface. A canvas
// is drawn on across ticks and `clear` wipes pixels; here `clear` discards
// the elements emitted so far and starts again from a background rect. The
// visible result is the same and the mechanism is not.

import { walk, FONT_FAMILY } from "./stream.mjs";
import { rgbHex } from "./color.mjs";

const toRad = (deg) => (deg * Math.PI) / 180;

// Six decimals: far below anything a renderer resolves, and enough to keep
// exponent notation out of path data, which is legal but unreadable.
function fmt(v) {
  if (!Number.isFinite(v)) return "0";
  const r = Math.round(v * 1e6) / 1e6;
  return Object.is(r, -0) ? "0" : String(r);
}

function escapeText(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

const ANCHOR = Object.freeze({ left: "start", center: "middle", right: "end" });

function svgSink({ width, height, background }) {
  let elements = [];
  // Every currently-unclosed <g>, innermost last. `clear` rebuilds the
  // element list from these, so discarding a picture never unbalances the
  // nesting a later `pop` is going to close.
  let open = [];

  let strokeC = [0, 0, 0, 1];
  let fillC = [0, 0, 0, 0];
  let lineWidth = 1;
  let capWord = "butt";
  let cornerWord = "miter";
  let sizePx = 16;
  let alignWord = "left";
  let backgroundColor = background;

  // A path under construction, as SVG path-data commands.
  let pathD = [];

  const emit = (el) => elements.push(el);
  const bgRect = () =>
    `<rect x="0" y="0" width="${fmt(width)}" height="${fmt(height)}" fill="${backgroundColor}"/>`;

  // Presentation attributes, restated per element rather than inherited from
  // a group: a `<g>` here carries a transform and nothing else, so an
  // element's paint never depends on how deeply it happens to be nested.
  function shapeAttrs() {
    const [sl, sc, sh, sa] = strokeC;
    const [fl, fc, fh, fa] = fillC;
    return (
      ` fill="${rgbHex(fl, fc, fh)}" fill-opacity="${fmt(fa)}"` +
      ` stroke="${rgbHex(sl, sc, sh)}" stroke-opacity="${fmt(sa)}"` +
      ` stroke-width="${fmt(lineWidth)}" stroke-linecap="${capWord}" stroke-linejoin="${cornerWord}"`
    );
  }

  function openGroup(tag, kind) {
    elements.push(tag);
    open.push({ tag, kind });
  }

  // `background` is a full-area fill of an opaque colour, so on canvas it
  // obliterates everything under it — the same thing `clear` does, with the
  // colour changed first. Here that is one operation: throw the elements
  // away and start from a fresh background rect, at the document root, where
  // no enclosing transform can reach it.
  function wipe() {
    elements = [bgRect(), ...open.map((g) => g.tag)];
  }

  const sink = {
    reset(defaults) {
      strokeC = defaults.stroke;
      fillC = defaults.fill;
      lineWidth = defaults.width;
      capWord = defaults.cap;
      cornerWord = defaults.corner;
      sizePx = defaults.size;
      alignWord = defaults.align;
      backgroundColor = background;
      open = [];
      pathD = [];
      elements = [bgRect()];
    },

    stroke(lcha) {
      strokeC = lcha;
    },
    fill(lcha) {
      fillC = lcha;
    },
    width(w) {
      lineWidth = w;
    },
    cap(word) {
      capWord = word;
    },
    corner(word) {
      cornerWord = word;
    },

    line(x1, y1, x2, y2) {
      emit(`<line x1="${fmt(x1)}" y1="${fmt(y1)}" x2="${fmt(x2)}" y2="${fmt(y2)}"${shapeAttrs()}/>`);
    },
    rect(x, y, w, h) {
      emit(`<rect x="${fmt(x)}" y="${fmt(y)}" width="${fmt(w)}" height="${fmt(h)}"${shapeAttrs()}/>`);
    },
    // r is a radius, and `<circle r>` is a radius, so this is direct — the one
    // place p5's diameter convention would have cost a translation layer.
    circle(x, y, r) {
      emit(`<circle cx="${fmt(x)}" cy="${fmt(y)}" r="${fmt(r)}"${shapeAttrs()}/>`);
    },
    ellipse(x, y, rx, ry) {
      emit(`<ellipse cx="${fmt(x)}" cy="${fmt(y)}" rx="${fmt(rx)}" ry="${fmt(ry)}"${shapeAttrs()}/>`);
    },
    // `end` arrives already wrapped past `start` (stream.mjs, §7), so the
    // swept angle is in (0, 360]. SVG's sweep-flag=1 is the positive angular
    // direction, which with y increasing downward is clockwise — the
    // protocol's own sense — so it is 1 always. large-arc-flag is set from
    // the sweep. A full circle cannot be one A command (its endpoints
    // coincide and SVG draws nothing), so it is two half turns.
    arc(x, y, r, start, end) {
      const at = (deg) => [x + r * Math.cos(toRad(deg)), y + r * Math.sin(toRad(deg))];
      const sweep = end - start;
      const [ax, ay] = at(start);
      const radii = `${fmt(r)} ${fmt(r)} 0`;
      let d;
      if (sweep >= 360) {
        const [hx, hy] = at(start + 180);
        d = `M ${fmt(ax)} ${fmt(ay)} A ${radii} 1 1 ${fmt(hx)} ${fmt(hy)} A ${radii} 1 1 ${fmt(ax)} ${fmt(ay)}`;
      } else {
        const [bx, by] = at(end);
        d = `M ${fmt(ax)} ${fmt(ay)} A ${radii} ${sweep > 180 ? 1 : 0} 1 ${fmt(bx)} ${fmt(by)}`;
      }
      emit(`<path d="${d}"${shapeAttrs()}/>`);
    },
    triangle(x1, y1, x2, y2, x3, y3) {
      const pts = `${fmt(x1)},${fmt(y1)} ${fmt(x2)},${fmt(y2)} ${fmt(x3)},${fmt(y3)}`;
      emit(`<polygon points="${pts}"${shapeAttrs()}/>`);
    },

    shape() {
      pathD = [];
    },
    vertex(x, y, first) {
      pathD.push(`${first ? "M" : "L"} ${fmt(x)} ${fmt(y)}`);
    },
    curve(cx1, cy1, cx2, cy2, x, y, first) {
      if (first) pathD.push(`M ${fmt(x)} ${fmt(y)}`);
      else pathD.push(`C ${fmt(cx1)} ${fmt(cy1)} ${fmt(cx2)} ${fmt(cy2)} ${fmt(x)} ${fmt(y)}`);
    },
    close() {
      pathD.push("Z");
    },
    end() {
      if (pathD.length) emit(`<path d="${pathD.join(" ")}"${shapeAttrs()}/>`);
      pathD = [];
    },

    push() {
      openGroup("<g>", "push");
    },
    // stream.mjs never forwards an unmatched pop, so a matching push marker
    // is always down there. Any transform groups opened since it are closed
    // first — they are what that push was saving the state ahead of.
    pop() {
      while (open.length && open[open.length - 1].kind === "xform") {
        elements.push("</g>");
        open.pop();
      }
      elements.push("</g>");
      open.pop();
    },
    translate(x, y) {
      openGroup(`<g transform="translate(${fmt(x)} ${fmt(y)})">`, "xform");
    },
    // Degrees, and positive is clockwise as pictured — SVG's own rotate()
    // already means exactly that, for the same reason canvas's does.
    rotate(deg) {
      openGroup(`<g transform="rotate(${fmt(deg)})">`, "xform");
    },
    scale(sx, sy) {
      openGroup(`<g transform="scale(${fmt(sx)} ${fmt(sy)})">`, "xform");
    },

    label(x, y, text) {
      const [fl, fc, fh, fa] = fillC;
      emit(
        `<text x="${fmt(x)}" y="${fmt(y)}" font-family="${FONT_FAMILY}" font-size="${fmt(sizePx)}"` +
          ` text-anchor="${ANCHOR[alignWord]}" fill="${rgbHex(fl, fc, fh)}" fill-opacity="${fmt(fa)}"` +
          ` stroke="none">${escapeText(text)}</text>`,
      );
    },
    size(n) {
      sizePx = n;
    },
    align(word) {
      alignWord = word;
    },

    background(L, C, H) {
      backgroundColor = rgbHex(L, C, H);
      wipe();
    },
    clear() {
      wipe();
    },

    finish() {
      while (open.length) {
        elements.push("</g>");
        open.pop();
      }
    },

    document() {
      const body = elements.length ? `\n${elements.join("\n")}\n` : "";
      return (
        `<svg xmlns="http://www.w3.org/2000/svg" width="${fmt(width)}" height="${fmt(height)}"` +
        ` viewBox="0 0 ${fmt(width)} ${fmt(height)}">${body}</svg>\n`
      );
    },
  };

  return sink;
}

export function toSvg(lines, { width, height, background = "#ffffff" } = {}) {
  const sink = svgSink({ width, height, background });
  const { drawn, text, errors, refused } = walk(lines, sink);
  // A refused stream draws nothing, in either renderer, and an SVG document
  // that drew nothing is not an empty picture — it is no picture at all
  // (specification §1.1).
  return { svg: refused ? "" : sink.document(), drawn, text, errors };
}
