// js/paint/stream.mjs — the walk over a drawing stream, once, for every
// renderer (planes-drawing-protocol-v1.md §§1-8, normative).
//
// A renderer is a SINK: an object with one method per verb. This module reads
// the stream in order, decides what each line means, and calls the sink. It
// owns everything that is protocol semantics rather than medium:
//
//   * the version declaration and its ordering rules (§1.1) — including that
//     an unimplemented version refuses the WHOLE stream and draws nothing;
//   * the refusal contract (§2) — which lines are errors and what they are
//     called;
//   * the path lifecycle: what `vertex` outside a block means, what a second
//     `shape` means, what a block left open at the end of the stream means;
//   * transform balance: `pop` without `push`, `push` left unmatched;
//   * the reset table (§5), handed to the sink as one value;
//   * the arc wrap (§7), so both renderers are given the SAME end angle
//     rather than each deriving it;
//   * the `drawn` count, the prose list, and the error list.
//
// None of that is canvas-specific or SVG-specific, and a second renderer that
// re-implemented it would agree on every case anyone thought to test and
// diverge on the first one nobody did. The two renderers in this repo differ
// only in what they do with a circle, not in what a circle *is*.

import { parseCommand, GRADIENT_GEOMETRY } from "./protocol.mjs";

const SUPPORTED_VERSIONS = new Set([1, 2, 3]);

// The version each verb first appeared in. A stream declaring less than a
// verb's own version is an error, not a silent draw (planes-drawing-protocol-
// v2.md §10.2, v3 §4.4) — unlike an OPTIONAL argument, which widens an
// EXISTING verb's arity and is accepted regardless of declared version.
// `ellipse`/`rect` rotation and `gradient radial`'s inner radius are both
// that second kind: protocol.mjs's OPTIONAL map has no notion of stream
// version at all, and v3 §1.1 lists the inner radius beside the rotations
// for exactly that reason.
const FIRST_VERSION = Object.freeze({
  gradient: 2, shadow: 2, blend: 2, clip: 2, unclip: 2, alpha: 2, dash: 2,
  blur: 3,
});

// A gradient KIND word can be newer than the `gradient` verb itself: `mid`
// is v3's third stop, on a verb v2 already had. Gated the same way, and named
// separately so the message can say which word rather than which verb.
const KIND_FIRST_VERSION = Object.freeze({ mid: 3 });

// The specification's §5 table, as one value. A sink resets to this at the
// start of every stream; nothing persists between streams except what a
// program restates.
export const DEFAULTS = Object.freeze({
  stroke: Object.freeze([0, 0, 0, 1]),
  fill: Object.freeze([0, 0, 0, 0]),
  width: 1,
  cap: "butt",
  corner: "miter",
  size: 16,
  align: "left",
  // v2 additions (planes-drawing-protocol-v2.md §5).
  blend: "normal",
  alpha: 1,
  dash: Object.freeze([0, 0]),
  // v3 addition (planes-drawing-protocol-v3.md §5): no blur.
  blur: 0,
});

// §5.1, normative: the shared walk computes a gradient's stops, so both
// sinks are handed an IDENTICAL list and cannot disagree about one by
// construction. Sixteen stops, offsets 0, 1/15, ..., 1. L, C and A
// interpolate linearly; H interpolates on the SHORTER arc (350 -> 10 sweeps
// forward 20 degrees through 0, not backward 340).
function hueArcDelta(h1, h2) {
  let d = (h2 - h1) % 360;
  if (d > 180) d -= 360;
  if (d <= -180) d += 360;
  return d;
}

const SAMPLES_PER_SEGMENT = 16;

// One segment between two whole OKLCH colours, sampled across the offset span
// it occupies. `includeFirst` is false for every segment after the first, so
// the shared colour is emitted once rather than as two stops at one offset.
function segmentStops(c1, c2, from, to, includeFirst) {
  const dH = hueArcDelta(c1[2], c2[2]);
  const out = [];
  for (let i = includeFirst ? 0 : 1; i < SAMPLES_PER_SEGMENT; i++) {
    const t = i / (SAMPLES_PER_SEGMENT - 1);
    out.push({
      offset: from + (to - from) * t,
      L: c1[0] + (c2[0] - c1[0]) * t,
      C: c1[1] + (c2[1] - c1[1]) * t,
      H: ((c1[2] + dH * t) % 360 + 360) % 360,
      A: c1[3] + (c2[3] - c1[3]) * t,
    });
  }
  return out;
}

