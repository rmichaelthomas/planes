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
      "regenerate the grammar data with a version of planes matching " +
        "this interpreter — if the data is newer than what this " +
        "interpreter reads, upgrade planes instead of regenerating the " +
        "data",
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

// grammar/core.json — the declared port surface, injected by the same route and
// for the same reason as the vocabulary: js/core_restrict.mjs and the interpreter
// both need it, neither may statically import node:fs, and there must be exactly
// one copy of it in the process. A browser page that never sets it simply has no
// core-restricted mode; `coreLoaded()` says so and the interpreter refuses to arm
// rather than guessing at a core it cannot read.
let _core = null;
const REQUIRED_CORE_KEYS = ["keywords", "builtins", "effect_kinds_all_core"];

export function setCore(doc) {
  if (doc.format !== GRAMMAR_FORMAT_VERSION) {
    throw new GrammarDataError(
      "grammar-data-missing",
      `core format ${JSON.stringify(doc.format)} is not ${GRAMMAR_FORMAT_VERSION}`,
      "regenerate the grammar data with a version of planes matching " +
        "this interpreter",
    );
  }
  const missing = REQUIRED_CORE_KEYS.filter((k) => !(k in doc));
  if (missing.length) {
    throw new GrammarDataError(
      "grammar-data-missing",
      `core is missing: ${missing.join(", ")}`,
      "reinstall planes — grammar/core.json is hand-edited, and " +
        "core_check.py holds it against the vocabulary",
    );
  }
  _core = doc;
}

export function core() {
  if (_core === null) {
    throw new GrammarDataError(
      "grammar-data-missing",
      "core not loaded",
      "call loadGrammar() (Node) or setCore(...) (browser) first",
    );
  }
  return _core;
}

export function coreLoaded() {
  return _core !== null;
}

// Amber's refusal-message templates — grammar/messages/amber.json, keyed by id.
// parser.py loads these lazily (render_amber); here they are injected the same
// way the vocabulary is.
let _amber = null;
export function setAmberTemplates(doc) {
  _amber = {};
  for (const t of doc.templates) _amber[t.id] = t;
}
export function amberTemplates() {
  if (_amber === null) {
    throw new GrammarDataError(
      "grammar-data-missing",
      "amber templates not loaded",
      "call loadGrammar() (Node) or setAmberTemplates(...) (browser) first",
    );
  }
  return _amber;
}
