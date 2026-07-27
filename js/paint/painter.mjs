// js/paint/painter.mjs — applies A.5 draw commands to a 2D canvas context.
//
// A pure function of (ctx, lines, dimensions): it reads no globals and no DOM
// beyond the context handed to it. Pen colour, stroke width and cursor
// position are local to one call and reset every time — nothing persists
// between calls except what a program re-states in its own output (that is
// what the `clear` verb, and the fact the canvas itself is drawn on
// cumulatively across ticks, are for).

import { parseCommand } from "./protocol.mjs";

function rgb([r, g, b]) {
  const to255 = (n) => Math.round(Math.max(0, Math.min(1, n)) * 255);
  return `rgb(${to255(r)}, ${to255(g)}, ${to255(b)})`;
}

export function paint(ctx, lines, { width, height, background = "#fff" } = {}) {
  let cursor = { x: 0, y: 0 };
  let drawn = 0;
  const text = [];

  // Reset to defaults on every call — ctx is a real, persistent canvas
  // context shared across ticks, and without this a call's pen/width would
  // silently inherit whatever an earlier, unrelated call last set.
  ctx.strokeStyle = "rgb(0, 0, 0)";
  ctx.fillStyle = "rgb(0, 0, 0)";
  ctx.lineWidth = 1;

  for (const line of lines) {
    const cmd = parseCommand(line);
    if (cmd === null) {
      text.push(line);
      continue;
    }
    drawn++;

    switch (cmd.verb) {
      case "pen": {
        const colour = rgb(cmd.args);
        ctx.strokeStyle = colour;
        ctx.fillStyle = colour;
        break;
      }
      case "width":
        ctx.lineWidth = cmd.args[0];
        break;
      case "move": {
        const [x, y] = cmd.args;
        cursor = { x, y };
        break;
      }
      case "line": {
        const [x, y] = cmd.args;
        ctx.beginPath();
        ctx.moveTo(cursor.x, cursor.y);
        ctx.lineTo(x, y);
        ctx.stroke();
        cursor = { x, y };
        break;
      }
      case "circle": {
        const [x, y, r] = cmd.args;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, 2 * Math.PI);
        ctx.stroke();
        break;
      }
      case "dot": {
        const [x, y, r] = cmd.args;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, 2 * Math.PI);
        ctx.fill();
        break;
      }
      case "rect": {
        const [x, y, w, h] = cmd.args;
        ctx.strokeRect(x, y, w, h);
        break;
      }
      case "box": {
        const [x, y, w, h] = cmd.args;
        ctx.fillRect(x, y, w, h);
        break;
      }
      case "text": {
        const [x, y] = cmd.args;
        ctx.fillText(cmd.text, x, y);
        break;
      }
      case "clear":
        ctx.fillStyle = background;
        ctx.fillRect(0, 0, width, height);
        break;
    }
  }

  return { drawn, text };
}
