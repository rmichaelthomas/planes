// js/host_browser.mjs — the browser backend (an in-memory virtual filesystem).
//
// Per A.4, one Host interface, two implementations: NodeHost over the real
// filesystem, and this over an in-memory VFS that a browser has instead of a
// disk. Both satisfy the same seven-method interface and the same tests
// (test_js_host.py runs the interface tests against both). BrowserHost is a
// MemoryHost — the in-memory VFS is exactly MemoryHost's `files` — plus an
// optional onShow callback so a page can render show output as it happens.

import { MemoryHost } from "./host.mjs";

export class BrowserHost extends MemoryHost {
  constructor({ responses = {}, files = {}, now = null, onShow = null } = {}) {
    super({ responses, files, now });
    this.onShow = onShow;
  }
  get name() {
    return "browser";
  }
  show(text) {
    this.shown.push(text);
    if (this.onShow) this.onShow(text);
  }
}
