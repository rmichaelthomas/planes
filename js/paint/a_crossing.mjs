// Derived presentation data for A Crossing. Planes owns all outcome decisions;
// this module only indexes what a completed Planes run actually emitted.

import { stepGraph } from "./loop.mjs";

export function splitCrossingLines(lines) {
  return {
    drawing: lines.filter((line) => line.startsWith("draw ")),
    sound: lines.filter((line) => line.startsWith("sound ")),
    status: lines.filter((line) => line.startsWith("crossing ")),
  };
}

export function crossingStatus(lines) {
  const line = splitCrossingLines(lines).status.at(-1) || "";
  return line.split(" ")[1] || null;
}

export function parseAtlas(lines) {
  return lines.flatMap((line, outputIndex) => {
    const match = /^atlas ([a-z0-9-]+) (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?) ([a-z0-9-]+)$/.exec(line);
    return match
      ? [{ id: match[1], x: Number(match[2]), y: Number(match[3]), kind: match[4], outputIndex }]
      : [];
  });
}

export function subjectsFromResult({ lines, trace = [] }) {
  const declarations = lines.flatMap((line, outputIndex) => {
    const match = /^scene subject ([a-z0-9-]+) /.exec(line);
    return match ? [{ id: match[1], outputIndex }] : [];
  });

  return declarations.flatMap((subject) => {
    const entry = trace[subject.outputIndex];
    if (!entry) return [];
    return [{
      id: subject.id,
      declarationIndex: subject.outputIndex,
      outputIndex: subject.outputIndex,
      markIndices: [],
      sourceLine: entry[1],
      node: entry[0],
      firstMark: null,
    }];
  });
}

export async function replayCrossing({ source, loader, base, seed, events = [], tick = 0 }) {
  let state = null;
  let result = null;
  const run = async (event) => {
    result = await stepGraph(source, {
      tick,
      seed,
      state,
      event,
      keys: [],
      pointer: { x: 0, y: 0, down: false },
    }, { loader, base });
    if (result.error) return result;
    state = result.state;
    return result;
  };
  await run(null);
  for (const event of events) {
    if (result.error) break;
    await run(event);
  }
  return { ...result, events: events.map((event) => ({ ...event })) };
}
