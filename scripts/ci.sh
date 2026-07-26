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

# The `--fast` tier: the eleven suites that account for 80.2% of the serial
# suite time (193.9 s total, measured on 10 cores after A.1 and A.2 landed;
# see gate-timing-post.md). Each line carries its measured cost so a reader
# can see why it is here and re-derive the list from .ci-logs/timings.tsv.
#
# --fast IS NOT THE GATE. It is for iterating on a change without waiting for
# the JavaScript agreement suites. Nothing may be merged on it: it skips the
# cross-implementation agreement that invariant 2 exists to enforce.
FAST_SKIP=(
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
  echo "   (--fast: iteration tier, NOT the gate — 11 slowest suites skipped)"
  timed "test suite (--fast)" python3 scripts/run_suites.py "${FAST_SKIP[@]}"
else
  timed "test suite" python3 scripts/run_suites.py
fi

echo "== audit_locked_vs_built.py =="
timed audit_locked_vs_built python3 audit_locked_vs_built.py

echo "== grammar_gen.py --check =="
timed grammar_gen python3 grammar_gen.py --check

echo "== core_check.py (interp.planes stays inside the declared core) =="
timed core_check python3 core_check.py
# C1: interp.planes now `use`s grammar/json.planes, so that file is part of the
# port surface a second host must implement and is held to the same core.
timed core_check_json python3 core_check.py grammar/json.planes

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
