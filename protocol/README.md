# protocol/

The Planes drawing protocol's verb table and error catalogue, as loadable
data. Both files here are **projections**, generated from the real source —
neither is hand-edited, and there is no third kind of file in this directory
(contrast `grammar/`, where `vocabulary.json` is hand-edited source of
truth and `rules.json`/`errors.json` are generated).

| File | What it is | Hand-edited or generated |
|---|---|---|
| `protocol.json` | The twenty-six-verb table (name, arity, argument shape, group), the `protocol` declaration verb, the word-argument sets (`cap`/`corner`/`align`), and the number grammar. Read `js/paint/protocol.mjs`'s live `VERBS` export and `parseCommand` behaviour — never a copy of the verb list. | **Generated** by `scripts/protocol_gen.mjs`. Never hand-edit. |
| `errors.json` | Every distinct error tag the protocol can produce — five from `js/paint/protocol.mjs` (`wrong-arity`, `bad-protocol-version`, `bad-number`, `unknown-verb`, `bad-word`), eight from `js/paint/stream.mjs`'s stream-level rules (`protocol-repeated`, `protocol-late`, `unsupported-version`, `path-already-open`, `path-not-open`, `unmatched-pop`, `path-unclosed`, `unmatched-push`) — with every site that raises it and, where the source states one, its fix clause. | **Generated** by `scripts/protocol_gen.mjs`. Never hand-edit. |

The source of truth for both files is **`js/paint/protocol.mjs`** (verb
table, number grammar) **and `js/paint/stream.mjs`** (stream-level error
tags). Neither JavaScript file is modified by the generator — it only reads.

## Why this is not in `grammar/`

`grammar/` is what Planes *is* — the language's own vocabulary, grammar
forms, and error catalogue, true of every program regardless of what it
draws. The drawing protocol is what one renderer family — this repository's
canvas and SVG sinks — agreed to accept as `draw`-prefixed lines; a pen
plotter, a different rendering library, or a future second protocol version
would have its own verb table without the language changing at all.
Conflating the two would make `grammar/` describe a specific renderer's
contract instead of the language, and would make it impossible to ask "what
does the language guarantee, with or without this protocol" — exactly the
question a later experiment (measuring what the machine-readable surface
says with and without `protocol/` present) depends on being answerable.

## Regenerating

```bash
node scripts/protocol_gen.mjs            # regenerate protocol.json and errors.json
node scripts/protocol_gen.mjs --check    # regenerate into memory, diff against
                                          # the committed files, print the first
                                          # divergent line, exit non-zero on any
                                          # difference — this is the CI gate
```

`protocol_gen.mjs` carries no copy of the verb table: it imports
`js/paint/protocol.mjs`'s exported `VERBS` and discovers each verb's arity
and argument shape by calling the real, exported `parseCommand` with crafted
inputs and reading the answer back out of its own error messages, rather
than re-declaring `ARITY`/`WORDS` (which are module-private and are not
exported so the generator can read them, since this build does not modify
`js/paint/protocol.mjs`). Error tags are found by a small source-level
scanner in `scripts/protocol_gen.mjs` — this repository has no JavaScript
AST library, so it is not `grammar_gen.py`'s `ast.walk`, but it is built on
the same principle: read the source mechanically, never hand-copy it.

## A note on verb groups

`protocol.json`'s `group` field (one of `colour-and-line`, `shapes`,
`paths`, `transforms`, `text-and-canvas` per verb) has no source in
`js/paint/protocol.mjs` — nothing in that file records which of these five
clusters a verb belongs to. The specification document
`planes-drawing-protocol-v1.md`, which `protocol.mjs`'s and `stream.mjs`'s
own header comments cite as normative, does not exist in this repository
(verified by a repo-wide search and by `git log --all` before this file was
generated). The groups are instead derived from `ARITY`'s own declared key
order in `js/paint/protocol.mjs`, which already clusters the 26 verbs into
exactly these five groups with no leftover — asserted, not merely assumed,
by a coverage check in `scripts/protocol_gen.mjs` and by
`js/test/protocol_gen.test.mjs`.

## CI

`scripts/ci.sh` runs `node scripts/protocol_gen.mjs --check` immediately
after `grammar_gen.py --check`.
