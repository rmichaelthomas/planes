// js/grammar_data.mjs — the grammar's data, injected rather than read.
//
// grammar/vocabulary.json (and later rules.json / errors.json) is the single
// source of truth, exactly as it is for lexer.py and parser.py. But the shared
// JS modules must load under both Node and a browser, and a browser cannot read
// a file — so this module holds the data and is populated from the outside:
// loader_node.mjs reads the files with fs under Node; the browser page sets the
// same data from an inlined copy. No shared module statically imports node:fs,
// so every one of them loads in a browser tab.
//
// The vocabulary itself is grammar/vocabulary.json verbatim — A.7 keeps it
// read-only; this build only reads it.

// Mirrors lexer.py's GrammarDataError — refuse, don't guess.
export class GrammarDataError extends Error {
  constructor(tag, detail = "", fix = "") {
    let msg = tag;
    if (detail) msg += `: ${detail}`;
    if (fix) msg += `\n  try: ${fix}`;
    super(msg);
    this.name = "GrammarDataError";
    this.tag = tag;
    this.detail = detail;
    this.fix = fix;
  }
}

const GRAMMAR_FORMAT_VERSION = 1;
const REQUIRED_VOCAB_KEYS = [
  "token_classes",
  "keywords",
  "builtins",
  "effect_kinds",
  "field_name_token_kinds",
];

let _vocab = null;

// Validate exactly as lexer.py's _load_vocabulary does: format version, then
// the required keys.
export function setVocabulary(doc) {
  const fix = "reinstall planes, or regenerate with python3 grammar_gen.py";
  if (doc.format !== GRAMMAR_FORMAT_VERSION) {
    throw new GrammarDataError(
      "grammar-data-missing",
      `vocabulary format ${JSON.stringify(doc.format)} is not ${GRAMMAR_FORMAT_VERSION}`,
      "regenerate with a matching version of planes",
    );
  }
  const missing = REQUIRED_VOCAB_KEYS.filter((k) => !(k in doc));
  if (missing.length) {
    throw new GrammarDataError(
      "grammar-data-missing",
      `vocabulary is missing: ${missing.join(", ")}`,
      fix,
    );
  }
  _vocab = doc;
}

export function vocabulary() {
  if (_vocab === null) {
    throw new GrammarDataError(
      "grammar-data-missing",
      "vocabulary not loaded",
      "call loadGrammar() (Node) or setVocabulary(...) (browser) first",
    );
  }
  return _vocab;
}

export function vocabularyLoaded() {
  return _vocab !== null;
}