// v3 §6.6: any number of stops at any offsets, each SEGMENT interpolated by
// v2's rule — L, C and A linear, hue on the shorter arc — and computed
// independently of its neighbours. Two colours at [0, 1] is exactly what v2
// did and produces exactly what it produced; three at [0, p, 1] is
// `gradient mid`, which is why the hue of a `mid` sweeps the short way twice
// rather than once across the whole ramp.
export function gradientStopsFrom(colours, offsets) {
  const out = [];
  for (let s = 0; s + 1 < colours.length; s++) {
    out.push(...segmentStops(colours[s], colours[s + 1], offsets[s], offsets[s + 1], s === 0));
  }
  return out;
}

export function gradientStops(L1, C1, H1, A1, L2, C2, H2, A2) {
  return gradientStopsFrom([[L1, C1, H1, A1], [L2, C2, H2, A2]], [0, 1]);
}

// Not in the protocol — the protocol says nothing about typefaces, and it is
// right not to: a pen plotter has none. It is here rather than in either
// renderer because the two must agree, and the only way a saved SVG can match
// what was on the canvas is for both to name the same family. `ui-monospace,
// monospace` is the most predictable stack across machines, which is the best
// available answer to the limit svg.mjs's header states: a font is resolved
// where a file is OPENED, not where it was written.
export const FONT_FAMILY = "ui-monospace, monospace";

// §7, pinned: if `end` is at or below `start`, add 360 until it is above.
// Done here, in degree space, so both renderers receive one already-resolved
// pair and cannot disagree about a wrap.
export function wrapArcEnd(start, end) {
  let e = end;
  while (e <= start) e += 360;
  return e;
}

