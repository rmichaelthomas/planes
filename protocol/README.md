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
table, number grammar), **`js/paint/stream.mjs`** (stream-level error tags),
and **`planes-drawing-protocol-v1.md`** (verb groups — see below). None of
the three is modified by the generator — it only reads.

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
clusters a verb belongs to. It is read out of
**`planes-drawing-protocol-v1.md`** instead: each `### 6.N <title>` heading
(§6.1 "Colour and line" through §6.5 "Text and canvas") names a group —
slugified, lowercased, spaces to hyphens — and that section's markdown table
names the verbs in it (`extractSpecGroups` in `scripts/protocol_gen.mjs`).
If the specification gains a verb, moves one to a different section, or
renames a section, `protocol.json` changes on the next run with no edit to
the generator.

This document was not present anywhere in this repository (verified by a
repo-wide search and `git log --all`) when this generator was first
written, so groups were originally derived from `ARITY`'s own declared key
order in `js/paint/protocol.mjs` — a source with no formal claim to
authority over grouping, only an empirical one. That derivation turned out
to agree with the specification's real section order exactly, verb for
verb, once the document became available and was copied in. The generator
now reads the specification directly; the coverage check (every verb
exactly one group, every group non-empty) and `js/test/protocol_gen.test.mjs`
still assert the result rather than assume it.

## CI

`scripts/ci.sh` runs `node scripts/protocol_gen.mjs --check` immediately
after `grammar_gen.py --check`.
