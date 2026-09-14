# H7 — the published benchmarks

Sprint A, item H7 (`docs/planes_sprint_2026_09_hardening.md`, decision #21):
four ordinary jobs written in Planes, plain Python and plain Node, plus
effect-surface time over the corpus. Decision #38 says which machine's
numbers count: the architect's Mac, named below.

**Commit measured:** `6b0499ee9e92f45c3bb98cb2674078c79229d681` — "H8: run the
oracle and three metamorphic checks over the whole corpus (#130)"
**Date:** 2026-09-13

## Machine

- CPU: Apple M1 Pro
- Cores: 10 (`sysctl -n hw.ncpu`)
- Memory: 16 GB (`sysctl -n hw.memsize` = 17179869184 bytes)
- OS: macOS 26.5.2 (`sw_vers -productVersion`)
- Python: 3.14.7
- Node: v22.23.1

No other heavy job ran on this machine while measuring; nothing else was
using the CPU concurrently.

## Method

- **Set A** — `benchmarks/published/set_a_bench.py`. Four jobs, each
  written in Planes, plain Python and plain Node by
  `benchmarks/published/gen_jobs.py`, checked for identical output across
  all four execution paths before any timing runs, then each path run 5
  times as a fresh subprocess; wall clock is `time.perf_counter()` around
  the whole `subprocess.run` call, so process startup is included in every
  number. A `hello` job (`show "hello"` / `print("hello")` /
  `console.log("hello")`) is measured the same way as a startup baseline.
  Reported: median and min, in milliseconds, over 5 runs.
- **Set B** — `benchmarks/published/set_b_bench.py`. `python3 shapes_cli.py
  <file> --json` and `node js/cli.mjs shapes <file>` timed the same way,
  5 runs per file, median taken per file and summed for the total, over
  all 51 files under `corpus/*.planes`. Process startup (`python3 -c
  "pass"` / `node -e ""`, 5 runs, median) is reported separately rather
  than subtracted, so the total above stays an honest wall-clock number.

**No job program is committed to this repo.** `gen_jobs.py` writes the
`.planes`/`.py`/`.mjs` sources for all four jobs (plus `hello`) to a temp
directory at benchmark time, not to `benchmarks/published/`. This is not
a style choice: `test_js_metacircular.py` and `test_js_core_restricted.py`
both glob every `**/*.planes` file anywhere under the repo and run each
one through the self-hosted interpreter and the restricted-core check,
and these programs — sized for a wall-clock benchmark, not for that —
broke three of those suites the first time they were committed under
`benchmarks/published/jobs/`. `gen_jobs.py --out DIR` writes the same
sources to any directory a reader wants to inspect them from, and
`set_a_bench.py` calls `gen_jobs.py` (default output) itself before every
run. Before removing the once-committed copies, the generator (already
updated to take `--out`) was run to a fresh temp directory and diffed
against them (`diff -rq`): the two trees were byte-identical, so this
change is a relocation of where the sources live, not a re-measurement —
the numbers above are the ones originally measured against the committed
files, unchanged.

Rerun either with `python3 benchmarks/published/set_a_bench.py --runs 5
--out /tmp/set_a.json` / `python3 benchmarks/published/set_b_bench.py
--runs 5 --out /tmp/set_b.json` — both regenerate their own inputs first
(`set_a_bench.py` calls `gen_jobs.py`; Set B reads the corpus directly)
and write only under `/tmp`, never the repo. To read the job sources
without running anything, `python3 benchmarks/published/gen_jobs.py --out
DIR` writes them to `DIR`.

---

## Set A — four ordinary jobs

Four execution paths per job:

- **planes.py** — `python3 planes.py <job>.planes` (the Python reference
  interpreter).
- **planes-js** — `node js/cli.mjs run <job>.planes` (README's own
  documented invocation, "the JavaScript implementation").
- **plain-py** — `python3 <job>.py`.
- **plain-js** — `node <job>.mjs`.

All four produce line-for-line identical `show`/`print`/`console.log`
output for every job (asserted by `set_a_bench.py` before any run is
timed); the file-transform job's written output is asserted equal too,
after JSON-decoding Planes' side (see that job's note below).

| job | size | planes.py median | planes.py min | planes-js median | planes-js min | plain-py median | plain-py min | plain-js median | plain-js min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| hello (baseline) | — | 78.58 ms | 78.01 ms | 80.09 ms | 79.63 ms | 27.18 ms | 25.67 ms | 66.80 ms | 63.43 ms |
| word count | 50,000 words | 5624.86 ms | 5614.67 ms | 391.09 ms | 385.17 ms | 33.66 ms | 30.39 ms | 82.06 ms | 78.50 ms |
| record updates | 2,000 records × 50 `with` updates | 1381.78 ms | 1374.12 ms | 263.17 ms | 258.94 ms | 32.72 ms | 31.96 ms | 68.62 ms | 68.14 ms |
| invoice arithmetic | 5,000 lines | 568.36 ms | 561.88 ms | 162.43 ms | 157.72 ms | 58.69 ms | 58.64 ms | 69.66 ms | 67.58 ms |
| file transform | 10,000 rows | 5361.75 ms | 5355.92 ms | 951.94 ms | 942.23 ms | 43.18 ms | 42.00 ms | 80.14 ms | 79.36 ms |

**Planes vs plain, by median** (raw ratio, and the same ratio after
subtracting the hello-world startup baseline from both sides — the second
column isolates the per-job work from process startup, which the hello row
shows dominates the raw ratio for the cheaper jobs):

| job | planes.py / plain-py | …startup-adjusted | planes-js / plain-js | …startup-adjusted |
|---|---:|---:|---:|---:|
| word count | 167.1x | 855.9x | 4.8x | 20.4x |
| record updates | 42.2x | 235.2x | 3.8x | 100.6x |
| invoice arithmetic | 9.7x | 15.5x | 2.3x | 28.8x |
| file transform | 124.2x | 330.2x | 11.9x | 65.4x |

No job scaled down: the slowest single run (word count, `planes.py`,
5.64 s) stayed well inside the ~60 s budget H7 sets before a size is
reduced.

### Why each job is shaped the way it is

Planes has no `range`/repeat construct ("Planes iterates collections, not
ranges" — `grammar/json.planes`) and no dict/map. `for each` walks an
existing collection or a string's code points; nothing manufactures a
collection from a bare count. That shapes all four Planes programs:

- **word count** — no `split`, so the program walks the generated text one
  code point at a time, accumulating the current word, and bumps one named
  counter per vocabulary word when it hits a space or newline (ten
  counters, one per word in a weighted-but-fixed vocabulary — the same
  shape `corpus/histogram.planes` already uses for its three score bands).
  Counting inline, rather than first building a list of all 50,000 words
  via repeated `plus`, is not a stylistic choice: `plus` is `base + [item]`
  (`interp.py`, `ListPlus`) — an O(n) copy per append — so building that
  list first cost 50 seconds instead of 5.6 in an early version of this
  program. That cost is real and worth naming even though the shipped
  version avoids it: an O(n²) trap sits directly behind the obvious way to
  write "collect the words," and nothing in the language warns you before
  you hit it.
- **record updates** — 2,000 `{id, value}` records, baked into the Planes
  source as a literal list (there is no other way to get 2,000 items into
  a Planes program that didn't read them from somewhere). Each record's
  `value` is bumped 50 times via `with`, which copies the whole record
  every time (`interp.py`'s `RecordWith`: `{**base.value, **updates}`).
  Python and JS mutate the dict/object field in place — the fair idiomatic
  choice for each language, and exactly the asymmetry being measured, not
  an artificial handicap against Planes.
- **invoice arithmetic** — 5,000 `{qty, price}` lines, again a literal
  list. Planes sums `qty * price + qty * price * tax-rate` over all lines
  in exact rational arithmetic and rounds once at the end (`round … to 2
  places`, half away from zero). Python's fair idiomatic choice for money
  is `decimal.Decimal`, not float — float would drift from an exact
  rational sum over 5,000 lines. JS's fair idiomatic choice is integer
  arithmetic (`BigInt` cents, scaled by 100 again so the 8% tax divides
  out evenly with no remainder — see `gen_jobs.py`'s `gen_invoice_mjs`
  (the generated `invoice.mjs`'s own comment explains why that scale is
  exact for these inputs). All three land on the same
  total, `2854966.72`, before any language-specific rounding could
  disagree.
- **file transform** — Planes has no `split`, so the CSV parse is another
  one-code-point-at-a-time scan, tracking which of the four columns
  (`id,name,qty,price`) is being read. `write` always JSON-encodes its
  argument (`interp.py`'s `WriteTo`: `payload = to_json(value.value)`), so
  the Planes output file holds a JSON string, not raw CSV text — the
  plain Python/JS versions write the CSV text directly, and the harness
  JSON-decodes the Planes side before comparing. This is a real property
  of `write`, not a benchmarking wrinkle: any Planes program that writes
  text produces a JSON-quoted file.

### A real gap this surfaced: no real-filesystem host in the JS CLI

`js/cli.mjs run` and `run-file` both construct a `TestHost` — in-memory
files, not the real filesystem. `js/host_node.mjs` ships a `NodeHost` that
*does* read and write real files (the JS analogue of `host.py`'s
`PythonHost`/`CliHost`), but nothing in `js/cli.mjs` wires it to `run` or
`run-file` — `NodeHost` today backs only the low-level `host <op>` probe
subcommand. So the word-count and file-transform jobs' `planes-js` runs
pass their input pre-loaded into a hostconfig JSON's `files` map (built by
the harness, not timed) rather than letting Planes' own `read` touch a
real file, and the file-transform job's write lands in the JSON result's
`files` map instead of on disk. The measured numbers are still real
interpreter time — the difference is where the bytes for `read`/`write`
live — but a user today has no single-command way to run a real `.planes`
file against the real filesystem on the JS host the way `python3
planes.py file.planes` does. Worth a follow-up; out of scope for H7 itself.

---

## Set B — effect-surface time over the corpus

51 programs, `corpus/*.planes`.

| | python (`shapes_cli.py --json`) | node (`js/cli.mjs shapes`) |
|---|---:|---:|
| median per file | 56.75 ms | 87.25 ms |
| total (sum of per-file medians) | 2894.24 ms | 4449.97 ms |
| process startup, separately (`python3 -c "pass"` / `node -e ""`, median of 5) | 27.81 ms | 58.40 ms |
| implied analysis time per file (median − startup) | ~28.9 ms | ~28.9 ms |

Once process startup is set aside, Python and Node spend almost exactly
the same time analysing a corpus file — the startup gap (Node's is about
30 ms higher) accounts for nearly all of the raw per-file difference.

**Foreign boundary fraction.** Defined precisely from the `--json` surface:
a program **crosses a foreign boundary** if its `effects` array contains at
least one entry with `"declared": true` — an effect that came from a
`foreign … doing …` line's claim, not one the analyser derived from a
builtin it understands (`shapes.py`'s effect construction sets `declared`
exactly there).

- **3 of 51 programs (5.88%)** cross a foreign boundary by that
  definition: `capability-manifest.planes`, `env-config.planes`,
  `retry-schedule.planes`.
- Separately, **4 of 51 (7.84%)** contain a literal `foreign …` line in
  source — one more than the `declared` count.
  `fastest-responses.planes` is the difference: its `foreign ranked of xs
  from "builtins.sorted" doing nothing` claims zero effects, so it
  contributes nothing to the effect surface and is not counted as crossing
  a boundary under the JSON-derived definition, even though the source
  names a foreign function. Both counts are reported because they answer
  different questions ("does this program declare a foreign function" vs.
  "does its surface show a boundary crossing"); the `declared` figure is
  the one H7 asks for.

Python and JS agreed on `declared` for all 51 files (checked by
`set_b_bench.py` as it ran, not just assumed).

Full per-file numbers: see `set_a_bench.py`/`set_b_bench.py`'s `--out`
JSON, or rerun as above.
