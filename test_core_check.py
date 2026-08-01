"""S3d (build 3), Phase 6 — the core-conformance checker (A.4).

core_check.py confirms grammar/interp.planes uses nothing outside the declared
core (grammar/core.json) — the last outstanding obligation from the core-subset
ruling. These tests pin: it conforms today, it has teeth (a non-core construct
fails it), `with` is confirmed used, all seven effect kinds are used, and the
core size it reports is the port surface for a second host.
"""
import json
import subprocess
import sys

import core_check

REPO = "."


def _run(path=None):
    args = [sys.executable, "core_check.py"] + ([path] if path else [])
    return subprocess.run(args, capture_output=True, text=True, cwd=REPO)


def test_interp_planes_conforms_to_the_declared_core():
    r = _run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "conforms" in r.stdout


def test_checker_has_teeth_flags_non_core_constructs(tmp_path):
    p = tmp_path / "noncore.planes"
    p.write_text("to f of x:\n  let y = x + 1\n  why y\n  give y\n")
    r = _run(str(p))
    assert r.returncode == 2, r.stdout        # let + why = 2 violations
    assert "non-core keyword 'let'" in r.stdout
    assert "non-core keyword 'why'" in r.stdout


def test_with_is_confirmed_used():
    r = _run()
    assert "CONFIRMED: `with` is used" in r.stdout


def test_all_seven_effect_kinds_confirmed_used():
    r = _run()
    assert "CONFIRMED: all seven effect kinds are used" in r.stdout


def test_reported_core_size_is_the_port_surface():
    # 28 of 32 keywords, eleven of the 12 builtins, all 7 effect kinds — larger
    # than the "half the keywords / 3 builtins" CORE_SUBSET.md predicted.
    kw, blt, core = core_check.load_core()
    assert len(kw) == 28
    assert len(blt) == 11
    assert core["effect_kinds_all_core"] is True
    r = _run()
    assert "keywords    : 28 of 32" in r.stdout
    # 11 of 12: interp.planes uses eleven builtins (`number` among them, A-Q19
    # -- it delegates to the host the same way `whole` and the rest already
    # do) and provably avoids `sine`, because it IMPLEMENTS the series rather
    # than calling it (§5.5).
    assert "builtins    : 11 of 13" in r.stdout


def test_core_json_excludes_exactly_let_rule_when_why():
    with open("grammar/core.json", encoding="utf-8") as f:
        core = json.load(f)
    assert set(core["excluded_keywords"]) == {"let", "rule", "when", "why"}


# A.2: this file had no `__main__` runner, so `python3 test_core_check.py` —
# which is how scripts/ci.sh runs every suite — imported it and exited 0 having
# executed nothing. Six tests sat inside a green gate without running. That is
# the failure REPORT_HOST_BOUNDARY.md §5 records, found here a second time by
# counting suite files (54) against suites that report a result (52).
#
# Two of the six take pytest's `tmp_path`, so the runner supplies one rather
# than skipping them — a runner that silently skipped a fixture case would
# reproduce the same fault one level down.
if __name__ == "__main__":
    import inspect
    import pathlib
    import tempfile

    fails = []
    tests = [(k, f) for k, f in sorted(globals().items())
             if k.startswith("test_")]
    for name, fn in tests:
        params = list(inspect.signature(fn).parameters)
        try:
            if params == ["tmp_path"]:
                with tempfile.TemporaryDirectory() as d:
                    fn(pathlib.Path(d))
            elif params:
                raise AssertionError(
                    f"unsupported fixture(s) {params} — this runner supplies "
                    f"only tmp_path; add it here rather than skipping the test")
            else:
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
