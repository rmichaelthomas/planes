# grammar/

The language's grammar, as loadable data (addendum v4.2 sections 69.1 and
69.5). Two kinds of file live here, and they are not interchangeable:

| File | What it is | Hand-edited or generated |
|---|---|---|
| `vocabulary.json` | Source of truth for the language's vocabulary — token classes, reserved words, builtin names, effect kinds, the field-name token set, and the six positional words no other table records. `lexer.py` and `parser.py` load it at import time. | **Hand-edited.** This is the one file in this directory a person changes directly. |
| `rules.json` | A **form inventory**, not a formal grammar — one entry per `parse_*` method: what token it opens with, what AST node it produces, what sub-forms it calls, and the surface form from that method's own docstring. Deriving a true BNF from recursive-descent code is not mechanical; this is what can honestly be generated instead. | **Generated** by `grammar_gen.py`. Never hand-edit. |
| `errors.json` | Every `PlanesError` / `PlanesSyntaxError` / `PlanesAmbiguity` / `RuleConflict` / `RuleNotSupported` construction in the repo, found by walking the AST of every `.py` file — not by regex. Includes a `tags` index: every distinct error tag and every site that raises it. | **Generated** by `grammar_gen.py`. Never hand-edit. |
| `messages/amber.json` | The message templates amber's four refusal sites render from (addendum v4.2 section 69.5, ruling D5). Authored as data from the start — no amber message text lives inline in `parser.py`. | **Hand-edited.** |
| `core.json` | The subset a self-hosting implementation may use (root `README.md`) — the port surface a second host must implement to run `grammar/interp.planes`. Declared here as a single source of truth, the same role `vocabulary.json` plays for the full surface, and enforced by `core_check.py`, which fails when `interp.planes` uses any keyword or builtin outside it. `core_check.py` also holds this file against `vocabulary.json` itself: every keyword and builtin the vocabulary declares must be in a core list or in the matching `excluded_` map with a reason, and the `size` strings must parse to the real counts. That guard exists because this file drifted exactly as a hand-edited file does — `root` was outside the core with no reason recorded, and nothing said so. | **Hand-edited.** `grammar_gen.py` never reads or writes it; `core_check.py` reads it directly. |

## Why the split (ruling D2)

Making the grammar itself the source of truth would mean writing a parser
generator — a rewrite, not a tier. So *vocabulary* is source-of-truth data,
and *production rules and error templates* are projections: generated from
the actual source and checked in CI so they cannot go stale silently. A
hand-written grammar file goes stale silently, and a stale specification is
worse than none (the same reasoning as the annotation plane's generated
marker, and `audit_locked_vs_built.py`'s evidence-or-nothing check).

Deleting `rules.json` or `errors.json` changes no program's output, no
effect log, and no test result — they are pure projections of the real
source. Deleting `vocabulary.json` fails loudly (`grammar-data-missing`),
never silently, from every entry point that loads it.

## The drawing protocol is not here

`protocol/` holds the same kind of thing (a verb table and an error
catalogue, both generated) for the Planes drawing protocol — but as a
sibling directory, not a subdirectory of this one. The drawing protocol is
what one renderer family agreed to accept, not part of the language itself,
so putting it here would conflate *what Planes is* with *what one renderer
family agreed to*. See `protocol/README.md`.

## Regenerating

```bash
python3 grammar_gen.py            # regenerate rules.json and errors.json
python3 grammar_gen.py --check    # regenerate into memory, diff against the
                                   # committed files, exit non-zero on any
                                   # difference — this is the CI gate
```

`grammar_gen.py --check` never touches `vocabulary.json`; that file is read
like any other input, not written.

## CI

`scripts/ci.sh` runs, in order: the full test suite, the JavaScript test
enumeration and `node --test`, `audit_locked_vs_built.py`,
`grammar_gen.py --check`, `protocol_gen.mjs --check`, `core_check.py` (twice —
once for `interp.planes`, once for `json.planes`), the two coverage reports,
`ruff check .`, and `mypy .`. Every step exits non-zero on failure except the
two coverage reports, which are reports by construction and never gate. There
was no existing CI configuration in this repo to extend, so this script is that
gate, until one exists.
