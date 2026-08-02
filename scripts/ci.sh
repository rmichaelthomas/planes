#!/usr/bin/env bash
# scripts/ci.sh — the CI gate for this repo.
#
# No CI configuration (GitHub Actions, etc.) existed when this script was
# added (grammar-as-data-and-scoped-amber, addendum v4.2 §69.1/§69.5), so
# this is that gate until one exists: run it locally, or point a CI
# workflow at it. Every step below exits non-zero on failure; the first
# failure stops the script (`set -e`).
#
# C4/A: every step is timed, and the timings are written to `.ci-logs/`. The
# gate's cost was guessed for several builds before it was measured; once it
# was, half of it turned out to be the suite running itself a second time
# (see scripts/run_suites.py). Keep the measurement so the next answer is
# also measured.
#
# Usage:
#   scripts/ci.sh          the gate
#   scripts/ci.sh --fast   iteration tier — skips the slowest suites (below)
#
# PLANES_JOBS=1 forces the serial suite run, which is the pre-parallel
# behaviour and the way to get exact attribution out of the leak check.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

FAST=0
if [ "${1:-}" = "--fast" ]; then FAST=1; fi

# The `--fast` tier: the slowest suites, which accounted for 80.2% of the
# serial suite time when this list stood at eleven entries (193.9 s total,
# measured on 10 cores after A.1 and A.2 landed; see gate-timing-post.md).
# Each line carries its measured cost so a reader can see why it is here and
# re-derive the list from .ci-logs/timings.tsv. The count is NOT written down
# here or in the banner below — it is read off the list, because the list grew
# to twelve and the two prose copies of "eleven" did not.
#
# --fast IS NOT THE GATE. It is for iterating on a change without waiting for
# the JavaScript agreement suites. Nothing may be merged on it: it skips the
# cross-implementation agreement that invariant 2 exists to enforce.
#
# ---------------------------------------------------------------------------
# THE RETIREMENT RULE (C6 / Ruling 3), stated where the next build reads it:
#
#   A VERIFICATION SCRIPT GRADUATES INTO A SUITE OR IS DELETED WHEN ITS BUILD
#   MERGES. There is no third option, in any language: no `verify_*.py` and no
#   `verify-*.mjs`. The rule was first written for Python because that is the
#   shape the problem had; three JavaScript builds then shipped
#   `scripts/verify-*.mjs`, one of which reported BLOCKING FAILURE on green
#   main for two builds because nothing ran it. `test_gate.py` now matches the
#   NAME in either spelling and every executable extension.
#
# A build's verification script is not product code and carries no maintenance
# expectation, so a kept one is a stale assertion waiting to mislead. Seven of
# them accumulated here and NOTHING ran any of them — not this script, not any
# suite. By the time C6 counted, two were already broken on main:
# `verify_annotation.py` asserted a reserved-word ceiling of 30 (it is 32) and
# `verify_grammar_and_amber.py` crashed outright, and one had asserted the
# opposite of the shipped `path` convention for a whole build.
#
# The remedy is not a fifth mechanism to watch. Every assertion worth failing a
# build over a year from now belongs in a suite this script runs — a
# `test_*.py`, where C5's silent-suite guard already covers it, or a
# `js/test/*.test.mjs`, which the `node --test` step below runs — and
# everything else has served its purpose and goes. `test_gate.py` asserts that
# no unrun verification script comes back.
# ---------------------------------------------------------------------------
FAST_SKIP=(
  --skip test_batch_equivalence.py         # 35.0s
  --skip test_js_render.py                 # 32.7s
  --skip test_interp_effects_in_planes.py  # 23.1s
  --skip test_js_shapes.py                 # 20.3s
  --skip test_js_metacircular.py           # 16.0s
  --skip test_why_in_planes.py             # 11.3s
  --skip test_js_interp.py                 # 10.6s
  --skip test_corpus.py                    # 10.3s
  --skip test_js_parser.py                 # 10.3s
  --skip test_js_lexer.py                  #  8.6s
  --skip test_js_json.py                   #  7.6s
  --skip test_interp_statements_in_planes.py  # 4.8s
)

# Preflight (C6 / A.4). The gate's last two steps invoke `ruff` and `mypy`
# bare, and this repo keeps both in ./.venv rather than on the default PATH. A
# fresh shell therefore died at step nine with `command not found` — after the
# whole suite, the JS tests and every checker had already run, which is the
# most expensive possible place to learn that a linter is missing.
#
# It FAILS rather than skipping, deliberately. `node` is the one thing this
# gate lets skip; a green gate that silently type-checked nothing is the same
# dishonesty about its own coverage that the silent-suite guard exists to
# prevent. The point is not that a missing linter is fatal — it is that you
# find out at step one, with a sentence you can act on.
NEED="ruff"
FAST_ARG=""
if [ "$FAST" -eq 1 ]; then
  FAST_ARG=" --fast"                       # --fast does not run mypy
else
  NEED="$NEED mypy"
fi
MISSING=""
for tool in $NEED; do
  command -v "$tool" >/dev/null 2>&1 || MISSING="$MISSING $tool"
