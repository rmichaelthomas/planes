# swift/ — Planes in Swift

The third host, after the Python reference and `js/`. It is a port of the
reference, held to the same agreement suites: each `test_swift_*.py` at the repo
root is its `test_js_*.py` counterpart with `planes-swift` in place of
`node js/cli.mjs`, and compares against the Python implementation. It has no
dependencies and targets macOS 14 (the `Planes` library also targets iOS 17;
see "The root manifest" below).

```bash
swift build --package-path swift          # the library and the CLI
python3 test_swift_text.py                 # one agreement suite (builds if stale)
```

`import Planes` is the library. `planes-swift` is the agreement CLI; its
subcommands and output forms mirror `js/cli.mjs` exactly.

## The root manifest (E3)

SwiftPM resolves a remote package dependency (`.package(url: ..., from: ...)`)
only from a manifest at the repository root, never one in a subdirectory
(Koncord v1.12 build prompt §2) — so `/Package.swift`, at the repo root, is
what a downstream consumer actually depends on. It is not a second copy of
the sources: it points `path:` at these same `Sources/Planes` and
`Sources/PlanesCLI` directories, under the same product names (`Planes`,
`planes-swift`). `swift/Package.swift` keeps working unchanged for local
development and for the `test_swift_*.py` suites (`swift_host.py` always
builds `--package-path swift`); `test_swift_root_package.py` holds the root
manifest to it — same products and targets by `swift package describe --type
json`, plus an actual `swift build` from the root, cached the way
`swift_host.py` caches `swift/`'s binary.

Platforms: `.macOS(.v14)` and `.iOS(.v17)`. The platform list is
package-wide — it is not possible to give one target in a manifest a
different platform list than another — so adding iOS was only safe to do
after checking nothing under `Sources/` is macOS-only: no `Process` (Foundation's
process-launching type, unavailable on iOS) anywhere in `Sources/Planes` or
`Sources/PlanesCLI`, no `#if os(macOS)`, and every `FileManager` use
(`Modules.swift`, `EffectSurfaceToolCommand.swift`, `CLI.swift`) is ordinary
path/file access available on iOS — nothing reads a home directory or
anything else iOS sandboxes away at compile time. Verified both ways:
`swift build --triple arm64-apple-ios17.0 --sdk $(xcrun --sdk iphoneos
--show-sdk-path)` from the root, and `xcodebuild -scheme Planes -destination
'generic/platform=iOS' build`, both succeed for the `Planes` library target
(the produced binary's load command reports `platform 2` / `minos 17.0`,
confirmed with `otool -l`). `PlanesCLI` also happens to compile for iOS
(nothing in it is macOS-only either), but stays a plain command-line
executable — iOS has no notion of running one outside a jailbreak, so its
practical iOS relevance is nil regardless of whether it type-checks. It is
kept macOS-only in practice, and the root manifest's `planes-swift` product
is not something an iOS consumer would ever depend on — only `Planes`,
the library, is.

A repo-internal benchmark tool (H4, added separately) is deliberately **not**
in the root manifest: it uses `Process` and `Darwin` APIs freely
(macOS-only, on purpose), and is not a product a downstream consumer should
ever see.

## What is ported

| Reference | Swift | Suite |
|---|---|---|
| `planes_text.py` | `PlanesText.swift` | `test_swift_text.py` |
| `planes_num.py` (exact rationals, over `BigInt.swift`) | `PlanesNumber.swift` | `test_swift_num.py` |
| `hashlib.sha256` | `SHA256.swift` (CryptoKit) | `test_swift_hash.py` |
| grammar data | `Grammar.swift`, `Generated/GrammarData.swift` | `test_swift_grammar_data.py` |
| `lexer.py` | `Lexer.swift` | `test_swift_lexer.py` |
| `parser.py` and the canonical AST form | `Nodes.swift`, `Parser.swift`, `Canonical.swift`, `CoreRestrict.swift` | `test_swift_parser.py` |
| `shapes.py`, `shapes_cli.py` | `EffectSurface.swift`, `Modules.swift` | `test_swift_shapes.py`, `test_swift_shapes_derivation.py`, `test_swift_shapes_cli.py`, `test_swift_metacircular_shapes.py` |
| `rules.py`, rule rendering | `Rules.swift`, `Render.swift` | `test_swift_rules.py` |
| Python's Unicode tables | `PythonUnicode.swift`, `Generated/PythonUnicodeData.swift` | `test_python_unicode_data.py` |

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
`python3 scripts/python_unicode_gen.py`; `test_python_unicode_data.py` runs its
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