export function walk(lines, sink) {
  const errors = [];
  const text = [];
  let drawn = 0;
  // The index of the line being walked, and the line itself, handed to the
  // sink BEFORE it is dispatched (§5b of the build this came from). This is
  // the whole of what the walk gained: a sink that wants to know which line
  // drew a mark is told, and every sink that does not care inherits a no-op.
  //
  // NOT A MATRIX. The walk tracks `pushDepth` and nothing else about the
  // transform, and that stays true — a sink that needs the CTM keeps its own
  // (js/paint/marks.mjs does exactly that). Putting one here would make this
  // module know how a renderer composes space, which is the one thing it has
  // never known.
  let index = -1;

  let versionSet = false;
  let declaredVersion = 1; // §1.1: absent is version 1
  let sawDrawingCommand = false;
  let pathOpen = false;
  let pathStarted = false; // has the open path received its first point yet
  let pushDepth = 0;
  let clipDepth = 0;

  sink.reset(DEFAULTS);

  try {
    for (const line of lines) {
      index += 1;
      if (sink.at) sink.at(index, line);
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
            refused: true,
            errors: [
              {
                tag: "unsupported-version",
                message:
                  `this renderer implements protocol versions 1-${Math.max(...SUPPORTED_VERSIONS)}; ` +
                  `the stream declared version ${requested} and is refused whole`,
              },
            ],
          };
        }
        versionSet = true;
        declaredVersion = requested;
        continue;
      }

      const needed =
        cmd.verb === "gradient" && KIND_FIRST_VERSION[cmd.args[0]]
          ? KIND_FIRST_VERSION[cmd.args[0]]
          : FIRST_VERSION[cmd.verb];
      if (needed !== undefined && declaredVersion < needed) {
        const named = cmd.verb === "gradient" && KIND_FIRST_VERSION[cmd.args[0]]
          ? `gradient ${cmd.args[0]}`
          : cmd.verb;
        errors.push({
          tag: "verb-not-in-version",
          message:
            `"${named}" is not part of protocol version ${declaredVersion} in "${line}" ` +
            `— write draw protocol ${needed} to use it`,
        });
        sawDrawingCommand = true;
        continue;
      }

      sawDrawingCommand = true;
      let lineErrored = false;

      switch (cmd.verb) {
        case "stroke":
          sink.stroke(cmd.args);
          break;
        case "fill":
          sink.fill(cmd.args);
          break;
        case "width":
          sink.width(cmd.args[0]);
          break;
        case "cap":
          sink.cap(cmd.args[0]);
          break;
        case "corner":
          sink.corner(cmd.args[0]);
          break;
        case "line":
          sink.line(...cmd.args);
          break;
        case "rect":
          sink.rect(...cmd.args);
          break;
        case "circle":
          sink.circle(...cmd.args);
          break;
        case "ellipse":
          sink.ellipse(...cmd.args);
          break;
        case "arc": {
          const [x, y, r, start, rawEnd] = cmd.args;
          sink.arc(x, y, r, start, wrapArcEnd(start, rawEnd));
          break;
        }
        case "triangle":
          sink.triangle(...cmd.args);
          break;
        case "shape": {
          if (pathOpen) {
            errors.push({ tag: "path-already-open", message: "a shape is already open" });
            lineErrored = true;
            break;
          }
          sink.shape();
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
          sink.vertex(cmd.args[0], cmd.args[1], !pathStarted);
          pathStarted = true;
          break;
        }
        case "curve": {
          if (!pathOpen) {
            errors.push({ tag: "path-not-open", message: "curve outside a shape ... end block" });
            lineErrored = true;
            break;
          }
          sink.curve(...cmd.args, !pathStarted);
          pathStarted = true;
          break;
        }
        case "close": {
          if (!pathOpen) {
            errors.push({ tag: "path-not-open", message: "close outside a shape ... end block" });
            lineErrored = true;
            break;
          }
          sink.close();
          break;
        }
        case "end": {
          if (!pathOpen) {
            errors.push({ tag: "path-not-open", message: "end without a preceding shape" });
            lineErrored = true;
            break;
          }
          sink.end();
          pathOpen = false;
          pathStarted = false;
          break;
        }
        case "push":
          sink.push();
          pushDepth += 1;
          break;
        case "pop": {
          if (pushDepth === 0) {
            errors.push({ tag: "unmatched-pop", message: "pop without a matching push" });
            lineErrored = true;
            break;
          }
          sink.pop();
          pushDepth -= 1;
          break;
        }
        case "translate":
          sink.translate(...cmd.args);
          break;
        case "rotate":
          sink.rotate(cmd.args[0]);
          break;
        case "scale":
          sink.scale(...cmd.args);
          break;
        case "label":
          sink.label(cmd.args[0], cmd.args[1], cmd.text);
          break;
        case "size":
          sink.size(cmd.args[0]);
          break;
        case "align":
          sink.align(cmd.args[0]);
          break;
        case "background":
          sink.background(...cmd.args);
          break;
        case "clear":
          sink.clear();
          break;
        // The whole of `mid` is decided HERE and nothing reaches a sink that
        // has not already been resolved. `mid` IS a linear gradient — the
        // same two points, the same fill — whose stop list happens to carry a
        // third colour at a stated offset, so the stop position `p` is spent
        // building the stops and the sink is handed the kind word `linear`
        // with four geometry numbers, exactly as it has been since v2.
        // Adding a third stop therefore cost the two renderers NOTHING: no
        // branch, no new method, no chance of disagreeing about a sky.
        case "gradient": {
          const [kindWord, ...nums] = cmd.args;
          const geomCount = GRADIENT_GEOMETRY[kindWord];
          const flat = nums.slice(geomCount);
          const colours = [];
          for (let i = 0; i < flat.length; i += 4) colours.push(flat.slice(i, i + 4));
          const isMid = kindWord === "mid";
          const offsets = isMid ? [0, nums[0], 1] : [0, 1];
          const geomArgs = isMid ? nums.slice(1, 5) : nums.slice(0, geomCount);
          sink.gradient(isMid ? "linear" : kindWord, geomArgs, gradientStopsFrom(colours, offsets));
          break;
        }
        case "shadow":
          sink.shadow(...cmd.args);
          break;
        case "blend":
          sink.blend(cmd.args[0]);
          break;
        case "alpha":
          sink.alpha(cmd.args[0]);
          break;
        case "dash":
          sink.dash(...cmd.args);
          break;
        case "blur":
          sink.blur(cmd.args[0]);
          break;
        case "clip":
          sink.clip();
          clipDepth += 1;
          break;
        case "unclip": {
          if (clipDepth === 0) {
            errors.push({ tag: "unmatched-unclip", message: "unclip without a matching clip" });
            lineErrored = true;
            break;
          }
          sink.unclip();
          clipDepth -= 1;
          break;
        }
      }

      if (!lineErrored) drawn += 1;
    }

    if (pathOpen) {
      errors.push({ tag: "path-unclosed", message: "a shape was left open at the end of the stream" });
    }
    if (pushDepth > 0) {
      errors.push({ tag: "unmatched-push", message: "a push was left unmatched at the end of the stream" });
    }
    if (clipDepth > 0) {
      errors.push({ tag: "clip-unclosed", message: "a clip was left open at the end of the stream" });
    }
  } finally {
    sink.finish();
  }

  return { drawn, text, errors, refused: false };
}
