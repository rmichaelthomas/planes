# Coverage baseline

Phase-zero tooling baseline (I-Q2). Branch-mode coverage (`coverage run --branch`),
full suite (`test_*.py`, 333/333 passing), committed before any Tier 0 code changes.

Run with: `coverage erase && for f in test_*.py; do coverage run --append "$f"; done && coverage report -m`

```
Name                     Stmts   Miss Branch BrPart  Cover   Missing
--------------------------------------------------------------------
host.py                     86     17     10      0    82%   49, 53, 57, 61, 65, 77, 81, 86, 89, 107-110, 113-114, 124-125, 148
interp.py                  553     45    312     37    90%   39, 54, 61, 87, 96, 103, 115, 136->138, 178, 193-195, 353, 395, 425, 434-438, 453-455, 469, 489, 495, 519, 528, 533, 546->537, 574-575, 620->624, 622->624, 665, 677->exit, 679->exit, 681, 706, 713->718, 718->exit, 721, 727, 752, 764, 798, 800-801, 803, 805, 808, 810, 825-826
lexer.py                   105      1     36     19    86%   65, 120->121, 120->exit, 122->123, 122->exit, 124->125, 124->exit, 126->127, 128->129, 128->exit, 130->131, 130->exit, 140->141, 140->exit, 142->143, 142->exit, 153->154, 153->exit, 172->173, 172->exit
modules.py                 120      1     54      3    98%   23->25, 144, 150->137
parser.py                  471     31    230     23    92%   43-44, 63, 72-73, 89, 179, 230, 253-254, 297-298, 304-305, 315-317, 364-367, 446-447, 474-475, 491, 496->503, 517, 566->573, 592, 622->626, 644, 667, 685->687, 707
planes.py                   64     31     28      9    52%   20-21, 24->27, 29-31, 34, 38-39, 45, 50-58, 61-72, 74->84, 88
planes_num.py              127     12     34      6    89%   67, 82, 110, 114, 123, 126, 135, 138, 141, 149, 155, 189
rules.py                   188      7     96      5    96%   206, 243, 347-348, 359, 448, 552
run_hn.py                   20     20      2      0     0%   1-29
shapes.py                  603     52    328     31    89%   179, 185, 229, 233, 247->249, 252, 295, 346, 400, 436-441, 486, 600-601, 602->614, 634, 667, 703, 708-709, 711-712, 714-715, 734, 744, 750-751, 779, 813-817, 821-827, 850-856, 878, 905, 907, 935, 941, 1012, 1026
shapes_cli.py              184    169     82      1     6%   92-114, 123-311, 315
shapes_python_probe.py      25     25     16      0     0%   13-54
--------------------------------------------------------------------
TOTAL                     2546    411   1228    134    82%
```

## Modules below 70% branch coverage

| Module | Cover | Note |
|---|---|---|
| `run_hn.py` | 0% | Standalone demo script (`__main__` entry point), never imported by the test suite. |
| `shapes_python_probe.py` | 0% | Standalone probe script, invoked out-of-process (not by `test_*.py`). |
| `shapes_cli.py` | 6% | The CLI entry point (`main`, `--effects`, `--why`, argument parsing, exit codes). A handful of `test_rules.py` cases shell out to it via `subprocess`, which coverage.py does not attribute back to the parent process's `.coverage` data — so the CLI's own line/branch coverage reads far lower than its actual exercise. |
| `planes.py` | 52% | The other CLI entry point (`main`, `--why`, `--effects` flags). Same `subprocess`-invocation blind spot as `shapes_cli.py`, plus several flag-combination branches with no direct in-process test. |

## Confirming the prediction

planes v3.0 §53a predicted the output layer would sit near zero while the analyser sat near
complete. Confirmed: the analyser (`shapes.py`, `rules.py`, `modules.py`) sits at 89–98%, while
the two CLI entry points (`shapes_cli.py`, `planes.py`) sit at 6% and 52% and the two standalone
scripts (`run_hn.py`, `shapes_python_probe.py`) sit at 0%. The gap is real, but it is partly a
measurement artifact, not purely absent coverage: `test_rules.py`'s CLI-exit-code tests invoke
`shapes_cli.py` as a subprocess, which does exercise those code paths at runtime but is invisible
to a `coverage.py` run scoped to the parent process. A tighter number would need
`coverage run --parallel-mode` combined with `COVERAGE_PROCESS_START` so subprocess invocations
report back — left as a follow-on, not fixed in this phase (no behavioral change permitted here).

Everything else — `lexer.py`, `interp.py`, `parser.py`, `host.py`, `planes_num.py` — is at
82–92%, consistent with "the analyser sat near complete."
