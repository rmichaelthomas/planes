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
5. **Port the reference's structure.** Keep `js/`'s file split and function
   names where Swift allows, so a divergence can be found by reading two files
   side by side.
