# protocol/ data verification

One-time build verification for "The machine-readable surface closes its gaps" — see scripts/verify-protocol-data.mjs's header for the retirement-rule note (this script is deleted after this report is captured; its durable assertions live in js/test/protocol_gen.test.mjs and test_grammar_data.py).

| # | Section | Check | Result | Detail |
|---|---|---|---|---|
| 1 | A | protocol.json's verb set equals VERBS | PASS | protocol.json: 26 verbs, VERBS: 26 verbs |
| 2 | A | every verb's declared arity matches parseCommand's own enforcement | PASS | all agree |
| 3 | A | every word_arguments set matches parseCommand's own bad-word rejection | PASS | all agree |
| 4 | A | draw.planes's helper set equals the verb set minus protocol | PASS | draw.planes: 26 helpers, VERBS: 26 |
| 5 | B | a verb added to a stub ARITY produces a differing JSON (the extra verb appears) | PASS | without: false, with: true |
| 6 | B | --check fails on a hand-edited protocol.json and passes after restoring it | PASS | fails-on-edit: true, passes-after-restore: true |
| 7 | C | every tag has its site and, for protocol.mjs, a fix clause | PASS | 20 entries, 13 distinct tags |
| 8 | C | 5 tags from protocol.mjs, 8 from stream.mjs, 13 total (this prompt's assumption) | PASS | protocol.mjs: {bad-number, bad-protocol-version, bad-word, unknown-verb, wrong-arity}<br>  stream.mjs:   {path-already-open, path-not-open, path-unclosed, protocol-late, protocol-repeated, unmatched-pop, unmatched-push, unsupported-version}<br>  stream.mjs matches this prompt's assumed eight exactly: true |
| 9 | D | the exactness section parses and has the expected shape | PASS | value_properties[0] is the exactness record with 5 rules |
| 10 | D | no loader references value_properties | PASS | zero references outside this build's own scripts |
| 11 | D | grammar_gen.py --check passes | PASS | exit 0 |
| 12 | E | every verb has exactly one group, every group is non-empty | PASS | colour-and-line: 5, shapes: 6, paths: 5, transforms: 5, text-and-canvas: 5 |

**12/12 checks passed.**

No blocking failures (sections A, B, D all pass).