done
if [ -n "$MISSING" ]; then
  echo "ci.sh: not on PATH:${MISSING}" >&2
  echo "  this repo keeps them in ./.venv, which is not activated in this shell." >&2
  echo "  run the gate with:" >&2
  echo "      PATH=\"\$PWD/.venv/bin:\$PATH\" scripts/ci.sh${FAST_ARG}" >&2
  echo "  or activate it first:  source .venv/bin/activate" >&2
  if [ ! -d .venv ]; then
    echo "  (no ./.venv here either — create one: python3 -m venv .venv &&" >&2
    echo "   .venv/bin/pip install$MISSING)" >&2
  fi
  exit 1
fi

mkdir -p .ci-logs
TIMING_FILE="$PWD/.ci-logs/steps.tsv"
: > "$TIMING_FILE"
CI_START=$(python3 -c 'import time;print(time.time())')

# timed <label> <command...>   — run it, print and record its wall time.
# timed_soft is the same but never fails the gate: two steps below are
# reports by construction (invariants 6 and 7) and must stay that way.
timed() {
  local label=$1; shift
  local s e
  s=$(python3 -c 'import time;print(time.time())')
  "$@"
  e=$(python3 -c 'import time;print(time.time())')
  python3 -c "print('   [%6.2fs] %s' % ($e-$s, '$label'))"
  python3 -c "print('%s\t%.3f' % ('$label', $e-$s))" >> "$TIMING_FILE"
}

timed_soft() {
  local label=$1; shift
  local s e
  s=$(python3 -c 'import time;print(time.time())')
  "$@" || true
  e=$(python3 -c 'import time;print(time.time())')
  python3 -c "print('%s\t%.3f' % ('$label', $e-$s))" >> "$TIMING_FILE"
}

echo "== test suite =="
if [ "$FAST" -eq 1 ]; then
  echo "   (--fast: iteration tier, NOT the gate — $((${#FAST_SKIP[@]} / 2)) slowest suites skipped)"
  timed "test suite (--fast)" python3 scripts/run_suites.py "${FAST_SKIP[@]}"
else
  timed "test suite" python3 scripts/run_suites.py
fi

echo "== js test enumeration (what exists vs what the glob below runs) =="
# C5 / Ruling 1, the JavaScript half. The glob on the `node --test` line covers
# one directory, non-recursively, and until now nothing counted how many JS test
# files EXIST against how many were run. This step does, and it fails the gate
# — it is pure Python, so it runs whether or not node is on PATH, and it reads
# the glob out of this file rather than restating it.
timed check_js_tests python3 scripts/check_js_tests.py

echo "== js/test (node --test) =="
# C4: these 47 tests existed and NOTHING ran them — not this script, not any
# test_js_*.py, not any other script. Found while removing a dead host method
# whose only remaining coverage lived here. Third instance in this build of the
# same failure REPORT_HOST_BOUNDARY.md §5 records: a test that exists, passes,
# and is never executed by the gate.
if command -v node >/dev/null 2>&1; then
  timed "js/test" node --test js/test/*.mjs
else
  echo "   (node not on PATH — skipped)"
fi

echo "== audit_locked_vs_built.py =="
timed audit_locked_vs_built python3 audit_locked_vs_built.py

echo "== grammar_gen.py --check =="
timed grammar_gen python3 grammar_gen.py --check

echo "== protocol_gen.mjs --check (protocol/*.json against js/paint/protocol.mjs and stream.mjs) =="
if command -v node >/dev/null 2>&1; then
  timed protocol_gen node scripts/protocol_gen.mjs --check
else
  echo "   (node not on PATH — skipped)"
fi

echo "== core_check.py (interp.planes stays inside the declared core) =="
timed core_check python3 core_check.py
# C1: interp.planes now `use`s grammar/json.planes, so that file is part of the
# port surface a second host must implement and is held to the same core.
timed core_check_json python3 core_check.py grammar/json.planes

echo "== check_derived_claims.py (a hand-written claim vs the machine-derived state it describes) =="
# derived-surface-audit: grammar/README.md's D2 doctrine (hand-edited source,
# generated projection, checked in CI) generalised past grammar/ -- four
# instances found by reading, none by any check, until this one. A gate, not
# a report: an unfixed instance of the class is exactly as much a build
# break as core_check.py's drift guard is.
timed check_derived_claims python3 scripts/check_derived_claims.py

echo "== errors coverage (every catalogued error names its fix; a report) =="
# C2: three states now — names a fix, deliberately names none, and should name
# one and does not. The last is the only one that is a work list, and its
# target is zero.
# A.5 / invariant 6: `errors name the fix` is measured, never enforced. A
# message with no fix clause is work to schedule, not a build to break, and an
# honest one-line error should not be un-committable. The checker exits 0 by
# construction; timed_soft says so twice.
timed_soft errors_coverage python3 errors_coverage.py

echo "== corpus coverage (S7 — a report, never a gate) =="
# A.2 / invariant 7: coverage over corpus/ is reported, never enforced. A gap is
# a fact to weigh, not a build break; timed_soft keeps set -e from ever letting
# this fail the gate.
timed_soft corpus_coverage python3 corpus_coverage.py

echo "== ruff =="
timed ruff ruff check .

if [ "$FAST" -eq 0 ]; then
  echo "== mypy =="
  timed mypy mypy .
fi

CI_END=$(python3 -c 'import time;print(time.time())')
python3 -c "print('\nall checks passed in %.1fs' % ($CI_END-$CI_START))"
