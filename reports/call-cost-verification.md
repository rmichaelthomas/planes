# Call-cost verification

| Check | Pass | Blocking | Detail |
|---|---|---|---|
| A — Non-perturbation: every changed/new path (tracked + untracked) is only under scripts/, benchmarks/, reports/ | PASS | yes | 7 file(s) changed, all within scope |
| B — Differential integrity: real arms byte-identical AND a perturbed twin is caught | PASS | yes | real run streamsIdentical=true, callsPerTick=140; perturbed run correctly exited 1 with STREAMS_IDENTICAL=false |
| C — Timer discipline: >=200ms/trial, >=7 trials, control subtracted correctly (JS + Python) | PASS | no | all rungs (JS + Python) satisfy the floor, trial count, and subtraction |
| D — Report completeness: 6 sections present, implementations named, closure criterion precedes ladder table | PASS | no | all six sections present; criterion at line 123, table at line 204 |
| E — Invariants: builtins=11, Host methods=7, VERBS=26, paint/grammar/js-paint untouched, *.py changes confined to scripts/ | PASS | yes | builtins=11, host methods present, VERBS=26, no out-of-scope diffs |

**Result: PASS**
