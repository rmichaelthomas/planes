# swift/ — Planes in Swift

The third host, after the Python reference and `js/`. It is a port of the
reference, held to the same agreement suites: each `test_swift_*.py` at the repo
root is its `test_js_*.py` counterpart with `planes-swift` in place of
`node js/cli.mjs`, and compares against the Python implementation. It has no
dependencies and targets macOS 14.

```bash
swift build --package-path swift          # the library and the CLI
python3 test_swift_text.py                 # one agreement suite (builds if stale)
```

`import Planes` is the library. `planes-swift` is the agreement CLI; its
subcommands and output forms mirror `js/cli.mjs` exactly.

## What is ported

| Reference | Swift | Suite |
|---|---|---|
| `planes_text.py` | `PlanesText.swift` | `test_swift_text.py` |
| `planes_num.py` (exact rationals, over `BigInt.swift`) | `PlanesNumber.swift` | `test_swift_num.py` |
| `hashlib.sha256` | `SHA256.swift` (CryptoKit) | `test_swift_hash.py` |
| grammar data | `Grammar.swift`, `Generated/GrammarData.swift` | `test_swift_grammar_data.py` |
| `lexer.py` | `Lexer.swift` | `test_swift_lexer.py` |
| `parser.py` and the canonical AST form | `Nodes.swift`, `Parser.swift`, `Canonical.swift`, `CoreRestrict.swift` | `test_swift_parser.py` |
| `shapes.py`, `shapes_cli.py` | `Shapes.swift`, `Modules.swift` | `test_swift_shapes.py`, `test_swift_shapes_derivation.py`, `test_swift_shapes_cli.py`, `test_swift_metacircular_shapes.py` |
| `rules.py`, rule rendering | `Rules.swift`, `Render.swift` | `test_swift_rules.py` |
| Python's Unicode tables | `PythonUnicode.swift`, `Generated/PythonUnicodeData.swift` | `test_swift_unicode_data.py` |

Not yet ported: the interpreter (`interp.py`, the host and module effects), so
`planes-swift` cannot run a program.

`HostRules.swift` is the one Swift-only surface: a host application parses a
`.planes` rules source, describes the effects it means to perform (a network
ask with a literal destination, a write), and checks them, getting back the
same `Violation`s `rules.py` would report for a program performing those
effects — plus each violated rule's `because`. `test_swift_host_rules.py`
holds it to shapes.py and rules.py on that equivalent program.

The grammar files `js/loader_node.mjs` reads off disk (`grammar/vocabulary.json`,
`grammar/messages/amber.json`, `grammar/core.json`) are embedded verbatim in
`Sources/Planes/Generated/GrammarData.swift`, so the library runs where this repo
is not. That file is generated: edit the grammar, then run
`python3 scripts/swift_grammar_gen.py`; `test_swift_grammar_data.py` runs its
`--check` and fails on a stale copy.

Python's own Unicode behaviour — `str.isprintable`, `str.lower`, `str.upper`,
NFC — is embedded the same way, in `Sources/Planes/Generated/PythonUnicodeData.swift`,
because shapes.py folds text through them and neither Swift's runtime tables nor
Foundation's normaliser match Python's (rule 5). After a Python upgrade, run
`python3 scripts/swift_unicode_gen.py`; `test_swift_unicode_data.py` runs its
`--check`.

## Porting rules

These are the places Swift differs from Python in ways that change results
silently. Every one has bitten a port somewhere.

1. **Text is code points.** Swift `String` compares, hashes and orders by
   canonical equivalence and counts grapheme clusters. Python does neither.
   Count, iterate, compare, sort and key Planes text through `unicodeScalars`,
   `CodePoints` or `sameText` (`PlanesText.swift`) — never `String ==`,
   `Character`, `.count`, `<`, or a `Dictionary<String, _>` whose keys come
   from program text.
2. **Order is insertion order.** Python `dict` iterates in insertion order;
   Swift `Dictionary` does not. Anything whose iteration order reaches output —
   a canonical form, an error message, a rendered list — uses an ordered
   structure.
3. **Numbers are exact.** Planes numbers are rationals over unbounded integers
   (`planes_num.py`). No `Double` on any path that computes a Planes value.
4. **Messages are byte-identical.** An error message is part of the language's
   output and is compared as a string. Port the text, not the gist.
5. **Character classes are Python's.** `re`'s `\d` is every Unicode decimal
   digit, `str.strip()` strips Python's `isspace` set, and both are fixed at
   Python's Unicode version, not Swift's. Where the reference uses one, port the
   exact set (`Lexer.swift` does) and drive every member through a suite.
6. **Port the reference's structure.** Keep `js/`'s file split and function
   names where Swift allows, so a divergence can be found by reading two files
   side by side.
