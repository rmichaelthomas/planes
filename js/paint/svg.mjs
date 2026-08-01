// js/paint/svg.mjs — the SVG renderer: a second SINK for js/paint/stream.mjs
// (planes-drawing-protocol-v1.md §§4-8, planes-drawing-protocol-v2.md,
// normative).
//
// `toSvg(lines, dimensions)` returns the same three-part result `paint()`
// does — `{ svg, drawn, text, errors }` in place of the canvas's `{ drawn,
// text, errors }` — because it walks the same stream with the same module.
// Everything that is protocol rather than medium (the version declaration and
// its ordering, the path lifecycle, transform balance, the reset table, the
// arc wrap, every error tag, a gradient's sixteen stops) lives in stream.mjs
// and is shared verbatim with painter.mjs. What is here is what it means to
// draw a circle *as SVG*.
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
//
// STATED LIMIT (v2): NO GRADIENT STROKE. §5.2 — a gradient sets the current
// FILL only; there is no gradient stroke in this version.
//
// STATED LIMIT (v2): BLEND'S MODE SET STAYS CLOSED AT TWO. `normal` and
// `add` (`mix-blend-mode: plus-lighter`, the exact match for canvas's
// `lighter`) are the only two — every other CSS blend mode differs between
// canvas and SVG in ways that would make the two renderers disagree about
// what a picture means (§7).

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
  // nesting a later `pop`/`unclip` is going to close. Each entry's `kind` is
  // "push" (a transform-save marker), "xform" (translate/rotate/scale) or
  // "clip" (v2) — pop closes everything down to and including its own
  // "push" marker, whichever kinds sit above it; unclip closes down to and
  // including its own "clip" marker.
  let open = [];

  let strokeC = [0, 0, 0, 1];
  let fillPaint = { kind: "solid", lcha: [0, 0, 0, 0] }; // | { kind: "gradient", id }
  let lineWidth = 1;
  let capWord = "butt";
  let cornerWord = "miter";
  let sizePx = 16;
  let alignWord = "left";
  let backgroundColor = background;
  // A path under construction, as SVG path-data commands.
  let pathD = [];

  // v2 state.
  let dashOn = 0;
  let dashOff = 0;
  let alphaVal = 1;
  let blendWord = "normal";
  let shadowState = null; // | { dx, dy, blur, L, C, H }
  let pendingClip = false;

  // v3 state.
  let blurRadius = 0;

  // ---- <defs> (v2 §4) ------------------------------------------------------
  //
  // A resource collection, content-keyed: two identical gradients (or
  // shadows, or clip regions) emit one <defs> entry and every reference
  // just points at it. `defs` survives `wipe()` — a def is a resource, not a
  // mark, and discarding the picture on `background`/`clear` must not
  // discard the resources a still-open group might reference again.
  let defs = [];
  let defIndexByKey = new Map();
  let defCounters = Object.create(null);

  function defRef(kind, key, buildBody) {
    const cacheKey = `${kind}:${key}`;
    const existing = defIndexByKey.get(cacheKey);
    if (existing) return existing;
    defCounters[kind] = (defCounters[kind] || 0) + 1;
    const id = `p-${kind}-${defCounters[kind]}`;
    defs.push({ id, body: buildBody(id) });
    defIndexByKey.set(cacheKey, id);
    return id;
  }

  function gradientDefBody(id, kindWord, geomArgs, stops) {
    const stopsMarkup = stops
      .map((s) => `<stop offset="${fmt(s.offset)}" stop-color="${rgbHex(s.L, s.C, s.H)}" stop-opacity="${fmt(s.A)}"/>`)
      .join("");
    if (kindWord === "linear") {
      const [x1, y1, x2, y2] = geomArgs;
      return (
        `<linearGradient id="${id}" gradientUnits="userSpaceOnUse" x1="${fmt(x1)}" y1="${fmt(y1)}"` +
        ` x2="${fmt(x2)}" y2="${fmt(y2)}">${stopsMarkup}</linearGradient>`
      );
    }
    // `fr` is SVG's own name for the inner radius canvas's two-circle
    // createRadialGradient takes as its third argument (v3 §4.3) — the same
    // ramp start, expressed natively on both sides. Omitted when 0, which is
    // its default anyway, so a stream that never states one produces exactly
    // the markup v2 produced.
    const [x, y, r, rInner] = geomArgs;
    const fr = rInner ? ` fr="${fmt(rInner)}"` : "";
    return (
      `<radialGradient id="${id}" gradientUnits="userSpaceOnUse" cx="${fmt(x)}" cy="${fmt(y)}"` +
      ` r="${fmt(r)}"${fr}>${stopsMarkup}</radialGradient>`
    );
  }

  // The blur/shadow filter reference — ONE filter chain, never two, and
  // recomputed (deduplicated by defRef's own cache) each time it is needed,
  // since the shadow's flood-opacity carries the CURRENT `alpha` state (§6:
  // "alpha comes from the current alpha state, not a seventh argument") and
  // must track a later `alpha` change the same way canvas's persistent
  // ctx.shadowColor does.
  //
  // COMPOSITION ORDER (v3 §6.1, first pinned semantic): the mark is BLURRED,
  // then the shadow is cast FROM THE BLURRED MARK. Canvas's drawing model
  // gives that order natively — `ctx.filter` is applied to the source before
  // the shadow is derived from it — and an SVG filter chain could produce
  // either answer, so this one is built to match: feGaussianBlur on
  // SourceGraphic, feDropShadow over its result.
  //
  // stdDeviation is set to the SAME numeric value as the protocol's radius
  // rather than a Gaussian-equivalent conversion (a common approximation is
  // radius/2) — v2 §6.3's acceptance criterion is that the two renderers'
  // parameters match at scale 1, which this makes true by construction rather
  // than by coincidence between two different blur models. `blur` uses the
  // identical rule, so the two soften by the same number.
  //
  // FILTER REGION (v3 §6.1, second pinned semantic): stated explicitly, and
  // widened past the -50%/200% a drop shadow alone needed. A blur spreads a
  // mark roughly three standard deviations in every direction, and a region
  // that cropped it would make the SVG disagree with the canvas at exactly
  // the soft edge blur exists to draw. The region is also what makes "blur
  // first, clip second" expressible: the filter runs in this box, and only
  // the already-blurred result meets an enclosing <g clip-path>.
  function effectDefId() {
    const shadowKey = shadowState
      ? `${shadowState.dx},${shadowState.dy},${shadowState.blur},${shadowState.L},${shadowState.C},${shadowState.H},${alphaVal}`
      : "none";
    const key = `${blurRadius}|${shadowKey}`;
    return defRef("effect", key, (id) => {
      const parts = [];
      let source = "SourceGraphic";
      if (blurRadius > 0) {
        parts.push(`<feGaussianBlur in="SourceGraphic" stdDeviation="${fmt(blurRadius)}" result="blurred"/>`);
        source = "blurred";
      }
      if (shadowState) {
        const { dx, dy, blur, L, C, H } = shadowState;
        // `in` is stated only when it is NOT the default: a shadow with no
        // blur ahead of it emits exactly the element v2 emitted.
        const inAttr = source === "SourceGraphic" ? "" : ` in="${source}"`;
        parts.push(
          `<feDropShadow${inAttr} dx="${fmt(dx)}" dy="${fmt(dy)}" stdDeviation="${fmt(blur)}"` +
            ` flood-color="${rgbHex(L, C, H)}" flood-opacity="${fmt(alphaVal)}"/>`,
        );
      }
      // USER UNITS, NOT A PERCENTAGE OF THE BOUNDING BOX — and that change
      // is what makes blur expressible at all. The default region, and v2's
      // -50%/200% shadow box, are proportions of the FILTERED ELEMENT's own
      // size, so a firefly two pixels across blurred by seven would have its
      // glow cropped at three pixels while a cloud a hundred across kept all
      // of its. One def is shared by every mark that sets the same effect,
      // so there is no per-mark bounding box to size against here anyway.
      //
      // The box is the canvas grown by one canvas in each direction: past any
      // blur this protocol's numbers reach, and past any translate a program
      // is likely to have in force (a `userSpaceOnUse` region is stated in
      // the LOCAL user space, which an enclosing <g transform> moves). What
      // falls outside the viewport is clipped by the viewport — which is
      // exactly where canvas's own bitmap crops it too, so the two sinks
      // agree at the edge as well as in the middle.
      return (
        `<filter id="${id}" filterUnits="userSpaceOnUse"` +
        ` x="${fmt(-width)}" y="${fmt(-height)}" width="${fmt(width * 3)}" height="${fmt(height * 3)}">` +
        `${parts.join("")}</filter>`
      );
    });
  }

  // The index of the stream line currently being walked, set by `at` below.
  // Every element carries it as `data-line`, so a saved SVG is not only a
  // picture but a map back into the program that drew it — open it in an
  // editor, click a shape, read which line emitted it.
  let currentLine = -1;

  const emit = (el) => elements.push(withLine(el));

  // Appended as the LAST attribute of the opening tag, never inserted after
  // the tag name: every geometry attribute keeps the position it has always
  // had, so a reader (and a test) reading `<circle cx=... cy=... r=...` still
  // reads exactly that.
  function withLine(el) {
    if (currentLine < 0 || el.startsWith("</")) return el;
    const close = el.indexOf(">");
    if (close === -1) return el;
    const at = el[close - 1] === "/" ? close - 1 : close;
    return `${el.slice(0, at)} data-line="${currentLine}"${el.slice(at)}`;
  }
  const bgRect = () =>
    `<rect x="0" y="0" width="${fmt(width)}" height="${fmt(height)}" fill="${backgroundColor}"/>`;

  // Presentation attributes, restated per element rather than inherited from
  // a group: a `<g>` here carries a transform (or a clip-path) and nothing
  // else, so an element's paint never depends on how deeply it happens to be
  // nested (v2's `alpha`, `dash`, `shadow` and `blend` all follow the same
  // rule — per-element, never per-group).
  function shapeAttrs() {
    const [sl, sc, sh, sa] = strokeC;
    const fillValue = fillPaint.kind === "gradient" ? `url(#${fillPaint.id})` : rgbHex(...fillPaint.lcha.slice(0, 3));
    const fillOpacity = (fillPaint.kind === "gradient" ? 1 : fillPaint.lcha[3]) * alphaVal;
    const strokeOpacity = sa * alphaVal;
    let extra = "";
    if (dashOn !== 0 || dashOff !== 0) extra += ` stroke-dasharray="${fmt(dashOn)} ${fmt(dashOff)}"`;
    // One filter attribute, whether the effect is a blur, a shadow or both
    // — v3 §6.1: "Both are one filter chain, not two."
    if (shadowState || blurRadius > 0) extra += ` filter="url(#${effectDefId()})"`;
    if (blendWord === "add") extra += ` style="mix-blend-mode:plus-lighter"`;
    return (
      ` fill="${fillValue}" fill-opacity="${fmt(fillOpacity)}"` +
      ` stroke="${rgbHex(sl, sc, sh)}" stroke-opacity="${fmt(strokeOpacity)}"` +
      ` stroke-width="${fmt(lineWidth)}" stroke-linecap="${capWord}" stroke-linejoin="${cornerWord}"` +
      extra
    );
  }

  function openGroup(tag, kind) {
    elements.push(tag);
    open.push({ tag, kind });
  }

  // §8.3: `clip` opens a masking region; the NEXT completed shape or path
  // defines it, by becoming a <clipPath> child (geometry only — a
  // <clipPath>'s children are never themselves rendered) AND, unchanged, the
  // visible element this call still emits — nested inside the new
  // <g clip-path> group it opens, so the defining shape ends up clipped to
  // itself (a no-op, matching canvas's ctx.clip() called on the same shape's
  // own path right before it is filled/stroked).
  function applyPendingClip(tagName, geomAttrs) {
    if (!pendingClip) return;
    pendingClip = false;
    const id = defRef("clip", `${tagName} ${geomAttrs}`, (defId) => `<clipPath id="${defId}"><${tagName} ${geomAttrs}/></clipPath>`);
    openGroup(`<g clip-path="url(#${id})">`, "clip");
  }

  // `background` is a full-area fill of an opaque colour, so on canvas it
  // obliterates everything under it — the same thing `clear` does, with the
  // colour changed first. Here that is one operation: throw the elements
  // away and start from a fresh background rect, at the document root, where
  // no enclosing transform can reach it. `defs` is a resource collection,
  // not a mark, and is untouched (v2 §4.1).
  function wipe() {
    elements = [bgRect(), ...open.map((g) => g.tag)];
  }

  const sink = {
    at(index) {
      currentLine = index;
    },
    reset(defaults) {
      strokeC = defaults.stroke;
      fillPaint = { kind: "solid", lcha: defaults.fill };
      lineWidth = defaults.width;
      capWord = defaults.cap;
      cornerWord = defaults.corner;
      sizePx = defaults.size;
      alignWord = defaults.align;
      backgroundColor = background;
      [dashOn, dashOff] = defaults.dash;
      alphaVal = defaults.alpha;
      blendWord = defaults.blend;
      shadowState = null;
      blurRadius = defaults.blur;
      pendingClip = false;
      open = [];
      pathD = [];
      elements = [bgRect()];
      defs = [];
      defIndexByKey = new Map();
      defCounters = Object.create(null);
    },

    stroke(lcha) {
      strokeC = lcha;
    },
    fill(lcha) {
      fillPaint = { kind: "solid", lcha };
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

    // §5.2: a gradient replaces the current fill; a later plain `fill`
    // replaces the gradient right back — both just reassign `fillPaint`.
    gradient(kindWord, geomArgs, stops) {
      const id = defRef("gradient", JSON.stringify([kindWord, geomArgs, stops]), (defId) =>
        gradientDefBody(defId, kindWord, geomArgs, stops),
      );
      fillPaint = { kind: "gradient", id };
    },
    shadow(dx, dy, blur, L, C, H) {
      shadowState = { dx, dy, blur, L, C, H };
    },
    blend(word) {
      blendWord = word;
    },
    alpha(a) {
      alphaVal = a;
    },
    dash(on, off) {
      dashOn = on;
      dashOff = off;
    },
    blur(r) {
      blurRadius = r;
    },
    clip() {
      pendingClip = true;
    },
    unclip() {
      if (pendingClip) {
        // No shape ever consumed the clip — nothing was ever opened.
        pendingClip = false;
        return;
      }
      while (open.length && open[open.length - 1].kind === "xform") {
        elements.push("</g>");
        open.pop();
      }
      if (open.length && open[open.length - 1].kind === "clip") {
        elements.push("</g>");
        open.pop();
      }
    },

    line(x1, y1, x2, y2) {
      const geom = `x1="${fmt(x1)}" y1="${fmt(y1)}" x2="${fmt(x2)}" y2="${fmt(y2)}"`;
      applyPendingClip("line", geom);
      emit(`<line ${geom}${shapeAttrs()}/>`);
    },
    rect(x, y, w, h, turn) {
      const rotateAttr = turn !== 0 ? ` transform="rotate(${fmt(turn)} ${fmt(x + w / 2)} ${fmt(y + h / 2)})"` : "";
      const geom = `x="${fmt(x)}" y="${fmt(y)}" width="${fmt(w)}" height="${fmt(h)}"${rotateAttr}`;
      applyPendingClip("rect", geom);
      emit(`<rect ${geom}${shapeAttrs()}/>`);
    },
    // r is a radius, and `<circle r>` is a radius, so this is direct — the one
    // place p5's diameter convention would have cost a translation layer.
    circle(x, y, r) {
      const geom = `cx="${fmt(x)}" cy="${fmt(y)}" r="${fmt(r)}"`;
      applyPendingClip("circle", geom);
      emit(`<circle ${geom}${shapeAttrs()}/>`);
    },
    // The optional rotation argument (v2 §9.2), about the mark's own centre
    // (x, y) — the one point an ellipse always carries.
    ellipse(x, y, rx, ry, turn) {
      const rotateAttr = turn !== 0 ? ` transform="rotate(${fmt(turn)} ${fmt(x)} ${fmt(y)})"` : "";
      const geom = `cx="${fmt(x)}" cy="${fmt(y)}" rx="${fmt(rx)}" ry="${fmt(ry)}"${rotateAttr}`;
      applyPendingClip("ellipse", geom);
      emit(`<ellipse ${geom}${shapeAttrs()}/>`);
    },
    // `end` arrives already wrapped past `start` (stream.mjs, §7). SVG's
    // sweep-flag=1 is the positive angular direction, which with y increasing
    // downward is clockwise — the protocol's own sense — so it is 1 always.
    // large-arc-flag is set from the sweep. A full circle cannot be one A
    // command (its endpoints coincide and SVG draws nothing), so it is two
    // half turns.
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
      const geom = `d="${d}"`;
      applyPendingClip("path", geom);
      emit(`<path ${geom}${shapeAttrs()}/>`);
    },
    triangle(x1, y1, x2, y2, x3, y3) {
      const pts = `${fmt(x1)},${fmt(y1)} ${fmt(x2)},${fmt(y2)} ${fmt(x3)},${fmt(y3)}`;
      const geom = `points="${pts}"`;
      applyPendingClip("polygon", geom);
      emit(`<polygon ${geom}${shapeAttrs()}/>`);
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
      if (pathD.length) {
        const geom = `d="${pathD.join(" ")}"`;
        applyPendingClip("path", geom);
        emit(`<path ${geom}${shapeAttrs()}/>`);
      } else if (pendingClip) {
        // An empty path defining a clip: nothing to clip to and nothing
        // painted — consume the flag so a later shape is not mistaken for
        // the region this `clip` was meant to define.
        pendingClip = false;
      }
      pathD = [];
    },

    push() {
      openGroup("<g>", "push");
    },
    // stream.mjs never forwards an unmatched pop, so a matching push marker
    // is always down there. Any xform or clip groups opened since it are
    // closed first — they are what that push was saving the state ahead of.
    pop() {
      while (open.length && open[open.length - 1].kind !== "push") {
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
      const fillValue = fillPaint.kind === "gradient" ? `url(#${fillPaint.id})` : rgbHex(...fillPaint.lcha.slice(0, 3));
      const fillOpacity = (fillPaint.kind === "gradient" ? 1 : fillPaint.lcha[3]) * alphaVal;
      let extra = "";
      if (shadowState || blurRadius > 0) extra += ` filter="url(#${effectDefId()})"`;
      if (blendWord === "add") extra += ` style="mix-blend-mode:plus-lighter"`;
      emit(
        `<text x="${fmt(x)}" y="${fmt(y)}" font-family="${FONT_FAMILY}" font-size="${fmt(sizePx)}"` +
          ` text-anchor="${ANCHOR[alignWord]}" fill="${fillValue}" fill-opacity="${fmt(fillOpacity)}"` +
          ` stroke="none"${extra}>${escapeText(text)}</text>`,
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
      const defsBlock = defs.length ? `<defs>\n${defs.map((d) => d.body).join("\n")}\n</defs>\n` : "";
      const body = elements.length ? `\n${elements.join("\n")}\n` : "";
      return (
        `<svg xmlns="http://www.w3.org/2000/svg" width="${fmt(width)}" height="${fmt(height)}"` +
        ` viewBox="0 0 ${fmt(width)} ${fmt(height)}">${defsBlock}${body}</svg>\n`
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
