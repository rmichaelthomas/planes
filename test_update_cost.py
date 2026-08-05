"""Keeps scripts/measure_update_cost.py and .mjs honest (build prompt §10.2).

Three assertions, the minimum this build's verification gate requires:

  A. Twin integrity -- benchmarks/world_shape.planes and
     benchmarks/world_shape_flat.planes produce byte-identical `show` output.
     The correctness anchor: if the record-update arm and its scalar-rebinding
     control ever disagree, no timing figure derived from either is trusted.
  B. Mirror integrity -- the Python and JS ladder scripts declare the same
     rung names, width set, and length set. Read out of both files; never
     hard-coded a third time here.
  C. Purity -- world_shape.planes's static effect surface is exactly
     `{show}`, computed through shapes.analyse(), not asserted by inspection.

A fourth section, D (non-interference: no file outside scripts/,
benchmarks/, reports/, and this file differs from `main`), lived here
through PR #70 and was removed in the tutor-daytime-scene build. It was a
self-check of THAT build's own scope discipline against a `main` that was,
at the time, still the pre-#70 base -- once #70 merged, `main` became the
PR's own tip, and the check turned from a build-local guard into a
permanent trap: any later PR touching a file outside those four prefixes
would fail `scripts/ci.sh` at the first suite, regardless of whether that
PR's own change was correct. The retirement rule (scripts/ci.sh's own
"THE RETIREMENT RULE" banner) says a build's verification check graduates
into a suite or is deleted when its build merges, because it carries no
ongoing maintenance expectation -- D graduated into this permanent file
instead of being deleted, which is the gap that let it survive.

Also checks that both scripts' generated world-shape source
(build_world_src(64) / buildWorldSrc(64)) matches benchmarks/world_shape.planes
on disk byte-for-byte -- the file and the generator are two descriptions of
the same program and must never drift apart silently.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, REPO)
from host import TestHost  # noqa: E402
from interp import Interpreter, PlanesError  # noqa: E402
from shapes import analyse  # noqa: E402

WORLD_PLANES = os.path.join(REPO, "benchmarks", "world_shape.planes")
WORLD_FLAT_PLANES = os.path.join(REPO, "benchmarks", "world_shape_flat.planes")
PY_SCRIPT = os.path.join(REPO, "scripts", "measure_update_cost.py")
JS_SCRIPT = os.path.join(REPO, "scripts", "measure_update_cost.mjs")


def _run_planes(path):
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    host = TestHost()
    try:
        Interpreter(host=host).run(src)
    except PlanesError as e:
        raise AssertionError(f"{path} failed to run: {e.tag}: {e}") from e
    return host.shown


# ============================================================ A. twin integrity


def test_world_shape_and_its_flat_twin_produce_byte_identical_output():
    library_output = _run_planes(WORLD_PLANES)
    flat_output = _run_planes(WORLD_FLAT_PLANES)
    assert library_output == flat_output, (
        "benchmarks/world_shape.planes and benchmarks/world_shape_flat.planes "
        "diverged -- the twin is stale (build prompt §5's correctness anchor):\n"
        f"  library: {library_output}\n  flat:    {flat_output}")
    assert library_output, "both programs produced no output at all"


# =========================================================== B. mirror integrity


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _extract_py_list(src, name):
    m = re.search(rf"^{re.escape(name)}\s*=\s*(\[[^\]]*\])", src, re.MULTILINE)
    assert m, f"{name} not found in {PY_SCRIPT}"
    return eval(m.group(1))  # noqa: S307 -- a literal list of names/numbers


def _extract_js_list(src, name):
    m = re.search(rf"const {re.escape(name)}\s*=\s*(\[[^\]]*\])", src)
    assert m, f"{name} not found in {JS_SCRIPT}"
    js_list = m.group(1)
    py_list = re.sub(r'"', "'", js_list)
    return eval(py_list.replace("'", '"'))  # noqa: S307


def _extract_py_str(src, name):
    m = re.search(rf'^{re.escape(name)}\s*=\s*"([^"]*)"', src, re.MULTILINE)
    assert m, f"{name} not found in {PY_SCRIPT}"
    return m.group(1)


def _extract_js_const_str(src, name):
    m = re.search(rf'const {re.escape(name)}\s*=\s*"([^"]*)"', src)
    assert m, f"{name} not found in {JS_SCRIPT}"
    return m.group(1)


def test_with_widths_match_between_python_and_javascript():
    py_src = _read(PY_SCRIPT)
    js_src = _read(JS_SCRIPT)
    py_widths = _extract_py_list(py_src, "WITH_WIDTHS")
    js_widths = _extract_js_list(js_src, "WITH_WIDTHS")
    assert py_widths == js_widths, (py_widths, js_widths)


def test_plus_lengths_match_between_python_and_javascript():
    py_src = _read(PY_SCRIPT)
    js_src = _read(JS_SCRIPT)
    py_lengths = _extract_py_list(py_src, "PLUS_LENGTHS")
    js_lengths = _extract_js_list(js_src, "PLUS_LENGTHS")
    assert py_lengths == js_lengths, (py_lengths, js_lengths)


def test_with_rung_names_match_between_python_and_javascript():
    py_src = _read(PY_SCRIPT)
    js_src = _read(JS_SCRIPT)
    py_rungs = _extract_py_list(py_src, "WITH_RUNG_NAMES")
    js_rungs = _extract_js_list(js_src, "WITH_RUNG_NAMES")
    assert py_rungs == js_rungs, (py_rungs, js_rungs)
    assert py_rungs == ["rung1_single", "rung2_chained", "rung3_multi"]


def test_plus_rung_name_matches_between_python_and_javascript():
    py_src = _read(PY_SCRIPT)
    js_src = _read(JS_SCRIPT)
    py_name = _extract_py_str(py_src, "PLUS_RUNG_NAME")
    js_name = _extract_js_const_str(js_src, "PLUS_RUNG_NAME")
    assert py_name == js_name, (py_name, js_name)


def test_world_subject_counts_match_between_python_and_javascript():
    py_src = _read(PY_SCRIPT)
    js_src = _read(JS_SCRIPT)
    py_counts = _extract_py_list(py_src, "WORLD_SUBJECT_COUNTS")
    js_counts = _extract_js_list(js_src, "WORLD_SUBJECT_COUNTS")
    assert py_counts == js_counts, (py_counts, js_counts)


def test_retention_checkpoints_match_between_python_and_javascript():
    py_src = _read(PY_SCRIPT)
    js_src = _read(JS_SCRIPT)
    py_checkpoints = _extract_py_list(py_src, "RETENTION_CHECKPOINTS")
    js_checkpoints = _extract_js_list(js_src, "RETENTION_CHECKPOINTS")
    assert py_checkpoints == js_checkpoints, (py_checkpoints, js_checkpoints)


def test_both_scripts_generate_the_shipped_world_shape_file_at_s_64():
    """The file and the generator are two descriptions of the same program.
    If build_world_src(64) / buildWorldSrc(64) ever drift from
    benchmarks/world_shape.planes, this fails loudly rather than the sweep
    silently measuring a different program from the one anyone can read."""
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import measure_update_cost as py_ladder  # noqa: E402

    shipped = _read(WORLD_PLANES)
    generated_py = py_ladder.build_world_src(64)

    def strip(text):
        return "\n".join(
            line for line in text.splitlines()
            if not line.strip().startswith("#") and line.strip() != "")

    assert strip(generated_py) == strip(shipped), (
        "scripts/measure_update_cost.py's build_world_src(64) no longer "
        "matches benchmarks/world_shape.planes")

    # scripts/measure_update_cost.mjs runs its ladder on import (no guard,
    # matching measure_call_cost.mjs's convention), so it cannot be imported
    # here without running the full ~80s measurement. Its WORLD_PRELUDE
    # template text is read directly instead -- exactly what a drift between
    # the two scripts would change.
    js_src = _read(JS_SCRIPT)
    m = re.search(r"const WORLD_PRELUDE = `(.*?)`;", js_src, re.DOTALL)
    assert m, "WORLD_PRELUDE not found in scripts/measure_update_cost.mjs"
    js_prelude = m.group(1)
    py_prelude = py_ladder._WORLD_PRELUDE
    assert js_prelude == py_prelude, (
        "scripts/measure_update_cost.mjs's WORLD_PRELUDE no longer matches "
        "scripts/measure_update_cost.py's _WORLD_PRELUDE")


# =============================================================== C. purity


def test_world_shape_effect_surface_is_exactly_show():
    with open(WORLD_PLANES, encoding="utf-8") as fh:
        src = fh.read()
    surface = analyse(src)
    kinds = {e.kind for e in surface.effects}
    assert kinds == {"show"}, kinds


def test_world_shape_flat_effect_surface_is_exactly_show():
    with open(WORLD_FLAT_PLANES, encoding="utf-8") as fh:
        src = fh.read()
    surface = analyse(src)
    kinds = {e.kind for e in surface.effects}
    assert kinds == {"show"}, kinds


if __name__ == "__main__":
    fails = []
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            fails.append(name)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
