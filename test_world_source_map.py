"""test_world_source_map.py — Horizon Phase 0 Build 2, Phase 2.

Covers the build prompt's §4 acceptance: every record an emitting program
produces carries a `sourceMapTarget` that resolves to real Planes source —
an unresolvable path fails the test, not a warning.
"""
import sys

import world_source_map as wsm
from host import TestHost
from interp import Interpreter

DEMO = "world_runtime_demo.planes"


def test_format_source_map_path_is_repo_relative():
    path = wsm.format_source_map_path("/Users/x/planes/world_runtime_demo.planes", 59)
    # Only the tail is asserted -- the absolute prefix above is a stand-in
    # for whatever this machine's checkout path actually is; what matters
    # is the function strips it down to a repo-relative path.
    assert path.endswith("world_runtime_demo.planes:59")
    assert not path.startswith("/")


def test_format_source_map_path_is_none_with_no_entry_file():
    assert wsm.format_source_map_path(None, 5) is None


def test_the_demo_programs_emitted_affordance_source_map_resolves_to_real_source():
    itp = Interpreter(host=TestHost())
    itp.run_file(DEMO)
    target = itp.world_envelopes[0].normalized["affordance"]["sourceMapTarget"]
    resolved = wsm.resolve_source_map_path(target)
    assert resolved == "show demo-world"


def test_the_resolved_path_points_at_the_top_level_show_not_the_placeholder():
    """The interpreter overwrites the placeholder the demo program wrote
    (`"pending"`) with the real path — proving this is generated
    attribution, not an author-typed guess that happens to be correct."""
    itp = Interpreter(host=TestHost())
    itp.run_file(DEMO)
    target = itp.world_envelopes[0].normalized["affordance"]["sourceMapTarget"]
    assert target != "pending"
    assert ":" in target


def test_a_path_outside_the_repo_refuses_rather_than_silently_failing():
    try:
        wsm.resolve_source_map_path("/etc/hosts:1")
        assert False, "expected a SourceMapError"
    except wsm.SourceMapError as e:
        assert e.tag == "unresolvable-source-map-path"


def test_a_path_naming_a_file_that_does_not_exist_refuses():
    try:
        wsm.resolve_source_map_path("demo/does_not_exist_at_all.planes:1")
        assert False, "expected a SourceMapError"
    except wsm.SourceMapError as e:
        assert e.tag == "unresolvable-source-map-path"


def test_a_path_naming_a_line_past_the_end_of_the_file_refuses():
    try:
        wsm.resolve_source_map_path("world_runtime_demo.planes:999999")
        assert False, "expected a SourceMapError"
    except wsm.SourceMapError as e:
        assert e.tag == "unresolvable-source-map-path"


def test_a_malformed_path_with_no_colon_refuses():
    try:
        wsm.resolve_source_map_path("no-line-number-here")
        assert False, "expected a SourceMapError"
    except wsm.SourceMapError as e:
        assert e.tag == "malformed-source-map-path"


def test_a_malformed_path_with_a_non_numeric_line_refuses():
    try:
        wsm.resolve_source_map_path("world_runtime_demo.planes:soon")
        assert False, "expected a SourceMapError"
    except wsm.SourceMapError as e:
        assert e.tag == "malformed-source-map-path"


def test_format_then_resolve_round_trips_for_every_line_of_a_real_file():
    """§7.3's round-trip guarantee, swept over a whole file rather than one
    line: every line `format_source_map_path` could name for this file
    resolves back to that exact line's text."""
    with open(DEMO, encoding="utf-8") as f:
        lines = f.readlines()
    for i, expected in enumerate(lines, start=1):
        path = wsm.format_source_map_path(DEMO, i)
        assert wsm.resolve_source_map_path(path) == expected.rstrip("\n")


if __name__ == "__main__":
    fails = []
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
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
