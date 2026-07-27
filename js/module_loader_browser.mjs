// js/module_loader_browser.mjs — the browser module loader (over fetch).
//
// Supplies modules.mjs's four host-bound operations — locate, read, key,
// label — over fetch, per checkpoint v21.0 §249's four rulings: a module
// path resolves relative to the importing source's own location (or this
// loader's `base` when there is none — the textarea's own case); existence is
// never tested ahead of time (a browser cannot, without fetching), so a
// failed resolution is a failed fetch, and the error text matches Node's
// missing-module message verbatim (js/modules.mjs's shared
// missingModuleError); and reads are cached for the length of one loader
// instance, so a program that stays open across many ticks issues exactly one
// fetch per module — construct a fresh loader per Run/Play, not per frame.

import { missingModuleError } from "./modules.mjs";

export class BrowserModuleLoader {
  constructor({ base }) {
    this.base = base;
    this._cache = new Map(); // key -> source text
    this._pending = new Map(); // key -> in-flight fetch, so concurrent reads of
    // the same not-yet-cached module (two `use` sites this frame) share one
    // fetch instead of racing two.
    this._loaded = []; // {name, location} in first-fetched order, for display.
    // modules.mjs's hoistAndRun opts into parse caching when this is present
    // — a ticking program re-runs the same graph every frame, and a library
    // file's text (and therefore its parse) never changes within one run.
    this.astCache = new Map();
  }

  locate(name, fromLocation) {
    const from = fromLocation ?? this.base;
    return new URL(`${name}.planes`, from).href;
  }

  async read(location) {
    const k = this.key(location);
    if (this._cache.has(k)) return this._cache.get(k);
    if (this._pending.has(k)) return this._pending.get(k);
    const p = this._fetchAndCache(location, k);
    this._pending.set(k, p);
    try {
      return await p;
    } finally {
      this._pending.delete(k);
    }
  }

  async _fetchAndCache(location, k) {
    let res;
    try {
      res = await fetch(location);
    } catch {
      throw missingModuleError(this._nameFromLocation(location));
    }
    if (!res.ok) throw missingModuleError(this._nameFromLocation(location));
    const text = await res.text();
    this._cache.set(k, text);
    this._loaded.push({ name: this._nameFromLocation(location), location: k });
    return text;
  }

  key(location) {
    return new URL(location, this.base).href;
  }

  label(location) {
    const url = new URL(location, this.base);
    const segs = url.pathname.split("/");
    return segs[segs.length - 1];
  }

  _nameFromLocation(location) {
    return this.label(location).replace(/\.planes$/, "");
  }

  // A cache-only read: the text if this location has already been fetched
  // this run, `undefined` otherwise. Never fetches — for a synchronous
  // caller that only wants to know what is already in hand.
  readIfCached(location) {
    return this._cache.get(this.key(location));
  }

  // The modules fetched so far this run, in first-fetched order — what
  // paint.html shows beside the base directory.
  loadedModules() {
    return this._loaded.map((m) => ({ ...m }));
  }
}
