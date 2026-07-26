#!/usr/bin/env bash
# scripts/ci.sh — the CI gate for this repo.
#
# No CI configuration (GitHub Actions, etc.) existed when this script was
# added (grammar-as-data-and-scoped-amber, addendum v4.2 §69.1/§69.5), so
# this is that gate until one exists: run it locally, or point a CI
# workflow at it. Every step below exits non-zero on failure; the first
# failure stops the script (`set -e`).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "== test suite =="
fail=0
for f in test_*.py; do
  python3 "$f" || fail=1
done
if [ "$fail" -ne 0 ]; then
  echo "one or more test files failed" >&2
  exit 1
fi

echo "== audit_locked_vs_built.py =="
python3 audit_locked_vs_built.py

echo "== grammar_gen.py --check =="
python3 grammar_gen.py --check

echo "== core_check.py (interp.planes stays inside the declared core) =="
python3 core_check.py

echo "== ruff =="
ruff check .

echo "== mypy =="
mypy .

echo "all checks passed"
