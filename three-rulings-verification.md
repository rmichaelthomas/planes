# C5 three-rulings verification

| | check | result | detail |
|---|---|---|---|
| A | a runner-less suite exits non-zero | ✅ pass | exit 1 |
| A | the failure names the silent file | ✅ pass | SILENT: 1 suite file(s) reported no result: test_zz_c5_silent_probe.py |
| A | a deliberately skipped suite does not fail the gate | ✅ pass | exit 0 |
| A | the probe suite is removed | ✅ pass | test_zz_c5_silent_probe.py |
| A | every js test file that exists is one the gate runs | ✅ pass | 7 of 7 |
| A | a stray .mjs in a subdirectory fails the gate | ✅ pass | exit 1 |
| A | a stray .mjs beside the test directory fails the gate | ✅ pass | exit 1 |
| A | the probe .mjs files are removed | ✅ pass | js/test/_c5_probe_sub/stray.test.mjs, js/_c5_stray.test.mjs |
| A | ci.sh runs run_suites.py as a hard step | ✅ pass | 2 timed, 0 timed_soft |
| A | ci.sh runs check_js_tests.py as a hard step | ✅ pass | 1 timed, 0 timed_soft |
| B | the sub-counts sum to the shortfall they split | ✅ pass | 44 + 28 = 72 |
| B | the self-hosted total is unmoved at 72 of 113 | ✅ pass | 72 of 113 |
| B | the per-file breakdown is preserved | ✅ pass | interp.planes 54, parser.planes 14, lexer.planes 3, json.planes 1 |
| B | multiplicity is reported rather than resolved | ✅ pass | 35 sites, 10 tags |
| B | an unreadable tag falls to the side nothing checked | ✅ pass | 3 sites |
| B | the reference work list is still zero of 109 | ✅ pass | 0 of 109 |
| B | the tag-matching ceiling is reported | ✅ pass | 51 of 109 catalogued errors carry no tag |
| B | the checker still reports and never fails (invariant 3) | ✅ pass | exit 0 / 0 |
| B | --json carries the split | ✅ pass | {"has a reference twin": 44, "no reference twin": 28, "sum": 72} |
| C | `when e is { path }` binds on every error | ✅ pass | py=['bound: nothing'] js=['bound: nothing'] planes=['bound: nothing'] |
| C | `when e is { fix }` is unchanged | ✅ pass | py=['bound: nothing'] js=['bound: nothing'] planes=['bound: nothing'] |
| C | a real path still carries the same steps | ✅ pass | py=['2', 'a1'] js=['2', 'a1'] |
| C | the field is present-and-nothing, not absent | ✅ pass | keys=['detail', 'fix', 'path', 'tag'] |
| C | the self-hosted record carries the field too | ✅ pass | make-error-value |
| C | no .planes program used `{ path }` as a presence test | ✅ pass | 109 files searched, 0 users |
| C | all three agree on tag and detail across every shape | ✅ pass | 348 shapes, 0 divergences |
| D | reserved words still 32 | ✅ pass | 32 |
| D | builtins still 10 | ✅ pass | 10 |
| D | effect kinds still 7 | ✅ pass | 7 |
| D | host methods still 7 | ✅ pass | ask, read, write, show, clock, resolve, parse_json |
| D | token classes still 7 | ✅ pass | 7 |
| D | js/test passes and is at least the 47 baseline | ✅ pass | 47 passing |
| D | the suite passes | ✅ pass | exit 0 |
| D | every suite file reports a result | ✅ pass | 54 of 54 |
| D | the ok total is at least the 1085 baseline | ✅ pass | 1092 oks |

B: the split is 44 to port, 28 to write — and 28 is a ceiling, not a measurement: 51 of the 109 catalogued reference errors carry no tag at all, so a self-hosted syntax error cannot match one however close the message.

**ALL CHECKS PASS**
