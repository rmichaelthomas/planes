# sound/

The Planes sound protocol's verb table and error catalogue, as loadable data.
Both files here are **projections**, generated from the real source — neither
is hand-edited, and there is no third kind of file in this directory. This is
`protocol/`'s arrangement, repeated deliberately for the second protocol.

| File | What it is | Hand-edited or generated |
|---|---|---|
| `protocol.json` | The four-verb table (name, arity, argument shape, group), the `protocol` declaration verb, the word-argument set (`wave`), and the number grammar. Read from `js/sound/protocol.mjs`'s live `VERBS` export and `parseCommand` behaviour — never a copy of the verb list. | **Generated** by `scripts/protocol_gen.mjs`. Never hand-edit. |
| `errors.json` | Every distinct error tag the protocol can produce — five from `js/sound/protocol.mjs` (`wrong-arity`, `bad-protocol-version`, `bad-number`, `unknown-verb`, `bad-word`) and the stream-level ones from `js/sound/stream.mjs` (`protocol-repeated`, `protocol-late`, `unsupported-version`, and the three domain refusals `gain-out-of-range`, `bad-ratio`, `bad-time`) — with every site that raises it and, where the source states one, its fix clause. | **Generated** by `scripts/protocol_gen.mjs`. Never hand-edit. |

The source of truth for both files is **`js/sound/protocol.mjs`** (verb table,
number grammar), **`js/sound/stream.mjs`** (stream-level error tags), and
**`planes-sound-protocol-v1.md`** (verb groups, read from its own `### 6.N`
section headings). None of the three is modified by the generator — it only
reads.

## One generator, two protocols

`scripts/protocol_gen.mjs` produces this directory and `protocol/` in one run,
from one descriptor table. That is not a convenience: the generator's bracket
scanner, error-site extractors, arity prober and section reader are all about
the *shape* both protocol modules were written in, not about drawing. A second
generator would be a second reader of that shape, free to drift, and the first
symptom would be a projection that quietly stopped matching its source.

```
node scripts/protocol_gen.mjs          # regenerate all four files
node scripts/protocol_gen.mjs --check  # diff against the committed ones
```

## Three domain refusals, and why they are stream-level

`js/sound/protocol.mjs` checks *shape* — the verb exists, the argument count is
right, a number is a number, a word is in its set. `js/sound/stream.mjs` checks
what a well-formed line can still get wrong: a ratio with a zero denominator, a
gain outside 0 to 1, a note that starts before its tick or lasts no time. They
sit in the shared walk rather than in either player because a rule enforced in
one player and not the other is exactly the divergence two players exist to
prevent.
