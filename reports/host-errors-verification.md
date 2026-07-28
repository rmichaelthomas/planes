# Verification — host-error reachability and the nine fix clauses

Build: `feat/host-error-reachability-and-fix-clauses`, base `f236b0d`.
Source: `reports/REPORT_ERROR_MESSAGES.md`.

## A note on `scripts/verify-host-errors.py`

The build prompt asked for a committed `scripts/verify-host-errors.py`.
`test_gate.py::test_no_verification_script_exists_for_the_gate_not_to_run`
forbids exactly that shape — any `verify_*`/`verify-*` file, any extension,
anywhere in the repo — precisely because seven such scripts once
accumulated here and the gate ran none of them (`test_gate.py` §205's own
account, and `verify-canvas-runtime.mjs`'s two builds of undetected
blocking failure). Its own stated remedy is explicit: move the assertions
into a suite the gate runs, or delete the script. This report does the
former — every assertion below is `test_fix_clause_corrections.py`, a
`test_*.py` the gate already runs — rather than adding an eighth instance
of the thing that rule exists to end.

## A. `read` and `ask` reach a Planes error through the real host

Before this build:

```
$ python3 -c "from interp import Interpreter; Interpreter().run(
    'use file\nlet x = read \"/tmp/does-not-exist-xyz.txt\"')"
FileNotFoundError: [Errno 2] No such file or directory: ...

$ python3 -c "from interp import Interpreter; Interpreter().run(
    'use http\nlet x = ask \"http://does-not-exist.invalid/\"')"
URLError: <urlopen error [Errno 8] nodename nor servname provided, or not known>
```

After (`interp.py`'s `read`/`ask` now catch `(HostError, OSError)`, matching
`write`'s existing pattern — `urllib.error.URLError`/`HTTPError` are
`OSError` subclasses, so no new import was needed):

```
=== A. missing file, real host ===
PlanesError : no-such-file: /var/folders/.../definitely-gone.json
  try: check the path, or write it first

=== B. unreachable url, real host ===
PlanesError : ask-failed: asking 'http://127.0.0.1:1/' failed: <urlopen error [Errno 61] Connection refused>
  try: check the url is reachable and spelled right; a run without the network needs a stubbed response
```

`write` was already correct (`except (HostError, OSError)`) and is
unchanged; confirmed by `test_the_host_receives_file_writes` and the new
`test_missing_file_on_the_real_host_is_a_program_error` /
`test_an_unreachable_url_on_the_real_host_is_a_program_error` (`test_host.py`)
using a real temp path and a local refused connection (port 1 —
deterministic, no real network dependency).

**JS and self-hosted needed no fix.** `host_node.mjs`'s `ask`/`read`
already wrap the real Node failure into `HostError` before `interp.mjs`
ever sees it — confirmed directly (`js/test/interp.test.mjs`'s two new
tests, both against a real `NodeHost`). The self-hosted interpreter either
never touches a real host (`inert` mode, its own in-memory simulation) or
delegates straight through to the enclosing Python/JS host in `real` mode,
with no wrapping of its own to have the same bug — no code change needed
there.

`test_js_host.py:198`'s comment claiming "its HostError surfaces as
no-such-file at the interp layer" was wrong about `PythonHost` (which
raises a bare `OSError`, not a `HostError`, as the same test's own
`except (FileNotFoundError, OSError)` three lines below already showed) —
corrected to describe what's actually true and point at where the
interp-layer check now lives.

## B. The nine corrected fix clauses

All nine, plus the `sine` completeness note, verified three ways in
`test_fix_clause_corrections.py`:

| # | tag | corrected in | self-hosted? |
|---|---|---|---|
| 1 | cannot-compare (nothing) | interp.py, js/interp.mjs, grammar/interp.planes (×2 sites) | yes |
| 3 | cannot-compare (equal() cross-type only — compare() unchanged) | interp.py, js/interp.mjs, grammar/interp.planes | yes |
| 5 | not-a-yes-no | interp.py, js/interp.mjs, grammar/interp.planes | yes (statement-level) |
| 8 | unrecognized-record-format | interp.py | no counterpart |
| 20 | write-failed | interp.py, js/interp.mjs | no counterpart |
| 44 | recursion-too-deep | interp.py, js/interp.mjs | no counterpart (inherited from the outer interpreter) |
| 49 | cannot-combine | interp.py, js/interp.mjs, grammar/interp.planes | yes |
| 52 | not-text (`in` over text) | interp.py, js/interp.mjs, grammar/interp.planes | yes |
| 59 | grammar-data-missing (format version) | lexer.py, js/grammar_data.mjs | no counterpart |
| — | sine (completeness note, not a misdirect) | interp.py, js/interp.mjs, grammar/interp.planes | yes |

Sample, run directly against all three implementations for `[1,2] + 5`
(`cannot-combine`) and `nothing == 5` (`cannot-compare`):

```
Python:  cannot-combine: cannot combine [2 items] with 5 using +
  try: convert first — `text of n` to build text, or `number of t` to do arithmetic — but only for a text/number pairing; if either side is a list or record, neither conversion is meaningful: use `plus` to append to a list, `with` to update a record, or rewrite the expression
JS:      <identical, byte for byte>
self-hosted (metacircular, via grammar/interp.planes's own eval()): <identical, byte for byte>
```

`test_the_nine_corrected_clauses_are_exact_in_python`,
`test_the_nine_corrected_clauses_are_byte_identical_in_javascript`, and
`test_the_corrected_clauses_agree_in_the_self_hosted_interpreter` pin all
nine (plus `sine` and the statement-level `not-a-yes-no` case) this way.

## C. `compare()`'s ordering clause is unchanged

The #3 split: `equal()`'s cross-type clause (`==`) changed;
`compare()`'s (`<` `>` `<=` `>=`) did not, since the audit found it
already correct there — lists and records can never be ordered at all,
same-typed or not:

```
$ show text of ([1] < [2])
cannot-compare: cannot compare [1 items] with [1 items]
  try: compare numbers with numbers, or text with text
```

Unchanged in Python and JS, pinned by
`test_orderings_ordering_clause_did_not_move`. No new tag was needed —
the two sites were never a shared literal, each had (and kept) its own.

## D. Counts and regeneration

- `grammar/errors.json` raw entry count: **119**, unchanged (no raise site
  added or removed — only fix text edited at nine existing sites, plus
  `sine`).
- `python3 grammar_gen.py --check`: clean.
- `errors_coverage.py`'s work lists: still 0 shortfall, both reference and
  self-hosted (`test_error_messages.py`'s `114`-count assertions —
  `kind=="error"` entries only, unaffected by fix-text edits — still pass).
- Full local suite run (`test_error_messages.py`, `test_builtin_guards.py`,
  `test_coverage.py`, and the rest): all green, no suite modified beyond
  what this report and the PR describe.

## Gate checklist (§5.2 of the build prompt, A–F)

- **A.** ✓ — see §A above.
- **B.** ✓ — see §A above.
- **C.** ✓ — `write` unchanged, still correct.
- **D.** ✓ — nine clauses match the report; `compare()` unchanged; `sine`
  now names `number of`.
- **E.** ✓ — byte-identical across all three implementations wherever a
  site has a counterpart in each.
- **F.** ✓ — counts 119 raw / 114 reference-error unchanged; sweep
  unchanged; `errors.json` regenerated via `grammar_gen.py`, never
  hand-edited.
