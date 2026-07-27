// js/paint/protocol.mjs — the draw-command protocol (A.5).
//
// A canvas paint is emission to the person at the machine, so a Planes
// program draws by emitting `show` lines in this fixed verb whitelist. A line
// whose first token is not one of these verbs — or whose argument count is
// wrong — is not an error: parseCommand returns null and the caller (the
// painter, or the page) routes it to the text pane instead. Coordinates are
// canvas pixels, origin top-left; a number may carry a leading `~` (an exact
// rational's rendering elsewhere in the language) which is accepted and
// dropped, never treated as part of the value.

const ARITY = Object.freeze({
  pen: 3,
  width: 1,
  move: 2,
  line: 2,
  circle: 3,
  dot: 3,
  rect: 4,
  box: 4,
  clear: 0,
});

export const VERBS = Object.freeze([...Object.keys(ARITY), "text"]);

function parseNumber(token) {
  const stripped = token.startsWith("~") ? token.slice(1) : token;
  if (stripped === "") return null;
  const n = Number(stripped);
  return Number.isNaN(n) ? null : n;
}

const TEXT_LINE = /^\s*text\s+(\S+)\s+(\S+)\s+(.+?)\s*$/;

export function parseCommand(line) {
  if (line.trim() === "") return null;

  if (/^\s*text\b/.test(line)) {
    const m = TEXT_LINE.exec(line);
    if (!m) return null;
    const x = parseNumber(m[1]);
    const y = parseNumber(m[2]);
    if (x === null || y === null) return null;
    return { verb: "text", args: [x, y], text: m[3] };
  }

  const tokens = line.trim().split(/\s+/);
  const [verb, ...rest] = tokens;
  if (!(verb in ARITY)) return null;

  const arity = ARITY[verb];
  if (rest.length !== arity) return null;

  const args = rest.map(parseNumber);
  if (args.some((a) => a === null)) return null;

  return { verb, args };
}
