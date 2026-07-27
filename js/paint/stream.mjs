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

import { parseCommand } from "./protocol.mjs";

const SUPPORTED_VERSIONS = new Set([1]);

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
});

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

  let versionSet = false;
  let sawDrawingCommand = false;
  let pathOpen = false;
  let pathStarted = false; // has the open path received its first point yet
  let pushDepth = 0;

  sink.reset(DEFAULTS);

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
            refused: true,
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
      }

      if (!lineErrored) drawn += 1;
    }

    if (pathOpen) {
      errors.push({ tag: "path-unclosed", message: "a shape was left open at the end of the stream" });
    }
    if (pushDepth > 0) {
      errors.push({ tag: "unmatched-push", message: "a push was left unmatched at the end of the stream" });
    }
  } finally {
    sink.finish();
  }

  return { drawn, text, errors, refused: false };
}
