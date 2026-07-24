"""Starts coverage measurement in a subprocess, when asked.

`test_rules.py`'s CLI-exit-code tests invoke `shapes_cli.py` (and
`planes.py`) via `subprocess.run([sys.executable, ...])` -- a separate
process a parent `coverage run` cannot see into on its own. Python's `site`
module imports `sitecustomize` from anywhere on `sys.path` at interpreter
startup (the invoked script's own directory, here the repo root, is on
`sys.path` before that import runs), so this file is the standard hook
coverage.py's own docs describe for subprocess measurement.

`coverage.process_startup()` is a no-op unless `COVERAGE_PROCESS_START` is
set in the environment -- which `subprocess.run` inherits from the parent
by default, so setting it once before a top-level `coverage run` is enough
for every child invocation to pick it up. Safe to leave in place always:
zero effect on a normal run, on a machine without `coverage` installed, or
in CI.
"""
try:
    import coverage
    coverage.process_startup()
except ImportError:
    pass
