"""The Swift host, located for the agreement suites.

Every test_swift_*.py is its test_js_*.py counterpart with `node js/cli.mjs`
swapped for `planes-swift`. This module finds that binary, building it first if
it is missing or older than any Swift source, so a suite never compares against
a stale build. SWIFT is None when there is no Swift toolchain on PATH, and the
suites SKIP then, as the JavaScript ones do without node.
"""
import os
import shutil
import subprocess

SWIFT = shutil.which("swift")
REPO = os.path.dirname(os.path.abspath(__file__))
PACKAGE = os.path.join(REPO, "swift")
BINARY = os.path.join(PACKAGE, ".build", "debug", "planes-swift")


def _newest_source_mtime():
    newest = os.path.getmtime(os.path.join(PACKAGE, "Package.swift"))
    for root, _dirs, files in os.walk(os.path.join(PACKAGE, "Sources")):
        for name in files:
            if name.endswith(".swift"):
                newest = max(newest, os.path.getmtime(os.path.join(root, name)))
    return newest


def binary():
    """The path to a current `planes-swift`, building it if needed."""
    if not os.path.exists(BINARY) or os.path.getmtime(BINARY) < _newest_source_mtime():
        r = subprocess.run([SWIFT, "build", "--package-path", PACKAGE, "--product", "planes-swift"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError(f"swift build failed:\n{r.stdout[-4000:]}\n{r.stderr[-4000:]}")
        # A source whose mtime moved but whose content did not (a checkout, a
        # restored backup) leaves the build a no-op that never relinks, so the
        # binary would stay "older" and every later call would pay for another
        # no-op build. The build just said the binary is current; record that.
        os.utime(BINARY)
    return BINARY


def command(*args):
    """The argv that runs `planes-swift` with `args`."""
    return [binary(), *args]
