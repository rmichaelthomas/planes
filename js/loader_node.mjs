// js/loader_node.mjs — the Node-only grammar loader.
//
// Reads grammar/vocabulary.json (and later rules.json / errors.json) from disk
// and injects them into grammar_data.mjs. This and js/module_loader_node.mjs
// are the only places in the JS implementation that touch node:fs, so every
// other module loads unchanged in a browser (Phase 6 sets the same grammar
// data from an inlined copy instead; module_loader_browser.mjs supplies the
// module-loading half over fetch).

import fs from "node:fs";
import { setVocabulary, setAmberTemplates } from "./grammar_data.mjs";

function readJson(relPath) {
  const url = new URL(relPath, import.meta.url);
  return JSON.parse(fs.readFileSync(url, "utf-8"));
}

// Load the grammar data from the repo's grammar/ directory, resolved relative
// to this module so it works from any working directory.
export function loadGrammar() {
  setVocabulary(readJson("../grammar/vocabulary.json"));
  setAmberTemplates(readJson("../grammar/messages/amber.json"));
}
