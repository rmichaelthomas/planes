// js/paint/program_session.mjs — one running instance of a tick-driven
// Planes program: owns exactly one module loader for its life (checkpoint
// v21.0 §249.4's "one loader per run"), fetches its own source with a
// per-visit cache-busting token, and runs it at an arbitrary (tick, seed)
// pair — never averaging or interpolating toward it, always a fresh
// stepGraph call from scratch (js/paint/loop.mjs).
//
// This is the "program-load, run-at-tick" piece paint.html always had
// inline. Pulled out here so garden.html and its sibling pages (tutor.html,
// which adds a why panel on top of the same picture) share one
// implementation of the discipline rather than one page rewriting the
// other's inline script to extend it.

import { stepGraph } from "./loop.mjs";
import { BrowserModuleLoader } from "../module_loader_browser.mjs";

// `file`: the .planes program to load, resolved against `location.href`.
// `cacheBust`: one token for the life of the page (paint.html's own
// `LOAD_TOKEN` pattern) — appended to the program fetch so an edited source
// is never served stale; the loader is given the same token for its own
// module fetches.
export function createProgramSession({ file, cacheBust }) {
  let source = null;
  let loader = null;
  // Bumped by load(); an in-flight runAt() from a superseded load() can
  // tell it has been superseded and return null instead of a stale result.
  let generation = 0;

  async function load() {
    generation += 1;
    const myGeneration = generation;
    const base = new URL(file, window.location.href).href;
    const res = await fetch(`${file}?v=${cacheBust}`);
    if (!res.ok) throw new Error(`could not fetch ${file}: ${res.status}`);
    const text = await res.text();
    if (myGeneration !== generation) return null; // superseded mid-fetch
    source = text;
    loader = new BrowserModuleLoader({ base, cacheBust });
    return source;
  }

  // Runs the loaded program at `tick`/`seed`, with `state` always `nothing`
  // (this session never threads state across calls — a program that reads
  // `state` at all is not the kind of program this session is for). Returns
  // null, not a stale result, if a later load() superseded this call.
  async function runAt(tick, seed = 0, { keys = [], pointer = { x: 0, y: 0, down: false } } = {}) {
    if (!loader) await load();
    const myGeneration = generation;
    const context = { tick, keys, pointer, state: null, seed };
    const result = await stepGraph(source, context, { loader });
    if (myGeneration !== generation) return null;
    return result;
  }

  return {
    load,
    runAt,
    getSource: () => source,
    getLoader: () => loader,
    loadedModules: () => (loader ? loader.loadedModules() : []),
  };
}
