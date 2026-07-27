# Coverage baseline

Phase-zero tooling baseline (I-Q2), corrected for subprocess attribution (Tier 0
follow-on, gap 3). Branch-mode coverage (`coverage run --branch`), full suite
(`test_*.py`).

## Before subprocess attribution

Original measurement, committed with the Tier 0 annotation-plane build, 333/333
passing, before any Tier 0 code changes. `coverage run` scoped to the parent
process only — `test_rules.py`'s CLI-exit-code tests invoke `shapes_cli.py` (and
`planes.py`) via `subprocess.run([sys.executable, ...])`, a separate process a
parent-scoped `coverage run` cannot see into.

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

`shapes_cli.py` at 6%, `planes.py` at 52% — flagged at the time as partly a
measurement artifact, not fixed because that phase was forbidden any behavioural
change.

## After subprocess attribution

Fixed per `pyproject.toml`'s `[tool.coverage.run] parallel = true` +
`[tool.coverage.paths]`, plus `sitecustomize.py` at the repo root calling
`coverage.process_startup()` (a no-op unless `COVERAGE_PROCESS_START` is set,
which `subprocess.run` inherits from the parent by default — the standard
coverage.py subprocess-measurement hook).

Run with:
```
coverage erase
export COVERAGE_PROCESS_START="$(pwd)/pyproject.toml"
for f in test_*.py; do coverage run "$f"; done
unset COVERAGE_PROCESS_START
coverage combine
coverage report -m
```

Suite verified passing both under coverage and without it (failure mode 8) —
365/365 either way (333 prior + `render.py`'s own 12 tests + the annotation gaps'
3 new inertness tests = the current total after this follow-on build's Phase 1/2).

```
Name                     Stmts   Miss Branch BrPart  Cover   Missing
--------------------------------------------------------------------
host.py                     86     17     10      0    82%   49, 53, 57, 61, 65, 77, 81, 86, 89, 107-110, 113-114, 124-125, 148
interp.py                  571     44    326     39    91%   39, 54, 61, 87, 103, 115, 136->138, 178, 193-195, 259, 291, 383, 425, 455, 465-466, 483-485, 499, 525, 549, 558, 563, 576->567, 604-605, 650->654, 652->654, 695, 707->exit, 709->exit, 711, 736, 743->748, 748->exit, 751, 757, 782, 794, 833, 835-836, 838, 840, 843, 845, 863-864, 873
lexer.py                   113      1     36     19    87%   65, 120->121, 120->exit, 122->123, 122->exit, 124->125, 124->exit, 126->127, 128->129, 128->exit, 130->131, 130->exit, 140->141, 140->exit, 142->143, 142->exit, 154->155, 154->exit, 173->174, 173->exit
modules.py                 120      1     54      3    98%   23->25, 144, 150->137
parser.py                  527     32    252     24    93%   43-44, 72-73, 89, 182, 233, 256-257, 300-301, 307-308, 318-320, 440, 447-448, 462-463, 470-471, 532-533, 560-561, 577, 582->589, 603, 652->659, 678, 708->712, 753, 771->773, 793
planes.py                   64     28     28      7    58%   24->27, 29-31, 34, 38-39, 45, 50-58, 61-72, 74->84
planes_num.py              127     12     34      6    89%   67, 82, 110, 114, 123, 126, 135, 138, 141, 149, 155, 189
render.py                  237     13    152     14    93%   94, 96, 109, 111, 123-128, 175, 184->181, 201->214, 281, 330->329, 400, 406, 410, 412
rules.py                   188      7     96      5    96%   206, 243, 347-348, 359, 448, 552
run_hn.py                   20     20      2      0     0%   1-29
shapes.py                  603     44    328     28    91%   179, 185, 229, 233, 247->249, 252, 346, 400, 436-441, 486, 600-601, 602->614, 634, 667, 703, 708-709, 711-712, 714-715, 734, 744, 779, 813-817, 821-827, 856, 878, 905, 907, 935, 941, 1026
shapes_cli.py              200     97     84     14    51%   97, 109, 131-152, 155-188, 192-193, 203-204, 209-214, 231-245, 254-256, 263-265, 270-272, 283-285, 301, 304-305, 312-320, 329, 335
shapes_python_probe.py      25     25     16      0     0%   13-54
--------------------------------------------------------------------
TOTAL                     2881    341   1418    159    87%
```

## The delta

| Module | Before | After | Change |
|---|---|---|---|
| `shapes_cli.py` | 6% | 51% | **+45pp** — the artifact was real |
| `planes.py` | 52% | 58% | +6pp |
| `run_hn.py` | 0% | 0% | unchanged — genuinely never imported by the suite |
| `shapes_python_probe.py` | 0% | 0% | unchanged — genuinely never imported by the suite |
| TOTAL | 82% | 87% | +5pp |

## What is genuinely under-covered after correction (not fixed here)

`shapes_cli.py` at 51% is real, not an artifact — `test_rules.py`'s subprocess
tests exercise only the `--rules` exit-code paths. Traced against the current
`Missing` column, the following CLI surfaces have **no test coverage at all**,
in-process or via subprocess: `--index`, `--search`, `--diff`, `--render`,
`--fingerprints`, `--json`, `--functions`, `--check`, and the top-level
`PlanesSyntaxError`/`ModuleError`/"no such file" error branches in `main()`.
`planes.py` at 58% is similarly real — several flag-combination branches
(`-e`, `--why` on a name that doesn't resolve, `--effects` with an empty
effect log) have no direct test.

Per this build's own scope (§5.3: no test written to chase a coverage number),
these are reported, not fixed. A future coverage-driven pass over the CLI
surfaces is its own build with its own review.

`run_hn.py` and `shapes_python_probe.py` staying at 0% is honest, not a gap —
both are standalone entry-point scripts, never imported by anything in
`test_*.py`, and running them would mean shelling out to the real network or a
Python-introspection probe respectively — outside what an automated suite
should do.

## Confirming (and correcting) the prediction

planes v3.0 §53a predicted the output layer would sit near zero while the
analyser sat near complete. Still true in shape — analyser modules (`shapes.py`,
`rules.py`, `modules.py`) sit at 91–98%, `shapes_cli.py` still trails everything
else in the codebase even after correction — but the *size* of the original gap
was inflated by the measurement blind spot: `shapes_cli.py` was never actually at
6% exercise, it was at 51%, and the other 49% is a real, now-named gap rather
than an invisible one.
