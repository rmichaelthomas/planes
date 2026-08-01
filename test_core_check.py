"""S3d (build 3), Phase 6 — the core-conformance checker (A.4).

core_check.py confirms grammar/interp.planes uses nothing outside the declared
core (grammar/core.json) — the last outstanding obligation from the core-subset
ruling. These tests pin: it conforms today, it has teeth (a non-core construct
fails it), `with` is confirmed used, all seven effect kinds are used, and the
core size it reports is the port surface for a second host.

THE SECOND HALF, added when the hand-edited files got the gate the generated
ones already had. core.json is hand-edited and drifted: it said "11 of 12"
builtins after the thirteenth was added, and `root` sat in neither its core
list nor its `excluded_builtins` map, so a builtin was outside the core with
no recorded reason and nothing said so. The checker already printed both
numbers without comparing them. The tests below pin the comparison — a builtin
that is neither core nor explained fails the gate, end to end, against a
crafted core.json rather than by mutating the real one.
"""
import json
import subprocess
import sys

import core_check
from lexer import EFFECT_KINDS, KEYWORDS
from parser import BUILTIN_NAMES

REPO = "."


def _run(path=None, core=None):
    args = [sys.executable, "core_check.py"] + ([path] if path else [])
    if core:
        args += ["--core", core]
    return subprocess.run(args, capture_output=True, text=True, cwd=REPO)


def _real_core():
    with open("grammar/core.json", encoding="utf-8") as f:
        return json.load(f)


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
    # 28 of 32 keywords, eleven of the 13 builtins, all 7 effect kinds — larger
    # than the "half the keywords / 3 builtins" CORE_SUBSET.md predicted.
    kw, blt, core = core_check.load_core()
    assert len(kw) == 28
    assert len(blt) == 11
    assert core["effect_kinds_all_core"] is True
    r = _run()
    assert "keywords    : 28 of 32" in r.stdout
    # 11 of 13: interp.planes uses eleven builtins (`number` among them, A-Q19
    # -- it delegates to the host the same way `whole` and the rest already
    # do) and provably avoids two, `sine` and `root`, because it IMPLEMENTS
    # both rather than calling them (§5.5, and the square-root section).
    assert "builtins    : 11 of 13" in r.stdout


def test_core_json_excludes_exactly_let_rule_when_why():
    core = _real_core()
    assert set(core["excluded_keywords"]) == {"let", "rule", "when", "why"}


def test_core_json_excludes_exactly_sine_and_root_and_says_why():
    """The slot that was empty while two builtins sat outside the core. A
    reason a loader can read, not prose in a `size` string."""
    core = _real_core()
    assert set(core["excluded_builtins"]) == {"sine", "root"}
    for name, reason in core["excluded_builtins"].items():
        assert len(reason) > 40, f"{name}'s exclusion has no reason: {reason!r}"


# ---- the drift guard --------------------------------------------------------


def test_the_real_core_json_does_not_drift():
    assert core_check.drift(_real_core(), KEYWORDS, BUILTIN_NAMES,
                            EFFECT_KINDS) == []


def test_a_builtin_in_neither_list_is_a_drift():
    """The finding that `root` was for two builds. Not "the count is wrong" —
    the count can be corrected by hand and go stale again; this one cannot be
    silenced without recording a reason."""
    core = _real_core()
    core["builtins"] = [b for b in core["builtins"] if b != "count"]
    core["size"]["builtins"] = "10 of 13"
    found = core_check.drift(core, KEYWORDS, BUILTIN_NAMES, EFFECT_KINDS)
    assert any("'count' is in neither" in f for f, _ in found), found


def test_a_keyword_in_neither_list_is_a_drift():
    core = _real_core()
    core["keywords"] = [k for k in core["keywords"] if k != "give"]
    core["size"]["keywords"] = "27 of 32"
    found = core_check.drift(core, KEYWORDS, BUILTIN_NAMES, EFFECT_KINDS)
    assert any("'give' is in neither" in f for f, _ in found), found


def test_a_core_name_the_vocabulary_no_longer_has_is_a_drift():
    core = _real_core()
    core["builtins"] = core["builtins"] + ["frobnicate"]
    found = core_check.drift(core, KEYWORDS, BUILTIN_NAMES, EFFECT_KINDS)
    assert any("'frobnicate', which the vocabulary does not have" in f
               for f, _ in found), found


def test_a_name_both_core_and_excluded_is_a_drift():
    core = _real_core()
    core["excluded_builtins"] = dict(core["excluded_builtins"],
                                     count="a contradiction")
    found = core_check.drift(core, KEYWORDS, BUILTIN_NAMES, EFFECT_KINDS)
    assert any("'count' is in both" in f for f, _ in found), found


def test_a_size_string_that_disagrees_with_the_real_numbers_is_a_drift():
    """The literal drift this build found: "11 of 12" against thirteen
    builtins. The integers are compared, not the prose around them."""
    core = _real_core()
    core["size"]["builtins"] = (
        "11 of 12 -- interp.planes delegates every ordinary builtin to the "
        "host")
    found = core_check.drift(core, KEYWORDS, BUILTIN_NAMES, EFFECT_KINDS)
    assert any("says 11 of 12; the real numbers are 11 of 13" in f
               for f, _ in found), found


def test_prose_after_the_size_numbers_is_not_a_drift():
    """The reason a `size` string carries is not parsed — only its two
    integers are. Otherwise the guard would fail on its own explanation."""
    core = _real_core()
    core["size"]["builtins"] = "11 of 13 -- any words at all, freely rewritten"
    assert core_check.drift(core, KEYWORDS, BUILTIN_NAMES, EFFECT_KINDS) == []


def test_the_guard_fails_the_gate_end_to_end(tmp_path):
    """Non-zero exit and a message naming the builtin, from a crafted
    core.json on disk — the checker's exit code is what CI reads.

    The crafted file is the defect as it actually shipped: `root` deleted
    from `excluded_builtins`, which is the state main was in for two builds.
    interp.planes does not use `root`, so nothing else fails — the run is
    non-zero on the drift alone."""
    core = _real_core()
    core["excluded_builtins"] = {k: v for k, v in
                                 core["excluded_builtins"].items()
                                 if k != "root"}
    p = tmp_path / "core.json"
    p.write_text(json.dumps(core), encoding="utf-8")

    r = _run(core=str(p))
    assert r.returncode == 1, r.stdout
    assert "interp.planes conforms" in r.stdout, r.stdout
    assert "1 DRIFT(S)" in r.stdout, r.stdout
    assert "builtin 'root' is in neither \"builtins\"" in r.stdout, r.stdout
    assert '"excluded_builtins"' in r.stdout, r.stdout
    # It names the file to edit rather than guessing which list it belongs in.
    assert "grammar/core.json" in r.stdout, r.stdout


def test_the_drift_block_is_separate_from_the_conformance_block():
    """Two failures that mean different things, reported apart: interp.planes
    using something it may not, and core.json describing another language."""
    r = _run()
    assert "interp.planes conforms" in r.stdout
    assert "agrees with the vocabulary" in r.stdout


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
