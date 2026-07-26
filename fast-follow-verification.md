# C4 fast-follow verification

| | check | result | detail |
|---|---|---|---|
| A | case list is non-trivial | ✅ pass | 481 cases |
| A | run and run-batch answer identically | ✅ pass | 481/481 identical |
| A | PLANES_JOBS=1 passes | ✅ pass | exit 0 |
| A | parallel run passes | ✅ pass | exit 0 |
| A | serial and parallel totals match | ✅ pass | serial=(54, 54, 1085) parallel=(54, 54, 1085) |
| A | every suite file reports a result | ✅ pass | 54 of 54 files reporting |
| A | ok total is at least the 996 baseline | ✅ pass | 1085 oks |
| B | fail accepts a record naming message and fix | ✅ pass | tag=t fix='f' |
| B | fail still accepts plain text, naming no fix | ✅ pass | fix='' |
| B | the record form's fix reaches e.fix | ✅ pass | py=['inner', 'boom', 'hold it right'] js=['inner', 'boom', 'hold it right'] planes=['inner', 'boom', 'hold it right'] |
| B | fix is nothing where none was given | ✅ pass | py=['true'] js=['true'] planes=['true'] |
| B | when e is { fix } binds a named fix | ✅ pass | py=['bound: do it this way'] js=['bound: do it this way'] planes=['bound: do it this way'] |
| B | when e is { fix } binds on an error with none | ✅ pass | py=['bound: nothing'] js=['bound: nothing'] planes=['bound: nothing'] |
| B | or fail carries a caught fix forward | ✅ pass | py=['re-tagged', 'deep', 'the original fix'] js=['re-tagged', 'deep', 'the original fix'] planes=['re-tagged', 'deep', 'the original fix'] |
| B | path keeps the opposite convention (reported, not fixed) | ✅ pass | ['no path field'] |
| C | declared host surface is seven | ✅ pass | declared: ask, read, write, show, clock, resolve, parse_json |
| C | used host surface equals declared | ✅ pass | used: ask, clock, parse_json, read, resolve, show, write |
| C | to_json is gone from the surface | ✅ pass |  |
| C | parse_json kept — it has a live caller | ✅ pass | 2 use(s) |
| C | the JS host names the same seven | ✅ pass | ask, read, write, show, clock, resolve, parseJson |
| C | no host JSON capability reachable from grammar/*.planes | ✅ pass | none |
| D | every effect-name case agrees in all three | ✅ pass | 19 cases |
| D | the refusal message is byte-identical (py vs js) | ✅ pass | identical |
| D | the refusal message is byte-identical (py vs self-hosted) | ✅ pass | identical |
| D | all seven kinds accepted after 'doing' and in a rule | ✅ pass | ask, clock, env, random, read, show, write |
| E | reserved words still 32 | ✅ pass | 32 |
| E | builtins still 10 | ✅ pass | 10 |
| E | effect kinds still 7 | ✅ pass | 7 |
| E | host methods now 7 | ✅ pass |  |
| E | corpus still runs through the self-hosted stack | ✅ pass | SELF-HOSTED RUNNABLE 50 / 50 |
| E | the reference error work list is still zero | ✅ pass | 0 |


C — host method call sites (production code only):

| method | declared | uses | sites |
|---|---|---|---|
| `ask` | yes | 2 | interp.py:936 (use), js/interp.mjs:753 (use) |
| `read` | yes | 3 | grammar_gen.py:20 (use), interp.py:963 (use), js/cli.mjs:84 (probe), js/interp.mjs:782 (use) |
| `write` | yes | 2 | interp.py:794 (use), js/cli.mjs:92 (probe), js/interp.mjs:628 (use) |
| `show` | yes | 2 | interp.py:585 (use), js/interp.mjs:415 (use) |
| `clock` | yes | 2 | interp.py:453 (use), js/cli.mjs:97 (probe), js/interp.mjs:327 (use) |
| `resolve` | yes | 3 | interp.py:1194 (use), js/cli.mjs:67 (probe), js/cli.mjs:74 (probe), js/interp.mjs:992 (use), scripts/run_corpus_through_planes.py:112 (use) |
| `parse_json` | yes | 2 | interp.py:949 (use), js/cli.mjs:60 (probe), js/interp.mjs:768 (use) |
| `to_json` | **removed** | 0 | — |

Before C4: declared 8, used 7 (`to_json` had 0). After: declared 7, used 7.

B.3 — self-hosted fix-clause shortfall: **72** of 113 raise sites in `grammar/*.planes`. Reported, not merged into the reference's list, and not driven to zero in this build.

**ALL CHECKS PASS**
